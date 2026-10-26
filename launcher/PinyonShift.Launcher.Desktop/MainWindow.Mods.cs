using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Platform.Storage;
using PinyonShift.Launcher.Mods;

namespace PinyonShift.Launcher.Desktop;

// The mod manager (FEATURE_BACKLOG FB-9.1): tools/pinyon.py mods, which prints one
// JSON object with --json. ModCatalog (launcher/Shared) holds the words both
// launchers show; this draws them as the Windows launcher's Mods view does.
public partial class MainWindow
{
    private ModsStatus? _mods;
    private string? _selectedMod;
    private int _modImage;
    // What the last change did to the next start's save; shown until another change
    // replaces it or the view opens again.
    private string _modsSaveChange = "";

    private ModEntry? SelectedMod => _mods?.Mods.FirstOrDefault(m => m.Name == _selectedMod);

    private async Task<ModsStatus> RunModsAsync(IEnumerable<string> arguments)
    {
        if (_installation is null) throw new InvalidOperationException("The installation is not ready.");
        var result = await _installation.RunJsonAsync(new[] { "mods" }.Concat(arguments).Concat(StateArguments()),
            onLine: AppendLog);
        if (!result.Succeeded) throw new InvalidOperationException(result.Error("Mod management"));
        return ModsStatus.Parse(result.Json!.Value.GetRawText())
            ?? throw new InvalidOperationException("Mod management returned an invalid result.");
    }

    // Runs one mods command and shows the mods; returns the error message when it failed.
    // The panel keeps its look while the tool runs (a second or two): _busy turns clicks
    // away instead of dimming every control for that long.
    private async Task<string?> ChangeModsAsync(string[] arguments, string working, string? success, string? select = null)
    {
        _busy = true;
        ShowModsStatus(working, error: false);
        var saveBefore = _mods?.Save;
        if (arguments[0] == "list") _modsSaveChange = "";
        string? message = success, failure = null;
        try
        {
            var status = await RunModsAsync(arguments);
            if (status.Installed.Count > 0)
            {
                select = status.Installed[0];
                message = status.Installed.Count == 1
                    ? $"{status.Mods.FirstOrDefault(m => m.Name == select)?.Title ?? select} installed. Switch it on to play it."
                    : $"Installed {string.Join(", ", status.Installed)}. Switch them on to play them.";
            }
            if (status.AlsoEnabled.Count > 0)
                message += $" It needs {string.Join(", ", status.AlsoEnabled)}, which is on now too.";
            if (status.SaveChangeText(saveBefore) is { Length: > 0 } change) _modsSaveChange = change;
            ShowMods(status, select ?? _selectedMod, message);
        }
        catch (Exception error)
        {
            failure = message = error.Message;
            AppendLog($"Mods: {message}");
            try { ShowMods(await RunModsAsync(new[] { "list" }), _selectedMod, message, error: true); }
            catch (Exception) { ShowModsStatus(message, error: true); }
        }
        _busy = false;
        return failure;
    }

    // A failure reads in amber with a capital, so it isn't mistaken for the quiet line a
    // successful change leaves.
    private void ShowModsStatus(string? message, bool error)
    {
        ModsStatusText.Text = error && !string.IsNullOrEmpty(message)
            ? char.ToUpperInvariant(message[0]) + message[1..] + (message.EndsWith('.') ? "" : ".")
            : message ?? "";
        ModsStatusText.Foreground = Brush(error ? "AmberBrush" : "MutedBrush");
    }

    private void ShowMods(ModsStatus status, string? select, string? message, bool error = false)
    {
        _mods = status;
        _selectedMod = status.Mods.FirstOrDefault(m => m.Name == select)?.Name ?? status.Mods.FirstOrDefault()?.Name;
        _modImage = 0;
        ModsSaveText.Text = status.Notice(_modsSaveChange);
        ModsSaveText.IsVisible = ModsSaveText.Text.Length > 0;
        ModsEmptyText.IsVisible = status.Mods.Count == 0;
        ModsBrowser.IsVisible = status.Mods.Count > 0;
        ShowModsStatus(message, error);
        ShowModList();
        ShowSelectedMod();
    }

