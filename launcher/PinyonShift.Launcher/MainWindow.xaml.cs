using Microsoft.Win32;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Windows;
using System.Windows.Controls;
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
    private bool _applyingGraphicsResult;

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
            GraphicsSettingsButton.Visibility = Visibility.Visible;
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
        GraphicsSettingsButton.IsEnabled = false;
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
            GraphicsSettingsButton.IsEnabled = true;
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
        GraphicsSettingsButton.IsEnabled = false;
        PrimaryButton.IsEnabled = false;
        PrimaryButton.Content = "GAME RUNNING";
        EyebrowText.Text = "PREVIEW RUNNING";
        HeadlineText.Text = "Controller A, Space, or left click.";
        StatusText.Text = "WATCHING FOR CRASHES";
        StatusDot.Fill = ActiveBrush;
        ReportProblemButton.IsEnabled = false;
        AppendLog("Game started. The launcher is watching for an unexpected exit.");
        AppendLog("Controls: use controller A, Space, or left click for the selected Xbox menu item; press Enter for Start.");

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
            GraphicsSettingsButton.IsEnabled = true;
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
        GraphicsPanel.Visibility = Visibility.Collapsed;
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
        GraphicsPanel.Visibility = Visibility.Collapsed;
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
        GraphicsPanel.Visibility = Visibility.Collapsed;
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
        GraphicsPanel.Visibility = Visibility.Collapsed;
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

    private async void GraphicsSettingsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_repositoryRoot is null || _busy || _pendingReport is not null) return;
        LogPanel.Visibility = Visibility.Collapsed;
        CrashPanel.Visibility = Visibility.Collapsed;
        GraphicsPanel.Visibility = Visibility.Visible;
        GraphicsStatusText.Text = "Loading current settings…";
        try
        {
            ApplyGraphicsResult(await RunGraphicsSettingsToolAsync("Get"));
            GraphicsStatusText.Text = "Current settings loaded. Saving a change requires a preview restart.";
        }
        catch (Exception ex)
        {
            GraphicsStatusText.Text = $"Settings could not be loaded: {ex.Message}";
        }
    }

    private void CloseGraphicsButton_Click(object sender, RoutedEventArgs e)
    {
        GraphicsPanel.Visibility = Visibility.Collapsed;
        LogPanel.Visibility = Visibility.Visible;
    }

    private async void SaveGraphicsButton_Click(object sender, RoutedEventArgs e) =>
        await ChangeGraphicsSettingsAsync("Apply", "Settings saved. Restart the preview to apply them.");

    private void GraphicsPresetComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_applyingGraphicsResult || GraphicsPresetComboBox.SelectedItem is null ||
            ResolutionComboBox is null || ReadbackResolveComboBox is null) return;
        _applyingGraphicsResult = true;
        try
        {
            switch (SelectedTag(GraphicsPresetComboBox))
            {
                case "shipping_1x":
                    SelectTag(ResolutionComboBox, "1");
                    SelectTag(ReadbackResolveComboBox, "none");
                    break;
                case "experimental_2x":
                    SelectTag(ResolutionComboBox, "2");
                    SelectTag(ReadbackResolveComboBox, "fast");
                    break;
                case "accurate_showroom":
                    SelectTag(ResolutionComboBox, "1");
                    SelectTag(ReadbackResolveComboBox, "full");
                    break;
            }
        }
        finally
        {
            _applyingGraphicsResult = false;
        }
        UpdateShowroomWarning();
    }

    private void GraphicsControl_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_applyingGraphicsResult || ResolutionComboBox?.SelectedItem is null ||
            ReadbackResolveComboBox?.SelectedItem is null || GraphicsPresetComboBox is null) return;
        var inferred = (SelectedTag(ResolutionComboBox), SelectedTag(ReadbackResolveComboBox)) switch
        {
            ("1", "none") => "shipping_1x",
            ("2", "fast") => "experimental_2x",
            (_, "full") => "accurate_showroom",
            _ => "custom"
        };
        _applyingGraphicsResult = true;
        SelectTag(GraphicsPresetComboBox, inferred);
        _applyingGraphicsResult = false;
        UpdateShowroomWarning();
    }

    private void UpdateShowroomWarning()
    {
        if (ShowroomWarning is null || ReadbackResolveComboBox?.SelectedItem is null) return;
        ShowroomWarning.Visibility = SelectedTag(ReadbackResolveComboBox) == "full"
            ? Visibility.Visible
            : Visibility.Collapsed;
    }

    private async void ResetGraphicsButton_Click(object sender, RoutedEventArgs e)
    {
        if (MessageBox.Show(this,
                "Reset only the Pinyon Shift runtime settings? Your current pinyon_shift.toml will be backed up first.",
                "Reset runtime settings", MessageBoxButton.OKCancel, MessageBoxImage.Warning) != MessageBoxResult.OK)
            return;
        await ChangeGraphicsSettingsAsync("Reset", "Runtime settings reset. Restart the preview to apply them.",
            revealBackup: true);
    }

    private async void RestoreGraphicsButton_Click(object sender, RoutedEventArgs e) =>
        await ChangeGraphicsSettingsAsync("Restore", "Latest settings backup restored. Restart the preview to apply it.");

    private async Task ChangeGraphicsSettingsAsync(string action, string success, bool revealBackup = false)
    {
        SetGraphicsControlsEnabled(false);
        GraphicsStatusText.Text = action == "Apply" ? "Saving validated settings…" : "Updating runtime settings…";
        try
        {
            var result = await RunGraphicsSettingsToolAsync(action);
            ApplyGraphicsResult(result);
            GraphicsStatusText.Text = success;
            if (revealBackup && !string.IsNullOrWhiteSpace(result.BackupPath) && File.Exists(result.BackupPath))
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = "explorer.exe",
                    UseShellExecute = true,
                    Arguments = $"/select,\"{result.BackupPath}\""
                });
            }
        }
        catch (Exception ex)
        {
            GraphicsStatusText.Text = $"No settings were changed: {ex.Message}";
        }
        finally
        {
            SetGraphicsControlsEnabled(true);
        }
    }

    private async Task<GraphicsResult> RunGraphicsSettingsToolAsync(string action)
    {
        if (_repositoryRoot is null) throw new InvalidOperationException("Release source is not ready.");
        var script = Path.Combine(_repositoryRoot, "tools", "set-graphics-experiment.ps1");
        if (!File.Exists(script)) throw new FileNotFoundException("The graphics settings tool is missing.", script);
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
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
            "-Action", action, "-StateRoot", Path.Combine(_repositoryRoot, ".local", "preview"),
            "-Anisotropy", SelectedTag(AnisotropyComboBox), "-PostEffect", SelectedTag(PostEffectComboBox),
            "-ResolutionScale", SelectedTag(ResolutionComboBox),
            "-Preset", SelectedTag(GraphicsPresetComboBox),
            "-ReadbackResolve", SelectedTag(ReadbackResolveComboBox),
            "-DisableMotionBlur", DisableMotionBlurCheckBox.IsChecked == true ? "true" : "false",
            "-DisableDepthOfField", DisableDepthOfFieldCheckBox.IsChecked == true ? "true" : "false",
            "-Json"
        }) startInfo.ArgumentList.Add(argument);
        using var process = Process.Start(startInfo) ??
            throw new InvalidOperationException("Windows could not start the graphics settings tool.");
        var outputTask = process.StandardOutput.ReadToEndAsync();
        var errorTask = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        var output = await outputTask;
        var error = await errorTask;
        if (process.ExitCode != 0)
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(error) ? "The settings tool stopped." : error.Trim());
        var result = JsonSerializer.Deserialize<GraphicsResult>(output.Trim(), new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        });
        return result ?? throw new InvalidDataException("The settings tool returned an invalid result.");
    }

    private static string SelectedTag(ComboBox comboBox) =>
        (comboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? throw new InvalidOperationException("Choose a setting first.");

    private void ApplyGraphicsResult(GraphicsResult result)
    {
        _applyingGraphicsResult = true;
        try
        {
            SelectTag(AnisotropyComboBox, result.Settings.Anisotropy.ToString());
            SelectTag(PostEffectComboBox, result.Settings.PostEffect);
            SelectTag(GraphicsPresetComboBox, result.Settings.Preset);
            SelectTag(ResolutionComboBox, result.Settings.ResolutionScale.ToString());
            SelectTag(ReadbackResolveComboBox, result.Settings.ReadbackResolve);
            DisableMotionBlurCheckBox.IsChecked = result.Settings.DisableMotionBlur;
            DisableDepthOfFieldCheckBox.IsChecked = result.Settings.DisableDepthOfField;
        }
        finally
        {
            _applyingGraphicsResult = false;
        }
        UpdateShowroomWarning();
    }

    private static void SelectTag(ComboBox comboBox, string value)
    {
        comboBox.SelectedItem = comboBox.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => string.Equals(item.Tag?.ToString(), value, StringComparison.OrdinalIgnoreCase));
    }

    private void SetGraphicsControlsEnabled(bool enabled)
    {
        AnisotropyComboBox.IsEnabled = enabled;
        PostEffectComboBox.IsEnabled = enabled;
        ResolutionComboBox.IsEnabled = enabled;
        GraphicsPresetComboBox.IsEnabled = enabled;
        ReadbackResolveComboBox.IsEnabled = enabled;
        DisableMotionBlurCheckBox.IsEnabled = enabled;
        DisableDepthOfFieldCheckBox.IsEnabled = enabled;
        SaveGraphicsButton.IsEnabled = enabled;
        ResetGraphicsButton.IsEnabled = enabled;
        RestoreGraphicsButton.IsEnabled = enabled;
    }

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
    private sealed record GraphicsResult(
        [property: JsonPropertyName("backup_path")] string? BackupPath,
        [property: JsonPropertyName("settings")] GraphicsSettings Settings,
        [property: JsonPropertyName("restart_required")] bool RestartRequired);
    private sealed record GraphicsSettings(
        [property: JsonPropertyName("anisotropy")] int Anisotropy,
        [property: JsonPropertyName("post_effect")] string PostEffect,
        [property: JsonPropertyName("disable_motion_blur")] bool DisableMotionBlur,
        [property: JsonPropertyName("disable_depth_of_field")] bool DisableDepthOfField,
        [property: JsonPropertyName("preset")] string Preset,
        [property: JsonPropertyName("resolution_scale")] int ResolutionScale,
        [property: JsonPropertyName("readback_resolve")] string ReadbackResolve,
        [property: JsonPropertyName("readback_resolve_half_pixel_offset")] bool ReadbackHalfPixelOffset,
        [property: JsonPropertyName("clear_memory_page_state")] bool ClearMemoryPageState,
        [property: JsonPropertyName("readback_memexport")] bool ReadbackMemexport,
        [property: JsonPropertyName("readback_memexport_fast")] bool ReadbackMemexportFast,
        [property: JsonPropertyName("vsync")] bool Vsync);
}
