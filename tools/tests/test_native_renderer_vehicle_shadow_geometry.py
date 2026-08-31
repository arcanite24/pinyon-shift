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
                "typed_constant_upload_hook": "82435E78:r3,r4,r5,r6,lr",
                "typed_constant_upload_contract": "exact_shader_used_vertex_register_hash",
                "typed_constant_upload_capacity": "8192",
                "typed_constant_upload_maximum_age_frames": "1",
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
                "material_topology_key": "A" * 16,
                "vertex_shader": "B" * 16,
                "pixel_shader": "C" * 16,
                "render_state_hash": "D" * 16,
                "texture_layout_hash": "E" * 16,
                **safety,
            },
            {
                "event": MODULE.CANDIDATE_EVENT,
                "classification": "bounded_vehicle_color_geometry_candidate_family",
                "match": "exact_index_and_shared_vertex_resource",
                "prepared_signature": "1" * 16,
                "template_key": "2" * 16,
                "material_topology_key": "A" * 16,
                "vertex_shader": "B" * 16,
                "pixel_shader": "C" * 16,
                "render_state_hash": "D" * 16,
                "texture_layout_hash": "E" * 16,
                "first_material_parameter_hash": "F" * 16,
                "last_material_parameter_hash": "0" * 16,
                "material_parameter_switches": "2",
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
                "mechanically_eligible_draws": "1",
                "mechanically_rejected_draws": "2",
                "first_rejection_mask": "00002000",
                "last_rejection_mask": "00000000",
                "rejection_mask_or": "00002000",
                "rejection_mask_and": "00000000",
                "rejection_mask_switches": "1",
                "private_capture_eligible_draws": "3",
                "private_capture_rejected_draws": "0",
                "first_private_capture_rejection_mask": "00000000",
                "last_private_capture_rejection_mask": "00000000",
                "private_capture_rejection_mask_or": "00000000",
                "private_capture_rejection_mask_and": "00000000",
                "private_capture_rejection_mask_switches": "0",
                "constant_identity_scans": "3",
                "constant_identity_missing_fresh_pose": "0",
                "constant_position_unique_matches": "3",
                "constant_position_ambiguous_matches": "0",
                "constant_position_misses": "0",
                "constant_position_identity_variations": "0",
                "constant_position_register_variations": "0",
                "constant_position_identity_generation": "00000001",
                "constant_position_identity_owner": "40123450",
                "constant_position_identity_slot": "2",
                "constant_position_register": "208",
                "closest_position_delta_squared": "0.01",
                "constant_forward_unique_matches": "0",
                "constant_forward_ambiguous_matches": "3",
                "constant_forward_misses": "0",
                "constant_forward_identity_variations": "0",
                "constant_forward_register_variations": "0",
                "constant_forward_identity_generation": "unknown",
                "constant_forward_identity_owner": "unknown",
                "constant_forward_identity_slot": "unknown",
                "constant_forward_register": "unknown",
                "constant_forward_sign": "unknown",
                "closest_forward_delta_squared": "0.01",
                "constant_identity_classification": "stable_tight_position_candidate",
                "typed_upload_scans": "3",
                "typed_upload_fresh_candidates": "12",
                "typed_upload_no_overlap_candidates": "6",
                "typed_upload_hash_mismatch_candidates": "3",
                "typed_upload_exact_candidates": "3",
                "typed_upload_exact_matches": "3",
                "typed_upload_misses": "0",
                "typed_upload_exact_used_vectors": "9",
                "typed_upload_start_register_variations": "0",
                "typed_upload_vector_count_variations": "0",
                "typed_upload_used_vector_count_variations": "0",
                "typed_upload_source_address_variations": "2",
                "typed_upload_buffer_address_variations": "0",
                "typed_upload_caller_variations": "0",
                "typed_upload_start_register": "208",
                "typed_upload_vector_count": "4",
                "typed_upload_used_vector_count": "3",
                "typed_upload_source_address": "7FFF1000",
                "typed_upload_buffer_address": "50001000",
                "typed_upload_caller_return_address": "8240EB60",
                "typed_upload_observed_register_min": "208",
                "typed_upload_observed_register_max": "211",
                "typed_upload_classification": "stable_exact_vertex_register_candidate",
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
                "private_replay_status": "bounded_stability_observed",
                "private_replay_requests": "3",
                "private_replay_recorded": "3",
                "private_replay_target_creation_failures": "0",
                "private_replay_unsupported": "0",
                "private_replay_frame_quota_yields": "0",
                "private_replay_limit_yields": "0",
                "private_replay_limit": "300",
                "private_replay_accounting_complete": "true",
                "native_draw": "private_capture_only",
                "xenos_draw": "preserved",
                "output_authority": "xenos",
                "suppression_allowed": "false",
            },
            {
                "event": MODULE.RETAINED_CONFIG_EVENT,
                "status": "armed",
                "native_draw": "private_retained_pass_only",
                "xenos_draw": "preserved",
                "output_authority": "xenos",
                "suppression_allowed": "false",
            },
            {
                "event": MODULE.RETAINED_RESULT_EVENT,
                "status": "recorded_complete_private_vehicle_pass",
                "draw_count": "30",
                "native_draw": "private_retained_pass_only",
                "xenos_draw": "preserved",
                "output_authority": "xenos",
                "suppression_allowed": "false",
            },
            {
                "event": MODULE.RETAINED_SUMMARY_EVENT,
                "status": "bounded_retained_pass_stable",
                "requests": "60",
                "recorded": "60",
                "target_creation_failures": "0",
                "unsupported": "0",
                "request_accounting_complete": "true",
                "reused_target_requests": "58",
                "frames_started": "2",
                "frames_completed": "2",
                "frames_failed": "0",
                "frame_accounting_complete": "true",
                "draws_per_frame": "30",
                "pass_limit": "2",
                "limit_yields": "1",
                "capture_recorded": "true",
                "native_draw": "private_retained_pass_only",
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
                "mechanically_eligible_draws": "1",
                "mechanically_rejected_draws": "2",
                "mechanical_rejection_accounting_complete": "true",
                "private_capture_eligible_draws": "3",
                "private_capture_rejected_draws": "0",
                "private_capture_rejection_accounting_complete": "true",
                "color_runs": "1",
                "color_run_draws": "3",
                "multi_draw_color_runs": "1",
                "maximum_color_run_length": "3",
                "full_family_color_runs": "1",
                "first_full_family_sequence_hash": "9" * 16,
                "full_family_sequence_variants": "0",
                "color_run_accounting_complete": "true",
                "constant_identity_scans": "3",
                "constant_identity_missing_fresh_pose": "0",
                "constant_vectors_scanned": "96",
                "constant_non_finite_vectors": "0",
                "constant_identity_comparisons": "8928",
                "constant_position_unique_matches": "3",
                "constant_position_ambiguous_matches": "0",
                "constant_position_misses": "0",
                "constant_position_accounting_complete": "true",
                "constant_forward_unique_matches": "0",
                "constant_forward_ambiguous_matches": "3",
                "constant_forward_misses": "0",
                "constant_forward_accounting_complete": "true",
                "constant_identity_maximum_pose_age_frames": "1",
                "typed_upload_observations": "4",
                "typed_upload_valid": "3",
                "typed_upload_invalid_register_range": "1",
                "typed_upload_invalid_source_range": "0",
                "typed_upload_overwrites": "0",
                "typed_upload_capacity": "8192",
                "typed_upload_scans": "3",
                "typed_upload_fresh_candidates": "12",
                "typed_upload_no_overlap_candidates": "6",
                "typed_upload_hash_mismatch_candidates": "3",
                "typed_upload_exact_candidates": "3",
                "typed_upload_candidate_accounting_complete": "true",
                "typed_upload_exact_matches": "3",
                "typed_upload_misses": "0",
                "typed_upload_exact_used_vectors": "9",
                "typed_upload_outcome_accounting_complete": "true",
                "typed_upload_maximum_age_frames": "1",
                "typed_upload_contract": "82435E78_exact_shader_used_vertex_register_hash",
                "material_topology_groups": "1",
                "material_topology_group_accounting_complete": "true",
                "material_topology_contract": "shader_specialization_render_state_texture_layout",
                "reject_resolved_input": "0",
                "reject_unsupported_geometry": "0",
                "reject_empty_draw": "0",
                "reject_vertex_binding_count": "0",
                "reject_vertex_binding_overflow": "0",
                "reject_vertex_attribute_overflow": "0",
                "reject_vertex_constant_overflow": "0",
                "reject_pixel_constant_overflow": "0",
                "reject_texture_state_overflow": "0",
                "reject_memexport": "0",
                "reject_query": "0",
                "reject_texture_count": "0",
                "reject_texture_layout": "0",
                "reject_prepared_pipeline": "2",
                "reject_render_targets": "0",
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
        self.assertEqual(2, report["mechanical_rejections"]["prepared_pipeline"])
        self.assertTrue(report["qualification"]["private_color_replay_stable"])
        self.assertTrue(
            report["qualification"]["private_retained_color_pass_stable"]
        )
        self.assertEqual(
            2,
            int(report["private_retained_color_pass"]["summary"]["frames_completed"]),
        )
        self.assertEqual(3, report["color_run_topology"]["maximum_run_length"])
        self.assertEqual(
            1,
            report["constant_identity"]["stable_position_candidate_families"],
        )
        self.assertFalse(
            report["qualification"][
                "complete_shared_vehicle_transform_candidate"
            ]
        )
        self.assertEqual(1, report["material_topology"]["group_count"])
        self.assertEqual(
            1, report["material_topology"]["groups"][0]["family_count"]
        )
        self.assertEqual(
            1,
            report["material_topology"][
                "families_with_parameter_variation"
            ],
        )
        self.assertEqual(3, report["typed_constant_upload"]["exact_matches"])
        self.assertEqual(
            12, report["typed_constant_upload"]["fresh_candidates"]
        )
        self.assertEqual(
            6, report["typed_constant_upload"]["no_overlap_candidates"]
        )
        self.assertEqual(
            3,
            report["typed_constant_upload"]["hash_mismatch_candidates"],
        )
        self.assertEqual(
            9, report["typed_constant_upload"]["exact_used_vectors"]
        )
        self.assertEqual(
            1, report["typed_constant_upload"]["stable_candidate_families"]
        )
        self.assertEqual(
            ["8240EB60"],
            report["typed_constant_upload"]["caller_return_addresses"],
        )
        self.assertFalse(
            report["qualification"]["complete_typed_upload_bridge_candidate"]
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

    def test_rejects_mechanical_eligibility_accounting_drift(self):
        events = self.fixture()
        events[3]["mechanically_rejected_draws"] = "1"
        with self.assertRaisesRegex(
            ValueError, "candidate mechanical eligibility accounting drift"
        ):
            self.summarize(events)

    def test_rejects_candidate_mask_bounds_drift(self):
        events = self.fixture()
        events[3]["rejection_mask_or"] = "00000000"
        with self.assertRaisesRegex(ValueError, "candidate first mask drift"):
            self.summarize(events)

    def test_rejects_private_capture_accounting_drift(self):
        events = self.fixture()
        events[3]["private_capture_eligible_draws"] = "2"
        with self.assertRaisesRegex(
            ValueError, "candidate private capture accounting drift"
        ):
            self.summarize(events)

    def test_rejects_color_run_accounting_drift(self):
        events = self.fixture()
        events[-1]["color_run_draws"] = "2"
        with self.assertRaisesRegex(ValueError, "color run draw accounting drift"):
            self.summarize(events)

    def test_rejects_constant_identity_scan_accounting_drift(self):
        events = self.fixture()
        events[-1]["constant_identity_scans"] = "2"
        with self.assertRaisesRegex(ValueError, "constant identity scan"):
            self.summarize(events)

    def test_rejects_constant_identity_classification_drift(self):
        events = self.fixture()
        events[3]["constant_identity_classification"] = "unresolved"
        with self.assertRaisesRegex(ValueError, "constant identity classification"):
            self.summarize(events)

    def test_rejects_material_topology_group_accounting_drift(self):
        events = self.fixture()
        events[-1]["material_topology_groups"] = "2"
        with self.assertRaisesRegex(ValueError, "material topology"):
            self.summarize(events)

    def test_rejects_typed_upload_outcome_drift(self):
        events = self.fixture()
        events[-1]["typed_upload_exact_matches"] = "2"
        with self.assertRaisesRegex(ValueError, "typed upload outcome drift"):
            self.summarize(events)

    def test_rejects_typed_upload_candidate_accounting_drift(self):
        events = self.fixture()
        events[-1]["typed_upload_no_overlap_candidates"] = "5"
        with self.assertRaisesRegex(
            ValueError, "typed upload candidate outcome drift"
        ):
            self.summarize(events)

    def test_rejects_private_capture_authority_drift(self):
        events = self.fixture()
        events[5]["output_authority"] = "native"
        with self.assertRaisesRegex(ValueError, "output authority"):
            self.summarize(events)

    def test_rejects_private_replay_accounting_drift(self):
        events = self.fixture()
        events[6]["private_replay_recorded"] = "2"
        with self.assertRaisesRegex(ValueError, "private replay outcome drift"):
            self.summarize(events)

    def test_rejects_retained_frame_accounting_drift(self):
        events = self.fixture()
        events[9]["frames_completed"] = "1"
        with self.assertRaisesRegex(ValueError, "retained frame outcome drift"):
            self.summarize(events)

    def test_runtime_contract_is_default_off_and_full_epoch_gated(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        capture = (ROOT / "tools/capture-native-renderer-census.ps1").read_text(
            encoding="utf-8"
        )
        analysis = (
            ROOT / "config/rexglue/analysis/main-xex.toml"
        ).read_text(encoding="utf-8")
        lr_patch = (
            ROOT
            / "patches/rexglue/0103-codegen-midasm-link-register-argument.patch"
        ).read_text(encoding="utf-8")
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
        self.assertIn(
            '"native_renderer.discovery.vehicle_shadow_color_retained_summary"',
            source,
        )
        self.assertIn("ObserveVehicleColorConstantIdentity", source)
        self.assertIn("ObserveVehicleTypedConstantUpload", source)
        self.assertIn("ObserveVehicleColorTypedConstantUpload", source)
        self.assertIn("MatchObservedVertexConstantSubset", source)
        self.assertIn("mismatched_vector_count", source)
        self.assertNotIn("HashObservedVertexConstantRange", source)
        self.assertNotIn("g_vehicle_constant_uploads = {};", source)
        self.assertIn("g_vehicle_constant_uploads.begin()", source)
        self.assertIn("VehicleConstantUploadEntry{}", source)
        self.assertIn(
            '"82435E78_exact_shader_used_vertex_register_hash"', source
        )
        self.assertIn("constant_position_accounting_complete", source)
        self.assertIn("typed_upload_outcome_accounting_complete", source)
        self.assertIn(
            'registers = ["r3", "r4", "r5", "r6", "lr"]', analysis
        )
        self.assertIn('if (reg == "lr")', lr_patch)
        self.assertIn('out += "ctx.lr"', lr_patch)
        self.assertIn('emit_print(out, "uint64_t& lr")', lr_patch)
        self.assertIn("[switch]$VehicleShadowGeometryCorrelation", capture)
        self.assertIn("[switch]$CaptureVehicleShadowColor", capture)
        self.assertIn("[switch]$RetainVehicleShadowColorPass", capture)
        self.assertIn(
            "VehicleShadowGeometryCorrelation requires ShadowDepthBatch",
            capture,
        )
        self.assertIn(
            "CaptureVehicleShadowColor requires VehicleShadowGeometryCorrelation",
            capture,
        )
        self.assertIn(
            "RetainVehicleShadowColorPass requires CaptureVehicleShadowColor",
            capture,
        )
        self.assertIn('{"native_draw", "false"}', source)
        self.assertIn('{"xenos_authority", "true"}', source)
        self.assertIn('{"suppression_allowed", "false"}', source)


if __name__ == "__main__":
    unittest.main()
