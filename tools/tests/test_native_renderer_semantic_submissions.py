import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-semantic-submissions.py"
SPEC = importlib.util.spec_from_file_location("semantic_submissions", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def static_inventory():
    return {
        "schema": "pinyon-shift.native-renderer-dispatch-static.v3",
        "procedural_model_receiver_lifecycle": {
            "rtti_vtable_identity_proved": True,
            "semantic_submission_extraction": {
                "primary_resource_binding_hook_address": "82417A74",
                "secondary_resource_binding_hook_address": "82417A9C",
                "resource_resolution_result_hook_address": "82415C50",
                "resource_bind_dispatch_hook_address": "82415C6C",
                "geometry_submission_hook_address": "82417B60",
                "resource_binding_helper_function_address": "82415BF8",
                "resource_binding_slots": [0, 1],
                "graphics_submission_primitive": 13,
                "graphics_submission_count_scale": 4,
                "resource_binding_derivation_proved": True,
                "resolved_resource_object_derivation_proved": True,
                "record_join_proved": True,
                "geometry_submission_derivation_proved": True,
                "descriptor_kind_partition_proved": True,
                "helper_state_partition_proved": True,
                "classification": "resolved_resource_and_state_variant_submission",
                "native_rendering_enabled": False,
                "suppression_eligible": False,
            },
        },
    }


def events():
    common = {"session": "submission-session"}
    safety = {
        "fallback": "xenos_replay",
        "guest_payload_read": "bounded_submission_fields_only",
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    return [
        {
            **common,
            "event": "native_renderer.discovery.semantic_submission_config",
            "status": "armed",
        },
        {
            **common,
            **safety,
            "event": "native_renderer.discovery.semantic_submission_entry",
            "class": "proceduralGeometry::CProceduralModels",
            "key": "0123456789ABCDEF",
            "calls": "12",
            "first_frame": "10",
            "last_frame": "30",
            "receiver_address": "10000000",
            "receiver_generation": "2",
            "record_index": "3",
            "descriptor_kind": "4",
            "helper_state": "7",
            "graphics_context": "20000000",
            "resource_lookup_context": "30000000",
            "primary_resource_index": "9",
            "primary_resource_key": "40000000",
            "primary_bound_resource_object": "41000000",
            "secondary_resource_present": "true",
            "secondary_resource_index": "10",
            "secondary_resource_key": "50000000",
            "secondary_bound_resource_object": "51000000",
            "runtime_submission_object": "60000000",
            "primitive_type": "13",
            "count_units": "16",
            "count_bytes": "64",
            "source_address": "70000000",
            "source_contract": "runtime_record_28_32",
            "descriptor_kind_group": "kind_4_5",
            "helper_state_family": "state_6_8_table_100_124",
            "classification": "resolved_resource_and_state_variant_submission",
        },
        {
            **common,
            **safety,
            "event": "native_renderer.discovery.semantic_submission_summary",
            "observations": "12",
            "live_observations": "12",
            "unknown_receivers": "0",
            "binding_mismatches": "0",
            "invalid_record_joins": "0",
            "invalid_resource_joins": "0",
            "unresolved_resource_joins": "0",
            "invalid_geometry": "0",
            "primary_binding_observations": "12",
            "secondary_binding_observations": "12",
            "resource_resolution_attempts": "2",
            "resource_resolution_successes": "2",
            "resource_resolution_misses": "0",
            "resource_resolution_cache_hits": "22",
            "resource_bind_dispatches": "2",
            "resource_resolution_protocol_faults": "0",
            "payload_bytes": "672",
            "maximum_payload_bytes_per_live_observation": "56",
            "replay_fallbacks": "12",
            "native_admissions": "0",
            "entries": "1",
            "capacity": "8192",
            "overflow": "0",
            "classification": "resolved_resource_and_state_variant_submission",
        },
    ]


class SemanticSubmissionTests(unittest.TestCase):
    def test_complete_structural_fallback_report(self):
        report = MODULE.build(events(), static_inventory())
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["coverage"]["source_contracts"], {"runtime_record_28_32": 12})
        self.assertEqual(report["coverage"]["descriptor_kind_groups"], {"kind_4_5": 12})
        self.assertEqual(
            report["coverage"]["helper_state_families"],
            {"state_6_8_table_100_124": 12},
        )
        self.assertEqual(report["entries"][0]["resources"]["secondary_index"], 10)
        self.assertEqual(
            report["entries"][0]["resources"]["primary_bound_object"],
            "41000000",
        )
        self.assertFalse(report["safety"]["suppression_allowed"])

    def test_binding_mismatch_keeps_report_incomplete(self):
        sample = copy.deepcopy(events())
        sample[-1]["observations"] = "13"
        sample[-1]["binding_mismatches"] = "1"
        sample[-1]["primary_binding_observations"] = "13"
        report = MODULE.build(sample, static_inventory())
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("binding_mismatches is nonzero", report["failures"])

    def test_count_scale_is_enforced(self):
        sample = copy.deepcopy(events())
        sample[1]["count_bytes"] = "63"
        with self.assertRaisesRegex(ValueError, "structural evidence"):
            MODULE.build(sample, static_inventory())

    def test_payload_accounting_is_enforced(self):
        sample = copy.deepcopy(events())
        sample[-1]["payload_bytes"] = "671"
        report = MODULE.build(sample, static_inventory())
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("payload accounting is inconsistent", report["failures"])

    def test_secondary_resource_presence_is_enforced(self):
        sample = copy.deepcopy(events())
        sample[1]["secondary_resource_index"] = "-1"
        with self.assertRaisesRegex(ValueError, "presence is inconsistent"):
            MODULE.build(sample, static_inventory())

    def test_native_admission_is_rejected(self):
        sample = copy.deepcopy(events())
        sample[-1]["native_admissions"] = "1"
        report = MODULE.build(sample, static_inventory())
        self.assertEqual(report["status"], "incomplete")
        self.assertIn("native_admissions is nonzero", report["failures"])

    def test_state_family_must_match_the_proved_partition(self):
        sample = copy.deepcopy(events())
        sample[1]["helper_state_family"] = "default_table_52_76"
        with self.assertRaisesRegex(ValueError, "structural evidence"):
            MODULE.build(sample, static_inventory())

    def test_resource_resolution_protocol_fault_is_rejected(self):
        sample = copy.deepcopy(events())
        sample[-1]["resource_resolution_protocol_faults"] = "1"
        report = MODULE.build(sample, static_inventory())
        self.assertEqual(report["status"], "incomplete")
        self.assertIn(
            "resource_resolution_protocol_faults is nonzero", report["failures"]
        )

    def test_suppression_claim_is_rejected(self):
        sample = copy.deepcopy(events())
        sample[1]["suppression_allowed"] = "true"
        with self.assertRaisesRegex(ValueError, "safety boundary"):
            MODULE.build(sample, static_inventory())


if __name__ == "__main__":
    unittest.main()
