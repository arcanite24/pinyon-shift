using System.Text;
using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;

namespace PinyonShift.Launcher.Desktop;

// The launcher for Linux (Steam Deck included) and macOS. Every feature of
// the Windows launcher (../PinyonShift.Launcher, the reference for wording)
// calls a tools/pinyon.py subcommand that prints one JSON object
// (.local/backlog-research/launcher-parity-2026-10-15/cli.md): setup, launch,
// dlc, title-update, config, hardware, crash-report, import-save, paths, xe,
// radio, android and shortcuts. The panels live in the MainWindow.*.cs files.
public partial class MainWindow : Window
{
    private const string Repository = "https://github.com/arcanite24/pinyon-shift";
    private enum Mode { Loading, Setup, Building, Ready, Playing, Crashed }

    private Installation? _installation;
    private string? _discImage;
    private Mode _mode = Mode.Loading;
    private CancellationTokenSource? _cancel;
    private readonly StringBuilder _log = new();
    private StreamWriter? _sessionLog;
    private bool _busy;
    private bool _updateChecked;
    private readonly List<string> _portableNotes = [];

    public MainWindow()
    {
        InitializeComponent();
        VersionText.Text = $"Pinyon Shift {Installation.Version} · Not affiliated with Microsoft or Playground Games";
        AddHandler(DragDrop.DropEvent, OnDrop);
        AddHandler(DragDrop.DragOverEvent, OnDragOver);
        AddHandler(DragDrop.DragLeaveEvent, (_, _) => DropOverlay.IsVisible = false);
        Opened += async (_, _) => await LoadAsync();
    }

    private IBrush Brush(string key) => (IBrush)this.FindResource(key)!;

    private async Task LoadAsync(string? installRoot = null)
    {
        _busy = true;
        IsEnabled = false;
        try
        {
            if (Installation.PortableRequested) _portableNotes.AddRange(Installation.PreparePortable());
            _installation = await Installation.OpenAsync(installRoot);
        }
        catch (Exception error)
        {
            Headline.Text = Installation.PortableRequested && error is IOException
                ? "Portable folder is not writable" : "Something is missing";
            Subhead.Text = error.Message;
            SetupPanel.IsVisible = false;
            PrimaryButton.IsVisible = false;
            return;
        }
        finally
        {
            _busy = false;
            IsEnabled = true;
        }
        StartSessionLog();
        foreach (var note in _portableNotes) AppendLog(note);
        _portableNotes.Clear();
        AppendLog($"Release source: {_installation.Root}");
        AppendLog($"State: {_installation.StateRoot}");
        if (!_updateChecked)
        {
            _updateChecked = true;
            _ = StartUpdateCheckAsync();
        }
        ShowInstallLocation();
        if (!Installation.HasAppleDeveloperTools())
        {
            AppleToolsPanel.IsVisible = true;
            SetupPanel.IsVisible = false;
            PrimaryButton.IsVisible = false;
            Headline.Text = "Build your copy";
            return;
        }
        ShowMode(_installation.IsReady() ? Mode.Ready : Mode.Setup);
        if (_mode == Mode.Ready) await DetectPendingReportAsync();
    }

    // "Portable: <data folder>" for a portable install, otherwise where it installs.
    private void ShowInstallLocation()
    {
        if (_installation is null) return;
        var size = Installation.IsMac ? "20" : "45";
        InstallText.Text = Installation.PortableRequested
            ? $"Portable: {Installation.PortableRoot}. Everything stays in this folder. The build needs about {size} GB free."
            : $"Installs to {_installation.Root}. The build needs about {size} GB free and takes 20 to 60 minutes.";
        ChooseInstallRootButton.IsVisible = _installation.CanChooseInstallRoot;
    }

