import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererPrototypeComparisonTests(unittest.TestCase):
    def test_comparison_modes_use_prototype_presentation(self):
        patch = (
            ROOT
            / "patches/rexglue/0097-d3d12-native-prototype-comparison.patch"
        ).read_text(encoding="utf-8")
        output = (ROOT / "src/native_renderer/guest_output_renderer.cpp").read_text(
            encoding="utf-8"
        )
        for mode in ("kPrototypeCompareNative", "kPrototypeCompareXenos"):
            self.assertIn(mode, patch)
            self.assertIn(mode, output)
        self.assertIn("prototype ? 1u : 0u", patch)
        self.assertNotIn("SetDrawSuppression", patch)

    def test_comparison_self_arms_world_and_shadow_observation(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        prototype_selector = hooks.split("bool NativePrototypeSelected()", 1)[1]
        prototype_selector = prototype_selector.split("}", 1)[0]
        for mode in (
            'mode == "native_prototype"',
            'mode == "hybrid_prototype"',
            'mode == "comparison_native"',
            'mode == "comparison_xenos"',
        ):
            self.assertIn(mode, prototype_selector)

    def test_depth_only_replay_preserves_deferred_color_preview(self):
        patch = (
            ROOT
            / "patches/rexglue/0098-d3d12-preserve-color-preview-across-depth-replay.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("bool depth_only_target = false", patch)
        self.assertIn("if (!depth_only_target)", patch)
        self.assertIn("if (depth_only_target)", patch)
        self.assertIn("-    isolated_replay_color_target_.reset();", patch)
        self.assertIn("isolated_draw_request.depth_only_target", patch)
        self.assertNotIn("SetDrawSuppression", patch)

    def test_device_loss_diagnostics_are_flushed_before_fatal_callback(self):
        patch = (
            ROOT
            / "patches/rexglue/0099-d3d12-flush-device-loss-diagnostics.patch"
        ).read_text(encoding="utf-8")
        diagnostic = patch.index("LogDeviceRemovalDiagnostics")
        flush = patch.index("rex::FlushLogging()")
        callback = patch.index("OnHostGpuLossFromAnyThread")
        self.assertLess(diagnostic, flush)
        self.assertLess(flush, callback)

    def test_shadow_replay_uses_a_separate_depth_target_lifetime(self):
        patch = (
            ROOT
            / "patches/rexglue/0100-d3d12-separate-depth-only-replay-target.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("isolated_replay_depth_only_target_", patch)
        self.assertIn("isolated_replay_active_depth_target_", patch)
        self.assertIn(
            "depth_only_target ? isolated_replay_depth_only_target_", patch
        )
        self.assertIn("isolated_replay_depth_target_", patch)
        self.assertNotIn("SetDrawSuppression", patch)

    def test_retained_preview_failures_are_actionable(self):
        patch = (
            ROOT
            / "patches/rexglue/0101-d3d12-report-retained-preview-failures.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("linear target allocation failed", patch)
        self.assertIn("retained-pass preview unavailable for frame", patch)
        self.assertIn("retained-pass preview is smaller than the", patch)
        self.assertIn('"logical scene:', patch)

        output = (ROOT / "src/native_renderer/guest_output_renderer.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn('"retained_pass_callback_failed"', output)
        self.assertIn("context.retained_pass_frame_sequence !=", output)

    def test_retained_preview_separates_backing_and_logical_extents(self):
        patch = (
            ROOT
            / "patches/rexglue/0102-d3d12-track-retained-preview-logical-extent.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("source_out.width = uint32_t(resource_desc.Width)", patch)
        self.assertIn("source_out.logical_width", patch)
        self.assertIn("isolated_replay_active_preview_width_", patch)
        self.assertIn("isolated_replay_deferred_preview_width_", patch)
        self.assertIn(
            "isolated_replay_preview_width_ = isolated_replay_deferred_preview_width_",
            patch,
        )
        self.assertIn("prototype ? preview_source.logical_width", patch)
        self.assertIn("prototype ? preview_source.logical_height", patch)
        self.assertIn("saturated_extent_end(viewport_info.xy_offset[0]", patch)
        self.assertIn("saturated_extent_end(scissor.offset[0]", patch)
        self.assertNotIn("SetDrawSuppression", patch)

    def test_continuous_workset_uses_only_the_qualified_retained_seed(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "g_isolated_draw.prepared_signature == kSkyHorizonFollowerSignature",
            hooks,
        )
        self.assertIn("qualified_retained_family_requests", hooks)
        self.assertIn(
            "fresh_track_texture_provider_visibility_or_qualified_sky_horizon_or_optional_exact_track_or_static_world_and_mechanical",
            hooks,
        )
        self.assertIn("static_world_requested = false", hooks)
        self.assertIn("prepared_static_world_exact", hooks)
        self.assertIn("!g_isolated_draw.prepared_candidate_eligible", hooks)

    def test_capture_does_not_inject_legacy_isolated_draw_configuration(self):
        capture = (
            ROOT / "tools/capture-native-renderer-output-comparison.ps1"
        ).read_text(encoding="utf-8")
        self.assertNotIn("IsolatedDrawSignature", capture)
        self.assertNotIn("PassAnchorSignature", capture)
        self.assertNotIn("IsolatedDrawDir", capture)
        self.assertIn("-CaptureDir $CaptureDir -Scene $Scene", capture)
        self.assertIn("finally", capture)

    def test_checkpoint_defers_expensive_qualification_to_b6(self):
        document = (
            ROOT / "docs/native-renderer/NATIVE_PROTOTYPE_COMPARISON.md"
        ).read_text(encoding="utf-8")
        self.assertIn("same-frame boundary", document)
        self.assertIn("native-output-comparison.json", document)
        self.assertIn("batched into B6", document)
        self.assertIn("Xenos stays default", document)


if __name__ == "__main__":
    unittest.main()
