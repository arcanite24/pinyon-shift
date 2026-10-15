using System.Diagnostics;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using PinyonShift.Launcher.Updates;

namespace PinyonShift.Launcher.Desktop;

/// <summary>A progress line from tools/pinyon.py (`::pinyon::{...}`).</summary>
public sealed record SetupEvent(string Stage, double Percent, string? Message, string? Error);

/// <summary>What a `pinyon.py ... --json` command printed: its exit code and
/// the one JSON object (the last stdout line starting with `{`), if any.</summary>
public sealed record CommandResult(int ExitCode, JsonElement? Json, string? LastError)
{
    public bool Succeeded => ExitCode == 0 && Json is { } json && !json.TryGetProperty("error", out _);

    public string String(string name) =>
        Json is { } json && json.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? "" : "";

    /// <summary>The player-facing error: the JSON's, else the last "error:"
    /// line on stderr, else the exit code.</summary>
    public string Error(string what) =>
        String("error") is { Length: > 0 } error ? error
        : LastError is { Length: > 0 } line ? line
        : $"{what} stopped (exit {ExitCode}).";
}

/// <summary>Where the source lives and how tools/pinyon.py is run. The work
/// itself is in tools/pinyon_setup.py and the other pinyon_*.py backends,
/// shared with the command line (.local/backlog-research cli.md).</summary>
public sealed class Installation
{
    public const string PortableMarker = "portable.txt";
    public const string PortableSwitch = "--portable";
    public const string PortableDataFolder = "data";
    // Overrides that would send writes outside a portable folder (PortableMode.cs).
    private static readonly string[] LocationOverrides =
        ["PINYON_SHIFT_INSTALL_ROOT", "PINYON_SHIFT_STATE_ROOT", "PINYON_SHIFT_GAME_ROOT"];

    public string Root { get; }
    public string Platform { get; }
    /// <summary>A repository checkout, not the release payload under an install root.</summary>
    public bool IsCheckout { get; }
    public string StateRoot { get; }
    public string GameRoot { get; }
    public string Logs => Path.Combine(Root, ".local", "logs");
    public string BuildDirectory => Path.Combine(Root, "out", "build", $"{Preset}-release");
    public string V4BuildDirectory => Path.Combine(Root, "out", "build", $"{Preset}-v4");
    public string Executable => Path.Combine(BuildDirectory, "pinyon_shift" + ExeSuffix);
    public string Extractor => Path.Combine(BuildDirectory, "pinyon_shift_fh1_archive_extract" + ExeSuffix);
    public string AndroidApk => Path.Combine(Root, ".local", "android", "pinyon-shift.apk");
    public string AndroidRecord => Path.Combine(Root, ".local", "android", "pinyon-shift.json");
    public static bool IsLinux => RuntimeInformation.IsOSPlatform(OSPlatform.Linux);
    public static bool IsMac => RuntimeInformation.IsOSPlatform(OSPlatform.OSX);
    // Windows keeps the WPF launcher; this one runs there for development.
    public static bool IsWindows => RuntimeInformation.IsOSPlatform(OSPlatform.Windows);
    private static string ExeSuffix => IsWindows ? ".exe" : "";
    public static string Version =>
        typeof(Installation).Assembly.GetName().Version?.ToString(3) ?? "dev";

    private static string Preset => IsMac ? "macos-arm64" : IsWindows ? "win-amd64" : "linux-amd64";

    private Installation(string root, bool checkout)
    {
        Root = root;
        IsCheckout = checkout;
        Platform = IsMac ? "macos-arm64" : IsWindows ? "windows-x86_64" : "linux-x86_64";
        // As the Windows launcher (ResolveStateRoot), an override for testing;
        // a portable install has dropped it from the environment.
        StateRoot = FromEnvironment("PINYON_SHIFT_STATE_ROOT") ?? Path.Combine(root, ".local", "preview");
        GameRoot = FromEnvironment("PINYON_SHIFT_GAME_ROOT") ?? Path.Combine(root, ".local", "game", "base");
    }

    private static string? FromEnvironment(string name) =>
        Environment.GetEnvironmentVariable(name) is { Length: > 0 } value && !string.IsNullOrWhiteSpace(value)
            ? Path.GetFullPath(value) : null;

    private static bool IsSourceRoot(string path) =>
        File.Exists(Path.Combine(path, "config", "supported-dumps.json"))
        && File.Exists(Path.Combine(path, "tools", "pinyon_setup.py"))
        && File.Exists(Path.Combine(path, "CMakeLists.txt"));

