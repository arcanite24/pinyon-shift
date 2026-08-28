import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_renderer_candidate",
    ROOT / "tools/select-native-renderer-candidate.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def signature(name: str, **overrides):
    record = {
        "signature": name,
        "draws": "20",
        "vertex_shader": "1111111111111111",
        "pixel_shader": "2222222222222222",
        "primitive": "4",
        "source_select": "2",
        "index_count_min": "3",
        "index_count_max": "3",
        "index_state": "format=0;endianness=2",
        "index_buffer_address": "00180000",
        "index_buffer_length_min": "6",
        "vertex_index_range": "offset=0;min=0;max=16777215",
        "vertex_binding_count": "1",
        "vertex_fetches": "0:00100000:4096:8:2",
        "vertex_attribute_count": "1",
        "vertex_attributes": "0:0:0:8:6:F:0:0:0:0:F:688:0",
        "texture_fetch_count": "1",
        "draw_state_hash": "3333333333333333",
        "vertex_float_constant_count": "1",
        "vertex_float_constants": "0:3F800000:00000000:00000000:3F800000",
        "pixel_float_constant_count": "1",
        "pixel_float_constants": "0:3F800000:3F800000:3F800000:3F800000",
        "bool_constants": "0:00000001:00000001",
        "loop_constants": "",
        "texture_state_count": "1",
        "texture_states": "2:0:0:0:0:0:0:0:0:1:0:1C:0:0:0:0:F:688",
        "pipeline_state": "opaque",
        "indexed": "true",
        "query": "false",
        "memexport": "false",
        "resolved_input": "false",
        "opaque": "true",
        "vertex_overflow": "false",
        "vertex_attribute_overflow": "false",
        "constant_overflow": "false",
        "texture_state_overflow": "false",
    }
    record.update(overrides)
    return record


def texture_state(base_address: int) -> str:
    fields = signature("STATE")["texture_states"].split(":")
    fields[3] = f"{base_address >> 12 << 12:08X}"
    return ":".join(fields)


def select_documents(first, second, shader_manifest):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        paths = []
        for index, document in enumerate((first, second)):
            path = root / f"census-{index}.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            paths.append(path)
        manifest = root / "shader-manifest.json"
        manifest.write_text(json.dumps(shader_manifest), encoding="utf-8")
        return MODULE.select(paths, manifest)


