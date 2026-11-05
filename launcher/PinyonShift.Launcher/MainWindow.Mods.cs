using Microsoft.Win32;
using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Imaging;
using PinyonShift.Launcher.Mods;

namespace PinyonShift.Launcher;

// The mod manager (FEATURE_BACKLOG FB-9.1): Mods on the main screen lists <state>/mods with
// what each mod.toml says about the mod, switches them in enabled_mods, and installs and
// removes them. The work is tools/manage-mods.ps1 (tools/pinyon_mods.py),
// which prints one JSON object; ModCatalog (launcher/Shared) holds the words shown.
public partial class MainWindow
{
    private ModsStatus? _mods;
    private int _modImage;
    // What the last change did to the next start's save; shown until another change
    // replaces it or the view opens again.
    private string _modsSaveChange = "";

    private ModEntry? SelectedMod => ModsList.SelectedItem as ModEntry;

    private async void ModsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || _repositoryRoot is null || _stateRoot is null) return;
        if (_panel is not (View.Dlc or View.Android or View.Radio or View.Mods)) _panelBeforeDlc = _panel;
        _modFactsShown = false;
        ShowModFacts();
        ShowPanel(View.Mods);
        await ChangeModsAsync("list");
    }

    private void CloseModsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        ShowPanel(_panelBeforeDlc);
    }

    private async void ModToggle_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || SelectedMod is not { } mod) return;
        var on = !mod.Enabled;
        var success = $"{mod.Title} is {(on ? "on" : "off")} from the next start.";
        // The dot, line and button change at the click; the tool confirms a moment later.
        _mods?.Preview(mod, on);
        ModsList.Items.Refresh();
        ShowSelectedMod();
        ShowModsStatus(success, error: false);
        await ChangeModsAsync(on ? "enable" : "disable", mod.Name, success: success);
    }

    private async void ModOption_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        // The list's first selection is the saved value; only a pick that changes it runs the tool.
        if (sender is not ComboBox { DataContext: ModOption option, SelectedItem: ModChoice choice } list ||
            choice.Value == option.Value || SelectedMod is not { } mod) return;
        if (_busy)
        {
            list.SelectedValue = option.Value;
            return;
        }
        await ChangeModsAsync("option", mod.Name, $"{option.Key}={choice.Value}",
            success: $"{mod.Title}: {option.Title} is {choice.Label} from the next start.");
    }

    private async void ModRemove_Click(object sender, RoutedEventArgs e)
    {
        if (_busy || SelectedMod is not { } mod) return;
        var answer = MessageBox.Show(this, $"Remove {mod.Title}? Its folder is deleted from this PC.", "Remove mod", MessageBoxButton.YesNo, MessageBoxImage.Question);
        if (answer == MessageBoxResult.Yes)
            await ChangeModsAsync("remove", mod.Name, success: $"{mod.Title} removed.");
    }

    private async void InstallModZip_Click(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        var picker = new OpenFileDialog { Title = "Choose a mod's ZIP", Filter = "ZIP files|*.zip|All files|*.*" };
        if (picker.ShowDialog(this) == true) await InstallModAsync(picker.FileName);
    }

    private async void InstallModFolder_Click(object sender, RoutedEventArgs e)
    {
        if (_busy) return;
        var picker = new OpenFolderDialog { Title = "Choose a mod's folder (the one with mod.toml)" };
        if (picker.ShowDialog(this) == true) await InstallModAsync(picker.FolderName);
    }

    private async Task InstallModAsync(string path)
    {
        if (await ChangeModsAsync("install", path: path) is { } error && error.EndsWith(" is already installed"))
        {
            var name = error[..^" is already installed".Length];
            var answer = MessageBox.Show(this, $"{name} is already installed. Replace it with this copy?",
                "Install mod", MessageBoxButton.YesNo, MessageBoxImage.Question);
            if (answer == MessageBoxResult.Yes) await ChangeModsAsync("install", value: "replace", path: path);
        }
    }

    private void OpenModsFolder_Click(object sender, RoutedEventArgs e)
    {
        if (_stateRoot is null) return;
        var folder = Path.Combine(_stateRoot, "mods");
        Directory.CreateDirectory(folder);
        Process.Start(new ProcessStartInfo("explorer.exe", folder) { UseShellExecute = true });
    }

    private void ModPage_Click(object sender, RoutedEventArgs e)
    {
        // The tool passes only http and https links; check again before the shell opens one.
        if (SelectedMod is not { HasUrl: true } mod || !Uri.TryCreate(mod.Url, UriKind.Absolute, out var url) ||
            url.Scheme is not ("http" or "https")) return;
        Process.Start(new ProcessStartInfo(url.AbsoluteUri) { UseShellExecute = true });
    }

    // The list and details grow into the window's spare height: the body is a centred stack
    // in a scroll viewer, so the Mods view would otherwise keep its 206-pixel minimum and
    // leave the rest of a tall window empty. Below the minimum the body scrolls as before.
    private const double ModsBrowserMinimum = 206;

    private void ModsFit_SizeChanged(object sender, SizeChangedEventArgs e) => FitModsBrowser();

    // The body's viewport and content height are settled by the time it reports a change;
    // its own SizeChanged comes before the content is measured again, so a shrinking
    // window would read the old height.
    private void ModsFit_ScrollChanged(object sender, ScrollChangedEventArgs e)
    {
        if (e.ViewportHeightChange != 0 || e.ExtentHeightChange != 0) FitModsBrowser();
    }

    private void FitModsBrowser()
    {
        if (ModsPanel.Visibility != Visibility.Visible || ModsBrowser.Visibility != Visibility.Visible) return;
        var spare = BodyScroll.ViewportHeight - BodyStack.ActualHeight - BodyStack.Margin.Top - BodyStack.Margin.Bottom;
        var height = Math.Max(ModsBrowserMinimum, ModsBrowser.ActualHeight + spare);
        // Setting it changes the stack's size and calls back here once with no spare left.
        if (Math.Abs(height - ModsBrowser.Height) > 1) ModsBrowser.Height = height;
    }

    // The technical facts stay hidden until asked for, then follow the selection until hidden again.
    private bool _modFactsShown;

    private void ModFacts_Click(object sender, RoutedEventArgs e)
    {
        _modFactsShown = !_modFactsShown;
        ShowModFacts();
    }

    private void ShowModFacts()
    {
        ModFactsText.Visibility = _modFactsShown ? Visibility.Visible : Visibility.Collapsed;
        ModFactsButton.Content = _modFactsShown ? "Hide details" : "Details";
        System.Windows.Automation.AutomationProperties.SetName(ModFactsButton,
            _modFactsShown ? "Hide the mod's technical details" : "Show the mod's technical details");
    }

    private void ModsList_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        _modImage = 0;
        ShowSelectedMod();
    }

    private void ModImagePrevious_Click(object sender, RoutedEventArgs e) => StepModImage(-1);

    private void ModImageNext_Click(object sender, RoutedEventArgs e) => StepModImage(1);

    private void StepModImage(int step)
    {
        if (SelectedMod is not { Images.Count: > 1 } mod) return;
        _modImage = (_modImage + step + mod.Images.Count) % mod.Images.Count;
        ShowSelectedMod();
    }

    private void ShowSelectedMod()
    {
        var mod = SelectedMod;
        // Mods aren't observable: a changed one is shown again by rebinding.
        ModDetail.DataContext = null;
        ModDetail.DataContext = mod;
        ModDetail.Visibility = mod is null ? Visibility.Hidden : Visibility.Visible;
        var images = mod?.Images ?? [];
        ModImagePanel.Visibility = images.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
        ModImageControls.Visibility = images.Count > 1 ? Visibility.Visible : Visibility.Collapsed;
        ModImageCount.Text = $"{_modImage + 1} of {images.Count}";
        ModImage.Source = images.Count > 0 ? LoadModImage(images[Math.Min(_modImage, images.Count - 1)]) : null;
    }

    // Read whole and closed, so the mod's folder can be replaced or removed while it shows.
    private static BitmapImage? LoadModImage(string path)
    {
        try
        {
            var image = new BitmapImage();
            image.BeginInit();
            image.CacheOption = BitmapCacheOption.OnLoad;
            image.CreateOptions = BitmapCreateOptions.IgnoreColorProfile;
            image.DecodePixelWidth = 520;
            image.UriSource = new Uri(path);
            image.EndInit();
            image.Freeze();
            return image;
        }
        catch (Exception ex) when (ex is IOException or NotSupportedException or UriFormatException or InvalidOperationException)
        {
            return null;
        }
    }

    // Runs one mods command and shows the result; returns the error message when it failed.
    // The panel keeps its look while the tool runs (a second or two): _busy turns clicks
    // away instead of dimming every control for that long.
    private async Task<string?> ChangeModsAsync(string action, string name = "", string value = "",
        string path = "", string? success = null)
    {
        _busy = true;
        var saveBefore = _mods?.Save;
        if (action == "list") _modsSaveChange = "";
        if (action is not ("enable" or "disable"))
            ShowModsStatus(action switch
            {
                "list" => "Reading mods…",
                "install" => "Installing…",
                _ => "Updating…"
            }, error: false);
        string? failure = null;
        try
        {
            var status = await RunModsToolAsync(action, name, value, path);
            // The mod selected now; a removed one is gone, so the first takes its place.
            var selected = SelectedMod?.Name;
            if (status.Installed.Count > 0)
            {
                selected = status.Installed[0];
                success = status.Installed.Count == 1
                    ? $"{status.Mods.FirstOrDefault(m => m.Name == selected)?.Title ?? selected} installed. Switch it on to play it."
                    : $"Installed {string.Join(", ", status.Installed)}. Switch them on to play them.";
            }
            if (status.AlsoEnabled.Count > 0)
                success += $" It needs {string.Join(", ", status.AlsoEnabled)}, which is on now too.";
            if (status.SaveChangeText(saveBefore) is { Length: > 0 } change) _modsSaveChange = change;
            ApplyMods(status, selected, success);
        }
        catch (Exception ex)
        {
            failure = ex.Message;
            try { ApplyMods(await RunModsToolAsync("list"), SelectedMod?.Name, ex.Message, error: true); }
            catch { ShowModsStatus(ex.Message, error: true); }
            AppendLog($"Mods: {ex.Message}");
        }
        finally
        {
            _busy = false;
        }
        return failure;
    }

    // A failure reads in amber with a capital, so it isn't mistaken for the quiet line a
    // successful change leaves.
    private void ShowModsStatus(string? message, bool error)
    {
        ModsStatusText.Text = error && !string.IsNullOrEmpty(message)
            ? char.ToUpperInvariant(message[0]) + message[1..] + (message.EndsWith('.') ? "" : ".")
            : message ?? "";
        ModsStatusText.Foreground = (System.Windows.Media.Brush)FindResource(error ? "AmberBrush" : "MutedBrush");
    }

    private void ApplyMods(ModsStatus status, string? selected, string? message, bool error = false)
    {
        _mods = status;
        ModsSaveText.Text = status.Notice(_modsSaveChange);
        ModsSaveText.Visibility = ModsSaveText.Text.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
        ModsList.ItemsSource = status.Mods;
        ModsList.SelectedItem = status.Mods.FirstOrDefault(m => m.Name == selected) ?? status.Mods.FirstOrDefault();
        ModsEmptyText.Visibility = status.Mods.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        ModsBrowser.Visibility = status.Mods.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
        ShowSelectedMod();
        ShowModsStatus(message, error);
    }

    private async Task<ModsStatus> RunModsToolAsync(string action, string name = "", string value = "", string path = "")
    {
        if (_repositoryRoot is null || _stateRoot is null)
            throw new InvalidOperationException("Release source is not ready.");
        var start = new ProcessStartInfo
        {
            FileName = PowerShellExecutable(), WorkingDirectory = _repositoryRoot,
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true
        };
        foreach (var argument in new[] { "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            Path.Combine(_repositoryRoot, "tools", "manage-mods.ps1"), "-Action", action, "-StateRoot", _stateRoot })
            start.ArgumentList.Add(argument);
        if (name.Length > 0) { start.ArgumentList.Add("-Name"); start.ArgumentList.Add(name); }
        if (value.Length > 0) { start.ArgumentList.Add("-Value"); start.ArgumentList.Add(value); }
        if (path.Length > 0) { start.ArgumentList.Add("-Path"); start.ArgumentList.Add(path); }
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Windows could not start mod management.");
        var output = process.StandardOutput.ReadToEndAsync();
        var error = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        var stderr = (await error).Trim();
        var status = ModsStatus.Parse(await output);
        if (process.ExitCode != 0 || status is null || status.Error is not null)
            throw new InvalidOperationException(status?.Error ?? (string.IsNullOrWhiteSpace(stderr) ? "Mod management stopped." : stderr));
        return status;
    }
}
