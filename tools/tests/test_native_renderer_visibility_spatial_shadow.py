import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = (
    ROOT / "tools" / "summarize-native-renderer-visibility-spatial-shadow.py"
)
SPEC = importlib.util.spec_from_file_location("visibility_spatial_shadow", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VisibilitySpatialShadowReportTests(unittest.TestCase):
    def static(self):
        return {
            "procedural_model_receiver_lifecycle": {
                "visibility_spatial_shadow": {
                    "input_hook_address": "82E2034C",
                    "result_hook_address": "82E20350",
                    "helper_address": "8243F9A0",
                    "distance_helper_address": "8243FD70",
                    "query_vector_offsets": [0, 4, 8],
                    "query_scalar_offsets": [16, 20, 24],
                    "endpoint_vector_offsets": [0, 4, 8],
                    "interpolation_factor": 0.5,
                    "shortcut": "query_scalar_20_less_than_zero_selects",
                    "comparison": "query_scalar_16_times_distance_squared_le_"
                    "query_scalar_24_times_half_segment_squared",
                    "bounded_guest_payload_bytes": 52,
                    "scope": "active_title_record_only",
                    "title_result_comparison_required": True,
                    "guest_payload_read": "bounded_spatial_helper_inputs",
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
            "input_hook": "82E2034C",
            "result_hook": "82E20350",
            "helper": "8243F9A0",
            "distance_helper": "8243FD70",
            "query_vector_offsets": "0,4,8",
            "query_scalar_offsets": "16,20,24",
            "endpoint_vector_offsets": "0,4,8",
            "interpolation_factor": "0.5",
            "shortcut": "query_scalar_20_less_than_zero_selects",
            "comparison": "query_scalar_16_times_distance_squared_le_"
            "query_scalar_24_times_half_segment_squared",
            "bounded_guest_payload_bytes": "52",
            "scope": "active_title_record_only",
            "classification": "independent_spatial_helper_shadow",
            "guest_payload_read": "bounded_spatial_helper_inputs",
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
            "spatial_helper_observations": str(inputs),
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
            "false_positive": "0",
            "false_negative": "0",
            "invalid_inputs": "0",
            "native_policy_execution": "shadow_only",
            "guest_payload_read": "bounded_spatial_helper_inputs",
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
            "false_positive": "0",
            "false_negative": "0",
            "invalid_inputs": "0",
            "input_without_record": "2",
            "result_without_input": "0",
            "accounting_complete": "true",
            "model": "bounded_title_spatial_helper_scalar_mirror",
            "scope": "active_title_record_only",
            "unscoped_continuations_excluded": "true",
            "classification": "independent_spatial_helper_shadow",
            "guest_payload_read": "bounded_spatial_helper_inputs",
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

    def test_build_qualifies_exact_spatial_mirror(self):
        document = MODULE.build(self.events(), self.static())
        self.assertEqual("complete", document["status"])
        self.assertEqual(7, document["totals"]["matches"])
        self.assertTrue(
            document["qualification"][
                "independent_spatial_helper_shadow_proved"
            ]
        )
        self.assertFalse(document["safety"]["guest_state_changed"])
        self.assertTrue(document["safety"]["xenos_authority"])

    def test_build_rejects_incomplete_runtime_summary(self):
        events = copy.deepcopy(self.events())
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["status"] = "incomplete"
        with self.assertRaisesRegex(ValueError, "incomplete or unsafe"):
            MODULE.build(events, self.static())

    def test_build_rejects_static_guest_write_drift(self):
        static = self.static()
        static["procedural_model_receiver_lifecycle"][
            "visibility_spatial_shadow"
        ]["guest_state_changed"] = True
        with self.assertRaisesRegex(ValueError, "contract drifted"):
            MODULE.build(self.events(), static)


if __name__ == "__main__":
    unittest.main()
