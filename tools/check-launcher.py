"""Exercise the real WPF launcher without launching a game or touching user saves.

Covers folder selection, portable installs (portable.txt), preservation of existing
files, graphics preparation, progress and layout. Every file it writes is in a
temporary project directory; it never reads or writes %LOCALAPPDATA%\\PinyonShift.

Run on Windows with .NET 8+: python tools/check-launcher.py [screenshot-directory]
"""
import pathlib
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape


ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = r'''
using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using PinyonShift.Launcher;

class Check {
    static void Require(bool value, string message) {
        if (!value) throw new Exception(message);
    }
    [STAThread] static void Main(string[] args) {
        var app = new App();
        app.InitializeComponent();
        var window = new MainWindow(); // Never show: Loaded would start a real installation.
        SynchronizationContext.SetSynchronizationContext(null);
        var flags = BindingFlags.Instance | BindingFlags.NonPublic;
        var resolver = typeof(MainWindow).GetMethod("ResolveRepositoryRootAsync", flags)!;
        string Resolve(string selected) => ((Task<string>)resolver.Invoke(window, [selected])!).GetAwaiter().GetResult();
        bool CanChoose() => (bool)typeof(MainWindow).GetField("_canChooseInstallRoot", flags)!.GetValue(window)!;
        var root = AppContext.BaseDirectory;
        using (var zip = ZipFile.Open(Path.Combine(root, "pinyon-shift-source.zip"), ZipArchiveMode.Create)) {
            foreach (var name in new[] { "config/supported-dumps.json", "tools/setup-preview.ps1", "CMakeLists.txt",
                "src/main.cpp", "src/config/host_config.cpp", "src/ui/settings_menu.cpp", "src/save/profile_body.cpp" }) {
                using var writer = new StreamWriter(zip.CreateEntry(name).Open());
                writer.Write("test payload");
            }
        }
        Environment.SetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT", null);
        var selected = Path.Combine(root, "chosen folder with spaces");
        var installed = Resolve(selected);
        Require(installed.StartsWith(selected + Path.DirectorySeparatorChar), "Chosen folder ignored");
        Require(CanChoose(), "Packaged chooser disabled");
        var sentinel = Path.Combine(installed, "user-save-sentinel");
        File.WriteAllText(sentinel, "preserve");
        Require(Resolve(selected) == installed && File.ReadAllText(sentinel) == "preserve", "Existing files changed");
        var preservedState = Path.Combine(installed, ".local", "preview");
        Directory.CreateDirectory(Path.Combine(preservedState, "user", "ForzaProfile"));
        Directory.CreateDirectory(Path.Combine(preservedState, "config"));
        var save = Path.Combine(preservedState, "user", "ForzaProfile", "ForzaProfile");
        var config = Path.Combine(preservedState, "config", "settings.toml");
        File.WriteAllBytes(save, new byte[] { 0, 255, 17, 42 });
        File.WriteAllText(config, "keep my settings");
        foreach (var damaged in new[] { "src/main.cpp", "src/config/host_config.cpp",
                "src/ui/settings_menu.cpp", "src/save/profile_body.cpp" }) {
            var file = Path.Combine(installed, damaged);
            File.Delete(file);
            Require(Resolve(selected) == installed && File.ReadAllText(file) == "test payload",
                $"Missing source not repaired: {damaged}");
            Require(Convert.ToHexString(File.ReadAllBytes(save)) == "00FF112A"
                && File.ReadAllText(config) == "keep my settings"
                && File.ReadAllText(sentinel) == "preserve", "Source repair changed user files");
        }
        File.WriteAllText(Path.Combine(installed, "src/main.cpp"), "truncated");
        Require(Resolve(selected) == installed
            && File.ReadAllText(Path.Combine(installed, "src/main.cpp")) == "test payload",
            "Truncated source accepted");
        var alternate = Path.Combine(root, "second installation");
        Require(Resolve(alternate).StartsWith(alternate), "Switch failed");
        Require(File.ReadAllText(sentinel) == "preserve", "Switch touched old installation");
        Environment.SetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT", selected);
        Require(Resolve(alternate) == installed && !CanChoose(), "Environment precedence changed");
        Environment.SetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT", null);
        try { Resolve(sentinel); throw new Exception("File accepted as installation root"); }
        catch (IOException) { }
        Require(CanChoose() && Resolve(selected) == installed, "Cannot recover after invalid folder");

        var button = (Button)window.FindName("ChooseInstallRootButton");
        var update = typeof(MainWindow).GetMethod("UpdatePrimaryButton", flags)!;
        update.Invoke(window, null);
        Require(button.IsEnabled, "Folder button unavailable");
        typeof(MainWindow).GetField("_busy", flags)!.SetValue(window, true);
        update.Invoke(window, null);
        Require(!button.IsEnabled, "Folder can change during build/play");
        typeof(MainWindow).GetField("_busy", flags)!.SetValue(window, false);
        update.Invoke(window, null);

        // An extracted source uses the same ownership gate as an ISO.
        var sourceFolder = Path.Combine(root, "owned extracted game");
        Directory.CreateDirectory(sourceFolder);
        var sourceField = typeof(MainWindow).GetField("_repositoryRoot", flags)!;
        var previousSource = sourceField.GetValue(window);
        sourceField.SetValue(window, installed);
        typeof(MainWindow).GetMethod("SelectDiscImage", flags)!.Invoke(window, [sourceFolder]);
        var ownership = (CheckBox)window.FindName("OwnershipCheckBox");
        ownership.IsChecked = false; update.Invoke(window, null);
        Require(!((Button)window.FindName("PrimaryButton")).IsEnabled, "Folder bypassed ownership gate");
        ownership.IsChecked = true; update.Invoke(window, null);
        Require(((Button)window.FindName("PrimaryButton")).IsEnabled, "Extracted folder cannot start setup");
        Require(((Button)window.FindName("BrowseFolderButton")).Content.ToString() == "Choose extracted folder",
            "Extracted folder picker missing");
        if (args.Length != 0) {
            Directory.CreateDirectory(args[0]);
            var setupContent = (FrameworkElement)window.Content;
            setupContent.Measure(new Size(920, 640));
            setupContent.Arrange(new Rect(new Size(920, 640)));
            setupContent.UpdateLayout();
            var bitmap = new RenderTargetBitmap(920, 640, 96, 96, PixelFormats.Pbgra32);
            bitmap.Render(setupContent);
            var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
            using var file = File.Create(Path.Combine(args[0], "launcher-extracted-source-920.png")); png.Save(file);
        }
        ownership.IsChecked = false;
        sourceField.SetValue(window, previousSource);
        ((TextBox)window.FindName("IsoPathTextBox")).Text = "";
        update.Invoke(window, null);

        // Portable installs: portable.txt beside the launcher keeps everything in its data folder.
        var portableType = typeof(MainWindow).Assembly.GetType("PinyonShift.Launcher.PortableMode")!;
        object Portable(string name, params object[] arguments) {
            try { return portableType.GetMethod(name)!.Invoke(null, arguments); }
            catch (TargetInvocationException ex) { throw ex.InnerException!; }
        }
        var marker = Path.Combine(root, "portable.txt");
        Require(!(bool)Portable("IsRequested", root, new string[0])!, "Portable without marker");
        Require((bool)Portable("IsRequested", root, new[] { "--PORTABLE" })!, "--portable ignored");
        File.WriteAllText(marker, "");
        Require((bool)Portable("IsRequested", root, new string[0])!, "portable.txt ignored");
        Environment.SetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT", selected);
        Environment.SetEnvironmentVariable("PINYON_SHIFT_STATE_ROOT", Path.Combine(root, "elsewhere"));
        var portableWindow = new MainWindow();
        var dataRoot = Path.Combine(Path.TrimEndingDirectorySeparator(root), "data");
        Require(((System.Windows.Documents.Run)portableWindow.FindName("BuildLocationPrefixRun")).Text == "Portable: "
            && ((System.Windows.Documents.Run)portableWindow.FindName("BuildLocationRun")).Text == dataRoot,
            "Portable location not shown");
        var portableInstalled = ((Task<string>)resolver.Invoke(portableWindow, [selected])!).GetAwaiter().GetResult();
        Require(portableInstalled.StartsWith(Path.Combine(dataRoot, "source") + Path.DirectorySeparatorChar),
            $"Portable install outside its data folder: {portableInstalled}");
        Require(!(bool)typeof(MainWindow).GetField("_canChooseInstallRoot", flags)!.GetValue(portableWindow)!,
            "Portable install offers another folder");
        Require((string)typeof(MainWindow).GetField("_portableRoot", flags)!.GetValue(portableWindow) == dataRoot,
            "Portable root not recorded");
        Require(Environment.GetEnvironmentVariable("PINYON_SHIFT_INSTALL_ROOT") is null
            && Environment.GetEnvironmentVariable("PINYON_SHIFT_STATE_ROOT") is null, "Overrides leak out of portable");
        Require(Environment.GetEnvironmentVariable("TEMP") == Path.Combine(dataRoot, "temp")
            && Environment.GetEnvironmentVariable("TMP") == Path.Combine(dataRoot, "temp")
            && Directory.Exists(Path.Combine(dataRoot, "temp")), "Portable children write temporary files elsewhere");
        var stateResolver = typeof(MainWindow).GetMethod("ResolveStateRoot", BindingFlags.Static | BindingFlags.NonPublic)!;
        Require((string)stateResolver.Invoke(null, [portableInstalled])! ==
            Path.Combine(portableInstalled, ".local", "preview"), "Portable saves outside the data folder");
        Require(Directory.GetFiles(dataRoot, ".write-test-*").Length == 0, "Portable write probe left behind");
        Require(Portable("PathLengthProblem", @"D:\Games\PinyonShift\data") is null, "Short portable folder refused");
        Require(Portable("PathLengthProblem", @"D:\" + new string('x', 80) + @"\data") is string,
            "Long portable folder accepted");
        try { Portable("EnsureWritable", Path.Combine(sentinel, "data")); throw new Exception("Unwritable portable folder accepted"); }
        catch (Exception ex) when (ex.GetType().Name == "PortableFolderException") {
            Require(ex.Message.Contains("cannot write") && ex.Message.Contains("portable.txt"), "Unclear portable error");
        }
        File.Delete(marker);
        portableWindow.Close();

        var state = Path.Combine(root, "fresh-state");
        var executable = Path.Combine(root, "out/build/win-amd64-release/pinyon_shift.exe");
        Directory.CreateDirectory(Path.GetDirectoryName(executable)!);
        File.WriteAllText(executable, "test executable");
        typeof(MainWindow).GetField("_repositoryRoot", flags)!.SetValue(window, root);
        typeof(MainWindow).GetField("_stateRoot", flags)!.SetValue(window, state);
        typeof(MainWindow).GetMethod("DetectExistingBuild", flags)!.Invoke(window, null);
        Require(typeof(MainWindow).GetField("_gameExecutable", flags)!.GetValue(window) is null,
            "Executable without game files is considered ready");
        var game = Path.Combine(root, ".local/game/base/default.xex");
        Directory.CreateDirectory(Path.GetDirectoryName(game)!);
        File.WriteAllText(game, "test game");
        // An old Direct3D 12 selection migrates to Vulkan on start.
        Directory.CreateDirectory(Path.Combine(state, "config"));
        File.WriteAllText(Path.Combine(state, "config/pinyon_shift.toml"),
            "pinyon_shift_config_schema = 27\ngpu_backend = \"d3d12\"\n");
        typeof(MainWindow).GetMethod("DetectExistingBuild", flags)!.Invoke(window, null);
        var primary = (TextBlock)window.FindName("PrimaryButtonText");
        Require(primary.Text == "Play", "Legacy settings still require Direct3D 12 preparation");
        Require(window.FindName("GraphicsApiComboBox") is null, "Unsupported graphics API is selectable");
        var payloadMarker = Path.Combine(root, ".pinyon-source-sha256");
        File.WriteAllText(payloadMarker, "current payload");
        typeof(MainWindow).GetMethod("DetectExistingBuild", flags)!.Invoke(window, null);
        Require(typeof(MainWindow).GetField("_gameExecutable", flags)!.GetValue(window) is null,
            "Old build without matching release provenance is considered ready");
        File.WriteAllText(Path.Combine(root, ".local/build.json"), "{\"pinyon_shift_source_payload_sha256\":\"current payload\"}");
        typeof(MainWindow).GetMethod("DetectExistingBuild", flags)!.Invoke(window, null);
        Require(typeof(MainWindow).GetField("_gameExecutable", flags)!.GetValue(window) is not null,
            "Matching release build cannot play");
        // Exercise the real watcher/result path without starting a game.
        Directory.CreateDirectory(Path.Combine(root, "tools"));
        File.WriteAllText(Path.Combine(root, "tools/launch-preview.ps1"),
            "Write-Output '{\"result\":\"saved-content-unavailable\",\"exit_code\":1307}'\nexit 1\n");
        var savedConfig = File.ReadAllText(Path.Combine(state, "config/pinyon_shift.toml"));
        SynchronizationContext.SetSynchronizationContext(
            new System.Windows.Threading.DispatcherSynchronizationContext(window.Dispatcher));
        var launch = (Task)typeof(MainWindow).GetMethod("LaunchGameAsync", flags)!.Invoke(window, null)!;
        var frame = new System.Windows.Threading.DispatcherFrame();
        var timeout = new System.Windows.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(15) };
        timeout.Tick += (_, _) => { timeout.Stop(); frame.Continue = false; };
        launch.ContinueWith(_ => window.Dispatcher.BeginInvoke(new Action(() => frame.Continue = false)));
        timeout.Start();
        System.Windows.Threading.Dispatcher.PushFrame(frame);
        timeout.Stop();
        Require(launch.IsCompleted, "Missing-content watcher did not finish");
        launch.GetAwaiter().GetResult();
        SynchronizationContext.SetSynchronizationContext(null);
        Require(((TextBlock)window.FindName("HeadlineText")).Text == "Restore your saved car's DLC",
            "Missing saved content is reported as a crash");
        Require(typeof(MainWindow).GetField("_pendingReport", flags)!.GetValue(window) is null,
            "Missing content creates a pending crash report");
        Require(((Button)window.FindName("DlcButton")).IsEnabled &&
            ((Button)window.FindName("DlcButton")).Visibility == Visibility.Visible,
            "Missing content cannot be restored from the DLC panel");
        Require(File.ReadAllText(Path.Combine(state, "config/pinyon_shift.toml")) == savedConfig,
            "Recovery rewrites the saved configuration");
        var output = typeof(MainWindow).GetMethod("HandleOutput", flags)!;
        output.Invoke(window, ["::pinyon::{\"stage\":\"shaders\",\"percent\":20,\"message\":\"Preparing graphics\"}"]);
        Require(primary.Text == "Preparing…", "Shader progress is not shown");
        output.Invoke(window, ["::pinyon::{\"stage\":\"play\",\"percent\":100,\"message\":\"Starting game\"}"]);
        Require(primary.Text == "Game running", "Launch status does not follow preparation");

        // A crash report made before the folder moved is found in the new reports folder.
        var reports = Path.Combine(state, "reports");
        Directory.CreateDirectory(reports);
        var bundleName = "PinyonShift-abc123-20260930T000000Z.zip";
        File.WriteAllText(Path.Combine(reports, bundleName), "bundle");
        File.WriteAllText(Path.Combine(reports, "pending-report.json"), System.Text.Json.JsonSerializer.Serialize(new {
            crash_id = "abc123", bundle = @"Z:\moved\away\data\source\0.1.1\.local\preview\reports\" + bundleName,
            issue_url = "https://github.com/arcanite24/pinyon-shift/issues/new?title=x" }));
        typeof(MainWindow).GetMethod("DetectPendingReport", flags)!.Invoke(window, null);
        var pending = typeof(MainWindow).GetField("_pendingReport", flags)!.GetValue(window);
        Require(pending is not null && (string)pending.GetType().GetProperty("Bundle")!.GetValue(pending)! ==
            Path.Combine(Path.GetFullPath(reports), bundleName), "Moved crash report lost");
        typeof(MainWindow).GetField("_pendingReport", flags)!.SetValue(window, null);

        var label = (System.Windows.Documents.Run)window.FindName("BuildLocationRun");
        label.Text = @"D:\Games\A deliberately long installation directory\PinyonShift\source\0.1.0\.local\preview";
        ((FrameworkElement)window.FindName("LogPanel")).Visibility = Visibility.Visible;
        ((FrameworkElement)window.FindName("LogBox")).Visibility = Visibility.Visible;
        ((FrameworkElement)window.FindName("SetupPanel")).Visibility = Visibility.Visible;
        var headline = (FrameworkElement)window.FindName("HeadlineText");
        var log = (TextBox)window.FindName("LogTextBox");
        log.Text = "CMake Error: example failure\nThe complete diagnostic remains readable here.";
        var content = (FrameworkElement)window.Content;
        if (content is Panel contentPanel) contentPanel.Background = window.Background;
        else if (content is Border contentBorder && contentBorder.Background is null) contentBorder.Background = window.Background;
        foreach (var size in new[] { new Size(1080, 720), new Size(920, 640) }) {
            content.Measure(size);
            content.Arrange(new Rect(size));
            content.UpdateLayout();
            Require(log.ActualHeight > 0 && log.TranslatePoint(new Point(), content).Y >=
                headline.TranslatePoint(new Point(), content).Y + headline.ActualHeight, "Log overlaps heading");
            if (args.Length != 0) {
                Directory.CreateDirectory(args[0]);
                var bitmap = new RenderTargetBitmap((int)size.Width, (int)size.Height, 96, 96, PixelFormats.Pbgra32);
                bitmap.Render(content);
                var png = new PngBitmapEncoder();
                png.Frames.Add(BitmapFrame.Create(bitmap));
                using var file = File.Create(Path.Combine(args[0], $"launcher-{size.Width}.png"));
                png.Save(file);
            }
            Require(button.ActualWidth > 0 && button.ActualHeight >= 24,
                $"Folder control clipped: {button.ActualWidth} x {button.ActualHeight}");
        }
        // The fixed Vulkan label and remaining graphics choices fit the panel.
        typeof(MainWindow).GetMethod("SetComplete", flags)!.Invoke(window, null);
        typeof(MainWindow).GetMethod("UpdateSummary", flags)!.Invoke(window, null);
        var viewType = typeof(MainWindow).GetNestedType("View", BindingFlags.NonPublic)!;
        typeof(MainWindow).GetMethod("ShowPanel", flags)!.Invoke(window, [Enum.Parse(viewType, "Graphics")]);
        typeof(MainWindow).GetMethod("UpdateResolutionLine", flags)!.Invoke(window, null);
        foreach (var size in new[] { new Size(1080, 720), new Size(920, 640) }) {
            content.Measure(size); content.Arrange(new Rect(size)); content.UpdateLayout();
            foreach (var name in new[] { "ResolutionComboBox", "OutputScalingComboBox", "SaveGraphicsButton" }) {
                var control = (FrameworkElement)window.FindName(name);
                Require(control.ActualHeight >= 24 && control.TranslatePoint(new Point(), content).Y +
                    control.ActualHeight < size.Height, $"Graphics control clipped: {name}");
            }
            if (args.Length != 0) {
                var bitmap = new RenderTargetBitmap((int)size.Width, (int)size.Height, 96, 96, PixelFormats.Pbgra32);
                bitmap.Render(content);
                var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
                using var file = File.Create(Path.Combine(args[0], $"launcher-graphics-{size.Width}.png")); png.Save(file);
            }
        }
        // DLC rows remain usable with the full catalog, and damaged content
        // cannot offer an enable button. No real package or save is used.
        var dlc = new MainWindow.DlcResult();
        for (var index = 0; index < 21; index++) dlc.Packages.Add(new MainWindow.DlcPackage {
            PackageId = index.ToString(), DisplayName = index == 0 ? "Rally Expansion Pack" :
                "Season Pass: 2006 Lamborghini Miura Concept", Status = "gameplay_unverified", Enabled = index == 0
        });
        dlc.Packages[1].Status = "missing";
        Require(dlc.Packages[0].ToggleText == "Disable" && dlc.Packages[0].CanToggle &&
            !dlc.Packages[1].CanToggle, "DLC status does not control management");
        Require(dlc.Packages[0].ToggleAccessibleName == "Disable Rally Expansion Pack",
            "DLC toggle omits its package name for accessibility");
        dlc.Packages[0].PackageId = "6F6992766050D818245ADD408031E280FB5F4E634D";
        Require(dlc.Packages[0].StatusText.Contains("Assets not prepared"),
            "Unprepared Rally assets are not reported");
        dlc.Packages[0].RallyAssetsCached = true;
        Require(dlc.Packages[0].StatusText.Contains("Assets cached") &&
            dlc.Packages[0].StatusText.Contains("Gameplay unverified"),
            "Rally preparation is mistaken for gameplay qualification");
        foreach (var damaged in new[] { "missing", "metadata_invalid" }) {
            dlc.Packages[1].Status = damaged;
            dlc.Packages[1].Enabled = true;
            Require(dlc.Packages[1].CanToggle && dlc.Packages[1].ToggleText == "Disable",
                "Damaged enabled DLC cannot be disabled");
            dlc.Packages[1].Enabled = false;
            Require(!dlc.Packages[1].CanToggle, "Damaged disabled DLC offers enable");
        }
        typeof(MainWindow).GetMethod("ApplyDlcResult", flags)!.Invoke(window, [dlc]);
        typeof(MainWindow).GetMethod("ShowPanel", flags)!.Invoke(window, [Enum.Parse(viewType, "Dlc")]);
        update.Invoke(window, null);
        Require(!((Button)window.FindName("PrimaryButton")).IsEnabled && !button.IsEnabled,
            "Launch or relocation remains available during DLC management");
        Require(((FrameworkElement)window.FindName("DlcEmptyText")).Visibility == Visibility.Collapsed,
            "Empty DLC message remains over imported content");
        foreach (var size in new[] { new Size(1080, 720), new Size(940, 640) }) {
            content.Measure(size); content.Arrange(new Rect(size)); content.UpdateLayout();
            var controls = (FrameworkElement)window.FindName("DlcControls");
            Require(controls.ActualHeight >= 30 && controls.TranslatePoint(new Point(), content).Y +
                controls.ActualHeight < size.Height - 44, "DLC import controls clipped");
            if (args.Length != 0) {
                var bitmap = new RenderTargetBitmap((int)size.Width, (int)size.Height, 96, 96, PixelFormats.Pbgra32);
                bitmap.Render(content);
                var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
                using var file = File.Create(Path.Combine(args[0], $"launcher-dlc-{size.Width}.png")); png.Save(file);
            }
        }
        File.Delete(payloadMarker); // This next fixture represents a developer checkout.
        // Checkout detection takes precedence over packaged configuration.
        Directory.CreateDirectory(Path.Combine(root, "config"));
        Directory.CreateDirectory(Path.Combine(root, "tools"));
        File.WriteAllText(Path.Combine(root, "config/supported-dumps.json"), "{}");
        File.WriteAllText(Path.Combine(root, "tools/setup-preview.ps1"), "");
        Require(Resolve(selected) == installed && CanChoose(), "Partial checkout accepted");
        Directory.CreateDirectory(Path.Combine(root, "src"));
        File.WriteAllText(Path.Combine(root, "CMakeLists.txt"), "");
        File.WriteAllText(Path.Combine(root, "src/main.cpp"), "");
        Require(Path.TrimEndingDirectorySeparator(Resolve(selected)) == Path.TrimEndingDirectorySeparator(root)
            && !CanChoose(), "Checkout relocated");
        File.WriteAllText(Path.Combine(root, ".pinyon-source-sha256"), "managed source");
        Require(Resolve(selected) == installed && CanChoose(), "Managed source bypasses payload checks");
        using (var damagedZip = ZipFile.Open(Path.Combine(root, "pinyon-shift-source.zip"), ZipArchiveMode.Update))
            damagedZip.GetEntry("src/main.cpp")!.Delete();
        var brokenRoot = Path.Combine(root, "broken release");
        try { Resolve(brokenRoot); throw new Exception("Incomplete release ZIP accepted"); }
        catch (InvalidDataException) { }
        Require(!File.Exists(Path.Combine(brokenRoot, "source", "0.1.1", ".pinyon-source-sha256")),
            "Incomplete ZIP marked as installed");
        Console.WriteLine("Launcher folders, portable installs, preservation, graphics, DLC states, progress and layout passed.");
        window.Close();
    }
}
'''


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="pinyon-launcher-check-") as directory:
        project = pathlib.Path(directory)
        reference = escape(str(ROOT / "launcher/PinyonShift.Launcher/PinyonShift.Launcher.csproj"))
        (project / "Check.csproj").write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0-windows</TargetFramework>
    <UseWPF>true</UseWPF><RuntimeIdentifier>win-x64</RuntimeIdentifier>
    <SelfContained>true</SelfContained></PropertyGroup>
  <ItemGroup><ProjectReference Include="{reference}" /></ItemGroup>
</Project>''')
        (project / "Program.cs").write_text(CHECK)
        output = project / "bin"
        subprocess.run(["dotnet", "build", str(project), "-c", "Release", "-o", str(output)], check=True)
        subprocess.run([str(output / "Check.exe"), *[str(pathlib.Path(p).resolve()) for p in sys.argv[1:]]], check=True)
