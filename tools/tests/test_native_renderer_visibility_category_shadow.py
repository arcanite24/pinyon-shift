import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-visibility-category-shadow.py"
SPEC = importlib.util.spec_from_file_location("visibility_category_shadow", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VisibilityCategoryShadowReportTests(unittest.TestCase):
    def static(self):
        return {
            "procedural_model_receiver_lifecycle": {
                "visibility_category_shadow": {
                    "input_hook_address": "82E20364",
                    "result_hook_address": "82E20368",
                    "helper_address": "82441048",
                    "plane_vector_offsets": [0, 16, 32, 48, 64, 80],
                    "plane_vector_count": 6,
                    "endpoint_registers": ["v1", "v2"],
                    "axis_signs": [1, 1, -1],
                    "support_rule": (
                        "plane_axis_nonnegative_selects_v2_for_positive"
                    ),
                    "positive_comparison": (
                        "greater_equal_zero_sets_intersection_bit"
                    ),
                    "negative_comparison": "greater_zero_sets_outside_bits",
                    "result_mapping": "bits_3_to_0_bits_1_to_1_other_to_2",
                    "bounded_guest_payload_bytes": 96,
                    "scope": "active_title_record_only",
                    "title_result_comparison_required": True,
                    "guest_payload_read": "bounded_category_planes",
                    "guest_state_changed": False,
                    "control_flow_changed": False,
                    "native_policy_execution": "shadow_only",
                    "native_culling_enabled": False,
                    "native_lod_enabled": False,
                    "xenos_authority": True,
                    "suppression_allowed": False,
                }
            }
        }

    def config(self):
        return {
            "event": MODULE.CONFIG,
            "session": "test",
            "status": "armed",
            "class": "proceduralGeometry::CProceduralModels",
            "visibility_function": "82E1FD00",
            "input_hook": "82E20364",
            "result_hook": "82E20368",
            "helper": "82441048",
            "plane_vector_offsets": "0,16,32,48,64,80",
            "plane_vector_count": "6",
            "endpoint_registers": "v1,v2",
            "axis_signs": "1,1,-1",
            "support_rule": "plane_axis_nonnegative_selects_v2_for_positive",
            "positive_comparison": "greater_equal_zero_sets_intersection_bit",
            "negative_comparison": "greater_zero_sets_outside_bits",
            "result_mapping": "bits_3_to_0_bits_1_to_1_other_to_2",
            "bounded_guest_payload_bytes": "96",
            "scope": "active_title_record_only",
            "classification": "independent_category_helper_shadow",
            "guest_payload_read": "bounded_category_planes",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_policy_execution": "shadow_only",
            "native_culling": "false",
            "native_lod": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }

    def oracle(self, outcome, records, inputs):
        return {
            "event": MODULE.ORACLE_CATEGORY,
            "session": "test",
            "status": "complete",
            "category": "9",
            "outcome": outcome,
            "records": str(records),
            "category_helper_observations": str(inputs),
        }

    def category(self, outcome, records, inputs):
        return {
            "event": MODULE.CATEGORY,
            "session": "test",
            "status": "complete",
            "category": "9",
            "outcome": outcome,
            "records": str(records),
            "input_observations": str(inputs),
            "comparisons": str(inputs),
            "matches": str(inputs),
            "false_result": "0",
            "invalid_inputs": "0",
            "native_policy_execution": "shadow_only",
            "guest_payload_read": "bounded_category_planes",
            "guest_state_changed": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }

    def events(self):
        rows = [("early_rejected", 4, 0), ("rejected", 2, 4), ("selected", 1, 3)]
        summary = {
            "event": MODULE.SUMMARY,
            "session": "test",
            "status": "complete",
            "records": "7",
            "input_observations": "7",
            "comparisons": "7",
            "matches": "7",
            "false_result": "0",
            "invalid_inputs": "0",
            "input_without_record": "2",
            "result_without_input": "0",
            "accounting_complete": "true",
            "model": "six_plane_support_point_classifier",
            "scope": "active_title_record_only",
            "unscoped_continuations_excluded": "true",
            "classification": "independent_category_helper_shadow",
            "guest_payload_read": "bounded_category_planes",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_policy_execution": "shadow_only",
            "native_culling": "false",
            "native_lod": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        return [
            self.config(),
            *(self.oracle(*row) for row in rows),
            *(self.category(*row) for row in rows),
            summary,
        ]

    def test_build_qualifies_exact_category_mirror(self):
        document = MODULE.build(self.events(), self.static())
        self.assertEqual("complete", document["status"])
        self.assertEqual(7, document["totals"]["matches"])
        self.assertTrue(
            document["qualification"][
                "independent_category_classifier_shadow_proved"
            ]
        )
        self.assertFalse(document["safety"]["guest_state_changed"])
        self.assertTrue(document["safety"]["xenos_authority"])

    def test_build_rejects_result_mismatch(self):
        events = copy.deepcopy(self.events())
        category = next(
            event
            for event in events
            if event["event"] == MODULE.CATEGORY
            and event["comparisons"] != "0"
        )
        category["matches"] = "0"
        category["false_result"] = category["comparisons"]
        with self.assertRaisesRegex(ValueError, "comparison failed"):
            MODULE.build(events, self.static())

    def test_build_rejects_static_suppression_drift(self):
        static = self.static()
        static["procedural_model_receiver_lifecycle"][
            "visibility_category_shadow"
        ]["suppression_allowed"] = True
        with self.assertRaisesRegex(ValueError, "contract drifted"):
            MODULE.build(self.events(), static)


if __name__ == "__main__":
    unittest.main()
