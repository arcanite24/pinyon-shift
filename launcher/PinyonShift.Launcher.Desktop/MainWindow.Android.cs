using System.Diagnostics;
using Avalonia.Controls;
using System.Text.Json;
using System.Text.RegularExpressions;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using PinyonShift.Launcher.Sharing;

namespace PinyonShift.Launcher.Desktop;

// Android (ONE_CLICK_SETUP_BACKLOG A-2 to A-5, AndroidPanel on Windows): the
// package is built from this computer's game build (pinyon.py android
// build, from title update v4 when it is played here), then installed over
// Wi-Fi with the shared AndroidShare (QR code and pairing code) or, for a
// device with USB debugging on, over adb (pinyon.py android install,
// push-data, push-title-update).
public partial class MainWindow
{
    private AndroidShare? _androidShare;
    private bool _androidPreparing;
    private string? _adbDevice;

    private sealed record AndroidRecord(bool TitleUpdateV4, DateTime? BuiltUtc);

    private AndroidRecord? ReadAndroidRecord()
    {
        if (_installation is null || !File.Exists(_installation.AndroidRecord)) return null;
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(_installation.AndroidRecord));
            var root = document.RootElement;
            return new AndroidRecord(
                root.TryGetProperty("title_update_v4", out var v4) && v4.ValueKind == JsonValueKind.True,
                root.TryGetProperty("built_utc", out var built) && built.TryGetDateTime(out var time) ? time : null);
        }
        catch (Exception error) when (error is IOException or JsonException) { return null; }
    }

    // Whether v4 is played here, so the package is built from it and the
    // update is copied to the device.
    private bool WantsTitleUpdateV4 => _titleUpdate is { } status && Bool(status, "use") && Bool(status, "built");

    private async Task LoadAndroidPanelAsync()
    {
        RefreshAndroidPanel();
        if (_installation is null) return;
        var status = await _installation.RunJsonAsync(new[] { "title-update", "status" }.Concat(GameArguments()));
        if (status.Succeeded) _titleUpdate = status.Json;
        RefreshAndroidPanel();
        await DetectAdbDeviceAsync();
    }

    private void RefreshAndroidPanel()
    {
        if (_installation is null) return;
        var apk = _installation.AndroidApk;
        var built = File.Exists(apk);
        var record = ReadAndroidRecord();
        if (built)
        {
            var info = new FileInfo(apk);
            AndroidApkText.Text = $"{apk}\n{info.Length / (1024.0 * 1024.0):0} MB, built {info.LastWriteTime:g}" +
                (record?.TitleUpdateV4 == true ? ", title update v4." : ".") +
                (WantsTitleUpdateV4 != (record?.TitleUpdateV4 == true)
                    ? WantsTitleUpdateV4
                        ? " You play v4 on this computer now: build again for a v4 package."
                        : " You play the base disc on this computer now: build again for a base package."
                    : "");
        }
        else
            AndroidApkText.Text = "Not built yet. The first build takes 20 to 60 minutes and about 15 GB of disk" +
                (WantsTitleUpdateV4 ? "; it is made from title update v4, as you play on this computer." : ".") +
                " It needs the Android SDK (Android Studio's SDK Manager, or the command-line tools with ANDROID_HOME set).";
        AndroidBuildButton.Content = built ? "Build again" : "Build APK";
        AndroidBuildButton.IsEnabled = !_busy;
        AndroidShowButton.IsEnabled = built;
        AndroidSaveButton.IsEnabled = built;
        AndroidShareButton.IsEnabled = !_busy && built && !_androidPreparing;
        AndroidShareButton.Content = _androidShare is null ? "Share on Wi-Fi" : "Stop sharing";
        AndroidUsbButton.IsEnabled = !_busy && built;
    }

    private void AndroidShow_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is not null && File.Exists(_installation.AndroidApk)) Installation.Reveal(_installation.AndroidApk);
    }

    private async void AndroidSave_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is null || !File.Exists(_installation.AndroidApk)) return;
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = "Save a copy of the Android package",
            SuggestedFileName = "PinyonShift.apk",
            DefaultExtension = "apk",
            FileTypeChoices = new[] { new FilePickerFileType("Android package") { Patterns = new[] { "*.apk" } } },
        });
        if (file?.TryGetLocalPath() is not { } destination) return;
        try
        {
            var source = _installation.AndroidApk;
            await Task.Run(() => File.Copy(source, destination, overwrite: true));
            AndroidStatusText.Text = $"Saved {destination}. Copy it to the device and open it there to install.";
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            AndroidStatusText.Text = $"The copy failed: {error.Message}";
        }
    }

    private async void AndroidShare_Click(object? sender, RoutedEventArgs e)
    {
        if (_androidShare is not null)
        {
            StopAndroidShare();
            AndroidStatusText.Text = "Sharing stopped.";
            return;
        }
        if (_androidPreparing || _installation is not { } installation || !File.Exists(installation.AndroidApk)) return;
        var addresses = AndroidShare.LocalAddresses();
        if (addresses.Count == 0)
        {
            AndroidStatusText.Text = "This computer is not on a local network. Connect it to the same Wi-Fi or router as the device.";
            return;
        }
        var record = ReadAndroidRecord();
        // The mods' generated patches, built for the enabled mods as a launch
        // builds them, so the device gets what this computer plays.
        var includeMods = AndroidShareContent.EnabledMods(installation.StateRoot).Count > 0;
        if (includeMods)
        {
            _androidPreparing = true;
            RefreshAndroidPanel();
            AndroidStatusText.Text = "Preparing this computer's mods for the device…";
            var python = AndroidShareContent.ToolchainPython(installation.Root) ?? installation.Python();
            var modError = await AndroidShareContent.BuildModsAsync(python, installation.Root, installation.StateRoot,
                installation.GameRoot, installation.Extractor);
            _androidPreparing = false;
            if (modError is not null)
            {
                AppendLog($"{modError} Sharing without the mods.");
                includeMods = false;
            }
            if (_panel != Panel.Android || _androidShare is not null) { RefreshAndroidPanel(); return; }
        }
        ShareContent content;
        try
        {
            content = await Task.Run(() => AndroidShareContent.Build(installation.Root, installation.StateRoot,
                record?.TitleUpdateV4 == true, includeMods));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            AndroidStatusText.Text = $"The game files cannot be read: {error.Message}";
            RefreshAndroidPanel();
            return;
        }
        var groups = content.Groups;
        var share = new AndroidShare(installation.AndroidApk, groups, new
        {
            title_update_v4 = record?.TitleUpdateV4 == true,
            club = record?.TitleUpdateV4 == true && _titleUpdate is { } status && Bool(status, "club"),
            // The enabled mods the share carries, in load order.
            mods_enabled = content.ModsEnabled,
        });
        share.Activity += message => Dispatcher.UIThread.Post(() =>
        {
            AndroidStatusText.Text = message;
            AppendLog(message);
        });
        try { share.Start(); }
        catch (Exception error) when (error is System.Net.Sockets.SocketException or UnauthorizedAccessException)
        {
            share.Dispose();
            AndroidStatusText.Text = $"Sharing could not start: {error.Message}";
            return;
        }
        _androidShare = share;
        var url = share.PageUrl(addresses[0]);
        AndroidQrImage.Source = QrCode.Encode(url).ToBitmap();
        AndroidQrPanel.IsVisible = true;
        AndroidCodeText.Text = share.Code[..3] + " " + share.Code[3..];
        AndroidUrlText.Text = $"Without the camera, open {url} in the device's browser." +
            (addresses.Count > 1 ? $" This computer is also at {string.Join(", ", addresses.Skip(1))}." : "") +
            $" On the device, the app finds this computer by itself, or enter {addresses[0]}.";
        AndroidCodePanel.IsVisible = true;
        var total = groups.Sum(group => group.Bytes);
        AndroidStatusText.Text = $"Sharing: {string.Join(", ", groups.Select(group => group.Label))} " +
            $"({total / (1024.0 * 1024 * 1024):0.0} GB). " + (Installation.IsLinux
                ? "If a firewall is on (ufw, firewalld), allow TCP 47615 and UDP 47616 on your local network."
                : Installation.IsMac ? "macOS may ask to allow incoming connections: allow them."
                : "Windows may ask to allow the launcher on private networks: allow it.");
        AppendLog($"Sharing the Android package and game files at {url}.");
        RefreshAndroidPanel();
    }

    private void StopAndroidShare()
    {
        _androidShare?.Dispose();
        _androidShare = null;
        AndroidQrPanel.IsVisible = false;
        AndroidQrImage.Source = null;
        AndroidCodePanel.IsVisible = false;
        RefreshAndroidPanel();
    }

    // adb from the SDK the build uses, or on PATH.
    private string? FindAdb()
    {
        var name = Installation.IsWindows ? "adb.exe" : "adb";
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var roots = new List<string?>
        {
            Environment.GetEnvironmentVariable("ANDROID_HOME"),
            Environment.GetEnvironmentVariable("ANDROID_SDK_ROOT"),
            Installation.IsMac ? Path.Combine(home, "Library", "Android", "sdk") : Path.Combine(home, "Android", "Sdk"),
            _installation is null ? null : Path.Combine(_installation.Root, ".local", "toolchain", "android-sdk"),
        };
        var found = roots.Where(root => !string.IsNullOrWhiteSpace(root))
            .Select(root => Path.Combine(root!, "platform-tools", name)).FirstOrDefault(File.Exists);
        if (found is not null) return found;
        return (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator)
            .Where(folder => folder.Length > 0).Select(folder => Path.Combine(folder, name)).FirstOrDefault(File.Exists);
    }

    // A device with USB debugging on, for developers (A-5); the button stays
    // hidden otherwise.
    private async Task DetectAdbDeviceAsync()
    {
        _adbDevice = null;
        AndroidUsbButton.IsVisible = false;
        if (FindAdb() is not { } adb) return;
        try
        {
            var output = await Task.Run(() =>
            {
                using var process = Process.Start(new ProcessStartInfo(adb, "devices")
                    { UseShellExecute = false, RedirectStandardOutput = true, CreateNoWindow = true })!;
                var text = process.StandardOutput.ReadToEnd();
                if (!process.WaitForExit(10000)) process.Kill();
                return text;
            });
            _adbDevice = output.Split('\n').Skip(1)
                .Select(line => line.Trim().Split('\t'))
                .Where(parts => parts.Length == 2 && parts[1] == "device")
                .Select(parts => parts[0]).FirstOrDefault();
        }
        catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException) { }
        if (_adbDevice is not null && _panel == Panel.Android)
        {
            AndroidUsbButton.IsVisible = true;
            ToolTip.SetTip(AndroidUsbButton, $"Install the app and copy the game to {_adbDevice} over USB with adb.");
        }
    }

    private async void AndroidBuild_Click(object? sender, RoutedEventArgs e)
    {
        if (_busy || _installation is null) return;
        var v4 = WantsTitleUpdateV4;
        // The player sees what will be installed and accepts the Android SDK
        // license before sdkmanager is answered for them.
        if (await Dialog.AskAsync(this, "Build Android APK",
                "Build an Android package (APK) of the game from this computer's build, for your own device" +
                (v4 ? ", with title update v4 as you play it here" : "") + ". " +
                "The first build takes 20 to 60 minutes and about 15 GB of disk.\n\n" +
                "It uses the Android SDK and a JDK 17 on this computer (Android Studio installs both; or set " +
                "ANDROID_HOME and JAVA_HOME). Missing Android NDK, build tools and platform packages are installed " +
                "with the SDK's sdkmanager; those packages are covered by the Android Software Development Kit " +
                "License Agreement (https://developer.android.com/studio/terms).\n\n" +
                "Accept the Android SDK license and build?", "Accept and build", "Cancel") != "Accept and build")
            return;
        StopAndroidShare();
        var build = new List<string> { "android", "build", "--jobs", Environment.ProcessorCount.ToString() };
        if (v4) build.Add("--title-update-v4");
        var succeeded = await RunAndroidStepsAsync("Building for Android",
            "The first build takes 20 to 60 minutes. You can leave it running.",
            [
                (["android", "doctor"], "Checking the Android SDK, NDK and JDK.", 2, true),
                (["android", "doctor", "--install", "--accept-licenses"],
                    "Installing the Android NDK, build tools and platform (a few GB, once).", 10, false),
                (build.ToArray(), "Compiling the game for Android. The first build takes 20 to 60 minutes.", 30, false),
            ]);
        if (!succeeded) return;
        if (!File.Exists(_installation.AndroidApk))
        {
            ShowFailure("Android build stopped", "The Android build completed without producing pinyon-shift.apk.");
            return;
        }
        AppendLog($"Android package: {_installation.AndroidApk}");
        ShowMode(Mode.Ready);
        Headline.Text = "Android package ready";
        await OpenPanelAsync(Panel.Android);
        AndroidStatusText.Text = "Ready. Share on Wi-Fi to install it on the device, or save a copy.";
    }

    private async void AndroidUsb_Click(object? sender, RoutedEventArgs e)
    {
        if (_busy || _installation is null || _adbDevice is not { } device) return;
        StopAndroidShare();
        var steps = new List<(string[], string, double, bool)>
        {
            (["android", "install", "--serial", device], "Installing the app over USB.", 5, false),
            (["android", "push-data", "--serial", device, "--game-root", _installation.GameRoot],
                "Copying the game files (about 7 GB; an interrupted copy resumes).", 20, false),
        };
        if (ReadAndroidRecord()?.TitleUpdateV4 == true)
            steps.Add((["android", "push-title-update", "--serial", device, "--state-root", _installation.StateRoot],
                "Copying title update v4.", 90, false));
        if (!await RunAndroidStepsAsync("Installing over USB", "The game files are about 7 GB; an interrupted copy resumes.",
                steps))
            return;
        ShowMode(Mode.Ready);
        Headline.Text = "Installed on the device";
        await OpenPanelAsync(Panel.Android);
        AndroidStatusText.Text = $"Installed on {device}. Start Pinyon Shift from the device's app list.";
    }

    // Runs pinyon.py android steps in order with the progress panel. A step
    // marked optional that succeeds skips the next one (doctor before its
    // --install). Ninja's [done/total] lines move the bar inside a step.
    private async Task<bool> RunAndroidStepsAsync(string headline, string subhead,
        IReadOnlyList<(string[] Arguments, string Message, double Percent, bool SkipNextOnSuccess)> steps)
    {
        if (_installation is null) return false;
        ShowMode(Mode.Building);
        Headline.Text = headline;
        Subhead.Text = subhead;
        _log.Clear();
        LogBox.Text = "";
        _cancel = new CancellationTokenSource();
        var ninja = new Regex(@"^\[(\d+)/(\d+)\]");
        try
        {
            for (var index = 0; index < steps.Count; index++)
            {
                var (arguments, message, start, skipNext) = steps[index];
                var end = index + 1 < steps.Count ? steps[index + 1].Percent : 100;
                SetProgress(start, message);
                AppendLog(message);
                string? lastError = null;
                var code = await _installation.RunAsync(arguments, _ => { }, line =>
                {
                    AppendLog(line);
                    if (line.StartsWith("error: ", StringComparison.Ordinal)) lastError = line["error: ".Length..];
                    if (ninja.Match(line) is { Success: true } match &&
                        double.TryParse(match.Groups[2].Value, out var total) && total > 0)
                    {
                        var done = double.Parse(match.Groups[1].Value);
                        Dispatcher.UIThread.Post(() => SetProgress(start + (end - start) * done / total, null));
                    }
                }, _cancel.Token);
                if (_cancel.IsCancellationRequested)
                {
                    ShowFailure($"{headline} cancelled", "Start it again to resume where it stopped.");
                    return false;
                }
                if (code == 0 && skipNext) { index++; continue; }
                if (code != 0 && !skipNext)
                {
                    ShowFailure($"{headline} stopped", (lastError is null ? $"{message} failed (exit {code})." : lastError + ".")
                        + " Show details has the log.");
                    return false;
                }
            }
            SetProgress(100, "Done.");
            return true;
        }
        finally
        {
            _cancel = null;
        }
    }
}
