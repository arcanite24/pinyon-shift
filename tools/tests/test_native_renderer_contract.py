import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class NativeRendererContractTests(unittest.TestCase):
    def test_graphics_hook_has_one_pass_through_owner(self):
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(analysis.count('name = "PinyonShiftObserveGraphicsFrame"'), 1)
        hook = analysis.split('name = "PinyonShiftObserveGraphicsFrame"', 1)[0]
        hook = hook.rsplit("[[midasm_hook]]", 1)[1]
        self.assertIn("address = 0x829EFEB8", hook)
        self.assertNotIn("jump_address", hook)
        self.assertNotIn("after_instruction", hook)
        self.assertNotIn("registers", hook)

    def test_census_is_default_off_and_bounded(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("pinyon_shift_native_renderer_census, false", source)
        self.assertIn("kFrameSummaryInterval = 300", source)
        self.assertIn("kSignatureCapacity = 4096", source)
        self.assertIn("kSummaryLimit = 16", source)
        self.assertIn("unique_signature_count", source)
        self.assertIn("overflow_draw_count", source)
        self.assertIn("kRequiresRestart", source)
        self.assertIn('"mode", "pass_through"', source)
        self.assertNotIn("REX_STORE", source)
        self.assertNotIn("GuestPtr", source)

    def test_draw_observer_is_read_only_and_contains_no_payload(self):
        patch = (ROOT / "patches/rexglue/0044-graphics-draw-observer.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn("GraphicsDrawObservation", patch)
        self.assertIn("auto draw_observer = graphics_system_->draw_observer();", patch)
        self.assertIn("if (draw_observer) {", patch)
        self.assertIn("draw_observer(observation);", patch)
        self.assertLess(
            patch.index("draw_observer(observation);"),
            patch.index("draw_succeeded = IssueDraw"),
        )
        self.assertLess(
            patch.index("if (draw_observer) {"),
            patch.index("GraphicsDrawObservation observation;"),
        )
        self.assertIn("vertex_shader_hash", patch)
        self.assertIn("pixel_shader_hash", patch)
        self.assertIn("vertex_memexport", patch)
        for forbidden in ("shader_code", "texture_data", "vertex_data", "payload"):
            self.assertNotIn(forbidden, patch)

        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        signature = source.split("DrawSignature(", 1)[1].split(
            "EmitDrawCensusWindow", 1
        )[0]
        self.assertIn("observation.primitive_type", signature)
        self.assertIn("observation.source_select", signature)
        self.assertNotIn("observation.initiator", signature)

    def test_first_pr_has_no_native_renderer_or_suppression_api(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        forbidden = ("native_rhi", "NativeRHI", "IssueDraw", "IssueCopy", "suppress")
        for token in forbidden:
            self.assertNotIn(token, source)

        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertEqual(cmake.count("src/native_renderer/graphics_hooks.cpp"), 2)

    def test_census_ledger_tracks_exact_starting_baseline(self):
        ledger = (ROOT / "docs/native-renderer/RENDER_PASS_CENSUS.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("cafc7233fef9e039f163d11023f40eccb22e8fc1", ledger)
        self.assertIn("f5337cdc947ff6d4c4196737e2c807a48f2a1fc2", ledger)
        self.assertIn("Unknown work stays on Xenos.", ledger)


if __name__ == "__main__":
    unittest.main()
