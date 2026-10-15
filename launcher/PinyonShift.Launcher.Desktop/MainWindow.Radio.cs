using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;

namespace PinyonShift.Launcher.Desktop;

// Custom radio stations: tools/pinyon.py radio, which prints one JSON
// object with --json (#445).
public partial class MainWindow
{
    private async Task<JsonElement> RunRadioAsync(IEnumerable<string> arguments)
    {
        if (_installation is null) throw new InvalidOperationException("The installation is not ready.");
        var result = await _installation.RunJsonAsync(new[] { "radio" }.Concat(arguments).Concat(StateArguments()),
            onLine: AppendLog);
        if (!result.Succeeded) throw new InvalidOperationException(result.Error("Radio management"));
        return result.Json!.Value;
    }

    // Runs one radio command (none: just list) and shows the stations.
    private async Task ChangeRadioAsync(string[] arguments, string working, string? success)
    {
        SetBusy(true);
        RadioControls.IsEnabled = false;
        RadioList.IsEnabled = false;
        RadioStatusText.Text = working;
        string? message = success;
        try
        {
            if (arguments.Length > 0) await RunRadioAsync(arguments);
        }
        catch (Exception error)
        {
            message = error.Message;
        }
        try
        {
            ShowRadio(await RunRadioAsync(new[] { "list" }), message);
        }
        catch (Exception error)
        {
            RadioStatusText.Text = message ?? error.Message;
        }
        RadioControls.IsEnabled = true;
        RadioList.IsEnabled = true;
        SetBusy(false);
    }

    private void ShowRadio(JsonElement status, string? message)
    {
        RadioList.Children.Clear();
        var stations = status.GetProperty("stations").EnumerateArray().ToList();
        foreach (var station in stations) RadioList.Children.Add(RadioRow(station));
        var ffmpeg = status.GetProperty("ffmpeg").ValueKind == JsonValueKind.String;
        RadioNewButton.IsEnabled = status.GetProperty("free_slots").GetArrayLength() > 0;
        RadioFfmpegButton.IsVisible = !ffmpeg;
        RadioStatusText.Text = message ?? (stations.Count == 0
            ? "No custom stations yet."
            : !ffmpeg
                ? "Building stations needs FFmpeg to encode the music. Install it from your package manager or locate the ffmpeg program."
                : status.GetProperty("out_of_date").GetBoolean()
                    ? "Changes are not built yet. Choose Build stations."
                    : "Built and on. The stations play from the next start.");
    }

