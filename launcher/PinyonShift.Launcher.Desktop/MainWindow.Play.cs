using System.Text.Json;
using Avalonia.Interactivity;
using Avalonia.Threading;

namespace PinyonShift.Launcher.Desktop;

// Play, the v4 title update's build before it, and what the game's exit
// means (MainWindow.xaml.cs LaunchGameAsync on Windows): pinyon.py launch
// --json reports normal-exit, crash (with its sanitized bundle),
// graphics-unavailable, config-unavailable, saved-content-unavailable, or an
// error with a reason.
public partial class MainWindow
{
    private sealed record CrashReport(string CrashId, string Bundle, string IssueUrl, long ExitCode);

    private CrashReport? _pendingReport;

    // Exit 1309: the GPU device was lost (src/pinyon_shift_app.cpp,
    // OnHostGpuLoss); POSIX keeps its low 8 bits.
    private static bool IsGpuLoss(long exitCode) =>
        exitCode == 1309 || (!Installation.IsWindows && exitCode == (1309 & 0xFF));

    private string[] StateArguments() => _installation is null ? []
        : ["--state-root", _installation.StateRoot];

    private string[] GameArguments() => _installation is null ? []
        : ["--state-root", _installation.StateRoot, "--game-root", _installation.GameRoot];

    private async Task PlayAsync()
    {
        if (_installation is null) return;
        _log.Clear();
        LogBox.Text = "";
        StatusText.Text = "";
        ShowMode(Mode.Playing);
        _cancel = new CancellationTokenSource();
        SetProgress(0, "Checking graphics for this computer.");
        AppendLog("Checking graphics for this computer. Missing shaders are prepared before the first start.");
        AppendLog("Controls: use controller A, Space, or left click for the selected Xbox menu item; press Enter for Start.");

        // The optional v4 title update runs its own build; the XE mod is made
        // for the base disc and wins over a chosen v4 (as pinyon.py launch).
        var titleUpdate = await _installation.RunJsonAsync(["title-update", "status", .. StateArguments()]);
        if (!titleUpdate.Succeeded)
            AppendLog($"Title update status unavailable, starting the base disc: {titleUpdate.Error("Title-update status")}");
        var xe = await _installation.RunJsonAsync(["xe", "status", .. StateArguments()]);
        var xeOn = xe.Succeeded && Bool(xe.Json, "installed") && Bool(xe.Json, "enabled");
        var wantsV4 = titleUpdate.Succeeded && Bool(titleUpdate.Json, "use") && Bool(titleUpdate.Json, "installed");
        if (xeOn)
            AppendLog(wantsV4
                ? "Starting the XE mod on the base disc; title update v4 is not used while XE is on."
                : "Starting the XE mod. It plays its own save; your base save is untouched.");
        var v4 = wantsV4 && !xeOn;
        if (v4 && (!Bool(titleUpdate.Json, "built") || Bool(titleUpdate.Json, "stale")))
        {
            Headline.Text = "Building title update v4";
            Subhead.Text = "This takes a while the first time. You can leave it running.";
            PrimaryButton.Content = "Building…";
            SetProgress(0, "Building the FH1 v4 title update. This takes a while the first time.");
            AppendLog("Building the FH1 v4 title update from your disc and your verified update.");
            var build = await _installation.RunJsonAsync(["title-update", "build", .. GameArguments()],
                update => Dispatcher.UIThread.Post(() => ShowLaunchEvent(update)), AppendLog, _cancel.Token);
            if (_cancel.IsCancellationRequested)
            {
                _cancel = null;
                ShowFailure("Build cancelled", "Play again to resume the v4 build where it stopped.");
                return;
            }
            if (!build.Succeeded)
            {
                _cancel = null;
                ShowFailure("The v4 build stopped", build.Error("The v4 build") + " Logs has the details.");
                return;
            }
        }
        if (v4) AppendLog("Starting the FH1 v4 title update. Your profile is backed up before its first v4 save.");

        var result = await _installation.RunJsonAsync(
            ["launch", .. GameArguments(), v4 ? "--title-update-v4" : "--base-disc"],
            update => Dispatcher.UIThread.Post(() => ShowLaunchEvent(update)), AppendLog, _cancel.Token);
        var cancelled = _cancel.IsCancellationRequested;
        _cancel = null;
        if (cancelled)
        {
            ShowFailure("Preparation cancelled", "Play again to finish preparing graphics.");
            return;
        }
        ShowLaunchResult(result);
    }

    private static bool Bool(JsonElement? json, string name) =>
        json is { } element && element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;

