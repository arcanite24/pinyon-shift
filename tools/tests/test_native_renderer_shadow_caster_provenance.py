import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-shadow-caster-provenance.py"
SPEC = importlib.util.spec_from_file_location("shadow_caster_provenance", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ShadowCasterProvenanceTests(unittest.TestCase):
    def fixture(self, draw):
        safety = {
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        control = {
            "event": MODULE.CONTROL_EVENT,
            "status": "armed",
            "requested": "true",
            "valid": "true",
            "capture_family_sha256": "A" * 64,
            "vertex_shader": "C8C39E5AE1B08DE6",
            "atlas_region": "1024,0,1024,1024",
            "viewport_raw": "43800000:44400000:C3800000:43800000",
            "classification_scope": "per_exact_draw",
            "maximum_vehicle_identity_age_frames": "1",
            **safety,
        }
        summary = {
            "event": MODULE.SUMMARY_EVENT,
            "status": "provenance_observed",
            "capture_family_sha256": "A" * 64,
            "vertex_shader": "C8C39E5AE1B08DE6",
            "atlas_region": "1024,0,1024,1024",
            "viewport_raw": "43800000:44400000:C3800000:43800000",
            "shader_matches": "1",
            "contract_matches": "1",
            "contract_rejections": "0",
            "dynamic_vehicle_proven": "1",
            "static_world_proven": "0",
            "unresolved": "0",
            "samples": "1",
            "sample_overflow": "0",
            "classification_accounting_complete": "true",
            "sample_accounting_complete": "true",
            "static_dynamic_separation_complete": "false",
            **safety,
        }
        return [control, draw, summary]

    def test_accepts_fresh_exact_vehicle_identity(self):
        draw = {
            "event": MODULE.DRAW_EVENT,
            "sample": "1",
            "classification": "dynamic_vehicle_proven",
            "provenance_source": "exact_title_argument",
            "unresolved_reason": "none",
            "identity_generation": "4",
            "identity_owner": "81234560",
            "identity_age_frames": "1",
            "static_inference_from_absence": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        with tempfile.TemporaryDirectory(prefix="pinyon-caster-provenance-") as root:
            log = Path(root) / "diagnostics.jsonl"
            log.write_text(
                "".join(json.dumps(event) + "\n" for event in self.fixture(draw)),
                encoding="utf-8",
            )
            report = MODULE.summarize(log)
            self.assertEqual(1, report["totals"]["dynamic_vehicle_proven"])
            self.assertTrue(
                report["qualification"]["per_draw_vehicle_promotion_allowed"]
            )
            self.assertFalse(
                report["qualification"]["whole_family_promotion_allowed"]
            )

    def test_rejects_stale_dynamic_promotion(self):
        draw = {
            "event": MODULE.DRAW_EVENT,
            "sample": "1",
            "classification": "dynamic_vehicle_proven",
            "provenance_source": "vehicle_owner_method",
            "unresolved_reason": "none",
            "identity_generation": "4",
            "identity_owner": "81234560",
            "identity_age_frames": "2",
            "static_inference_from_absence": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        with tempfile.TemporaryDirectory(prefix="pinyon-caster-stale-") as root:
            log = Path(root) / "diagnostics.jsonl"
            log.write_text(
                "".join(json.dumps(event) + "\n" for event in self.fixture(draw)),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "stale identity"):
                MODULE.summarize(log)

    def test_accepts_bounded_sample_overflow_with_complete_accounting(self):
        draw = {
            "event": MODULE.DRAW_EVENT,
            "sample": "1",
            "classification": "unresolved",
            "provenance_source": "none",
            "unresolved_reason": "no_vehicle_identity",
            "identity_generation": "",
            "identity_owner": "",
            "identity_age_frames": "",
            "static_inference_from_absence": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        events = self.fixture(draw)
        events[-1].update(
            {
                "status": "sample_capacity_exhausted",
                "contract_matches": "3",
                "dynamic_vehicle_proven": "1",
                "unresolved": "2",
                "sample_overflow": "2",
            }
        )
        with tempfile.TemporaryDirectory(prefix="pinyon-caster-overflow-") as root:
            log = Path(root) / "diagnostics.jsonl"
            log.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            report = MODULE.summarize(log)
            self.assertEqual(3, report["totals"]["contract_matches"])
            self.assertEqual(2, report["totals"]["sample_overflow"])
            self.assertFalse(report["qualification"]["sample_coverage_complete"])



if __name__ == "__main__":
    unittest.main()
