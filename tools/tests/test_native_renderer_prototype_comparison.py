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
