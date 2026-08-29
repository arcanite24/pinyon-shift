import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-visibility-oracle.py"
SPEC = importlib.util.spec_from_file_location("visibility_oracle", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VisibilityOracleSummaryTest(unittest.TestCase):
    def static(self):
        return {
            "procedural_model_receiver_lifecycle": {
                "visibility_policy_inputs": {
                    "spatial_helper_address": "8243F9A0",
                    "category_helper_address": "82441048",
                    "spatial_helper_result_hook_address": "82E20350",
                    "category_helper_result_hook_address": "82E20368",
                    "helper_result_capture": "ordered_per_record_return_trace",
                    "category_helper_contract": {"return_domain": [0, 1, 2]},
                    "structural_derivation_proved": True,
                    "camera_semantics_proved": False,
                    "frustum_plane_layout_proved": False,
                    "bounds_shape_semantics_proved": False,
                    "native_policy_execution_enabled": False,
                    "guest_state_changed": False,
                    "xenos_authority": True,
                    "suppression_allowed": False,
                }
            }
        }

    def events(self):
        common = {"schema": 1, "session": "s"}
        config = {
            **common,
            "event": MODULE.CONFIG,
            "status": "armed",
            "class": "proceduralGeometry::CProceduralModels",
            "visibility_function": "82E1FD00",
            "record_entry_hook": "82E20094",
            "spatial_helper": "8243F9A0",
            "spatial_helper_result_hook": "82E20350",
            "category_helper": "82441048",
            "category_helper_result_hook": "82E20368",
            "category_result_domain": "0,1,2",
            "outcomes": "early_rejected,rejected,selected",
            "classification": "title_ordered_visibility_helper_oracle",
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_policy_execution": "false",
            "native_culling": "false",
            "native_lod": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        visibility = {
            **common,
            "event": MODULE.VISIBILITY_CATEGORY,
            "status": "complete",
            "category": "9",
            "early_rejected": "1",
            "rejected": "1",
            "selected": "1",
        }
        safety = {
            "status": "complete",
            "native_policy_execution": "false",
            "guest_state_changed": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        categories = [
            {
                **common,
                **safety,
                "event": MODULE.CATEGORY,
                "category": "9",
                "outcome": "early_rejected",
                "records": "1",
                "spatial_helper_observations": "0",
                "spatial_helper_passes": "0",
                "category_helper_observations": "0",
                "category_result_0": "0",
                "category_result_1": "0",
                "category_result_2": "0",
            },
            {
                **common,
                **safety,
                "event": MODULE.CATEGORY,
                "category": "9",
                "outcome": "rejected",
                "records": "1",
                "spatial_helper_observations": "2",
                "spatial_helper_passes": "1",
                "category_helper_observations": "1",
                "category_result_0": "1",
                "category_result_1": "0",
                "category_result_2": "0",
            },
            {
                **common,
                **safety,
                "event": MODULE.CATEGORY,
                "category": "9",
                "outcome": "selected",
                "records": "1",
                "spatial_helper_observations": "1",
                "spatial_helper_passes": "1",
                "category_helper_observations": "1",
                "category_result_0": "0",
                "category_result_1": "1",
                "category_result_2": "0",
            },
        ]
        summary = {
            **common,
            **safety,
            "event": MODULE.SUMMARY,
            "accounting_complete": "true",
            "classification": "title_ordered_visibility_helper_oracle",
            "guest_payload_read": "false",
            "control_flow_changed": "false",
            "native_culling": "false",
            "native_lod": "false",
            "records": "3",
            "spatial_helper_observations": "3",
            "spatial_helper_passes": "2",
            "category_helper_observations": "2",
            "category_result_0": "1",
            "category_result_1": "1",
            "category_result_2": "0",
            "spatial_helper_without_record": "0",
            "category_helper_without_record": "0",
            "category_helper_without_spatial_pass": "0",
            "category_helper_invalid_result": "0",
        }
        return [config, visibility, *categories, summary]

    def test_builds_complete_ordered_oracle(self):
        document = MODULE.build(self.events(), self.static())
        self.assertEqual("complete", document["status"])
        self.assertTrue(document["qualification"]["ordered_helper_trace_proved"])
        self.assertTrue(
            document["qualification"]["ready_for_shadow_policy_modeling"]
        )
        self.assertEqual(3, document["totals"]["records"])

    def test_rejects_category_without_spatial_pass(self):
        events = copy.deepcopy(self.events())
        events[-1]["category_helper_without_spatial_pass"] = "1"
        with self.assertRaisesRegex(ValueError, "aggregate accounting"):
            MODULE.build(events, self.static())

    def test_rejects_static_hook_drift(self):
        static = self.static()
        static["procedural_model_receiver_lifecycle"][
            "visibility_policy_inputs"
        ]["category_helper_result_hook_address"] = "82E2036C"
        with self.assertRaisesRegex(ValueError, "static visibility-oracle"):
            MODULE.build(self.events(), static)


if __name__ == "__main__":
    unittest.main()
