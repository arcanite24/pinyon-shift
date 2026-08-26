using Microsoft.Win32;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
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
    private CrashReport? _pendingReport;
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
            BuildLocationText.Text = Path.Combine(_repositoryRoot, ".local");
            AppendLog($"Release source: {_repositoryRoot}");
            StageControllerMappings();
            DetectExistingBuild();
            DetectPendingReport();
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
        if (_pendingReport is not null)
        {
            ReportCrash();
            return;
        }
        if (_gameExecutable is not null && File.Exists(_gameExecutable))
        {
            await LaunchGameAsync();
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

    private async Task LaunchGameAsync()
    {
        if (_repositoryRoot is null || _gameExecutable is null) return;
        if (_busy) return;

        _busy = true;
        PrimaryButton.IsEnabled = false;
        PrimaryButton.Content = "GAME RUNNING";
        EyebrowText.Text = "PREVIEW RUNNING";
        HeadlineText.Text = "Enjoy the drive.";
        StatusText.Text = "WATCHING FOR CRASHES";
        StatusDot.Fill = ActiveBrush;
        ReportProblemButton.IsEnabled = false;
        AppendLog("Game started. The launcher is watching for an unexpected exit.");

        try
        {
            var launcher = Path.Combine(_repositoryRoot, "tools", "launch-preview.ps1");
            var startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                WorkingDirectory = _repositoryRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };
            foreach (var argument in new[]
            {
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", launcher,
                "-Configuration", "Release", "-Json"
            }) startInfo.ArgumentList.Add(argument);

            using var watcher = Process.Start(startInfo) ??
                throw new InvalidOperationException("Windows could not start the preview watcher.");
            var outputTask = watcher.StandardOutput.ReadToEndAsync();
            var errorTask = watcher.StandardError.ReadToEndAsync();
            await watcher.WaitForExitAsync();
            var output = await outputTask;
            var error = await errorTask;

            var result = ParseLaunchResult(output);
            if (watcher.ExitCode == 0 && string.Equals(result?.Result, "normal-exit", StringComparison.OrdinalIgnoreCase))
            {
                AppendLog("The game closed normally.");
                SetComplete();
                return;
            }

            DetectPendingReport();
            if (_pendingReport is null && result is not null &&
                !string.IsNullOrWhiteSpace(result.CrashId) &&
                !string.IsNullOrWhiteSpace(result.Bundle) &&
                !string.IsNullOrWhiteSpace(result.IssueUrl))
            {
                SetPendingReport(new CrashReport(result.CrashId, result.Bundle, result.IssueUrl,
                    $"0x{unchecked((uint)result.ExitCode):X8}"));
            }
            if (_pendingReport is null)
                throw new InvalidOperationException(string.IsNullOrWhiteSpace(error)
                    ? "The game exited unexpectedly, but its diagnostic report could not be prepared."
                    : error.Trim());
        }
        catch (Exception ex)
        {
            SetFailure("PREVIEW STOPPED", ex.Message);
        }
        finally
        {
            _busy = false;
            ReportProblemButton.IsEnabled = true;
            UpdatePrimaryButton();
        }
    }

    private static LaunchResult? ParseLaunchResult(string output)
    {
        foreach (var line in output.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries).Reverse())
        {
            try
            {
                var result = JsonSerializer.Deserialize<LaunchResult>(line, new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true
                });
                if (result is not null) return result;
            }
            catch (JsonException) { }
        }
        return null;
    }

    private void DetectPendingReport()
    {
        if (_repositoryRoot is null) return;
        var reportsRoot = Path.GetFullPath(Path.Combine(_repositoryRoot, ".local", "preview", "reports"));
        var marker = Path.Combine(reportsRoot, "pending-report.json");
        if (!File.Exists(marker)) return;
        try
        {
            var report = JsonSerializer.Deserialize<CrashReport>(File.ReadAllText(marker), new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });
            if (report is null || string.IsNullOrWhiteSpace(report.CrashId) ||
                string.IsNullOrWhiteSpace(report.Bundle) || string.IsNullOrWhiteSpace(report.IssueUrl)) return;
            var bundle = Path.GetFullPath(report.Bundle);
            var reportsPrefix = reportsRoot.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            if (!bundle.StartsWith(reportsPrefix, StringComparison.OrdinalIgnoreCase) || !File.Exists(bundle)) return;
            if (!Uri.TryCreate(report.IssueUrl, UriKind.Absolute, out var issueUri) ||
                issueUri.Scheme != Uri.UriSchemeHttps || issueUri.Host != "github.com" ||
                !issueUri.AbsolutePath.StartsWith("/arcanite24/pinyon-shift/issues/new", StringComparison.OrdinalIgnoreCase)) return;
            SetPendingReport(report with { Bundle = bundle, IssueUrl = issueUri.AbsoluteUri });
        }
        catch (IOException) { }
        catch (JsonException) { }
    }

    private void SetPendingReport(CrashReport report)
    {
        _pendingReport = report;
        for (var i = 0; i < _steps.Count; i++)
            _steps[i].SetState(i == _steps.Count - 1 ? StepState.Failed : StepState.Complete,
                WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        EyebrowText.Text = "CRASH REPORT READY";
        HeadlineText.Text = "We caught the crash.";
        StatusText.Text = "REPORT READY";
        StatusDot.Fill = FailedBrush;
        CrashIdText.Text = report.CrashId;
        CrashPanel.Visibility = Visibility.Visible;
        LogPanel.Visibility = Visibility.Collapsed;
        OwnershipCheckBox.Visibility = Visibility.Collapsed;
        ReportProblemButton.Visibility = Visibility.Collapsed;
        OpenLogsButton.Content = "OPEN REPORT FOLDER";
        OpenLogsButton.Visibility = Visibility.Visible;
        PrimaryButton.Content = "REPORT CRASH";
        PrimaryButton.IsEnabled = true;
    }

    private void ReportCrash()
    {
        if (_pendingReport is null || _repositoryRoot is null) return;
        Process.Start(new ProcessStartInfo
        {
            FileName = "explorer.exe",
            UseShellExecute = true,
            Arguments = $"/select,\"{_pendingReport.Bundle}\""
        });
        Process.Start(new ProcessStartInfo(_pendingReport.IssueUrl) { UseShellExecute = true });
        var marker = Path.Combine(_repositoryRoot, ".local", "preview", "reports", "pending-report.json");
        try { if (File.Exists(marker)) File.Delete(marker); } catch (IOException) { }
        StatusText.Text = "GITHUB OPENED";
        PrimaryButton.Content = "OPEN GITHUB AGAIN";
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
        var payloadHash = await Task.Run(async () =>
        {
            await using var stream = File.OpenRead(payload);
            return Convert.ToHexString(await SHA256.HashDataAsync(stream));
        });
        var payloadMarker = Path.Combine(destination, ".pinyon-source-sha256");
        var installedHash = File.Exists(payloadMarker)
            ? (await File.ReadAllTextAsync(payloadMarker)).Trim()
            : string.Empty;
        if (!IsRoot(destination) || !string.Equals(installedHash, payloadHash,
                StringComparison.OrdinalIgnoreCase))
        {
            Directory.CreateDirectory(destination);
            await Task.Run(() => ZipFile.ExtractToDirectory(payload, destination, overwriteFiles: true));
            await File.WriteAllTextAsync(payloadMarker, payloadHash + Environment.NewLine);
        }
        if (!IsRoot(destination))
            throw new InvalidDataException("The release source payload is incomplete.");
        return destination;
    }

    private void StageControllerMappings()
    {
        if (_repositoryRoot is null) return;
        var source = Path.Combine(_repositoryRoot, "config", "gamecontrollerdb.txt");
        var executable = Path.Combine(_repositoryRoot, "out", "build", "win-amd64-release",
            "pinyon_shift.exe");
        if (!File.Exists(source) || !File.Exists(executable)) return;
        var destination = Path.Combine(Path.GetDirectoryName(executable)!, "gamecontrollerdb.txt");
        File.Copy(source, destination, overwrite: true);
        AppendLog("Controller compatibility mappings are current.");
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
        _pendingReport = null;
        foreach (var step in _steps)
            step.SetState(StepState.Complete, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        ProgressText.Text = "100%";
        EyebrowText.Text = "LOCAL BUILD COMPLETE";
        HeadlineText.Text = "The road is open.";
        StatusText.Text = "READY TO PLAY";
        StatusDot.Fill = CompleteBrush;
        PrimaryButton.Content = "PLAY PINYON SHIFT";
        CrashPanel.Visibility = Visibility.Collapsed;
        ReportProblemButton.Visibility = Visibility.Visible;
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
        _pendingReport = null;
        foreach (var step in _steps)
            step.SetState(StepState.Waiting, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        PrimaryButton.Content = "VERIFY & BUILD";
        CrashPanel.Visibility = Visibility.Collapsed;
        ReportProblemButton.Visibility = Visibility.Visible;
        OwnershipCheckBox.Visibility = Visibility.Visible;
    }

    private void UpdatePrimaryButton()
    {
        PrimaryButton.IsEnabled = !_busy && (_pendingReport is not null || _gameExecutable is not null ||
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
        if (_pendingReport is not null)
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = "explorer.exe",
                UseShellExecute = true,
                Arguments = $"/select,\"{_pendingReport.Bundle}\""
            });
            return;
        }
        var logs = Path.Combine(_repositoryRoot, ".local", "logs");
        Directory.CreateDirectory(logs);
        Process.Start(new ProcessStartInfo("explorer.exe", logs) { UseShellExecute = true });
    }

    private void ReportProblemButton_Click(object sender, RoutedEventArgs e) =>
        Process.Start(new ProcessStartInfo(
            "https://github.com/arcanite24/pinyon-shift/issues/new?template=bug.yml")
        { UseShellExecute = true });

    private sealed record ProgressMessage(string? Stage, int Percent, string? Message);
    private sealed record LaunchResult(
        [property: JsonPropertyName("result")] string? Result,
        [property: JsonPropertyName("crash_id")] string? CrashId,
        [property: JsonPropertyName("bundle")] string? Bundle,
        [property: JsonPropertyName("issue_url")] string? IssueUrl,
        [property: JsonPropertyName("exit_code")] long ExitCode);
    private sealed record CrashReport(
        [property: JsonPropertyName("crash_id")] string CrashId,
        [property: JsonPropertyName("bundle")] string Bundle,
        [property: JsonPropertyName("issue_url")] string IssueUrl,
        [property: JsonPropertyName("exit_code_hex")] string? ExitCodeHex);
}
