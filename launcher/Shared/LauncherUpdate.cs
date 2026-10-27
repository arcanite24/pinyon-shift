using System.Diagnostics;
using System.Formats.Tar;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;

namespace PinyonShift.Launcher.Updates;

/// <summary>A release version: major.minor.patch with an optional
/// prerelease part (0.5.0-preview.1), ordered as in Semantic Versioning.</summary>
public sealed class ReleaseVersion : IComparable<ReleaseVersion>
{
    public int Major { get; }
    public int Minor { get; }
    public int Patch { get; }
    public IReadOnlyList<string> Prerelease { get; }

    private ReleaseVersion(int major, int minor, int patch, string[] prerelease)
    {
        Major = major;
        Minor = minor;
        Patch = patch;
        Prerelease = prerelease;
    }

    /// <summary>Accepts a release tag ("v0.4.0") or a version ("0.5.0-preview.1").
    /// Build metadata after '+' is ignored.</summary>
    public static bool TryParse(string? text, out ReleaseVersion version)
    {
        version = null!;
        if (string.IsNullOrWhiteSpace(text)) return false;
        var value = text.Trim();
        if (value.StartsWith('v') || value.StartsWith('V')) value = value[1..];
        var plus = value.IndexOf('+');
        if (plus >= 0) value = value[..plus];
        var dash = value.IndexOf('-');
        var core = dash >= 0 ? value[..dash] : value;
        var prerelease = dash >= 0 ? value[(dash + 1)..].Split('.') : [];
        var parts = core.Split('.');
        if (parts.Length != 3) return false;
        var numbers = new int[3];
        for (var i = 0; i < 3; i++)
            if (parts[i].Length == 0 || !parts[i].All(char.IsAsciiDigit) || !int.TryParse(parts[i], out numbers[i]))
                return false;
        if (prerelease.Any(part => part.Length == 0 || !part.All(c => char.IsAsciiLetterOrDigit(c) || c == '-')))
            return false;
        version = new ReleaseVersion(numbers[0], numbers[1], numbers[2], prerelease);
        return true;
    }

    public int CompareTo(ReleaseVersion? other)
    {
        if (other is null) return 1;
        var core = (Major, Minor, Patch).CompareTo((other.Major, other.Minor, other.Patch));
        if (core != 0) return core;
        // A release ranks above its own previews.
        if (Prerelease.Count == 0 || other.Prerelease.Count == 0)
            return Prerelease.Count == other.Prerelease.Count ? 0 : Prerelease.Count == 0 ? 1 : -1;
        for (var i = 0; i < Math.Min(Prerelease.Count, other.Prerelease.Count); i++)
        {
            var left = Prerelease[i];
            var right = other.Prerelease[i];
            var leftNumeric = left.All(char.IsAsciiDigit);
            var rightNumeric = right.All(char.IsAsciiDigit);
            int order;
            if (leftNumeric && rightNumeric)
                order = left.Length != right.Length ? left.Length.CompareTo(right.Length) : string.CompareOrdinal(left, right);
            else if (leftNumeric != rightNumeric)
                order = leftNumeric ? -1 : 1;
            else
                order = string.CompareOrdinal(left, right);
            if (order != 0) return Math.Sign(order);
        }
        return Prerelease.Count.CompareTo(other.Prerelease.Count);
    }

    public override string ToString() =>
        $"{Major}.{Minor}.{Patch}" + (Prerelease.Count > 0 ? "-" + string.Join('.', Prerelease) : "");
}

/// <summary>A newer launcher release for this platform.</summary>
public sealed record AvailableUpdate(
    string Version, string Tag, string ReleaseUrl, string AssetName, string AssetUrl, long Size, string Sha256);

