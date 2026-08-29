import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-dispatch.py"
SPEC = importlib.util.spec_from_file_location("native_dispatch_summary", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def static_inventory():
    return {
        "schema": MODULE.STATIC_SCHEMA,
        "direct_calls": [
            {
                "wrapper": "8240F4D8",
                "return_address": "82B2BD78",
                "caller_function": "sub_82B2B180",
                "caller_function_address": "82B2B180",
                "callsite": "82B2BD74",
            }
        ],
    }


def events(safe=True):
    summary = {
        "event": "native_renderer.discovery.dispatch_summary",
        "session": "run",
        "tracked_callers": "1",
        "tracked_calls": "12",
        "overflow_calls": "0",
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false" if safe else "true",
    }
    return [
        {
            "event": "native_renderer.discovery.dispatch_config",
            "session": "run",
            "status": "armed",
        },
        {
            "event": "native_renderer.discovery.dispatch_frame",
            "session": "run",
            "frame_sequence": "300",
        },
        {
            "event": "native_renderer.discovery.dispatch_caller",
            "session": "run",
            "wrapper": "draw_indexed",
            "wrapper_address": "8240F4D8",
            "caller": "82B2BD78",
            "calls": "12",
            "first_frame": "4",
            "first_r3": "10000000",
            "first_r4": "00000004",
            "first_r5": "00000000",
        },
        summary,
    ]


class NativeRendererDispatchSummaryTests(unittest.TestCase):
    def test_correlates_runtime_lr_with_static_callsite(self):
        document = MODULE.build(events(), static_inventory())
        self.assertEqual(document["frames_observed"], 300)
        self.assertEqual(document["totals"]["tracked_calls"], 12)
        self.assertEqual(document["totals"]["static_matches"], 1)
        self.assertEqual(
            document["callers"][0]["static_match"]["callsite"], "82B2BD74"
        )
        self.assertEqual(document["callers"][0]["semantic_identity"], "unknown")
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_rejects_unsafe_or_incomplete_summary(self):
        with self.assertRaisesRegex(ValueError, "safety"):
            MODULE.build(events(safe=False), static_inventory())
        mismatch = events()
        mismatch[-1]["tracked_calls"] = "13"
        with self.assertRaisesRegex(ValueError, "counts"):
            MODULE.build(mismatch, static_inventory())

    def test_requires_armed_session(self):
        disabled = events()
        disabled[0]["status"] = "disabled"
        with self.assertRaisesRegex(ValueError, "armed"):
            MODULE.build(disabled, static_inventory())


if __name__ == "__main__":
    unittest.main()
