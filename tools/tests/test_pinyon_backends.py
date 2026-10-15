"""pinyon.py's launcher backends: paths, title update, saves, crash bundles,
the launch result, the hardware check and shader preparation.

The Desktop launcher runs these on Linux, the Steam Deck and macOS and parses
one JSON object from each (RunXeAsync's contract), so the shapes and the
path handling (case-sensitive file systems, portable installs) are checked
here on every OS.
"""

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import pinyon  # noqa: E402
import pinyon_common as common  # noqa: E402
import pinyon_crash  # noqa: E402
import pinyon_hardware  # noqa: E402
import pinyon_saves  # noqa: E402
import pinyon_shaders  # noqa: E402
import pinyon_title_update  # noqa: E402

TITLE = common.TITLE_ID
XUID = "E0000123456789AB"


def run_json(argv: list[str]) -> tuple[int, dict]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = pinyon.main(argv)
    lines = [line for line in out.getvalue().splitlines() if line.startswith("{")]
    return code, json.loads(lines[-1])


def make_profile(user: Path, xuid: str, content: bytes = b"save") -> Path:
    profile = user / xuid / TITLE / "00000001" / "ForzaProfile" / "ForzaProfile"
    profile.parent.mkdir(parents=True)
    profile.write_bytes(content)
    return profile


class PathTests(unittest.TestCase):
    def test_lookups_ignore_case_and_keep_the_folder_spelling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Content" / "0000000000000000" / "4d5309c9").mkdir(parents=True)
            found = common.path_ignoring_case(root, "content", "0000000000000000", "4D5309C9")
            self.assertIsNotNone(found)
            # On a case-sensitive file system this is the folder's own spelling.
            self.assertTrue(found.is_dir())
            self.assertEqual(found.name.lower(), "4d5309c9")
            self.assertIsNone(common.path_ignoring_case(root, "content", "missing", "x"))
            self.assertIsNone(common.child_ignoring_case(root / "absent", "x"))

    def test_portable_marker_puts_the_install_beside_the_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory)
            (launcher / "portable.txt").write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PINYON_SHIFT_INSTALL_ROOT": str(launcher / "x")}):
                code, result = run_json(["paths", "--launcher-dir", str(launcher), "--json"])
            self.assertEqual(code, 0)
            self.assertTrue(result["portable"])
            self.assertEqual(Path(result["install_root"]), launcher.resolve() / "data")
            self.assertEqual(result["ignored_overrides"], ["PINYON_SHIFT_INSTALL_ROOT"])
            self.assertFalse(result["install_root_overridden"])
            for key in ("platform", "source_root", "state_root", "game_root", "logs", "saves",
                        "build_directory", "v4_build_directory", "extractor", "game_built",
                        "v4_built", "result"):
                self.assertIn(key, result)

    def test_install_root_override_and_default(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"PINYON_SHIFT_INSTALL_ROOT": directory}):
                self.assertEqual(common.install_root(None), (Path(directory).resolve(), False))
            environment = {key: value for key, value in os.environ.items()
                           if key != "PINYON_SHIFT_INSTALL_ROOT"}
            with mock.patch.dict(os.environ, environment, clear=True):
                root, portable = common.install_root(Path(directory))
            self.assertFalse(portable)
            self.assertEqual(root.name, "PinyonShift")

    def test_folder_check_reports_the_file_system(self):
        with tempfile.TemporaryDirectory() as directory:
            code, result = run_json(["paths", "--check", directory, "--json"])
            self.assertEqual(code, 0)
            check = result["check"]
            for key in ("writable", "free_gb", "case_sensitive", "problems"):
                self.assertIn(key, check)
            self.assertTrue(check["writable"])
            self.assertIsInstance(check["problems"], list)