    private void ShowLaunchEvent(SetupEvent update)
    {
        if (_mode != Mode.Playing) return;
        switch (update.Stage)
        {
            case "shaders":
                Headline.Text = "Preparing graphics";
                Subhead.Text = "Once per build: later starts skip this.";
                PrimaryButton.Content = "Preparing…";
                break;
            case "build":
                Headline.Text = "Building title update v4";
                PrimaryButton.Content = "Building…";
                break;
            case "play":
                Headline.Text = "Driving";
                Subhead.Text = "Controller A, Space, or left click. Enter is Start, F6 opens settings.";
                PrimaryButton.Content = "Game running";
                CancelButton.IsVisible = false;
                break;
        }
        SetProgress(update.Stage == "play" ? 100 : update.Percent, update.Message);
        if (!string.IsNullOrWhiteSpace(update.Message)) AppendLog(update.Message);
    }

    // The same messages as the Windows launcher (MainWindow.xaml.cs:700-735).
    private void ShowLaunchResult(CommandResult launch)
    {
        var result = launch.String("result");
        long exitCode = launch.Json is { } json && json.TryGetProperty("exit_code", out var code) &&
            code.ValueKind == JsonValueKind.Number ? code.GetInt64() : launch.ExitCode;
        switch (result)
        {
            case "normal-exit":
                AppendLog("The game closed normally.");
                ShowMode(Mode.Ready);
                return;
            case "saved-content-unavailable":
                ShowFailure("Restore your saved car's DLC",
                    "Re-enable its DLC in DLC and v4, or import the missing content again, then retry. " +
                    "Your saved car and purchased parts have been preserved.");
                return;
            case "graphics-unavailable":
                ShowFailure("Update the graphics driver",
                    "The game could not start the graphics device. It needs a GPU whose driver supports " +
                    "Vulkan 1.3; " + (Installation.IsMac
                        ? "update macOS, then retry."
                        : Installation.IsLinux
                            ? "install a current Mesa (23.1 or newer) or the NVIDIA driver from your distribution, then retry. "
                              + "A software renderer such as llvmpipe cannot run the game."
                            : "install the newest driver from AMD, Intel or NVIDIA, then retry."));
                return;
            case "config-unavailable":
                ShowFailure("The settings file could not be read",
                    "The game could not read or write its settings file" +
                    (launch.String("config") is { Length: > 0 } config ? $" ({config})" : "") +
                    ". Close other copies of the game, and check that the folder is not read-only " +
                    "or held by a sync app. To start from default settings, rename the file, then retry.");
                return;
            case "crash":
                var report = launch.String("crash_id") is { Length: > 0 } id &&
                             launch.String("bundle") is { Length: > 0 } bundle &&
                             launch.String("issue_url") is { Length: > 0 } issue
                    ? new CrashReport(id, bundle, issue, exitCode) : null;
                if (report is not null && ValidReport(report) is { } valid)
                {
                    ShowCrash(valid);
                    return;
                }
                var signal = launch.String("signal");
                ShowFailure("The game stopped",
                    $"The game exited unexpectedly ({(signal.Length > 0 ? signal : $"exit {exitCode}")}), " +
                    "but its diagnostic report could not be prepared. Logs has the details; Report a problem opens an issue.");
                return;
        }
        // An error before the game ran, with a reason.
        var error = launch.Error("Play");
        switch (launch.String("reason"))
        {
            case "not-built":
                ShowFailure("Build the game first", error, Mode.Setup);
                break;
            case "game-files-missing":
                ShowFailure("Restore your game files",
                    "Choose your disc image to run setup again. Your save stays in place.", Mode.Setup);
                break;
            case "already-running":
                ShowFailure("The game is already running", "Close the other copy of Pinyon Shift, then play again.");
                break;
            case "title-update-missing":
                ShowFailure("Import title update v4 again",
                    "The v4 update is no longer installed. Import it again in DLC and v4, or choose Use base disc there.");
                break;
            case "build-failed":
                ShowFailure("The v4 build stopped", error + " Logs has the details.");
                break;
            case "profile-backup-failed":
                ShowFailure("Your profile could not be backed up",
                    error + " v4 did not start, so your save is unchanged.");
                break;
            case "mods-failed":
                ShowFailure("A mod could not be prepared", error + ". Logs has the details.");
                break;
            case "rally-unavailable":
                ShowFailure("Restore Rally", error + ".");
                break;
            case "shaders-failed":
                ShowFailure("Graphics preparation stopped", error + ". Play again to retry.");
                break;
            default:
                ShowFailure("The game stopped", result.Length == 0 && launch.ExitCode != 0 && launch.Json is null
                    ? $"The launcher's game watcher stopped (exit {launch.ExitCode}). Logs has the details."
                    : error);
                break;
        }
    }

