import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererHybridPrototypeTests(unittest.TestCase):
    def test_hybrid_selector_arms_workset_and_reports_safe_authority(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        output = (ROOT / "src/native_renderer/guest_output_renderer.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn('== "hybrid_prototype"', hooks)
        self.assertIn('mode != "hybrid_prototype"', output)
        self.assertIn("kPrototypeHybrid", output)
        self.assertIn('"conservative_pixel_agreement_hybrid"', output)
        self.assertIn(
            '"logical_scene_scale_then_title_gamma_then_title_upscale"', output
        )


    def test_launcher_exposes_complete_frame_hybrid_as_explicit_preview(self):
        settings = (ROOT / "tools/set-graphics-experiment.ps1").read_text(
            encoding="utf-8"
        )
        launcher = (
            ROOT / "launcher/PinyonShift.Launcher/MainWindow.xaml"
        ).read_text(encoding="utf-8")
        self.assertIn("'hybrid_prototype'", settings)
        self.assertIn('Tag="hybrid_prototype"', launcher)
        self.assertIn("Xenos-safe complete frame", launcher)


if __name__ == "__main__":
    unittest.main()