    private void ShowMode(Mode mode)
    {
        _mode = mode;
        var ready = mode is Mode.Ready or Mode.Playing;
        SetupPanel.IsVisible = mode == Mode.Setup;
        AppleToolsPanel.IsVisible = false;
        PrimaryButton.IsVisible = true;
        SteamButton.IsVisible = ready && Installation.IsLinux;
        RebuildButton.IsVisible = mode == Mode.Ready;
        NavPanel.IsVisible = mode == Mode.Ready;
        CrashPanel.IsVisible = mode == Mode.Crashed;
        ReportButton.IsVisible = mode != Mode.Crashed;
        LogsButton.Content = mode == Mode.Crashed ? "Report folder" : "Logs";
        if (mode != Mode.Ready) ShowPanel(Panel.None);
        CancelButton.IsVisible = mode is Mode.Building or Mode.Playing;
        if (mode is Mode.Building or Mode.Playing) ProgressPanel.IsVisible = true;
        StatusText.Foreground = Brush("MutedBrush");
        switch (mode)
        {
            case Mode.Setup:
                Headline.Text = "Build your copy";
                Subhead.Text = "Verified, extracted and compiled on this computer. Nothing is uploaded.";
                if (_installation is { } installation && File.Exists(installation.Executable))
                {
                    Headline.Text = installation.GameFilesMissing ? "Restore your game files" : "Update your build";
                    Subhead.Text = installation.GameFilesMissing
                        ? "Choose your disc image to run setup again. Your save stays in place."
                        : "This release changed the game code. Choose your disc image to rebuild; your save stays in place.";
                }
                PrimaryButton.Content = "Verify and build";
                break;
            case Mode.Building:
                Headline.Text = "Building";
                Subhead.Text = "Your computer stays awake until the build is done. Closing this window stops it.";
                PrimaryButton.Content = "Building…";
                break;
            case Mode.Ready:
                Headline.Text = "Ready to drive";
                UpdateSummary();
                PrimaryButton.Content = "▶  Play";
                ProgressPanel.IsVisible = false;
                break;
            case Mode.Playing:
                Headline.Text = "Starting";
                Subhead.Text = "The game opens in its own window.";
                PrimaryButton.Content = "Starting…";
                break;
            case Mode.Crashed:
                PrimaryButton.Content = "Report crash";
                ProgressPanel.IsVisible = false;
                break;
        }
        UpdateActions();
    }

    // Which actions are open: nothing runs twice, and Play waits for a panel's work.
    private void UpdateActions()
    {
        PrimaryButton.IsEnabled = !_busy && _mode switch
        {
            Mode.Setup => _discImage is not null && OwnershipCheck.IsChecked == true,
            Mode.Ready or Mode.Crashed => true,
            _ => false,
        };
        RebuildButton.IsEnabled = !_busy;
        SteamButton.IsEnabled = !_busy;
        NavPanel.IsEnabled = !_busy;
        BrowseButton.IsEnabled = BrowseFolderButton.IsEnabled = ChooseInstallRootButton.IsEnabled = !_busy;
    }

    private void SetBusy(bool busy)
    {
        _busy = busy;
        UpdateActions();
    }

    // The resolution the next start uses, under the headline (UpdateSummary on Windows).
    private void UpdateSummary()
    {
        var scale = 1;
        if (_installation is not null)
        {
            var config = Path.Combine(_installation.StateRoot, "config", "pinyon_shift.toml");
            try
            {
                var match = File.Exists(config)
                    ? System.Text.RegularExpressions.Regex.Match(File.ReadAllText(config),
                        @"(?m)^\s*draw_resolution_scale_x\s*=\s*([0-9]+)")
                    : System.Text.RegularExpressions.Match.Empty;
                if (match.Success) scale = Math.Clamp(int.Parse(match.Groups[1].Value), 1, 4);
            }
            catch (IOException) { }
        }
        Subhead.Text = $"Vulkan · {scale}× ({1280 * scale} × {720 * scale}) · F6 or the pause menu opens settings in game";
    }

    private void SetDisc(string path)
    {
        _discImage = path;
        DiscText.Text = Path.GetFileName(Path.TrimEndingDirectorySeparator(path));
        UpdateActions();
    }

