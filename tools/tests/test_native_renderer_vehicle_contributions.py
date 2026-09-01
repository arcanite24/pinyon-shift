import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-vehicle-contributions.py"
SPEC = importlib.util.spec_from_file_location("vehicle_contributions", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def family(contribution, variant):
    token = f"{contribution + 1:016X}"
    signature = f"{0x100 + contribution * 2 + variant:016X}"
    return {
        "seed_index": contribution,
        "geometry_resource_hash": token,
        "prepared_signature": signature,
        "draw_argument_hash": f"{0x200 + contribution:016X}",
        "material_topology_key": "0000000000000300",
        "pixel_shader": "0000000000000400",
        "prepared_pipeline_hash": "0000000000000500",
        "render_state_hash": "0000000000000600",
        "template_key": f"{0x700 + contribution:016X}",
        "texture_layout_hash": "0000000000000800",
        "texture_resource_hash": "0000000000000900",
        "vertex_shader": "0000000000000A00",
        "draws": 20,
        "semantic_constant_bridge_publications": 20,
    }


def fixture():
    families = [
        family(contribution, variant)
        for contribution in range(15)
        for variant in range(2)
    ]
    return {
        "schema": MODULE.INPUT_SCHEMA,
        "safety": {
            "xenos_authority": True,
            "native_draw": False,
            "suppression_allowed": False,
            "guest_payload_capture": False,
        },
        "qualification": {
            "working_color_bridge_candidate": True,
            "native_admission_allowed": False,
        },
        "totals": {"correlations": len(families)},
        "candidate_families": families,
    }


def summarize(document):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "report.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return MODULE.summarize(path)


class VehicleContributionTests(unittest.TestCase):
    def test_partitions_thirty_families_into_fifteen_resources(self):
        report = summarize(fixture())
        self.assertEqual("qualified", report["status"])
        self.assertEqual(30, report["summary"]["candidate_family_count"])
        self.assertEqual(15, report["summary"]["resource_contribution_count"])
        self.assertEqual(15, report["summary"]["complete_resource_contributions"])
        self.assertTrue(
            report["qualification"][
                "exact_resource_contribution_partition_proved"
            ]
        )
        self.assertFalse(
            report["qualification"]["semantic_mesh_material_roles_proved"]
        )
        self.assertTrue(
            all(
                row["semantic_role"] == "unclassified"
                and not row["semantic_label_proved"]
                for row in report["contributions"]
            )
        )

    def test_rejects_missing_pass_variant(self):
        document = fixture()
        document["candidate_families"][-1]["geometry_resource_hash"] = (
            "FFFFFFFFFFFFFFFF"
        )
        report = summarize(document)
        self.assertEqual("incomplete", report["status"])
        self.assertTrue(any("variant_count" in row for row in report["failures"]))

    def test_rejects_mechanical_drift_within_resource(self):
        document = fixture()
        document["candidate_families"][1]["template_key"] = "FFFFFFFFFFFFFFFF"
        report = summarize(document)
        self.assertEqual("incomplete", report["status"])
        self.assertTrue(
            any("mechanical_contract_drift" in row for row in report["failures"])
        )

    def test_accepts_one_trailing_partial_frame(self):
        document = fixture()
        document["candidate_families"][1]["draws"] = 19
        document["candidate_families"][1][
            "semantic_constant_bridge_publications"
        ] = 19
        report = summarize(document)
        self.assertEqual("qualified", report["status"])

    def test_rejects_multi_frame_draw_count_drift(self):
        document = fixture()
        document["candidate_families"][1]["draws"] = 18
        document["candidate_families"][1][
            "semantic_constant_bridge_publications"
        ] = 18
        report = summarize(document)
        self.assertEqual("incomplete", report["status"])
        self.assertTrue(
            any("draw_count_drift" in row for row in report["failures"])
        )

    def test_rejects_changed_authority(self):
        document = fixture()
        document["safety"]["xenos_authority"] = False
        with self.assertRaisesRegex(ValueError, "Xenos authority"):
            summarize(document)

    def test_private_capture_is_targeted_and_preserves_xenos(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        capture = (ROOT / "tools/capture-native-renderer-census.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("VEHICLE_RESOURCE_CONTRIBUTION", hooks)
        self.assertIn("CompleteVehicleResourceContributionReadback", hooks)
        self.assertIn("retain_first_release_second", hooks)
        self.assertIn('"xenos_draw", "preserved"', hooks)
        self.assertIn('"suppression_allowed", "false"', hooks)
        self.assertIn("[string]$VehicleResourceContribution", capture)
        self.assertIn(
            "VehicleResourceContribution and RetainVehicleShadowColorPass",
            capture,
        )


if __name__ == "__main__":
    unittest.main()