class NativeRendererCandidateTests(unittest.TestCase):
    def test_requires_two_census_inventories(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            MODULE.select([], Path("unused.json"))

    def test_selects_only_repeatable_bounded_opaque_draw(self):
        shader_manifest = {
            "schema": MODULE.SHADER_SCHEMA,
            "entries": [
                {
                    "stage": "vertex",
                    "guest_hash": "1111111111111111",
                    "specialization_mask": "AAAAAAAAAAAAAAAA",
                },
                {
                    "stage": "pixel",
                    "guest_hash": "2222222222222222",
                    "specialization_mask": "BBBBBBBBBBBBBBBB",
                },
            ],
        }
        first = {
            "schema": MODULE.CENSUS_SCHEMA,
            "classification": {"scene": "open_world_day"},
            "draw_candidates": [
                signature("GOOD", indexed="false"),
                signature("QUERY", query="true"),
            ],
            "prepared_shader_pairs": [
                {
                    "vertex_shader": "1111111111111111",
                    "pixel_shader": "2222222222222222",
                    "vertex_specialization_mask": "AAAAAAAAAAAAAAAA",
                    "pixel_specialization_mask": "BBBBBBBBBBBBBBBB",
                }
            ],
        }
        second = {
            "schema": MODULE.CENSUS_SCHEMA,
            "classification": {"scene": "open_world_day"},
            "draw_candidates": [
                signature("GOOD", draws="30", indexed="false")
            ],
            "prepared_shader_pairs": first["prepared_shader_pairs"],
        }
        result = select_documents(first, second, shader_manifest)

        self.assertEqual(1, result["candidate_count"])
        self.assertEqual("GOOD", result["candidates"][0]["signature"])
        self.assertEqual(50, result["candidates"][0]["total_draws"])
        self.assertEqual(3, result["candidates"][0]["index_count_min"])
        self.assertEqual(3, result["candidates"][0]["index_count_max"])
        self.assertEqual(6, result["candidates"][0]["index_buffer_length_min"])
        self.assertFalse(result["candidates"][0]["indexed"])
        self.assertEqual(
            ["3333333333333333", "3333333333333333"],
            result["candidates"][0]["draw_state_hashes"],
        )
        self.assertEqual(1, result["candidates"][0]["texture_state_count"])
        self.assertEqual(
            "AAAAAAAAAAAAAAAA",
            result["candidates"][0]["vertex_specialization_mask"],
        )
        self.assertFalse(result["safety"]["suppression_allowed"])
        self.assertTrue(result["safety"]["xenos_authority"])

    def test_rejects_dynamic_input(self):
        reasons = MODULE.rejection_reasons(signature("BAD", resolved_input="true"))
        self.assertIn("dynamic_render_target_input", reasons)

    def test_rejects_texture_inside_any_observed_resolve_range(self):
        record = signature(
            "BAD", texture_states=texture_state(0x00124000)
        )
        self.assertTrue(
            MODULE.reads_known_resolve_target(
                record, MODULE.resolve_ranges({"resolve_targets": [
                    {"address": "00123000", "length": "8192"}
                ]})
            )
        )

    def test_selector_rejects_candidate_with_known_resolve_provenance(self):
        shader_manifest = {
            "schema": MODULE.SHADER_SCHEMA,
            "entries": [
                {
                    "stage": stage,
                    "guest_hash": guest_hash,
                    "specialization_mask": specialization,
                }
                for stage, guest_hash, specialization in (
                    ("vertex", "1111111111111111", "AAAAAAAAAAAAAAAA"),
                    ("pixel", "2222222222222222", "BBBBBBBBBBBBBBBB"),
                )
            ],
        }
        prepared = [{
            "vertex_shader": "1111111111111111",
            "pixel_shader": "2222222222222222",
            "vertex_specialization_mask": "AAAAAAAAAAAAAAAA",
            "pixel_specialization_mask": "BBBBBBBBBBBBBBBB",
        }]
        census = {
            "schema": MODULE.CENSUS_SCHEMA,
            "classification": {"scene": "open_world_day"},
            "draw_candidates": [signature(
                "DYNAMIC", texture_states=texture_state(0x00124000)
            )],
            "prepared_shader_pairs": prepared,
            "resolve_targets": [{"address": "00123000", "length": "8192"}],
        }
        result = select_documents(census, census, shader_manifest)
        self.assertEqual(0, result["candidate_count"])
        self.assertEqual(
            {"reason": "dynamic_render_target_input", "signatures": 1},
            next(item for item in result["rejections"]
                 if item["reason"] == "dynamic_render_target_input"),
        )
    def test_ignores_texture_outside_observed_resolve_ranges(self):
        record = signature(
            "GOOD", texture_states=texture_state(0x00125000)
        )
        self.assertFalse(
            MODULE.reads_known_resolve_target(
                record, MODULE.resolve_ranges({"resolve_targets": [
                    {"address": "00123000", "length": "8192"}
                ]})
            )
        )

    def test_rejects_vertex_attribute_overflow(self):
        reasons = MODULE.rejection_reasons(
            signature("BAD", vertex_attribute_overflow="true")
        )
        self.assertIn("vertex_attribute_overflow", reasons)

    def test_rejects_draw_state_overflow(self):
        self.assertIn(
            "constant_observer_overflow",
            MODULE.rejection_reasons(signature("BAD", constant_overflow="true")),
        )
        self.assertIn(
            "texture_state_observer_overflow",
            MODULE.rejection_reasons(
                signature("BAD", texture_state_overflow="true")
            ),
        )


if __name__ == "__main__":
    unittest.main()
