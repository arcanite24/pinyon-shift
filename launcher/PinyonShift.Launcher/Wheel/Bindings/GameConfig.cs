using System.Diagnostics;
using System.IO;
using System.Text;

namespace PinyonShift.Launcher.Wheel.Bindings;

/// <summary>Finds, reads and updates the game's pinyon_shift.toml (flat top-level keys).</summary>
public static class GameConfig
{
    /// <summary>Configs the launcher could have written, newest first.</summary>
    public static List<string> Find()
    {
        var roots = new List<string>();
        var found = new List<string>();
        void AddFile(string file) { if (File.Exists(file)) found.Add(Path.GetFullPath(file)); }

        if (Environment.GetEnvironmentVariable("PINYON_SHIFT_STATE_ROOT") is { Length: > 0 } state)
            AddFile(Path.Combine(state, "config", "pinyon_shift.toml"));
        if (Environment.GetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT") is { Length: > 0 } install)
            roots.Add(install);
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string pref = Path.Combine(local, "PinyonShift", "install-root.txt");
        try
        {
            if (File.Exists(pref) && File.ReadAllText(pref).Trim() is { Length: > 0 } chosen) roots.Add(chosen);
        }
        catch (IOException) { }
        roots.Add(Path.Combine(local, "PinyonShift"));
        // A portable launcher keeps its data beside itself.
        string exeDir = AppContext.BaseDirectory;
        string? processDir = Path.GetDirectoryName(Environment.ProcessPath);
        foreach (var dir in new[] { processDir, exeDir })
        {
            if (dir == null) continue;
            roots.Add(Path.Combine(dir, "data"));
            if (Path.GetDirectoryName(dir) is { } parent) roots.Add(Path.Combine(parent, "data"));
        }
        foreach (string root in roots)
        {
            string source = Path.Combine(root, "source");
            if (!Directory.Exists(source)) continue;
            try
            {
                foreach (string version in Directory.EnumerateDirectories(source))
                    AddFile(Path.Combine(version, ".local", "preview", "config", "pinyon_shift.toml"));
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
        return found.Distinct(StringComparer.OrdinalIgnoreCase)
                    .OrderByDescending(File.GetLastWriteTimeUtc).ToList();
    }

    public static bool GameRunning() => Process.GetProcessesByName("pinyon_shift").Length > 0;

    /// <summary>Top-level keys and their values (strings unquoted and unescaped).</summary>
    public static Dictionary<string, string> Read(string file)
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (string raw in File.ReadAllLines(file))
        {
            string line = raw.Trim();
            if (line.StartsWith('[')) break;
            if (line.Length == 0 || line.StartsWith('#')) continue;
            int eq = line.IndexOf('=');
            if (eq <= 0) continue;
            string key = line[..eq].Trim();
            string value = line[(eq + 1)..].Trim();
            if (value.StartsWith('"'))
            {
                var sb = new StringBuilder();
                for (int i = 1; i < value.Length; i++)
                {
                    char c = value[i];
                    if (c == '\\' && i + 1 < value.Length)
                    {
                        char n = value[++i];
                        sb.Append(n switch { 'n' => '\n', 't' => '\t', _ => n });
                    }
                    else if (c == '"') break;
                    else sb.Append(c);
                }
                value = sb.ToString();
            }
            else if (value.StartsWith('\''))
            {
                int end = value.IndexOf('\'', 1);
                value = end > 0 ? value[1..end] : value[1..];
            }
            else
            {
                int hash = value.IndexOf('#');
                if (hash >= 0) value = value[..hash].Trim();
            }
            values[key] = value;
        }
        return values;
    }

    /// <summary>Replaces or adds top-level `key = value` lines, keeping everything else. Backs the
    /// file up first unless <paramref name="backup"/> is false; returns the backup's path, or null.</summary>
    public static string? Update(string file, IReadOnlyList<(string Key, string Value)> lines, bool backup = true)
    {
        string text = File.ReadAllText(file);
        bool bom = File.ReadAllBytes(file) is [0xEF, 0xBB, 0xBF, ..];
        string newline = text.Contains("\r\n") ? "\r\n" : "\n";
        var rows = text.Replace("\r\n", "\n").Split('\n').ToList();
        if (rows.Count > 0 && rows[^1].Length == 0) rows.RemoveAt(rows.Count - 1);
        int table = rows.FindIndex(r => r.TrimStart().StartsWith('['));
        if (table < 0) table = rows.Count;

        var added = new List<string>();
        foreach (var (key, value) in lines)
        {
            bool replaced = false;
            for (int i = 0; i < table; i++)
            {
                string t = rows[i].Trim();
                if (t.StartsWith(key, StringComparison.Ordinal) && t[key.Length..].TrimStart().StartsWith('='))
                {
                    rows[i] = $"{key} = {value}";
                    replaced = true;
                }
            }
            if (!replaced) added.Add($"{key} = {value}");
        }
        if (added.Count > 0)
        {
            added.Insert(0, "# Set by the Pinyon Shift launcher's wheel screen");
            rows.InsertRange(table, added);
        }

        string? backupPath = null;
        if (backup)
        {
            backupPath = $"{file}.wheel-backup-{DateTime.Now:yyyyMMdd-HHmmss}";
            File.Copy(file, backupPath, overwrite: true);
        }
        string temporary = file + ".tmp";
        File.WriteAllText(temporary, string.Join(newline, rows) + newline, new UTF8Encoding(bom));
        File.Move(temporary, file, overwrite: true);
        return backupPath;
    }
}
