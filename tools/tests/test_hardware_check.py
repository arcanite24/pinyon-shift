import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "launcher/PinyonShift.Launcher/HardwareCheck.cs"
GAME = ROOT / "src/pinyon_shift_app.cpp"
TOOL = ROOT / "tools/set-graphics-experiment.ps1"
MENU = ROOT / "src/ui/settings_menu.cpp"


class HardwareCheckContractTests(unittest.TestCase):
    """The launcher recommends what the game picks for a new config (LS-1.7)."""

    def test_launcher_thresholds_match_the_first_run_rule(self):
        launcher = LAUNCHER.read_text(encoding="utf-8")
        game = GAME.read_text(encoding="utf-8")
        self.assertIn("CapableDeviceLocalBytes = 6UL << 30", launcher)
        self.assertIn("device_local >= (uint64_t(6) << 30)", game)
        self.assertIn("CapableLogicalProcessors = 6", launcher)
        self.assertIn("cores >= 6", game)
        self.assertIn("CapableRefreshHz = 119", launcher)
        self.assertIn("refresh >= 119.0", game)
        self.assertIn("VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU", game)

    def test_recommended_presets_exist_in_the_tool_and_the_game(self):
        launcher = LAUNCHER.read_text(encoding="utf-8")
        tool = TOOL.read_text(encoding="utf-8")
        menu = MENU.read_text(encoding="utf-8")
        presets = set(re.findall(r'new Recommendation\("([a-z0-9_]+)"', launcher))
        self.assertEqual(presets, {"performance_120", "balanced_40", "low_spec_60"})
        for preset in presets:
            self.assertIn(f"'{preset}'", tool)
            self.assertIn(preset.upper().replace("_", " ").replace("LOW SPEC", "LOW-SPEC"), menu)


if __name__ == "__main__":
    unittest.main()
