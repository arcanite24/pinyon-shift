using System.Diagnostics;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;

namespace PinyonShift.Launcher.Desktop;

/// <summary>A progress line from tools/pinyon.py (`::pinyon::{...}`).</summary>
public sealed record SetupEvent(string Stage, double Percent, string? Message, string? Error);

/// <summary>Where the source lives and how tools/pinyon.py is run. The work
/// itself is in tools/pinyon_setup.py, shared with the command line.</summary>
public sealed class Installation
{
    public string Root { get; }
    public string Platform { get; }
    public string StateRoot => Path.Combine(Root, ".local", "preview");
    public string Logs => Path.Combine(Root, ".local", "logs");
    public string BuildDirectory => Path.Combine(Root, "out", "build", $"{Preset}-release");
    public string Executable => Path.Combine(BuildDirectory, "pinyon_shift");
    public static bool IsLinux => RuntimeInformation.IsOSPlatform(OSPlatform.Linux);
    public static bool IsMac => RuntimeInformation.IsOSPlatform(OSPlatform.OSX);
    public static string Version =>
        typeof(Installation).Assembly.GetName().Version?.ToString(3) ?? "dev";

    private string Preset => IsMac ? "macos-arm64" : "linux-amd64";

    private Installation(string root)
    {
        Root = root;
        Platform = IsMac ? "macos-arm64" : "linux-x86_64";
    }

    private static bool IsSourceRoot(string path) =>
        File.Exists(Path.Combine(path, "config", "supported-dumps.json"))
        && File.Exists(Path.Combine(path, "tools", "pinyon_setup.py"))
        && File.Exists(Path.Combine(path, "CMakeLists.txt"));

    public static string InstallRoot()
    {
        var configured = Environment.GetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT");
        if (!string.IsNullOrWhiteSpace(configured)) return Path.GetFullPath(configured);
        var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        if (IsMac) return Path.Combine(home, "Library", "Application Support", "PinyonShift");
        var data = Environment.GetEnvironmentVariable("XDG_DATA_HOME");
        return Path.Combine(string.IsNullOrWhiteSpace(data)
            ? Path.Combine(home, ".local", "share") : data, "PinyonShift");
    }

    /// <summary>A repository checkout around the launcher, or the release's
    /// source payload unpacked under the install root (as on Windows).</summary>
    public static async Task<Installation> OpenAsync()
    {
        var directory = AppContext.BaseDirectory;
        for (var i = 0; i < 8; i++)
        {
            if (IsSourceRoot(directory) && !File.Exists(Path.Combine(directory, ".pinyon-source-sha256")))
                return new Installation(directory);
            var parent = Directory.GetParent(directory);
            if (parent is null) break;
            directory = parent.FullName;
        }
        var payload = FindPayload() ?? throw new FileNotFoundException(
            "Keep pinyon-shift-source.zip beside the launcher, or run it from a repository checkout.");
        var destination = Path.Combine(InstallRoot(), "source", Version);
        var hash = await Task.Run(() =>
        {
            using var stream = File.OpenRead(payload);
            return Convert.ToHexString(SHA256.HashData(stream));
        });
        var marker = Path.Combine(destination, ".pinyon-source-sha256");
        var installed = File.Exists(marker) ? (await File.ReadAllTextAsync(marker)).Trim() : "";
        if (!IsSourceRoot(destination) || !string.Equals(installed, hash, StringComparison.OrdinalIgnoreCase))
        {
            Directory.CreateDirectory(destination);
            // .local (game files, the build's toolchain and saves) is never in the payload.
            await Task.Run(() => ZipFile.ExtractToDirectory(payload, destination, overwriteFiles: true));
            if (!IsSourceRoot(destination))
                throw new InvalidDataException("The source payload is incomplete. Download the launcher again.");
            await File.WriteAllTextAsync(marker, hash + "\n");
        }
        return new Installation(destination);
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

    /// <summary>Ready when the game is built from this payload and its files are there.</summary>
    public bool IsReady()
    {
        if (!File.Exists(Executable)) return false;
        if (!File.Exists(Path.Combine(Root, ".local", "game", "base", "default.xex"))) return false;
        var state = Path.Combine(Root, ".local", "setup-state.json");
        if (!File.Exists(state)) return false;
        var marker = Path.Combine(Root, ".pinyon-source-sha256");
        var build = Path.Combine(Root, ".local", "build.json");
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
                .Select(path => Path.Combine(path, "bin", "python3"))
                .FirstOrDefault(File.Exists);
            if (pinned is not null) return pinned;
        }
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

    /// <summary>Runs tools/pinyon.py, reporting ::pinyon:: events and every line.</summary>
    public async Task<int> RunAsync(IEnumerable<string> arguments, Action<SetupEvent> onEvent,
        Action<string> onLine, CancellationToken cancel = default)
    {
        var start = new ProcessStartInfo(Python())
        {
            WorkingDirectory = Root,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        start.ArgumentList.Add(Path.Combine(Root, "tools", "pinyon.py"));
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        start.Environment["PYTHONUNBUFFERED"] = "1";
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Python did not start.");
        void Read(string? line)
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
                        root.TryGetProperty("percent", out var percent) ? percent.GetDouble() : 0,
                        root.TryGetProperty("message", out var message) ? message.GetString() : null,
                        root.TryGetProperty("error", out var error) ? error.GetString() : null));
                    return;
                }
                catch (JsonException) { }
            }
            onLine(line);
        }
        process.OutputDataReceived += (_, e) => Read(e.Data);
        process.ErrorDataReceived += (_, e) => Read(e.Data);
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        using var registration = cancel.Register(() =>
        {
            try { process.Kill(entireProcessTree: true); } catch (InvalidOperationException) { }
        });
        await process.WaitForExitAsync(CancellationToken.None);
        return process.ExitCode;
    }

    public static void Open(string target)
    {
        var opener = IsMac ? "open" : "xdg-open";
        try { Process.Start(new ProcessStartInfo(opener, $"\"{target}\"") { UseShellExecute = false }); }
        catch (Exception) { }
    }
}