class TitleUpdateTests(unittest.TestCase):
    def test_choice_round_trip_keeps_only_use_and_club(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            self.assertEqual(pinyon_title_update.read_choice(state), {"use": False, "club": False})
            path = pinyon_title_update.choice_path(state)
            path.parent.mkdir(parents=True)
            # The Windows launcher's PowerShell 5.1 writes a byte-order mark.
            path.write_bytes(b'\xef\xbb\xbf{"use": true, "other": 1}')
            self.assertEqual(pinyon_title_update.read_choice(state), {"use": True, "club": False})
            pinyon_title_update.write_choice(state, "club", True)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                             {"use": True, "club": True})
            # Not installed: the saved choice does not start v4.
            self.assertFalse(pinyon_title_update.wants_v4(state))
            folder = state / pinyon_title_update.UPDATE_FOLDER
            folder.mkdir()
            for name in pinyon_title_update.UPDATE_FILES:
                (folder / name).write_bytes(b"x")
            self.assertTrue(pinyon_title_update.wants_v4(state))

    def test_commands_change_the_saved_choice(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.dict(os.environ, {"PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME": "1"}):
            code, result = run_json(["title-update", "enable", "--state-root", directory,
                                     "--json"])
            self.assertEqual((code, result["result"]), (1, "error"))
            self.assertIn("Import the verified title update first", result["error"])
            folder = Path(directory) / pinyon_title_update.UPDATE_FOLDER
            folder.mkdir()
            for name in pinyon_title_update.UPDATE_FILES:
                (folder / name).write_bytes(b"x")
            for action, expected in (("enable", {"use": True, "club": False}),
                                     ("club-on", {"use": True, "club": True}),
                                     ("disable", {"use": False, "club": True}),
                                     ("club-off", {"use": False, "club": False})):
                code, result = run_json(["title-update", action, "--state-root", directory,
                                         "--json"])
                self.assertEqual(code, 0, result)
                self.assertEqual(pinyon_title_update.read_choice(Path(directory)), expected)
                for key in ("installed", "use", "club", "built", "stale", "build_directory",
                            "profiles", "pre_v4_backups"):
                    self.assertIn(key, result)
                self.assertTrue(result["installed"])
                self.assertEqual(result["use"], expected["use"])
                self.assertEqual(result["club"], expected["club"])

    def test_import_of_a_missing_package_fails_as_json(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.dict(os.environ, {"PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME": "1"}):
            code, result = run_json(["title-update", "import", str(Path(directory) / "none.zip"),
                                     "--state-root", directory, "--json"])
            self.assertEqual(code, 1)
            self.assertEqual(result["result"], "error")
            self.assertIn("error", result)

    def test_zip_members_cannot_leave_the_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "update.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("../escape.txt", "x")
            with self.assertRaises(common.CommandError):
                pinyon_title_update.extract_zip(archive, Path(directory) / "out")
            self.assertFalse((Path(directory) / "escape.txt").exists())


class LaunchTests(unittest.TestCase):
    def test_deliberate_exits_map_on_every_os(self):
        for code, result in ((1306, "config-unavailable"), (1307, "saved-content-unavailable"),
                             (1308, "graphics-unavailable")):
            self.assertEqual(pinyon.exit_result(code), result)
            with mock.patch.object(pinyon, "WINDOWS", False):
                # POSIX keeps the low 8 bits: 26, 27, 28.
                self.assertEqual(pinyon.exit_result(code & 0xFF), result)
            with mock.patch.object(pinyon, "WINDOWS", True):
                self.assertIsNone(pinyon.exit_result(code & 0xFF))
        self.assertIsNone(pinyon.exit_result(0))
        self.assertIsNone(pinyon.exit_result(-11))

    def test_play_follows_the_saved_title_update_choice(self):
        def args(**overrides):
            values = {"title_update_v4": False, "base_disc": False, "render_test_script": None,
                      "build_directory": None}
            values.update(overrides)
            return argparse.Namespace(**values)

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with mock.patch.object(pinyon_title_update, "wants_v4", return_value=True), \
                    mock.patch.object(pinyon, "xe_enabled", return_value=False):
                self.assertTrue(pinyon.choose_title_update(args(), state))
                self.assertFalse(pinyon.choose_title_update(args(base_disc=True), state))
                self.assertFalse(pinyon.choose_title_update(
                    args(render_test_script=Path("route.fh1test")), state))
                self.assertFalse(pinyon.choose_title_update(args(build_directory=Path("b")),
                                                            state))
            with mock.patch.object(pinyon_title_update, "wants_v4", return_value=True), \
                    mock.patch.object(pinyon, "xe_enabled", return_value=True), \
                    redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                # XE is made for the base disc and wins over a saved v4 choice.
                self.assertFalse(pinyon.choose_title_update(args(), state))
            with mock.patch.object(pinyon_title_update, "wants_v4", return_value=False):
                self.assertFalse(pinyon.choose_title_update(args(), state))
                self.assertTrue(pinyon.choose_title_update(args(title_update_v4=True), state))

    def test_v4_without_the_update_is_a_reasoned_error(self):
        with tempfile.TemporaryDirectory() as directory:
            namespace = argparse.Namespace(title_update_v4=True, build_directory=None, json=True,
                                           render_test_script=None)
            with self.assertRaises(pinyon.LaunchError) as raised:
                pinyon.prepare_title_update(namespace, Path(directory), Path(directory),
                                            Path(directory))
            self.assertEqual(raised.exception.reason, "title-update-missing")


class CrashReportTests(unittest.TestCase):
    def test_paths_user_names_and_profiles_are_replaced(self):
        replacements = {"<STATE_ROOT>": r"C:\Users\Ann\code\pinyon\.local\preview",
                        "<SOURCE_ROOT>": r"C:\Users\Ann\code\pinyon", "<USERNAME>": "Ann"}
        text = ("state C:/Users/Ann/code/pinyon/.local/preview/logs/a.jsonl\n"
                r"source c:\users\ann\code\pinyon\src" "\n"
                r"json C:\\Users\\Ann\\code\\pinyon\\x" "\n"
                "other D:\\Users\\Bob\\file and /home/carol/.config and /Users/dave/Library\n"
                "user Ann said hi; Annette stays\n")
        protected = pinyon_crash.protect(text, replacements)
        self.assertIn("state <STATE_ROOT>/logs/a.jsonl", protected)
        self.assertIn(r"source <SOURCE_ROOT>\src", protected)
        self.assertIn(r"json <SOURCE_ROOT>\\x", protected)
        for name in ("Ann ", "Bob", "carol", "dave"):
            self.assertNotIn(name, protected)
        self.assertIn("user <USERNAME> said hi; Annette stays", protected)
        self.assertEqual(protected.count("<USER_PROFILE>"), 3)

    def test_windows_and_posix_crash_text(self):
        windows = pinyon_crash.crash_details(
            "code=0xc0000005 address=0x7ff612345678 operation=Read\n"
            "fault_module=PINYON_SHIFT.EXE fault_offset=0x1234\n#0 0x7ff6 Guest_Foo+0x10\n")
        self.assertEqual(windows, {"exception_code": "0XC0000005", "operation": "read",
                                   "fault_module": "pinyon_shift.exe", "fault_offset": "0x1234",
                                   "top_frame": "guest_foo+0x10"})
        posix = pinyon_crash.crash_details(
            "signal=SIGSEGV\nfault_address=0x0000000000000010\npc=0x00005555deadbeef\n"
            "pc_module=/home/ann/pinyon/out/build/linux-amd64-release/pinyon_shift\n"
            "pc_offset=0x0000000000abc123\n")
        self.assertEqual(posix["exception_code"], "SIGSEGV")
        self.assertEqual(posix["fault_module"], "pinyon_shift")
        self.assertEqual(posix["fault_offset"], "0xabc123")
        self.assertEqual(posix["operation"], "unspecified")

    def test_no_pending_report(self):
        with tempfile.TemporaryDirectory() as directory:
            code, result = run_json(["crash-report", "pending", "--state-root", directory,
                                     "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(result["result"], "ok")

    def test_iso_times_round_trip(self):
        moment = pinyon_crash.parse_utc("2026-10-15T01:02:03.4560000Z")
        self.assertEqual(pinyon_crash.iso_utc(moment), "2026-10-15T01:02:03.4560000Z")


class ImportSaveTests(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ,
                                           {"PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state = self.root / "state"

    def test_another_install_replaces_profiles_after_a_backup(self):
        make_profile(self.state / "user", XUID, b"old")
        make_profile(self.state / "user", "E000000000000002", b"kept")
        content = self.state / "user" / common.CONTENT_USER / TITLE / "00000002" / "pack"
        content.mkdir(parents=True)
        other = self.root / "other" / ".local" / "preview"
        make_profile(other / "user", XUID.lower(), b"new")
        code, result = run_json(["import-save", str(self.root / "other"), "--state-root",
                                 str(self.state), "--json"])
        self.assertEqual(code, 0, result)
        self.assertEqual(result["imported_profiles"], [XUID])
        self.assertEqual(result["source_trees"], ["user"])
        backup = Path(result["backup"]) / "user"
        self.assertEqual((backup / XUID / TITLE / "00000001/ForzaProfile/ForzaProfile")
                         .read_bytes(), b"old")
        self.assertTrue((backup / "E000000000000002").is_dir())
        self.assertFalse((backup / common.CONTENT_USER).exists())
        self.assertEqual((self.state / "user" / XUID / TITLE /
                          "00000001/ForzaProfile/ForzaProfile").read_bytes(), b"new")
        self.assertTrue((self.state / "user/E000000000000002").is_dir())
        self.assertTrue(content.is_dir())
        self.assertEqual(result["xuid"], XUID)

    def test_the_modded_tree_stays_apart_from_the_players_own(self):
        # Cheats and mods play user-modded so cheated progress never reaches
        # the player's own save (src/cheats.cpp); an import keeps that apart.
        make_profile(self.state / "user-modded", XUID, b"old modded")
        other = self.root / "other"
        make_profile(other / "user", XUID, b"base")
        make_profile(other / "user-modded", XUID, b"modded")
        self.assertEqual(set(pinyon_saves.find_source_trees(other)), {"user", "user-modded"})
        code, result = run_json(["import-save", str(other), "--state-root", str(self.state),
                                 "--json"])
        self.assertEqual(code, 0, result)
        self.assertEqual(result["source_trees"], ["user", "user-modded"])
        self.assertEqual(result["imported_modded_profiles"], [XUID])
        save = Path(XUID) / TITLE / "00000001/ForzaProfile/ForzaProfile"
        self.assertEqual((self.state / "user" / save).read_bytes(), b"base")
        self.assertEqual((self.state / "user-modded" / save).read_bytes(), b"modded")
        self.assertEqual((Path(result["backup"]) / "user-modded" / save).read_bytes(),
                         b"old modded")

    def test_a_zip_with_unsafe_paths_is_refused(self):
        archive = self.root / "save.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr(f"user/{XUID}/{TITLE}/00000001/ForzaProfile/ForzaProfile", "x")
            output.writestr("../evil.txt", "x")
        code, result = run_json(["import-save", str(archive), "--state-root", str(self.state),
                                 "--json"])
        self.assertEqual(code, 1)
        self.assertIn("unsafe", result["error"])
        self.assertFalse((self.root / "evil.txt").exists())

    def test_a_zip_of_a_user_folder_imports(self):
        archive = self.root / "save.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr(f"preview/user/{XUID}/{TITLE}/00000001/ForzaProfile/ForzaProfile",
                            "zipped")
        code, result = run_json(["import-save", str(archive), "--state-root", str(self.state),
                                 "--json"])
        self.assertEqual(code, 0, result)
        self.assertIsNone(result["backup"])
        self.assertEqual(result["imported_profiles"], [XUID])

    def test_this_install_is_not_its_own_source(self):
        make_profile(self.state / "user", XUID)
        for source in (self.state, self.state / "user"):
            code, result = run_json(["import-save", str(source), "--state-root",
                                     str(self.state), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("not this one", result["error"])

    def test_a_folder_without_a_save(self):
        (self.root / "empty").mkdir()
        code, result = run_json(["import-save", str(self.root / "empty"), "--state-root",
                                 str(self.state), "--json"])
        self.assertEqual(code, 1)
        self.assertIn("No Pinyon Shift save", result["error"])


class HardwareTests(unittest.TestCase):
    def gpu(self, discrete=True, memory=8 << 30, vulkan_13=True):
        return {"name": "GPU", "discrete": discrete, "device_local_bytes": memory,
                "supports_vulkan_13": vulkan_13, "vulkan_version": "1.3.0" if vulkan_13 else "1.2.0"}

    def test_presets_follow_the_windows_launcher_thresholds(self):
        recommend = pinyon_hardware.recommend
        self.assertEqual(recommend(self.gpu(), 16, 8, 120)["preset"], "performance_120")
        self.assertNotEqual(recommend(self.gpu(), 16, 8, 60)["preset"], "performance_120")
        self.assertNotEqual(recommend(self.gpu(memory=4 << 30), 16, 8, 144)["preset"],
                            "performance_120")
        self.assertEqual(recommend(self.gpu(discrete=False), 4, 2, 60)["preset"], "ultra_low_30")
        self.assertEqual(recommend(self.gpu(), 4, 3, 60)["preset"], "balanced_40")
        self.assertIsNone(recommend(self.gpu(), 16, 8, 120)["warning"])
        self.assertIn("1.3", recommend(self.gpu(vulkan_13=False), 16, 8, 60)["warning"])
        self.assertIsNotNone(recommend(None, 16, 8, 60)["warning"])
        # llvmpipe (WSL, a VM, no driver) draws on the CPU.
        software = self.gpu(discrete=False) | {"software": True, "name": "llvmpipe"}
        self.assertIn("software Vulkan renderer", recommend(software, 16, 8, 60)["warning"])

    def test_presets_are_ones_the_settings_backend_knows(self):
        import pinyon_config
        for gpu, logical, cores, refresh in ((self.gpu(), 16, 8, 120),
                                             (self.gpu(discrete=False), 4, 2, 60),
                                             (self.gpu(), 4, 3, 60), (self.gpu(), 8, 4, 60)):
            preset = pinyon_hardware.recommend(gpu, logical, cores, refresh)["preset"]
            self.assertIn(preset, pinyon_config.GAME_PRESETS)

    def test_the_command_answers_with_one_object(self):
        code, result = run_json(["hardware", "--refresh-hz", "60", "--json"])
        self.assertEqual(code, 0)
        for key in ("vulkan", "gpu", "logical_processors", "physical_cores", "refresh_hz",
                    "recommendation", "description", "driver_page", "result"):
            self.assertIn(key, result)


class ShaderPreparationTests(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ,
                                           {"PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state, self.build = self.root / "state", self.root / "build"
        self.build.mkdir()
        (self.build / common.EXECUTABLE).write_bytes(b"game")
        self.quiet = mock.patch("sys.stderr", io.StringIO())
        self.quiet.start()
        self.addCleanup(self.quiet.stop)

    def test_stored_pipelines_need_no_preparation(self):
        shareable = self.state / "cache/shaders/shareable"
        shareable.mkdir(parents=True)
        (shareable / "a.vk.xpso").write_bytes(b"x")
        with mock.patch.object(subprocess, "run") as run:
            result = pinyon_shaders.prepare(self.state, self.root, self.build, True)
        self.assertEqual(result["shaders"], "ready")
        run.assert_not_called()

    def test_a_failed_attempt_is_not_retried_for_the_same_build(self):
        completed = subprocess.CompletedProcess([], 0, stdout='{"result":"crashed"}\n', stderr="")
        with mock.patch.object(common, "ROOT", self.root), \
                mock.patch.object(subprocess, "run", return_value=completed) as run:
            first = pinyon_shaders.prepare(self.state, self.root, self.build, True)
            second = pinyon_shaders.prepare(self.state, self.root, self.build, True)
            self.assertEqual(first["shaders"], "skipped")
            self.assertEqual(second["shaders"], "ready")
            self.assertEqual(run.call_count, 1)
            # A new build tries again.
            (self.build / common.EXECUTABLE).write_bytes(b"new game")
            pinyon_shaders.prepare(self.state, self.root, self.build, True)
            self.assertEqual(run.call_count, 2)

    def test_a_completed_route_keeps_its_storage_without_replacing(self):
        existing = self.state / "cache/shaders/b.vkpipelinecache.1.bin"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"player's")

        def route(command, **_):
            route_state = Path(command[command.index("--state-root") + 1])
            (route_state / "logs").mkdir(parents=True)
            (route_state / "logs/s.jsonl").write_text(
                '{"event":"fh1.render_test.complete"}\n', encoding="utf-8")
            shareable = route_state / "cache/shaders/shareable"
            shareable.mkdir(parents=True)
            (shareable / "a.vk.xpso").write_bytes(b"pso")
            (shareable / "a.xsh").write_bytes(b"xsh")
            (route_state / "cache/shaders/b.vkpipelinecache.1.bin").write_bytes(b"route's")
            return subprocess.CompletedProcess(command, 0, stdout='{"result":"normal-exit"}\n',
                                               stderr="")

        with mock.patch.object(common, "ROOT", self.root), \
                mock.patch.object(subprocess, "run", side_effect=route):
            result = pinyon_shaders.prepare(self.state, self.root, self.build, True)
        self.assertEqual(result["shaders"], "prepared")
        self.assertEqual(result["copied"], 2)
        self.assertEqual(existing.read_bytes(), b"player's")
        self.assertTrue((self.state / "cache/shaders/shareable/a.vk.xpso").is_file())

    def test_the_route_state_carries_the_title_update_for_v4(self):
        update = self.state / "title-update-v4"
        update.mkdir(parents=True)
        (update / "default.xexp").write_bytes(b"patch")
        seen = []

        def route(command, **_):
            route_state = Path(command[command.index("--state-root") + 1])
            seen.append((route_state / "title-update-v4/default.xexp").read_bytes())
            return subprocess.CompletedProcess(command, 0, stdout='{"result":"normal-exit"}\n',
                                               stderr="")

        with mock.patch.object(common, "ROOT", self.root), \
                mock.patch.object(subprocess, "run", side_effect=route):
            pinyon_shaders.prepare(self.state, self.root, self.build, True)
        self.assertEqual(seen, [b"patch"])


if __name__ == "__main__":
    unittest.main()
