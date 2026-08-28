import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_renderer_pass_follower",
    ROOT / "tools/select-native-renderer-pass-follower.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def follower(signature="FOLLOWER"):
    return {
        "anchor_signature": "ANCHOR",
        "follower_signature": signature,
        "anchor_frame": "10",
        "anchor_draw": "20",
        "follower_frame": "10",
        "follower_draw": "21",
        "query": "false",
        "memexport": "false",
        "resolved_input": "false",
        "suppression_eligible": "false",
        "native_draw": "false",
        "xenos_draw": "preserved",
    }


class PassFollowerTests(unittest.TestCase):
    def write(self, root, name, record):
        path = Path(root) / name
        path.write_text(json.dumps({"pass_followers": [record]}), encoding="utf-8")
        return path

    def test_selects_stable_adjacent_follower(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [self.write(temp, f"run-{i}.json", follower()) for i in range(2)]
            result = MODULE.select(paths, "ANCHOR")
        self.assertEqual("FOLLOWER", result["follower_signature"])
        self.assertEqual(2, result["captures"])
        self.assertTrue(result["safety"]["xenos_authority"])
        self.assertFalse(result["safety"]["suppression_allowed"])

    def test_rejects_contract_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = [
                self.write(temp, "run-1.json", follower()),
                self.write(temp, "run-2.json", follower("DRIFT")),
            ]
            with self.assertRaisesRegex(ValueError, "contract drift"):
                MODULE.select(paths, "ANCHOR")

    def test_requires_draw_adjacency(self):
        record = follower()
        record["follower_draw"] = "22"
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, "run.json", record)
            with self.assertRaisesRegex(ValueError, "draw-adjacent"):
                MODULE.load_capture(path, "ANCHOR")


if __name__ == "__main__":
    unittest.main()
