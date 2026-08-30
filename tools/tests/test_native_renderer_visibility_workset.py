import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-visibility-workset.py"
SPEC = importlib.util.spec_from_file_location("visibility_workset", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VisibilityWorksetReportTests(unittest.TestCase):
    def static(self):
        return {
            "schema": MODULE.STATIC_SCHEMA,
            "procedural_model_receiver_lifecycle": {
                "visibility_policy_workset": {
                    "record_completion_hook_address": "82E2084C",
                    "semantic_instance_hook_address": "8241741C",
                    "capacity": 4096,
                    "model": "independent_policy_to_semantic_candidate_handoff",
                    "identity": "receiver_generation_record_index",
                    "selection_rule": (
                        "any_nonzero_predicted_category_result_selects"
                    ),
                    "execution": "bounded_host_visibility_workset",
                    "guest_payload_read": "qualified_policy_inputs_only",
                    "guest_state_changed": False,
                    "control_flow_changed": False,
                    "title_culling_changed": False,
                    "native_lod_enabled": False,
                    "native_draw_enabled": False,
                    "xenos_authority": True,
                    "suppression_allowed": False,
                }
            },
        }

    def safety(self, entry=False):
        value = {
            "execution": "bounded_host_visibility_workset",
            "guest_state_changed": "false",
            "title_culling_changed": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        if not entry:
            value.update(
                {"control_flow_changed": "false", "native_lod": "false"}
            )
        return value

    def events(self):
        config = {
            "event": MODULE.CONFIG,
            "session": "test",
            "status": "armed",
            "class": "proceduralGeometry::CProceduralModels",
            "record_completion_hook": "82E2084C",
            "semantic_instance_hook": "8241741C",
            "capacity": "4096",
            "model": "independent_policy_to_semantic_candidate_handoff",
            "identity": "receiver_generation_record_index",
            "selection_rule": "any_nonzero_predicted_category_result_selects",
            "guest_payload_read": "qualified_policy_inputs_only",
            **self.safety(),
        }
        selected = {
            "event": MODULE.ENTRY,
            "session": "test",
            "status": "complete",
            "key": "1111111111111111",
            "receiver_address": "10001000",
            "receiver_generation": "2",
            "record_index": "4",
            "category": "9",
            "observations": "3",
            "first_frame": "10",
            "last_frame": "12",
            "predicted_selected": "3",
            "predicted_rejected": "0",
            "title_matches": "3",
            "title_mismatches": "0",
            "semantic_instance_joins": "7",
            "latest_category_result_mask": "6",
            "latest_selected": "true",
            **self.safety(entry=True),
        }
        rejected = {
            **selected,
            "key": "2222222222222222",
            "record_index": "5",
            "observations": "2",
            "predicted_selected": "0",
            "predicted_rejected": "2",
            "title_matches": "2",
            "semantic_instance_joins": "0",
            "latest_category_result_mask": "1",
            "latest_selected": "false",
        }
        summary = {
            "event": MODULE.SUMMARY,
            "session": "test",
            "status": "complete",
            "modelled_records": "5",
            "predicted_selected": "3",
            "predicted_rejected": "2",
            "title_matches": "5",
            "title_mismatches": "0",
            "invalid_records": "0",
            "entries": "2",
            "entry_observations": "5",
            "capacity": "4096",
            "overflow": "0",
            "semantic_instance_lookups": "7",
            "selected_joins": "7",
            "rejected_joins": "0",
            "missing_joins": "0",
            "accounting_complete": "true",
            "model": "independent_policy_to_semantic_candidate_handoff",
            "identity": "receiver_generation_record_index",
            **self.safety(),
        }
        assembly = {
            "event": MODULE.ASSEMBLY,
            "session": "test",
            "modelled_records": "5",
            "predicted_selected": "3",
            "predicted_rejected": "2",
            "title_matches": "5",
            "false_positive": "0",
            "false_negative": "0",
            "invalid_inputs": "0",
        }
        semantic = {
            "event": MODULE.SEMANTIC_INSTANCES,
            "session": "test",
            "live_observations": "7",
        }
        return [config, selected, rejected, summary, assembly, semantic]

    def test_build_qualifies_exact_semantic_handoff(self):
        document = MODULE.build(self.events(), self.static())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["semantic_candidate_handoff_proved"]
        )
        self.assertFalse(document["safety"]["title_culling_changed"])
        self.assertTrue(document["safety"]["xenos_authority"])

    def test_build_filters_missing_superset_observation(self):
        events = copy.deepcopy(self.events())
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["selected_joins"] = "6"
        summary["missing_joins"] = "1"
        selected = next(event for event in events if event["event"] == MODULE.ENTRY)
        selected["semantic_instance_joins"] = "6"
        document = MODULE.build(events, self.static())
        self.assertEqual("complete", document["status"])
        self.assertEqual(1, document["totals"]["missing_joins"])

    def test_build_filters_rejected_superset_observation(self):
        events = copy.deepcopy(self.events())
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["selected_joins"] = "6"
        summary["rejected_joins"] = "1"
        selected = next(event for event in events if event["event"] == MODULE.ENTRY)
        selected["semantic_instance_joins"] = "6"
        rejected = [event for event in events if event["event"] == MODULE.ENTRY][1]
        rejected["semantic_instance_joins"] = "1"
        document = MODULE.build(events, self.static())
        self.assertEqual("complete", document["status"])
        self.assertEqual(1, document["totals"]["rejected_joins"])

    def test_build_rejects_assembly_drift(self):
        events = copy.deepcopy(self.events())
        assembly = next(event for event in events if event["event"] == MODULE.ASSEMBLY)
        assembly["predicted_selected"] = "2"
        document = MODULE.build(events, self.static())
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "assembled policy did not reconcile with workset",
            document["failures"],
        )

    def test_build_rejects_static_suppression_drift(self):
        static = self.static()
        static["procedural_model_receiver_lifecycle"][
            "visibility_policy_workset"
        ]["suppression_allowed"] = True
        with self.assertRaisesRegex(ValueError, "contract drifted"):
            MODULE.build(self.events(), static)


if __name__ == "__main__":
    unittest.main()
