import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_renderer_draw_state",
    ROOT / "tools/build-native-draw-state-contract.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def texture_state(**overrides):
    fields = {
        "stage": 2,
        "fetch": 0,
        "dwords": [
            2 | (2 << 10) | (2 << 13) | (2 << 16) | (4 << 22) | (1 << 31),
            6 | (2 << 6) | (0x12345 << 12),
            63 | (31 << 13),
            (0x688 << 1) | (1 << 19) | (1 << 21),
            0,
            1 << 9,
        ],
        "opcode": 1,
        "dimension": 1,
        "filters": 0x7333,
        "flags": 0x14,
        "lod": 0,
        "offsets": 0,
        "target": 0,
        "index": 0,
        "mask": 0xF,
        "components": 0x688,
    }
    fields.update(overrides)
    return ":".join(
        [str(fields["stage"]), str(fields["fetch"])]
        + [f"{word:08X}" for word in fields["dwords"]]
        + [
            str(fields["opcode"]),
            str(fields["dimension"]),
            f"{fields['filters']:06X}",
            f"{fields['flags']:02X}",
            f"{fields['lod']:08X}",
            f"{fields['offsets']:06X}",
            str(fields["target"]),
            str(fields["index"]),
            f"{fields['mask']:X}",
            f"{fields['components']:X}",
        ]
    )


def selection(**overrides):
    candidate = {
        "signature": "DRAW",
        "draw_state_hashes": ["1111111111111111", "1111111111111111"],
        "vertex_float_constant_count": 1,
        "vertex_float_constants": "0:3F800000:00000000:00000000:3F800000",
        "pixel_float_constant_count": 1,
        "pixel_float_constants": "2:3F000000:3F800000:40000000:40400000",
        "bool_constants": "0:00000003:00000001",
        "loop_constants": "1:00000002",
        "texture_state_count": 1,
        "texture_states": texture_state(),
        "pipeline_state": "vertex=00000000",
    }
    candidate.update(overrides)
    return {"schema": MODULE.SELECTION_SCHEMA, "candidates": [candidate]}


class NativeRendererDrawStateTests(unittest.TestCase):
    def test_decodes_bounded_constant_texture_and_sampler_state(self):
        result = MODULE.build(selection())
        self.assertEqual(MODULE.SCHEMA, result["schema"])
        self.assertTrue(result["state_stable_across_captures"])
        self.assertEqual(1.0, result["constants"]["vertex_float"][0]["values"][0])
        texture = result["textures"][0]
        self.assertEqual("8_8_8_8", texture["format"]["name"])
        self.assertEqual("2d_or_stacked", texture["dimension"])
        self.assertEqual({"width": 64, "height": 32, "depth": 1}, texture["size"])
        self.assertEqual("linear", texture["filter"]["mag"])
        self.assertEqual("linear", texture["filter"]["min"])
        self.assertEqual("point", texture["filter"]["mip"])
        self.assertEqual("disabled", texture["filter"]["anisotropic"])
        self.assertFalse(result["safety"]["guest_resource_payload_read"])
        self.assertFalse(result["safety"]["native_draw"])
        self.assertTrue(result["safety"]["xenos_authority"])

    def test_reports_dynamic_draw_state_across_captures(self):
        result = MODULE.build(
            selection(draw_state_hashes=["1111111111111111", "2222222222222222"])
        )
        self.assertFalse(result["state_stable_across_captures"])

    def test_rejects_constant_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "count or indices"):
            MODULE.build(selection(vertex_float_constant_count=2))

    def test_accepts_multiple_instructions_for_one_texture_resource(self):
        states = ";".join([texture_state(), texture_state(offsets=1)])
        result = MODULE.build(selection(texture_state_count=2, texture_states=states))
        self.assertEqual(1, result["texture_resource_count"])
        self.assertEqual(2, len(result["textures"]))

    def test_accepts_multiple_texture_resources_within_bound(self):
        states = ";".join([texture_state(), texture_state(fetch=1)])
        result = MODULE.build(selection(texture_state_count=2, texture_states=states))
        self.assertEqual(2, result["texture_resource_count"])

    def test_rejects_missing_texture_resource(self):
        with self.assertRaisesRegex(ValueError, "observed texture states"):
            MODULE.build(selection(texture_state_count=0, texture_states=""))

    def test_rejects_more_than_four_texture_resources(self):
        states = ";".join(texture_state(fetch=index) for index in range(5))
        with self.assertRaisesRegex(ValueError, "one to four"):
            MODULE.build(selection(texture_state_count=5, texture_states=states))

    def test_rejects_non_texture_fetch_constant(self):
        state = texture_state(dwords=[0, 0, 0, 0, 0, 0])
        with self.assertRaisesRegex(ValueError, "not a texture"):
            MODULE.build(selection(texture_states=state))


if __name__ == "__main__":
    unittest.main()
