"""Startup failures players can fix themselves are not crash reports.

A config the F4 settings overlay rewrote without its schema line stopped
every later start with exit 1306 (#345, #364, #387, #396, #398), and a GPU
without Vulkan 1.3 exited 1, which the launcher filed as a crash (#402, #404,
#405). These pin the repair and the explained exit.
"""

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class ConfigRepairTests(unittest.TestCase):
    def test_the_overlay_merges_into_the_file(self):
        cvar = read("thirdparty/shiftglue-sdk/src/core/cvar.cpp")
        save = cvar[cvar.index("void SaveConfig("):]
        save = save[:save.index("\n}\n")]
        self.assertIn("MergeIntoTOML(existing)", save)
        self.assertNotIn("SerializeToTOML()", save)
        self.assertIn("std::filesystem::rename(temporary, config_path)", save)

    def test_a_config_without_a_schema_is_repaired_and_kept(self):
        app = read("src/pinyon_shift_app.cpp")
        check = app[app.index("bool EnsureSupportedConfig("):]
        missing = check[check.index("if (!std::regex_search(config_text, match, schema_pattern)"):]
        missing = missing[:missing.index("  try {")]
        self.assertIn('".noschema.bak"', missing)
        self.assertIn("WriteAtomically(path, repaired)", missing)
        self.assertIn("migrated = true;", missing)
        # A schema line the pattern cannot read is still refused.
        self.assertIn("return false;", missing)


class GraphicsUnavailableTests(unittest.TestCase):
    def test_the_game_explains_and_exits_1308(self):
        app = read("src/pinyon_shift_app.cpp")
        setup = app[app.index("bool PinyonShiftApp::SetupPresentation()"):]
        setup = setup[:setup.index("\n}\n")]
        self.assertIn('"graphics.unavailable"', setup)
        self.assertIn("Vulkan 1.3", setup)
        self.assertIn("ExitImmediately(1308)", setup)
        self.assertIn("bool SetupPresentation() override;", read("src/pinyon_shift_app.h"))

    def test_the_watcher_does_not_file_a_crash_report(self):
        launch = read("tools/launch-preview.ps1")
        self.assertLess(launch.index("$exitCode -eq 1308"), launch.index("create-crash-report.ps1"))
        self.assertIn("result = 'graphics-unavailable'", launch)

    def test_the_launcher_points_at_the_driver(self):
        window = read("launcher/PinyonShift.Launcher/MainWindow.xaml.cs")
        handled = window.index('"graphics-unavailable"')
        self.assertLess(handled, window.index("DetectPendingReport();", handled))
        self.assertIn('SetFailure("Update the graphics driver"', window)


if __name__ == "__main__":
    unittest.main()
