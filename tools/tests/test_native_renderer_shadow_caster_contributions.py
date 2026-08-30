import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/analyze-native-renderer-shadow-caster-contributions.py"
SPEC = importlib.util.spec_from_file_location("shadow_caster_contributions", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ShadowCasterContributionTests(unittest.TestCase):
    def test_measures_exact_png_delta_and_joins_family(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-caster-delta-") as root:
            root = Path(root)
            before = root / "before.png"
            after = root / "after.png"
            before_pixels = bytes([0, 0, 0, 255] * 4)
            after_pixels = bytearray(before_pixels)
            after_pixels[4:8] = bytes([64, 64, 64, 255])
            MODULE.write_rgba_png(before, 2, 2, before_pixels)
            MODULE.write_rgba_png(after, 2, 2, bytes(after_pixels))
            capture = {"path": "fixture.rdc", "sha256": "A" * 64}
            export = {
                "schema": MODULE.EXPORT_SCHEMA,
                "capture": capture,
                "resource": {"resource_name": "depth", "width": 2, "height": 2},
                "events": [
                    {
                        "event_id": 10,
                        "before": {
                            "path": before.name,
                            "sha256": MODULE.sha256(before),
                        },
                        "after": {
                            "path": after.name,
                            "sha256": MODULE.sha256(after),
                        },
                    }
                ],
                "safety": {
                    "local_resource_payload_exported": True,
                    "tracked_payload_allowed": False,
                    "xenos_authority": True,
                    "native_rendering_changed": False,
                    "suppression_allowed": False,
                },
            }
            census = {
                "schema": MODULE.CENSUS_SCHEMA,
                "capture": capture,
                "families": [
                    {
                        "sha256": "B" * 64,
                        "event_ids": [10],
                        "semantic_role": "unknown_unclassified",
                        "signature": {
                            "pipeline_name": "fixture pipeline",
                            "vertex_shader_name": "fixture vertex",
                            "pixel_shader_name": None,
                            "viewport": {"width": 2, "height": 2},
                            "scissor": {"width": 2, "height": 2},
                        },
                    }
                ],
                "safety": {
                    "metadata_only": True,
                    "resource_payload_exported": False,
                    "xenos_authority": True,
                    "suppression_allowed": False,
                },
            }
            export_path = root / "export.json"
            census_path = root / "census.json"
            export_path.write_text(json.dumps(export), encoding="utf-8")
            census_path.write_text(json.dumps(census), encoding="utf-8")
            report_path, report = MODULE.analyze(
                export_path, census_path, root / "analysis"
            )
            self.assertTrue(report_path.is_file())
            self.assertEqual(1, report["totals"]["events_with_delta"])
            self.assertEqual(1, report["totals"]["changed_pixels"])
            event = report["events"][0]
            self.assertEqual(
                {"x": 1, "y": 0, "width": 1, "height": 1},
                event["bounding_box"],
            )
            self.assertEqual(
                "fixture pipeline", event["signature"]["pipeline_name"]
            )
            delta_path = report_path.parent / event["delta_image"]
            self.assertEqual((1, 1), MODULE.decode_rgba_png(delta_path)[:2])
            self.assertFalse(
                report["qualification"][
                    "caster_classification_allowed_without_review"
                ]
            )

    def test_rejects_hash_drift_and_unsafe_export(self):
        with tempfile.TemporaryDirectory(prefix="pinyon-caster-unsafe-") as root:
            root = Path(root)
            image = root / "image.png"
            MODULE.write_rgba_png(image, 1, 1, bytes([0, 0, 0, 255]))
            capture = {"path": "fixture.rdc", "sha256": "A" * 64}
            export = {
                "schema": MODULE.EXPORT_SCHEMA,
                "capture": capture,
                "events": [
                    {
                        "event_id": 1,
                        "before": {"path": image.name, "sha256": "B" * 64},
                        "after": {"path": image.name, "sha256": "B" * 64},
                    }
                ],
                "safety": {
                    "local_resource_payload_exported": True,
                    "tracked_payload_allowed": False,
                    "xenos_authority": True,
                    "native_rendering_changed": False,
                    "suppression_allowed": False,
                },
            }
            census = {
                "schema": MODULE.CENSUS_SCHEMA,
                "capture": capture,
                "families": [],
                "safety": {
                    "metadata_only": True,
                    "resource_payload_exported": False,
                    "xenos_authority": True,
                    "suppression_allowed": False,
                },
            }
            export_path = root / "export.json"
            census_path = root / "census.json"
            export_path.write_text(json.dumps(export), encoding="utf-8")
            census_path.write_text(json.dumps(census), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "image hash drifted"):
                MODULE.analyze(export_path, census_path, root / "analysis")

    def test_export_contract_is_local_only_and_xenos_preserving(self):
        exporter = (
            ROOT / "tools/export-native-renderer-shadow-caster-contributions.py"
        ).read_text(encoding="utf-8")
        wrapper = (
            ROOT / "tools/export-native-renderer-shadow-caster-contributions.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("controller.SetFrameEvent(event_id - 1, True)", exporter)
        self.assertIn("controller.SetFrameEvent(event_id, True)", exporter)
        self.assertIn("controller.SaveTexture", exporter)
        self.assertIn('"tracked_payload_allowed": False', exporter)
        self.assertIn('"xenos_authority": True', exporter)
        self.assertIn('"native_rendering_changed": False', exporter)
        self.assertIn('"suppression_allowed": False', exporter)
        self.assertIn("must be below $localRoot", wrapper)
        self.assertIn("Get-AuthenticodeSignature", wrapper)
        self.assertIn("depth_write_events", wrapper)


if __name__ == "__main__":
    unittest.main()
