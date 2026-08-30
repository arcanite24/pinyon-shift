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
        selection="fresh_visibility_or_qualified_sky_horizon_and_mechanical",
        maximum_draws_per_frame="64",
        target_lifetime="one_guest_frame",
        freshness_commit="matching_swap_after_complete_accumulation",
        semantic_lineage="armed",
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
        prepared_observations="17",
        requests="8",
        recorded="8",
        target_creation_failures="0",
        unsupported="0",
        mechanical_rejections="4",
        stale_or_unselected_rejections="3",
        per_frame_quota_yields="2",
        fail_closed_yields="0",
        qualified_retained_family_requests="2",
        reused_target_requests="6",
        frames_started="2",
        frames_completed="2",
        frames_failed="0",
        accounting_complete="true",
        selection_accounting_complete="true",
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
        self.assertIn('"native_renderer.continuous_world_workset.summary"', source)
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
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_WORLD_WORKSET", capture
        )

    def test_qualifies_complete_multi_draw_worksets(self):
        document = MODULE.build(fixture())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["continuous_multi_draw_workset_proved"]
        )
        self.assertFalse(document["qualification"]["suppression_allowed"])

    def test_rejects_single_draw_frames(self):
        events = fixture()
        events[-1]["reused_target_requests"] = "0"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "no frame accumulated multiple native draws", document["failures"]
        )

    def test_qualifies_an_accounted_fail_closed_frame(self):
        events = fixture()
        events[-1].update(
            status="fallback_observed",
            recorded="7",
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
