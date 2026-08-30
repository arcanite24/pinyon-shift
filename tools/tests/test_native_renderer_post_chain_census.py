import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build-native-renderer-post-chain-census.py"
SPEC = importlib.util.spec_from_file_location("native_post_chain_census", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def target(identifier):
    return {
        "resource_id": identifier,
        "resource_name": identifier,
        "width": 1280,
        "height": 720,
        "format": "R8G8B8A8_UNORM",
    }


def draw(event_id, output, index_count=3):
    return {
        "event_id": event_id,
        "kind": "draw",
        "index_count": index_count,
        "instance_count": 1,
        "pipeline": "pipeline-{}".format(event_id),
        "pipeline_name": "pipeline {}".format(event_id),
        "vertex_shader": "vs",
        "vertex_shader_name": "vs",
        "pixel_shader": "ps",
        "pixel_shader_name": "ps",
        "primitive_topology": "TriangleList",
        "viewport": {"enabled": True, "width": 1280.0, "height": 720.0},
        "scissor": {"enabled": True, "width": 1280, "height": 720},
        "depth_state": {"writes": False},
        "raster_state": {"cull_mode": "NoCull"},
        "color_targets": [target(output)],
        "depth_target": None,
        "isolated_native": False,
    }


def pass_trace(events, capture="A" * 64):
    return {
        "schema": MODULE.PASS_SCHEMA,
        "capture": {"path": "fixture.rdc", "sha256": capture},
        "events": events,
        "safety": {"resource_payload_exported": False},
    }


def resource(identifier, usages):
    return {**target(identifier), "usages": usages}


def target_usage(resources, capture="A" * 64, transfers=None):
    return {
        "schema": MODULE.USAGE_SCHEMA,
        "capture": {"path": "fixture.rdc", "sha256": capture},
        "resources": resources,
        "transfers": [] if transfers is None else transfers,
        "safety": {
            "resource_payload_exported": False,
            "action_metadata_only": True,
        },
    }


class NativeRendererPostChainCensusTests(unittest.TestCase):
    def test_builds_presentation_reachable_fullscreen_chain(self):
        events = [draw(10, "scene", 100), draw(20, "post"), draw(30, "swap")]
        resources = [
            resource("scene", [
                {"event_id": 10, "usage": "ColorTarget"},
                {"event_id": 20, "usage": "PS_Resource"},
            ]),
            resource("post", [
                {"event_id": 20, "usage": "ColorTarget"},
                {"event_id": 30, "usage": "PS_Resource"},
            ]),
            resource("swap", [
                {"event_id": 30, "usage": "ColorTarget"},
                {"event_id": 40, "usage": "Present"},
            ]),
        ]
        result = MODULE.build_census(target_usage(resources), pass_trace(events))
        self.assertEqual(result["presentation_reachable_events"], [10, 20, 30])
        self.assertEqual(
            [item["event_id"] for item in result["fullscreen_candidates"]],
            [20, 30],
        )
        self.assertEqual(result["totals"]["resource_edges"], 2)
        self.assertTrue(result["qualification"]["presentation_topology_observed"])
        self.assertTrue(result["qualification"]["presentation_ingress_resolved"])
        self.assertFalse(result["qualification"]["effect_semantics_proven"])
        self.assertFalse(result["safety"]["suppression_allowed"])

    def test_uses_most_recent_draw_write_for_a_read(self):
        events = [draw(10, "ping"), draw(11, "ping"), draw(20, "swap")]
        resources = [
            resource("ping", [
                {"event_id": 10, "usage": "ColorTarget"},
                {"event_id": 11, "usage": "ColorTarget"},
                {"event_id": 20, "usage": "PS_Resource"},
            ]),
            resource("swap", [
                {"event_id": 20, "usage": "ColorTarget"},
                {"event_id": 30, "usage": "Present"},
            ]),
        ]
        result = MODULE.build_census(target_usage(resources), pass_trace(events))
        self.assertEqual(result["edges"][0]["producer_event"], 11)
        self.assertNotIn(10, result["presentation_reachable_events"])

    def test_correlates_swapchain_target_with_later_present_boundary(self):
        event = draw(20, "swap")
        event["color_targets"][0]["resource_name"] = "Swapchain Image 1"
        boundary = {
            "event_id": 30,
            "kind": "boundary",
            "boundary_kinds": ["present"],
        }
        swap = resource(
            "swap", [{"event_id": 20, "usage": "ColorTarget"}]
        )
        swap["resource_name"] = "Swapchain Image 1"
        result = MODULE.build_census(
            target_usage([swap]), pass_trace([event, boundary])
        )
        self.assertEqual(result["presentation_reachable_events"], [20])
        self.assertEqual(
            result["presentation_sinks"][0]["present_source"],
            "swapchain_name_and_boundary",
        )
        self.assertFalse(result["qualification"]["presentation_ingress_resolved"])
        self.assertEqual(result["presentation_source_boundaries"], [20])

    def test_records_copy_or_missing_producers_as_unresolved(self):
        events = [draw(20, "swap")]
        resources = [
            resource("copied", [
                {"event_id": 10, "usage": "CopyDst"},
                {"event_id": 20, "usage": "PS_Resource"},
            ]),
            resource("swap", [
                {"event_id": 20, "usage": "ColorTarget"},
                {"event_id": 30, "usage": "Present"},
            ]),
        ]
        result = MODULE.build_census(target_usage(resources), pass_trace(events))
        self.assertEqual(result["totals"]["unresolved_reads"], 1)
        self.assertEqual(result["unresolved_reads"][0]["last_write_usage"], "CopyDst")
        self.assertFalse(result["qualification"]["native_implementation_ready"])

    def test_follows_copy_destination_back_to_draw_producer(self):
        events = [draw(10, "scene", 100), draw(20, "swap")]
        resources = [
            resource("scene", [
                {"event_id": 10, "usage": "ColorTarget"},
                {"event_id": 15, "usage": "CopySrc"},
            ]),
            resource("resolved", [
                {"event_id": 15, "usage": "CopyDst"},
                {"event_id": 20, "usage": "PS_Resource"},
            ]),
            resource("swap", [
                {"event_id": 20, "usage": "ColorTarget"},
                {"event_id": 30, "usage": "Present"},
            ]),
        ]
        transfers = [{
            "event_id": 15,
            "kind": "copy",
            "source_resource_id": "scene",
            "destination_resource_id": "resolved",
        }]
        result = MODULE.build_census(
            target_usage(resources, transfers=transfers), pass_trace(events)
        )
        self.assertEqual(result["edges"][0]["producer_event"], 10)
        self.assertEqual(result["presentation_reachable_events"], [10, 20])
        self.assertEqual(result["totals"]["transfers"], 1)

    def test_rejects_capture_drift_and_unsafe_inputs(self):
        with self.assertRaisesRegex(ValueError, "captures differ"):
            MODULE.build_census(target_usage([], "A" * 64), pass_trace([], "B" * 64))
        unsafe = target_usage([])
        unsafe["safety"]["resource_payload_exported"] = True
        with self.assertRaisesRegex(ValueError, "payload-free"):
            MODULE.build_census(unsafe, pass_trace([]))


if __name__ == "__main__":
    unittest.main()
