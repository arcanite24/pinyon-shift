import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererPrototypePresentationTests(unittest.TestCase):
    def test_prototype_selector_arms_workset_and_full_source_output(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        output = (ROOT / "src/native_renderer/guest_output_renderer.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn('== "native_prototype"', hooks)
        self.assertIn("requested = prototype_selected", hooks)
        self.assertIn('mode != "native_prototype"', output)
        self.assertIn("kPrototypeNative", output)
        self.assertIn('"continuous_world_passthrough"', output)
        self.assertIn(
            '"logical_scene_scale_then_title_gamma_then_title_upscale"', output
        )

    def test_prototype_fails_closed_outside_qualified_draw_scale(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        output = (ROOT / "src/native_renderer/guest_output_renderer.cpp").read_text(
            encoding="utf-8"
        )
        for source in (hooks, output):
            self.assertIn("draw_resolution_scale_x", source)
            self.assertIn("draw_resolution_scale_y", source)
            self.assertIn('"unsupported_draw_resolution_scale"', source)
            self.assertIn('{"fallback", "xenos"}', source)
        self.assertIn("NativePrototypeScaleSupported()", hooks)
        self.assertIn('"prototype_observers"', hooks)
        self.assertIn("if (prototype_mode &&", output)
        self.assertLess(
            output.index("if (prototype_mode &&"),
            output.index("SetNativeGuestOutputRenderer"),
        )

    def test_rexglue_patch_preserves_legacy_preview_and_adds_passthrough(self):
        patch = (
            ROOT
            / "patches/rexglue/0095-d3d12-native-prototype-presentation.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("kPrototypeNative = 3", patch)
        self.assertIn("uint presentation_mode", patch)
        self.assertIn("if (presentation_mode == 1)", patch)
        self.assertIn("output_position * source_size / output_size", patch)
        self.assertIn("preview_size = min(output_size.x, output_size.y)", patch)
        self.assertNotIn("SetDrawSuppression", patch)

    def test_hybrid_patch_corrects_padded_allocation_mapping(self):
        patch = (
            ROOT
            / "patches/rexglue/0096-d3d12-conservative-hybrid-composition.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("kLogicalSceneWidth = 512", patch)
        self.assertIn("kLogicalSceneHeight = 288", patch)
        self.assertIn("output_position * crop_size / output_size", patch)
        self.assertIn("native_guest_output_linear_target_", patch)

    def test_launcher_and_settings_expose_explicit_prototype_and_comparison(self):
        settings = (ROOT / "tools/set-graphics-experiment.ps1").read_text(
            encoding="utf-8"
        )
        launcher = (
            ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml"
        ).read_text(encoding="utf-8")
        for mode in ("native_prototype", "comparison_native", "comparison_xenos"):
            self.assertIn(mode, settings)
            self.assertIn(f'Tag="{mode}"', launcher)


if __name__ == "__main__":
    unittest.main()
