import copy
import importlib.util
import pathlib
import struct
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = (
    ROOT
    / "tools"
    / "summarize-native-renderer-static-world-instance-classification.py"
)
SPEC = importlib.util.spec_from_file_location(
    "static_world_instance_classification", TOOL
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def word(value):
    return f"{int.from_bytes(struct.pack('>f', value), 'big'):08X}"


def catalog(duplicate=False):
    instances = []
    for index in range(8):
        instances.append(
            {
                "category": "collision_prop" if index < 6 else "gameplay_object",
                "source_ordinal": index,
                "identity_hash": f"{index + 1:016X}",
                "identity_field_hashes": {},
                "position": [float(index * 10 + 1), float(index + 2), float(-index)],
                "orientation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            }
        )
    if duplicate:
        extra = copy.deepcopy(instances[0])
        extra["identity_hash"] = "00000000000000FF"
        instances.append(extra)
    return {
        "schema": MODULE.CATALOG_SCHEMA,
        "status": "complete",
        "sources": [],
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


def events():
    session = "session-1"
    result = [
        {"event": "process.start", "session": session},
        {"event": MODULE.CONFIG, "session": session},
    ]
    for index in range(8):
        words = [word(0.0)] * 16
        words[0] = words[5] = words[10] = words[15] = word(1.0)
        words[12] = word(float(index * 10 + 1))
        words[13] = word(float(index + 2))
        words[14] = word(float(-index))
        result.append(
            {
                "event": MODULE.PROVENANCE,
                "session": session,
                "outcome": "prepared",
                "static_world_origin": "true",
                "static_world_transform_valid": "true",
                "static_world_transform_hash": f"{index + 100:016X}",
                "static_world_transform_words": ":".join(words),
                "calls": str(index + 1),
                "xenos_draw": "preserved",
                "suppression_eligible": "false",
            }
        )
    result.extend(
        [
            {
                "event": MODULE.SUMMARY,
                "session": session,
                "status": "complete",
                "qualification_complete": "true",
            },
            {"event": "process.shutdown", "session": session},
        ]
    )
    return result


def track_events():
    result = events()
    for event in result:
        if event.get("event") == MODULE.PROVENANCE:
            event["unified_track_mesh_origin"] = "true"
            event["unified_track_mesh_transform_hash"] = event.pop(
                "static_world_transform_hash"
            )
            event["unified_track_mesh_transform_words"] = event.pop(
                "static_world_transform_words"
            ).replace(":", ",")
            event["static_world_origin"] = "false"
            event["static_world_transform_valid"] = ""
    result[-2] = {
        "event": MODULE.DIRECT_SUMMARY,
        "session": "session-1",
        "status": "complete",
        "accounting_complete": "true",
        "scope_accounting_complete": "true",
        "prepared_join_accounting_complete": "true",
        "unified_track_mesh_scopes_exact": "8",
        "unified_track_mesh_scopes_without_packets": "0",
        "unified_track_mesh_prepared_matches": "8",
        "unified_track_mesh_unprepared_matches": "0",
    }
    return result


class StaticWorldInstanceClassificationTests(unittest.TestCase):
    def test_proves_unique_row_translation_join(self):
        document = MODULE.build(catalog(), events())
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            "translation_words_12_13_14",
            document["selected_matrix_convention"],
        )
        self.assertEqual(
            {"collision_prop": 6, "gameplay_object": 2},
            document["category_counts"],
        )
        self.assertTrue(
            document["qualification"][
                "building_or_prop_instance_identity_proved"
            ]
        )
        self.assertFalse(document["qualification"]["native_admission"])

    def test_rejects_ambiguous_spatial_match(self):
        document = MODULE.build(catalog(duplicate=True), events())
        self.assertEqual("incomplete", document["status"])
        self.assertEqual(
            1,
            document["conventions"]["translation_words_12_13_14"]["ambiguous"],
        )
        self.assertFalse(
            document["qualification"]["runtime_transform_join_proved"]
        )

    def test_rejects_incomplete_runtime_summary(self):
        observed = events()
        observed[-2]["status"] = "incomplete"
        document = MODULE.build(catalog(), observed)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "runtime transform qualification is incomplete",
            document["failures"],
        )

    def test_rejects_gameplay_only_classification(self):
        gameplay_catalog = catalog()
        for instance in gameplay_catalog["instances"]:
            instance["category"] = "gameplay_object"
        document = MODULE.build(gameplay_catalog, events())
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "no collision-prop runtime transform was classified",
            document["failures"],
        )

    def test_rejects_unsafe_runtime_provenance(self):
        observed = events()
        observed[2]["suppression_eligible"] = "true"
        document = MODULE.build(catalog(), observed)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "runtime provenance violated Xenos authority", document["failures"]
        )

    def test_proves_unified_track_mesh_prepared_join(self):
        document = MODULE.build(
            catalog(), track_events(), origin="unified_track_mesh"
        )
        self.assertEqual("complete", document["status"])
        self.assertEqual("unified_track_mesh", document["runtime_origin"])
        self.assertTrue(
            document["qualification"][
                "building_or_prop_instance_identity_proved"
            ]
        )

    def test_rejects_incomplete_track_packet_join(self):
        observed = track_events()
        observed[-2]["unified_track_mesh_scopes_without_packets"] = "1"
        document = MODULE.build(catalog(), observed, origin="unified_track_mesh")
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "runtime transform qualification is incomplete",
            document["failures"],
        )


if __name__ == "__main__":
    unittest.main()
