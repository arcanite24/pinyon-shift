using Microsoft.Win32;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;

namespace PinyonShift.Launcher;

public partial class MainWindow : Window
{
    private readonly ObservableCollection<RouteStep> _steps =
    [
        new("VERIFY", "Disc image", "Exact size and SHA-256", "1"),
        new("TOOLS", "Windows toolchain", "Provisioned when missing", "2"),
        new("EXTRACT", "Local game files", "Never uploaded or modified", "3"),
        new("BUILD", "Native translation", "Generated and compiled here", "4"),
        new("PLAY", "Ready to drive", "Launch from this screen", "5")
    ];

    private CancellationTokenSource? _cancellation;
    private string? _repositoryRoot;
    private string? _gameExecutable;
    private bool _busy;

    private static readonly Brush WaitingBrush = new SolidColorBrush(Color.FromRgb(57, 64, 57));
    private static readonly Brush ActiveBrush = new SolidColorBrush(Color.FromRgb(241, 174, 54));
    private static readonly Brush CompleteBrush = new SolidColorBrush(Color.FromRgb(115, 185, 137));
    private static readonly Brush FailedBrush = new SolidColorBrush(Color.FromRgb(225, 110, 95));

    public MainWindow()
    {
        InitializeComponent();
        RouteList.ItemsSource = _steps;
        BuildLocationText.Text = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PinyonShift");
        Loaded += MainWindow_Loaded;
        Closing += (_, _) => _cancellation?.Cancel();
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
    {
        try
        {
            _repositoryRoot = await ResolveRepositoryRootAsync();
            AppendLog($"Release source: {_repositoryRoot}");
            DetectExistingBuild();
        }
        catch (Exception ex)
        {
            SetFailure("SOURCE UNAVAILABLE", ex.Message);
        }
    }

    private void BrowseButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Choose your Forza Horizon disc image",
            Filter = "Xbox 360 disc image (*.iso)|*.iso|All files (*.*)|*.*",
            CheckFileExists = true,
            Multiselect = false
        };
        if (dialog.ShowDialog(this) == true)
        {
            IsoPathTextBox.Text = dialog.FileName;
            ResetRoute();
            SetReadyState();
        }
        UpdatePrimaryButton();
    }

    private void InputChanged(object sender, RoutedEventArgs e) => UpdatePrimaryButton();

    private async void PrimaryButton_Click(object sender, RoutedEventArgs e)
    {
        if (_gameExecutable is not null && File.Exists(_gameExecutable))
        {
            LaunchGame();
            return;
        }

        if (_busy || _repositoryRoot is null)
            return;

        _busy = true;
        _cancellation = new CancellationTokenSource();
        BrowseButton.IsEnabled = false;
        OwnershipCheckBox.IsEnabled = false;
        PrimaryButton.IsEnabled = false;
        PrimaryButton.Content = "BUILDING…";
        LogPanel.Visibility = Visibility.Visible;
        HeadlineText.Text = "Preparing the road.";
        EyebrowText.Text = "LOCAL BUILD IN PROGRESS";
        StatusText.Text = "WORKING";
        StatusDot.Fill = ActiveBrush;
        AppendLog("Starting local setup. The first build can take a while.");

        try
        {
            var script = Path.Combine(_repositoryRoot, "tools", "setup-preview.ps1");
            if (!File.Exists(script))
                throw new FileNotFoundException("The setup workflow is missing from the release payload.", script);

            var startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                WorkingDirectory = _repositoryRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };
            startInfo.ArgumentList.Add("-NoLogo");
            startInfo.ArgumentList.Add("-NoProfile");
            startInfo.ArgumentList.Add("-ExecutionPolicy");
            startInfo.ArgumentList.Add("Bypass");
            startInfo.ArgumentList.Add("-File");
            startInfo.ArgumentList.Add(script);
            startInfo.ArgumentList.Add("-IsoPath");
            startInfo.ArgumentList.Add(IsoPathTextBox.Text);
            startInfo.ArgumentList.Add("-JsonEvents");

            using var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
            process.OutputDataReceived += (_, args) => Dispatcher.Invoke(() => HandleOutput(args.Data));
            process.ErrorDataReceived += (_, args) => Dispatcher.Invoke(() =>
            {
                if (!string.IsNullOrWhiteSpace(args.Data)) AppendLog(args.Data);
            });
            if (!process.Start())
                throw new InvalidOperationException("Windows could not start the setup process.");
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            using var registration = _cancellation.Token.Register(() =>
            {
                try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            });
            await process.WaitForExitAsync(_cancellation.Token);
            if (process.ExitCode != 0)
                throw new InvalidOperationException("Setup stopped before completing. The build log above contains the cause.");

            DetectExistingBuild();
            if (_gameExecutable is null)
                throw new InvalidOperationException("Setup completed without producing the expected game executable.");
            SetComplete();
        }
        catch (OperationCanceledException)
        {
            SetFailure("BUILD CANCELLED", "No game or source files were uploaded. Run the launcher again to resume.");
        }
        catch (Exception ex)
        {
            SetFailure("SETUP NEEDS ATTENTION", ex.Message);
        }
        finally
        {
            _busy = false;
            BrowseButton.IsEnabled = true;
            OwnershipCheckBox.IsEnabled = true;
            UpdatePrimaryButton();
        }
    }

    private void HandleOutput(string? line)
    {
        if (string.IsNullOrWhiteSpace(line)) return;
        const string prefix = "::pinyon::";
        if (!line.StartsWith(prefix, StringComparison.Ordinal))
        {
            AppendLog(line);
            return;
        }

        try
        {
            var message = JsonSerializer.Deserialize<ProgressMessage>(line[prefix.Length..], new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
            if (message is null) return;
            var index = Array.FindIndex(RouteStep.StageOrder, x =>
                string.Equals(x, message.Stage, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
            {
                for (var i = 0; i < _steps.Count; i++)
                    _steps[i].SetState(i < index ? StepState.Complete : i == index ? StepState.Active : StepState.Waiting,
                        WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
            }
            if (message.Percent is >= 0 and <= 100)
                ProgressText.Text = $"{message.Percent}%";
            if (!string.IsNullOrWhiteSpace(message.Message))
                AppendLog(message.Message);
        }
        catch (JsonException)
        {
            AppendLog(line);
        }
    }

    private void DetectExistingBuild()
    {
        if (_repositoryRoot is null) return;
        var candidate = Path.Combine(_repositoryRoot, "out", "build", "win-amd64-release", "pinyon_shift.exe");
        if (File.Exists(candidate))
        {
            _gameExecutable = candidate;
            SetComplete();
        }
    }

    private void LaunchGame()
    {
        if (_repositoryRoot is null || _gameExecutable is null) return;
        var launcher = Path.Combine(_repositoryRoot, "tools", "launch-preview.ps1");
        Process.Start(new ProcessStartInfo
        {
            FileName = "powershell.exe",
            WorkingDirectory = _repositoryRoot,
            UseShellExecute = true,
            Arguments = $"-NoLogo -NoProfile -ExecutionPolicy Bypass -File \"{launcher}\" -Configuration Release"
        });
    }

    private async Task<string> ResolveRepositoryRootAsync()
    {
        static bool IsRoot(string path) => File.Exists(Path.Combine(path, "config", "supported-dumps.json"))
            && File.Exists(Path.Combine(path, "tools", "setup-preview.ps1"));

        var directory = AppContext.BaseDirectory;
        for (var i = 0; i < 8; i++)
        {
            if (IsRoot(directory)) return directory;
            var parent = Directory.GetParent(directory);
            if (parent is null) break;
            directory = parent.FullName;
        }

        var payload = Path.Combine(AppContext.BaseDirectory, "pinyon-shift-source.zip");
        if (!File.Exists(payload))
            throw new FileNotFoundException("Keep pinyon-shift-source.zip beside the launcher, or run the launcher from a repository checkout.");

        var version = typeof(MainWindow).Assembly.GetName().Version?.ToString(3) ?? "dev";
        var destination = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PinyonShift", "source", version);
        if (!IsRoot(destination))
        {
            Directory.CreateDirectory(destination);
            await Task.Run(() => ZipFile.ExtractToDirectory(payload, destination, overwriteFiles: true));
        }
        if (!IsRoot(destination))
            throw new InvalidDataException("The release source payload is incomplete.");
        return destination;
    }

    private void SetReadyState()
    {
        EyebrowText.Text = "READY FOR YOUR DISC";
        HeadlineText.Text = "Build your preview.";
        StatusText.Text = "SYSTEM READY";
        StatusDot.Fill = CompleteBrush;
    }

    private void SetComplete()
    {
        foreach (var step in _steps)
            step.SetState(StepState.Complete, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        ProgressText.Text = "100%";
        EyebrowText.Text = "LOCAL BUILD COMPLETE";
        HeadlineText.Text = "The road is open.";
        StatusText.Text = "READY TO PLAY";
        StatusDot.Fill = CompleteBrush;
        PrimaryButton.Content = "PLAY PINYON SHIFT";
        OpenLogsButton.Visibility = Visibility.Visible;
        OwnershipCheckBox.Visibility = Visibility.Collapsed;
        AppendLog("Build complete. Generated files remain on this computer.");
    }

    private void SetFailure(string eyebrow, string message)
    {
        var active = _steps.FirstOrDefault(x => x.State == StepState.Active);
        active?.SetState(StepState.Failed, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        EyebrowText.Text = eyebrow;
        HeadlineText.Text = "We stopped safely.";
        StatusText.Text = "ACTION NEEDED";
        StatusDot.Fill = FailedBrush;
        PrimaryButton.Content = "TRY AGAIN";
        LogPanel.Visibility = Visibility.Visible;
        OpenLogsButton.Visibility = Visibility.Visible;
        AppendLog($"ERROR: {message}");
    }

    private void ResetRoute()
    {
        _gameExecutable = null;
        foreach (var step in _steps)
            step.SetState(StepState.Waiting, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        PrimaryButton.Content = "VERIFY & BUILD";
        OwnershipCheckBox.Visibility = Visibility.Visible;
    }

    private void UpdatePrimaryButton()
    {
        PrimaryButton.IsEnabled = !_busy && (_gameExecutable is not null ||
            (_repositoryRoot is not null && File.Exists(IsoPathTextBox.Text) && OwnershipCheckBox.IsChecked == true));
    }

    private void AppendLog(string line)
    {
        LogTextBox.AppendText($"[{DateTime.Now:HH:mm:ss}] {line}{Environment.NewLine}");
        const int maximumLogCharacters = 120_000;
        if (LogTextBox.Text.Length > maximumLogCharacters)
            LogTextBox.Text = LogTextBox.Text[^maximumLogCharacters..];
        LogTextBox.ScrollToEnd();
    }

    private void OpenLogsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_repositoryRoot is null) return;
        var logs = Path.Combine(_repositoryRoot, ".local", "logs");
        Directory.CreateDirectory(logs);
        Process.Start(new ProcessStartInfo("explorer.exe", logs) { UseShellExecute = true });
    }

    private sealed record ProgressMessage(string? Stage, int Percent, string? Message);
}
