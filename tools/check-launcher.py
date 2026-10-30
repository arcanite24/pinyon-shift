"""Exercise the real WPF launcher without launching a game or touching user saves.

Covers folder selection, portable installs (portable.txt), preservation of existing
files, graphics preparation, the Mods view, progress and layout. Every file it writes is in a
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
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using PinyonShift.Launcher;
using PinyonShift.Launcher.Mods;
using PinyonShift.Launcher.Updates;

class Check {
    static void Require(bool value, string message) {
        if (!value) throw new Exception(message);
    }
    // A CI runner's scanner can briefly hold a ZIP the check has just
    // written ("being used by another process"); the launcher's own reads
    // are closed by then.
    // ZipFile.Open asks for exclusive access, which fails while a scanner on
    // the CI runner reads the new ZIP; sharing it lets the scanner keep its
    // handle. Retry for up to about a minute in case one still blocks writes.
    static ZipArchive OpenZipForUpdate(string path) {
        for (var attempt = 1; ; attempt++) {
            try {
                var stream = new FileStream(path, FileMode.Open, FileAccess.ReadWrite,
                    FileShare.ReadWrite | FileShare.Delete);
                return new ZipArchive(stream, ZipArchiveMode.Update);
            }
            catch (IOException) when (attempt < 30) { System.Threading.Thread.Sleep(Math.Min(200 * attempt, 2000)); }
            catch (IOException error) {
                throw new IOException($"{error.Message} Held by: {FileHolders(path)}", error);
            }
        }
    }

    // Names the processes holding a file (Restart Manager), for lock failures in CI.
    [StructLayout(LayoutKind.Sequential)] struct RmUniqueProcess { public int Pid; public System.Runtime.InteropServices.ComTypes.FILETIME Start; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct RmProcessInfo {
        public RmUniqueProcess Process;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string AppName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string ServiceName;
        public int AppType; public int AppStatus; public int TSSessionId; [MarshalAs(UnmanagedType.Bool)] public bool Restartable;
    }
    [DllImport("rstrtmgr.dll", CharSet = CharSet.Unicode)] static extern int RmStartSession(out uint session, int flags, string key);
    [DllImport("rstrtmgr.dll")] static extern int RmEndSession(uint session);
    [DllImport("rstrtmgr.dll", CharSet = CharSet.Unicode)] static extern int RmRegisterResources(uint session, uint files, string[] names, uint apps, IntPtr processes, uint services, string[]? serviceNames);
    [DllImport("rstrtmgr.dll")] static extern int RmGetList(uint session, out uint needed, ref uint count, [In, Out] RmProcessInfo[]? info, out uint reasons);
    static string FileHolders(string path) {
        if (RmStartSession(out var session, 0, Guid.NewGuid().ToString()) != 0) return "unknown";
        try {
            if (RmRegisterResources(session, 1, [path], 0, IntPtr.Zero, 0, null) != 0) return "unknown";
            uint count = 0;
            RmGetList(session, out var needed, ref count, null, out _);
            var info = new RmProcessInfo[needed];
            count = needed;
            if (needed == 0 || RmGetList(session, out needed, ref count, info, out _) != 0) return needed == 0 ? "no process found" : "unknown";
            return string.Join(", ", info.Take((int)count).Select(p => $"{p.AppName} (pid {p.Process.Pid}{(p.Process.Pid == Environment.ProcessId ? ", this process" : "")})"));
        }
        finally { RmEndSession(session); }
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
        // The launcher expands 8.3 short names (C:\Users\RUNNER~1) in the
        // paths it resolves; compare against the same long form.
        var root = Path.GetFullPath(AppContext.BaseDirectory);
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
            var method = portableType.GetMethod(name)!;
            // Optional parameters left out take their defaults.
            var padded = arguments.Concat(Enumerable.Repeat(Type.Missing,
                method.GetParameters().Length - arguments.Length)).ToArray();
            try { return method.Invoke(null, BindingFlags.OptionalParamBinding, null, padded, null); }
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
        // FB-9.1: the Mods view, from the JSON tools/pinyon_mods.py prints. A long
        // description, an image and a mod the game would refuse fit both sizes.
        var modImage = Path.Combine(root, "mod preview.png");
        var preview = new RenderTargetBitmap(640, 360, 96, 96, PixelFormats.Pbgra32);
        var drawing = new DrawingVisual();
        using (var context = drawing.RenderOpen())
            context.DrawRectangle(new LinearGradientBrush(Colors.DarkGreen, Colors.Goldenrod, 20), null, new Rect(0, 0, 640, 360));
        preview.Render(drawing);
        using (var file = File.Create(modImage)) {
            var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(preview)); png.Save(file);
        }
        var modsJson = System.Text.Json.JsonSerializer.Serialize(new {
            result = "ok", build = "base disc", mods_root = Path.Combine(state, "mods"), missing = new[] { "gone_mod" },
            save = new { kind = "modded", profile = "user-modded" },
            mods = new object[] {
                new { name = "sharper_roads", title = "Sharper road textures", version = "2.1.0", author = "A modder",
                      description = string.Join("\n\n", Enumerable.Repeat("Replaces the road and kerb textures with four times larger copies made from your own disc, so the tarmac stays sharp at 4K. Paint lines, cracks and patches keep their places.", 3)),
                      url = "https://example.com/sharper-roads", images = new[] { modImage, modImage }, enabled = true,
                      shares_save = true, contents = new[] { "textures" }, builds = new[] { "base disc", "title update v4" },
                      options = new[] {
                          new { key = "detail", title = "Road detail", description = "How much sharper the roads get.",
                                value = "4", choices = new[] { new { value = "2", label = "2x" }, new { value = "4", label = "4x" } } },
                          new { key = "kerbs", title = "Kerbs", description = "",
                                value = "1", choices = new[] { new { value = "1", label = "As the game" }, new { value = "2", label = "Sharper" } } } },
                      problems = Array.Empty<string>() },
                new { name = "more_cars", title = "More cars", version = "1.0.0", author = "", description = "",
                      url = "", images = Array.Empty<string>(), enabled = true, contents = new[] { "database", "text" },
                      requires = new[] { "car_pack_base" }, problems = new[] { "needs car_pack_base, which is not installed" } },
                new { name = "custom_radio", title = "custom_radio", enabled = false, managed_by = "Radio",
                      contents = new[] { "archive members" }, problems = Array.Empty<string>() },
                new { name = "photo_mode_limits", title = "Photo mode limits", builtin = true, enabled = false,
                      shares_save = true, contents = new[] { "merged settings" }, problems = Array.Empty<string>() },
            } });
        var mods = ModsStatus.Parse("log line\n" + modsJson)!;
        Require(mods.Mods[0].StateText == "On" && mods.Mods[1].State == "problem" &&
            mods.Mods[1].StateText.StartsWith("On · won't load"), "Mod states are wrong");
        Require(!mods.Mods[2].CanRemove && !mods.Mods[3].CanRemove && mods.Mods[0].CanRemove,
            "Managed or built-in mods can be removed");
        // The note above the mods says only what needs saying: nothing on a plain visit,
        // missing mods always, and the save the next start plays when a change moved it.
        var ownSave = new ModsStatus { Mods = mods.Mods, Save = new ModSave { Kind = "own", Profile = "user", ModdedCopy = true } };
        Require(mods.Notice("") == "Switched on but not installed: gone_mod." && ownSave.Notice("") == "",
            "The mods' note shows without a reason");
        // The first mod that changes the save moves the game to a copy; switching the last one
        // off goes back to the player's own save, with the modded progress kept in the copy.
        var entering = mods.SaveChangeText(ownSave.Save);
        var leaving = ownSave.SaveChangeText(mods.Save);
        Require(entering.Contains("separate copy") && leaving.Contains("your own save") &&
            leaving.Contains("modded progress") && mods.SaveChangeText(mods.Save) == "",
            "Entering or leaving the modded copy is not explained");
        Require(mods.Mods[0].ToggleAccessibleName == "Switch off Sharper road textures",
            "Mod toggle omits its name for accessibility");
        // A switch shows at the click, before the tool answers.
        var switched = ModsStatus.Parse(modsJson)!;
        switched.Preview(switched.Mods[2], true);
        switched.Preview(switched.Mods[0], false);
        Require(switched.Mods[2].StateText == "On" && switched.Mods[0].StateText == "Off",
            "A switch does not show at the click");
        // A failure stands out from the quiet line a success leaves.
        typeof(MainWindow).GetMethod("ApplyMods", flags)!.Invoke(window, [mods, "sharper_roads", "roads.7z is a 7-Zip archive", true]);
        var modsStatus = (TextBlock)window.FindName("ModsStatusText");
        Require(modsStatus.Foreground == window.FindResource("AmberBrush") && modsStatus.Text == "Roads.7z is a 7-Zip archive.",
            "A mods failure looks like a success");
        // The tallest the view gets: the longest save note with a missing mod, under a switch.
        typeof(MainWindow).GetField("_modsSaveChange", flags)!.SetValue(window, entering);
        typeof(MainWindow).GetMethod("ApplyMods", flags)!.Invoke(window, [mods, "sharper_roads",
            "Sharper road textures is on from the next start.", false]);
        Require(modsStatus.Foreground == window.FindResource("MutedBrush"), "A mods success keeps the failure's colour");
        Require(((TextBlock)window.FindName("ModsSaveText")).Visibility == Visibility.Visible,
            "The mods' note is hidden while it has something to say");
        typeof(MainWindow).GetMethod("ShowPanel", flags)!.Invoke(window, [Enum.Parse(viewType, "Mods")]);
        update.Invoke(window, null);
        Require(!((Button)window.FindName("PrimaryButton")).IsEnabled, "Launch remains available during mod management");
        // A mod's options show as one list each, on its saved choice; a mod without options shows none.
        var optionList = (ItemsControl)window.FindName("ModOptions");
        Require(mods.Mods[0].Options[0].ValueLabel == "4x" && mods.Mods[1].Options.Count == 0 &&
            optionList.Visibility == Visibility.Visible && optionList.Items.Count == 2, "The mod's options are not shown");
        // The technical facts are behind Details: hidden at first, shown and hidden by the link.
        var facts = (TextBlock)window.FindName("ModFactsText");
        var factsButton = (Button)window.FindName("ModFactsButton");
        var factsClick = typeof(MainWindow).GetMethod("ModFacts_Click", flags)!;
        Require(facts.Visibility == Visibility.Collapsed && (string)factsButton.Content == "Details",
            "The mod's technical details show without being asked for");
        factsClick.Invoke(window, [factsButton, new RoutedEventArgs()]);
        Require(facts.Visibility == Visibility.Visible && facts.Text.StartsWith("Changes: textures") &&
            (string)factsButton.Content == "Hide details", "Details does not show the mod's technical details");
        factsClick.Invoke(window, [factsButton, new RoutedEventArgs()]);
        Require(facts.Visibility == Visibility.Collapsed, "Hide details leaves the details shown");
        Require(((Image)window.FindName("ModImage")).Source is not null, "The mod's image is not shown");
        foreach (var size in new[] { new Size(1080, 720), new Size(940, 640), new Size(1280, 1000) }) {
            content.Measure(size); content.Arrange(new Rect(size)); content.UpdateLayout();
            // Before the checks, so a failure leaves its picture.
            if (args.Length != 0) {
                var bitmap = new RenderTargetBitmap((int)size.Width, (int)size.Height, 96, 96, PixelFormats.Pbgra32);
                bitmap.Render(content);
                var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
                using var file = File.Create(Path.Combine(args[0], $"launcher-mods-{size.Width}.png")); png.Save(file);
            }
            // The list and details take the window's spare height, never less than their minimum.
            var browser = (FrameworkElement)window.FindName("ModsBrowser");
            var body = (FrameworkElement)window.FindName("BodyStack");
            var bodyScroll = (ScrollViewer)window.FindName("BodyScroll");
            Require(browser.ActualHeight >= 205 && (browser.ActualHeight < 207 ||
                Math.Abs(body.ActualHeight + body.Margin.Bottom - bodyScroll.ViewportHeight) < 2),
                $"The mods box does not fill the window at {size.Width} x {size.Height}");
            if (size.Height >= 1000) Require(browser.ActualHeight > 400, "The mods box stays small in a tall window");
            // The option's list shows its chosen label, not a type name.
            ComboBox FindList(DependencyObject parent)
            {
                for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
                    if (VisualTreeHelper.GetChild(parent, i) is var child && (child as ComboBox ?? FindList(child)) is { } found)
                        return found;
                return null;
            }
            Require(FindList(optionList) is { SelectionBoxItem: var shown } && shown?.ToString() == "4x",
                "The mod's option list does not show its choice");
            foreach (var name in new[] { "ModsControls", "ModControls", "ModsList" }) {
                var control = (FrameworkElement)window.FindName(name);
                Require(control.ActualHeight >= 30 && control.TranslatePoint(new Point(), content).Y +
                    control.ActualHeight < size.Height - 44, $"Mods control clipped: {name}");
            }
            var removeButton = (FrameworkElement)window.FindName("ModRemoveButton");
            Require(removeButton.TranslatePoint(new Point(removeButton.ActualWidth, 0), content).X <= size.Width,
                "Mod buttons run off the window");
        }
        ((ListBox)window.FindName("ModsList")).SelectedIndex = 1;
        Require(((TextBlock)window.FindName("ModsStatusText")).Text.Length > 0 &&
            ((FrameworkElement)window.FindName("ModImagePanel")).Visibility == Visibility.Collapsed,
            "A mod without images keeps the previous image");
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
        Require(Path.TrimEndingDirectorySeparator(Path.GetFullPath(Resolve(selected))) == Path.TrimEndingDirectorySeparator(root)
            && !CanChoose(), "Checkout relocated");
        File.WriteAllText(Path.Combine(root, ".pinyon-source-sha256"), "managed source");
        Require(Resolve(selected) == installed && CanChoose(), "Managed source bypasses payload checks");
        using (var damagedZip = OpenZipForUpdate(Path.Combine(root, "pinyon-shift-source.zip")))
            damagedZip.GetEntry("src/main.cpp")!.Delete();
        var brokenRoot = Path.Combine(root, "broken release");
        try { Resolve(brokenRoot); throw new Exception("Incomplete release ZIP accepted"); }
        catch (InvalidDataException) { }
        Require(!File.Exists(Path.Combine(brokenRoot, "source", "0.1.1", ".pinyon-source-sha256")),
            "Incomplete ZIP marked as installed");
        UpdateChecks(Path.Combine(root, "update checks"));
        Console.WriteLine("Launcher folders, portable installs, preservation, graphics, DLC states, mods, progress, layout and updates passed.");
        window.Close();
    }

    // FB-10.7: release selection, the file swap and stale source removal.
    static void UpdateChecks(string root) {
        string[] ordered = ["0.4.0", "0.4.1-preview.1", "0.4.1-preview.2", "0.4.1-preview.10", "0.4.1", "0.5.0", "1.0.0"];
        for (var i = 0; i + 1 < ordered.Length; i++) {
            Require(ReleaseVersion.TryParse(ordered[i], out var a) && ReleaseVersion.TryParse(ordered[i + 1], out var b)
                && a.CompareTo(b) < 0 && b.CompareTo(a) > 0, $"Version order {ordered[i]} < {ordered[i + 1]}");
        }
        Require(ReleaseVersion.TryParse("v0.4.0", out var tagged) && tagged.ToString() == "0.4.0", "Tag not parsed");
        Require(!ReleaseVersion.TryParse("0.4", out _) && !ReleaseVersion.TryParse("latest", out _), "Bad version parsed");
        var hex = new string('a', 64);
        string Asset(string url, string digest) =>
            $"{{\"name\":\"PinyonShift-Launcher.zip\",\"size\":5,\"digest\":\"{digest}\",\"browser_download_url\":\"{url}\"}}";
        string Release(string tag, bool pre, string asset, bool draft = false) =>
            $"{{\"tag_name\":\"{tag}\",\"prerelease\":{(pre ? "true" : "false")},\"draft\":{(draft ? "true" : "false")},\"html_url\":\"https://github.com/arcanite24/pinyon-shift/releases/tag/{tag}\",\"assets\":[{asset}]}}";
        var good = Asset("https://github.com/arcanite24/pinyon-shift/releases/download/x/PinyonShift-Launcher.zip", "sha256:" + hex);
        var json = "[" + string.Join(",",
            Release("v0.7.0", false, good, draft: true),
            Release("v0.6.0-preview.1", true, good),
            Release("v0.5.1", false, Asset("https://example.com/a.zip", "")),
            Release("v0.5.2", false, Asset("http://example.com/a.zip", "sha256:" + hex)),
            Release("v0.5.0", false, good),
            Release("v0.3.0", false, good)) + "]";
        using var feed = System.Text.Json.JsonDocument.Parse(json);
        var stable = LauncherUpdate.Select(feed.RootElement, "0.4.0", "stable", LauncherUpdate.WindowsAsset);
        Require(stable is { Version: "0.5.0", Sha256: var sha } && sha == hex, $"Stable picked {stable?.Version}");
        Require(LauncherUpdate.Select(feed.RootElement, "0.4.0", "preview", LauncherUpdate.WindowsAsset)?.Version
            == "0.6.0-preview.1", "Preview channel skipped the preview");
        Require(LauncherUpdate.Select(feed.RootElement, "0.5.0", "stable", LauncherUpdate.WindowsAsset) is null,
            "Offered an unverifiable or insecure release");
        Require(LauncherUpdate.Select(feed.RootElement, "0.4.0", "stable", LauncherUpdate.LinuxAsset) is null,
            "Offered another platform's asset");

        var launcher = Path.Combine(root, "launcher");
        var staged = Path.Combine(root, "staged");
        Directory.CreateDirectory(launcher);
        Directory.CreateDirectory(staged);
        File.WriteAllText(Path.Combine(launcher, "PinyonShiftLauncher.exe"), "old launcher");
        File.WriteAllText(Path.Combine(launcher, "pinyon-shift-source.zip"), "old payload");
        File.WriteAllText(Path.Combine(launcher, "portable.txt"), "");
        File.WriteAllText(Path.Combine(staged, "PinyonShiftLauncher.exe"), "new launcher");
        File.WriteAllText(Path.Combine(staged, "pinyon-shift-source.zip"), "new payload");
        var plan = LauncherUpdate.Plan(staged, launcher);
        var broken = plan.Append((Path.Combine(staged, "missing"), Path.Combine(launcher, "missing"))).ToList();
        try { LauncherUpdate.Swap(broken); throw new Exception("Swap with a missing file succeeded"); }
        catch (FileNotFoundException) { }
        Require(File.ReadAllText(Path.Combine(launcher, "PinyonShiftLauncher.exe")) == "old launcher"
            && File.ReadAllText(Path.Combine(launcher, "pinyon-shift-source.zip")) == "old payload"
            && File.ReadAllText(Path.Combine(staged, "PinyonShiftLauncher.exe")) == "new launcher",
            "A failed swap was not rolled back");
        LauncherUpdate.Swap(plan);
        Require(File.ReadAllText(Path.Combine(launcher, "PinyonShiftLauncher.exe")) == "new launcher"
            && File.ReadAllText(Path.Combine(launcher, "pinyon-shift-source.zip")) == "new payload"
            && File.ReadAllText(Path.Combine(launcher, "PinyonShiftLauncher.exe.pinyon-old")) == "old launcher"
            && File.Exists(Path.Combine(launcher, "portable.txt")), "Swap did not install the release");
        Directory.CreateDirectory(Path.Combine(launcher, LauncherUpdate.StagingFolder));
        LauncherUpdate.CleanUpAsync(launcher).GetAwaiter().GetResult();
        Require(Directory.GetFileSystemEntries(launcher).Select(Path.GetFileName).Order(StringComparer.Ordinal).SequenceEqual(
            ["PinyonShiftLauncher.exe", "pinyon-shift-source.zip", "portable.txt"]),
            "Update leftovers remain: " + string.Join(", ", Directory.GetFileSystemEntries(launcher)));

        var source = Path.Combine(root, "source");
        string[] listed = ["kept.txt", "dropped/old.ps1", ".local/preview/user/ForzaProfile/ForzaProfile", "out/build/x", "../outside.txt"];
        foreach (var file in listed.Append("unlisted.txt")) {
            var path = Path.Combine(source, file);
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, "x");
        }
        PayloadManifest.Write(source, listed);
        var removed = PayloadManifest.RemoveStale(source, ["kept.txt"]);
        Require(removed.SequenceEqual(["dropped/old.ps1"]) && File.Exists(Path.Combine(source, "kept.txt"))
            && File.Exists(Path.Combine(source, ".local/preview/user/ForzaProfile/ForzaProfile"))
            && File.Exists(Path.Combine(source, "out/build/x")) && File.Exists(Path.Combine(root, "outside.txt"))
            && File.Exists(Path.Combine(source, "unlisted.txt")), "Stale source removal touched other files");

        // #802: an update over an earlier build must not stamp changed sources
        // with the payload's old fixed timestamp.
        var zipPath = Path.Combine(root, "payload.zip");
        var fixedStamp = new DateTimeOffset(2026, 7, 23, 0, 0, 0, TimeSpan.Zero);
        using (var zip = System.IO.Compression.ZipFile.Open(zipPath, System.IO.Compression.ZipArchiveMode.Create))
            foreach (var (name, text) in new[] { ("same.txt", "same"), ("changed.txt", "new"), ("sub/added.txt", "added") }) {
                var entry = zip.CreateEntry(name);
                entry.LastWriteTime = fixedStamp;
                using var writer = new StreamWriter(entry.Open());
                writer.Write(text);
            }
        var target = Path.Combine(root, "extract");
        Directory.CreateDirectory(target);
        File.WriteAllText(Path.Combine(target, "same.txt"), "same");
        File.WriteAllText(Path.Combine(target, "changed.txt"), "old!");
        var built = new DateTime(2026, 9, 1, 0, 0, 0, DateTimeKind.Utc);
        File.SetLastWriteTimeUtc(Path.Combine(target, "same.txt"), built);
        File.SetLastWriteTimeUtc(Path.Combine(target, "changed.txt"), built);
        Require(PayloadExtractor.Extract(zipPath, target) == 2, "Extraction rewrote unchanged files");
        Require(File.ReadAllText(Path.Combine(target, "changed.txt")) == "new"
            && File.ReadAllText(Path.Combine(target, "sub/added.txt")) == "added", "Extraction missed changed files");
        Require(File.GetLastWriteTimeUtc(Path.Combine(target, "same.txt")) == built, "Unchanged file lost its timestamp");
        Require(File.GetLastWriteTimeUtc(Path.Combine(target, "changed.txt")) > built
            && File.GetLastWriteTimeUtc(Path.Combine(target, "sub/added.txt")) > built, "Changed files kept the old payload date");
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
