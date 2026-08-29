import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-semantic-batches.py"
SPEC = importlib.util.spec_from_file_location("semantic_batches", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def static_inventory():
    return {
        "schema": MODULE.STATIC_SCHEMA,
        "procedural_model_receiver_lifecycle": {
            "semantic_draw_association": {
                "semantic_pm4_packet_construction_proved": True,
                "semantic_pm4_backend_join_required": True,
                "semantic_prepared_contract_runtime_join_required": True,
                "semantic_catalog_classification": (
                    "immutable_template_and_dynamic_resource_instance"
                ),
                "semantic_batch_admission_census_required": True,
                "semantic_batch_ordering": MODULE.EXPECTED_ORDERING,
                "semantic_batch_execution_enabled": False,
                "native_rendering_enabled": False,
                "suppression_eligible": False,
            }
        },
    }


def events():
    common = {"schema": 1, "session": "batch-session"}
    summary = {
        **common,
        "event": MODULE.BATCH_SUMMARY,
        "status": "complete",
        "observations": "12",
        "eligible_draws": "10",
        "rejected_draws": "2",
        "opportunity_entries": "2",
        "opportunity_overflow": "0",
        "consecutive_runs": "4",
        "multi_draw_runs": "2",
        "multi_draw_draws": "8",
        "maximum_run_length": "5",
        "instance_switches": "3",
        "same_instance_continuations": "3",
        "frames": "2",
        "maximum_draws_per_frame": "7",
        "template_transitions": "4",
        "geometry_transitions": "3",
        "texture_transitions": "2",
        "title_resource_transitions": "1",
        "projected_commands": "6",
        "potential_command_reduction": "6",
        "potential_command_reduction_percent": "50.000",
        "accounting_complete": "true",
        "ordering": MODULE.EXPECTED_ORDERING,
        "reordering": "false",
        "native_batch_execution": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    for field in MODULE.REJECTION_FIELDS.values():
        summary[field] = "0"
    summary["reject_non_opaque"] = "2"
    return [
        {
            **common,
            "event": MODULE.TITLE_CONFIG,
            "status": "armed",
            "scene": "open_world",
            "semantic_batch_planner": (
                "exact_consecutive_opaque_prepared_draw_order"
            ),
            "semantic_batch_execution": "disabled_measurement_only",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.BATCH_ENTRY,
            "opportunity_key": "1000000000000001",
            "template_key": "2000000000000001",
            "geometry_resource_hash": "3000000000000001",
            "texture_resource_hash": "4000000000000001",
            "primary_resource_key": "50000001",
            "secondary_resource_present": "false",
            "secondary_resource_key": "00000000",
            "draws": "10",
            "frames": "2",
            "first_frame": "20",
            "last_frame": "21",
            "consecutive_runs": "4",
            "multi_draw_runs": "2",
            "multi_draw_draws": "8",
            "maximum_run_length": "5",
            "instance_switches": "3",
            "same_instance_continuations": "3",
            "eligible": "true",
            "rejection": "none",
            "classification": "conservative_consecutive_batch_candidate",
            "native_batch": "false",
            "xenos_draw": "preserved",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.BATCH_ENTRY,
            "opportunity_key": "1000000000000002",
            "template_key": "2000000000000002",
            "geometry_resource_hash": "3000000000000002",
            "texture_resource_hash": "4000000000000002",
            "primary_resource_key": "50000002",
            "secondary_resource_present": "true",
            "secondary_resource_key": "60000002",
            "draws": "2",
            "frames": "1",
            "first_frame": "21",
            "last_frame": "21",
            "consecutive_runs": "0",
            "multi_draw_runs": "0",
            "multi_draw_draws": "0",
            "maximum_run_length": "0",
            "instance_switches": "0",
            "same_instance_continuations": "0",
            "eligible": "false",
            "rejection": "non_opaque",
            "classification": "xenos_replay_rejected",
            "native_batch": "false",
            "xenos_draw": "preserved",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.TITLE_SUMMARY,
            "semantic_contract_calls": "12",
            "semantic_draw_prepared_matches": "12",
            "semantic_draw_unprepared_matches": "0",
        },
        summary,
    ]


class SemanticBatchTests(unittest.TestCase):
    def test_builds_fail_closed_in_order_batch_plan(self):
        document = MODULE.build(events(), static_inventory())
        self.assertEqual("complete", document["status"])
        self.assertTrue(document["conservative_batch_plan_proved"])
        self.assertFalse(document["execution_admitted"])
        self.assertEqual(10, document["totals"]["eligible_draws"])
        self.assertEqual(6, document["totals"]["potential_command_reduction"])
        self.assertEqual(2, document["rejections"]["non_opaque"])
        self.assertFalse(document["safety"]["native_batch_execution"])
        self.assertTrue(document["safety"]["xenos_authority"])

    def test_rejects_duplicate_opportunity_key(self):
        observed = events()
        observed.insert(3, copy.deepcopy(observed[1]))
        observed[-1]["opportunity_entries"] = "3"
        with self.assertRaisesRegex(ValueError, "duplicate or zero"):
            MODULE.build(observed, static_inventory())

    def test_rejects_unsafe_runtime_summary(self):
        observed = events()
        observed[-1]["native_batch_execution"] = "true"
        with self.assertRaisesRegex(ValueError, "incomplete or unsafe"):
            MODULE.build(observed, static_inventory())

    def test_rejects_aggregate_drift(self):
        observed = events()
        observed[-1]["potential_command_reduction"] = "5"
        with self.assertRaisesRegex(ValueError, "aggregate accounting"):
            MODULE.build(observed, static_inventory())

    def test_requires_static_admission_contract(self):
        static = static_inventory()
        static["procedural_model_receiver_lifecycle"][
            "semantic_draw_association"
        ]["semantic_batch_execution_enabled"] = True
        with self.assertRaisesRegex(ValueError, "static contract"):
            MODULE.build(events(), static)


if __name__ == "__main__":
    unittest.main()
