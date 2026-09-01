import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-color-producer-lineage.py"
SPEC = importlib.util.spec_from_file_location("color_producer_lineage", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    session = "session"
    common = {"session": session}
    config = {
        **common,
        "event": MODULE.CONFIG,
        "prepared_target_shape_census": "bounded_aggregate_v1",
    }
    entry = {
        **common,
        "event": MODULE.ENTRY,
        "calls": "12",
        "depth_only_draws": "2",
        "color_only_draws": "8",
        "color_depth_draws": "2",
        "other_target_draws": "0",
        "other_color_draws": "0",
        "opaque_color_draws": "9",
        "bounded_color_draws": "10",
        "resolved_input_color_draws": "0",
        "constructor_function_address": "82416A00",
        "owner_function_address": "824167F8",
        "producer_function_address": "82417060",
        "context_function_address": "82417BC0",
        "semantic_receiver_class": "proceduralGeometry::CProceduralModels",
        "track_command_lineage": "false",
        "sample_color_prepared_signature": "0123456789ABCDEF",
        "color_sample_varied": "true",
        "sample_color_vertex_shader": "1111111111111111",
        "sample_color_pixel_shader": "2222222222222222",
        "sample_color_bound_render_target_bits": "00000002",
        "sample_color_bound_render_target_formats": "0:1:0:0:0",
        "sample_color_prepared_pipeline_flags": "00000003",
        "sample_color_target_state": "1:2:3:4:5:6",
        "sample_color_scissor": "00000000:050002D0",
    }
    summary = {
        **common,
        "event": MODULE.SUMMARY,
        "entries": "1",
        "prepared_draws": "12",
        "invalid_lineages": "0",
        "overflow": "0",
        "indirect_buffer_stack_faults": "0",
        "indirect_draw_stack_faults": "0",
        "indirect_constructor_stack_faults": "0",
        "indirect_constructor_owner_mismatches": "0",
        "indirect_owner_stack_faults": "0",
        "indirect_owner_producer_mismatches": "0",
        "indirect_producer_stack_faults": "0",
        "indirect_producer_context_mismatches": "0",
        "indirect_context_stack_faults": "0",
    }
    shutdown = {**common, "event": MODULE.SHUTDOWN}
    return [config, entry, summary, shutdown]


class ColorProducerLineageTests(unittest.TestCase):
    def test_ranks_exact_semantic_color_candidate(self):
        result = MODULE.build(fixture(), "session")
        self.assertEqual("complete", result["status"])
        self.assertEqual(10, result["totals"]["color_draws"])
        self.assertEqual("82417BC0", result["candidates"][0]["context_function"])
        self.assertTrue(result["qualification"]["semantic_color_candidate_observed"])
        self.assertFalse(result["qualification"]["native_admission"])

    def test_fails_closed_on_target_accounting_drift(self):
        events = fixture()
        events[1]["color_only_draws"] = "7"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn(
            "entry target-shape accounting is incomplete", result["failures"]
        )


if __name__ == "__main__":
    unittest.main()
