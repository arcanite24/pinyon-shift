import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "qualify-native-renderer-state-yield.py"
SPEC = importlib.util.spec_from_file_location("native_state_yield", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def event(name, **fields):
    return {"schema": 1, "session": "session", "event": name, **fields}


def log_events():
    return [
        event("process.start", executable_sha256="A" * 64),
        event(
            "native_renderer.suppression_control",
            requested="true",
            status="armed_experimental",
            state_gate="consecutive_publication_warmup",
            warmup_frames="8",
            failure_cooldown_frames="120",
        ),
        event(
            "native_renderer.suppression_state",
            previous="warming",
            current="active",
            reason="warmup_complete",
        ),
        event(
            "native_renderer.retained_pass.publication_summary",
            attempts="28",
            published="28",
            failures="0",
        ),
        event(
            "native_renderer.suppression_summary",
            status="active",
            runtime_state="active",
            attempts="20",
            suppressed="20",
            fallbacks="0",
            unexpected_suppressions="0",
            yielded_attempts="8",
            warmup_publications="8",
            cooldown_entries="0",
            anchor_draw="preserved",
            pm4_parsing="preserved",
            query_event_fence="preserved",
            memexport="preserved",
            resolves_consumers="preserved",
            resolve_suppression="false",
        ),
        event("process.shutdown"),
    ]


class NativeRendererStateYieldQualificationTests(unittest.TestCase):
    def qualify(self, events):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.jsonl"
            path.write_text(
                "".join(json.dumps(item) + "\n" for item in events),
                encoding="utf-8",
            )
            return MODULE.qualify(path)

    def test_accepts_warmup_yield_then_active_suppression(self):
        result = self.qualify(log_events())
        self.assertEqual("pass", result["gate"]["state_based_yield"])
        self.assertEqual("pass", result["gate"]["guest_side_effects"])
        self.assertEqual(8, result["state_gate"]["yielded_attempts"])
        self.assertEqual(20, result["suppression"]["suppressed"])

    def test_rejects_missing_warmup_transition_or_yield(self):
        events = log_events()
        del events[2]
        with self.assertRaisesRegex(ValueError, "warmup-to-active"):
            self.qualify(events)

        events = log_events()
        events[4]["yielded_attempts"] = "0"
        with self.assertRaisesRegex(ValueError, "never yielded"):
            self.qualify(events)

    def test_rejects_fallback_cooldown_or_side_effect_drift(self):
        events = log_events()
        events[4]["suppressed"] = "19"
        events[4]["fallbacks"] = "1"
        with self.assertRaisesRegex(ValueError, "fail-closed"):
            self.qualify(events)

        events = log_events()
        events[4]["cooldown_entries"] = "1"
        with self.assertRaisesRegex(ValueError, "cooldown"):
            self.qualify(events)

        events = log_events()
        events[4]["memexport"] = "unknown"
        with self.assertRaisesRegex(ValueError, "memexport"):
            self.qualify(events)

        events = log_events()
        events[4]["unexpected_suppressions"] = "1"
        with self.assertRaisesRegex(ValueError, "state gate yielded"):
            self.qualify(events)


if __name__ == "__main__":
    unittest.main()
