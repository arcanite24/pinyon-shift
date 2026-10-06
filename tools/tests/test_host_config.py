"""The launcher's and the game's host-configuration writers must agree.

tools/host-config.ps1 (used by the launcher's tools) and
src/config/host_config.cpp (used by the in-game settings screen) follow the
same editing rules. Each case applies the same edits with both and compares
the written bytes and the values read back.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell")
NATIVE = ROOT / "out/build/win-amd64-release/pinyon_shift_host_config_tests.exe"

CASES = [
    ("bom_first_setting", "\ufeffvsync = true\r\ncustom_value = 77\r\n", [("vsync", "false")]),
    ("replace_crlf", "pinyon_shift_config_schema = 25\r\nvsync = true\r\nmnk_mode = true\r\n",
     [("vsync", "false")]),
    ("replace_lf_indented_comment", "a = 1\n  vsync=true   # keep in sync\nb = 2\n",
     [("vsync", "false")]),
    ("keeps_blank_lines", "a = 1\r\n\r\n\r\nvsync = true\r\n", [("vsync", "false")]),
    ("append_crlf", "a = 1\r\nb = 2\r\n\r\n", [("swap_post_effect", '"fxaa"')]),
    ("append_lf", "a = 1\n", [("host_present_fps_limit", "60")]),
    ("empty_file", "", [("vsync", "true")]),
    ("prefix_name_is_not_a_match", "vsync_other = 1\n", [("vsync", "false")]),
    ("first_of_duplicates", "vsync = true\nvsync = true\n", [("vsync", "false")]),
    ("dollar_in_value", "keybind_a = \"LMB\"\n", [("keybind_a", '"$1 Space"')]),
    ("several", "pinyon_shift_config_schema = 25\r\ndraw_resolution_scale_x = 1\r\n",
     [("draw_resolution_scale_x", "2"), ("draw_resolution_scale_y", "2"),
      ("anisotropic_override", "5")]),
]

POWERSHELL_DRIVER = r"""
param([string]$Cases)
. (Join-Path '{tools}' 'host-config.ps1')
foreach ($case in (Get-Content -LiteralPath $Cases -Raw | ConvertFrom-Json)) {{
    $text = [IO.File]::ReadAllText($case.path)
    foreach ($edit in $case.edits) {{ $text = Set-TomlValue $text $edit[0] $edit[1] }}
    Write-HostConfig $case.path $text
    $values = @{{}}
    foreach ($edit in $case.edits) {{ $values[$edit[0]] = Get-TomlValue $text $edit[0] '<absent>' }}
    [IO.File]::WriteAllText($case.path + '.values', ($values | ConvertTo-Json -Compress))
}}
"""


@unittest.skipUnless(POWERSHELL, "PowerShell is not available")
@unittest.skipUnless(NATIVE.is_file(), "pinyon_shift_host_config_tests is not built")
class HostConfigWritersAgreeTests(unittest.TestCase):
    def test_both_writers_produce_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = []
            for name, text, edits in CASES:
                for writer in ("powershell", "native"):
                    path = root / writer / name / "pinyon_shift.toml"
                    path.parent.mkdir(parents=True)
                    path.write_bytes(text.encode("utf-8"))
                cases.append({"path": str(root / "powershell" / name / "pinyon_shift.toml"),
                              "edits": [list(edit) for edit in edits]})
            (root / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
            driver = root / "driver.ps1"
            driver.write_text(POWERSHELL_DRIVER.format(tools=ROOT / "tools"), encoding="utf-8")
            subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            str(driver), "-Cases", str(root / "cases.json")],
                           check=True, capture_output=True, text=True)
            for name, _, edits in CASES:
                native = root / "native" / name / "pinyon_shift.toml"
                arguments = [str(NATIVE), "--set", str(native)]
                for setting, literal in edits:
                    arguments += [setting, literal]
                subprocess.run(arguments, check=True)
                powershell = root / "powershell" / name / "pinyon_shift.toml"
                with self.subTest(case=name):
                    self.assertEqual(powershell.read_bytes(), native.read_bytes())
                    values = json.loads((powershell.parent / "pinyon_shift.toml.values")
                                        .read_text(encoding="utf-8-sig"))
                    for setting, _ in edits:
                        read = subprocess.run([str(NATIVE), "--get", str(native), setting],
                                              check=True, capture_output=True, text=True).stdout
                        self.assertEqual(values[setting], read)

    def test_launcher_reads_what_the_game_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            str(ROOT / "tools/set-graphics-experiment.ps1"), "-Action", "Reset",
                            "-StateRoot", str(state)], check=True, capture_output=True)
            config = state / "config" / "pinyon_shift.toml"
            subprocess.run([str(NATIVE), "--set", str(config),
                            "anisotropic_override", "5",
                            "swap_post_effect", '"fxaa"',
                            "disable_motion_blur", "true",
                            "draw_resolution_scale_x", "2", "draw_resolution_scale_y", "2",
                            "host_present_fps_limit", "120"], check=True)
            result = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", str(ROOT / "tools/set-graphics-experiment.ps1"),
                                     "-Action", "Get", "-StateRoot", str(state), "-Json"],
                                    check=True, capture_output=True, text=True)
            settings = json.loads(result.stdout)["settings"]
            self.assertEqual(16, settings["anisotropy"])
            self.assertEqual("fxaa", settings["post_effect"])
            self.assertTrue(settings["disable_motion_blur"])
            self.assertEqual(2, settings["resolution_scale"])
            self.assertEqual(120, settings["host_present_fps_limit"])


if __name__ == "__main__":
    unittest.main()
