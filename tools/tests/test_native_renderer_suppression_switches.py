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
                "cvar": "pinyon_shift_native_renderer_sky_horizon_suppression",
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

    def test_reports_diagnostic_control_without_claiming_rollback(self):
        document = manifest()
        document["families"][0]["implementation_status"] = "diagnostic_only"
        result = MODULE.validate(document)
        self.assertEqual(1, result["summary"]["diagnostic_control_count"])
        self.assertEqual("unknown", result["summary"]["rollback_switch_gate"])
        self.assertFalse(result["safety"]["suppression_allowed"])

    def test_rejects_suppression_claim_before_implementation(self):
        document = manifest()
        document["families"][0]["draw_suppression_implemented"] = True
        with self.assertRaisesRegex(ValueError, "before implementation"):
            MODULE.validate(document)

    def test_implemented_switch_requires_runtime_rollback_qualification(self):
        document = manifest()
        family = document["families"][0]
        family["implementation_status"] = "implemented"
        family["draw_suppression_implemented"] = True
        family["rollback_qualified"] = False
        result = MODULE.validate(document)
        self.assertEqual("requires_runtime_test", result["families"][0]["rollback_gate"])
        self.assertEqual("unknown", result["summary"]["rollback_switch_gate"])
        self.assertFalse(result["safety"]["suppression_allowed"])

        family["rollback_qualified"] = True
        result = MODULE.validate(document)
        self.assertEqual("pass", result["summary"]["rollback_switch_gate"])
        self.assertTrue(result["safety"]["suppression_allowed"])

    def test_state_yield_requires_fail_closed_contract_and_qualification(self):
        document = manifest()
        family = document["families"][0]
        family.update(
            {
                "implementation_status": "implemented",
                "draw_suppression_implemented": True,
                "rollback_qualified": True,
                "state_yield_implemented": True,
                "state_yield_qualified": False,
                "state_gate": "consecutive_publication_warmup",
                "warmup_frames": 8,
                "failure_cooldown_frames": 120,
                "gap_behavior": "reset_warmup_and_execute_xenos",
                "failure_behavior": "cooldown_and_execute_xenos",
                "guest_side_effects_preserved": True,
            }
        )
        result = MODULE.validate(document)
        self.assertEqual(
            "requires_runtime_test", result["summary"]["state_based_yield_gate"]
        )
        self.assertIn("state-yield", result["summary"]["reason"])
        self.assertFalse(result["safety"]["suppression_allowed"])

        family["state_yield_qualified"] = True
        result = MODULE.validate(document)
        self.assertEqual("pass", result["summary"]["state_based_yield_gate"])
        self.assertTrue(result["safety"]["suppression_allowed"])

        family["failure_behavior"] = "continue_suppression"
        with self.assertRaisesRegex(ValueError, "yield after publication failure"):
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
