import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-visibility-prepared-candidates.py"
SPEC = importlib.util.spec_from_file_location("visibility_prepared", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VisibilityPreparedCandidateReportTests(unittest.TestCase):
    def static(self):
        return {
            "schema": MODULE.STATIC_SCHEMA,
            "procedural_model_receiver_lifecycle": {
                "visibility_prepared_candidates": {
                    "semantic_instance_hook_address": "8241741C",
                    "semantic_packet_hook_addresses": ["82416260", "824162F4"],
                    "capacity": 4096,
                    "maximum_policy_age_frames": 1,
                    "identity": "receiver_generation_record_index",
                    "selection": "independent_visibility_selected_and_fresh",
                    "prepared_lineage": "exact_semantic_pm4_prepared_draw",
                    "guest_state_changed": False,
                    "control_flow_changed": False,
                    "native_upload_enabled": False,
                    "native_draw_enabled": False,
                    "xenos_draw_preserved": True,
                    "suppression_allowed": False,
                }
            },
        }

    def safety(self):
        return {
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "native_upload": "false",
            "native_draw": "false",
            "xenos_draw": "preserved",
            "suppression_allowed": "false",
        }

    def events(self):
        config = {
            "event": MODULE.CONFIG,
            "session": "test",
            "status": "armed",
            "class": "proceduralGeometry::CProceduralModels",
            "semantic_instance_hook": "8241741C",
            "semantic_packet_hooks": "82416260,824162F4",
            "prepared_draw_join": "physical_pm4_header_generation",
            "capacity": "4096",
            "policy_age_limit_frames": "1",
            "identity": "receiver_generation_record_index",
            "selection": "independent_visibility_selected_and_fresh",
            "prepared_lineage": "exact_semantic_pm4_prepared_draw",
            **self.safety(),
        }
        entry = {
            "event": MODULE.ENTRY,
            "session": "test",
            "status": "complete",
            "candidate_key": "1111111111111111",
            "template_key": "2222222222222222",
            "geometry_resource_hash": "3333333333333333",
            "texture_resource_hash": "4444444444444444",
            "receiver_address": "10001000",
            "receiver_generation": "2",
            "record_index": "4",
            "visibility_category": "9",
            "visibility_result_mask": "6",
            "draws": "7",
            "first_frame": "10",
            "last_frame": "12",
            "maximum_policy_age_frames": "1",
            "policy_age_limit_frames": "1",
            "classification": "fresh_visibility_selected_prepared_candidate",
            **self.safety(),
        }
        summary = {
            "event": MODULE.SUMMARY,
            "session": "test",
            "status": "complete",
            "observations": "15",
            "selected_joins": "9",
            "fresh_candidates": "7",
            "stale_exclusions": "2",
            "future_exclusions": "0",
            "rejected_exclusions": "3",
            "missing_exclusions": "3",
            "candidate_entries": "1",
            "entry_draws": "7",
            "capacity": "4096",
            "overflow": "0",
            "policy_age_limit_frames": "1",
            "accounting_complete": "true",
            "identity": "receiver_generation_record_index",
            "prepared_lineage": "exact_semantic_pm4_prepared_draw",
            "selection": "independent_visibility_selected_and_fresh",
            **self.safety(),
        }
        workset = {
            "event": MODULE.WORKSET,
            "session": "test",
            "selected_joins": "10",
        }
        return [config, entry, summary, workset]

    def test_build_qualifies_fresh_prepared_handoff(self):
        document = MODULE.build(self.events(), self.static())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"][
                "fresh_visibility_prepared_handoff_proved"
            ]
        )
        self.assertEqual(2, document["totals"]["stale_exclusions"])

    def test_build_rejects_future_policy_decision(self):
        events = copy.deepcopy(self.events())
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["fresh_candidates"] = "6"
        summary["future_exclusions"] = "1"
        summary["entry_draws"] = "6"
        entry = next(event for event in events if event["event"] == MODULE.ENTRY)
        entry["draws"] = "6"
        document = MODULE.build(events, self.static())
        self.assertEqual("incomplete", document["status"])
        self.assertIn("future_exclusions is nonzero", document["failures"])

    def test_build_rejects_overflow(self):
        events = copy.deepcopy(self.events())
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["fresh_candidates"] = "8"
        summary["overflow"] = "1"
        document = MODULE.build(events, self.static())
        self.assertEqual("incomplete", document["status"])
        self.assertIn("overflow is nonzero", document["failures"])

    def test_build_rejects_workset_join_drift(self):
        events = copy.deepcopy(self.events())
        workset = next(event for event in events if event["event"] == MODULE.WORKSET)
        workset["selected_joins"] = "8"
        document = MODULE.build(events, self.static())
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "prepared selected joins exceed workset joins", document["failures"]
        )

    def test_build_rejects_static_suppression_drift(self):
        static = self.static()
        static["procedural_model_receiver_lifecycle"][
            "visibility_prepared_candidates"
        ]["suppression_allowed"] = True
        with self.assertRaisesRegex(ValueError, "contract drifted"):
            MODULE.build(self.events(), static)


if __name__ == "__main__":
    unittest.main()
