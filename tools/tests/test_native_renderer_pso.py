import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_pso", ROOT / "tools" / "build-native-pso-contract.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


SIGNATURE = "FA45AAFDC22C8625"


def documents():
    candidate = {
        "signature": SIGNATURE,
        "vertex_shader": "1111111111111111",
        "pixel_shader": "2222222222222222",
        "vertex_specialization_mask": "0000000000000003",
        "pixel_specialization_mask": "0000400000000003",
        "prepared_pipeline_hash": "3333333333333333",
        "host_primitive": "4",
        "host_vertex_shader_type": "0",
        "tessellation_mode": "0",
        "host_index_buffer_type": "1",
        "host_index_format": "1",
        "host_primitive_reset": False,
        "normalized_depth_control": "087087E3",
        "normalized_color_mask": "0000000F",
        "bound_render_target_bits": "00000003",
        "bound_render_target_formats": "0000002D:0000001C:00000000:00000000:00000000",
        "prepared_pipeline_flags": "00000003",
        "pipeline_state": "color_mask=0000000F",
    }
    selection = {
        "schema": MODULE.SELECTION_SCHEMA,
        "candidates": [candidate],
    }
    geometry = {
        "schema": MODULE.GEOMETRY_SCHEMA,
        "candidate_signature": SIGNATURE,
        "primitive": 4,
        "indexed": True,
        "index": {"format": 1},
        "bounds": {"validated": True},
        "safety": {
            "native_upload": False,
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }
    draw_state = {
        "schema": MODULE.DRAW_STATE_SCHEMA,
        "candidate_signature": SIGNATURE,
        "state_stable_across_captures": False,
        "safety": {
            "native_upload": False,
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }
    texture = {
        "schema": MODULE.TEXTURE_SCHEMA,
        "candidate_signature": SIGNATURE,
        "qualification": {
            "content_stable_across_captures": True,
            "visual_identity_confirmed": False,
            "dynamic_render_target_exclusion_required": True,
        },
        "safety": {
            "native_upload": False,
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }
    return selection, geometry, draw_state, texture


class NativePsoContractTests(unittest.TestCase):
    def test_builds_supported_pipeline_key_without_creating_it(self):
        result = MODULE.build(*documents(), SIGNATURE)
        self.assertTrue(result["support"]["ready_for_pso_creation"])
        self.assertEqual([], result["support"]["unsupported_or_unknown"])
        self.assertEqual(64, len(result["pso_key_sha256"]))
        self.assertFalse(result["safety"]["native_pso_created"])
        self.assertTrue(result["safety"]["xenos_authority"])

    def test_reports_unsupported_host_conversion(self):
        inputs = documents()
        inputs[0]["candidates"][0]["host_primitive"] = "5"
        result = MODULE.build(*inputs, SIGNATURE)
        self.assertFalse(result["support"]["ready_for_pso_creation"])
        self.assertIn("primitive_conversion", result["support"]["unsupported_or_unknown"])

    def test_ignores_residual_tessellation_mode_for_vertex_shader(self):
        inputs = documents()
        inputs[0]["candidates"][0]["tessellation_mode"] = "1"
        result = MODULE.build(*inputs, SIGNATURE)
        self.assertTrue(result["support"]["ready_for_pso_creation"])

    def test_rejects_active_tessellation_host_shader(self):
        inputs = documents()
        inputs[0]["candidates"][0]["host_vertex_shader_type"] = "1"
        inputs[0]["candidates"][0]["tessellation_mode"] = "1"
        result = MODULE.build(*inputs, SIGNATURE)
        self.assertFalse(result["support"]["ready_for_pso_creation"])
        self.assertIn("tessellation", result["support"]["unsupported_or_unknown"])

    def test_requires_prepared_pipeline_observation(self):
        inputs = documents()
        del inputs[0]["candidates"][0]["prepared_pipeline_hash"]
        with self.assertRaisesRegex(ValueError, "prepared pipeline"):
            MODULE.build(*inputs, SIGNATURE)

    def test_rejects_relaxed_input_safety_gate(self):
        inputs = documents()
        inputs[2]["safety"]["native_draw"] = True
        with self.assertRaisesRegex(ValueError, "safety gates"):
            MODULE.build(*inputs, SIGNATURE)

    def test_requires_xenos_authority_in_every_input(self):
        inputs = documents()
        inputs[1]["safety"]["xenos_authority"] = False
        with self.assertRaisesRegex(ValueError, "safety gates"):
            MODULE.build(*inputs, SIGNATURE)


if __name__ == "__main__":
    unittest.main()