/// <summary>Finds, downloads and installs a newer launcher release from the
/// project's GitHub releases (FB-10.7). The launcher and its source payload
/// are replaced beside the running launcher; the install root (source, game
/// files, build, saves and settings) is not touched here. The new launcher
/// unpacks its payload into the same source folder on its first start.</summary>
public static class LauncherUpdate
{
    public const string WindowsAsset = "PinyonShift-Launcher.zip";
    public const string LinuxAsset = "PinyonShift-Launcher-linux-x86_64.tar.gz";
    public const string MacAsset = "PinyonShift-Launcher-macos-arm64.zip";
    public const string PayloadName = "pinyon-shift-source.zip";
    public const string StagingFolder = ".pinyon-update";
    public const string LeftoverSuffix = ".pinyon-old";
    /// <summary>Passed to the new launcher after an update, with the old version.</summary>
    public const string UpdatedArgument = "--updated-from";

    private static bool IsMac => RuntimeInformation.IsOSPlatform(OSPlatform.OSX);
    private static bool IsLinux => RuntimeInformation.IsOSPlatform(OSPlatform.Linux);
    private static string LauncherFile => OperatingSystem.IsWindows() ? "PinyonShiftLauncher.exe" : "PinyonShiftLauncher";

    public static string AssetName => OperatingSystem.IsWindows() ? WindowsAsset : IsMac ? MacAsset : LinuxAsset;

    /// <summary>False when PINYON_SHIFT_UPDATE_CHECK is 0, false or off.</summary>
    public static bool CheckEnabled =>
        Environment.GetEnvironmentVariable("PINYON_SHIFT_UPDATE_CHECK")?.Trim().ToLowerInvariant()
            is not ("0" or "false" or "off" or "no");

