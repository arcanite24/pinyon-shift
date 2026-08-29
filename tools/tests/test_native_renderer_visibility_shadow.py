import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-visibility-shadow.py"
SPEC = importlib.util.spec_from_file_location("visibility_shadow", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VisibilityShadowReportTests(unittest.TestCase):
    def static(self):
        return {
            "procedural_model_receiver_lifecycle": {
                "visibility_shadow_policy": {
                    "record_entry_hook_address": "82E20094",
                    "category_helper_result_hook_address": "82E20368",
                    "title_result_hook_address": "82E206F8",
                    "record_exit_hook_address": "82E2084C",
                    "model": "any_nonzero_category_result_selects",
                    "category_result_domain": [0, 1, 2],
                    "scope": "active_title_record_only",
                    "title_outcome_comparison_required": True,
                    "guest_payload_read": False,
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
            "record_entry_hook": "82E20094",
            "category_helper_result_hook": "82E20368",
            "title_result_hook": "82E206F8",
            "record_completion_hook": "82E2084C",
            "model": "any_nonzero_category_result_selects",
            "category_result_domain": "0,1,2",
            "outcomes": "early_rejected,rejected,selected",
            "scope": "active_title_record_only",
            "classification": "title_result_domain_shadow_selection",
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_policy_execution": "shadow_only",
            "native_culling": "false",
            "native_lod": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }

    def category(self, outcome, records, modelled, selected=0, rejected=0):
        result_1 = selected
        return {
            "event": MODULE.CATEGORY,
            "session": "test",
            "status": "complete",
            "category": "9",
            "outcome": outcome,
            "records": str(records),
            "modelled_records": str(modelled),
            "predicted_selected": str(selected),
            "predicted_rejected": str(rejected),
            "title_matches": str(modelled),
            "false_positive": "0",
            "false_negative": "0",
            "result_1_records": str(result_1),
            "result_2_records": "0",
            "mixed_nonzero_records": "0",
            "native_policy_execution": "shadow_only",
            "guest_state_changed": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }

    def events(self):
        categories = [
            self.category("early_rejected", 4, 0),
            self.category("rejected", 2, 2, rejected=2),
            self.category("selected", 1, 1, selected=1),
        ]
        summary = {
            "event": MODULE.SUMMARY,
            "session": "test",
            "status": "complete",
            "records": "7",
            "modelled_records": "3",
            "unmodelled_records": "4",
            "predicted_selected": "1",
            "predicted_rejected": "2",
            "title_matches": "3",
            "false_positive": "0",
            "false_negative": "0",
            "result_1_records": "1",
            "result_2_records": "0",
            "mixed_nonzero_records": "0",
            "accounting_complete": "true",
            "model": "any_nonzero_category_result_selects",
            "scope": "active_title_record_only",
            "classification": "title_result_domain_shadow_selection",
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_policy_execution": "shadow_only",
            "native_culling": "false",
            "native_lod": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        visibility = {
            "event": MODULE.VISIBILITY_CATEGORY,
            "session": "test",
            "status": "complete",
            "category": "9",
            "early_rejected": "4",
            "rejected": "2",
            "selected": "1",
        }
        return [self.config(), visibility, *categories, summary]

    def test_build_qualifies_zero_mismatch_shadow_model(self):
        document = MODULE.build(self.events(), self.static())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["title_result_shadow_model_proved"]
        )
        self.assertEqual(3, document["totals"]["modelled_records"])
        self.assertTrue(document["safety"]["xenos_authority"])
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_build_rejects_runtime_mismatch(self):
        events = copy.deepcopy(self.events())
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["status"] = "incomplete"
        summary["accounting_complete"] = "false"
        with self.assertRaisesRegex(ValueError, "incomplete or unsafe"):
            MODULE.build(events, self.static())

    def test_build_rejects_static_suppression_drift(self):
        static = self.static()
        static["procedural_model_receiver_lifecycle"][
            "visibility_shadow_policy"
        ]["suppression_allowed"] = True
        with self.assertRaisesRegex(ValueError, "contract drifted"):
            MODULE.build(self.events(), static)


if __name__ == "__main__":
    unittest.main()
