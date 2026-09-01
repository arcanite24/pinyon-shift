import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class TrackPresentationPassTests(unittest.TestCase):
    def test_adjacent_unified_passes_have_balanced_hooks(self):
        analysis = (
            ROOT / "config/rexglue/analysis/main-xex.toml"
        ).read_text(encoding="utf-8")
        hooks = {
            78: ("0x82DEEEE0", "0x82DEF2A4"),
            79: ("0x8240E7B0", "0x8240ED40"),
            80: ("0x82DEF2B0", "0x82DEFE78"),
            81: ("0x82DEADE0", "0x82DEAEE8"),
        }
        for slot, (entry, exit_) in hooks.items():
            self.assertIn(f"address = {entry}", analysis)
            self.assertIn(
                f'name = "PinyonShiftObserveTrackPresentationSlot{slot}Entry"',
                analysis,
            )
            self.assertIn(f"address = {exit_}", analysis)
            self.assertIn(
                f'name = "PinyonShiftObserveTrackPresentationSlot{slot}Exit"',
                analysis,
            )

    def test_pass_census_is_observation_only_and_shutdown_bounded(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "kTrackPresentationUnifiedVtable = 0x82243774", source
        )
        self.assertIn("BeginTrackPresentationPass", source)
        self.assertIn("EndTrackPresentationPass", source)
        self.assertIn(
            '"native_renderer.discovery.track_presentation_pass_summary"',
            source,
        )
        self.assertIn('"native_admission", "false"', source)
        self.assertIn('"xenos_authority", "true"', source)
        self.assertIn('"suppression_allowed", "false"', source)

    def test_prepared_layout_exports_exact_target_shape(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        prepared = source.split(
            "void EmitTrackWorldPreparedLayoutEntries()", 1
        )[1].split("std::string SerializeStaticWorldTransform", 1)[0]
        self.assertIn('"bound_render_target_bits"', prepared)
        self.assertIn('"bound_render_target_formats"', prepared)
        self.assertIn('"prepared_pipeline_flags"', prepared)


if __name__ == "__main__":
    unittest.main()