    // A bundle in this state's reports folder and an issue link to this
    // project, as the Windows launcher accepts them (DetectPendingReport).
    private CrashReport? ValidReport(CrashReport report)
    {
        if (_installation is null) return null;
        var reports = Path.GetFullPath(Path.Combine(_installation.StateRoot, "reports"));
        var prefix = Path.TrimEndingDirectorySeparator(reports) + Path.DirectorySeparatorChar;
        var bundle = Path.GetFullPath(report.Bundle);
        // A folder moved since the crash (a portable install) still holds it.
        if (!bundle.StartsWith(prefix, StringComparison.Ordinal)) bundle = Path.Combine(reports, Path.GetFileName(bundle));
        if (!File.Exists(bundle)) return null;
        if (!Uri.TryCreate(report.IssueUrl, UriKind.Absolute, out var issue) || issue.Scheme != Uri.UriSchemeHttps ||
            issue.Host != "github.com" ||
            !issue.AbsolutePath.StartsWith("/arcanite24/pinyon-shift/issues/new", StringComparison.OrdinalIgnoreCase))
            return null;
        return report with { Bundle = bundle, IssueUrl = issue.AbsoluteUri };
    }

    private async Task DetectPendingReportAsync()
    {
        if (_installation is null) return;
        var pending = await _installation.RunJsonAsync(["crash-report", "pending", .. StateArguments()]);
        if (!pending.Succeeded || !Bool(pending.Json, "pending") || _mode != Mode.Ready) return;
        long exitCode = 0;
        var hex = pending.String("exit_code_hex");
        if (hex.StartsWith("0x", StringComparison.OrdinalIgnoreCase))
            long.TryParse(hex[2..], System.Globalization.NumberStyles.HexNumber, null, out exitCode);
        if (ValidReport(new CrashReport(pending.String("crash_id"), pending.String("bundle"),
                pending.String("issue_url"), exitCode)) is { } report)
            ShowCrash(report);
    }

    private void ShowCrash(CrashReport report)
    {
        _pendingReport = report;
        ShowMode(Mode.Crashed);
        Headline.Text = "The game crashed";
        Subhead.Text = "";
        // Usually a driver reset on weak graphics, which the player can act on;
        // the report still helps when it is not.
        if (IsGpuLoss(report.ExitCode))
        {
            Headline.Text = "The graphics driver stopped responding";
            Subhead.Text = (Installation.IsMac ? "Update macOS, which brings the graphics driver. "
                    : "Install the newest graphics driver. ") +
                "On integrated or older graphics, choose Low-spec 60 or a lower resolution scale in Settings, " +
                "then play again.";
        }
        CrashIdText.Text = report.CrashId;
        AppendLog($"Crash report {report.CrashId}: {report.Bundle}");
    }

    private void ReportCrash()
    {
        if (_pendingReport is not { } report || _installation is null) return;
        Installation.Reveal(report.Bundle);
        Installation.Open(report.IssueUrl);
        var marker = Path.Combine(_installation.StateRoot, "reports", "pending-report.json");
        try { if (File.Exists(marker)) File.Delete(marker); } catch (IOException) { }
        PrimaryButton.Content = "Open GitHub again";
    }

    private void DismissCrash_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is not null)
        {
            var marker = Path.Combine(_installation.StateRoot, "reports", "pending-report.json");
            try { if (File.Exists(marker)) File.Delete(marker); } catch (IOException) { }
        }
        _pendingReport = null;
        ShowMode(Mode.Ready);
    }

    // A build takes 20 to 60 minutes, and the game cannot start without a
    // Vulkan 1.3 driver, so a missing or old driver (or a software renderer)
    // is raised before it, with the driver page. The player may build anyway.
    private async Task<bool> ConfirmGraphicsDriverBeforeBuildAsync()
    {
        if (_installation is null) return true;
        var hardware = await HardwareAsync();
        if (hardware is not { } json || !json.TryGetProperty("recommendation", out var recommendation) ||
            !recommendation.TryGetProperty("warning", out var warning) || warning.ValueKind != JsonValueKind.String)
            return true;
        var answer = await Dialog.AskAsync(this, "Graphics driver",
            $"{warning.GetString()}\n\nThe build takes 20 to 60 minutes and the game will not start without a Vulkan 1.3 driver.",
            "Build anyway", "Open the driver page", "Cancel");
        if (answer == "Open the driver page" && json.TryGetProperty("driver_page", out var page) &&
            page.GetString() is { } url && url.StartsWith("https://", StringComparison.Ordinal))
            Installation.Open(url);
        return answer == "Build anyway";
    }
}
