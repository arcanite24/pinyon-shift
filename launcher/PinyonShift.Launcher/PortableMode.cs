using System.IO;

namespace PinyonShift.Launcher;

// A portable install keeps everything the launcher and the game write (release source,
// build tools, the build, logs, crash reports, saves, settings, photos, backups and
// shader caches) in a "data" folder beside the launcher instead of
// %LOCALAPPDATA%\PinyonShift. It is chosen by a portable.txt beside the launcher, or for
// one run by starting the launcher with --portable. Every location is derived from the
// launcher's own folder at each start and nothing records it, so the whole folder can
// move to another drive or PC.
internal static class PortableMode
{
    public const string MarkerFileName = "portable.txt";
    public const string CommandLineSwitch = "--portable";
    public const string DataFolderName = "data";

    // The deepest file setup creates lies about 185 characters below the data folder
    // (source\<version>\.local\rexglue\thirdparty\vulkan-loader\tests\...), and Git, CMake
    // and the compilers stop at Windows' 260-character path limit. The default
    // %LOCALAPPDATA%\PinyonShift stays well inside this budget.
    public const int MaximumDataRootLength = 70;

    // Overrides that would send writes outside the portable folder.
    private static readonly string[] LocationOverrides =
        ["PINYON_SHIFT_INSTALL_ROOT", "PINYON_SHIFT_STATE_ROOT", "PINYON_SHIFT_GAME_ROOT"];

    public static bool IsRequested(string launcherDirectory, IEnumerable<string> arguments) =>
        File.Exists(Path.Combine(launcherDirectory, MarkerFileName)) ||
        arguments.Any(argument => string.Equals(argument, CommandLineSwitch, StringComparison.OrdinalIgnoreCase));

    public static string DataRoot(string launcherDirectory) =>
        Path.Combine(Path.TrimEndingDirectorySeparator(Path.GetFullPath(launcherDirectory)), DataFolderName);

    // Creates the data folder and proves a file can be written there, so an install
    // extracted into Program Files or onto read-only media fails now with a clear cause
    // instead of partway through a build.
    public static void EnsureWritable(string dataRoot)
    {
        var probe = Path.Combine(dataRoot, $".write-test-{Guid.NewGuid():N}");
        try
        {
            Directory.CreateDirectory(dataRoot);
            File.WriteAllText(probe, "portable");
            File.Delete(probe);
        }
        catch (Exception ex) when (ex is UnauthorizedAccessException or IOException or NotSupportedException
                                       or System.Security.SecurityException)
        {
            throw new PortableFolderException(
                $"Pinyon Shift cannot write to {dataRoot} ({ex.Message.TrimEnd('.')}). A portable install keeps " +
                "its build, tools and saves beside the launcher, so that folder must be writable. Move the " +
                @"whole launcher folder to one you own, such as D:\Games\PinyonShift (not Program Files), or " +
                $@"delete {MarkerFileName} to install under %LOCALAPPDATA%\PinyonShift instead.", ex);
        }
    }

    // Null when the data folder is short enough to build in. A chosen install
    // folder holds the same tree, so the same limit applies to it (#393).
    public static string? PathLengthProblem(string dataRoot, string kind = "portable") =>
        dataRoot.Length <= MaximumDataRootLength
            ? null
            : $"The {kind} folder {dataRoot} is {dataRoot.Length} characters long. The build creates files " +
              $"about 185 characters below it, past the 260-character limit of the build tools, so keep it " +
              $@"to {MaximumDataRootLength} characters or fewer: " + (kind == "portable"
                  ? @"move the launcher folder higher, such as D:\PinyonShift."
                  : @"choose a shorter install folder, such as D:\PinyonShift.");

    // Points the temporary folder of the launcher and every tool it starts (setup, the
    // compilers, crash reports) and PowerShell's module cache into the data folder, and
    // drops location overrides inherited from the environment. Only this process and its
    // children see the change. Returns what it ignored.
    public static IReadOnlyList<string> ApplyToEnvironment(string dataRoot)
    {
        var temporary = Path.Combine(dataRoot, "temp");
        Directory.CreateDirectory(temporary);
        Environment.SetEnvironmentVariable("TEMP", temporary);
        Environment.SetEnvironmentVariable("TMP", temporary);
        Environment.SetEnvironmentVariable("PSModuleAnalysisCachePath",
            Path.Combine(temporary, "powershell", "ModuleAnalysisCache"));
        // The Visual Studio developer prompt otherwise records telemetry in the user profile.
        Environment.SetEnvironmentVariable("VSCMD_SKIP_SENDTELEMETRY", "1");
        var ignored = new List<string>();
        foreach (var name in LocationOverrides)
        {
            if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(name))) continue;
            ignored.Add(name);
            Environment.SetEnvironmentVariable(name, null);
        }
        return ignored;
    }
}

internal sealed class PortableFolderException(string message, Exception? inner = null) : Exception(message, inner);
