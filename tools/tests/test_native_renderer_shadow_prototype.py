import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererShadowPrototypeTests(unittest.TestCase):
    def test_prototype_arms_observers_without_hidden_census_settings(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("bool NativePrototypeSelected()", source)
        self.assertIn(
            "observation_requested = census_requested || prototype_selected", source
        )
        self.assertIn("title_provenance_requested", source)
        self.assertIn(
            "shadow_depth_prototype_mode = NativePrototypeSelected()", source
        )
        self.assertIn("shadow_depth_batch_mode = true", source)
        self.assertIn("shadow_depth_publication_mode = true", source)
        self.assertIn("shadow_depth_continuous_mode = true", source)

    def test_shadow_members_bypass_world_workset_and_publish_fail_closed(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "!g_isolated_draw.prepared_shadow_depth_batch_member", source
        )
        self.assertIn("!g_isolated_draw.shadow_depth_batch_active", source)
        self.assertIn("prepared_shadow_depth_seed_eligible", source)
        self.assertIn("prototype_current_frame_fail_closed", source)
        self.assertIn("g_native_shadow_publication_frame.store", source)
        self.assertIn("g_native_shadow_fail_closed.store", source)
        self.assertIn("request.suppress_guest_draw_if_published = false", source)

    def test_output_reports_native_and_xenos_fallback_shadow_states(self):
        output = (ROOT / "src/native_renderer/guest_output_renderer.cpp").read_text(
            encoding="utf-8"
        )
        for marker in (
            "native_current_frame",
            "fallback_xenos_unavailable",
            "fallback_xenos_failed_closed",
            "xenos_rt_dump_retained",
        ):
            self.assertIn(marker, output)

    def test_checkpoint_documents_exact_consumer_and_preserved_xenos_path(self):
        document = (
            ROOT / "docs/native-renderer/NATIVE_SHADOW_PROTOTYPE_INTEGRATION.md"
        ).read_text(encoding="utf-8")
        self.assertIn("80-draw", document)
        self.assertIn("xenos_rt_dump_retained", document)
        self.assertIn("No draw or resolve suppression", document)
        self.assertIn("batched Phase B6", document)


if __name__ == "__main__":
    unittest.main()
