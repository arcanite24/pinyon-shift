import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build-native-renderer-pass-inventory.py"
SPEC = importlib.util.spec_from_file_location("native_pass_inventory", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def target(resource_id, width=640, height=8192):
    return {
        "resource_id": resource_id,
        "width": width,
        "height": height,
        "mip": 0,
        "slice": 0,
        "format": "R8G8B8A8_UNORM",
    }


def draw(event_id, color="ResourceId::1", **fields):
    event = {
        "event_id": event_id,
        "kind": "draw",
        "index_count": 3,
        "instance_count": 1,
        "color_targets": [target(color)],
        "depth_target": target("ResourceId::2"),
        "isolated_native": False,
        "authoritative_candidate": False,
    }
    event.update(fields)
    return event


def trace(events, payload_exported=False):
    return {
        "schema": MODULE.TRACE_SCHEMA,
        "capture": {"path": "fixture.rdc", "sha256": "A" * 64},
        "events": events,
        "safety": {"resource_payload_exported": payload_exported},
    }


class NativeRendererPassInventoryTests(unittest.TestCase):
    def test_groups_contiguous_xenos_draws_and_ignores_native_replay(self):
        inventory = MODULE.build_inventory(trace([
            draw(10),
            draw(11, isolated_native=True),
            draw(12, authoritative_candidate=True),
            draw(13),
        ]))
        self.assertEqual(inventory["totals"]["phases"], 1)
        self.assertEqual(inventory["totals"]["draws"], 3)
        self.assertEqual(inventory["totals"]["isolated_native_draws_ignored"], 1)
        self.assertEqual(inventory["totals"]["authoritative_candidate_draws"], 1)
        self.assertEqual(inventory["phases"][0]["candidate_draw_count"], 1)
        self.assertFalse(inventory["phases"][0]["suppression_eligible"])

    def test_splits_on_explicit_boundary_and_target_change(self):
        inventory = MODULE.build_inventory(trace([
            draw(1),
            {"event_id": 2, "kind": "boundary", "boundary_kinds": ["clear"]},
            draw(3),
            draw(4, color="ResourceId::9"),
        ]))
        self.assertEqual(inventory["totals"]["phases"], 3)
        self.assertEqual(inventory["phases"][1]["boundary_before"], ["clear"])
        self.assertEqual(inventory["phases"][2]["boundary_before"], [])

    def test_preserves_exact_enriched_pipeline_signatures(self):
        event = draw(
            1,
            pipeline="ResourceId::10",
            pipeline_name="Pipeline 10",
            vertex_shader="ResourceId::11",
            vertex_shader_name="Shader {11111111}",
            pixel_shader=None,
            pixel_shader_name=None,
            primitive_topology="TriangleList",
            viewport={"width": 1024.0, "height": 1024.0},
            scissor={"width": 1024, "height": 1024},
            depth_state={"enabled": True, "writes": True},
            raster_state={"cull_mode": "Back"},
        )
        inventory = MODULE.build_inventory(trace([event, dict(event, event_id=2)]))
        signatures = inventory["phases"][0]["pipeline_signatures"]
        self.assertEqual(1, len(signatures))
        self.assertEqual(2, signatures[0]["draw_count"])
        self.assertEqual("ResourceId::10", signatures[0]["signature"]["pipeline"])
        self.assertEqual(
            "Shader {11111111}",
            signatures[0]["signature"]["vertex_shader_name"],
        )

    def test_rejects_payload_export_and_unordered_events(self):
        with self.assertRaisesRegex(ValueError, "payload-free"):
            MODULE.build_inventory(trace([], payload_exported=True))
        with self.assertRaisesRegex(ValueError, "monotonically"):
            MODULE.build_inventory(trace([draw(2), draw(1)]))

    def test_rejects_unknown_schema_and_event_kind(self):
        document = trace([])
        document["schema"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unsupported"):
            MODULE.build_inventory(document)
        with self.assertRaisesRegex(ValueError, "unknown event"):
            MODULE.build_inventory(trace([{"event_id": 1, "kind": "mystery"}]))


if __name__ == "__main__":
    unittest.main()
