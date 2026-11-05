import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "experiment", Path(__file__).parents[1] / "check-recomp-experiment.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


class ExperimentIsolationTests(unittest.TestCase):
    def test_rejects_preset_path_reset_and_codegen(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            snapshot = build / "snapshot"
            command = {"file": str(snapshot / "pinyon_shift_recomp.0.cpp"),
                       "command": "clang++ -msse4.1 -fasync-exceptions -flto=thin"}
            commands = build / "compile_commands.json"
            commands.write_text(json.dumps([command]))
            ninja = build / "build.ninja"
            ninja.write_text("# frozen")
            self.assertEqual(experiment.check(build, snapshot, True), 1)
            with self.assertRaisesRegex(ValueError, "PGO mode"):
                experiment.check(build, snapshot, True, "generate")
            command["command"] += " -fprofile-generate -fprofile-update=atomic"
            commands.write_text(json.dumps([command]))
            self.assertEqual(experiment.check(build, snapshot, True, "generate"), 1)
            with self.assertRaisesRegex(ValueError, "PGO mode"):
                experiment.check(build, snapshot, True, "use")
            command["command"] = command["command"].replace(
                " -fprofile-generate -fprofile-update=atomic", "")
            commands.write_text(json.dumps([command]))
            with self.assertRaisesRegex(ValueError, "ThinLTO"):
                experiment.check(build, snapshot, False)
            command["file"] = str(build / "original" / "pinyon_shift_recomp.0.cpp")
            commands.write_text(json.dumps([command]))
            with self.assertRaisesRegex(ValueError, "escaped snapshot"):
                experiment.check(build, snapshot, True)
            command["file"] = str(snapshot / "pinyon_shift_recomp.0.cpp")
            commands.write_text(json.dumps([command]))
            ninja.write_text("Generating dependency-tracked recompiled code for Pinyon Shift")
            with self.assertRaisesRegex(ValueError, "invoke codegen"):
                experiment.check(build, snapshot, True)


if __name__ == "__main__":
    unittest.main()
