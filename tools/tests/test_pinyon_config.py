"""pinyon.py config: the host-config editing rules and the Settings panel.

tools/pinyon_config.py is the Desktop launcher's settings backend and
tools/set-graphics-experiment.ps1 the Windows launcher's (it must work before
setup provisions Python). Where PowerShell is available, every scenario runs
through both and the written bytes and reported settings must agree.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import pinyon  # noqa: E402
import pinyon_config  # noqa: E402

POWERSHELL = shutil.which("powershell") if os.name == "nt" else None

EDIT_CASES = [
    ("bom_first_setting", "﻿vsync = true\r\ncustom_value = 77\r\n", [("vsync", "false")],
     "vsync = false\r\ncustom_value = 77\r\n"),
    ("replace_lf_indented_comment", "a = 1\n  vsync=true   # keep in sync\nb = 2\n",
     [("vsync", "false")], "a = 1\nvsync = false\nb = 2\n"),
    ("append_crlf", "a = 1\r\nb = 2\r\n\r\n", [("swap_post_effect", '"fxaa"')],
     'a = 1\r\nb = 2\r\nswap_post_effect = "fxaa"\r\n'),
    ("empty_file", "", [("vsync", "true")], "vsync = true\n"),
    ("prefix_name_is_not_a_match", "vsync_other = 1\n", [("vsync", "false")],
     "vsync_other = 1\nvsync = false\n"),
    ("first_of_duplicates", "vsync = true\nvsync = true\n", [("vsync", "false")],
     "vsync = false\nvsync = true\n"),
    ("dollar_in_value", 'keybind_a = "LMB"\n', [("keybind_a", '"$1 Space"')],
     'keybind_a = "$1 Space"\n'),
]

# Each scenario: the starting file (None: no file) and the operations, as
# (action, {option: value}) with the PowerShell parameter names.
SCENARIOS = [
    ("defaults", None, [("Get", {})]),
    ("presets", None, [("Apply", {"ResolutionScale": "3", "OutputScaling": "cas",
                                  "GamePreset": "performance_120"}),
                       ("Apply", {"GamePreset": "balanced_40"}),
                       ("Apply", {"RenderFps": "30"}),
                       ("Apply", {"GamePreset": "ultra_low_30"})]),
    ("migrate", "pinyon_shift_config_schema = 1\nmnk_mode = true\ncustom_value = 77\n"
                "pinyon_shift_fh1_guest_vblank_hz = 60\nreadback_resolve = true\n"
                "fh1_renderer = \"native\"\nocclusion_query = 1\n",
     [("Apply", {"ResolutionScale": "2", "TreasureMap": "false", "Anisotropy": "16",
                 "PostEffect": "fxaa", "DisableBloom": "false", "PresentationFps": "60"})]),
    ("crlf_keeps_in_game_choices", "pinyon_shift_config_schema = 29\r\nvsync = false\r\n"
                                   "user_name = \"Ann\"\r\n",
     [("Apply", {"ResolutionScale": "1", "TreasureMap": "true"}), ("Get", {})]),
    ("reset_then_restore", "pinyon_shift_config_schema = 5\nswap_post_effect = \"fxaa\"\n",
     [("Reset", {}), ("Restore", {})]),
    ("preset_name", "pinyon_shift_config_schema = 29\n",
     [("Apply", {"Preset": "experimental_2x", "ResolutionScale": "4"})]),
]

PYTHON_OPTIONS = {"ResolutionScale": "--resolution-scale", "OutputScaling": "--output-scaling",
                  "GamePreset": "--game-preset", "RenderFps": "--render-fps",
                  "TreasureMap": "--treasure-map", "Anisotropy": "--anisotropy",
                  "PostEffect": "--post-effect", "DisableBloom": "--disable-bloom",
                  "PresentationFps": "--presentation-fps", "Preset": "--preset"}


def run_python(state: Path, action: str, options: dict) -> dict:
    argv = ["config", action.lower(), "--state-root", str(state), "--json"]
    for name, value in options.items():
        argv += [PYTHON_OPTIONS[name], value]
    from contextlib import redirect_stdout
    import io
    out = io.StringIO()
    with redirect_stdout(out):
        code = pinyon.main(argv)
    result = json.loads(out.getvalue().strip().splitlines()[-1])
    assert code == 0, result
    return result


def run_powershell(state: Path, action: str, options: dict) -> dict:
    arguments = []
    for name, value in options.items():
        arguments += [f"-{name}", value]
    completed = subprocess.run(
        [POWERSHELL, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(ROOT / "tools/set-graphics-experiment.ps1"), "-Action", action, "-StateRoot",
         str(state), *arguments, "-Json"], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


class HostConfigRulesTests(unittest.TestCase):
    def test_edits_follow_the_shared_rules(self):
        for name, text, edits, expected in EDIT_CASES:
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "pinyon_shift.toml"
                path.write_bytes(text.encode("utf-8"))
                edited = pinyon_config.read_config(path)
                for key, value in edits:
                    edited = pinyon_config.set_value(edited, key, value)
                pinyon_config.write_config(path, edited)
                self.assertEqual(path.read_bytes().decode("utf-8"), expected)
                self.assertEqual(pinyon_config.get_value(edited, edits[0][0], "<absent>"),
                                 edits[0][1].strip('"'))

    def test_values_read_without_quotes_comments_or_empties(self):
        text = 'a = "x" # note\nb =   \nc=3\n'
        self.assertEqual(pinyon_config.get_value(text, "a", None), "x")
        self.assertEqual(pinyon_config.get_value(text, "b", "default"), "default")
        self.assertEqual(pinyon_config.get_value(text, "c", None), "3")
        self.assertEqual(pinyon_config.remove_value(text, "a"), 'b =   \nc=3\n')

    def test_backups_are_timestamped_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "pinyon_shift.toml"
            self.assertIsNone(pinyon_config.backup_config(path))
            path.parent.mkdir()
            path.write_text("vsync = true\n", encoding="utf-8")
            first = Path(pinyon_config.backup_config(path))
            second = Path(pinyon_config.backup_config(path))
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, path.parent / "backups")
            self.assertRegex(first.name, r"^pinyon_shift-\d{8}T\d{9}Z.*\.toml$")


class ConfigCommandTests(unittest.TestCase):
    def test_treasure_map_off_and_on(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            result = run_python(state, "get", {})
            self.assertTrue(result["settings"]["treasure_map"])
            self.assertEqual(result["result"], "ok")
            from contextlib import redirect_stdout
            import io
            for switch, expected in (("off", False), ("on", True)):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(0, pinyon.main(["config", "treasure-map", switch,
                                                     "--state-root", str(state), "--json"]))
                result = json.loads(out.getvalue())
                self.assertEqual(result["settings"]["treasure_map"], expected)
                self.assertEqual(result["operation"], "apply")
            text = (state / "config/pinyon_shift.toml").read_text(encoding="utf-8")
            self.assertIn("pinyon_shift_dlc_treasure_map = true", text)
            self.assertIn("pinyon_shift_config_schema = 29", text)

    def test_restore_without_a_backup_fails_as_json(self):
        with tempfile.TemporaryDirectory() as directory:
            from contextlib import redirect_stdout
            import io
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(1, pinyon.main(["config", "restore", "--state-root", directory,
                                                 "--json"]))
            self.assertEqual(json.loads(out.getvalue()),
                             {"result": "error", "error": "No runtime-settings backup is available."})

    def test_reset_backs_up_and_restore_brings_the_file_back(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text('pinyon_shift_config_schema = 29\nswap_post_effect = "fxaa"\n',
                              encoding="utf-8")
            reset = run_python(state, "reset", {})
            self.assertTrue(Path(reset["backup_path"]).is_file())
            self.assertEqual(reset["settings"]["post_effect"], "none")
            time.sleep(0.01)
            restored = run_python(state, "restore", {})
            self.assertEqual(restored["settings"]["post_effect"], "fxaa")

    def test_unsupported_schema_is_refused_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            config = state / "config/pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            config.write_text("pinyon_shift_config_schema = 99\n", encoding="utf-8")
            with self.assertRaises(pinyon_config.common.CommandError):
                pinyon_config.run(pinyon.argparse.Namespace(
                    state_root=state, config_command="treasure-map", state="off", json=True))
            self.assertEqual(config.read_text(encoding="utf-8"), "pinyon_shift_config_schema = 99\n")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required for the parity check")
class SettingsParityTests(unittest.TestCase):
    maxDiff = None
    """The Windows launcher's tool and the Desktop launcher's agree."""

    def test_both_tools_write_the_same_file_and_report_the_same_settings(self):
        for name, start, operations in SCENARIOS:
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                states = {tool: Path(directory) / tool for tool in ("powershell", "python")}
                for state in states.values():
                    if start is not None:
                        (state / "config").mkdir(parents=True)
                        (state / "config/pinyon_shift.toml").write_bytes(start.encode("utf-8"))
                    else:
                        state.mkdir()
                for action, options in operations:
                    results = {"powershell": run_powershell(states["powershell"], action, options),
                               "python": run_python(states["python"], action, options)}
                    for result in results.values():
                        result.pop("config_path")
                        result.pop("result", None)
                        # PowerShell reports no backup as "", Python as null.
                        result["backup_path"] = bool(result["backup_path"])
                    self.assertEqual(results["powershell"], results["python"], action)
                    files = [state / "config/pinyon_shift.toml" for state in states.values()]
                    if files[0].is_file() or files[1].is_file():
                        self.assertEqual(files[0].read_bytes(), files[1].read_bytes(), action)
                    time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
