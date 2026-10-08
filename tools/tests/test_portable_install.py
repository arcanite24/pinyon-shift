"""Portable installs keep everything beside the launcher and survive a move.

A portable.txt beside PinyonShiftLauncher.exe (or --portable) puts the release
source, tools, build, logs, crash reports and the save tree in a data folder
beside the launcher. Nothing may record that folder's absolute location in a
way that breaks after the folder moves to another drive or PC, and the game
itself must take every location from the state root it is started with.
tools/check-launcher.py exercises the launcher itself.
"""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "launcher/PinyonShift.Launcher"
POWERSHELL = shutil.which("powershell")


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def run_powershell(script, environment=None):
    command = ". ./tools/release-common.ps1\n$ErrorActionPreference = 'Stop'\n" + script
    env = os.environ.copy()
    env.update(environment or {})
    return subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


class PortableLauncherContractTests(unittest.TestCase):
    def setUp(self):
        self.portable = read("launcher/PinyonShift.Launcher/PortableMode.cs")
        self.window = read("launcher/PinyonShift.Launcher/MainWindow.xaml.cs")

    def test_marker_switch_and_data_folder_are_documented_names(self):
        self.assertIn('MarkerFileName = "portable.txt"', self.portable)
        self.assertIn('CommandLineSwitch = "--portable"', self.portable)
        self.assertIn('DataFolderName = "data"', self.portable)
        readme = read("README.md")
        for text in ("portable.txt", "--portable", "Portable:"):
            self.assertIn(text, readme)
        self.assertIn("portable.txt", read("docs/TROUBLESHOOTING.md"))

    def test_portable_root_is_derived_from_the_launcher_folder_each_start(self):
        self.assertIn("PortableMode.DataRoot(AppContext.BaseDirectory)", self.window)
        self.assertIn("Environment.GetCommandLineArgs().Skip(1)", self.window)
        # The only persisted location is the non-portable preference, written
        # only by the folder chooser, which a portable install does not offer.
        portable_branch = self.window[self.window.index("if (_portableRequested)\n        {\n            // Everything"):]
        portable_branch = portable_branch[:portable_branch.index("else")]
        self.assertNotIn("InstallRootPreference", portable_branch)
        self.assertIn("_canChooseInstallRoot = false;", portable_branch)
        # The one registry entry, the RunOnce that resumes setup after a
        # restart, is skipped in portable mode.
        self.assertNotIn("Registry", self.portable)
        registry = self.window[self.window.index("Registry.") - 300:self.window.index("Registry.")]
        self.assertIn("if (_portableRoot is null)", registry)
        self.assertEqual(self.window.count("Registry."), 1)
        self.assertNotIn("LocalApplicationData", self.portable)

    def test_portable_folder_must_be_writable_and_short_enough(self):
        self.assertIn("PortableMode.EnsureWritable(installRoot);", self.window)
        self.assertIn("catch (PortableFolderException ex)", self.window)
        self.assertIn("Program Files", self.portable)
        self.assertIn("MaximumDataRootLength = 70", self.portable)
        self.assertIn("PortableMode.PathLengthProblem(_portableRoot)", self.window)
        # A chosen install folder holds the same tree (#393).
        self.assertIn('PortableMode.PathLengthProblem(_installRoot, "install")', self.window)

    def test_a_missing_vulkan_driver_is_raised_before_the_build(self):
        click = self.window[self.window.index("private async void PrimaryButton_Click"):]
        click = click[:click.index('SetPrimaryText("Building')]
        self.assertIn("ConfirmGraphicsDriverBeforeBuild()", click)
        hardware = (ROOT / "launcher/PinyonShift.Launcher/HardwareCheck.cs").read_text(encoding="utf-8")
        for vendor in ("0x1002", "0x10DE", "0x8086"):
            self.assertIn(vendor, hardware)

    def test_children_keep_temporary_files_and_overrides_inside(self):
        for name in ('"TEMP"', '"TMP"', '"PSModuleAnalysisCachePath"', '"PINYON_SHIFT_INSTALL_ROOT"',
                     '"PINYON_SHIFT_STATE_ROOT"', '"PINYON_SHIFT_GAME_ROOT"'):
            self.assertIn(name, self.portable)
        # Crash reports stage in the temporary folder the launcher hands down.
        self.assertIn("[IO.Path]::GetTempPath()", read("tools/create-crash-report.ps1"))

    def test_location_line_shows_portable_mode(self):
        xaml = read("launcher/PinyonShift.Launcher/MainWindow.xaml")
        self.assertIn('x:Name="BuildLocationPrefixRun"', xaml)
        self.assertIn('"Portable: "', self.window)

    def test_pending_crash_report_follows_a_moved_folder(self):
        self.assertIn("bundle = Path.Combine(reportsRoot, Path.GetFileName(bundle));", self.window)

    def test_path_budget_covers_the_deepest_known_build_file(self):
        budget = int(re.search(r"MaximumDataRootLength = (\d+)", self.portable).group(1))
        deepest = ("source\\0.1.1\\.local\\rexglue\\thirdparty\\vulkan-loader\\tests\\framework\\data\\"
                   "fuzz_test_minimized_test_cases\\clusterfuzz-testcase-minimized-instance_create_"
                   "advanced_fuzzer-4788849181261824")
        self.assertLess(budget + 1 + len(deepest), 260)


