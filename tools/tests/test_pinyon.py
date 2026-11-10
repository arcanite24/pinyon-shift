import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "pinyon.py"
SPEC = importlib.util.spec_from_file_location("pinyon", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PinyonLauncherTests(unittest.TestCase):
    def test_setup_starts_without_tomllib(self):
        # Simulate the system Python on macOS before setup provisions Python.
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "sitecustomize.py").write_text(
                "import sys\n"
                "class NoTomllib:\n"
                "    def find_spec(self, fullname, path=None, target=None):\n"
                "        if fullname == 'tomllib':\n"
                "            raise ModuleNotFoundError(\"No module named 'tomllib'\")\n"
                "sys.meta_path.insert(0, NoTomllib())\n", encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": directory}
            result = subprocess.run([sys.executable, str(MODULE_PATH), "setup", "--help"],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("usage:", result.stdout)

    def test_mods_explains_that_setup_needs_to_run_on_old_python(self):
        with mock.patch.object(MODULE.pinyon_mods.sys, "version_info", (3, 9)):
            with self.assertRaisesRegex(MODULE.pinyon_common.CommandError, "run setup first"):
                MODULE.pinyon_mods.run(None)

    def test_default_build_directory_follows_the_host(self):
        with mock.patch.object(MODULE, "WINDOWS", False), \
                mock.patch.object(MODULE.platform, "system", return_value="Linux"), \
                mock.patch.object(MODULE.platform, "machine", return_value="aarch64"):
            self.assertEqual(MODULE.ROOT / "out" / "build" / "linux-arm64-release",
                             MODULE.default_build_directory("Release"))
        with mock.patch.object(MODULE, "WINDOWS", True), \
                mock.patch.object(MODULE.platform, "machine", return_value="AMD64"):
            self.assertEqual(MODULE.ROOT / "out" / "build" / "win-amd64-relwithdebinfo",
                             MODULE.default_build_directory("RelWithDebInfo"))

    def test_refuses_a_missing_build_or_game(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(1, MODULE.main(["launch", "--build-directory", str(root / "build"),
                                                 "--game-root", str(root / "game"),
                                                 "--state-root", str(root / "state")]))
            self.assertIn("not built", stderr.getvalue())
            (root / "build").mkdir()
            (root / "build" / MODULE.EXECUTABLE).write_bytes(b"")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(1, MODULE.main(["launch", "--build-directory", str(root / "build"),
                                                 "--game-root", str(root / "game"),
                                                 "--state-root", str(root / "state")]))
            self.assertIn("game files are missing", stderr.getvalue())
            self.assertFalse((root / "state").exists())

    def test_prepares_the_state_and_drops_a_pending_report(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            (state / "reports").mkdir(parents=True)
            (state / "reports" / "pending-report.json").write_text("{}", encoding="utf-8")
            MODULE.prepare_state(state)
            for name in MODULE.STATE_DIRECTORIES:
                self.assertTrue((state / name).is_dir())
            self.assertFalse((state / "reports" / "pending-report.json").exists())

    def test_game_arguments_follow_a_double_dash(self):
        parser_args = ["launch", "--hidden", "--", "--gpu_backend=vulkan", "--fh1_frame_dump_frame=9"]
        with mock.patch.object(MODULE, "launch", return_value={"result": "normal-exit"}) as launch:
            with redirect_stderr(io.StringIO()), mock.patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(0, MODULE.main(parser_args))
        args = launch.call_args[0][0]
        self.assertTrue(args.hidden)
        self.assertEqual(["--gpu_backend=vulkan", "--fh1_frame_dump_frame=9"], args.game_arguments)


if __name__ == "__main__":
    unittest.main()