    private async void Browse_Click(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Choose your Forza Horizon disc image",
            AllowMultiple = false,
            FileTypeFilter = new[]
            {
                new FilePickerFileType("Disc image") { Patterns = new[] { "*.iso", "*.ISO" } },
                FilePickerFileTypes.All,
            },
        });
        var path = files.Count > 0 ? files[0].TryGetLocalPath() : null;
        if (path is not null) SetDisc(path);
    }

    private async void BrowseFolder_Click(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
            { Title = "Choose your extracted Forza Horizon game folder", AllowMultiple = false });
        var path = folders.Count > 0 ? folders[0].TryGetLocalPath() : null;
        if (path is not null) SetDisc(path);
    }

    // Dropping selects the game source during setup, or imports DLC while
    // the DLC panel is open.
    private string? DroppedPath(DragEventArgs e)
    {
        var paths = e.DataTransfer.TryGetFiles()?.Select(item => item.TryGetLocalPath()).OfType<string>().ToList();
        return paths is { Count: 1 } && (File.Exists(paths[0]) || Directory.Exists(paths[0])) ? paths[0] : null;
    }

    private bool AcceptsDrop => !_busy && (_mode == Mode.Setup || (_mode == Mode.Ready && _panel == Panel.Dlc));

    private void OnDragOver(object? sender, DragEventArgs e)
    {
        var accepted = AcceptsDrop && DroppedPath(e) is not null;
        e.DragEffects = accepted ? DragDropEffects.Copy : DragDropEffects.None;
        DropOverlayText.Text = _mode == Mode.Setup ? "Drop to use this disc image or folder" : "Drop to import this DLC";
        DropOverlay.IsVisible = accepted;
    }

    private async void OnDrop(object? sender, DragEventArgs e)
    {
        DropOverlay.IsVisible = false;
        if (!AcceptsDrop || DroppedPath(e) is not { } path) return;
        if (_mode == Mode.Setup) SetDisc(path);
        else await ImportDlcAsync(path);
    }

    private void Ownership_Changed(object? sender, RoutedEventArgs e) => UpdateActions();

    private async void ChooseInstallRoot_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is not { CanChooseInstallRoot: true } installation || _busy) return;
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "Choose the installation folder (existing installations and saves stay in place)",
            AllowMultiple = false,
        });
        if (folders.Count == 0 || folders[0].TryGetLocalPath() is not { } folder) return;
        // pinyon.py paths --check: writable, free space, a file system that
        // keeps symlinks and executables.
        SetBusy(true);
        StatusText.Text = "Checking the folder…";
        var check = await installation.RunJsonAsync(new[] { "paths", "--check", folder });
        SetBusy(false);
        StatusText.Text = "";
        if (check.Json is { } json && json.TryGetProperty("check", out var result) &&
            result.TryGetProperty("problems", out var problems) && problems.GetArrayLength() > 0)
        {
            var text = string.Join("\n", problems.EnumerateArray().Select(problem => "· " + problem.GetString()));
            if (await Dialog.AskAsync(this, "This folder may not work", $"{folder}\n\n{text}",
                    "Choose another", "Use it anyway") != "Use it anyway")
                return;
        }
        AppendLog($"Installing to {folder}.");
        await LoadAsync(folder);
    }

    private async void Primary_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is null || _busy) return;
        if (_mode == Mode.Crashed)
            ReportCrash();
        else if (_mode == Mode.Setup && _discImage is not null)
        {
            if (!await ConfirmGraphicsDriverBeforeBuildAsync()) return;
            await BuildAsync(new[] { "setup", "--json", Directory.Exists(_discImage) ? "--extracted" : "--iso", _discImage });
        }
        else if (_mode == Mode.Ready)
            await PlayAsync();
    }

    private async void Rebuild_Click(object? sender, RoutedEventArgs e) =>
        await BuildAsync(new[] { "setup", "--json", "--build-only" });

    private async Task BuildAsync(string[] arguments)
    {
        if (_installation is null) return;
        _log.Clear();
        LogBox.Text = "";
        StatusText.Text = "";
        SetProgress(0, "Starting.");
        ShowMode(Mode.Building);
        _cancel = new CancellationTokenSource();
        string? failure = null;
        var code = await _installation.RunAsync(arguments, update => Dispatcher.UIThread.Post(() =>
        {
            if (update.Error is not null)
            {
                failure = update.Error;
                return;
            }
            Progress.Value = OverallPercent(update.Stage, update.Percent);
            PercentText.Text = $"{Progress.Value:0}%";
            if (update.Message is not null) ProgressMessage.Text = update.Message;
        }), AppendLog, _cancel.Token);
        var cancelled = _cancel.IsCancellationRequested;
        _cancel = null;
        if (code == 0)
        {
            ShowMode(Mode.Ready);
            StatusText.Text = Installation.IsLinux
                ? "Built. Add it to Steam to play from Game Mode with a controller."
                : "Built.";
            return;
        }
        ShowMode(_installation.IsReady() ? Mode.Ready : Mode.Setup);
        ProgressPanel.IsVisible = true;
        StatusText.Foreground = Brush("RedBrush");
        StatusText.Text = cancelled ? "Stopped. Start the build again to resume where it stopped."
            : failure ?? $"The build stopped (exit {code}). See the details or the logs.";
    }

    // setup's stages, weighted by how long each one takes.
    private static double OverallPercent(string stage, double percent) => stage switch
    {
        "verify" => percent * 0.01,
        "extract" => 1 + percent * 0.09,
        "tools" => 10 + percent * 0.10,
        "build" => 20 + percent * 0.80,
        "play" => 100,
        _ => 0,
    };

    private void AppendLog(string line) => Dispatcher.UIThread.Post(() =>
    {
        _log.AppendLine(line);
        if (_log.Length > 200_000) _log.Remove(0, _log.Length - 150_000);
        try { _sessionLog?.WriteLine($"[{DateTime.Now:HH:mm:ss}] {line}"); }
        catch (IOException) { _sessionLog = null; }
        if (LogBox.IsVisible)
        {
            LogBox.Text = _log.ToString();
            LogBox.CaretIndex = LogBox.Text.Length;
        }
    });

    // .local/logs/launcher.log, as the Windows launcher keeps it.
    private void StartSessionLog()
    {
        if (_installation is null) return;
        try
        {
            _sessionLog?.Dispose();
            Directory.CreateDirectory(_installation.Logs);
            _sessionLog = new StreamWriter(Path.Combine(_installation.Logs, "launcher.log"), append: false)
                { AutoFlush = true };
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { _sessionLog = null; }
    }

    private void SetProgress(double percent, string? message)
    {
        Progress.IsVisible = true;
        Progress.IsIndeterminate = percent < 0;
        if (percent >= 0)
        {
            Progress.Value = percent;
            PercentText.Text = $"{percent:0}%";
        }
        else PercentText.Text = "";
        if (!string.IsNullOrWhiteSpace(message)) ProgressMessage.Text = message;
    }

    // A failure the player can act on, with Play to try again (SetFailure on Windows).
    private void ShowFailure(string headline, string message, Mode mode = Mode.Ready)
    {
        ShowMode(mode);
        Headline.Text = headline;
        Subhead.Text = message;
        // The panel keeps only the details; the headline says what happened.
        ProgressPanel.IsVisible = true;
        CancelButton.IsVisible = false;
        Progress.IsVisible = false;
        ProgressMessage.Text = "";
        PercentText.Text = "";
        if (mode == Mode.Ready) PrimaryButton.Content = "▶  Try again";
        AppendLog($"ERROR: {message}");
    }

    private async void Steam_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is null) return;
        SteamButton.IsEnabled = false;
        StatusText.Text = "Adding to Steam (Steam restarts if it is open)…";
        var output = new StringBuilder();
        var code = await _installation.RunAsync(new[] { "shortcuts", "add" }, _ => { },
            line => { lock (output) output.AppendLine(line); });
        SteamButton.IsEnabled = true;
        StatusText.Text = code == 0
            ? "Added to Steam and the applications menu. On a Steam Deck, return to Game Mode and find "
              + "Pinyon Shift under Non-Steam in your library."
            : "Could not add it to Steam: " + output.ToString().Trim();
    }

    private void Details_Click(object? sender, RoutedEventArgs e)
    {
        LogBox.IsVisible = !LogBox.IsVisible;
        DetailsButton.Content = LogBox.IsVisible ? "Hide details" : "Show details";
        if (LogBox.IsVisible)
        {
            LogBox.Text = _log.ToString();
            LogBox.CaretIndex = LogBox.Text.Length;
        }
    }

    private void Cancel_Click(object? sender, RoutedEventArgs e) => _cancel?.Cancel();

    private void InstallAppleTools_Click(object? sender, RoutedEventArgs e) =>
        Installation.InstallAppleDeveloperTools();

    private async void CheckAppleTools_Click(object? sender, RoutedEventArgs e) => await LoadAsync();

    private void Saves_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is null) return;
        Directory.CreateDirectory(Path.Combine(_installation.StateRoot, "user"));
        Installation.Open(Path.Combine(_installation.StateRoot, "user"));
    }

    private void Logs_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is null) return;
        if (_mode == Mode.Crashed && _pendingReport is { } report)
        {
            Installation.Reveal(report.Bundle);
            return;
        }
        // The game's own logs (runtime.log) once it has run, else setup's.
        var gameLogs = Path.Combine(_installation.StateRoot, "logs");
        if (File.Exists(Path.Combine(gameLogs, "runtime.log")))
        {
            Installation.Open(gameLogs);
            return;
        }
        Directory.CreateDirectory(_installation.Logs);
        Installation.Open(_installation.Logs);
    }

    private void Report_Click(object? sender, RoutedEventArgs e) =>
        Installation.Open($"{Repository}/issues/new?template=bug.yml");

    private void GitHub_Click(object? sender, RoutedEventArgs e) => Installation.Open(Repository);

    // The README section with GitHub Sponsors and Ko-fi; nothing depends on it.
    private void Support_Click(object? sender, RoutedEventArgs e) =>
        Installation.Open($"{Repository}#supporting-the-project");

    protected override void OnClosing(WindowClosingEventArgs e)
    {
        _cancel?.Cancel();
        StopAndroidShare();
        _sessionLog?.Dispose();
        base.OnClosing(e);
    }
}
