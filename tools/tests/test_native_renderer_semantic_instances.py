import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-semantic-instances.py"
SPEC = importlib.util.spec_from_file_location("semantic_instances", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def static_inventory():
    return {
        "schema": "pinyon-shift.native-renderer-dispatch-static.v3",
        "procedural_model_receiver_lifecycle": {
            "rtti_vtable_identity_proved": True,
            "semantic_instance_extraction": {
                "argument_mapping_proved": True,
                "record_address_derivation_proved": True,
                "hook_address": "8241741C",
                "bounded_payload_bytes_per_observation": 380,
                "native_rendering_enabled": False,
                "suppression_eligible": False,
            },
        },
    }


def events():
    common = {"session": "semantic-session"}
    safety = {
        "fallback": "xenos_replay",
        "guest_payload_read": "bounded_semantic_records_only",
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    return [
        {
            **common,
            "event": "native_renderer.discovery.semantic_instance_config",
            "status": "armed",
        },
        {
            **common,
            **safety,
            "event": "native_renderer.discovery.semantic_instance_entry",
            "class": "proceduralGeometry::CProceduralModels",
            "key": "0123456789ABCDEF",
            "calls": "12",
            "first_frame": "10",
            "last_frame": "30",
            "receiver_address": "10000000",
            "receiver_generation": "2",
            "record_index": "3",
            "descriptor_count": "8",
            "descriptor_address": "20000114",
            "runtime_address": "300000CC",
            "descriptor_kind": "4",
            "active_buffer_index": "1",
            "per_record_resource_capacity": "8",
            "helper_arguments": "00000001,00000002,00000003,00000004,00000005,00000006,00000007",
            "descriptor_hash": "1111111111111111",
            "runtime_hash": "2222222222222222",
            "transform_hash": "3333333333333333",
            "descriptor_variations": "0",
            "runtime_variations": "2",
            "transform_variations": "1",
            "immutable_sample_words": "88",
            "classification": "unclassified_material_or_state",
        },
        {
            **common,
            **safety,
            "event": "native_renderer.discovery.semantic_instance_summary",
            "observations": "12",
            "live_observations": "12",
            "unknown_receivers": "0",
            "invalid_layouts": "0",
            "invalid_indices": "0",
            "payload_bytes": "4560",
            "replay_fallbacks": "12",
            "native_admissions": "0",
            "entries": "1",
            "capacity": "4096",
            "overflow": "0",
            "payload_bytes_per_live_observation": "380",
        },
    ]


class SemanticInstanceTests(unittest.TestCase):
    def test_complete_bounded_fallback_report(self):
        report = MODULE.build(events(), static_inventory())
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["totals"]["live_observations"], 12)
        self.assertEqual(report["entries"][0]["record_index"], 3)
        self.assertFalse(report["safety"]["suppression_allowed"])

    def test_unknown_receiver_keeps_report_incomplete(self):
        sample = copy.deepcopy(events())
        sample[-1]["observations"] = "13"
        sample[-1]["unknown_receivers"] = "1"
        report = MODULE.build(sample, static_inventory())
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("unknown_receivers is nonzero", report["failures"])

    def test_native_admission_is_rejected(self):
        sample = copy.deepcopy(events())
        sample[-1]["native_admissions"] = "1"
        report = MODULE.build(sample, static_inventory())
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("native_admissions is nonzero", report["failures"])

    def test_suppression_claim_is_rejected(self):
        sample = copy.deepcopy(events())
        sample[1]["suppression_allowed"] = "true"
        with self.assertRaisesRegex(ValueError, "safety boundary"):
            MODULE.build(sample, static_inventory())

    def test_record_index_must_be_in_descriptor_range(self):
        sample = copy.deepcopy(events())
        sample[1]["record_index"] = "8"
        with self.assertRaisesRegex(ValueError, "immutable evidence"):
            MODULE.build(sample, static_inventory())


if __name__ == "__main__":
    unittest.main()
