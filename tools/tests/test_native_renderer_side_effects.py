import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-side-effects.py"
SPEC = importlib.util.spec_from_file_location("native_side_effects", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def static_inventory():
    return {
        "schema": MODULE.STATIC_SCHEMA,
        "reviewed_wrappers": [
            {"kind": "viz_query_owner"},
            {"kind": "resolve_controller"},
            {"kind": "binning_state_reset"},
        ],
        "query_owner_lifecycle": {"owner": "82D951E0"},
        "side_effect_packets": {"semantic_identity": "unknown"},
    }


def events(safe=True):
    return [
        {
            "event": "native_renderer.discovery.dispatch_config",
            "session": "run",
            "status": "armed",
            "scene": "race",
        },
        {
            "event": "native_renderer.census.resolve_window",
            "session": "run",
            "first_frame": "1",
            "last_frame": "300",
            "resolves": "40",
            "resolve_bytes": "4096",
            "query_draws": "3",
            "memexport_draws": "2",
            "target_overflow": "0",
            "page_overflow": "0",
        },
        {
            "event": "native_renderer.discovery.dispatch_caller",
            "session": "run",
            "wrapper": "viz_query_owner",
            "calls": "9",
        },
        {
            "event": "native_renderer.discovery.dispatch_summary",
            "session": "run",
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false" if safe else "true",
        },
    ]


class NativeRendererSideEffectTests(unittest.TestCase):
    def test_summarizes_side_effects_without_promoting_semantics(self):
        document = MODULE.build(events(), static_inventory())
        self.assertEqual(document["scene"], "race")
        self.assertEqual(document["totals"]["query_draws"], 3)
        self.assertEqual(document["totals"]["memexport_draws"], 2)
        self.assertEqual(
            document["wrapper_activity"]["viz_query_owner"]["calls"], 9
        )
        self.assertEqual(document["query"]["semantic_identity"], "unknown")
        self.assertEqual(
            document["memexport"]["guest_side_effect"],
            "preserved_on_xenos",
        )
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_rejects_unsafe_or_overlapping_evidence(self):
        with self.assertRaisesRegex(ValueError, "passive safety"):
            MODULE.build(events(safe=False), static_inventory())
        overlapping = events()
        overlapping.insert(
            2,
            {
                "event": "native_renderer.census.resolve_window",
                "session": "run",
                "first_frame": "300",
                "last_frame": "600",
            },
        )
        with self.assertRaisesRegex(ValueError, "overlapping"):
            MODULE.build(overlapping, static_inventory())

    def test_uses_unobserved_not_absent_for_zero_counts(self):
        zero = events()
        zero[1]["query_draws"] = "0"
        zero[1]["memexport_draws"] = "0"
        document = MODULE.build(zero, static_inventory())
        self.assertEqual(
            document["query"]["draw_observation"], "unobserved_not_absent"
        )
        self.assertEqual(
            document["memexport"]["draw_observation"],
            "unobserved_not_absent",
        )


if __name__ == "__main__":
    unittest.main()
