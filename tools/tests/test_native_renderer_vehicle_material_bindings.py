import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-vehicle-material-bindings.py"
SPEC = importlib.util.spec_from_file_location("vehicle_material_bindings", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def summary():
    return {
        "event": MODULE.SUMMARY_EVENT,
        "status": "complete",
        "hook": "82549670",
        "observations": "2",
        "valid_observations": "2",
        "invalid_relation": "0",
        "asset_read_faults": "0",
        "bindings": "1",
        "capacity": "128",
        "overflow": "0",
        "accounting_complete": "true",
        "title_semantic": "tire_wheel_shader_settings",
        "guest_payload_exported": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }


def detail(signatures="1111111111111111,2222222222222222"):
    count = len([value for value in signatures.split(",") if value])
    return {
        "event": MODULE.DETAIL_EVENT,
        "asset_key_hash": "AAAAAAAAAAAAAAAA",
        "asset_key_length": "12",
        "load_ui": "true",
        "slod": "false",
        "observations": "2",
        "root_draw_probe_matches": str(count),
        "binding_draw_probe_matches": "0",
        "backend_signatures": signatures,
        "backend_signature_count": str(count),
        "backend_signature_capacity": "16",
        "backend_signature_overflow": "0",
        "classification": "exact_tire_wheel_material_binding_seed",
        "guest_payload_exported": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }


def contributions():
    return {
        "schema": MODULE.CONTRIBUTION_SCHEMA,
        "status": "qualified",
        "contributions": [
            {
                "geometry_resource_hash": "AAAAAAAAAAAAAAAA",
                "prepared_signatures": [
                    "1111111111111111",
                    "2222222222222222",
                ],
            },
            {
                "geometry_resource_hash": "BBBBBBBBBBBBBBBB",
                "prepared_signatures": [
                    "3333333333333333",
                    "4444444444444444",
                ],
            },
        ],
        "qualification": {
            "exact_resource_contribution_partition_proved": True,
        },
        "safety": {
            "source_xenos_authority": True,
        },
    }


def summarize(events, contribution_document=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        log_path = root / "events.jsonl"
        contribution_path = root / "contributions.json"
        log_path.write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )
        contribution_path.write_text(
            json.dumps(contribution_document or contributions()),
            encoding="utf-8",
        )
        return MODULE.summarize(log_path, contribution_path)


class VehicleMaterialBindingTests(unittest.TestCase):
    def test_qualifies_unique_two_variant_join(self):
        report = summarize([summary(), detail()])
        self.assertEqual("qualified", report["status"])
        self.assertEqual(
            ["AAAAAAAAAAAAAAAA"], report["matched_geometry_resources"]
        )
        self.assertTrue(
            report["qualification"]["unique_geometry_resource_join_proved"]
        )
        self.assertFalse(
            report["qualification"]["tire_wheel_visual_role_proved"]
        )

    def test_reports_no_direct_draw_join(self):
        report = summarize([summary(), detail("")])
        self.assertEqual("bounded_negative_result", report["status"])
        self.assertEqual(
            ["no_direct_binding_to_draw_join"], report["failures"]
        )

    def test_rejects_ambiguous_contribution_join(self):
        report = summarize(
            [summary(), detail("1111111111111111,3333333333333333")]
        )
        self.assertEqual("bounded_negative_result", report["status"])
        self.assertEqual(2, len(report["matched_geometry_resources"]))
        self.assertEqual(
            ["binding_to_geometry_join_not_unique"], report["failures"]
        )

    def test_rejects_changed_authority(self):
        row = detail()
        row["xenos_authority"] = "false"
        with self.assertRaisesRegex(ValueError, "Xenos authority"):
            summarize([summary(), row])


if __name__ == "__main__":
    unittest.main()
