import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/discover-native-renderer-track-presentation-callgraph.py"
SPEC = importlib.util.spec_from_file_location("track_presentation_callgraph", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TrackPresentationCallgraphTests(unittest.TestCase):
    def test_parses_direct_and_indirect_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "pinyon_shift_recomp.0.cpp"
            path.write_text(
                "DEFINE_REX_FUNC(sub_82000010) {\n"
                "  sub_82000020(ctx, base);\n"
                "  REX_CALL_INDIRECT_FUNC(ctx.ctr.u32);\n"
                "}\n"
                "DEFINE_REX_FUNC(sub_82000020) {\n}\n",
                encoding="utf-8",
            )
            graph, indirect = MODULE.parse_generated([path])
        self.assertEqual((0x82000020,), graph[0x82000010])
        self.assertEqual(1, indirect[0x82000010])

    def test_ranks_shortest_exact_sink_path(self):
        wrapper_slots = [0x82000010] * MODULE.SLOT_COUNT
        unified_slots = list(wrapper_slots)
        graph = {
            0x82000010: (0x82000020,),
            0x82000020: (0x82416380,),
            0x82416380: (),
        }
        document = MODULE.build(graph, {}, unified_slots, wrapper_slots)
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            ["82000010", "82000020", "82416380"],
            document["candidates"][0]["sink_paths"]["direct_indexed_draw"],
        )
        self.assertFalse(document["qualification"]["runtime_activity_proved"])

    def test_rejects_incomplete_vtable(self):
        with self.assertRaisesRegex(ValueError, "vtable length"):
            MODULE.build({}, {}, [0], [0])


if __name__ == "__main__":
    unittest.main()
