import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-procedural-color-targets.py"
SPEC = importlib.util.spec_from_file_location("procedural_color_targets", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(scissor_extent="0:0:1280:720", predicated="false"):
    common = {"session": "session"}
    return [
        {
            **common,
            "event": MODULE.CONFIG,
            "procedural_color_target_profile_census": "bounded_exact_v2",
            "procedural_color_target_profile_bin_state": "exact_backend_v1",
        },
        {
            **common,
            "event": MODULE.ENTRY,
            "calls": "12",
            "opaque_calls": "12",
            "bounded_calls": "12",
            "resolved_input_calls": "0",
            "prepared_signature": "751139AF66FBCCF4",
            "vertex_shader": "D3EE3BD1E086935B",
            "pixel_shader": "CE7C54664D18A4E3",
            "bound_render_target_bits": "00000003",
            "bound_render_target_formats": "1:3:0:0:0",
            "target_state": "1:2:3:4:5:6",
            "viewport": "1:2:3:4",
            "scissor": "00000000:02D00500",
            "scissor_extent": scissor_extent,
            "predicated": predicated,
            "bin_select": "0000000000000004",
            "bin_mask": "000000000000000C",
            "bin_intersection": "0000000000000004",
            "semantic_receiver_varied": "true",
        },
        {
            **common,
            "event": MODULE.SUMMARY,
            "observations": "12",
            "accounted": "12",
            "entries": "1",
            "overflow": "0",
            "accounting_complete": "true",
        },
        {**common, "event": MODULE.SHUTDOWN},
    ]


class ProceduralColorTargetTests(unittest.TestCase):
    def test_promotes_exact_full_preview_profile_to_capture_selection(self):
        result = MODULE.build(fixture(), "session")
        self.assertEqual("complete", result["status"])
        self.assertEqual("full_preview_extent", result["profiles"][0]["role"])
        self.assertTrue(
            result["qualification"]["eligible_for_isolated_capture_selection"]
        )
        self.assertFalse(result["qualification"]["native_admission"])

    def test_reduced_height_profile_stays_out_of_selection(self):
        result = MODULE.build(fixture("0:0:1280:256"), "session")
        self.assertEqual("reduced_preview_width", result["profiles"][0]["role"])
        self.assertFalse(
            result["qualification"]["eligible_for_isolated_capture_selection"]
        )

    def test_predicated_reduced_height_profile_is_edram_tile(self):
        result = MODULE.build(fixture("0:0:1280:256", "true"), "session")
        self.assertEqual("predicated_edram_tile", result["profiles"][0]["role"])
        self.assertTrue(
            result["qualification"]["eligible_for_tile_assembly_investigation"]
        )
        self.assertFalse(
            result["qualification"]["eligible_for_isolated_capture_selection"]
        )

    def test_fails_closed_on_accounting_drift(self):
        events = fixture()
        events[2]["accounted"] = "11"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn("observations do not match accounted profiles", result["failures"])


if __name__ == "__main__":
    unittest.main()