    /// <summary>The installed release (version, channel and repository) from
    /// the source payload's config/release.json.</summary>
    public static (string Version, string Channel, string Repository)? ReadRelease(string releaseJson)
    {
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(releaseJson));
            var root = document.RootElement;
            var version = root.GetProperty("version").GetString();
            var channel = root.TryGetProperty("channel", out var c) ? c.GetString() : "stable";
            var repository = root.TryGetProperty("repository", out var r) ? r.GetString() : null;
            if (string.IsNullOrWhiteSpace(version) || string.IsNullOrWhiteSpace(repository)) return null;
            return (version, channel ?? "stable", repository);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException
                                       or KeyNotFoundException or InvalidOperationException)
        {
            return null;
        }
    }

    /// <summary>The GitHub API list of releases for a https://github.com/owner/repo
    /// URL. PINYON_SHIFT_UPDATE_FEED replaces it (a URL serving the same JSON),
    /// for testing.</summary>
    public static Uri ReleasesFeed(string repository)
    {
        var feed = Environment.GetEnvironmentVariable("PINYON_SHIFT_UPDATE_FEED");
        if (!string.IsNullOrWhiteSpace(feed)) return new Uri(feed.Trim());
        var uri = new Uri(repository.Trim().TrimEnd('/'));
        if (uri.Host != "github.com")
            throw new InvalidDataException($"Updates come from GitHub; release.json names {repository}.");
        var path = uri.AbsolutePath.Trim('/');
        if (path.EndsWith(".git", StringComparison.Ordinal)) path = path[..^4];
        if (path.Split('/').Length != 2)
            throw new InvalidDataException($"release.json names no GitHub repository: {repository}.");
        return new Uri($"https://api.github.com/repos/{path}/releases?per_page=30");
    }

    /// <summary>The newest release newer than <paramref name="current"/> that
    /// has this platform's asset with a SHA-256 digest. The stable channel
    /// skips prereleases; the preview channel takes both.</summary>
    public static AvailableUpdate? Select(JsonElement releases, string current, string channel, string assetName)
    {
        if (!ReleaseVersion.TryParse(current, out var installed) || releases.ValueKind != JsonValueKind.Array)
            return null;
        var preview = string.Equals(channel, "preview", StringComparison.OrdinalIgnoreCase);
        AvailableUpdate? best = null;
        ReleaseVersion? bestVersion = null;
        foreach (var release in releases.EnumerateArray())
        {
            if (Bool(release, "draft") || (!preview && Bool(release, "prerelease"))) continue;
            var tag = Text(release, "tag_name");
            if (!ReleaseVersion.TryParse(tag, out var version) || version.CompareTo(installed) <= 0) continue;
            if (!preview && version.Prerelease.Count > 0) continue;
            if (bestVersion is not null && version.CompareTo(bestVersion) <= 0) continue;
            if (!release.TryGetProperty("assets", out var assets) || assets.ValueKind != JsonValueKind.Array) continue;
            foreach (var asset in assets.EnumerateArray())
            {
                if (Text(asset, "name") != assetName) continue;
                var digest = Text(asset, "digest") ?? "";
                var url = Text(asset, "browser_download_url");
                if (!digest.StartsWith("sha256:", StringComparison.Ordinal) || digest.Length != 71
                    || !digest[7..].All(char.IsAsciiHexDigit) || !IsAllowedDownload(url))
                    continue;
                best = new AvailableUpdate(version.ToString(), tag!, Text(release, "html_url") ?? "",
                    assetName, url!, asset.TryGetProperty("size", out var size) && size.TryGetInt64(out var bytes) ? bytes : 0,
                    digest[7..].ToLowerInvariant());
                bestVersion = version;
                break;
            }
        }
        return best;

        static bool Bool(JsonElement element, string name) =>
            element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;
        static string? Text(JsonElement element, string name) =>
            element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
    }

    // HTTPS, or plain HTTP to this computer for a test feed.
    private static bool IsAllowedDownload(string? url) =>
        Uri.TryCreate(url, UriKind.Absolute, out var uri)
        && (uri.Scheme == Uri.UriSchemeHttps || (uri.Scheme == Uri.UriSchemeHttp && uri.IsLoopback));

    public static HttpClient CreateClient(string currentVersion)
    {
        var client = new HttpClient { Timeout = Timeout.InfiniteTimeSpan };
        client.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("PinyonShiftLauncher",
            ReleaseVersion.TryParse(currentVersion, out var version) ? version.ToString() : "0"));
        return client;
    }

    /// <summary>One request to the releases feed; null when up to date.</summary>
    public static async Task<AvailableUpdate?> CheckAsync(HttpClient client, string releaseJson, CancellationToken cancellation)
    {
        if (ReadRelease(releaseJson) is not { } release) return null;
        using var request = new HttpRequestMessage(HttpMethod.Get, ReleasesFeed(release.Repository));
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.github+json"));
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        timeout.CancelAfter(TimeSpan.FromSeconds(20));
        using var response = await client.SendAsync(request, timeout.Token);
        response.EnsureSuccessStatusCode();
        await using var stream = await response.Content.ReadAsStreamAsync(timeout.Token);
        using var document = await JsonDocument.ParseAsync(stream, cancellationToken: timeout.Token);
        return Select(document.RootElement, release.Version, release.Channel, AssetName);
    }

    /// <summary>Where the running launcher lives: its folder on Windows and
    /// Linux, the .app bundle on macOS.</summary>
    public static string InstalledLauncher()
    {
        var process = Environment.ProcessPath ?? Path.Combine(AppContext.BaseDirectory, LauncherFile);
        var folder = Path.GetDirectoryName(Path.GetFullPath(process))!;
        if (IsMac)
        {
            var bundle = Path.GetFullPath(Path.Combine(folder, "..", ".."));
            if (bundle.EndsWith(".app", StringComparison.OrdinalIgnoreCase)) return bundle;
        }
        return folder;
    }

    /// <summary>The folder that receives the download and the unpacked release:
    /// beside the launcher, so the final moves stay on one volume.</summary>
    public static string StagingRoot(string installedLauncher) =>
        Path.Combine(LauncherFolder(installedLauncher), StagingFolder);

    // The folder holding the launcher's files, or the bundle on macOS.
    private static string LauncherFolder(string installedLauncher) =>
        installedLauncher.EndsWith(".app", StringComparison.OrdinalIgnoreCase)
            ? Path.GetDirectoryName(installedLauncher)! : installedLauncher;

    /// <summary>Throws when the launcher's folder cannot be written, before
    /// anything is downloaded.</summary>
    public static void EnsureWritable(string installedLauncher)
    {
        var staging = StagingRoot(installedLauncher);
        Directory.CreateDirectory(staging);
        var probe = Path.Combine(staging, ".write-test");
        File.WriteAllText(probe, "");
        File.Delete(probe);
    }

    /// <summary>Downloads the release asset and checks its SHA-256 against the
    /// digest GitHub published; a mismatch deletes the file and throws.</summary>
    public static async Task<string> DownloadAsync(HttpClient client, AvailableUpdate update, string stagingRoot,
        IProgress<double>? progress, CancellationToken cancellation)
    {
        if (Directory.Exists(stagingRoot)) Directory.Delete(stagingRoot, recursive: true);
        Directory.CreateDirectory(stagingRoot);
        var file = Path.Combine(stagingRoot, update.AssetName);
        using (var response = await client.GetAsync(update.AssetUrl, HttpCompletionOption.ResponseHeadersRead, cancellation))
        {
            response.EnsureSuccessStatusCode();
            var total = response.Content.Headers.ContentLength ?? update.Size;
            await using var input = await response.Content.ReadAsStreamAsync(cancellation);
            await using var output = File.Create(file);
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            var buffer = new byte[1 << 16];
            long received = 0;
            int read;
            while ((read = await input.ReadAsync(buffer, cancellation)) > 0)
            {
                await output.WriteAsync(buffer.AsMemory(0, read), cancellation);
                hash.AppendData(buffer, 0, read);
                received += read;
                if (total > 0) progress?.Report(Math.Min(1.0, (double)received / total));
            }
            var actual = Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
            if (actual != update.Sha256)
            {
                output.Close();
                File.Delete(file);
                throw new InvalidDataException(
                    $"The download does not match the release's SHA-256 ({actual} instead of {update.Sha256}). Nothing was changed.");
            }
        }
        return file;
    }

    /// <summary>Unpacks the downloaded release into the staging folder and
    /// returns what replaces the installed launcher: its files (Windows,
    /// Linux) or the .app bundle (macOS).</summary>
    public static async Task<string> UnpackAsync(string download, string stagingRoot, CancellationToken cancellation)
    {
        var unpacked = Path.Combine(stagingRoot, "release");
        if (Directory.Exists(unpacked)) Directory.Delete(unpacked, recursive: true);
        Directory.CreateDirectory(unpacked);
        if (download.EndsWith(".tar.gz", StringComparison.OrdinalIgnoreCase))
        {
            await using var file = File.OpenRead(download);
            await using var gzip = new GZipStream(file, CompressionMode.Decompress);
            await TarFile.ExtractToDirectoryAsync(gzip, unpacked, overwriteFiles: false, cancellation);
        }
        else if (IsMac)
        {
            // ditto keeps the bundle's signature and modes, as it made them.
            using var ditto = Process.Start(new ProcessStartInfo("/usr/bin/ditto", ["-x", "-k", download, unpacked])
                { UseShellExecute = false }) ?? throw new InvalidOperationException("ditto did not start.");
            await ditto.WaitForExitAsync(cancellation);
            if (ditto.ExitCode != 0) throw new InvalidDataException("The downloaded release could not be unpacked.");
        }
        else
        {
            await Task.Run(() => ZipFile.ExtractToDirectory(download, unpacked), cancellation);
        }

        if (IsMac)
        {
            var bundle = Directory.GetDirectories(unpacked, "*.app").SingleOrDefault()
                ?? throw new InvalidDataException("The downloaded release has no app.");
            Require(Path.Combine(bundle, "Contents", "MacOS", LauncherFile));
            Require(Path.Combine(bundle, "Contents", "Resources", PayloadName));
            return bundle;
        }
        // The Linux archive holds a PinyonShift folder; the Windows one is flat.
        var root = IsLinux && Directory.Exists(Path.Combine(unpacked, "PinyonShift"))
            ? Path.Combine(unpacked, "PinyonShift") : unpacked;
        Require(Path.Combine(root, LauncherFile));
        Require(Path.Combine(root, PayloadName));
        return root;

        static void Require(string path)
        {
            if (!File.Exists(path))
                throw new InvalidDataException($"The downloaded release is missing {Path.GetFileName(path)}.");
        }
    }

    /// <summary>What moves where: each top-level file of the release beside the
    /// launcher, or the new bundle in place of the old one.</summary>
    public static IReadOnlyList<(string Source, string Target)> Plan(string unpacked, string installedLauncher) =>
        unpacked.EndsWith(".app", StringComparison.OrdinalIgnoreCase)
            ? [(unpacked, installedLauncher)]
            : Directory.GetFiles(unpacked).Order(StringComparer.Ordinal)
                .Select(file => (file, Path.Combine(installedLauncher, Path.GetFileName(file)))).ToList();

    /// <summary>Moves each source into place. An existing target, the running
    /// launcher included, is renamed to *.pinyon-old first (a running program
    /// can be renamed but not overwritten). Any failure puts every target back.</summary>
    public static void Swap(IReadOnlyList<(string Source, string Target)> moves)
    {
        var done = new List<(string Source, string Target, string? Old)>();
        try
        {
            foreach (var (source, target) in moves)
            {
                var old = target + LeftoverSuffix;
                DeletePath(old);
                string? moved = null;
                if (File.Exists(target) || Directory.Exists(target))
                {
                    MovePath(target, old);
                    moved = old;
                }
                done.Add((source, target, moved));
                MovePath(source, target);
            }
        }
        catch
        {
            for (var i = done.Count - 1; i >= 0; i--)
            {
                var (source, target, old) = done[i];
                try
                {
                    if (File.Exists(target) || Directory.Exists(target))
                        if (!File.Exists(source) && !Directory.Exists(source)) MovePath(target, source);
                    if (old is not null) MovePath(old, target);
                }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
            throw;
        }
    }

    /// <summary>Starts the new launcher with the given arguments, less any
    /// option in <paramref name="dropWithValue"/> and the value after it.</summary>
    public static void Restart(string installedLauncher, IReadOnlyList<string> arguments, string fromVersion,
        params string[] dropWithValue)
    {
        var kept = new List<string>();
        for (var i = 0; i < arguments.Count; i++)
        {
            if (arguments[i] == UpdatedArgument || dropWithValue.Contains(arguments[i])) i++;
            else kept.Add(arguments[i]);
        }
        var all = kept.Append(UpdatedArgument).Append(fromVersion);
        ProcessStartInfo start;
        if (IsMac && installedLauncher.EndsWith(".app", StringComparison.OrdinalIgnoreCase))
        {
            start = new ProcessStartInfo("/usr/bin/open") { UseShellExecute = false };
            foreach (var argument in new[] { "-n", installedLauncher, "--args" }.Concat(all)) start.ArgumentList.Add(argument);
        }
        else
        {
            start = new ProcessStartInfo(Path.Combine(installedLauncher, LauncherFile))
                { UseShellExecute = false, WorkingDirectory = installedLauncher };
            foreach (var argument in all) start.ArgumentList.Add(argument);
        }
        Process.Start(start);
    }

    /// <summary>Removes what an update left behind: the *.pinyon-old files of
    /// the previous launcher and the staging folder. The previous launcher may
    /// still be closing, so this retries for a few seconds.</summary>
    public static async Task CleanUpAsync(string installedLauncher)
    {
        var folder = LauncherFolder(installedLauncher);
        for (var attempt = 0; attempt < 10; attempt++)
        {
            var remaining = false;
            try
            {
                foreach (var path in Directory.EnumerateFileSystemEntries(folder, "*" + LeftoverSuffix)
                             .Append(Path.Combine(folder, StagingFolder)).ToList())
                {
                    try { DeletePath(path); }
                    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { remaining = true; }
                }
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return; }
            if (!remaining) return;
            await Task.Delay(1000);
        }
    }

    private static void MovePath(string source, string target)
    {
        if (Directory.Exists(source)) Directory.Move(source, target);
        else File.Move(source, target);
    }

    private static void DeletePath(string path)
    {
        if (Directory.Exists(path)) Directory.Delete(path, recursive: true);
        else if (File.Exists(path)) File.Delete(path);
    }
}

