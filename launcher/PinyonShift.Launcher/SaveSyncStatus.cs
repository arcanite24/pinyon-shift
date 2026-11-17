using System.IO;

namespace PinyonShift.Launcher;

/// <summary>What the launcher shows about save sync (docs/SAVE_SYNC.md): it
/// reads the manifests the game publishes in &lt;folder&gt;\devices and this
/// device's state in &lt;state&gt;\config\save_sync.toml, never the saves. The game
/// makes every decision when it starts; this is only the status line.</summary>
public static class SaveSyncStatus
{
    public static string Describe(string folder, string stateRoot)
    {
        if (!Directory.Exists(folder)) return "the save sync folder is not reachable";
        var state = Read(Path.Combine(stateRoot, "config", "save_sync.toml"));
        state.TryGetValue("device_id", out var ownId);
        state.TryGetValue("current", out var current);
        var history = Split(state.GetValueOrDefault("history"));
        var devices = Path.Combine(folder, "devices");
        string? newer = null, different = null;
        var others = 0;
        if (Directory.Exists(devices))
        {
            foreach (var path in Directory.EnumerateFiles(devices, "*.toml"))
            {
                var id = Path.GetFileNameWithoutExtension(path);
                if (id.Length != 32 || id == ownId) continue;
                var manifest = Read(path);
                if (!manifest.TryGetValue("save_hash", out var hash) || hash.Length == 0) continue;
                others++;
                var name = manifest.GetValueOrDefault("device_name") ?? "another device";
                if (hash == current || history.Contains(hash)) continue;
                if (string.IsNullOrEmpty(current) || Split(manifest.GetValueOrDefault("history")).Contains(current)) newer ??= name;
                else different ??= name;
            }
        }
        if (different is not null) return $"{different}'s save differs from this PC's; choose in game: F6, Profile, Save sync";
        if (newer is not null) return $"a newer save from {newer} loads when you press Play";
        var last = state.GetValueOrDefault("last_export");
        var shared = string.IsNullOrEmpty(last) ? "not shared yet" : "last shared " + last.Replace('T', ' ').TrimEnd('Z') + " UTC";
        return others == 0 ? $"saves sync through {folder} ({shared})" : $"saves in sync with {others} other device{(others == 1 ? "" : "s")} ({shared})";
    }

    // The flat `name = value` files the game writes (src/config/host_config.h).
    private static Dictionary<string, string> Read(string path)
    {
        var values = new Dictionary<string, string>();
        try
        {
            if (!File.Exists(path)) return values;
            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                var equals = line.IndexOf('=');
                if (line.StartsWith('#') || equals <= 0) continue;
                var name = line[..equals].Trim();
                var value = line[(equals + 1)..];
                var hash = value.IndexOf('#');
                if (hash >= 0) value = value[..hash];
                value = value.Trim().Trim('"');
                values.TryAdd(name, value);
            }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        return values;
    }

    private static HashSet<string> Split(string? list) =>
        [.. (list ?? "").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)];
}
