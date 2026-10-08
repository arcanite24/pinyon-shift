"""Contracts of the Android port's tooling (docs/ANDROID_PORT_BACKLOG.md)."""

import json
import re
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

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
        stray = ROOT / "android" / f"stray-{uuid.uuid4().hex}.bin"
        stray.write_bytes(b"\x7fELF\x02\x01\x01" + bytes(64))
        try:
            check = subprocess.run(
                ["powershell", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                 str(ROOT / "tools" / "check-repository-boundary.ps1"), "-Json"],
                capture_output=True, text=True, cwd=ROOT)
        finally:
            stray.unlink()
        self.assertNotEqual(check.returncode, 0)
        self.assertIn(stray.name, check.stdout + check.stderr)

    def test_project_template_holds_no_game_code_or_data(self):
        # Only the manifest, the activity's Java source, the game mode
        # config, the launcher icon and the bundled driver's notice are
        # checked in; everything derived from the disc is built locally.
        files = sorted(path.relative_to(ROOT / "android").as_posix()
                       for path in (ROOT / "android").rglob("*") if path.is_file())
        self.assertEqual(files, ["AndroidManifest.xml",
                                 "drivers/turnip-gen8-v37/NOTICE.txt",
                                 "java/studio/deimos/pinyonshift/PinyonShiftActivity.java",
                                 "res/drawable-xxxhdpi/ic_launcher_foreground.png",
                                 "res/mipmap-anydpi-v26/ic_launcher.xml",
                                 "res/values/ic_launcher_background.xml",
                                 "res/xml/game_mode_config.xml"])
        for path in (ROOT / "android").rglob("*"):
            if path.is_file():
                self.assertLess(path.stat().st_size, 16 * 1024)

    def test_manifest_asks_only_for_sockets_and_rumble(self):
        manifest = (ROOT / "android" / "AndroidManifest.xml").read_text(encoding="utf-8")
        permissions = sorted(re.findall(r'uses-permission android:name="([^"]+)"', manifest))
        # Sockets for the title's system link (socket() fails without it and
        # the title dereferences null), vibration for rumble; nothing else.
        self.assertEqual(permissions, ["android.permission.INTERNET",
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


if __name__ == "__main__":
    unittest.main()