    private Control RadioRow(JsonElement station)
    {
        var slot = station.GetProperty("slot").GetString()!;
        var name = station.GetProperty("name").GetString()!;
        var replaces = station.GetProperty("replaces").GetString();
        var tracks = station.GetProperty("tracks").GetInt32();
        var missing = station.GetProperty("missing").GetArrayLength();
        var hasLogo = station.GetProperty("logo").ValueKind == JsonValueKind.String;
        var sources = station.GetProperty("sources").EnumerateArray().Select(s => s.GetString()!).ToArray();
        var nameBox = new TextBox { Text = name, MaxLength = 40, Width = 280, HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Left };
        async Task Rename()
        {
            var text = nameBox.Text?.Trim() ?? "";
            if (text.Length == 0 || text == name) { nameBox.Text = name; return; }
            await ChangeRadioAsync(new[] { "rename", slot, text }, "Updating…", $"Renamed to {text}.");
        }
        nameBox.LostFocus += async (_, _) => await Rename();
        nameBox.KeyDown += (_, e) =>
        {
            if (e.Key == Key.Enter) Focus();
            else if (e.Key == Key.Escape) { nameBox.Text = name; Focus(); }
        };
        var keep = new CheckBox
        {
            IsChecked = station.GetProperty("mode").GetString() == "add",
            Content = new TextBlock { Text = "Keep the station's own songs too", FontSize = 12 },
        };
        keep.IsCheckedChanged += async (_, _) => await ChangeRadioAsync(
            new[] { "mode", slot, keep.IsChecked == true ? "add" : "replace" }, "Updating…",
            keep.IsChecked == true ? "Your songs join the station's own." : "Only your songs play on this station.");
        Button Action(string text, Func<Task> run)
        {
            var button = new Button { Content = text, Margin = new Avalonia.Thickness(0, 0, 8, 6) };
            button.Classes.Add("quiet");
            button.Click += async (_, _) => await run();
            return button;
        }
        var actions = new WrapPanel();
        actions.Children.Add(Action("Add folder", async () =>
        {
            var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
                { Title = $"Choose music folders for {name}", AllowMultiple = true });
            var paths = folders.Select(folder => folder.TryGetLocalPath()).OfType<string>().ToArray();
            if (paths.Length > 0)
                await ChangeRadioAsync(new[] { "add", slot }.Concat(paths).ToArray(), "Updating…", "Music added.");
        }));
        actions.Children.Add(Action("Add songs", async () =>
        {
            var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = $"Choose songs for {name}", AllowMultiple = true,
                FileTypeFilter = new[]
                {
                    new FilePickerFileType("Music")
                        { Patterns = new[] { "*.mp3", "*.wav", "*.flac", "*.ogg", "*.m4a", "*.aac", "*.opus", "*.wma" } },
                    FilePickerFileTypes.All,
                },
            });
            var paths = files.Select(file => file.TryGetLocalPath()).OfType<string>().ToArray();
            if (paths.Length > 0)
                await ChangeRadioAsync(new[] { "add", slot }.Concat(paths).ToArray(), "Updating…", "Songs added.");
        }));
        if (sources.Length > 0)
            actions.Children.Add(Action("Clear music", () => ChangeRadioAsync(
                new[] { "remove", slot }.Concat(sources).ToArray(), "Updating…",
                "Music cleared. Your files were not touched.")));
        actions.Children.Add(Action(hasLogo ? "Change logo" : "Logo", async () =>
        {
            var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = $"Choose a PNG logo for {name}",
                FileTypeFilter = new[] { new FilePickerFileType("PNG images") { Patterns = new[] { "*.png" } } },
            });
            var path = files.Select(file => file.TryGetLocalPath()).OfType<string>().FirstOrDefault();
            if (path is not null)
                await ChangeRadioAsync(new[] { "logo", slot, path }, "Updating…",
                    "Logo set. It is fitted into 210 by 100 pixels.");
        }));
        if (hasLogo)
            actions.Children.Add(Action("Own logo", () => ChangeRadioAsync(
                new[] { "logo", slot, "--clear" }, "Updating…", "The station's own logo is back.")));
        actions.Children.Add(Action("Delete", async () =>
        {
            if (await Dialog.AskAsync(this, "Delete station",
                    $"Delete {name}? {replaces} plays as on the disc again after you build stations. " +
                    "Your music files are not touched.", "Delete", "Cancel") == "Delete")
                await ChangeRadioAsync(new[] { "delete", slot }, "Updating…",
                    "Station deleted; your music files were not touched. Build stations to apply.");
        }));
        var details = $"Instead of {replaces} · {tracks} {(tracks == 1 ? "song" : "songs")}"
            + (missing > 0 ? $" · {missing} missing" : "") + (hasLogo ? " · own logo" : "");
        var row = new StackPanel { Spacing = 4 };
        row.Children.Add(nameBox);
        row.Children.Add(new TextBlock
        {
            Text = details, FontSize = 12, TextWrapping = Avalonia.Media.TextWrapping.Wrap,
            Foreground = Brush("MutedBrush"),
        });
        row.Children.Add(keep);
        row.Children.Add(actions);
        return row;
    }

    private async void RadioNew_Click(object? sender, RoutedEventArgs e) =>
        await ChangeRadioAsync(new[] { "create", "My Station" }, "Updating…",
            "Station added. Rename it, add a music folder or songs, then build stations.");

    private async void RadioBuild_Click(object? sender, RoutedEventArgs e) =>
        await ChangeRadioAsync(new[] { "build" },
            "Encoding your music and building the stations. Long playlists take a few minutes…",
            "Stations built. They play from the next start.");

    private async void RadioFfmpeg_Click(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions { Title = "Choose the ffmpeg program" });
        var path = files.Select(file => file.TryGetLocalPath()).OfType<string>().FirstOrDefault();
        if (path is not null)
            await ChangeRadioAsync(new[] { "ffmpeg", path }, "Updating…", "FFmpeg found. Build stations when ready.");
    }
}
