using Microsoft.Win32;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace PinyonShift.Launcher;

public partial class MainWindow : Window
{
    private readonly ObservableCollection<RouteStep> _steps =
    [
        new("VERIFY", "Verify disc", "", "1"),
        new("TOOLS", "Get build tools", "", "2"),
        new("EXTRACT", "Extract game", "", "3"),
        new("BUILD", "Build", "", "4"),
        new("PLAY", "Play", "", "5")
    ];

    // The content area shows one of these at a time.
    private enum View { Setup, Ready, Log, Crash, Graphics }

    private CancellationTokenSource? _cancellation;
    private string? _repositoryRoot;
    private string? _stateRoot;
    private string? _gameExecutable;
    private StreamWriter? _sessionLog;
    private CrashReport? _pendingReport;
    private bool _busy;
    private bool _canChooseInstallRoot;
    // Set when this launcher keeps everything beside itself (PortableMode); the data folder.
    private string? _portableRoot;
    private readonly bool _portableRequested = PortableMode.IsRequested(
        AppContext.BaseDirectory, Environment.GetCommandLineArgs().Skip(1));
    private readonly List<string> _portableNotes = [];
    private View _panel = View.Setup;
    private View _panelBeforeGraphics = View.Setup;

    private static readonly string InstallRootPreference = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "PinyonShift", "install-root.txt");

    private static readonly Brush WaitingBrush = new SolidColorBrush(Color.FromRgb(52, 73, 59));
    private static readonly Brush ActiveBrush = new SolidColorBrush(Color.FromRgb(241, 174, 54));
    private static readonly Brush CompleteBrush = new SolidColorBrush(Color.FromRgb(92, 208, 138));
    private static readonly Brush FailedBrush = new SolidColorBrush(Color.FromRgb(225, 110, 95));

    public MainWindow()
    {
        InitializeComponent();
        RouteList.ItemsSource = _steps;
        BuildLocationRun.Text = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PinyonShift");
        if (_portableRequested)
        {
            BuildLocationPrefixRun.Text = "Portable: ";
            BuildLocationRun.Text = PortableMode.DataRoot(AppContext.BaseDirectory);
            ChooseInstallRootButton.Visibility = Visibility.Collapsed;
        }
        VersionRun.Text = $"Pinyon Shift {typeof(MainWindow).Assembly.GetName().Version?.ToString(3) ?? "dev"}";
        Loaded += MainWindow_Loaded;
        StateChanged += (_, _) =>
        {
            // A maximized borderless window reaches past the screen edge by the
            // resize border; pad it back in.
            RootBorder.Margin = WindowState == WindowState.Maximized ? new Thickness(7) : new Thickness(0);
            // Two overlapping squares while maximized, one otherwise.
            MaximizeGlyph.Data = Geometry.Parse(WindowState == WindowState.Maximized
                ? "M2.5,0.5 H9.5 V7.5 M0.5,2.5 H7.5 V9.5 H0.5 Z"
                : "M0.5,0.5 H9.5 V9.5 H0.5 Z");
        };
        Closing += (_, _) =>
        {
            _cancellation?.Cancel();
            _sessionLog?.Dispose();
        };
    }

    private async void MainWindow_Loaded(object sender, RoutedEventArgs e)
        => await InitializeSourceAsync();

    private async Task InitializeSourceAsync(string? installRoot = null)
    {
        _busy = true;
        IsEnabled = false;
        try
        {
            var repositoryRoot = await ResolveRepositoryRootAsync(installRoot);
            var stateRoot = ResolveStateRoot(repositoryRoot);
            if (installRoot is not null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(InstallRootPreference)!);
                await File.WriteAllTextAsync(InstallRootPreference, installRoot);
            }
            _sessionLog?.Dispose();
            _sessionLog = null;
            ResetRoute();
            SetReadyState();
            _repositoryRoot = repositoryRoot;
            _stateRoot = stateRoot;
            StartSessionLog(_repositoryRoot);
            ShowReleaseVersion();
            GraphicsSettingsButton.Visibility = Visibility.Visible;
            ShowBuildLocation();
            foreach (var note in _portableNotes) AppendLog(note);
            _portableNotes.Clear();
            AppendLog($"Release source: {_repositoryRoot}");
            AppendLog($"Preview state: {_stateRoot}");
            StageControllerMappings();
            DetectExistingBuild();
            DetectPendingReport();
            UpdatePrimaryButton();
        }
        catch (PortableFolderException ex)
        {
            SetFailure("Portable folder is not writable", ex.Message);
        }
        catch (Exception ex)
        {
            SetFailure("Release files missing", ex.Message);
        }
        finally
        {
            _busy = false;
            IsEnabled = true;
            UpdatePrimaryButton();
        }
    }

    // "Portable: <data folder>" for a portable install, otherwise where the saves are.
    private void ShowBuildLocation()
    {
        BuildLocationPrefixRun.Text = _portableRoot is null ? "Installs to " : "Portable: ";
        BuildLocationRun.Text = _portableRoot ?? _stateRoot ?? BuildLocationRun.Text;
        ChooseInstallRootButton.Visibility = _portableRoot is null ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ShowReleaseVersion()
    {
        if (_repositoryRoot is null) return;
        try
        {
            using var release = JsonDocument.Parse(File.ReadAllText(Path.Combine(_repositoryRoot, "config", "release.json")));
            var version = release.RootElement.GetProperty("version").GetString();
            if (!string.IsNullOrWhiteSpace(version))
                VersionRun.Text = $"Pinyon Shift {version}";
        }
        catch (Exception ex) when (ex is IOException or JsonException or KeyNotFoundException or InvalidOperationException) { }
    }

    private async void ChooseInstallRootButton_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || !_canChooseInstallRoot) return;
        var dialog = new OpenFolderDialog
        {
            Title = "Choose installation folder (existing installations and saves stay in place)",
            Multiselect = false
        };
        if (dialog.ShowDialog(this) == true)
            await InitializeSourceAsync(dialog.FolderName);
    }

    private void BrowseButton_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Choose your Forza Horizon disc image",
            Filter = "Xbox 360 disc image (*.iso)|*.iso|All files (*.*)|*.*",
            CheckFileExists = true,
            Multiselect = false,
            // A portable install leaves no trace in the user's recent files.
            AddToRecent = _portableRoot is null
        };
        if (dialog.ShowDialog(this) == true)
            SelectDiscImage(dialog.FileName);
        UpdatePrimaryButton();
    }

    private void SelectDiscImage(string path)
    {
        IsoPathTextBox.Text = path;
        DropHintText.Text = Path.GetFileName(path);
        ResetRoute();
        SetReadyState();
        ShowPanel(View.Setup);
        UpdatePrimaryButton();
    }

    // Dragging a disc image anywhere onto the window selects it.
    private bool CanAcceptDrop(DragEventArgs e, out string? path)
    {
        path = null;
        if (_busy || _gameExecutable is not null || _pendingReport is not null ||
            !e.Data.GetDataPresent(DataFormats.FileDrop)) return false;
        if (e.Data.GetData(DataFormats.FileDrop) is not string[] { Length: 1 } files) return false;
        path = files[0];
        return File.Exists(path);
    }

    private void Window_DragOver(object sender, DragEventArgs e)
    {
        var accepted = CanAcceptDrop(e, out _);
        e.Effects = accepted ? DragDropEffects.Copy : DragDropEffects.None;
        DropOverlay.Visibility = accepted ? Visibility.Visible : Visibility.Collapsed;
        e.Handled = true;
    }

    protected override void OnDragLeave(DragEventArgs e)
    {
        base.OnDragLeave(e);
        DropOverlay.Visibility = Visibility.Collapsed;
    }

    private void Window_Drop(object sender, DragEventArgs e)
    {
        DropOverlay.Visibility = Visibility.Collapsed;
        if (CanAcceptDrop(e, out var path) && path is not null)
            SelectDiscImage(path);
        e.Handled = true;
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
        if (_portableRoot is not null && PortableMode.PathLengthProblem(_portableRoot) is { } pathTooLong)
        {
            SetFailure("Portable folder path is too long", pathTooLong);
            return;
        }

        _busy = true;
        ChooseInstallRootButton.IsEnabled = false;
        GraphicsSettingsButton.IsEnabled = false;
        AndroidButton.IsEnabled = false;
        _cancellation = new CancellationTokenSource();
        BrowseButton.IsEnabled = false;
        OwnershipCheckBox.IsEnabled = false;
        PrimaryButton.IsEnabled = false;
        SetPrimaryText("Building…");
        ShowPanel(View.Log);
        SetProgress(0, "Starting local setup.");
        HeadlineText.Text = "Building";
        SetSubhead("The first build takes 20 to 60 minutes. You can leave it running.");
        AppendLog("Starting local setup. The first build can take a while.");

        var setupStartedUtc = DateTime.UtcNow;
        _setupFailurePrinted = false;
        try
        {
            var script = Path.Combine(_repositoryRoot, "tools", "setup-preview.ps1");
            if (!File.Exists(script))
                throw new FileNotFoundException("The setup workflow is missing from the release payload.", script);

            var startInfo = new ProcessStartInfo
            {
                FileName = PowerShellExecutable(),
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
                throw new InvalidOperationException(DescribeSetupFailure(process.ExitCode, setupStartedUtc));

            DetectExistingBuild();
            if (_gameExecutable is null)
                throw new InvalidOperationException("Setup completed without producing the expected game executable.");
            SetComplete();
        }
        catch (OperationCanceledException)
        {
            SetFailure("Build cancelled", "Nothing was uploaded. Start the build again to resume where it stopped.");
        }
        catch (Exception ex)
        {
            SetFailure("Setup stopped", ex.Message);
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
            if (line.StartsWith(SetupFailureBanner, StringComparison.Ordinal)) _setupFailurePrinted = true;
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
            var stage = string.Equals(message.Stage, "shaders", StringComparison.OrdinalIgnoreCase)
                ? "build" : message.Stage;
            var index = Array.FindIndex(RouteStep.StageOrder, x =>
                string.Equals(x, stage, StringComparison.OrdinalIgnoreCase));
            if (message.Stage == "shaders")
            {
                HeadlineText.Text = "Preparing graphics";
                SetPrimaryText("Preparing…");
            }
            else if (message.Stage == "play" && _gameExecutable is not null)
            {
                HeadlineText.Text = "Game running";
                SetSubhead("Controller A, Space, or left click. Enter is Start, F6 opens settings.");
                SetPrimaryText("Game running");
            }
            if (index >= 0)
            {
                for (var i = 0; i < _steps.Count; i++)
                    _steps[i].SetState(i < index ? StepState.Complete : i == index ? StepState.Active : StepState.Waiting,
                        WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
            }
            if (message.Percent is >= 0 and <= 100)
                SetProgress(message.Percent, message.Message);
            else if (!string.IsNullOrWhiteSpace(message.Message))
                ProgressMessageText.Text = message.Message;
            if (!string.IsNullOrWhiteSpace(message.Message))
                AppendLog(message.Message);
        }
        catch (JsonException)
        {
            AppendLog(line);
        }
    }

    // tools/release-common.ps1 (Format-PinyonFailureRecord) starts its failure report with this line.
    private const string SetupFailureBanner = "==================== SETUP FAILED";
    private bool _setupFailurePrinted;

    // The failed step, exit code, log and first error from .local/logs/setup-error.json. The report
    // is repeated in the log only when the setup output did not already show it, so a lost or
    // interleaved stream still leaves the cause on screen.
    private string DescribeSetupFailure(int exitCode, DateTime startedUtc,
        string reportName = "setup-error.json", string what = "Setup")
    {
        var fallback = $"{what} stopped before completing (exit code {exitCode}). The details above contain the cause.";
        if (_repositoryRoot is null) return fallback;
        var path = Path.Combine(_repositoryRoot, ".local", "logs", reportName);
        SetupFailure? failure;
        try
        {
            if (!File.Exists(path) || File.GetLastWriteTimeUtc(path) < startedUtc.AddSeconds(-2)) return fallback;
            failure = JsonSerializer.Deserialize<SetupFailure>(File.ReadAllText(path));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            return fallback;
        }
        if (failure is null) return fallback;

        var excerpt = new List<string>();
        if (failure.ErrorExcerpt is { ValueKind: JsonValueKind.Array } lines)
            excerpt.AddRange(lines.EnumerateArray().Select(x => x.ValueKind == JsonValueKind.String ? x.GetString() ?? "" : x.ToString()));
        else if (failure.ErrorExcerpt is { ValueKind: JsonValueKind.String } single)
            excerpt.Add(single.GetString() ?? "");
        var code = failure.ExitCode is { ValueKind: JsonValueKind.Number } number ? number.ToString() : null;

        if (!_setupFailurePrinted)
        {
            AppendLog($"{what} failure report ({path}):");
            if (!string.IsNullOrWhiteSpace(failure.Message)) AppendLog($"Error: {failure.Message}");
            if (!string.IsNullOrWhiteSpace(failure.Step)) AppendLog($"Failed step: {failure.Step}");
            if (code is not null) AppendLog($"Exit code: {code}");
            if (!string.IsNullOrWhiteSpace(failure.BuildLog)) AppendLog($"Full log: {failure.BuildLog}");
            if (excerpt.Count > 0)
            {
                AppendLog("First error from the log:");
                foreach (var line in excerpt) AppendLog("    " + line);
            }
            if (!string.IsNullOrWhiteSpace(failure.Hint)) AppendLog($"What to try: {failure.Hint}");
        }

        var summary = string.IsNullOrWhiteSpace(failure.Step) ? $"{what} stopped" : $"{failure.Step} failed";
        if (code is not null) summary += $" (exit code {code})";
        summary += ". ";
        summary += string.IsNullOrWhiteSpace(failure.Hint)
            ? (excerpt.Count > 0 ? "The first error is shown in the log above." : failure.Message ?? "The details above contain the cause.")
            : failure.Hint;
        return summary;
    }

    private void SetProgress(int percent, string? message)
    {
        BuildProgress.Value = percent;
        ProgressText.Text = $"{percent}%";
        if (!string.IsNullOrWhiteSpace(message))
            ProgressMessageText.Text = message;
    }

    // What the next start uses, read straight from the settings file.
    private string ConfiguredGraphicsApi()
    {
        if (_stateRoot is null) return "vulkan";
        var config = Path.Combine(_stateRoot, "config", "pinyon_shift.toml");
        if (!File.Exists(config)) return "vulkan";
        try
        {
            var text = File.ReadAllText(config);
            var schema = Regex.Match(text, @"(?m)^\s*pinyon_shift_config_schema\s*=\s*([0-9]+)");
            var backend = Regex.Match(text, @"(?m)^\s*gpu_backend\s*=\s*""([^""]*)""");
            // Config schema 27 moves earlier files to Vulkan when the game starts;
            // "any" is the first backend, Direct3D 12.
            if (!schema.Success || int.Parse(schema.Groups[1].Value) < 27 || !backend.Success) return "vulkan";
            return string.Equals(backend.Groups[1].Value, "vulkan", StringComparison.OrdinalIgnoreCase) ? "vulkan" : "d3d12";
        }
        catch (IOException) { return "vulkan"; }
    }

    private int ConfiguredResolutionScale()
    {
        if (_stateRoot is null) return 1;
        var config = Path.Combine(_stateRoot, "config", "pinyon_shift.toml");
        try
        {
            var match = File.Exists(config)
                ? Regex.Match(File.ReadAllText(config), @"(?m)^\s*draw_resolution_scale_x\s*=\s*([0-9]+)")
                : Match.Empty;
            return match.Success ? Math.Clamp(int.Parse(match.Groups[1].Value), 1, 4) : 1;
        }
        catch (IOException) { return 1; }
    }

    // What the next start uses, in one line under the headline.
    private void UpdateSummary()
    {
        var scale = ConfiguredResolutionScale();
        SetSubhead($"{(ConfiguredGraphicsApi() == "vulkan" ? "Vulkan" : "Direct3D 12")} · " +
                   $"{scale}× ({1280 * scale} × {720 * scale}) · F6 opens settings in game");
    }

    private void DetectExistingBuild()
    {
        _gameExecutable = null;
        if (_repositoryRoot is null) return;
        var candidate = Path.Combine(_repositoryRoot, "out", "build", "win-amd64-release", "pinyon_shift.exe");
        if (File.Exists(candidate))
        {
            if (!File.Exists(Path.Combine(_repositoryRoot, ".local", "game", "base", "default.xex")))
            {
                HeadlineText.Text = "Restore your game files";
                SetSubhead("Choose your disc image to run setup again. Your save stays in place.");
                AppendLog("Select your disc image and run setup to restore the missing game files. Your save stays in place.");
                return;
            }
            var payloadMarker = Path.Combine(_repositoryRoot, ".pinyon-source-sha256");
            if (File.Exists(payloadMarker))
            {
                var matchesRelease = false;
                try
                {
                    using var build = JsonDocument.Parse(File.ReadAllText(Path.Combine(_repositoryRoot, ".local", "build.json")));
                    matchesRelease = build.RootElement.TryGetProperty("pinyon_shift_source_payload_sha256", out var hash)
                        && string.Equals(hash.GetString(), File.ReadAllText(payloadMarker).Trim(), StringComparison.OrdinalIgnoreCase);
                }
                catch (Exception ex) when (ex is IOException or JsonException or InvalidOperationException) { }
                if (!matchesRelease)
                {
                    HeadlineText.Text = "Update your build";
                    SetSubhead("This release changed the game code. Choose your disc image to rebuild; your save stays in place.");
                    AppendLog("Select your disc image and run setup to build this release. Existing game files and your save are preserved.");
                    return;
                }
            }
            _gameExecutable = candidate;
            SetComplete();
            // Only Direct3D 12 loads prepared shader packs.
            if (_stateRoot is not null && ConfiguredGraphicsApi() == "d3d12" &&
                !File.Exists(Path.Combine(_stateRoot, "cache", "fh1-artifacts.json")))
            {
                _steps[3].SetState(StepState.Waiting, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
                _steps[4].SetState(StepState.Waiting, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
                HeadlineText.Text = "Prepare graphics";
                SetSubhead("Direct3D 12 prepares its shaders once for this PC before the first start.");
                SetPrimaryText("Prepare and play");
            }
        }
    }

    private async Task LaunchGameAsync()
    {
        if (_repositoryRoot is null || _stateRoot is null || _gameExecutable is null) return;
        if (_busy) return;

        _busy = true;
        ChooseInstallRootButton.IsEnabled = false;
        GraphicsSettingsButton.IsEnabled = false;
        AndroidButton.IsEnabled = false;
        PrimaryButton.IsEnabled = false;
        SetPrimaryText("Starting…");
        HeadlineText.Text = "Starting";
        SetSubhead("The game opens in its own window.");
        ShowPanel(View.Log);
        SetProgress(0, "Checking graphics for this computer.");
        ReportProblemButton.IsEnabled = false;
        AppendLog("Checking graphics for this computer. Missing or outdated shaders are prepared automatically.");
        AppendLog("Controls: use controller A, Space, or left click for the selected Xbox menu item; press Enter for Start.");

        try
        {
            _cancellation?.Dispose();
            _cancellation = new CancellationTokenSource();
            var launcher = Path.Combine(_repositoryRoot, "tools", "launch-preview.ps1");
            var startInfo = new ProcessStartInfo
            {
                FileName = PowerShellExecutable(),
                WorkingDirectory = _repositoryRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };
            foreach (var argument in new[]
            {
                "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", launcher,
                "-Configuration", "Release", "-StateRoot", _stateRoot, "-Json", "-JsonEvents"
            }) startInfo.ArgumentList.Add(argument);

            using var watcher = new Process { StartInfo = startInfo };
            var output = new System.Text.StringBuilder();
            var errors = new System.Text.StringBuilder();
            watcher.OutputDataReceived += (_, args) => Dispatcher.Invoke(() =>
            {
                if (args.Data is null) return;
                if (args.Data.StartsWith('{')) output.AppendLine(args.Data);
                else HandleOutput(args.Data);
            });
            watcher.ErrorDataReceived += (_, args) => Dispatcher.Invoke(() =>
            {
                if (args.Data is null) return;
                errors.AppendLine(args.Data);
                AppendLog(args.Data);
            });
            if (!watcher.Start()) throw new InvalidOperationException("Windows could not start the preview watcher.");
            watcher.BeginOutputReadLine();
            watcher.BeginErrorReadLine();
            using var registration = _cancellation.Token.Register(() =>
            {
                try { if (!watcher.HasExited) watcher.Kill(entireProcessTree: true); } catch { }
            });
            await watcher.WaitForExitAsync(_cancellation.Token);
            var error = errors.ToString();

            var result = ParseLaunchResult(output.ToString());
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
        catch (OperationCanceledException)
        {
            SetFailure("Preparation cancelled", "Play again to finish preparing graphics.");
        }
        catch (Exception ex)
        {
            SetFailure("The game stopped", ex.Message);
        }
        finally
        {
            _busy = false;
            GraphicsSettingsButton.IsEnabled = true;
            ReportProblemButton.IsEnabled = true;
            UpdatePrimaryButton();
        }
    }

    // Windows PowerShell by its full path. A bare "powershell.exe" is found only through PATH,
    // so a PATH that lost the WindowsPowerShell folder made every setup step fail with
    // "The specified file cannot be found". PowerShell 7 serves when Windows PowerShell is gone.
    private static string PowerShellExecutable()
    {
        string[] candidates =
        [
            Path.Combine(Environment.SystemDirectory, "WindowsPowerShell", "v1.0", "powershell.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "PowerShell", "7",
                "pwsh.exe")
        ];
        return candidates.FirstOrDefault(File.Exists) ?? "powershell.exe";
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
        if (_stateRoot is null) return;
        var reportsRoot = Path.GetFullPath(Path.Combine(_stateRoot, "reports"));
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
            // A folder moved since the crash (a portable install) still holds the bundle in its
            // own reports folder.
            if (!bundle.StartsWith(reportsPrefix, StringComparison.OrdinalIgnoreCase))
                bundle = Path.Combine(reportsRoot, Path.GetFileName(bundle));
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
        HeadlineText.Text = "The game crashed";
        SetSubhead("");
        CrashIdRun.Text = report.CrashId;
        ShowPanel(View.Crash);
        ReportProblemButton.Visibility = Visibility.Collapsed;
        OpenLogsButton.Content = "Report folder";
        OpenLogsButton.Visibility = Visibility.Visible;
        SetPrimaryText("Report crash");
        PrimaryButton.IsEnabled = true;
    }

    private void ReportCrash()
    {
        if (_pendingReport is null || _stateRoot is null) return;
        Process.Start(new ProcessStartInfo
        {
            FileName = "explorer.exe",
            UseShellExecute = true,
            Arguments = $"/select,\"{_pendingReport.Bundle}\""
        });
        Process.Start(new ProcessStartInfo(_pendingReport.IssueUrl) { UseShellExecute = true });
        var marker = Path.Combine(_stateRoot, "reports", "pending-report.json");
        try { if (File.Exists(marker)) File.Delete(marker); } catch (IOException) { }
        SetPrimaryText("Open GitHub again");
    }

    private async Task<string> ResolveRepositoryRootAsync(string? selectedInstallRoot = null)
    {
        static bool IsRoot(string path) => File.Exists(Path.Combine(path, "config", "supported-dumps.json"))
            && File.Exists(Path.Combine(path, "tools", "setup-preview.ps1"));

        var directory = AppContext.BaseDirectory;
        for (var i = 0; i < 8; i++)
        {
            if (IsRoot(directory))
            {
                _canChooseInstallRoot = false;
                _portableRoot = null;
                if (_portableRequested)
                    _portableNotes.Add("Portable mode does not apply to a repository checkout; using the checkout.");
                return directory;
            }
            var parent = Directory.GetParent(directory);
            if (parent is null) break;
            directory = parent.FullName;
        }

        var payload = Path.Combine(AppContext.BaseDirectory, "pinyon-shift-source.zip");
        if (!File.Exists(payload))
            throw new FileNotFoundException("Keep pinyon-shift-source.zip beside the launcher, or run the launcher from a repository checkout.");

        var version = typeof(MainWindow).Assembly.GetName().Version?.ToString(3) ?? "dev";
        string? installRoot;
        if (_portableRequested)
        {
            // Everything beside the launcher, derived again at every start so the folder can move;
            // no preference file and no environment override.
            installRoot = PortableMode.DataRoot(AppContext.BaseDirectory);
            _canChooseInstallRoot = false;
            PortableMode.EnsureWritable(installRoot);
            foreach (var ignored in PortableMode.ApplyToEnvironment(installRoot))
                _portableNotes.Add($"Portable mode ignores {ignored}.");
            if (PortableMode.PathLengthProblem(installRoot) is { } pathTooLong)
                _portableNotes.Add(pathTooLong);
            _portableRoot = installRoot;
        }
        else
        {
            installRoot = Environment.GetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT");
            _canChooseInstallRoot = string.IsNullOrWhiteSpace(installRoot);
            if (_canChooseInstallRoot)
                installRoot = selectedInstallRoot ?? (File.Exists(InstallRootPreference)
                    ? (await File.ReadAllTextAsync(InstallRootPreference)).Trim() : null);
            if (string.IsNullOrWhiteSpace(installRoot))
                installRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PinyonShift");
        }
        var destination = Path.Combine(Path.GetFullPath(installRoot), "source", version);
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

    private static string ResolveStateRoot(string repositoryRoot)
    {
        var configured = Environment.GetEnvironmentVariable("PINYON_SHIFT_STATE_ROOT");
        return Path.GetFullPath(string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(repositoryRoot, ".local", "preview")
            : configured);
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

    private void ShowPanel(View panel)
    {
        _panel = panel;
        SetupPanel.Visibility = panel == View.Setup ? Visibility.Visible : Visibility.Collapsed;
        LogPanel.Visibility = panel == View.Log ? Visibility.Visible : Visibility.Collapsed;
        CrashPanel.Visibility = panel == View.Crash ? Visibility.Visible : Visibility.Collapsed;
        GraphicsPanel.Visibility = panel == View.Graphics ? Visibility.Visible : Visibility.Collapsed;
        // The route only tells something while there is setup left to do.
        RouteList.Visibility = panel is View.Setup or View.Log ? Visibility.Visible : Visibility.Collapsed;
        if (panel == View.Ready) UpdateSummary();
    }

    private void SetPrimaryText(string text)
    {
        PrimaryButtonText.Text = text;
        PrimaryIcon.Visibility = text is "Play" or "Prepare and play"
            ? Visibility.Visible : Visibility.Collapsed;
    }

    private void SetSubhead(string text)
    {
        SubheadText.Text = text;
        SubheadText.Visibility = string.IsNullOrEmpty(text) ? Visibility.Collapsed : Visibility.Visible;
    }

    private void SetReadyState()
    {
        HeadlineText.Text = "Build your preview";
        SetSubhead("Verified, extracted and compiled on this PC. Nothing is uploaded.");
    }

    private void SetComplete()
    {
        _pendingReport = null;
        foreach (var step in _steps)
            step.SetState(StepState.Complete, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        SetProgress(100, "Ready.");
        HeadlineText.Text = "Ready to drive";
        SetPrimaryText("Play");
        ShowPanel(View.Ready);
        ReportProblemButton.Visibility = Visibility.Visible;
        OpenLogsButton.Content = "Logs";
        OpenLogsButton.Visibility = Visibility.Visible;
        OpenStateFolderButton.Visibility = Visibility.Visible;
        AppendLog("Build complete. Generated files remain on this computer.");
    }

    private void SetFailure(string headline, string message)
    {
        var active = _steps.FirstOrDefault(x => x.State == StepState.Active);
        active?.SetState(StepState.Failed, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        HeadlineText.Text = headline;
        SetSubhead(message);
        SetPrimaryText("Try again");
        ShowPanel(View.Log);
        ProgressMessageText.Text = message;
        OpenLogsButton.Visibility = Visibility.Visible;
        AppendLog($"ERROR: {message}");
    }

    private void ResetRoute()
    {
        _gameExecutable = null;
        _pendingReport = null;
        foreach (var step in _steps)
            step.SetState(StepState.Waiting, WaitingBrush, ActiveBrush, CompleteBrush, FailedBrush);
        SetPrimaryText("Verify and build");
        ShowPanel(View.Setup);
        ReportProblemButton.Visibility = Visibility.Visible;
        OwnershipCheckBox.Visibility = Visibility.Visible;
    }

    private void UpdatePrimaryButton()
    {
        ChooseInstallRootButton.IsEnabled = !_busy && _canChooseInstallRoot &&
            GraphicsPanel.Visibility != Visibility.Visible;
        PrimaryButton.IsEnabled = !_busy && (_pendingReport is not null || _gameExecutable is not null ||
            (_repositoryRoot is not null && File.Exists(IsoPathTextBox.Text) && OwnershipCheckBox.IsChecked == true));
        // The Android package is made from the game this PC built.
        AndroidButton.Visibility = _gameExecutable is not null && _pendingReport is null
            ? Visibility.Visible : Visibility.Collapsed;
        AndroidButton.IsEnabled = !_busy;
    }

    private async void AndroidButton_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _repositoryRoot is null || _gameExecutable is null) return;
        var script = Path.Combine(_repositoryRoot, "tools", "build-android.ps1");
        if (!File.Exists(script))
        {
            SetFailure("Android build unavailable", "This release does not include the Android build workflow.");
            SetPrimaryText("Play");
            return;
        }
        // The player sees what will be downloaded and accepts the Android SDK license
        // before sdkmanager is answered for them.
        var answer = MessageBox.Show(this,
            "Build an Android package (APK) of the game from this PC's build, for your own device. " +
            "The first build takes 20 to 60 minutes and about 10 GB of disk.\n\n" +
            "If this PC has no Android SDK or JDK, the launcher downloads Google's Android SDK command-line " +
            "tools and the Eclipse Temurin JDK 17 into the install folder, then installs the Android NDK, " +
            "build tools and platform. Those packages are covered by the Android Software Development Kit " +
            "License Agreement (https://developer.android.com/studio/terms).\n\n" +
            "Accept the Android SDK license and build?",
            "Build Android APK", MessageBoxButton.YesNo, MessageBoxImage.Question);
        if (answer != MessageBoxResult.Yes) return;

        _busy = true;
        ChooseInstallRootButton.IsEnabled = false;
        GraphicsSettingsButton.IsEnabled = false;
        AndroidButton.IsEnabled = false;
        PrimaryButton.IsEnabled = false;
        _cancellation?.Dispose();
        _cancellation = new CancellationTokenSource();
        ShowPanel(View.Log);
        SetProgress(0, "Starting the Android build.");
        HeadlineText.Text = "Building for Android";
        SetSubhead("The first build takes 20 to 60 minutes. You can leave it running.");
        AppendLog("Starting the Android build.");

        var startedUtc = DateTime.UtcNow;
        _setupFailurePrinted = false;
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = PowerShellExecutable(),
                WorkingDirectory = _repositoryRoot,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };
            foreach (var argument in new[] { "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                         "-AcceptAndroidLicenses", "-JsonEvents" })
                startInfo.ArgumentList.Add(argument);

            using var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
            process.OutputDataReceived += (_, args) => Dispatcher.Invoke(() => HandleOutput(args.Data));
            process.ErrorDataReceived += (_, args) => Dispatcher.Invoke(() =>
            {
                if (!string.IsNullOrWhiteSpace(args.Data)) AppendLog(args.Data);
            });
            if (!process.Start())
                throw new InvalidOperationException("Windows could not start the Android build.");
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            using var registration = _cancellation.Token.Register(() =>
            {
                try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            });
            await process.WaitForExitAsync(_cancellation.Token);
            if (process.ExitCode != 0)
                throw new InvalidOperationException(DescribeSetupFailure(process.ExitCode, startedUtc,
                    "android-error.json", "The Android build"));

            var apk = Path.Combine(_repositoryRoot, ".local", "android", "pinyon-shift.apk");
            if (!File.Exists(apk))
                throw new InvalidOperationException("The Android build completed without producing pinyon-shift.apk.");
            SetProgress(100, "Android package ready.");
            HeadlineText.Text = "Android package ready";
            SetSubhead("Install it on your own device: copy the APK over, or with USB debugging run " +
                "\"python tools\\pinyon.py android install\" and \"android push-data\" in the install folder.");
            AppendLog($"Android package: {apk}");
            Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{apk}\"") { UseShellExecute = true });
        }
        catch (OperationCanceledException)
        {
            SetFailure("Android build cancelled", "Start it again to resume where it stopped.");
        }
        catch (Exception ex)
        {
            SetFailure("Android build stopped", ex.Message);
        }
        finally
        {
            _busy = false;
            GraphicsSettingsButton.IsEnabled = true;
            // The game is still built: the primary action stays Play.
            SetPrimaryText("Play");
            UpdatePrimaryButton();
        }
    }

    private void AppendLog(string line)
    {
        var entry = $"[{DateTime.Now:HH:mm:ss}] {line}";
        LogTextBox.AppendText(entry + Environment.NewLine);
        try
        {
            _sessionLog?.WriteLine(entry);
        }
        catch (IOException)
        {
            _sessionLog?.Dispose();
            _sessionLog = null;
        }
        const int maximumLogCharacters = 120_000;
        if (LogTextBox.Text.Length > maximumLogCharacters)
            LogTextBox.Text = LogTextBox.Text[^maximumLogCharacters..];
        LogTextBox.ScrollToEnd();
    }

    private void LogToggleButton_Click(object sender, RoutedEventArgs e)
    {
        var show = LogBox.Visibility != Visibility.Visible;
        LogBox.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        LogToggleButton.Content = show ? "Hide details" : "Show details";
    }

    private void OpenLogsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_repositoryRoot is null || _stateRoot is null) return;
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

    private void StartSessionLog(string repositoryRoot)
    {
        try
        {
            var logs = Path.Combine(repositoryRoot, ".local", "logs");
            Directory.CreateDirectory(logs);
            _sessionLog = new StreamWriter(Path.Combine(logs, "launcher.log"), append: false)
            {
                AutoFlush = true
            };
        }
        catch (IOException)
        {
            _sessionLog = null;
        }
        catch (UnauthorizedAccessException)
        {
            _sessionLog = null;
        }
    }

    private void ReportProblemButton_Click(object sender, RoutedEventArgs e) =>
        Process.Start(new ProcessStartInfo(
            "https://github.com/arcanite24/pinyon-shift/issues/new?template=bug.yml")
        { UseShellExecute = true });

    private void ProjectButton_Click(object sender, RoutedEventArgs e) =>
        Process.Start(new ProcessStartInfo("https://github.com/arcanite24/pinyon-shift") { UseShellExecute = true });

    // Opens the README section listing GitHub Sponsors and Ko-fi; nothing in
    // the launcher depends on or changes with support.
    private void SupportButton_Click(object sender, RoutedEventArgs e) =>
        Process.Start(new ProcessStartInfo(
            "https://github.com/arcanite24/pinyon-shift#supporting-the-project")
        { UseShellExecute = true });

    private void OpenStateFolderButton_Click(object sender, RoutedEventArgs e)
    {
        if (_stateRoot is null) return;
        Directory.CreateDirectory(_stateRoot);
        Process.Start(new ProcessStartInfo("explorer.exe", _stateRoot) { UseShellExecute = true });
    }

    private void MinimizeButton_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;

    private void MaximizeButton_Click(object sender, RoutedEventArgs e) =>
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private void CloseButton_Click(object sender, RoutedEventArgs e) => Close();

    private async void GraphicsSettingsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_repositoryRoot is null || _busy || _pendingReport is not null) return;
        if (_panel != View.Graphics) _panelBeforeGraphics = _panel;
        ShowPanel(View.Graphics);
        ChooseInstallRootButton.IsEnabled = false;
        GraphicsStatusText.Text = InGameHint;
        try
        {
            ApplyGraphicsResult(await RunGraphicsSettingsToolAsync("Get"));
        }
        catch (Exception ex)
        {
            GraphicsStatusText.Text = $"Settings could not be loaded: {ex.Message}";
        }
    }

    private void CloseGraphicsButton_Click(object sender, RoutedEventArgs e)
    {
        ShowPanel(_panelBeforeGraphics == View.Graphics ? View.Setup : _panelBeforeGraphics);
        UpdatePrimaryButton();
    }

    private const string InGameHint = "Everything else is in the game: press F6 while playing.";

    private async void SaveGraphicsButton_Click(object sender, RoutedEventArgs e)
    {
        if (!await ChangeGraphicsSettingsAsync("Apply", "Saved. Applies at the next start.")) return;
        // Direct3D 12 may now need its shader packs.
        if (_gameExecutable is not null && !_busy) DetectExistingBuild();
        CloseGraphicsButton_Click(sender, e);
    }

    private async void ResetGraphicsButton_Click(object sender, RoutedEventArgs e)
    {
        if (MessageBox.Show(this,
                "Reset only the Pinyon Shift runtime settings? Your current pinyon_shift.toml will be backed up first.",
                "Reset runtime settings", MessageBoxButton.OKCancel, MessageBoxImage.Warning) != MessageBoxResult.OK)
            return;
        await ChangeGraphicsSettingsAsync("Reset", "Reset to defaults. Applies at the next start.",
            revealBackup: true);
    }

    private async void RestoreGraphicsButton_Click(object sender, RoutedEventArgs e) =>
        await ChangeGraphicsSettingsAsync("Restore", "Backup restored. Applies at the next start.");

    private async Task<bool> ChangeGraphicsSettingsAsync(string action, string success, bool revealBackup = false)
    {
        SetGraphicsControlsEnabled(false);
        GraphicsStatusText.Text = action == "Apply" ? "Saving…" : "Updating…";
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
            return true;
        }
        catch (Exception ex)
        {
            GraphicsStatusText.Text = $"No settings were changed: {ex.Message}";
            return false;
        }
        finally
        {
            SetGraphicsControlsEnabled(true);
        }
    }

    private async Task<GraphicsResult> RunGraphicsSettingsToolAsync(string action)
    {
        if (_repositoryRoot is null || _stateRoot is null)
            throw new InvalidOperationException("Release source is not ready.");
        var script = Path.Combine(_repositoryRoot, "tools", "set-graphics-experiment.ps1");
        if (!File.Exists(script)) throw new FileNotFoundException("The graphics settings tool is missing.", script);
        var startInfo = new ProcessStartInfo
        {
            FileName = PowerShellExecutable(),
            WorkingDirectory = _repositoryRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        foreach (var argument in new[]
        {
            "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
            "-Action", action, "-StateRoot", _stateRoot,
            // Only the choices in this panel: the rest is set in game and must
            // not be overwritten.
            "-ResolutionScale", SelectedTag(ResolutionComboBox),
            "-GraphicsApi", SelectedTag(GraphicsApiComboBox),
            "-OutputScaling", SelectedTag(OutputScalingComboBox),
            "-TreasureMap", TreasureMapCheckBox.IsChecked == true ? "true" : "false",
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
        _graphicsSettings = result.Settings;
        SelectTag(ResolutionComboBox, result.Settings.ResolutionScale.ToString());
        SelectTag(GraphicsApiComboBox, string.IsNullOrWhiteSpace(result.Settings.GraphicsApi)
            ? "vulkan" : result.Settings.GraphicsApi);
        SelectTag(OutputScalingComboBox, string.IsNullOrWhiteSpace(result.Settings.OutputScaling)
            ? "bilinear" : result.Settings.OutputScaling);
        TreasureMapCheckBox.IsChecked = result.Settings.TreasureMap;
        UpdateResolutionLine();
    }

    private GraphicsSettings? _graphicsSettings;

    private void GraphicsChoice_SelectionChanged(object sender, SelectionChangedEventArgs e) =>
        UpdateResolutionLine();

    // What the game renders and what reaches the screen, as the in-game
    // display settings say it: the scaled 1280 x 720 image, fitted to the
    // display (or the window) with the chosen output scaling.
    private void UpdateResolutionLine()
    {
        if (ResolutionLineText is null) return;
        var scale = int.TryParse((ResolutionComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString(), out var value)
            ? value : 1;
        var (renderWidth, renderHeight) = (1280 * scale, 720 * scale);
        var line = $"Renders {renderWidth} × {renderHeight}";
        var output = OutputSize(_graphicsSettings);
        if (output is not var (outputWidth, outputHeight))
        {
            ResolutionLineText.Text = line + ".";
            return;
        }
        var fsr = (OutputScalingComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() == "fsr";
        ResolutionLineText.Text = (long)outputWidth * outputHeight == (long)renderWidth * renderHeight
            ? $"{line}, the size of your screen."
            : (long)outputWidth * outputHeight > (long)renderWidth * renderHeight
                ? $"{line}, {(fsr ? "FSR 1 upscales" : "stretched")} to {outputWidth} × {outputHeight}."
                : $"{line}, downscaled to {outputWidth} × {outputHeight}.";
    }

    private (int Width, int Height)? OutputSize(GraphicsSettings? settings)
    {
        (int Width, int Height)? area;
        if (settings is null || settings.Fullscreen)
        {
            area = DisplaySize(settings?.Monitor ?? 0);
        }
        else
        {
            // The game sizes its window in logical pixels, 1280 x 720 unless set.
            var dpi = VisualTreeHelper.GetDpi(this);
            area = ((int)Math.Round((settings.WindowWidth > 0 ? settings.WindowWidth : 1280) * dpi.DpiScaleX),
                    (int)Math.Round((settings.WindowHeight > 0 ? settings.WindowHeight : 720) * dpi.DpiScaleY));
        }
        if (area is not var (width, height) || width <= 0 || height <= 0) return null;
        if (settings is not null && !settings.Letterbox) return (width, height);
        // Letterboxed to the game's 16:9.
        return (long)width * 9 > (long)height * 16 ? (height * 16 / 9, height) : (width, width * 9 / 16);
    }

    // The display mode of the game's monitor: 0 and 1 are the primary, 2 on
    // the other displays in Windows' order.
    private static (int Width, int Height)? DisplaySize(int monitor)
    {
        string? deviceName = null;
        if (monitor > 1)
        {
            var others = new List<string>();
            var device = new DisplayDevice { cb = System.Runtime.InteropServices.Marshal.SizeOf<DisplayDevice>() };
            for (uint index = 0; EnumDisplayDevices(null, index, ref device, 0); index++)
            {
                if ((device.StateFlags & 0x1) != 0 && (device.StateFlags & 0x4) == 0) others.Add(device.DeviceName);
                device.cb = System.Runtime.InteropServices.Marshal.SizeOf<DisplayDevice>();
            }
            if (monitor - 2 < others.Count) deviceName = others[monitor - 2];
        }
        var mode = new DevMode { dmSize = (short)System.Runtime.InteropServices.Marshal.SizeOf<DevMode>() };
        return EnumDisplaySettings(deviceName, -1, ref mode) ? (mode.dmPelsWidth, mode.dmPelsHeight) : null;
    }

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern bool EnumDisplaySettings(string? deviceName, int modeNum, ref DevMode devMode);

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern bool EnumDisplayDevices(string? device, uint deviceIndex, ref DisplayDevice displayDevice,
        uint flags);

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential,
        CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private struct DisplayDevice
    {
        public int cb;
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.ByValTStr, SizeConst = 32)]
        public string DeviceName;
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceString;
        public int StateFlags;
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceID;
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.ByValTStr, SizeConst = 128)]
        public string DeviceKey;
    }

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential,
        CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private struct DevMode
    {
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmDeviceName;
        public short dmSpecVersion;
        public short dmDriverVersion;
        public short dmSize;
        public short dmDriverExtra;
        public int dmFields;
        public int dmPositionX;
        public int dmPositionY;
        public int dmDisplayOrientation;
        public int dmDisplayFixedOutput;
        public short dmColor;
        public short dmDuplex;
        public short dmYResolution;
        public short dmTTOption;
        public short dmCollate;
        [System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.ByValTStr, SizeConst = 32)]
        public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel;
        public int dmPelsWidth;
        public int dmPelsHeight;
        public int dmDisplayFlags;
        public int dmDisplayFrequency;
        public int dmICMMethod;
        public int dmICMIntent;
        public int dmMediaType;
        public int dmDitherType;
        public int dmReserved1;
        public int dmReserved2;
        public int dmPanningWidth;
        public int dmPanningHeight;
    }

    private static void SelectTag(ComboBox comboBox, string value)
    {
        comboBox.SelectedItem = comboBox.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => string.Equals(item.Tag?.ToString(), value, StringComparison.OrdinalIgnoreCase));
    }

    private void SetGraphicsControlsEnabled(bool enabled)
    {
        ResolutionComboBox.IsEnabled = enabled;
        GraphicsApiComboBox.IsEnabled = enabled;
        OutputScalingComboBox.IsEnabled = enabled;
        TreasureMapCheckBox.IsEnabled = enabled;
        SaveGraphicsButton.IsEnabled = enabled;
        ResetGraphicsButton.IsEnabled = enabled;
        RestoreGraphicsButton.IsEnabled = enabled;
    }

    private sealed record ProgressMessage(string? Stage, int Percent, string? Message);
    private sealed record SetupFailure(
        [property: JsonPropertyName("message")] string? Message,
        [property: JsonPropertyName("step")] string? Step,
        [property: JsonPropertyName("exit_code")] JsonElement? ExitCode,
        [property: JsonPropertyName("build_log")] string? BuildLog,
        [property: JsonPropertyName("error_excerpt")] JsonElement? ErrorExcerpt,
        [property: JsonPropertyName("hint")] string? Hint);
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
        [property: JsonPropertyName("graphics_api")] string? GraphicsApi,
        [property: JsonPropertyName("output_scaling")] string? OutputScaling,
        [property: JsonPropertyName("fullscreen")] bool Fullscreen,
        [property: JsonPropertyName("monitor")] int Monitor,
        [property: JsonPropertyName("window_width")] int WindowWidth,
        [property: JsonPropertyName("window_height")] int WindowHeight,
        [property: JsonPropertyName("letterbox")] bool Letterbox,
        [property: JsonPropertyName("treasure_map")] bool TreasureMap,
        [property: JsonPropertyName("clear_memory_page_state")] bool ClearMemoryPageState,
        [property: JsonPropertyName("vsync")] bool Vsync);
}
