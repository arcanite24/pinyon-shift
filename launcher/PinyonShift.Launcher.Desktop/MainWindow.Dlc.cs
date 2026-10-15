using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;

namespace PinyonShift.Launcher.Desktop;

// The DLC panel (DlcPanel on Windows): the 21 supported packages with what
// is imported (pinyon.py dlc), title update v4 with 1000 Club offline
// (pinyon.py title-update) and the Forza Horizon XE mod (pinyon.py xe).
public partial class MainWindow
{
    private const string RallyId = "6F6992766050D818245ADD408031E280FB5F4E634D";
    private JsonElement? _titleUpdate;
    private bool _xeInstalled, _xeEnabled;

    private async Task LoadDlcPanelAsync()
    {
        await ChangeDlcAsync(null, null, "Changes apply the next time you start the game.");
        await RefreshTitleUpdateAsync();
        await RefreshXeAsync();
    }

    // config/supported-dlc.json: every package the verifier accepts, in its order.
    private IReadOnlyList<(string Id, string Name)> SupportedDlc()
    {
        if (_installation is null) return [];
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(
                Path.Combine(_installation.Root, "config", "supported-dlc.json")));
            return document.RootElement.GetProperty("packages").EnumerateArray()
                .Select(package => (package.GetProperty("package_id").GetString()!.ToUpperInvariant(),
                    package.GetProperty("display_name").GetString() ?? ""))
                .ToList();
        }
        catch (Exception error) when (error is IOException or JsonException or KeyNotFoundException
                                          or InvalidOperationException)
        {
            return [];
        }
    }

    private async Task ChangeDlcAsync(string[]? action, string? working, string success)
    {
        if (_installation is null) return;
        SetBusy(true);
        DlcControls.IsEnabled = false;
        DlcList.IsEnabled = false;
        DlcStatusText.Text = working ?? "Reading content…";
        string message = success;
        if (action is not null)
        {
            var change = await _installation.RunJsonAsync(new[] { "dlc" }.Concat(action).Concat(StateArguments()),
                onLine: AppendLog);
            if (!change.Succeeded)
            {
                message = change.Error("DLC management");
                AppendLog($"DLC: {message}");
            }
        }
        // A batch may have completed some packages before a failure: the
        // list always shows what is on disk.
        var status = await _installation.RunJsonAsync(new[] { "dlc", "status" }.Concat(StateArguments()));
        if (status.Succeeded) ShowDlc(status.Json!.Value);
        else message = action is null ? status.Error("DLC management") : message;
        DlcStatusText.Text = message;
        DlcControls.IsEnabled = true;
        DlcList.IsEnabled = true;
        SetBusy(false);
    }

    private void ShowDlc(JsonElement status)
    {
        var installed = status.GetProperty("packages").EnumerateArray()
            .ToDictionary(package => package.GetProperty("package_id").GetString()!.ToUpperInvariant(),
                package => package.Clone());
        var supported = SupportedDlc();
        DlcList.Children.Clear();
        foreach (var (id, name) in supported)
            DlcList.Children.Add(DlcRow(id, name, installed.TryGetValue(id, out var package) ? package : null));
        // Content imported some other way, which the panel can only show.
        foreach (var (id, package) in installed.Where(entry => supported.All(known => known.Id != entry.Key)))
            DlcList.Children.Add(DlcRow(id, package.TryGetProperty("display_name", out var name)
                ? name.GetString() ?? id : id, package));
        var enabled = installed.Values.Count(package => package.TryGetProperty("enabled", out var on) && on.GetBoolean());
        DlcSummaryText.Text = installed.Count == 0
            ? "No DLC imported for this installation."
            : $"{installed.Count} of {supported.Count} imported · {enabled} enabled";
    }

    private Control DlcRow(string id, string name, JsonElement? package)
    {
        var enabled = package is { } p && p.TryGetProperty("enabled", out var on) && on.GetBoolean();
        var status = package is { } q && q.TryGetProperty("status", out var value) ? value.GetString() ?? "" : "";
        var cached = package is { } r && r.TryGetProperty("rally_assets_cached", out var assets) && assets.GetBoolean();
        var canToggle = package is not null && (status == "gameplay_unverified" ||
            (enabled && status is "missing" or "metadata_invalid"));
        var text = package is null ? "Not imported" : status switch
        {
            "missing" => "Content or header missing. Import the original package again.",
            "metadata_invalid" => "Import record damaged. Import the original package again to repair it.",
            "conflict" => "Both enabled and disabled copies exist. Check the content folder.",
            "unmanaged" => "Content imported outside the launcher. Management unavailable.",
            _ when enabled && id == RallyId => cached
                ? "Enabled · Assets cached · Gameplay unverified"
                : "Enabled · Assets not prepared · Gameplay unverified",
            _ => $"{(enabled ? "Enabled" : "Disabled")} · Gameplay unverified",
        };
        var row = new DockPanel();
        if (package is not null)
        {
            var toggle = new Button
            {
                Content = enabled ? "Disable" : "Enable", MinWidth = 88, IsEnabled = canToggle,
                VerticalAlignment = VerticalAlignment.Center, HorizontalContentAlignment = HorizontalAlignment.Center,
            };
            toggle.Classes.Add("quiet");
            toggle.Padding = new Avalonia.Thickness(16, 8);
            Avalonia.Automation.AutomationProperties.SetName(toggle, $"{(enabled ? "Disable" : "Enable")} {name}");
            toggle.Click += async (_, _) => await ChangeDlcAsync([enabled ? "disable" : "enable", id, "--game-root",
                    _installation!.GameRoot],
                !enabled && id == RallyId ? "Verifying Rally and preparing its assets…" : "Updating…",
                "Updated. Applies at the next start; saves were not changed.");
            DockPanel.SetDock(toggle, Dock.Right);
            row.Children.Add(toggle);
        }
        var label = new StackPanel { Margin = new Avalonia.Thickness(0, 0, 18, 0), VerticalAlignment = VerticalAlignment.Center };
        label.Children.Add(new TextBlock
        {
            Text = name, FontSize = 14, TextWrapping = TextWrapping.Wrap,
            Foreground = Brush(package is null ? "MutedBrush" : "FogBrush"),
        });
        label.Children.Add(new TextBlock
        {
            Text = text, FontSize = 12, Margin = new Avalonia.Thickness(0, 2, 0, 0), TextWrapping = TextWrapping.Wrap,
            Foreground = Brush(package is null ? "FaintBrush" : "MutedBrush"),
        });
        row.Children.Add(label);
        return row;
    }

    private Task ImportDlcAsync(string path) => ChangeDlcAsync(["import", path], "Verifying and importing packages…",
        "Import verified. Enable individual packages when ready to test them.");

    private async void ImportDlc_Click(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            { Title = "Choose your FH1 DLC package or ZIP", AllowMultiple = false });
        if (files.Count > 0 && files[0].TryGetLocalPath() is { } path) await ImportDlcAsync(path);
    }

    private async void ImportDlcFolder_Click(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
            { Title = "Choose your FH1 DLC folder", AllowMultiple = false });
        if (folders.Count > 0 && folders[0].TryGetLocalPath() is { } path) await ImportDlcAsync(path);
    }

    // ---- Title update v4 (TITLE_UPDATE_V4_BACKLOG TU-2) ------------------------

    private async Task RefreshTitleUpdateAsync(string? message = null)
    {
        if (_installation is null) return;
        var status = await _installation.RunJsonAsync(new[] { "title-update", "status" }.Concat(GameArguments()));
        if (status.Succeeded) ApplyTitleUpdate(status.Json!.Value, message);
        else TitleUpdateStatusText.Text = message ?? status.Error("Title-update management");
    }

    private void ApplyTitleUpdate(JsonElement status, string? message = null)
    {
        _titleUpdate = status;
        var installed = Bool(status, "installed");
        var use = Bool(status, "use");
        TitleUpdateToggleButton.IsEnabled = installed;
        TitleUpdateClubCheck.IsEnabled = installed;
        TitleUpdateClubCheck.IsChecked = Bool(status, "club");
        TitleUpdateToggleButton.Content = use ? "Use base disc" : "Use v4";
        Avalonia.Automation.AutomationProperties.SetName(TitleUpdateToggleButton,
            use ? "Use the base disc instead of title update v4" : "Use title update v4");
        TitleUpdateStatusText.Text = message ?? (!installed
            ? "Not installed. Import your own update; it is checked against your disc."
            : use
                ? "On. v4 saves cannot go back to the base disc; your profile is backed up first."
                  + (Bool(status, "built") && !Bool(status, "stale") ? "" : " It is built the next time you play.")
                : "Verified and off. The game runs the base disc.");
    }

    private async Task<bool> ChangeTitleUpdateAsync(string[] action, string success)
    {
        if (_installation is null) return false;
        SetBusy(true);
        TitleUpdateControls.IsEnabled = false;
        TitleUpdateClubCheck.IsEnabled = false;
        TitleUpdateStatusText.Text = action[0] == "import" ? "Verifying the title update against your disc…" : "Updating…";
        var result = await _installation.RunJsonAsync(new[] { "title-update" }.Concat(action).Concat(GameArguments()),
            onLine: AppendLog);
        if (result.Succeeded) ApplyTitleUpdate(result.Json!.Value, success);
        else
        {
            var error = result.Error("Title-update management");
            AppendLog($"Title update: {error}");
            await RefreshTitleUpdateAsync(error);
        }
        TitleUpdateControls.IsEnabled = true;
        SetBusy(false);
        return result.Succeeded;
    }

    private async void ImportTitleUpdate_Click(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            { Title = "Choose your FH1 title update package or ZIP", AllowMultiple = false });
        if (files.Count > 0 && files[0].TryGetLocalPath() is { } path)
            await ChangeTitleUpdateAsync(["import", path], "Title update verified against your disc. Choose Use v4 to play it.");
    }

    private async void ImportTitleUpdateFolder_Click(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
            { Title = "Choose the folder with your FH1 title update", AllowMultiple = false });
        if (folders.Count > 0 && folders[0].TryGetLocalPath() is { } path)
            await ChangeTitleUpdateAsync(["import", path], "Title update verified against your disc. Choose Use v4 to play it.");
    }

    private async void TitleUpdateClub_Click(object? sender, RoutedEventArgs e)
    {
        if (_titleUpdate is null) return;
        var on = TitleUpdateClubCheck.IsChecked == true;
        await ChangeTitleUpdateAsync([on ? "club-on" : "club-off"],
            on ? "1000 Club runs offline the next time you start v4." : "1000 Club needs the Forza server again (offline play is off).");
    }

    private async void TitleUpdateToggle_Click(object? sender, RoutedEventArgs e)
    {
        if (_titleUpdate is not { } current) return;
        if (!Bool(current, "use"))
        {
            if (await Dialog.AskAsync(this, "FH1 title update v4",
                    "Title update v4 runs the original Rally and 1000 Club code.\n\n" +
                    "Saves it writes cannot be loaded by the base disc. Your current profile is backed up " +
                    "before the first v4 start, and you can restore it when you switch back.\n\nUse v4?",
                    "Use v4", "Cancel") == "Use v4")
                await ChangeTitleUpdateAsync(["enable"], "v4 is on. It is built the next time you start, if needed.");
            return;
        }
        if (!await ChangeTitleUpdateAsync(["disable"], "The base disc is on.") || _titleUpdate is not { } status) return;
        var savedByV4 = status.TryGetProperty("profiles", out var profiles) &&
            profiles.EnumerateObject().Any(profile => profile.Value.GetString() == "v4");
        if (!savedByV4) return;
        if (!status.TryGetProperty("pre_v4_backups", out var backups) || backups.GetArrayLength() == 0)
        {
            TitleUpdateStatusText.Text = "The base disc is on, but your profile was saved by v4 and no pre-v4 backup exists. The base disc cannot load it.";
            return;
        }
        if (await Dialog.AskAsync(this, "FH1 title update v4",
                "Your profile was saved by v4, which the base disc cannot load.\n\n" +
                "Restore the profile backed up before v4? Your v4 saves are kept in the backups folder.",
                "Restore", "Keep v4 profile") == "Restore")
            await ChangeTitleUpdateAsync(["restore"], "Restored the profile from before v4. Your v4 saves are kept in backups.");
    }

    // ---- The Forza Horizon XE mod (pinyon.py xe) --------------------------------

    private async Task<CommandResult> RunXeAsync(params string[] arguments) =>
        await _installation!.RunJsonAsync(new[] { "xe" }.Concat(arguments).Concat(StateArguments()), onLine: AppendLog);

    private async Task RefreshXeAsync(string? message = null)
    {
        if (_installation is null) return;
        var status = await RunXeAsync("status");
        if (!status.Succeeded)
        {
            XeStatusText.Text = message ?? status.Error("XE management");
            return;
        }
        _xeInstalled = Bool(status.Json, "installed");
        _xeEnabled = _xeInstalled && Bool(status.Json, "enabled");
        var version = _xeInstalled ? status.String("version") : null;
        XeToggleButton.IsEnabled = _xeInstalled;
        XeToggleButton.Content = _xeEnabled ? "Turn off" : "Use XE";
        XeInstallButton.Content = _xeInstalled ? "Reinstall" : "Install XE";
        XeStatusText.Text = message ?? (!_xeInstalled
            ? "Not installed. Download from ModDB opens both downloads in your browser and installs them when they finish; Install XE takes archives you already have."
            : _xeEnabled
                ? $"XE {version} is on. It plays its own new save and hides Horizon Rally; your base save is kept."
                : $"XE {version} is installed and off. The game runs as on the disc.");
    }

    private async Task ChangeXeAsync(string[] arguments, string working, string success)
    {
        SetBusy(true);
        XeControls.IsEnabled = false;
        XeStatusText.Text = working;
        var result = await RunXeAsync(arguments);
        var message = result.Succeeded ? success : result.Error("XE management");
        if (!result.Succeeded) AppendLog($"XE mod: {message}");
        await RefreshXeAsync(message);
        XeControls.IsEnabled = true;
        SetBusy(false);
    }

    private async void XeInstall_Click(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Choose the XE 1.0 download and the 1.01 hotfix",
            AllowMultiple = true,
            FileTypeFilter = new[]
            {
                new FilePickerFileType("XE mod archives") { Patterns = new[] { "*.7z" } },
                FilePickerFileTypes.All,
            },
        });
        var paths = files.Select(file => file.TryGetLocalPath()).OfType<string>().ToArray();
        if (paths.Length == 0) return;
        await ChangeXeAsync(new[] { "install" }.Concat(paths).Append("--replace").ToArray(),
            "Checking and extracting the XE archives. This takes a few minutes…",
            "XE is installed and on. Its first start creates a new save.");
    }

    // ModDB disallows automated downloads, so the player's browser fetches both
    // archives and the tool installs them from Downloads when they finish (#426).
    private async void XeDownload_Click(object? sender, RoutedEventArgs e)
    {
        await ChangeXeAsync(new[] { "install", "--find", "--open-pages", "--wait", "14400", "--replace" },
            "Download both files on the ModDB pages that opened (XE by Teancum, 3.7 GB). " +
            "Installing starts by itself when they finish in your Downloads folder…",
            "XE is installed and on. Its first start creates a new save.");
    }

    private async void XeToggle_Click(object? sender, RoutedEventArgs e)
    {
        if (!_xeInstalled) return;
        if (_xeEnabled)
        {
            await ChangeXeAsync(["disable"], "Updating…", "XE is off. Your base save is used again.");
            return;
        }
        if (await Dialog.AskAsync(this, "Forza Horizon XE mod",
                "The XE mod adds cars and replaces the game's database.\n\n" +
                "It plays its own new save, so your current save is kept as it is, and it hides the " +
                "Horizon Rally expansion while it is on. Title update v4 is not used with XE.\n\nUse XE?",
                "Use XE", "Cancel") == "Use XE")
            await ChangeXeAsync(["enable"], "Updating…", "XE is on. It starts with a new save.");
    }
}
