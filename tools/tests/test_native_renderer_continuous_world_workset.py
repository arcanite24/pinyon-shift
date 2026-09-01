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
    def test_runtime_contract_is_swap_committed_and_fail_closed(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_WORLD_WORKSET", source
        )
        self.assertIn("kContinuousWorldWorksetMaximumDrawsPerFrame = 64", source)
        self.assertIn("request.reuse_target = reuse_target", source)
        self.assertIn("request.defer_preview_publication_until_swap = true", source)
        self.assertIn("qualified_retained_family_requests", source)
        self.assertIn("prepared_track_texture_provider", source)
        self.assertIn("prepared_track_render_model_scope", source)
        self.assertIn("track_world_mechanically_rejected", source)
        self.assertIn("track_world_mechanical_rejection_reasons", source)
        self.assertIn("prepared_procedural_color_producer", source)
        self.assertIn("procedural_color_producer_requests", source)
        self.assertIn("procedural_color_producer_target_failures", source)
        self.assertIn("procedural_color_target_failure_reasons", source)
        self.assertIn(
            "request.frame_accumulator_source = "
            "exact_procedural_color_producer",
            source,
        )
        self.assertIn("ContinuousWorldRetainedTargetIdentity", source)
        self.assertIn("current_retained_target_identity", source)
        self.assertIn("target_reseed_requests", source)
        self.assertIn("procedural_color_target_reseed_requests", source)
        self.assertIn(
            "current_retained_target_identity ==\n"
            "            retained_target_identity",
            source,
        )

        self.assertIn(
            ".track_command_lineage = exact_track_command", source
        )
        self.assertIn("!exact_track_world &&", source)
        self.assertIn(
            "prepared_track_world_resource_shared_identity_mask", source
        )
        self.assertIn("prepared_static_world_exact", source)
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_STATIC_WORLD", source
        )
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_TRACK_WORLD", source
        )
        self.assertIn(
            "track_world_environment == 0 && prototype_selected", source
        )
        self.assertIn("kTrackTextureUnifiedVtable = 0x82001708", source)
        self.assertIn("non_track_provider_rejections", source)
        self.assertIn('"native_renderer.continuous_world_workset.summary"', source)
        self.assertIn(
            '"native_renderer.continuous_world_workset.checkpoint"', source
        )
        self.assertIn('{"xenos_draw", "preserved"}', source)
        self.assertIn('{"draw_suppression", "false"}', source)

        patch = (
            ROOT
            / "patches/rexglue/0094-d3d12-deferred-replay-preview-publication.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("CommitDeferredIsolatedReplayPreview", patch)
        self.assertIn("CancelDeferredIsolatedReplayPreview", patch)
        self.assertIn("defer_preview_publication_until_swap", patch)
        self.assertIn("observation_frame_sequence_", patch)
        self.assertNotIn("suppress_guest_draw_if_published = true", patch)

        capture = (ROOT / "tools/capture-native-renderer-census.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[switch]$ContinuousWorldWorkset", capture)
        self.assertIn("[switch]$ContinuousTrackWorld", capture)
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_WORLD_WORKSET", capture
        )

    def test_rexglue_reports_isolated_target_failure_detail(self):
        patch = (
            ROOT
            / "patches/rexglue/0112-d3d12-isolated-target-failure-detail.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("GraphicsIsolatedDrawTargetFailure", patch)
        self.assertIn("kDepthTargetCreationFailed", patch)
        self.assertIn("kColorTargetCreationFailed", patch)
        self.assertIn("kRetainedTargetMismatch", patch)
        self.assertIn("isolated_result.target_failure", patch)

    def test_accumulator_requires_exact_private_source_ownership(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0113-d3d12-procedural-accumulator-source-ownership.patch"
        ).read_text(encoding="utf-8")
        result_patch = (
            ROOT
            / "patches/rexglue/0114-isolated-replay-result-source-identity.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("frame_accumulator_source", patch)
        self.assertIn("kUnqualifiedSource", patch)
        self.assertIn(
            "isolated_replay_frame_accumulator_source_frame_sequence_", patch
        )
        self.assertIn("unqualified_source", source)
        self.assertIn(
            "g_procedural_frame_accumulator_exact_source_frame", source
        )
        self.assertIn(
            "CompleteContinuousWorldProceduralSourceReplay", source
        )
        self.assertIn(
            '"source_gate", "same_frame_recorded_exact_procedural_replay"',
            source,
        )
        self.assertIn("isolated_result.frame_sequence", result_patch)
        self.assertIn("isolated_result.frame_accumulator_source", result_patch)
        self.assertIn("result.frame_sequence", source)
        self.assertIn("result.frame_accumulator_source", source)
        self.assertNotIn(
            "g_procedural_frame_accumulator_pending_source_frame", source
        )

    def test_accumulator_reports_scaled_source_topology(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0115-d3d12-frame-accumulator-topology-result.patch"
        ).read_text(encoding="utf-8")
        for field in (
            "source_resource_width",
            "source_resource_height",
            "source_sample_count",
            "source_guest_msaa_samples",
            "draw_resolution_scale_x",
            "draw_resolution_scale_y",
            "native_2x_msaa",
        ):
            self.assertIn(field, patch)
            self.assertIn(field, source)
        self.assertIn("isolated_color->key().msaa_samples", patch)

    def test_resolve_census_reports_authoritative_source_topology(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0116-d3d12-resolve-source-topology-observation.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("PopulateCopySourceTopology", patch)
        self.assertIn("last_update_accumulated_render_targets", patch)
        self.assertIn("source_target_available", patch)
        self.assertIn("source_guest_msaa_samples", patch)
        self.assertIn('"source_resource_extent"', source)
        self.assertIn('"draw_scale"', source)

    def test_resolve_census_reports_derived_source_region(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0117-d3d12-resolve-region-topology-observation.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("copy_observation_resolve_info_", patch)
        self.assertIn("resolve_info.coordinate_info.width_div_8", patch)
        self.assertIn("resolve_info.height_div_8", patch)
        self.assertIn("copy_sample_select", patch)
        self.assertIn('"resolve_guest_rect"', source)
        self.assertIn('"resolve_physical_rect"', source)
        self.assertIn('"resolve_destination"', source)

    def test_isolated_replay_reports_scaled_geometry(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0118-d3d12-isolated-replay-geometry-result.patch"
        ).read_text(encoding="utf-8")
        for field in (
            "logical_width",
            "logical_height",
            "draw_resolution_scale_x",
            "draw_resolution_scale_y",
        ):
            self.assertIn(field, patch)
            self.assertIn(field, source)
        self.assertIn('"procedural_source_logical_extent"', source)
        self.assertIn('"procedural_source_target_extent"', source)
        self.assertIn('"procedural_source_draw_scale"', source)

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

    def test_scaled_layout_crosses_accumulator_backend_contract(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "patches/rexglue/0119-d3d12-accumulator-source-layout-request.patch"
        ).read_text(encoding="utf-8")
        for field in (
            "source_x",
            "source_y",
            "source_width",
            "source_height",
            "copy_row_count",
            "padding_row_count",
            "sample_select",
        ):
            self.assertIn(field, patch)
            self.assertIn(f"request_out.{field}", source)
        self.assertIn("requested_source_x", patch)
        self.assertIn('"requested_source_rect"', source)
        self.assertIn('"requested_rows"', source)
        self.assertIn("!physical_layout.ready()", source)

    def test_exact_track_color_only_replay_is_private_and_bounded(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("const bool exact_track_color_only", source)
        self.assertIn("observation.bound_render_target_bits == 2", source)
        self.assertIn("~kIsolatedRejectRenderTargets", source)
        self.assertIn("request.color_only_target", source)
        self.assertIn("exact_track_world &&", source)

        patch = (
            ROOT
            / "patches/rexglue/0106-d3d12-color-only-isolated-replay.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("bool color_only_target = false", patch)
        self.assertIn("depth_only_target && color_only_target", patch)
        self.assertIn("color_only_target && guest_targets[0]", patch)
        self.assertIn("color_only_target\n+          ? nullptr", patch)
        self.assertIn("guest_targets[1]", patch)
        self.assertNotIn("SetDrawSuppression", patch)

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
