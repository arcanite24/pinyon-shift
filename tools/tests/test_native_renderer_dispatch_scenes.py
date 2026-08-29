import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-dispatch-scenes.py"
SPEC = importlib.util.spec_from_file_location("native_dispatch_scenes", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def report(session, scene, callers):
    return {
        "schema": MODULE.RUNTIME_SCHEMA,
        "session": session,
        "scene": scene,
        "callers": [
            {
                "wrapper": "draw_adapter",
                "wrapper_address": "824079B8",
                "caller": caller,
                "calls": calls,
            }
            for caller, calls in callers
        ],
        "safety": {
            "metadata_only": True,
            "guest_payload_read": False,
            "guest_state_changed": False,
            "control_flow_changed": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


class NativeRendererDispatchSceneTests(unittest.TestCase):
    def test_requires_repeated_scene_evidence_and_retains_unknowns(self):
        reports = [
            report("ow-a", "open_world", [("AAA00004", 10), ("CCC00004", 5)]),
            report("ow-b", "open_world", [("AAA00004", 12), ("CCC00004", 6)]),
            report("g-a", "garage", [("BBB00004", 4), ("CCC00004", 2)]),
            report("g-b", "garage", [("BBB00004", 5), ("CCC00004", 3)]),
        ]
        document = MODULE.build(reports)
        by_caller = {item["caller"]: item for item in document["families"]}
        self.assertEqual(
            by_caller["AAA00004"]["candidate_status"],
            "stable_scene_candidate",
        )
        self.assertEqual(by_caller["AAA00004"]["stable_scenes"], ["open_world"])
        self.assertEqual(
            by_caller["CCC00004"]["candidate_status"],
            "stable_multi_scene_candidate",
        )
        self.assertEqual(by_caller["AAA00004"]["semantic_identity"], "unknown")
        self.assertFalse(by_caller["AAA00004"]["promotion_eligible"])
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_rejects_unsafe_or_duplicate_sessions(self):
        unsafe = report("one", "garage", [("AAA00004", 1)])
        unsafe["safety"]["suppression_allowed"] = True
        with self.assertRaisesRegex(ValueError, "passive safety"):
            MODULE.build([unsafe])
        duplicate = report("one", "garage", [("AAA00004", 1)])
        with self.assertRaisesRegex(ValueError, "unique"):
            MODULE.build([duplicate, duplicate])

    def test_refuses_single_session_promotion(self):
        document = MODULE.build(
            [report("one", "race", [("AAA00004", 7)])]
        )
        self.assertEqual(
            document["families"][0]["candidate_status"],
            "insufficient_repeats",
        )
        self.assertFalse(document["families"][0]["promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