/// <summary>The list of files the installed source payload put in the source
/// folder (.pinyon-source-files). Extracting a new payload overwrites files
/// but never removes any, so files a release dropped are removed by this
/// list. Only files the previous payload listed are touched: .local (game
/// files, saves, settings), the build and anything else stay.</summary>
public static class PayloadManifest
{
    public const string FileName = ".pinyon-source-files";

    public static IReadOnlyList<string> Entries(ZipArchive archive) =>
        archive.Entries.Where(entry => !string.IsNullOrEmpty(entry.Name))
            .Select(entry => entry.FullName.Replace('\\', '/')).Order(StringComparer.Ordinal).ToList();

    /// <summary>Deletes files the previous payload listed that the new one
    /// does not; returns their relative paths.</summary>
    public static IReadOnlyList<string> RemoveStale(string destination, IReadOnlyCollection<string> entries)
    {
        var manifest = Path.Combine(destination, FileName);
        if (!File.Exists(manifest)) return [];
        var keep = new HashSet<string>(entries, StringComparer.OrdinalIgnoreCase);
        var root = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var removed = new List<string>();
        foreach (var line in File.ReadAllLines(manifest))
        {
            var relative = line.Trim().Replace('\\', '/');
            if (relative.Length == 0 || keep.Contains(relative)) continue;
            var first = relative.Split('/')[0];
            if (first is ".local" or "out" or ".." || relative.StartsWith('/')) continue;
            var path = Path.GetFullPath(Path.Combine(destination, relative));
            if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !File.Exists(path)) continue;
            File.Delete(path);
            removed.Add(relative);
        }
        return removed;
    }

    public static void Write(string destination, IReadOnlyList<string> entries) =>
        File.WriteAllText(Path.Combine(destination, FileName), string.Join('\n', entries) + "\n");
}

