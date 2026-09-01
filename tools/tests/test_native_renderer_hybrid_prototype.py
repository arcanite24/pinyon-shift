import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererHybridPrototypeTests(unittest.TestCase):
    def test_minimal_producer_graph_retains_native_replay_observers(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("minimal_producer_graph_requested", source)
        self.assertIn("SetCopyObserver(&ObservePrototypeResolveCopy)", source)
        for observer in (
            "SetDrawObserver(&ObserveDraw)",
            "SetPreparedDrawObserver(&ObservePreparedDraw)",
            "SetIndirectBufferObserver(&ObserveIndirectBuffer)",
            "SetDrawOutcomeObserver(&ObserveDrawOutcome)",
            "SetIsolatedDrawRequestObserver(&RequestIsolatedDraw)",
        ):
            self.assertIn(observer, source)
        self.assertIn('"native_replay_producer", "retained"', source)
        self.assertIn('"xenos_draw", "preserved"', source)
        self.assertNotIn("PublishIsolatedReplayTarget", source)

    def test_prototype_skips_discovery_only_hotpath_work(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("vehicle_shader_constant_observer_requested", source)
        self.assertIn(
            "g_vehicle_discovery_installed.load(std::memory_order_acquire) &&",
            source,
        )
        self.assertIn('"draw_signature_scope"', source)
        self.assertIn('"producer_required_only"', source)
        self.assertIn("g_graphics_full_census_armed ||", source)
        self.assertIn("g_shadow_caster_provenance.requested", source)

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
