import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build-native-renderer-presentation-ingress.py"
SPEC = importlib.util.spec_from_file_location("native_presentation_ingress", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def bindings(usages=None, capture="A" * 64):
    return {
        "schema": MODULE.BINDING_SCHEMA,
        "capture": {"path": "capture.rdc", "sha256": capture},
        "presentation": {
            "draw_event": 30,
            "present_event": 40,
            "output_resource_id": "swap",
            "output_resource_name": "Swapchain Image 1",
            "output": {
                "resource_id": "swap",
                "resource_name": "Swapchain Image 1",
                "resource_kind": "texture",
                "width": 3840,
                "height": 2160,
                "format": "B8G8R8A8_UNORM",
            },
        },
        "bindings": [{
            "resource_id": "input",
            "resource_name": "2D Texture 1",
            "resource_kind": "texture",
            "width": 2560,
            "height": 1440,
            "format": "R10G10B10A2_UNORM",
            "view_format": "R10G10B10A2_UNORM",
            "stage": "ShaderStage.Pixel",
            "descriptor_type": "DescriptorType.Image",
            "index": 0,
            "array_element": 0,
            "statically_unused": False,
            "usages": (
                [{"event_id": 30, "usage": "PS_Resource"}]
                if usages is None
                else usages
            ),
        }],
        "safety": {
            "resource_payload_exported": False,
            "action_metadata_only": True,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def census(capture="A" * 64):
    return {
        "schema": MODULE.POST_SCHEMA,
        "capture": {"path": "capture.rdc", "sha256": capture},
        "presentation_sinks": [{
            "resource_id": "swap",
            "producer_event": 30,
            "present_event": 40,
        }],
        "safety": {
            "metadata_only": True,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


class NativeRendererPresentationIngressTests(unittest.TestCase):
    def test_proves_uniform_upscale_but_keeps_guest_lineage_closed(self):
        result = MODULE.build_ingress(bindings(), census())
        self.assertEqual(
            result["presentation"]["width_scale"],
            {"numerator": 3, "denominator": 2},
        )
        self.assertEqual(
            result["presentation"]["height_scale"],
            {"numerator": 3, "denominator": 2},
        )
        self.assertTrue(result["presentation"]["upscale"])
        self.assertTrue(
            result["qualification"]["presentation_upscale_boundary_proven"]
        )
        self.assertTrue(result["lineage"]["external_or_pre_capture_ingress"])
        self.assertFalse(result["qualification"]["guest_post_chain_joined"])
        self.assertFalse(result["qualification"]["upscale_algorithm_proven"])
        self.assertFalse(result["qualification"]["native_implementation_ready"])
        self.assertFalse(result["safety"]["suppression_allowed"])

    def test_records_capture_local_input_without_promoting_readiness(self):
        document = bindings([
            {"event_id": 20, "usage": "CopyDst"},
            {"event_id": 30, "usage": "PS_Resource"},
        ])
        result = MODULE.build_ingress(document, census())
        self.assertTrue(result["lineage"]["capture_local_producer_observed"])
        self.assertTrue(result["qualification"]["guest_post_chain_joined"])
        self.assertFalse(result["qualification"]["native_implementation_ready"])

    def test_rejects_sink_or_capture_drift(self):
        wrong_sink = census()
        wrong_sink["presentation_sinks"][0]["producer_event"] = 31
        with self.assertRaisesRegex(ValueError, "identity drifted"):
            MODULE.build_ingress(bindings(), wrong_sink)
        with self.assertRaisesRegex(ValueError, "captures differ"):
            MODULE.build_ingress(
                bindings(capture="A" * 64), census("B" * 64)
            )

    def test_rejects_unsafe_or_ambiguous_binding_reports(self):
        unsafe = bindings()
        unsafe["safety"]["suppression_allowed"] = True
        with self.assertRaisesRegex(ValueError, "suppression"):
            MODULE.build_ingress(unsafe, census())
        ambiguous = bindings()
        ambiguous["bindings"].append(dict(ambiguous["bindings"][0]))
        with self.assertRaisesRegex(ValueError, "one bounded ingress"):
            MODULE.build_ingress(ambiguous, census())


if __name__ == "__main__":
    unittest.main()
