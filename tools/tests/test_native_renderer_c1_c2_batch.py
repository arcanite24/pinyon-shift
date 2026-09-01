import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-c1-c2-batch.py"
SPEC = importlib.util.spec_from_file_location(
    "summarize_native_renderer_c1_c2_batch", TOOL
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    passive_safety = {
        "guest_state_changed": False,
        "native_admission": False,
        "native_draw": False,
        "suppression_allowed": False,
        "xenos_authority": True,
    }
    return {
        "track": {
            "schema": MODULE.INPUT_SCHEMAS["track"],
            "session": "session-1",
            "status": "complete",
            "failures": [],
            "evidence": {"session_exit_proved": True},
            "qualification": {
                "track_command_lineage_to_prepared_draw_proved": True,
            },
            "safety": passive_safety,
        },
        "presentation": {
            "schema": MODULE.INPUT_SCHEMAS["presentation"],
            "session": "session-1",
            "status": "complete",
            "failures": [],
            "qualification": {
                "color_target_slots": [80],
                "opaque_world_slot_proved": True,
            },
            "slot_totals": {
                "80": {
                    "adapter_route": {
                        "entries": 4,
                        "enabled": 4,
                        "eligible": 4,
                        "dispatches": 4,
                        "first_target": "8240F000",
                        "last_target": "8240F000",
                        "target_changes": 0,
                    }
                }
            },
            "safety": passive_safety,
        },
        "static_world": {
            "schema": MODULE.INPUT_SCHEMAS["static_world"],
            "session": "session-1",
            "status": "complete",
            "failures": [],
            "evidence": {"session_exit_proved": True},
            "qualification": {
                "simple_model_renderer_scope_proved": True,
                "simple_model_resource_lifetime_proved": True,
                "payload_generation_invalidation_proved": True,
                "simple_mesh_to_prepared_draw_proved": True,
                "model_presentation_transform_to_prepared_draw_proved": True,
                "hashed_asset_identity_to_prepared_draw_proved": True,
                "complete_vertex_layout_to_prepared_draw_proved": True,
                "static_world_pm4_to_prepared_draw_proved": True,
            },
            "safety": passive_safety,
        },
        "classification": {
            "schema": MODULE.INPUT_SCHEMAS["classification"],
            "session": "session-1",
            "status": "complete",
            "failures": [],
            "qualification": {
                "runtime_transform_join_proved": True,
                "building_or_prop_instance_identity_proved": True,
            },
            "safety": {
                "guest_state_changed": False,
                "source_files_changed": False,
                "plaintext_identity_exported": False,
                "xenos_draw": "preserved",
                "native_admission": False,
                "native_draw": False,
                "suppression_allowed": False,
            },
        },
        "workset": {
            "schema": MODULE.INPUT_SCHEMAS["workset"],
            "session": "session-1",
            "status": "complete",
            "failures": [],
            "evidence": {"session_exit_proved": True},
            "qualification": {
                "continuous_multi_draw_workset_proved": True,
                "swap_committed_freshness_proved": True,
                "clean_xenos_fallback_proved": True,
                "track_world_selection_proved": True,
                "static_world_selection_proved": True,
            },
            "safety": {
                "readback": False,
                "xenos_draw_preserved": True,
                "output_authority": "renderer_selector",
                "suppression_allowed": False,
            },
        },
    }


class NativeRendererC1C2BatchTests(unittest.TestCase):
    def test_qualifies_one_clean_exact_session(self):
        document = MODULE.build(fixture())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["c1_exact_track_world_output_proved"]
        )
        self.assertTrue(
            document["qualification"][
                "c2_exact_classified_static_world_output_proved"
            ]
        )
        self.assertFalse(
            document["qualification"]["manual_visual_acceptance_proved"]
        )
        self.assertFalse(document["qualification"]["suppression_allowed"])
        self.assertEqual(
            "8240F000",
            document["presentation_lead"][
                "slot_80_stable_adapter_target"
            ],
        )

    def test_rejects_cross_session_evidence(self):
        reports = fixture()
        reports["workset"]["session"] = "session-2"
        with self.assertRaisesRegex(ValueError, "one exact session"):
            MODULE.build(reports)

    def test_rejects_checkpoint_only_evidence(self):
        reports = fixture()
        reports["workset"]["status"] = "checkpoint_complete"
        reports["workset"]["evidence"]["session_exit_proved"] = False
        document = MODULE.build(reports)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "workset report does not prove session exit", document["failures"]
        )

    def test_reports_missing_track_command_lineage(self):
        reports = fixture()
        reports["track"]["qualification"][
            "track_command_lineage_to_prepared_draw_proved"
        ] = False
        document = MODULE.build(reports)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "track gate is unproved: "
            "track_command_lineage_to_prepared_draw_proved",
            document["failures"],
        )

    def test_routes_unproved_color_pass_to_stable_adapter_target(self):
        reports = fixture()
        reports["presentation"]["qualification"][
            "opaque_world_slot_proved"
        ] = False
        reports["presentation"]["qualification"]["color_target_slots"] = []
        document = MODULE.build(reports)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "track presentation color-pass identity is unproved",
            document["failures"],
        )
        self.assertEqual(
            "instrument_slot_80_adapter_target", document["next_gate"]
        )

    def test_closes_gated_slot_80_before_semantic_pivot(self):
        reports = fixture()
        reports["presentation"]["qualification"][
            "opaque_world_slot_proved"
        ] = False
        reports["presentation"]["qualification"]["color_target_slots"] = []
        adapter = reports["presentation"]["slot_totals"]["80"][
            "adapter_route"
        ]
        adapter["dispatches"] = 0
        adapter["first_target"] = "00000000"
        adapter["last_target"] = "00000000"
        document = MODULE.build(reports)
        self.assertEqual(
            "close_slot_80_and_pivot_to_semantic_world_ingress",
            document["next_gate"],
        )

    def test_rejects_safety_drift(self):
        reports = copy.deepcopy(fixture())
        reports["static_world"]["safety"]["native_draw"] = True
        with self.assertRaisesRegex(ValueError, "safety boundary drifted"):
            MODULE.build(reports)


if __name__ == "__main__":
    unittest.main()
