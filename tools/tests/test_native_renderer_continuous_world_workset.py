import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-continuous-world-workset.py"
SPEC = importlib.util.spec_from_file_location(
    "summarize_native_renderer_continuous_world_workset", TOOL
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def event(name, **values):
    return {"event": name, "session": "session-1", **values}


def fixture():
    config = event(
        MODULE.CONFIG,
        status="armed_deferred_private_composition",
        activation="startup_environment_only",
        default_enabled="false",
        selection=MODULE.SELECTION,
        maximum_draws_per_frame="64",
        target_lifetime="one_guest_frame",
        freshness_commit="matching_swap_after_complete_accumulation",
        semantic_lineage="armed",
        track_world_selection=MODULE.TRACK_WORLD_SELECTION,
        static_world_selection=MODULE.STATIC_WORLD_SELECTION,
        readback="disabled",
        native_draw="continuous_world_workset",
        xenos_draw="preserved",
        output_authority="renderer_selector",
        draw_suppression="false",
        suppression_eligible="false",
    )
    summary = event(
        MODULE.SUMMARY,
        status="complete",
        final_summary="true",
        frame_sequence="900",
        prepared_observations="22",
        requests="10",
        recorded="10",
        target_creation_failures="0",
        unsupported="0",
        mechanical_rejections="4",
        stale_or_unselected_rejections="3",
        non_track_provider_rejections="2",
        track_world_identity_exclusions="1",
        track_world_candidates="7",
        track_world_mechanically_eligible="3",
        track_world_mechanically_rejected="4",
        track_world_mechanical_rejection_reasons=(
            "resolved_input=0;unsupported_geometry=4;empty_draw=0;"
            "vertex_binding_count=0;vertex_binding_overflow=0;"
            "vertex_attribute_overflow=0;vertex_constant_overflow=0;"
            "pixel_constant_overflow=0;texture_state_overflow=0;memexport=0;"
            "query=0;texture_count=0;texture_layout=0;prepared_pipeline=0;"
            "render_targets=0"
        ),
        track_world_requests="3",
        procedural_color_producer_candidates="2",
        procedural_color_producer_requests="2",
        static_world_lineage_rejections="0",
        static_world_requests="3",
        per_frame_quota_yields="2",
        fail_closed_yields="0",
        qualified_retained_family_requests="2",
        reused_target_requests="8",
        frames_started="2",
        frames_completed="2",
        frames_failed="0",
        accounting_complete="true",
        selection_accounting_complete="true",
        selection=MODULE.SELECTION,
        track_world_selection=MODULE.TRACK_WORLD_SELECTION,
        static_world_selection=MODULE.STATIC_WORLD_SELECTION,
        maximum_draws_per_frame="64",
        freshness_commit="matching_swap_after_complete_accumulation",
        readback="disabled",
        native_draw="continuous_world_workset",
        xenos_draw="preserved",
        output_authority="renderer_selector",
        draw_suppression="false",
        suppression_eligible="false",
    )
    output_frames = [
        event(
            MODULE.OUTPUT_FRAME,
            callback=str(callback),
            frame=str(callback),
            retained_frame=str(callback),
            selected_output="native",
            authority="native",
            xenos_draw="preserved",
            suppression="disabled",
        )
        for callback in (300, 600, 900)
    ]
    waiting = event(
        MODULE.OUTPUT_WAITING,
        reason="retained_pass_unavailable",
        fallback="xenos",
        suppression="disabled",
    )
    return [config, *output_frames, waiting, summary]


class ContinuousWorldWorksetTests(unittest.TestCase):







    def test_scaled_accumulator_layout_reconciles_authoritative_regions(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        header = (
            ROOT / "src/native_renderer/resolve_frame_accumulator.h"
        ).read_text(encoding="utf-8")
        implementation = (
            ROOT / "src/native_renderer/resolve_frame_accumulator.cpp"
        ).read_text(encoding="utf-8")
        native_test = (
            ROOT / "tests/native_renderer/resolve_frame_accumulator_test.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("ProceduralFrameAccumulatorSourceTopology", header)
        self.assertIn("ProceduralFrameAccumulatorPhysicalLayout", header)
        self.assertIn("BuildProceduralFrameAccumulatorPhysicalLayout", header)
        self.assertIn("topology.source_guest_y", implementation)
        self.assertIn("destination_copy_rows", implementation)
        self.assertIn("padding_rows", implementation)
        self.assertIn("third_layout.source_y == 0", native_test)
        self.assertIn("third_layout.padding_rows == 32", native_test)
        self.assertIn(
            '"native_renderer.procedural_frame_accumulator.layout"', source
        )
        self.assertIn('"backend_copy", "not_yet_admitted"', source)





    def test_scaled_accumulator_qualification_keeps_xenos_authoritative(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        capture = (
            ROOT / "tools/capture-native-renderer-census.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "pinyon_shift_native_renderer_scaled_accumulator_qualification",
            source,
        )
        self.assertIn("NativeScaledAccumulatorScaleSupported", source)
        self.assertIn('== "2"', source)
        self.assertIn(
            'REXCVAR_GET(pinyon_shift_native_renderer) == "xenos"', source
        )
        self.assertIn('"armed_private_2x"', source)
        self.assertIn('{"publication", "disabled"}', source)
        self.assertIn('{"output_authority", "xenos"}', source)
        self.assertIn("[switch]$ScaledAccumulatorQualification", capture)
        qualification = capture.split(
            "if ($ScaledAccumulatorQualification) {", 1
        )[1]
        self.assertIn("$ProceduralFrameAccumulator = $true", qualification)
        self.assertIn("$ContinuousWorldWorkset = $true", qualification)
        self.assertIn("$ContinuousTrackWorld = $true", qualification)
        self.assertIn("$ContinuousStaticWorld = $true", qualification)
        self.assertIn(
            "$env:REX_PINYON_SHIFT_NATIVE_RENDERER = 'xenos'", capture
        )
        self.assertIn(
            "$env:REX_PINYON_SHIFT_NATIVE_RENDERER = $savedNativeRenderer",
            capture,
        )


    def test_qualifies_complete_multi_draw_worksets(self):
        document = MODULE.build(fixture())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["continuous_multi_draw_workset_proved"]
        )
        self.assertTrue(
            document["qualification"]["track_provider_selection_proved"]
        )
        self.assertTrue(
            document["qualification"]["track_world_selection_proved"]
        )
        self.assertTrue(
            document["qualification"][
                "procedural_color_producer_selection_proved"
            ]
        )
        self.assertTrue(
            document["qualification"]["static_world_selection_proved"]
        )
        self.assertFalse(document["qualification"]["suppression_allowed"])
        self.assertTrue(document["evidence"]["session_exit_proved"])

    def test_qualifies_latest_non_mutating_checkpoint(self):
        events = fixture()
        checkpoint = events[-1]
        checkpoint.update(
            event=MODULE.CHECKPOINT,
            status="checkpoint_complete",
            final_summary="false",
        )
        document = MODULE.build(events, allow_checkpoint=True)
        self.assertEqual("checkpoint_complete", document["status"])
        self.assertEqual("checkpoint", document["evidence"]["kind"])
        self.assertFalse(document["evidence"]["session_exit_proved"])

    def test_requires_explicit_checkpoint_opt_in(self):
        events = fixture()
        events[-1].update(
            event=MODULE.CHECKPOINT,
            status="checkpoint_complete",
            final_summary="false",
        )
        with self.assertRaisesRegex(ValueError, "exactly one.*summary"):
            MODULE.build(events)

    def test_final_summary_wins_over_later_checkpoint_input(self):
        events = fixture()
        checkpoint = copy.deepcopy(events[-1])
        checkpoint.update(
            event=MODULE.CHECKPOINT,
            status="checkpoint_complete",
            final_summary="false",
            frame_sequence="1200",
        )
        document = MODULE.build([*events, checkpoint], allow_checkpoint=True)
        self.assertEqual("complete", document["status"])
        self.assertTrue(document["evidence"]["session_exit_proved"])

    def test_rejects_single_draw_frames(self):
        events = fixture()
        events[-1]["reused_target_requests"] = "0"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "no frame accumulated multiple native draws", document["failures"]
        )

    def test_rejects_seed_only_workset(self):
        events = fixture()
        summary = events[-1]
        summary["prepared_observations"] = "13"
        summary["requests"] = "2"
        summary["recorded"] = "2"
        summary["qualified_retained_family_requests"] = "2"
        summary["static_world_requests"] = "0"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "no track-provider visibility request was observed",
            document["failures"],
        )

    def test_rejects_static_world_lineage_failure(self):
        events = fixture()
        events[-1]["static_world_lineage_rejections"] = "1"
        events[-1]["stale_or_unselected_rejections"] = "2"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "static-world lineage rejection was observed",
            document["failures"],
        )

    def test_rejects_missing_exact_track_world_request(self):
        events = fixture()
        events[-1]["track_world_requests"] = "0"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "no exact track-world request was observed", document["failures"]
        )

    def test_rejects_missing_exact_procedural_color_producer(self):
        events = fixture()
        events[-1].update(
            procedural_color_producer_candidates="0",
            procedural_color_producer_requests="0",
        )
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "no exact procedural color producer was observed",
            document["failures"],
        )
        self.assertIn(
            "no exact procedural color producer was replayed",
            document["failures"],
        )

    def test_rejects_track_world_eligibility_accounting_drift(self):
        events = fixture()
        events[-1]["track_world_mechanically_rejected"] = "3"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "track-world mechanical eligibility accounting drifted",
            document["failures"],
        )

    def test_accepts_legacy_summary_without_eligibility_partition(self):
        events = fixture()
        for key in (
            "track_world_candidates",
            "track_world_mechanically_eligible",
            "track_world_mechanically_rejected",
            "track_world_mechanical_rejection_reasons",
        ):
            events[-1].pop(key)
        document = MODULE.build(events)
        self.assertEqual("complete", document["status"])

    def test_keeps_exact_track_world_selection_optional(self):
        events = fixture()
        events[0]["track_world_selection"] = "disabled"
        events[-1].update(
            prepared_observations="21",
            track_world_selection="disabled",
            track_world_identity_exclusions="0",
            track_world_requests="0",
        )
        document = MODULE.build(events)
        self.assertEqual("complete", document["status"])
        self.assertFalse(
            document["qualification"]["track_world_selection_proved"]
        )

    def test_qualifies_an_accounted_fail_closed_frame(self):
        events = fixture()
        events[-1].update(
            status="fallback_observed",
            recorded="9",
            unsupported="1",
            frames_completed="1",
            frames_failed="1",
        )
        document = MODULE.build(events)
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["clean_xenos_fallback_proved"]
        )

    def test_rejects_unreconciled_failed_frame(self):
        events = fixture()
        events[-1].update(
            status="fallback_observed",
            frames_completed="1",
            frames_failed="1",
        )
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "failed frames do not reconcile with replay fallbacks",
            document["failures"],
        )

    def test_rejects_stale_native_output_claim(self):
        events = fixture()
        events[2]["retained_frame"] = "599"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "native output marker violates freshness or safety",
            document["failures"],
        )

    def test_rejects_safety_drift(self):
        events = copy.deepcopy(fixture())
        events[-1]["draw_suppression"] = "true"
        with self.assertRaisesRegex(ValueError, "safety boundary"):
            MODULE.build(events)


if __name__ == "__main__":
    unittest.main()