class GameStorageTests(unittest.TestCase):
    """The game writes only below the state root the launcher passes it."""

    def test_game_sources_do_not_resolve_user_folders(self):
        pattern = re.compile(r"LOCALAPPDATA|SHGetKnownFolderPath|FOLDERID_|SHGetFolderPath|CSIDL_|"
                             r"SDL_GetPrefPath|GetTempPath|RegCreateKey|RegSetValue")
        offenders = [str(path.relative_to(ROOT)) for path in (ROOT / "src").rglob("*")
                     if path.suffix in {".cpp", ".h", ".hpp", ".c", ".inl"}
                     and pattern.search(path.read_text(encoding="utf-8", errors="replace"))]
        self.assertEqual(offenders, [])

    def test_every_sdk_storage_root_is_overridden_from_the_state_root(self):
        app = read("src/pinyon_shift_app.cpp")
        # The user root is a long (\\?\) path so deep save trees stay under
        # the Win32 limit; the v4 build mounts its own update root.
        for line in ('paths.user_data_root = LongHostPath(state_root / "user");',
                     'paths.update_data_root = state_root / "update";',
                     'paths.update_data_root = state_root / "title-update-v4";',
                     'paths.cache_root = state_root / "cache";',
                     'paths.config_path = state_root / "config" / "pinyon_shift.toml";',
                     'REXCVAR_SET(log_file, (state_root / "logs" / "runtime.log").string());'):
            self.assertIn(line, app)
        diagnostics = read("src/pinyon_shift_diagnostics.cpp")
        self.assertIn('EnvironmentPath("PINYON_SHIFT_STATE_ROOT")', diagnostics)
        self.assertIn('crash::Install(g_state_root / "crashes"', diagnostics)
        self.assertIn('StateRoot() / "photos"', read("src/ui/photo_export.cpp"))
        self.assertIn("$env:PINYON_SHIFT_STATE_ROOT = $resolvedStateRoot", read("tools/launch-preview.ps1"))


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class RelocatedBuildTreeTests(unittest.TestCase):
    def reset(self, build_directory):
        result = run_powershell(
            "[Console]::Out.Write((Reset-PinyonRelocatedCMakeCache -BuildDirectory $env:PINYON_BUILD))",
            {"PINYON_BUILD": str(build_directory)},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def make_tree(self, directory, recorded):
        build = pathlib.Path(directory) / "out" / "build" / "win-amd64-release"
        (build / "CMakeFiles" / "3.31.10").mkdir(parents=True)
        (build / "CMakeFiles" / "3.31.10" / "CMakeSystem.cmake").write_text("x", encoding="utf-8")
        (build / "pinyon_shift.exe").write_text("built", encoding="utf-8")
        (build / "CMakeCache.txt").write_text(
            "# This is the CMakeCache file.\n"
            f"CMAKE_CACHEFILE_DIR:INTERNAL={recorded}\n"
            "CMAKE_HOME_DIRECTORY:INTERNAL=C:/somewhere\n", encoding="utf-8")
        return build

    def test_a_moved_tree_is_configured_afresh_and_keeps_its_outputs(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-moved-") as directory:
            build = self.make_tree(directory, "E:/old place/data/source/0.1.1/out/build/win-amd64-release")
            self.assertEqual(self.reset(build), "True")
            self.assertFalse((build / "CMakeCache.txt").exists())
            self.assertFalse((build / "CMakeFiles").exists())
            self.assertTrue((build / "pinyon_shift.exe").exists())

    def test_a_tree_in_place_is_left_alone_regardless_of_case_and_slashes(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-inplace-") as directory:
            build = pathlib.Path(directory) / "out" / "build" / "win-amd64-release"
            recorded = str(build).replace("\\", "/")
            recorded = recorded[0].lower() + recorded[1:]
            build = self.make_tree(directory, recorded)
            self.assertEqual(self.reset(build), "False")
            self.assertTrue((build / "CMakeCache.txt").exists())
            self.assertTrue((build / "CMakeFiles").exists())

    def test_a_missing_tree_is_not_an_error(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-empty-") as directory:
            self.assertEqual(self.reset(pathlib.Path(directory) / "absent"), "False")

    def test_build_preview_checks_both_trees_before_configuring(self):
        build = read("tools/build-preview.ps1")
        check = build.index("Reset-PinyonRelocatedCMakeCache -BuildDirectory $buildTree")
        self.assertIn("(Join-Path $sdkRoot 'out/build/win-amd64')", build)
        self.assertIn("(Join-Path $root \"out/build/$previewPreset\")", build)
        self.assertLess(check, build.index("'--preset', 'win-amd64'"))
        self.assertLess(check, build.index("'--preset', $previewPreset"))


if __name__ == "__main__":
    unittest.main()
