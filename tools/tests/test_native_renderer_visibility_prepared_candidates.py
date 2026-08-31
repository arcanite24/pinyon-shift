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
                    "title_lod_lineage": "exact_visibility_identity_to_prepared_draw",
                    "mechanical_admission_contract": "isolated_draw_v1",
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
            "title_lod_lineage": "exact_visibility_identity_to_prepared_draw",
            "mechanical_admission_contract": "isolated_draw_v1",
            **self.safety(),
        }
        entry = {
            "event": MODULE.ENTRY,
            "session": "test",
            "status": "complete",
            "candidate_key": "1111111111111111",
            "prepared_signature": "AAAAAAAAAAAAAAAA",
            "template_key": "2222222222222222",
            "geometry_resource_hash": "3333333333333333",
            "texture_resource_hash": "4444444444444444",
            "vertex_shader": "5555555555555555",
            "pixel_shader": "6666666666666666",
            "vertex_specialization_mask": "000000000000007F",
            "pixel_specialization_mask": "0000000F001D007F",
            "receiver_address": "10001000",
            "receiver_generation": "2",
            "record_index": "4",
            "visibility_category": "9",
            "visibility_result_mask": "6",
            "title_lod_index": "2",
            "title_lod_valid": "true",
            "title_lod_lineage": "exact_visibility_identity_to_prepared_draw",
            "track_texture_provider": "true",
            "track_texture_provider_lineage": (
                "exact_primary_provider_vtable_and_four_methods"
            ),
            "track_render_model_scope": "true",
            "track_render_shared_identity_mask": "00000002",
            "track_render_model_lineage": (
                "exact_unified_instance_model_nested_dispatch_scope"
            ),
            "track_world_resource_identity_mask": "00000012",
            "track_world_resource_shared_identity_mask": "00000002",
            "track_world_resource_lineage": (
                "host_mapped_direct_vtable_identity_from_exact_model_graph"
            ),
            "draws": "7",
            "first_frame": "10",
            "last_frame": "12",
            "maximum_policy_age_frames": "1",
            "mechanically_eligible": "true",
            "mechanical_rejection_mask": "00000000",
            "mechanical_admission_contract": "isolated_draw_v1",
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
            "mechanically_eligible_entries": "1",
            "mechanically_eligible_draws": "7",
            "mechanically_ineligible_entries": "0",
            "mechanically_ineligible_draws": "0",
            "mechanical_admission_contract": "isolated_draw_v1",
            "title_lod_entries": "1",
            "title_lod_draws": "7",
            "track_texture_provider_entries": "1",
            "track_texture_provider_draws": "7",
            "track_render_model_scope_entries": "1",
            "track_render_model_scope_draws": "7",
            "track_render_shared_identity_entries": "1",
            "track_render_shared_identity_draws": "7",
            "track_world_resource_identity_entries": "1",
            "track_world_resource_identity_draws": "7",
            "track_world_resource_shared_identity_entries": "1",
            "track_world_resource_shared_identity_draws": "7",
            "capacity": "4096",
            "overflow": "0",
            "policy_age_limit_frames": "1",
            "accounting_complete": "true",
            "identity": "receiver_generation_record_index",
            "prepared_lineage": "exact_semantic_pm4_prepared_draw",
            "selection": "independent_visibility_selected_and_fresh",
            "title_lod_lineage": "exact_visibility_identity_to_prepared_draw",
            "track_texture_provider_lineage": (
                "exact_primary_provider_vtable_and_four_methods"
            ),
            "track_render_model_lineage": (
                "exact_unified_instance_model_nested_dispatch_scope"
            ),
            "track_world_resource_lineage": (
                "host_mapped_direct_vtable_identity_from_exact_model_graph"
            ),
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
        self.assertTrue(
            document["qualification"]["isolated_native_candidate_proved"]
        )
        self.assertTrue(document["qualification"]["title_lod_lineage_proved"])
        self.assertTrue(
            document["qualification"][
                "track_texture_provider_lineage_proved"
            ]
        )
        self.assertTrue(
            document["qualification"][
                "track_render_model_scope_lineage_proved"
            ]
        )
        self.assertTrue(
            document["qualification"]["track_render_shared_identity_proved"]
        )
        self.assertTrue(
            document["qualification"]["track_world_resource_identity_proved"]
        )
        self.assertTrue(
            document["qualification"][
                "track_world_resource_shared_identity_proved"
            ]
        )

    def test_build_accepts_candidate_without_title_lod(self):
        events = copy.deepcopy(self.events())
        entry = next(event for event in events if event["event"] == MODULE.ENTRY)
        entry["title_lod_index"] = "0"
        entry["title_lod_valid"] = "false"
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["title_lod_entries"] = "0"
        summary["title_lod_draws"] = "0"
        document = MODULE.build(events, self.static())
        self.assertEqual("complete", document["status"])
        self.assertFalse(document["qualification"]["title_lod_lineage_proved"])

    def test_build_reports_each_mechanical_rejection_reason(self):
        events = copy.deepcopy(self.events())
        entry = next(event for event in events if event["event"] == MODULE.ENTRY)
        entry["mechanically_eligible"] = "false"
        entry["mechanical_rejection_mask"] = "00002003"
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["mechanically_eligible_entries"] = "0"
        summary["mechanically_eligible_draws"] = "0"
        summary["mechanically_ineligible_entries"] = "1"
        summary["mechanically_ineligible_draws"] = "7"
        document = MODULE.build(events, self.static())
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            ["resolved_input", "unsupported_geometry", "prepared_pipeline"],
            document["entries"][0]["mechanical_rejections"],
        )
        self.assertEqual(
            7,
            document["mechanical_rejection_draw_counts"]["prepared_pipeline"],
        )

    def test_build_accepts_non_track_provider_partition(self):
        events = copy.deepcopy(self.events())
        entry = next(event for event in events if event["event"] == MODULE.ENTRY)
        entry["track_texture_provider"] = "false"
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["track_texture_provider_entries"] = "0"
        summary["track_texture_provider_draws"] = "0"
        document = MODULE.build(events, self.static())
        self.assertEqual("complete", document["status"])
        self.assertFalse(
            document["qualification"][
                "track_texture_provider_lineage_proved"
            ]
        )

    def test_build_accepts_track_scope_without_shared_identity(self):
        events = copy.deepcopy(self.events())
        entry = next(event for event in events if event["event"] == MODULE.ENTRY)
        entry["track_render_shared_identity_mask"] = "00000000"
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["track_render_shared_identity_entries"] = "0"
        summary["track_render_shared_identity_draws"] = "0"
        document = MODULE.build(events, self.static())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"][
                "track_render_model_scope_lineage_proved"
            ]
        )
        self.assertFalse(
            document["qualification"]["track_render_shared_identity_proved"]
        )

    def test_build_rejects_eligibility_mask_drift(self):
        events = copy.deepcopy(self.events())
        entry = next(event for event in events if event["event"] == MODULE.ENTRY)
        entry["mechanical_rejection_mask"] = "00000001"
        with self.assertRaisesRegex(ValueError, "entry evidence drifted"):
            MODULE.build(events, self.static())

    def test_build_accepts_fresh_candidate_without_isolated_eligibility(self):
        events = copy.deepcopy(self.events())
        entry = next(event for event in events if event["event"] == MODULE.ENTRY)
        entry["mechanically_eligible"] = "false"
        entry["mechanical_rejection_mask"] = "00000001"
        summary = next(event for event in events if event["event"] == MODULE.SUMMARY)
        summary["mechanically_eligible_entries"] = "0"
        summary["mechanically_eligible_draws"] = "0"
        summary["mechanically_ineligible_entries"] = "1"
        summary["mechanically_ineligible_draws"] = "7"
        document = MODULE.build(events, self.static())
        self.assertEqual("complete", document["status"])
        self.assertFalse(
            document["qualification"]["isolated_native_candidate_proved"]
        )

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
