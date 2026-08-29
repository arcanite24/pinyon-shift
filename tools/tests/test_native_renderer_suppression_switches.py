import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_renderer_suppression_switches",
    ROOT / "tools/validate-native-renderer-suppression-switches.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def manifest():
    return {
        "schema": MODULE.INPUT_SCHEMA,
        "families": [
            {
                "family": "sky_horizon",
                "anchor_signature": "747837906D0BF484",
                "follower_signature": "1D253A52B55C9FB3",
                "switch": "native_renderer.sky_horizon_suppression",
                "scope": "exact_pass_family",
                "activation": "startup_only",
                "default_enabled": False,
                "independent": True,
                "implementation_status": "absent",
                "draw_suppression_implemented": False,
                "resolve_suppression_implemented": False,
                "xenos_fallback": "mandatory",
            }
        ],
    }


class NativeRendererSuppressionSwitchTests(unittest.TestCase):
    def test_validates_default_off_absent_switch(self):
        result = MODULE.validate(manifest())
        self.assertEqual("unknown", result["summary"]["rollback_switch_gate"])
        self.assertEqual(0, result["summary"]["implemented_count"])
        self.assertFalse(result["safety"]["suppression_allowed"])
        self.assertTrue(result["safety"]["xenos_authority"])

    def test_rejects_default_on_switch(self):
        document = manifest()
        document["families"][0]["default_enabled"] = True
        with self.assertRaisesRegex(ValueError, "default off"):
            MODULE.validate(document)

    def test_rejects_suppression_claim_before_implementation(self):
        document = manifest()
        document["families"][0]["draw_suppression_implemented"] = True
        with self.assertRaisesRegex(ValueError, "before implementation"):
            MODULE.validate(document)

    def test_rejects_duplicate_switch(self):
        document = manifest()
        duplicate = copy.deepcopy(document["families"][0])
        duplicate["family"] = "other"
        duplicate["anchor_signature"] = "AAAAAAAAAAAAAAAA"
        duplicate["follower_signature"] = "BBBBBBBBBBBBBBBB"
        document["families"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate switch"):
            MODULE.validate(document)


if __name__ == "__main__":
    unittest.main()
