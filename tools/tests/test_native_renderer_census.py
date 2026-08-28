import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_renderer_census",
    ROOT / "tools/summarize-native-renderer-census.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NativeRendererCensusTests(unittest.TestCase):
    def test_summarizer_selects_latest_session_and_merges_dependencies(self):
        events = [
            {"event": "native_renderer.census.installed", "session": "old"},
            {"event": "native_renderer.census.draw_window", "session": "old", "draws": "9"},
            {"event": "native_renderer.census.installed", "session": "new"},
            {
                "event": "native_renderer.census.draw_window",
                "session": "new",
                "draws": "100",
                "overflow_draws": "0",
            },
            {
                "event": "native_renderer.census.resolve_window",
                "session": "new",
                "resolves": "7",
                "resolve_bytes": "4096",
                "sampled_draws": "3",
                "sample_references": "4",
                "query_draws": "1",
                "memexport_draws": "2",
                "target_overflow": "0",
                "page_overflow": "0",
            },
            {
                "event": "native_renderer.census.resolve_dependency",
                "session": "new",
                "address": "00123000",
                "length": "4096",
                "suppression_eligible": "false",
            },
            {
                "event": "native_renderer.census.resolve_target",
                "session": "new",
                "address": "00123000",
                "last_resolve_frame": "42",
                "resolves": "7",
                "resolved_bytes": "28672",
                "sampled_draws": "3",
                "sample_references": "4",
                "conditional_sample_draws": "1",
                "query_state_sample_draws": "0",
                "memexport_sample_draws": "2",
            },
        ]
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "events.jsonl"
            log.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )
            result = MODULE.summarize([log])

        self.assertEqual("new", result["session"])
        self.assertEqual(100, result["totals"]["draws"])
        self.assertEqual(7, result["totals"]["resolves"])
        self.assertEqual("7", result["resolve_dependencies"][0]["resolves"])
        self.assertFalse(result["safety"]["suppression_allowed"])

    def test_summarizer_rejects_missing_session(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "events.jsonl"
            log.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.summarize([log])


if __name__ == "__main__":
    unittest.main()
