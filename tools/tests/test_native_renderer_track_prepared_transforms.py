import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/classify-native-renderer-track-prepared-transforms.py"
SPEC = importlib.util.spec_from_file_location("track_prepared_transforms", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def catalog():
    instances = [
        {
            "category": "collision_prop",
            "identity_hash": f"{index + 1:016X}",
            "position": [float(index * 10 + 1), float(index * 10 + 2), float(index * 10 + 3)],
        }
        for index in range(8)
    ]
    return {
        "schema": MODULE.CATALOG_SCHEMA,
        "status": "complete",
        "instance_count": len(instances),
        "instances": instances,
        "safety": {
            "source_files_changed": False,
            "plaintext_identity_exported": False,
            "numeric_spatial_metadata_only": True,
            "native_admission": False,
            "suppression_allowed": False,
        },
    }


def prepared():
    runs = []
    for index in range(8):
        position = (float(index * 10 + 1), float(index * 10 + 2), float(index * 10 + 3))
        values = (
            (1.0, 0.0, 0.0, 1000.0 + index),
            (0.0, 1.0, 0.0, 2000.0 + index),
            (0.0, 0.0, 1.0, 3000.0 + index),
            (*position, 1.0),
        )
        runs.append(
            {
                "layout_key": f"{index + 100:016X}",
                "vertex_shader": "1111222233334444",
                "calls": 1,
                "start_register": 4,
                "end_register": 7,
                "register_count": 4,
                "registers": [
                    {"index": register + 4, "words": ["00000000"] * 4, "values": list(row)}
                    for register, row in enumerate(values)
                ],
            }
        )
    return {
        "schema": MODULE.PREPARED_SCHEMA,
        "session": "test",
        "status": "complete",
        "vertex_consecutive_register_runs": runs,
        "vertex_shader_layout_frequency": [
            {
                "vertex_shader": "1111222233334444",
                "layouts": 8,
                "calls": 8,
            }
        ],
        "qualification": {
            "exact_track_prepared_layouts_proved": True,
            "world_transform_constant_layout_proved": False,
        },
        "safety": {
            "guest_state_changed": False,
            "control_flow_changed": False,
            "xenos_authority": True,
            "native_admission": False,
            "suppression_allowed": False,
        },
    }


class TrackPreparedTransformTests(unittest.TestCase):
    def test_proves_unique_shader_register_and_matrix_convention(self):
        document = MODULE.build(catalog(), prepared())
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            {
                "vertex_shader": "1111222233334444",
                "start_register": 4,
                "convention": "translation_words_12_13_14",
            },
            document["selected_mapping"],
        )
        self.assertTrue(
            document["qualification"]["world_transform_constant_layout_proved"]
        )
        self.assertFalse(document["qualification"]["native_admission"])

    def test_rejects_ambiguous_catalog_position(self):
        duplicated = catalog()
        duplicate = copy.deepcopy(duplicated["instances"][0])
        duplicate["identity_hash"] = "FFFFFFFFFFFFFFFF"
        duplicated["instances"].append(duplicate)
        duplicated["instance_count"] += 1
        document = MODULE.build(duplicated, prepared())
        self.assertEqual("incomplete", document["status"])
        self.assertIsNone(document["selected_mapping"])

    def test_rejects_unsafe_prepared_report(self):
        report = prepared()
        report["safety"]["xenos_authority"] = False
        with self.assertRaisesRegex(ValueError, "safety drifted"):
            MODULE.build(catalog(), report)

    def test_rejects_too_few_distinct_matches(self):
        document = MODULE.build(catalog(), prepared(), minimum_matches=9)
        self.assertEqual("incomplete", document["status"])


if __name__ == "__main__":
    unittest.main()
