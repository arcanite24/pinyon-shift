using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Win32;

namespace PinyonShift.Launcher;

// Save sync from the launcher (docs/SAVE_SYNC.md): the player picks a folder a sync app
// (Syncthing, Dropbox, OneDrive...) shares between devices. The launcher only writes it to the
// game's pinyon_shift.toml as pinyon_shift_sync_folder; the game does the syncing when it starts.
public partial class MainWindow
{
    private string? SyncConfigPath =>
        _stateRoot is null ? null : Path.Combine(_stateRoot, "config", "pinyon_shift.toml");

    private static readonly Regex SyncFolderLine =
        new(@"(?m)^\s*pinyon_shift_sync_folder\s*=\s*""([^""]*)""[^\r\n]*$");

    // The configured folder, or null when save sync is off.
    private string? ConfiguredSyncFolder()
    {
        var config = SyncConfigPath;
        try
        {
            if (config is null || !File.Exists(config)) return null;
            var match = SyncFolderLine.Match(File.ReadAllText(config));
            var folder = match.Success ? match.Groups[1].Value.Trim() : "";
            return folder.Length == 0 ? null : folder.Replace('/', Path.DirectorySeparatorChar);
        }
        catch (IOException) { return null; }
        catch (UnauthorizedAccessException) { return null; }
    }

    private void UpdateSyncButton() =>
        OpenSyncButton.Content = ConfiguredSyncFolder() is null ? "Save sync" : "Save sync: on";

    private void OpenSyncButton_Click(object sender, RoutedEventArgs e)
    {
        var current = ConfiguredSyncFolder();
        var menu = new ContextMenu { PlacementTarget = OpenSyncButton };
        var choose = new MenuItem { Header = current is null ? "Choose a sync folder…" : "Choose another sync folder…" };
        choose.Click += (_, _) => ChooseSyncFolder(current);
        menu.Items.Add(choose);
        if (current is not null)
        {
            var open = new MenuItem { Header = "Open the sync folder" };
            open.Click += (_, _) =>
            {
                if (Directory.Exists(current))
                    Process.Start(new ProcessStartInfo("explorer.exe", current) { UseShellExecute = true });
            };
            menu.Items.Add(open);
            var off = new MenuItem { Header = "Turn off save sync" };
            off.Click += (_, _) => SetSyncFolder(null);
            menu.Items.Add(off);
        }
        menu.IsOpen = true;
    }

    private void ChooseSyncFolder(string? current)
    {
        if (_stateRoot is null) return;
        var dialog = new OpenFolderDialog
        {
            Title = "Choose a folder your sync app shares between devices",
            InitialDirectory = current ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        };
        if (dialog.ShowDialog(this) != true) return;
        var folder = Path.GetFullPath(dialog.FolderName);
        // An update or a removed install would take the folder with it, and the state folder
        // holds the live save the sync folder must stay apart from.
        if ((_repositoryRoot is not null && IsInside(folder, _repositoryRoot)) || IsInside(folder, _stateRoot))
        {
            MessageBox.Show(this, "Choose a folder outside the Pinyon Shift folders, such as one your sync app already shares.",
                "Save sync", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        SetSyncFolder(folder);
    }

    private void SetSyncFolder(string? folder)
    {
        var config = SyncConfigPath;
        if (config is null) return;
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(config)!);
            var text = File.Exists(config) ? File.ReadAllText(config) : "";
            // Forward slashes: the value is a TOML basic string, where a backslash escapes.
            var line = $"pinyon_shift_sync_folder = \"{(folder ?? "").Replace('\\', '/')}\"";
            text = SyncFolderLine.IsMatch(text)
                ? SyncFolderLine.Replace(text, line.Replace("$", "$$"), 1)
                : text.TrimEnd('\r', '\n') + (text.Length == 0 ? "" : Environment.NewLine) + line + Environment.NewLine;
            var temporary = config + ".tmp";
            File.WriteAllText(temporary, text);
            File.Move(temporary, config, overwrite: true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            MessageBox.Show(this, $"The sync folder could not be saved: {ex.Message}", "Save sync",
                MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }
        UpdateSyncButton();
        if (!_busy) UpdateSummary();
    }

    // The ready line's save sync part, or "" when it is off.
    private string SyncSummary()
    {
        var folder = ConfiguredSyncFolder();
        return folder is null || _stateRoot is null ? "" : " · " + SaveSyncStatus.Describe(folder, _stateRoot);
    }

    private static bool IsInside(string path, string folder)
    {
        var root = Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return (Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar)
            .StartsWith(root, StringComparison.OrdinalIgnoreCase);
    }
}