    private void ShowModList()
    {
        ModsList.Children.Clear();
        foreach (var mod in _mods?.Mods ?? [])
        {
            var dot = new Avalonia.Controls.Shapes.Ellipse
            {
                Width = 8, Height = 8, Margin = new Avalonia.Thickness(0, 6, 10, 0), VerticalAlignment = VerticalAlignment.Top,
                Fill = mod.State switch { "on" => Brush("AccentBrush"), "problem" => Brush("AmberBrush"), _ => Brush("LineStrongBrush") },
            };
            var text = new StackPanel { Spacing = 2 };
            text.Children.Add(new TextBlock { Text = mod.Title, FontSize = 14, TextTrimming = TextTrimming.CharacterEllipsis });
            text.Children.Add(new TextBlock
            {
                Text = mod.StateText, FontSize = 12, TextTrimming = TextTrimming.CharacterEllipsis,
                Foreground = Brush("MutedBrush"),
            });
            var content = new DockPanel();
            DockPanel.SetDock(dot, Dock.Left);
            content.Children.Add(dot);
            content.Children.Add(text);
            var button = new Button
            {
                Content = content, HorizontalAlignment = HorizontalAlignment.Stretch,
                HorizontalContentAlignment = HorizontalAlignment.Left,
            };
            button.Classes.Add("quiet");
            button.Classes.Add("nav");
            button.Classes.Set("selected", mod.Name == _selectedMod);
            Avalonia.Automation.AutomationProperties.SetName(button, mod.AccessibleName);
            button.Click += (_, _) =>
            {
                _selectedMod = mod.Name;
                _modImage = 0;
                ShowModList();
                ShowSelectedMod();
            };
            ModsList.Children.Add(button);
        }
    }

    private void ShowSelectedMod()
    {
        var mod = SelectedMod;
        ModDetail.IsVisible = mod is not null;
        if (mod is null) return;
        ModTitleText.Text = mod.Title;
        ModBylineText.Text = mod.Byline;
        ModProblemText.Text = mod.ProblemText;
        ModProblemText.IsVisible = mod.HasProblems;
        ModDescriptionText.Text = mod.DescriptionText;
        ModFactsText.Text = mod.Facts;
        ModPageButton.IsVisible = mod.HasUrl;
        ToolTip.SetTip(ModPageButton, mod.Url);
        ModToggleButton.Content = mod.ToggleText;
        Avalonia.Automation.AutomationProperties.SetName(ModToggleButton, mod.ToggleAccessibleName);
        ModRemoveButton.IsEnabled = mod.CanRemove;
        ShowModOptions(mod);
        var images = mod.Images;
        ModImageFrame.IsVisible = images.Count > 0;
        ModImageControls.IsVisible = images.Count > 1;
        ModImageCount.Text = $"{_modImage + 1} of {images.Count}";
        (ModImage.Source as IDisposable)?.Dispose();
        ModImage.Source = images.Count > 0 ? LoadModImage(images[Math.Min(_modImage, images.Count - 1)]) : null;
    }

    // The technical facts stay hidden until asked for, then follow the selection until hidden again.
    private bool _modFactsShown;

    private void ModFacts_Click(object? sender, RoutedEventArgs e)
    {
        _modFactsShown = !_modFactsShown;
        ShowModFacts();
    }

    private void ShowModFacts()
    {
        ModFactsText.IsVisible = _modFactsShown;
        ModFactsButton.Content = _modFactsShown ? "Hide details" : "Details";
        Avalonia.Automation.AutomationProperties.SetName(ModFactsButton,
            _modFactsShown ? "Hide the mod's technical details" : "Show the mod's technical details");
    }

    // One list per option the mod declares; a pick runs `mods option` and applies at the next start.
    private void ShowModOptions(ModEntry mod)
    {
        ModOptionsPanel.Children.Clear();
        ModOptionsPanel.IsVisible = mod.HasOptions;
        foreach (var option in mod.Options)
        {
            var panel = new StackPanel { Spacing = 4 };
            panel.Children.Add(new TextBlock { Text = option.Title, FontSize = 13 });
            if (option.HasDescription)
                panel.Children.Add(new TextBlock
                {
                    Text = option.Description, FontSize = 12, TextWrapping = TextWrapping.Wrap,
                    Foreground = Brush("MutedBrush"),
                });
            var list = new ComboBox
            {
                ItemsSource = option.Choices.Select(c => c.Label).ToList(),
                SelectedIndex = Math.Max(0, option.Choices.FindIndex(c => c.Value == option.Value)),
                Width = 220,
            };
            Avalonia.Automation.AutomationProperties.SetName(list, option.Title);
            list.SelectionChanged += async (_, _) =>
            {
                if (list.SelectedIndex < 0 || option.Choices[list.SelectedIndex] is not { } choice ||
                    choice.Value == option.Value) return;
                if (_busy)
                {
                    list.SelectedIndex = option.Choices.FindIndex(c => c.Value == option.Value);
                    return;
                }
                await ChangeModsAsync(new[] { "option", mod.Name, option.Key, choice.Value }, "Updating…",
                    $"{mod.Title}: {option.Title} is {choice.Label} from the next start.", mod.Name);
            };
            panel.Children.Add(list);
            ModOptionsPanel.Children.Add(panel);
        }
    }

