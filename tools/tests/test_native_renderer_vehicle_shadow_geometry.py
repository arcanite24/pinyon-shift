import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-vehicle-shadow-geometry.py"
SPEC = importlib.util.spec_from_file_location("vehicle_shadow_geometry", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class VehicleShadowGeometryTests(unittest.TestCase):
    def fixture(self):
        safety = {
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        }
        return [
            {
                "event": MODULE.CONFIG_EVENT,
                "status": "armed",
                **safety,
            },
            {
                "event": MODULE.EPOCH_EVENT,
                "draw_count": "80",
                "promotion_boundary": "backend_recorded_full_80_draw_epoch",
                **safety,
            },
            {
                "event": MODULE.CORRELATION_EVENT,
                "classification": "vehicle_color_geometry_correlation_candidate",
                "match": "exact_index_and_shared_vertex_resource",
                **safety,
            },
            {
                "event": MODULE.CANDIDATE_EVENT,
                "classification": "bounded_vehicle_color_geometry_candidate_family",
                "match": "exact_index_and_shared_vertex_resource",
                "prepared_signature": "1" * 16,
                "template_key": "2" * 16,
                "draw_argument_hash": "3" * 16,
                "geometry_resource_hash": "4" * 16,
                "texture_resource_hash": "5" * 16,
                "prepared_pipeline_hash": "6" * 16,
                "first_parameter_hash": "7" * 16,
                "last_parameter_hash": "8" * 16,
                "draws": "3",
                "parameter_switches": "2",
                "first_frame": "10",
                "last_frame": "12",
                "pose_variation_observed": "true",
                **safety,
            },
            {
                "event": MODULE.CAPTURE_CONFIG_EVENT,
                "status": "armed",
                "native_draw": "private_capture_only",
                "xenos_draw": "preserved",
                "output_authority": "xenos",
                "suppression_allowed": "false",
            },
            {
                "event": MODULE.CAPTURE_RESULT_EVENT,
                "status": "recorded_private_color_candidate",
                "native_draw": "private_capture_only",
                "xenos_draw": "preserved",
                "output_authority": "xenos",
                "suppression_allowed": "false",
            },
            {
                "event": MODULE.CAPTURE_SUMMARY_EVENT,
                "status": "recorded_private_color_candidate",
                "requests": "1",
                "recorded": "1",
                "target_creation_failures": "0",
                "unsupported": "0",
                "request_accounting_complete": "true",
                "native_draw": "private_capture_only",
                "xenos_draw": "preserved",
                "output_authority": "xenos",
                "suppression_allowed": "false",
            },
            {
                "event": MODULE.SUMMARY_EVENT,
                "status": "qualified_epoch_observed",
                "epochs_committed": "1",
                "unique_geometry_seeds": "76",
                "seed_overflow": "0",
                "seed_accounting_complete": "true",
                "color_draws_examined": "40",
                "color_draws_matched": "3",
                "full_geometry_matches": "1",
                "index_vertex_matches": "2",
                "correlations": "1",
                "correlation_overflow": "0",
                **safety,
            },
        ]

    def summarize(self, events):
        with tempfile.TemporaryDirectory(prefix="pinyon-vehicle-shadow-") as root:
            log = Path(root) / "diagnostics.jsonl"
            log.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            return MODULE.summarize(log)

    def test_accepts_full_epoch_and_bounded_color_candidate(self):
        report = self.summarize(self.fixture())
        self.assertEqual(1, report["totals"]["epochs_committed"])
        self.assertEqual(3, report["totals"]["color_draws_matched"])
        self.assertTrue(
            report["qualification"]["working_color_bridge_candidate"]
        )
        self.assertEqual(1, len(report["candidate_families"]))
        self.assertEqual(
            "recorded_private_color_candidate",
            report["private_color_capture"]["result"]["status"],
        )
        self.assertFalse(report["qualification"]["native_admission_allowed"])
        self.assertTrue(
            report["qualification"]["private_color_capture_recorded"]
        )

    def test_rejects_partial_epoch_promotion(self):
        events = self.fixture()
        events[1]["draw_count"] = "79"
        with self.assertRaisesRegex(ValueError, "epoch draw count drift"):
            self.summarize(events)

    def test_rejects_match_accounting_drift(self):
        events = self.fixture()
        events[-1]["color_draws_matched"] = "4"
        with self.assertRaisesRegex(ValueError, "match accounting drift"):
            self.summarize(events)

    def test_rejects_suppression(self):
        events = self.fixture()
        events[2]["suppression_allowed"] = "true"
        with self.assertRaisesRegex(ValueError, "suppression was allowed"):
            self.summarize(events)

    def test_rejects_pose_variation_accounting_drift(self):
        events = self.fixture()
        events[3]["pose_variation_observed"] = "false"
        with self.assertRaisesRegex(ValueError, "pose variation accounting drift"):
            self.summarize(events)

    def test_rejects_private_capture_authority_drift(self):
        events = self.fixture()
        events[5]["output_authority"] = "native"
        with self.assertRaisesRegex(ValueError, "output authority"):
            self.summarize(events)

    def test_runtime_contract_is_default_off_and_full_epoch_gated(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        capture = (ROOT / "tools/capture-native-renderer-census.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "PINYON_SHIFT_NATIVE_RENDERER_VEHICLE_SHADOW_GEOMETRY_CORRELATION",
            source,
        )
        self.assertIn("CommitVehicleShadowGeometryEpoch", source)
        self.assertIn(
            "vehicle_shadow_geometry_staging_count !=\n"
            "          kShadowDepthBatchDrawCount",
            source,
        )
        self.assertIn('"native_renderer.discovery.vehicle_shadow_geometry_summary"', source)
        self.assertIn('"native_renderer.discovery.vehicle_shadow_geometry_candidate"', source)
        self.assertIn("CompleteVehicleShadowColorCapture", source)
        self.assertIn(
            '"native_renderer.discovery.vehicle_shadow_color_capture_summary"',
            source,
        )
        self.assertIn("[switch]$VehicleShadowGeometryCorrelation", capture)
        self.assertIn("[switch]$CaptureVehicleShadowColor", capture)
        self.assertIn(
            "VehicleShadowGeometryCorrelation requires ShadowDepthBatch",
            capture,
        )
        self.assertIn(
            "CaptureVehicleShadowColor requires VehicleShadowGeometryCorrelation",
            capture,
        )
        self.assertIn('{"native_draw", "false"}', source)
        self.assertIn('{"xenos_authority", "true"}', source)
        self.assertIn('{"suppression_allowed", "false"}', source)


if __name__ == "__main__":
    unittest.main()
