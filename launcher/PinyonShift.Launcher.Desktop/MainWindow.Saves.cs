using System.Text.Json;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;

namespace PinyonShift.Launcher.Desktop;

// Bringing a save over (pinyon.py import-save, LX-3.8): another install's
// state, its user folder or a ZIP of either, and a Xenia save. Every profile
// here is backed up first; imported DLC and the source are left alone.
public partial class MainWindow
{
    private async Task ImportSaveAsync(string[] arguments, string what)
    {
        if (_installation is null) return;
        SetBusy(true);
        SavesControls.IsEnabled = false;
        SavesStatusText.Foreground = Brush("MutedBrush");
        SavesStatusText.Text = $"Importing {what}…";
        var result = await _installation.RunJsonAsync(new[] { "import-save" }.Concat(arguments).Concat(StateArguments()),
            onLine: AppendLog);
        if (result.Succeeded && result.Json is { } json)
        {
            var profiles = Strings(json, "imported_profiles");
            var modded = Strings(json, "imported_modded_profiles");
            var lines = new List<string>();
            if (json.TryGetProperty("save", out _))
                // --xenia: the save goes beside the current one under its XUID.
                lines.Add($"Imported the Xenia save for profile {result.String("xuid")}; the game loads it from the next start.");
            else
                lines.Add(profiles.Count + modded.Count == 0
                    ? "Nothing was imported."
                    : $"Imported {Count(profiles.Count, "profile")}" +
                      (modded.Count > 0 ? $" and {Count(modded.Count, "modded profile")} (the cheats and mods save)" : "") +
                      ". The game loads it from the next start.");
            if (result.String("backup") is { Length: > 0 } backup) lines.Add($"Your previous profiles are backed up in {backup}.");
            if (result.String("previous_save_kept") is { Length: > 0 } kept) lines.Add($"The previous save is kept in {kept}.");
            if (result.String("config_backup") is { Length: > 0 } config)
                lines.Add($"The game now loads profile {result.String("xuid")}; the settings file before that is in {config}.");
            SavesStatusText.Text = string.Join(" ", lines);
            AppendLog($"Save import: {SavesStatusText.Text}");
        }
        else
        {
            SavesStatusText.Foreground = Brush("RedBrush");
            SavesStatusText.Text = "Nothing was changed: " + result.Error("The save import");
        }
        SavesControls.IsEnabled = true;
        SetBusy(false);
    }

    private static string Count(int count, string noun) => $"{count} {noun}{(count == 1 ? "" : "s")}";

    private static List<string> Strings(JsonElement json, string name) =>
        json.TryGetProperty(name, out var array) && array.ValueKind == JsonValueKind.Array
            ? array.EnumerateArray().Select(item => item.GetString() ?? "").ToList() : [];

    private async void ImportSaveFolder_Click(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
            { Title = "Choose the other install's folder (its .local/preview or user folder)", AllowMultiple = false });
        if (folders.Count > 0 && folders[0].TryGetLocalPath() is { } path)
            await ImportSaveAsync([path], "the save");
    }

    private async void ImportSaveZip_Click(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "Choose a ZIP of another install's save",
            AllowMultiple = false,
            FileTypeFilter = new[]
            {
                new FilePickerFileType("ZIP archives") { Patterns = new[] { "*.zip", "*.ZIP" } },
                FilePickerFileTypes.All,
            },
        });
        if (files.Count > 0 && files[0].TryGetLocalPath() is { } path)
            await ImportSaveAsync([path], "the save");
    }

    private async void ImportXeniaSave_Click(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
            { Title = "Choose Xenia's content/<profile>/4D5309C9 folder", AllowMultiple = false });
        if (folders.Count > 0 && folders[0].TryGetLocalPath() is { } path)
            await ImportSaveAsync(["--xenia", path], "the Xenia save");
    }
}
