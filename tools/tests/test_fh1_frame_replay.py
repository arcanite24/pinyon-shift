import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "replay-fh1-frame.py"
SPEC = importlib.util.spec_from_file_location("fh1_frame_replay", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReplayFailureTests(unittest.TestCase):
    def test_failed_process_does_not_publish_a_golden_from_its_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dump = root / "input.fh1frame"
            dump.write_bytes(b"test dump")
            golden = Path(f"{dump}.native.golden.bin")
            golden.write_bytes(b"previous golden")
            args = argparse.Namespace(
                dump=dump, work=root / "work", state_root=root / "seed",
                shader_pack=None, game_argument=[], configuration=None,
                build_directory=None, game_root=None, hidden=False, timeout=1,
                max_differing_words=None, write_golden=True,
            )

            def failed_replay(command, **kwargs):
                Path(f"{dump}.replay.json").write_text(json.dumps({
                    "executed": True, "readback": True, "differing_words": 0,
                }))
                Path(f"{dump}.replay.bin").write_bytes(b"unqualified output")
                return subprocess.CompletedProcess(command, 1, "", "capture failed")

            with mock.patch.object(MODULE, "load_runner"), mock.patch.object(
                    MODULE.subprocess, "run", side_effect=failed_replay):
                result = MODULE.replay(args)
            self.assertEqual(result["failure"], "replay process exited with code 1")
            self.assertEqual(golden.read_bytes(), b"previous golden")


if __name__ == "__main__":
    unittest.main()