    // Read whole, so the mod's folder can be replaced or removed while it shows.
    private static Bitmap? LoadModImage(string path)
    {
        try
        {
            using var stream = new MemoryStream(File.ReadAllBytes(path));
            return Bitmap.DecodeToWidth(stream, 600);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException
                                          or InvalidOperationException or NotSupportedException)
        {
            return null;
        }
    }

    private void ModImagePrevious_Click(object? sender, RoutedEventArgs e) => StepModImage(-1);

    private void ModImageNext_Click(object? sender, RoutedEventArgs e) => StepModImage(1);

    private void StepModImage(int step)
    {
        if (SelectedMod is not { Images.Count: > 1 } mod) return;
        _modImage = (_modImage + step + mod.Images.Count) % mod.Images.Count;
        ShowSelectedMod();
    }

    private async void ModToggle_Click(object? sender, RoutedEventArgs e)
    {
        if (_busy || SelectedMod is not { } mod) return;
        var on = !mod.Enabled;
        var success = $"{mod.Title} is {(on ? "on" : "off")} from the next start.";
        // The dot, line and button change at the click; the tool confirms a moment later.
        _mods?.Preview(mod, on);
        ShowModList();
        ShowSelectedMod();
        await ChangeModsAsync(new[] { on ? "enable" : "disable", mod.Name }, success, success, mod.Name);
    }

    private async void ModRemove_Click(object? sender, RoutedEventArgs e)
    {
        if (_busy || SelectedMod is not { } mod) return;
        if (await Dialog.AskAsync(this, "Remove mod",
                $"Remove {mod.Title}? Its folder is deleted from this computer.",
                "Remove", "Cancel") == "Remove")
            await ChangeModsAsync(new[] { "remove", mod.Name }, "Updating…", $"{mod.Title} removed.");
    }

    private async void InstallModZip_Click(object? sender, RoutedEventArgs e)
    {
        if (_busy) return;
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Choose a mod's ZIP",
            FileTypeFilter = new[] { new FilePickerFileType("ZIP files") { Patterns = new[] { "*.zip" } }, FilePickerFileTypes.All },
        });
        if (files.Select(file => file.TryGetLocalPath()).OfType<string>().FirstOrDefault() is { } path)
            await InstallModAsync(path);
    }

    private async void InstallModFolder_Click(object? sender, RoutedEventArgs e)
    {
        if (_busy) return;
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
            { Title = "Choose a mod's folder (the one with mod.toml)" });
        if (folders.Select(folder => folder.TryGetLocalPath()).OfType<string>().FirstOrDefault() is { } path)
            await InstallModAsync(path);
    }

    private async Task InstallModAsync(string path)
    {
        const string installed = " is already installed";
        if (await ChangeModsAsync(new[] { "install", path }, "Installing…", null) is { } error && error.EndsWith(installed))
        {
            var name = error[..^installed.Length];
            if (await Dialog.AskAsync(this, "Install mod", $"{name} is already installed. Replace it with this copy?",
                    "Replace", "Cancel") == "Replace")
                await ChangeModsAsync(new[] { "install", path, "--replace" }, "Installing…", null);
        }
    }

    private void OpenModsFolder_Click(object? sender, RoutedEventArgs e)
    {
        if (_installation is null) return;
        var folder = Path.Combine(_installation.StateRoot, "mods");
        Directory.CreateDirectory(folder);
        Installation.Open(folder);
    }

    private void ModPage_Click(object? sender, RoutedEventArgs e)
    {
        // The tool passes only http and https links; check again before the system opens one.
        if (SelectedMod is { HasUrl: true } mod && Uri.TryCreate(mod.Url, UriKind.Absolute, out var url) &&
            url.Scheme is "http" or "https")
            Installation.Open(url.AbsoluteUri);
    }
}
