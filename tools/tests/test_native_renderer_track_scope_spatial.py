import copy
import importlib.util
import pathlib
import struct
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/classify-native-renderer-track-scope-spatial.py"
SPEC = importlib.util.spec_from_file_location("track_scope_spatial", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def word(value):
    return f"{int.from_bytes(struct.pack('>f', float(value)), 'big'):08X}"


def catalog():
    instances = [
        {
            "category": "collision_prop" if index == 0 else "gameplay_object",
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


def event(name, session="test", **values):
    return {"event": name, "session": session, **values}


def evidence():
    safety = {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    events = [event("process.start")]
    for index in range(8):
        position = (index * 10 + 1, index * 10 + 2, index * 10 + 3)
        matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, *position, 1]
        descriptor = [word(1000 + index)] * 8 + [word(value) for value in matrix] + [word(2000 + index)] * 38
        events.append(event(
            MODULE.ENTRY,
            snapshot_key=f"{index + 1:016X}",
            child_address=f"{0x1000 + index * 0x100:08X}",
            descriptor_address=f"{0x2000 + index * 0x100:08X}",
            calls="1", first_frame="1", last_frame="2",
            snapshot_variations="0", child_word_count="16",
            child_words=":".join([word(3000 + index)] * 16),
            descriptor_word_count="62", descriptor_words=":".join(descriptor),
            **safety,
        ))
    events.extend([
        event(MODULE.SUMMARY, checkpoint_kind="final", scope_spatial_entries="8",
              scope_spatial_observations="8", scope_spatial_table_overflow="0",
              scope_spatial_accounting_complete="true", **safety),
        event("process.shutdown"),
    ])
    return events


class TrackScopeSpatialTests(unittest.TestCase):
    def test_proves_unique_descriptor_matrix_window(self):
        document = MODULE.build(evidence(), catalog())
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            {"source": "descriptor", "word_offset": 8, "convention": "translation_words_12_13_14"},
            document["selected_mapping"],
        )
        self.assertFalse(document["qualification"]["native_admission"])

    def test_reports_unmatched_windows_without_admission(self):
        changed = catalog()
        for instance in changed["instances"]:
            instance["position"] = [value + 0.5 for value in instance["position"]]
        document = MODULE.build(evidence(), changed)
        self.assertEqual("incomplete", document["status"])
        self.assertIsNone(document["selected_mapping"])
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_rejects_snapshot_variation(self):
        events = evidence()
        events[1]["snapshot_variations"] = "1"
        with self.assertRaisesRegex(ValueError, "unstable"):
            MODULE.build(events, catalog())

    def test_rejects_unsafe_summary(self):
        events = copy.deepcopy(evidence())
        events[-2]["xenos_authority"] = "false"
        with self.assertRaisesRegex(ValueError, "violates safety"):
            MODULE.build(events, catalog())

    def test_source_contract_is_passive_and_bounded(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(encoding="utf-8")
        self.assertIn("kTrackWorldScopeSpatialCapacity = 1024", source)
        self.assertIn("RecordTrackWorldScopeSpatialSnapshot", source)
        self.assertIn(MODULE.ENTRY, source)
        self.assertIn('"scope_spatial_export", "numeric_words_hash_variation_only"', source)
        self.assertIn('"native_admission", "false"', source)
        self.assertIn('"suppression_allowed", "false"', source)


if __name__ == "__main__":
    unittest.main()
