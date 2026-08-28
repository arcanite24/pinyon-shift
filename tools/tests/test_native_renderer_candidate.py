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
        "index_state": "format=0;endianness=2",
        "vertex_binding_count": "1",
        "vertex_fetches": "0:00100000:4096:8:2",
        "texture_fetch_count": "1",
        "pipeline_state": "opaque",
        "indexed": "true",
        "query": "false",
        "memexport": "false",
        "resolved_input": "false",
        "opaque": "true",
        "vertex_overflow": "false",
    }
    record.update(overrides)
    return record


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
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = []
            for index, document in enumerate((first, second)):
                path = root / f"census-{index}.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                paths.append(path)
            manifest = root / "shader-manifest.json"
            manifest.write_text(json.dumps(shader_manifest), encoding="utf-8")
            result = MODULE.select(paths, manifest)

        self.assertEqual(1, result["candidate_count"])
        self.assertEqual("GOOD", result["candidates"][0]["signature"])
        self.assertEqual(50, result["candidates"][0]["total_draws"])
        self.assertEqual(
            "AAAAAAAAAAAAAAAA",
            result["candidates"][0]["vertex_specialization_mask"],
        )
        self.assertFalse(result["safety"]["suppression_allowed"])
        self.assertTrue(result["safety"]["xenos_authority"])

    def test_rejects_dynamic_input(self):
        reasons = MODULE.rejection_reasons(signature("BAD", resolved_input="true"))
        self.assertIn("dynamic_render_target_input", reasons)


if __name__ == "__main__":
    unittest.main()
