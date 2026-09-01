import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-procedural-resolve-assembly.py"
SPEC = importlib.util.spec_from_file_location("procedural_resolve_assembly", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    common = {"session": "session"}
    events = [
        {
            **common,
            "event": MODULE.CONFIG,
            "procedural_color_resolve_source_state": "exact_backend_v1",
        },
        {
            **common,
            "event": MODULE.PROFILE,
            "first_frame": "100",
            "last_frame": "110",
            "target_state": (
                "14020500:00030000:00000000:00000000:00000000:00010400"
            ),
        },
        {
            **common,
            "event": MODULE.PROFILE_SUMMARY,
            "accounting_complete": "true",
        },
    ]
    base = 0x1C4E1000
    lengths = [1280 * 256 * 4, 1280 * 256 * 4, 1280 * 224 * 4]
    for length in lengths:
        events.append(
            {
                **common,
                "event": MODULE.RESOLVE,
                "address": f"{base:08X}",
                "length": str(length),
                "last_resolve_frame": "110",
                "copy_source": "0",
                "copy_source_state": "14020500:00030000",
                "copy_state": "00100360:003E0382:02D00500:14020500",
            }
        )
        base += length
    events.append({**common, "event": MODULE.SHUTDOWN})
    return events


class ProceduralResolveAssemblyTests(unittest.TestCase):
    def test_runtime_exports_exact_copy_source_state(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn('{"copy_source", number(copy_source)}', source)
        self.assertIn('{"copy_source_state",', source)
        self.assertIn('{"copy_source_targets",', source)
        self.assertIn(
            '{"procedural_color_resolve_source_state", "exact_backend_v1"}',
            source,
        )

    def test_qualifies_three_contiguous_resolves_as_full_frame(self):
        result = MODULE.build(fixture(), "session")
        self.assertEqual("complete", result["status"])
        assembly = result["assemblies"][0]
        self.assertEqual(3, assembly["copy_count"])
        self.assertEqual(1280, assembly["pitch_width"])
        self.assertEqual(720, assembly["logical_height"])
        self.assertEqual(736, assembly["padded_height"])
        self.assertEqual(16, assembly["padding_rows"])
        self.assertTrue(assembly["exact_contiguous_full_frame"])
        self.assertTrue(
            result["qualification"]["exact_procedural_color_resolve_assembly"]
        )
        self.assertFalse(
            result["qualification"]["standalone_1280x256_publication_allowed"]
        )

    def test_rejects_gap_between_resolve_chunks(self):
        events = fixture()
        events[5]["address"] = "1C762000"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn(
            "no exact contiguous full-frame color resolve assembly",
            result["failures"],
        )

    def test_fails_closed_without_exact_source_state_capability(self):
        events = fixture()
        del events[0]["procedural_color_resolve_source_state"]
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn("exact resolve source state was not armed", result["failures"])

    def test_ignores_depth_resolves(self):
        events = fixture()
        for event in events:
            if event.get("event") == MODULE.RESOLVE:
                event["copy_source"] = "4"
                event["copy_source_state"] = "14020500:00010400"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertEqual([], result["assemblies"])


if __name__ == "__main__":
    unittest.main()