    // ---- Install root, portable mode (PortableMode.cs, pinyon_common.install_root) ----

    /// <summary>The folder the player keeps the launcher in: the one holding
    /// the .app bundle on macOS.</summary>
    public static string LauncherDirectory
    {
        get
        {
            var installed = LauncherUpdate.InstalledLauncher();
            return installed.EndsWith(".app", StringComparison.OrdinalIgnoreCase)
                ? Path.GetDirectoryName(installed)! : installed;
        }
    }

    /// <summary>A portable.txt beside the launcher, or --portable for one run.</summary>
    public static bool PortableRequested =>
        File.Exists(Path.Combine(LauncherDirectory, PortableMarker))
        || Environment.GetCommandLineArgs().Skip(1).Any(argument =>
            string.Equals(argument, PortableSwitch, StringComparison.OrdinalIgnoreCase));

    /// <summary>Derived again at every start, so the folder can move.</summary>
    public static string PortableRoot =>
        Path.Combine(Path.TrimEndingDirectorySeparator(Path.GetFullPath(LauncherDirectory)), PortableDataFolder);

    public static string DefaultInstallRoot()
    {
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (IsWindows)
            return Path.Combine(Environment.GetEnvironmentVariable("LOCALAPPDATA") is { Length: > 0 } local
                ? local : Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PinyonShift");
        if (IsMac) return Path.Combine(home, "Library", "Application Support", "PinyonShift");
        var data = Environment.GetEnvironmentVariable("XDG_DATA_HOME");
        return Path.Combine(string.IsNullOrWhiteSpace(data)
            ? Path.Combine(home, ".local", "share") : data, "PinyonShift");
    }

    /// <summary>The folder the player chose with Change, as the Windows
    /// launcher keeps it (install-root.txt in the default root).</summary>
    public static string InstallRootPreference => Path.Combine(DefaultInstallRoot(), "install-root.txt");

    public static bool InstallRootOverridden =>
        !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT"));

    public static string InstallRoot()
    {
        if (PortableRequested) return PortableRoot;
        if (FromEnvironment("PINYON_SHIFT_INSTALL_ROOT") is { } configured) return configured;
        try
        {
            if (File.Exists(InstallRootPreference) &&
                File.ReadAllText(InstallRootPreference).Trim() is { Length: > 0 } chosen)
                return Path.GetFullPath(chosen);
        }
        catch (IOException) { }
        return DefaultInstallRoot();
    }

    /// <summary>Whether the Change link is offered: a release install that is
    /// neither portable nor placed by PINYON_SHIFT_INSTALL_ROOT.</summary>
    public bool CanChooseInstallRoot => !IsCheckout && !PortableRequested && !InstallRootOverridden;

    /// <summary>Creates the portable data folder, proves it is writable, keeps
    /// temporary files inside and drops location overrides. Returns notes for
    /// the log.</summary>
    public static IReadOnlyList<string> PreparePortable()
    {
        var root = PortableRoot;
        var probe = Path.Combine(root, $".write-test-{Guid.NewGuid():N}");
        try
        {
            Directory.CreateDirectory(root);
            File.WriteAllText(probe, "portable");
            File.Delete(probe);
        }
        catch (Exception error) when (error is UnauthorizedAccessException or IOException)
        {
            throw new IOException(
                $"Pinyon Shift cannot write to {root} ({error.Message.TrimEnd('.')}). A portable install keeps its " +
                "build, tools and saves beside the launcher, so that folder must be writable. Move the launcher " +
                $"folder to one you own, or delete {PortableMarker} to install in the usual place.", error);
        }
        var temporary = Path.Combine(root, "temp");
        Directory.CreateDirectory(temporary);
        foreach (var name in IsWindows ? new[] { "TEMP", "TMP" } : new[] { "TMPDIR" })
            Environment.SetEnvironmentVariable(name, temporary);
        var notes = new List<string>();
        foreach (var name in LocationOverrides)
        {
            if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(name))) continue;
            notes.Add($"Portable mode ignores {name}.");
            Environment.SetEnvironmentVariable(name, null);
        }
        return notes;
    }

    /// <summary>A repository checkout around the launcher, or the release's
    /// source payload unpacked under the install root (as on Windows).
    /// installRoot is a folder the player chose; it is remembered once the
    /// source is unpacked there.</summary>
    public static async Task<Installation> OpenAsync(string? installRoot = null)
    {
        var directory = AppContext.BaseDirectory;
        for (var i = 0; i < 8; i++)
        {
            if (IsSourceRoot(directory) && !File.Exists(Path.Combine(directory, ".pinyon-source-sha256")))
                return new Installation(directory, checkout: true);
            var parent = Directory.GetParent(directory);
            if (parent is null) break;
            directory = parent.FullName;
        }
        var payload = FindPayload() ?? throw new FileNotFoundException(
            "Keep pinyon-shift-source.zip beside the launcher, or run it from a repository checkout.");
        var destination = Path.Combine(Path.GetFullPath(installRoot ?? InstallRoot()), "source", Version);
        var hash = await Task.Run(() =>
        {
            using var stream = File.OpenRead(payload);
            return Convert.ToHexString(SHA256.HashData(stream));
        });
        var marker = Path.Combine(destination, ".pinyon-source-sha256");
        var installed = File.Exists(marker) ? (await File.ReadAllTextAsync(marker)).Trim() : "";
        IReadOnlyList<string> entries;
        using (var archive = ZipFile.OpenRead(payload)) entries = PayloadManifest.Entries(archive);
        if (!IsSourceRoot(destination) || !string.Equals(installed, hash, StringComparison.OrdinalIgnoreCase))
        {
            Directory.CreateDirectory(destination);
            // Files an earlier release had and this one dropped. .local (game
            // files, the build's toolchain and saves) is never in the payload.
            PayloadManifest.RemoveStale(destination, entries);
            await Task.Run(() => ZipFile.ExtractToDirectory(payload, destination, overwriteFiles: true));
            if (!IsSourceRoot(destination))
                throw new InvalidDataException("The source payload is incomplete. Download the launcher again.");
            await File.WriteAllTextAsync(marker, hash + "\n");
            PayloadManifest.Write(destination, entries);
        }
        else if (!File.Exists(Path.Combine(destination, PayloadManifest.FileName)))
            PayloadManifest.Write(destination, entries);
        if (installRoot is not null && !PortableRequested)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(InstallRootPreference)!);
            await File.WriteAllTextAsync(InstallRootPreference, Path.GetFullPath(installRoot) + "\n");
        }
        return new Installation(destination, checkout: false);
    }

    private static string? FindPayload()
    {
        var candidates = new List<string> { Path.Combine(AppContext.BaseDirectory, "pinyon-shift-source.zip") };
        // In a macOS bundle the payload sits in Contents/Resources.
        if (IsMac)
            candidates.Add(Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "Resources",
                "pinyon-shift-source.zip")));
        return candidates.FirstOrDefault(File.Exists);
    }

    /// <summary>The game is built but its extracted files are gone: setup
    /// restores them from the disc (the save stays).</summary>
    public bool GameFilesMissing => File.Exists(Executable) && !File.Exists(Path.Combine(GameRoot, "default.xex"));

    /// <summary>Ready when the game is built from this payload and its files are there.</summary>
    public bool IsReady()
    {
        if (!File.Exists(Executable)) return false;
        if (!File.Exists(Path.Combine(GameRoot, "default.xex"))) return false;
        var state = Path.Combine(Root, ".local", "setup-state.json");
        var build = Path.Combine(Root, ".local", "build.json");
        // A checkout built by hand (build-preview, cmake) has no setup state.
        if (IsCheckout) return true;
        if (!File.Exists(state)) return false;
        var marker = Path.Combine(Root, ".pinyon-source-sha256");
        if (!File.Exists(marker) || !File.Exists(build)) return File.Exists(build);
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(build));
            return document.RootElement.TryGetProperty("pinyon_shift_source_payload_sha256", out var value)
                && string.Equals(value.GetString(), File.ReadAllText(marker).Trim(),
                    StringComparison.OrdinalIgnoreCase);
        }
        catch (JsonException) { return false; }
    }

    /// <summary>The pinned Python once setup provisioned it, else the system's.
    /// pinyon_setup.py provisions the pinned one itself when the system's is
    /// older than 3.11 (macOS ships 3.9).</summary>
    public string Python()
    {
        var toolchain = Path.Combine(Root, ".local", "toolchain");
        if (Directory.Exists(toolchain))
        {
            var pinned = Directory.GetDirectories(toolchain, "python-*")
                .Select(path => IsWindows ? Path.Combine(path, "python.exe") : Path.Combine(path, "bin", "python3"))
                .FirstOrDefault(File.Exists);
            if (pinned is not null) return pinned;
        }
        if (IsWindows) return "python.exe";
        if (IsMac) return "/usr/bin/python3";
        foreach (var candidate in new[] { "/usr/bin/python3", "/usr/local/bin/python3" })
            if (File.Exists(candidate)) return candidate;
        return "python3";
    }

    /// <summary>Apple's Command Line Tools (the compiler, and the system
    /// Python behind /usr/bin/python3).</summary>
    public static bool HasAppleDeveloperTools()
    {
        if (!IsMac) return true;
        try
        {
            using var probe = Process.Start(new ProcessStartInfo("/usr/bin/xcode-select", "-p")
            {
                RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false,
            });
            probe!.WaitForExit();
            return probe.ExitCode == 0;
        }
        catch (Exception) { return false; }
    }

    public static void InstallAppleDeveloperTools()
    {
        Process.Start(new ProcessStartInfo("/usr/bin/xcode-select", "--install") { UseShellExecute = false });
    }

    /// <summary>Runs tools/pinyon.py, reporting ::pinyon:: events and every line.
    /// onOutput, when given, also receives the stdout lines alone.</summary>
    public async Task<int> RunAsync(IEnumerable<string> arguments, Action<SetupEvent> onEvent,
        Action<string> onLine, CancellationToken cancel = default, Action<string>? onOutput = null)
    {
        var start = new ProcessStartInfo(Python())
        {
            WorkingDirectory = Root,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        start.ArgumentList.Add(Path.Combine(Root, "tools", "pinyon.py"));
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        start.Environment["PYTHONUNBUFFERED"] = "1";
        start.Environment["PYTHONUTF8"] = "1";
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Python did not start.");
        void Read(string? line, bool output)
        {
            if (line is null) return;
            const string prefix = "::pinyon::";
            if (line.StartsWith(prefix, StringComparison.Ordinal))
            {
                try
                {
                    using var document = JsonDocument.Parse(line[prefix.Length..]);
                    var root = document.RootElement;
                    onEvent(new SetupEvent(
                        root.TryGetProperty("stage", out var stage) ? stage.GetString() ?? "" : "",
                        root.TryGetProperty("percent", out var percent) && percent.ValueKind == JsonValueKind.Number
                            ? percent.GetDouble() : -1,
                        root.TryGetProperty("message", out var message) ? message.GetString() : null,
                        root.TryGetProperty("error", out var error) ? error.GetString() : null));
                    return;
                }
                catch (JsonException) { }
            }
            if (output) onOutput?.Invoke(line);
            onLine(line);
        }
        process.OutputDataReceived += (_, e) => Read(e.Data, true);
        process.ErrorDataReceived += (_, e) => Read(e.Data, false);
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        using var registration = cancel.Register(() =>
        {
            try { process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
        });
        await process.WaitForExitAsync(CancellationToken.None);
        return process.ExitCode;
    }

    /// <summary>Runs a `pinyon.py ... --json` command and returns its object.</summary>
    public async Task<CommandResult> RunJsonAsync(IEnumerable<string> arguments, Action<SetupEvent>? onEvent = null,
        Action<string>? onLine = null, CancellationToken cancel = default)
    {
        string? json = null, lastError = null;
        var gate = new object();
        var code = await RunAsync(arguments.Append("--json"), onEvent ?? (_ => { }), line =>
        {
            if (line.StartsWith("error: ", StringComparison.Ordinal))
                lock (gate) lastError = line["error: ".Length..].Trim();
            // The result object is parsed below; it is not a line for the log.
            if (!line.StartsWith('{')) onLine?.Invoke(line);
        }, cancel, line =>
        {
            if (line.StartsWith('{')) lock (gate) json = line;
        });
        JsonElement? parsed = null;
        if (json is not null)
        {
            try { parsed = JsonDocument.Parse(json).RootElement.Clone(); }
            catch (JsonException) { }
        }
        return new CommandResult(code, parsed, lastError);
    }

    public static void Open(string target)
    {
        try
        {
            if (IsWindows) Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
            else Process.Start(new ProcessStartInfo(IsMac ? "open" : "xdg-open") { UseShellExecute = false, ArgumentList = { target } });
        }
        catch (Exception) { }
    }

    /// <summary>Shows a file in its folder (selected where the desktop can).</summary>
    public static void Reveal(string file)
    {
        try
        {
            if (IsMac) Process.Start(new ProcessStartInfo("open") { UseShellExecute = false, ArgumentList = { "-R", file } });
            else if (IsWindows) Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{file}\"") { UseShellExecute = true });
            else Open(Path.GetDirectoryName(file) ?? file);
        }
        catch (Exception) { }
    }
}
