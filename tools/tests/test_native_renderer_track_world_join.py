import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-track-world-join.py"
SPEC = importlib.util.spec_from_file_location("native_track_world_join", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def ingress():
    return {
        "schema": "pinyon-shift.native-renderer-track-ingress.v1",
        "status": "complete",
        "classification": "title_track_world_ingress_statically_proved",
        "classes": {
            "track_texture_unified": {
                "decorated_name": ".?AVCTrackTexture_Unified@Presentation_Unified@@",
                "vtable_address": "82001708",
                "vtable_slot_count": 14,
            }
        },
        "passive_observation_candidates": {
            "track_texture_unified": [
                {"slot": 6, "target": "824107C8"},
                {"slot": 9, "target": "824108D0"},
                {"slot": 10, "target": "82DF1300"},
                {"slot": 11, "target": "82DF0B40"},
            ]
        },
        "safety": {
            "runtime_hook_enabled": False,
            "native_admission": False,
            "suppression_allowed": False,
            "xenos_authority_required": True,
        },
    }


def submissions():
    return {
        "schema": "pinyon-shift.native-renderer-semantic-submissions.v4",
        "session": "track-session",
        "status": "complete",
        "entries": [
            {
                "key": "0123456789ABCDEF",
                "calls": 12,
                "frames": [10, 30],
                "resources": {
                    "primary_key": "00004C8A",
                    "primary_provider": {
                        "vtable": "82001708",
                        "predicate_24_method": "824107C8",
                        "primary_36_method": "824108D0",
                        "fallback_40_method": "82DF1300",
                        "predicate_44_method": "82DF0B40",
                        "selection": "primary_method_36",
                        "object_source": "provider_method",
                    },
                },
            },
            {
                "key": "1111111111111111",
                "calls": 3,
                "frames": [12, 14],
                "resources": {
                    "primary_key": "00000001",
                    "primary_provider": {"vtable": "8200AAAA"},
                },
            },
        ],
        "safety": {
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }


class NativeRendererTrackWorldJoinTests(unittest.TestCase):
    def test_joins_exact_track_provider_without_native_admission(self):
        report = MODULE.build(ingress(), submissions())
        self.assertEqual("complete", report["status"])
        self.assertEqual(1, report["coverage"]["matched_submission_entries"])
        self.assertEqual(12, report["coverage"]["matched_submission_calls"])
        self.assertEqual(3, report["coverage"]["unmatched_submission_calls"])
        self.assertTrue(
            report["remaining_identity_gap"]["track_texture_ownership_proved"]
        )
        self.assertFalse(
            report["remaining_identity_gap"]["track_model_or_mesh_ownership_proved"]
        )
        self.assertFalse(report["safety"]["native_admission"])
        self.assertFalse(report["safety"]["suppression_allowed"])

    def test_rejects_runtime_provider_method_drift(self):
        sample = submissions()
        sample["entries"][0]["resources"]["primary_provider"][
            "primary_36_method"
        ] = "824108D4"
        report = MODULE.build(ingress(), sample)
        self.assertEqual("incomplete", report["status"])
        self.assertEqual(12, report["coverage"]["method_mismatch_calls"])

    def test_rejects_native_submission_report(self):
        sample = copy.deepcopy(submissions())
        sample["safety"]["native_draw"] = True
        with self.assertRaisesRegex(ValueError, "safety boundary drifted"):
            MODULE.build(ingress(), sample)


if __name__ == "__main__":
    unittest.main()
