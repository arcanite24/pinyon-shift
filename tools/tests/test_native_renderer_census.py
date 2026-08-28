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
    def test_classifier_matches_scene_rules_and_bounds_drift(self):
        events = [
            {"event": "native_renderer.census.installed", "session": "run"},
            {
                "event": "native_renderer.census.scene_marker",
                "session": "run",
                "scene": "front_end",
            },
            {
                "event": "native_renderer.census.draw_signature",
                "session": "run",
                "signature": "KNOWN",
                "draws": "99",
            },
            {
                "event": "native_renderer.census.draw_signature",
                "session": "run",
                "signature": "DRIFT_B",
                "draws": "2",
            },
            {
                "event": "native_renderer.census.draw_signature",
                "session": "run",
                "signature": "DRIFT_A",
                "draws": "3",
            },
        ]
        classifier = {
            "schema": "pinyon-shift.pass-classifier.v1",
            "maximum_drift_records": 1,
            "rules": [
                {
                    "scene": "front_end",
                    "family": "front_end_observed",
                    "confidence": "medium",
                    "evidence": "test evidence",
                    "signatures": ["KNOWN"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "events.jsonl"
            manifest = Path(temp) / "classifier.json"
            log.write_text(
                "\n".join(json.dumps(event) for event in events) + "\n",
                encoding="utf-8",
            )
            manifest.write_text(json.dumps(classifier), encoding="utf-8")
            result = MODULE.summarize([log], classifier_path=manifest)

        classification = result["classification"]
        self.assertEqual("front_end", classification["scene"])
        self.assertEqual(99, classification["classified_draws"])
        self.assertEqual(2, classification["drift_count"])
        self.assertEqual(1, classification["drift_overflow"])
        self.assertEqual("DRIFT_A", classification["drift"][0]["signature"])
        self.assertEqual(
            "retained_unknown", result["draw_signatures"][1]["family"]
        )

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
