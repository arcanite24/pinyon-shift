using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace PinyonShift.Launcher.Sharing;

// What the Android share offers, and the groups' order of mods to enable.
public sealed record ShareContent(IReadOnlyList<ShareGroup> Groups, IReadOnlyList<string> ModsEnabled);

// What the device can copy from this PC (ONE_CLICK_SETUP_BACKLOG A-4), the
// same for every launcher: the extracted game, and from the PC's state the
// v4 update (for a v4 package), imported DLC, the Rally overlay, the PC's
// mods as it plays them (custom radio stations and the XE mod as their own
// rows) and, only when chosen on the device, the save the PC plays.
public static class AndroidShareContent
{
    // Mods the PC's tools generate for the enabled set (build-mod-patches.py,
    // build-mod-archives.py): built for exactly the PC's enabled mods, which
    // is why the device copies the mod groups together.
    public static readonly string[] GeneratedMods = ["zz-db-patches", "zz-archive-patches"];
    public const string RadioMod = "custom_radio";  // tools/pinyon_radio.py
    public const string XeMod = "xe";               // tools/pinyon_xe.py
    public const string ModSet = "mods";

    public static ShareContent Build(string repositoryRoot, string stateRoot, bool titleUpdateV4,
        bool includeMods = true)
    {
        var groups = new List<ShareGroup>();
        var game = Path.Combine(repositoryRoot, ".local", "game", "base");
        if (!File.Exists(Path.Combine(game, "default.xex")))
            throw new IOException($"The extracted game is not at {game}. Build and play on this PC first.");
        groups.Add(new ShareGroup("game", "game files", true, Tree(game, "game/base")));
        var state = stateRoot;
        if (titleUpdateV4)
        {
            var update = Tree(Path.Combine(state, "title-update-v4"), "state/title-update-v4",
                name => !name.Contains('/'));
            if (update.Count > 0) groups.Add(new ShareGroup("title_update_v4", "title update v4", true, update));
        }
        var dlc = Tree(Path.Combine(state, "user", "0000000000000000", "4D5309C9"), "state/user/0000000000000000/4D5309C9")
            .Concat(Tree(Path.Combine(state, "dlc"), "state/dlc",
                name => name.EndsWith(".json", StringComparison.OrdinalIgnoreCase) && !name.Contains('/')))
            .ToList();
        if (dlc.Count > 0) groups.Add(new ShareGroup("dlc", "DLC", true, dlc));
        var rally = Tree(Path.Combine(state, "cache", "rally_adapter"), "state/cache/rally_adapter");
        if (rally.Count > 0) groups.Add(new ShareGroup("rally", "Rally", true, rally));
        var enabled = new List<string>();
        if (includeMods) enabled = AddModGroups(groups, state, titleUpdateV4);
        // The PC plays from user-modded while cheats or mods are on: offer the
        // tree written last.
        static bool IsSave(string name) => !name.StartsWith("0000000000000000/", StringComparison.Ordinal);
        var save = new[] { "user", "user-modded" }
            .Select(tree => Tree(Path.Combine(state, tree), "state/user", IsSave))
            .Where(files => files.Count > 0)
            .OrderByDescending(files => files.Max(file => File.GetLastWriteTimeUtc(file.Source)))
            .FirstOrDefault();
        if (save is not null) groups.Add(new ShareGroup("save", "this PC's save", false, save));
        return new ShareContent(groups, enabled);
    }

    // The PC's enabled mods, in its order, split into the mods group (with
    // the generated patches), custom radio and XE. Only mods the device can
    // load go: asset mods. A native mod's library is a Windows, Linux or
    // macOS binary, and XE targets the base executable, so it is left out of
    // a v4 package. Returns the order to enable on the device.
    private static List<string> AddModGroups(List<ShareGroup> groups, string state, bool titleUpdateV4)
    {
        var shared = new List<string>();
        var buckets = new Dictionary<string, List<string>> { ["mods"] = [], ["radio"] = [], ["xe"] = [] };
        foreach (var name in EnabledMods(state))
        {
            var manifest = Path.Combine(state, "mods", name, "mod.toml");
            if (!File.Exists(manifest)) continue;
            if (Regex.IsMatch(File.ReadAllText(manifest), @"^\s*library\s*=", RegexOptions.Multiline)) continue;
            if (name == XeMod && titleUpdateV4) continue;
            buckets[name == RadioMod ? "radio" : name == XeMod ? "xe" : "mods"].Add(name);
            shared.Add(name);
        }
        if (shared.Count == 0) return shared;
        void Add(string id, string label, List<string> mods)
        {
            if (mods.Count == 0) return;
            var files = mods.SelectMany(mod => Tree(Path.Combine(state, "mods", mod), $"state/mods/{mod}",
                modified: true)).ToList();
            groups.Add(new ShareGroup(id, label, true, files) { Set = ModSet, Mods = mods, Mirror = true });
        }
        Add("mods", "mods: " + string.Join(", ", buckets["mods"].Where(mod => !GeneratedMods.Contains(mod))
            .DefaultIfEmpty("the PC's built patches")), buckets["mods"]);
        Add("radio", "custom radio stations", buckets["radio"]);
        Add("xe", "Forza Horizon XE mod (plays its own new save)", buckets["xe"]);
        return shared;
    }

    // enabled_mods in the state's pinyon_shift.toml, as build-mod-patches.py
    // reads it.
    public static IReadOnlyList<string> EnabledMods(string stateRoot)
    {
        var config = Path.Combine(stateRoot, "config", "pinyon_shift.toml");
        if (!File.Exists(config)) return [];
        var match = Regex.Match(File.ReadAllText(config), @"^enabled_mods[ \t]*=[ \t]*""([^""]*)""[ \t]*\r?$",
            RegexOptions.Multiline);
        return match.Success
            ? match.Groups[1].Value.Split(',').Select(name => name.Trim()).Where(name => name.Length > 0).ToList()
            : [];
    }

