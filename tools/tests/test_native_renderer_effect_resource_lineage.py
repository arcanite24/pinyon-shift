import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "build-native-renderer-effect-resource-lineage.py"
SPEC = importlib.util.spec_from_file_location("effect_resource_lineage", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


CAPTURE = {"path": "fixture.rdc", "sha256": "A" * 64}


def usage_trace(usages, *, payload=False, metadata=True):
    return {
        "schema": MODULE.USAGE_SCHEMA,
        "capture": CAPTURE,
        "resource": {"resource_name": "depth"},
        "usages": usages,
        "safety": {
            "resource_payload_exported": payload,
            "action_metadata_only": metadata,
        },
    }


def draw(event_id, pixel="Shader {pixel}"):
    return {
        "event_id": event_id,
        "kind": "draw",
        "isolated_native": False,
        "pipeline": "ResourceId::1",
        "pipeline_name": "pipeline",
        "vertex_shader": "ResourceId::2",
        "vertex_shader_name": "Shader {vertex}",
        "pixel_shader": "ResourceId::3",
        "pixel_shader_name": pixel,
        "primitive_topology": "TriangleList",
        "viewport": {"width": 1024, "height": 1024},
        "color_targets": [],
        "depth_target": {"resource_name": "consumer-depth"},
    }


def pass_trace(events, sha="A" * 64):
    return {
        "schema": MODULE.PASS_SCHEMA,
        "capture": {"path": "fixture.rdc", "sha256": sha},
        "events": events,
        "safety": {"resource_payload_exported": False},
    }


def effect_census(families, sha="A" * 64):
    return {
        "schema": MODULE.EFFECT_CENSUS_SCHEMA,
        "capture": {"path": "fixture.rdc", "sha256": sha},
        "families": families,
        "safety": {"metadata_only": True, "suppression_allowed": False},
    }


class EffectResourceLineageTests(unittest.TestCase):
    def test_proves_fully_sampled_depth_epochs_but_not_semantics(self):
        usages = [
            {"event_id": 1, "usage": "Clear"},
            {"event_id": 2, "usage": "DepthStencilTarget"},
            {"event_id": 3, "usage": "PS_Resource"},
            {"event_id": 4, "usage": "Clear"},
            {"event_id": 5, "usage": "DepthStencilTarget"},
            {"event_id": 6, "usage": "CS_Resource"},
            {"event_id": 6, "usage": "CS_Resource"},
        ]
        report = MODULE.build_lineage(usage_trace(usages), pass_trace([draw(3)]))
        self.assertEqual(2, report["totals"]["clear_epochs"])
        self.assertEqual(2, report["totals"]["sampled_epochs"])
        self.assertEqual(1, report["totals"]["consumer_families"])
        self.assertTrue(
            report["qualification"]["depth_producer_consumer_chain_proved"]
        )
        self.assertTrue(
            report["qualification"][
                "depth_to_depth_propagation_chain_proved"
            ]
        )
        self.assertFalse(
            report["qualification"]["direct_color_sampling_observed"]
        )
        self.assertEqual(1, report["totals"]["pixel_consumers_depth_only"])
        self.assertEqual(0, report["totals"]["pixel_consumers_with_color"])
        self.assertFalse(report["qualification"]["shadow_semantic_proved"])
        self.assertFalse(report["qualification"]["reflection_semantic_proved"])
        self.assertFalse(report["consumer_families"][0]["native_coverage"])
        self.assertFalse(report["consumer_families"][0]["suppression_eligible"])

    def test_keeps_incomplete_epoch_unqualified(self):
        usages = [
            {"event_id": 1, "usage": "Clear"},
            {"event_id": 2, "usage": "DepthStencilTarget"},
        ]
        report = MODULE.build_lineage(usage_trace(usages), pass_trace([]))
        self.assertFalse(
            report["qualification"]["depth_producer_consumer_chain_proved"]
        )
        self.assertFalse(
            report["qualification"][
                "depth_to_depth_propagation_chain_proved"
            ]
        )

    def test_joins_exact_shadow_caster_families_into_epochs(self):
        usages = [
            {"event_id": 1, "usage": "Clear"},
            {"event_id": 2, "usage": "DepthStencilTarget"},
            {"event_id": 3, "usage": "DepthStencilTarget"},
            {"event_id": 4, "usage": "CS_Resource"},
        ]
        census = effect_census(
            [
                {
                    "sha256": "B" * 64,
                    "event_ids": [2, 3],
                    "semantic_role": "shadow_depth",
                    "caster_class": "dynamic_vehicle",
                    "atlas_region": {
                        "x": 0,
                        "y": 0,
                        "width": 2048,
                        "height": 2048,
                    },
                }
            ]
        )
        report = MODULE.build_lineage(
            usage_trace(usages), pass_trace([]), census
        )
        epoch = report["epochs"][0]
        self.assertEqual(2, epoch["classified_shadow_write_count"])
        self.assertEqual(2, report["totals"]["classified_shadow_writes"])
        self.assertEqual(0, epoch["unclassified_write_count"])
        self.assertEqual(["dynamic_vehicle"], epoch["caster_classes"])
        self.assertTrue(epoch["caster_class_complete"])
        self.assertEqual(1, len(epoch["producer_families"]))
        self.assertEqual(
            1, report["qualification"]["caster_complete_epochs"]
        )
        self.assertEqual(
            ["dynamic_vehicle"],
            report["qualification"]["caster_classes_identified"],
        )
        self.assertFalse(
            report["qualification"]["static_dynamic_caster_separation_ready"]
        )
        self.assertTrue(
            report["qualification"]["producer_caster_inventory_joined"]
        )
        self.assertTrue(report["qualification"]["shadow_semantic_proved"])
        self.assertFalse(
            report["qualification"]["reflection_semantic_proved"]
        )

    def test_reports_color_sampling_without_promoting_semantics(self):
        usages = [
            {"event_id": 1, "usage": "Clear"},
            {"event_id": 2, "usage": "DepthStencilTarget"},
            {"event_id": 3, "usage": "PS_Resource"},
        ]
        event = draw(3)
        event["color_targets"] = [{"resource_name": "scene-color"}]
        event["depth_target"] = None
        report = MODULE.build_lineage(usage_trace(usages), pass_trace([event]))
        self.assertTrue(
            report["qualification"]["direct_color_sampling_observed"]
        )
        self.assertFalse(
            report["qualification"][
                "depth_to_depth_propagation_chain_proved"
            ]
        )
        self.assertFalse(report["qualification"]["shadow_semantic_proved"])

    def test_requires_complete_dynamic_and_static_epochs_for_separation(self):
        usages = [
            {"event_id": 1, "usage": "Clear"},
            {"event_id": 2, "usage": "DepthStencilTarget"},
            {"event_id": 3, "usage": "CS_Resource"},
            {"event_id": 4, "usage": "Clear"},
            {"event_id": 5, "usage": "DepthStencilTarget"},
            {"event_id": 6, "usage": "CS_Resource"},
        ]
        census = effect_census(
            [
                {
                    "sha256": "B" * 64,
                    "event_ids": [2],
                    "semantic_role": "shadow_depth",
                    "caster_class": "dynamic_vehicle",
                    "atlas_region": {"x": 0, "y": 0, "width": 2, "height": 2},
                },
                {
                    "sha256": "C" * 64,
                    "event_ids": [5],
                    "semantic_role": "shadow_depth",
                    "caster_class": "static_world",
                    "atlas_region": {"x": 0, "y": 0, "width": 1, "height": 1},
                },
            ]
        )
        report = MODULE.build_lineage(
            usage_trace(usages), pass_trace([]), census
        )
        self.assertTrue(
            report["qualification"]["static_dynamic_caster_separation_ready"]
        )

    def test_rejects_missing_consumer_metadata_and_capture_drift(self):
        usages = [
            {"event_id": 1, "usage": "Clear"},
            {"event_id": 2, "usage": "DepthStencilTarget"},
            {"event_id": 3, "usage": "PS_Resource"},
        ]
        with self.assertRaisesRegex(ValueError, "no authoritative draw"):
            MODULE.build_lineage(usage_trace(usages), pass_trace([]))
        with self.assertRaisesRegex(ValueError, "captures differ"):
            MODULE.build_lineage(
                usage_trace(usages), pass_trace([draw(3)], sha="B" * 64)
            )
        with self.assertRaisesRegex(ValueError, "census capture differs"):
            MODULE.build_lineage(
                usage_trace(usages),
                pass_trace([draw(3)]),
                effect_census([], sha="B" * 64),
            )

    def test_rejects_unsafe_or_unordered_usage(self):
        with self.assertRaisesRegex(ValueError, "payload-free"):
            MODULE.build_lineage(usage_trace([], payload=True), pass_trace([]))
        with self.assertRaisesRegex(ValueError, "action-metadata-only"):
            MODULE.build_lineage(
                usage_trace([], metadata=False), pass_trace([])
            )
        with self.assertRaisesRegex(ValueError, "monotonically"):
            MODULE.build_lineage(
                usage_trace(
                    [
                        {"event_id": 2, "usage": "Clear"},
                        {"event_id": 1, "usage": "Clear"},
                    ]
                ),
                pass_trace([]),
            )

    def test_export_contract_is_payload_free_and_local_only(self):
        exporter = (
            ROOT / "tools/export-native-renderer-resource-usage.py"
        ).read_text(encoding="utf-8")
        wrapper = (
            ROOT / "tools/export-native-renderer-resource-usage.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("controller.GetUsage(resource.resourceId)", exporter)
        self.assertIn('"resource_payload_exported": False', exporter)
        self.assertIn('"action_metadata_only": True', exporter)
        self.assertIn("if len(matches) != 1", exporter)
        self.assertIn("Get-AuthenticodeSignature", wrapper)
        self.assertIn("must be below $localRoot", wrapper)
        self.assertIn("ResourceName must not be empty", wrapper)


if __name__ == "__main__":
    unittest.main()
