import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "qualify-native-renderer-rollback.py"
SPEC = importlib.util.spec_from_file_location("native_rollback", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


SHA = "A" * 64


def event(name, **fields):
    return {"schema": 1, "session": "session", "event": name, **fields}


def logs():
    enabled = [
        event("process.start", executable_sha256=SHA),
        event(
            "native_renderer.suppression_control",
            requested="true",
            status="armed_experimental",
            implementation="fail_closed_follower_draw",
            resolve_suppression="false",
        ),
        event(
            "native_renderer.retained_pass.publication_summary",
            attempts="20",
            published="20",
            failures="0",
        ),
        event(
            "native_renderer.suppression_summary",
            status="active",
            attempts="12",
            suppressed="12",
            fallbacks="0",
            yielded_attempts="8",
            anchor_draw="preserved",
            resolve_suppression="false",
        ),
        event("process.shutdown"),
    ]
    disabled = [
        event("process.start", executable_sha256=SHA),
        event("native_renderer.suppression_control", requested="false", status="disabled"),
        event("process.shutdown"),
    ]
    return enabled, disabled


class NativeRendererRollbackQualificationTests(unittest.TestCase):
    def qualify(self, enabled, disabled):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            enabled_path = root / "enabled.jsonl"
            disabled_path = root / "disabled.jsonl"
            enabled_path.write_text("".join(json.dumps(item) + "\n" for item in enabled), encoding="utf-8")
            disabled_path.write_text("".join(json.dumps(item) + "\n" for item in disabled), encoding="utf-8")
            return MODULE.qualify(enabled_path, disabled_path)

    def test_accepts_same_build_enabled_and_disabled_pair(self):
        enabled, disabled = logs()
        result = self.qualify(enabled, disabled)
        self.assertEqual(result["gate"]["rollback_switch"], "pass")
        self.assertEqual(result["enabled"]["suppressed"], 12)
        self.assertEqual(result["enabled"]["yielded_attempts"], 8)
        self.assertEqual(result["disabled"]["suppressed"], 0)
        self.assertTrue(result["safety"]["anchor_xenos_draw_preserved"])
        self.assertFalse(result["safety"]["resolve_suppression_implemented"])

    def test_rejects_fallback_or_partial_publication(self):
        enabled, disabled = logs()
        enabled[3]["suppressed"] = "11"
        enabled[3]["fallbacks"] = "1"
        with self.assertRaisesRegex(ValueError, "not every enabled attempt"):
            self.qualify(enabled, disabled)

        enabled, disabled = logs()
        enabled[2]["published"] = "19"
        with self.assertRaisesRegex(ValueError, "publication was incomplete"):
            self.qualify(enabled, disabled)

    def test_rejects_build_drift_and_failed_rollback(self):
        enabled, disabled = logs()
        disabled[0]["executable_sha256"] = "B" * 64
        with self.assertRaisesRegex(ValueError, "same executable"):
            self.qualify(enabled, disabled)

        enabled, disabled = logs()
        disabled.insert(
            -1,
            event(
                "native_renderer.retained_pass.publication",
                draw_suppression="follower",
            ),
        )
        with self.assertRaisesRegex(ValueError, "still suppressed"):
            self.qualify(enabled, disabled)


if __name__ == "__main__":
    unittest.main()
