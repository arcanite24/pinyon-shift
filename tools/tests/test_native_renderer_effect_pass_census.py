import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build-native-renderer-effect-pass-census.py"
SPEC = importlib.util.spec_from_file_location("effect_pass_census", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def draw(event_id, colors=True, depth=True, writes=True, isolated=False):
    target = {
        "resource_id": "ResourceId::1",
        "resource_name": "target",
        "width": 1024,
        "height": 1024,
        "mip": 0,
        "slice": 0,
        "format": "D32_FLOAT",
    }
    return {
        "event_id": event_id,
        "kind": "draw",
        "index_count": 3,
        "instance_count": 1,
        "pipeline": "ResourceId::10",
        "pipeline_name": "Pipeline 10",
        "vertex_shader": "ResourceId::11",
        "vertex_shader_name": "Shader {11111111}",
        "pixel_shader": None,
        "pixel_shader_name": None,
        "primitive_topology": "TriangleList",
        "viewport": {"width": 1024.0, "height": 1024.0},
        "scissor": {"width": 1024, "height": 1024},
        "depth_state": {"enabled": True, "writes": writes},
        "raster_state": {"cull_mode": "Back"},
        "color_targets": [target] if colors else [],
        "depth_target": target if depth else None,
        "isolated_native": isolated,
    }


def trace(events, metadata=True, payload=False):
    return {
        "schema": MODULE.TRACE_SCHEMA,
        "capture": {"path": "fixture.rdc", "sha256": "A" * 64},
        "events": events,
        "safety": {
            "resource_payload_exported": payload,
            "pipeline_metadata_only": metadata,
        },
    }


class EffectPassCensusTests(unittest.TestCase):
    def test_groups_exact_metadata_and_keeps_semantics_closed(self):
        census = MODULE.build_census(
            trace([draw(1, colors=False), draw(2, colors=False), draw(3)])
        )
        self.assertEqual(3, census["totals"]["draws"])
        self.assertEqual(2, census["totals"]["families"])
        self.assertEqual(
            2,
            census["totals"]["draws_by_output_class"][
                "depth_only_write_candidate"
            ],
        )
        self.assertTrue(
            all(
                item["semantic_role"] == "unknown_unclassified"
                and not item["native_coverage"]
                and not item["suppression_eligible"]
                for item in census["families"]
            )
        )
        self.assertFalse(census["qualification"]["shadow_pass_identified"])
        self.assertFalse(
            census["qualification"]["reflection_pass_identified"]
        )

    def test_ignores_native_draws_and_sorts_deterministically(self):
        census = MODULE.build_census(
            trace([draw(1), draw(2, colors=False), draw(3, isolated=True)])
        )
        self.assertEqual(2, census["totals"]["draws"])
        self.assertEqual(1, census["totals"]["isolated_native_draws_ignored"])
        self.assertEqual(
            sorted(
                census["families"],
                key=lambda item: (-item["draw_count"], item["sha256"]),
            ),
            census["families"],
        )

    def test_rejects_unsafe_or_unenriched_trace(self):
        with self.assertRaisesRegex(ValueError, "payload-free"):
            MODULE.build_census(trace([], payload=True))
        with self.assertRaisesRegex(ValueError, "enriched"):
            MODULE.build_census(trace([], metadata=False))
        event = draw(1)
        event.pop("viewport")
        with self.assertRaisesRegex(ValueError, "missing enriched"):
            MODULE.build_census(trace([event]))

    def test_rejects_unknown_or_unordered_events(self):
        with self.assertRaisesRegex(ValueError, "unknown event"):
            MODULE.build_census(
                trace([{"event_id": 1, "kind": "mystery"}])
            )
        with self.assertRaisesRegex(ValueError, "monotonically"):
            MODULE.build_census(trace([draw(2), draw(1)]))


if __name__ == "__main__":
    unittest.main()
