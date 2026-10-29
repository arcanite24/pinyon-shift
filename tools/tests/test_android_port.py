"""Contracts of the Android port's tooling (docs/ANDROID_PORT_BACKLOG.md)."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pinyon_android  # noqa: E402


class AndroidPortTest(unittest.TestCase):
    def test_policy_forbids_android_binaries(self):
        # AP-6.2: the package and its libraries hold the player's translated
        # game, so none of their forms may enter the repository.
        policy = json.loads((ROOT / "config" / "repository-policy.json").read_text(
            encoding="utf-8"))
        for extension in (".so", ".apk", ".aab", ".idsig", ".keystore", ".jks", ".dex"):
            self.assertIn(extension, policy["forbidden_extensions"])
        self.assertIn("\x7fELF", policy["forbidden_magic_ascii"])
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for pattern in ("*.so", "*.apk", "*.aab", "*.keystore"):
            self.assertIn(pattern, ignore)
        launcher = (ROOT / "tools" / "package-launcher.ps1").read_text(encoding="utf-8")
        for extension in (".so", ".apk", ".keystore"):
            self.assertIn(f"'{extension}'", launcher)

    def test_boundary_check_rejects_a_renamed_elf_library(self):
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            self.skipTest("powershell is not available on this host")
        stray = ROOT / "android" / f"stray-{uuid.uuid4().hex}.bin"
        stray.write_bytes(b"\x7fELF\x02\x01\x01" + bytes(64))
        try:
            check = subprocess.run(
                [ps, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(ROOT / "tools" / "check-repository-boundary.ps1"), "-Json"],
                capture_output=True, text=True, cwd=ROOT)
        finally:
            stray.unlink()
        self.assertNotEqual(check.returncode, 0)
        self.assertIn(stray.name, check.stdout + check.stderr)

    def test_project_template_holds_no_game_code_or_data(self):
        # Only the manifest, the activities' Java sources, the game mode
        # config, the launcher icon and shortcut and the bundled driver's
        # notice are checked in; everything derived from the disc is built
        # locally.
        files = sorted(path.relative_to(ROOT / "android").as_posix()
                       for path in (ROOT / "android").rglob("*") if path.is_file())
        self.assertEqual(files, ["AndroidManifest.xml",
                                 "drivers/turnip-gen8-v37/NOTICE.txt",
                                 "java/studio/deimos/pinyonshift/PinyonShiftActivity.java",
                                 "java/studio/deimos/pinyonshift/SetupActivity.java",
                                 "res/drawable-xxxhdpi/ic_launcher_foreground.png",
                                 "res/mipmap-anydpi-v26/ic_launcher.xml",
                                 "res/values/ic_launcher_background.xml",
                                 "res/values/strings.xml",
                                 "res/xml/game_mode_config.xml",
                                 "res/xml/shortcuts.xml"])
        # Small files only, so nothing large hides among them; the setup
        # screen's source is the one longer file.
        for path in (ROOT / "android").rglob("*"):
            if path.is_file():
                limit = 64 * 1024 if path.suffix == ".java" else 16 * 1024
                self.assertLess(path.stat().st_size, limit, path.name)

    def test_manifest_asks_only_for_sockets_rumble_and_updates(self):
        manifest = (ROOT / "android" / "AndroidManifest.xml").read_text(encoding="utf-8")
        permissions = sorted(re.findall(r'uses-permission android:name="([^"]+)"', manifest))
        # Sockets for the title's system link (socket() fails without it and
        # the title dereferences null), vibration for rumble, and installing
        # the newer APK a PC's share offers; nothing else.
        self.assertEqual(permissions, ["android.permission.INTERNET",
                                       "android.permission.REQUEST_INSTALL_PACKAGES",
                                       "android.permission.VIBRATE"])
        self.assertIn('android:extractNativeLibs="true"', manifest)
        self.assertIn("android.hardware.vulkan.version", manifest)
        self.assertIn(pinyon_android.ACTIVITY, manifest)

    def test_activity_loads_the_runtime_before_the_game(self):
        # SDL lives in librexruntime.so; it registers its Java natives when
        # System.loadLibrary loads it, and SDL calls SDL_main in the last.
        activity = (ROOT / "android" / "java" / "studio" / "deimos" / "pinyonshift"
                    / "PinyonShiftActivity.java").read_text(encoding="utf-8")
        self.assertIn('{"c++_shared", "rexruntime", "main"}', activity)
        self.assertEqual(pinyon_android.NATIVE_LIBRARIES[-1], "libmain.so")

    def test_the_app_icon_opens_setup_until_the_game_is_copied(self):
        # ONE_CLICK_SETUP_BACKLOG A-4: the launcher entry is the setup
        # screen, which hands over to the game once its files are present;
        # tooling still starts the game activity directly.
        manifest = (ROOT / "android" / "AndroidManifest.xml").read_text(encoding="utf-8")
        setup = manifest[manifest.index('android:name="studio.deimos.pinyonshift.SetupActivity"'):]
        setup = setup[:setup.index("</activity>")]
        game = manifest[manifest.index(f'android:name="{pinyon_android.ACTIVITY}"'):]
        game = game[:game.index("</activity>")]
        self.assertIn("android.intent.category.LAUNCHER", setup)
        self.assertNotIn("android.intent.category.LAUNCHER", game)
        self.assertIn("studio.deimos.pinyonshift.SETUP", setup)
        self.assertIn('android:usesCleartextTraffic="true"', manifest)
        shortcuts = (ROOT / "android" / "res" / "xml" / "shortcuts.xml").read_text(encoding="utf-8")
        self.assertIn("studio.deimos.pinyonshift.SETUP", shortcuts)

    def test_setup_writes_only_inside_the_game_and_state_folders(self):
        source = (ROOT / "android" / "java" / "studio" / "deimos" / "pinyonshift"
                  / "SetupActivity.java").read_text(encoding="utf-8")
        self.assertIn('path.startsWith("game/base/") || path.startsWith("state/")', source)
        self.assertIn('part.equals("..")', source)
        self.assertIn("getCanonicalPath()", source)
        # The PC's save replaces the device's only after a backup.
        self.assertLess(source.index("backUpSave();"), source.index("fetch(code,"))

    def test_java_sources_avoid_lambdas(self):
        # javac compiles against android.jar alone, which has no
        # LambdaMetafactory: a lambda or method reference fails the package.
        for path in (ROOT / "android" / "java").rglob("*.java"):
            code = re.sub(r"//.*|/\*.*?\*/|\"(?:\\.|[^\"\\])*\"", "",
                          path.read_text(encoding="utf-8"), flags=re.S)
            self.assertNotRegex(code, r"->|::", path.name)

    def test_version_code_follows_the_release(self):
        release = json.loads((ROOT / "config" / "release.json").read_text(encoding="utf-8"))
        name, code = pinyon_android.release_version()
        self.assertEqual(name, release["version"])
        major, minor, patch = (int(part) for part in name.split("-")[0].split(".")[:3])
        self.assertEqual(code, major * 10000 + minor * 100 + patch)

    def test_android_presets_target_the_pinned_platform(self):
        presets = json.loads((ROOT / "CMakePresets.json").read_text(encoding="utf-8"))
        base = next(p for p in presets["configurePresets"] if p["name"] == "android-base")
        variables = base["cacheVariables"]
        self.assertEqual(variables["ANDROID_ABI"], pinyon_android.CONFIG["abi"])
        self.assertEqual(variables["ANDROID_PLATFORM"],
                         f"android-{pinyon_android.CONFIG['min_sdk']}")
        # One C++ runtime shared by the game, the runtime and the plugin.
        self.assertEqual(variables["ANDROID_STL"], "c++_shared")
        # Android 15's 16 KiB-page kernels need 16 KiB-aligned segments.
        self.assertIn("max-page-size=16384", variables["CMAKE_SHARED_LINKER_FLAGS"])
        self.assertNotIn("-msse", json.dumps(base))

    def test_pushed_files_are_opened_to_the_app(self):
        # On Android 15 the app cannot list what adb pushed into its own
        # folder; the shell opens what it owns, and only that.
        calls = []
        original = pinyon_android.adb
        pinyon_android.adb = lambda tools, args, *command, **kwargs: calls.append(command)
        try:
            pinyon_android.share_with_app(None, None, "/sdcard/app/game", "/sdcard/app/state")
        finally:
            pinyon_android.adb = original
        self.assertEqual(len(calls), 2)
        for command, path in zip(calls, ("/sdcard/app/game", "/sdcard/app/state")):
            self.assertEqual(command[0], "shell")
            self.assertIn(f"find '{path}' -user shell", command[1])
            self.assertIn("chmod a+rwX", command[1])
        source = (ROOT / "tools" / "pinyon_android.py").read_text(encoding="utf-8")
        push_data = source[source.index("def push_data"):source.index("def _pid")]
        self.assertIn("share_with_app(", push_data)


class FakeProcess:
    def __init__(self, code, lines):
        self.returncode = code
        self.stdout = iter(lines)
        self.stdin = mock.MagicMock()

    def wait(self):
        return self.returncode


class AndroidSetupRobustnessTest(unittest.TestCase):
    """Player failures of the Android build on a PC with no developer tools."""

    def install(self, processes):
        tools = mock.Mock(sdkmanager=Path("sdkmanager.bat"), sdk=Path("sdk"))
        sleeps = []
        with mock.patch.object(pinyon_android.subprocess, "Popen", side_effect=processes) as popen:
            try:
                pinyon_android.sdkmanager_install(tools, mock.Mock(accept_licenses=True), {},
                                                  sleep=sleeps.append)
            finally:
                self.popen = popen
        return sleeps

    def test_a_dropped_download_is_retried_with_a_pause(self):
        # Changing network or a VPN fixed the failure for players (#811, #868).
        sleeps = self.install([FakeProcess(1, ["Fetch remote repository...\n"]),
                               FakeProcess(1, ["Connection reset\n"]), FakeProcess(0, [])])
        self.assertEqual(self.popen.call_count, 3)
        self.assertEqual(sleeps, [10, 20])
        for call in self.popen.call_args_list:
            self.assertIn("--install", call.args[0])

    def test_the_last_failure_names_the_packages_and_the_host(self):
        with self.assertRaises(pinyon_android.AndroidError) as raised:
            self.install([FakeProcess(1, []) for _ in range(pinyon_android.TRANSIENT_ATTEMPTS)])
        self.assertIn("ndk;29.0.14206865", str(raised.exception))
        self.assertIn("dl.google.com", str(raised.exception))
        self.assertEqual(self.popen.call_count, pinyon_android.TRANSIENT_ATTEMPTS)

    def test_old_java_is_not_retried(self):
        # sdkmanager: "Java version 17 or higher is required." (#811).
        with self.assertRaises(pinyon_android.AndroidError) as raised:
            self.install([FakeProcess(1, ["Java version 17 or higher is required.\n"])])
        self.assertEqual(self.popen.call_count, 1)
        self.assertIn("Java 17", str(raised.exception))

    def test_jdk_versions_parse_and_unrunnable_ones_are_none(self):
        for text, major in (("javac 17.0.20.1\n", 17), ("javac 1.8.0_411\n", 8),
                            ("javac 21\n", 21), ("nonsense\n", None)):
            completed = mock.Mock(stdout="", stderr=text)
            with mock.patch.object(pinyon_android.subprocess, "run", return_value=completed):
                self.assertEqual(pinyon_android.jdk_major("javac"), major, text)
        with mock.patch.object(pinyon_android.subprocess, "run", side_effect=OSError):
            self.assertIsNone(pinyon_android.jdk_major("javac"))

    def test_a_jdk_folder_needs_javac_keytool_and_the_pinned_version(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / "bin").mkdir()
            (home / "bin" / pinyon_android._exe("javac")).write_bytes(b"")
            with mock.patch.object(pinyon_android, "jdk_major", return_value=17):
                self.assertFalse(pinyon_android._usable_jdk(home))  # no keytool (#868)
                (home / "bin" / pinyon_android._exe("keytool")).write_bytes(b"")
                self.assertTrue(pinyon_android._usable_jdk(home))
            with mock.patch.object(pinyon_android, "jdk_major", return_value=8):
                self.assertFalse(pinyon_android._usable_jdk(home))  # Java 8 (#811)
                with mock.patch.dict(os.environ, {"JAVA_HOME": str(home)}), \
                        mock.patch.object(pinyon_android, "LOCAL_JDK", home / "none"):
                    self.assertIsNone(pinyon_android.java_home())

    def test_cmake_gets_a_git_when_the_pc_has_none(self):
        # FetchContent cloned FidelityFX with git: "could not find git" (#810).
        git = Path("mingit") / "cmd" / "git.exe"
        with mock.patch.object(pinyon_android, "pinned_git", return_value=git), \
                mock.patch.object(pinyon_android.shutil, "which", return_value=None):
            environment = pinyon_android.with_git({"PATH": "elsewhere"})
        self.assertEqual(environment["PATH"].split(os.pathsep), [str(git.parent), "elsewhere"])
        with mock.patch.object(pinyon_android, "pinned_git", return_value=git), \
                mock.patch.object(pinyon_android.shutil, "which", return_value="/usr/bin/git"):
            self.assertEqual(pinyon_android.with_git({"PATH": "elsewhere"}), {"PATH": "elsewhere"})

    def test_the_pinned_git_is_read_from_the_toolchain_pins(self):
        pins = (ROOT / "config" / "release-toolchain.json").read_text(encoding="utf-8")
        entry = json.loads(pins)["git"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config").mkdir()
            (root / "config" / "release-toolchain.json").write_text(pins, encoding="utf-8")
            with mock.patch.object(pinyon_android, "ROOT", root):
                self.assertIsNone(pinyon_android.pinned_git())  # not provisioned yet
                executable = root / entry["install_path"] / entry["executable"]
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b"")
                self.assertEqual(pinyon_android.pinned_git(), executable)

    def test_both_cmake_runs_get_the_git_environment(self):
        source = (ROOT / "tools" / "pinyon_android.py").read_text(encoding="utf-8")
        build = source[source.index("def build(args"):source.index("def configured")]
        self.assertIn("with_git(dict(os.environ, ANDROID_NDK_HOME", build)
        self.assertIn("build_fidelityfx(tools, args, environment)", build)


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell 5.1 only")
class LongPathUnzipTest(unittest.TestCase):
    def test_a_zip_deeper_than_260_characters_unpacks(self):
        # The Android command-line tools under a long install folder (#799).
        import zipfile
        with tempfile.TemporaryDirectory(prefix="pinyon long ") as temp:
            temp = Path(temp)
            archive = temp / "tools.zip"
            deep = "cmdline-tools/lib/" + "/".join(["segment-" + "x" * 30] * 5) + "/leaf.jar"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("cmdline-tools/bin/sdkmanager.bat", "bat")
                bundle.writestr(deep, "jar")
            destination = temp / ("d" * 40) / ("e" * 40)
            script = temp / "run.ps1"
            script.write_text(
                f". '{ROOT / 'tools' / 'release-common.ps1'}'\n"
                "$ErrorActionPreference = 'Stop'\n"
                f"Expand-PinyonZip -Archive '{archive}' -Destination '{destination}'\n"
                f"$deep = Join-Path '{destination}' '{deep.replace('/', chr(92))}'\n"
                "if ($deep.Length -le 260) { throw 'the test path is not long enough' }\n"
                "Initialize-PinyonLongPath\n"
                "if (-not [IO.File]::Exists([PinyonLongPath]::Prefix($deep))) { throw 'missing' }\n"
                f"[IO.Directory]::Move('{destination}\\cmdline-tools', '{destination}\\latest')\n"
                f"if (-not (Test-Path '{destination}\\latest\\bin\\sdkmanager.bat')) "
                "{ throw 'not moved' }\n"
                f"Remove-PinyonTree -Path '{temp / ('d' * 40)}'\n"
                f"if (Test-Path '{destination}') {{ throw 'not removed' }}\n"
                "'ok'\n", encoding="utf-8")
            result = subprocess.run(
                ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