    private static IReadOnlyList<ShareFile> Tree(string source, string destination,
        Func<string, bool>? include = null, bool modified = false)
    {
        if (!Directory.Exists(source)) return [];
        return Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories)
            .Select(path => (path, relative: Path.GetRelativePath(source, path).Replace('\\', '/')))
            .Where(entry => include?.Invoke(entry.relative) ?? true)
            .Select(entry =>
            {
                var info = new FileInfo(entry.path);
                return new ShareFile(entry.path, destination + "/" + entry.relative, info.Length,
                    modified ? new DateTimeOffset(info.LastWriteTimeUtc).ToUnixTimeMilliseconds() : null);
            })
            .ToList();
    }

    // The mods' generated patches, rebuilt from this PC's game files for its
    // enabled mods, as every launch does (launch-preview.ps1, pinyon.py
    // build_mods); the device's game files come from the same disc. The
    // first step also installs the built-in mods. Null when both succeeded,
    // otherwise what failed.
    public static async Task<string?> BuildModsAsync(string python, string repositoryRoot, string stateRoot,
        string gameRoot, string? archiveExtractor, CancellationToken cancel = default)
    {
        var tools = Path.Combine(repositoryRoot, "tools");
        var patches = new List<string> { Path.Combine(tools, "build-mod-patches.py"), stateRoot, "--game-root", gameRoot };
        if (await RunAsync(python, repositoryRoot, patches, cancel) is { } patchError)
            return "The mods' database patches could not be built: " + patchError;
        var archives = new List<string> { Path.Combine(tools, "build-mod-archives.py"), stateRoot, "--game-root", gameRoot };
        if (archiveExtractor is not null && File.Exists(archiveExtractor))
            archives.AddRange(["--archive-extractor", archiveExtractor]);
        if (await RunAsync(python, repositoryRoot, archives, cancel) is { } archiveError)
            return "The mods' archive members could not be built: " + archiveError;
        return null;
    }

    private static async Task<string?> RunAsync(string python, string workingDirectory, IEnumerable<string> arguments,
        CancellationToken cancel)
    {
        var start = new ProcessStartInfo(python)
        {
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        start.Environment["PYTHONUTF8"] = "1";
        try
        {
            using var process = Process.Start(start) ?? throw new InvalidOperationException("Python did not start.");
            var output = process.StandardOutput.ReadToEndAsync(cancel);
            var error = process.StandardError.ReadToEndAsync(cancel);
            await process.WaitForExitAsync(cancel);
            await output;
            var message = (await error).Trim();
            if (process.ExitCode == 0) return null;
            var last = message.Split('\n').Select(line => line.Trim()).LastOrDefault(line => line.Length > 0);
            return last ?? $"exit {process.ExitCode}";
        }
        catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            return ex.Message;
        }
    }

    // The pinned Python setup provisions (config/release-toolchain.json), as
    // tools/release-common.ps1 Get-PinyonPython finds it on Windows; the
    // platform's entry elsewhere. Null when it is not there.
    public static string? ToolchainPython(string repositoryRoot)
    {
        var config = Path.Combine(repositoryRoot, "config", "release-toolchain.json");
        if (!File.Exists(config)) return null;
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(config));
            var root = document.RootElement;
            JsonElement python;
            if (OperatingSystem.IsWindows())
            {
                if (!root.TryGetProperty("python", out python)) return null;
            }
            else
            {
                var platform = OperatingSystem.IsMacOS() ? "macos-arm64" : "linux-x86_64";
                if (!root.TryGetProperty("posix", out var platforms) ||
                    !platforms.TryGetProperty(platform, out var entry) || !entry.TryGetProperty("python", out python))
                    return null;
            }
            var path = Path.GetFullPath(Path.Combine(repositoryRoot, python.GetProperty("install_path").GetString()!,
                python.GetProperty("executable").GetString()!));
            return File.Exists(path) ? path : null;
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException)
        {
            return null;
        }
    }
}

// The Android package's build, from the provenance tools/pinyon_android.py
// packs as assets/pinyon_shift_build.json. The app compares it with its own
// to offer the PC's package as an update.
public sealed record AndroidApkInfo(string Version, long VersionCode, string Build, string? CreatedUtc, long Bytes)
{
    public static AndroidApkInfo? TryRead(string apk)
    {
        try
        {
            using var zip = ZipFile.OpenRead(apk);
            var entry = zip.GetEntry("assets/pinyon_shift_build.json");
            if (entry is null) return null;
            using var stream = entry.Open();
            using var document = JsonDocument.Parse(stream);
            var root = document.RootElement;
            var version = root.GetProperty("version").GetString() ?? "";
            var build = root.TryGetProperty("executable_sha256", out var sha) ? sha.GetString() ?? "" : "";
            var created = root.TryGetProperty("created_utc", out var time) ? time.GetString() : null;
            return new AndroidApkInfo(version, CodeOf(version), build, created, new FileInfo(apk).Length);
        }
        catch (Exception ex) when (ex is IOException or InvalidDataException or JsonException or
                                       KeyNotFoundException or InvalidOperationException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    // The package's versionCode, as pinyon_android.py release_version()
    // derives it from the version name: major * 10000 + minor * 100 + patch.
    public static long CodeOf(string version)
    {
        var parts = version.Split('-')[0].Split('.');
        if (parts.Length < 3 || !int.TryParse(parts[0], out var major) || !int.TryParse(parts[1], out var minor) ||
            !int.TryParse(parts[2], out var patch))
            return 0;
        return major * 10000L + minor * 100 + patch;
    }
}
