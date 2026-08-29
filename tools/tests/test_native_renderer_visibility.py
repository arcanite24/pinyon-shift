import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "summarize-native-renderer-visibility.py"
SPEC = importlib.util.spec_from_file_location("native_renderer_visibility", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def static_contract():
    return {
        "schema": "pinyon-shift.native-renderer-dispatch-static.v3",
        "procedural_model_receiver_lifecycle": {
            "visibility_selection": {
                "record_entry_hook_address": "82E20094",
                "lod_write_hook_addresses": ["82E205E4", "82E206DC"],
                "result_hook_address": "82E206F8",
                "record_exit_hook_address": "82E2084C",
                "receiver_register": "r20",
                "record_index_register": "r16",
                "category_register": "r15",
                "descriptor_register": "r23",
                "runtime_register": "r21",
                "selection_byte_offset": 18,
                "lod_index_offset": 104,
                "title_visibility_authority": True,
                "passive_census_required": True,
                "native_culling_enabled": False,
                "native_lod_enabled": False,
                "guest_payload_read": False,
                "guest_state_changed": False,
                "control_flow_changed": False,
                "xenos_authority": True,
                "suppression_allowed": False,
            }
        },
    }


def events():
    common = {"session": "test-session"}
    return [
        {
            **common,
            "event": MODULE.CONFIG,
            "status": "armed",
            "class": "proceduralGeometry::CProceduralModels",
            "visibility_function": "82E1FD00",
            "record_entry_hook": "82E20094",
            "lod_write_hooks": "82E205E4,82E206DC",
            "result_hook": "82E206F8",
            "record_completion_hook": "82E2084C",
            "record_identity": (
                "receiver_generation,record_index,category,descriptor,runtime"
            ),
            "visibility_result": "runtime_selection_byte_18",
            "lod_selection": "runtime_record_plus_104",
            "category_capacity": "32",
            "lod_capacity": "32",
            "result_value_capacity": "256",
            "classification": (
                "title_authoritative_visibility_and_lod_observation"
            ),
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_culling": "false",
            "native_lod": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.CATEGORY,
            "status": "complete",
            "category": "2",
            "entries": "5",
            "completions": "5",
            "selected": "1",
            "rejected": "1",
            "early_rejected": "3",
            "lod_writes": "0",
            "title_visibility_authority": "true",
            "native_culling": "false",
            "native_lod": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.CATEGORY,
            "status": "complete",
            "category": "9",
            "entries": "5",
            "completions": "5",
            "selected": "3",
            "rejected": "1",
            "early_rejected": "1",
            "lod_writes": "3",
            "title_visibility_authority": "true",
            "native_culling": "false",
            "native_lod": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.LOD,
            "status": "complete",
            "lod_index": "2",
            "writes": "3",
            "source": "title_selected_runtime_record_plus_104",
            "native_lod": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.RESULT_VALUE,
            "status": "complete",
            "selection_value": "0",
            "observations": "2",
            "interpretation": "rejected_zero",
            "native_culling": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.RESULT_VALUE,
            "status": "complete",
            "selection_value": "7",
            "observations": "4",
            "interpretation": "selected_nonzero",
            "native_culling": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": MODULE.SUMMARY,
            "status": "complete",
            "record_entries": "10",
            "record_completions": "10",
            "result_observations": "6",
            "selected_records": "4",
            "rejected_records": "2",
            "early_rejected_records": "4",
            "lod_writes": "3",
            "lod_category_selected_with_lod": "3",
            "lod_category_selected_without_lod": "0",
            "category_overflow": "0",
            "lod_overflow": "0",
            "record_stack_faults": "0",
            "entry_overlaps": "0",
            "lod_without_record": "0",
            "lod_rewrites": "2",
            "result_without_record": "0",
            "duplicate_result": "0",
            "completion_without_record": "0",
            "visibility_exit_with_record": "0",
            "record_identity_mismatches": "0",
            "record_unknown_receivers": "0",
            "record_open_at_shutdown": "0",
            "accounting_complete": "true",
            "classification": (
                "title_authoritative_visibility_and_lod_observation"
            ),
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_culling": "false",
            "native_lod": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
    ]


class NativeRendererVisibilityTests(unittest.TestCase):
    def test_accepts_complete_passive_census(self):
        document = MODULE.build(events(), static_contract())
        self.assertEqual(MODULE.SCHEMA, document["schema"])
        self.assertEqual("complete", document["status"])
        self.assertEqual(4, document["totals"]["selected_records"])
        self.assertEqual(2, document["totals"]["lod_rewrites"])
        self.assertEqual({"2": 3}, document["lod_histogram"])
        self.assertEqual(
            {"0": 2, "7": 4}, document["result_value_histogram"]
        )
        self.assertTrue(
            document["qualification"]["ready_for_native_policy_modeling"]
        )
        self.assertTrue(document["safety"]["xenos_authority"])
        self.assertFalse(document["safety"]["native_culling"])

    def test_rejects_runtime_faults(self):
        broken = events()
        broken[-1]["record_stack_faults"] = "1"
        broken[-1]["duplicate_result"] = "1"
        with self.assertRaisesRegex(ValueError, "aggregate accounting"):
            MODULE.build(broken, static_contract())

    def test_normalizes_legacy_lod_rewrites(self):
        legacy = events()
        legacy[-1].pop("lod_rewrites")
        legacy[-1]["duplicate_lod"] = "2"
        legacy[-1]["record_stack_faults"] = "2"
        legacy[-1]["status"] = "incomplete"
        legacy[-1]["accounting_complete"] = "false"
        document = MODULE.build(legacy, static_contract())
        self.assertEqual(2, document["totals"]["lod_rewrites"])
        self.assertEqual(0, document["totals"]["record_stack_faults"])
        self.assertEqual(
            "legacy_duplicate_lod_normalized_as_rewrite",
            document["qualification"]["capture_model"],
        )

    def test_rejects_native_execution(self):
        broken = events()
        broken[0]["native_lod"] = "true"
        with self.assertRaisesRegex(ValueError, "configuration drifted"):
            MODULE.build(broken, static_contract())

    def test_rejects_static_suppression(self):
        broken = static_contract()
        broken["procedural_model_receiver_lifecycle"]["visibility_selection"][
            "suppression_allowed"
        ] = True
        with self.assertRaisesRegex(ValueError, "static semantic-visibility"):
            MODULE.build(events(), broken)


if __name__ == "__main__":
    unittest.main()