/// <summary>Unpacks the source payload over an earlier release (#802). The
/// payload's entries all carry one fixed timestamp (the ZIP is
/// deterministic), so a plain extraction stamped every source file with that
/// old date. The build tree left by the previous release is newer than that,
/// so Ninja saw nothing to rebuild and the update kept running the old
/// executable. Files whose bytes changed are written with the current time;
/// identical files are left alone, which keeps their build outputs valid.</summary>
public static class PayloadExtractor
{
    public static int Extract(string payload, string destination)
    {
        var root = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var written = 0;
        using var archive = ZipFile.OpenRead(payload);
        foreach (var entry in archive.Entries)
        {
            var path = Path.GetFullPath(Path.Combine(root, entry.FullName));
            if (!path.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"The payload entry {entry.FullName} points outside the source folder.");
            if (string.IsNullOrEmpty(entry.Name))
            {
                Directory.CreateDirectory(path);
                continue;
            }
            if (SameContent(entry, path)) continue;
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            entry.ExtractToFile(path, overwrite: true);
            File.SetLastWriteTimeUtc(path, DateTime.UtcNow);
            written++;
        }
        return written;
    }

    private static bool SameContent(ZipArchiveEntry entry, string path)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length != entry.Length) return false;
        using var existing = info.OpenRead();
        using var packed = entry.Open();
        var left = new byte[81920];
        var right = new byte[81920];
        while (true)
        {
            var read = existing.Read(left, 0, left.Length);
            var filled = 0;
            while (filled < read)
            {
                var got = packed.Read(right, filled, read - filled);
                if (got == 0) return false;
                filled += got;
            }
            if (read == 0) return true;
            if (!left.AsSpan(0, read).SequenceEqual(right.AsSpan(0, read))) return false;
        }
    }
}
