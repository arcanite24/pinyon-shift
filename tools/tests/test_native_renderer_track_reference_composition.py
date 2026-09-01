import importlib.util
import pathlib
import struct
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/classify-native-renderer-track-reference-composition.py"
SPEC = importlib.util.spec_from_file_location("track_reference_composition", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def word(value):
    return f"{int.from_bytes(struct.pack('>f', float(value)), 'big'):08X}"


def safety():
    return {
        "guest_state_changed": "false", "control_flow_changed": "false",
        "native_admission": "false", "xenos_authority": "true",
        "suppression_allowed": "false",
    }


def catalog():
    instances = [
        {
            "category": "collision_prop" if index == 0 else "gameplay_object",
            "identity_hash": f"{index + 1:016X}",
            "position": [index * 10.0 + 1, index * 10.0 + 2, index * 10.0 + 3],
        }
        for index in range(8)
    ]
    return {
        "schema": MODULE.SCOPE.CATALOG_SCHEMA, "status": "complete",
        "instance_count": 8, "instances": instances,
        "safety": {
            "source_files_changed": False, "plaintext_identity_exported": False,
            "numeric_spatial_metadata_only": True, "native_admission": False,
            "suppression_allowed": False,
        },
    }


def words(values):
    return ":".join(word(value) for value in values)


def evidence():
    object_reference = [2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1]
    bad_reference = [3, 0, 0, 0, 0, 3, 0, 0, 0, 0, 3, 0, 1000, 1000, 1000, 1]
    events = [{"event": "process.start", "session": "test"}]
    for index in range(8):
        child_address = f"{0x1000 + index * 0x100:08X}"
        descriptor_address = f"{0x2000 + index * 0x100:08X}"
        position = [index * 10.0 + 1, index * 10.0 + 2, index * 10.0 + 3]
        local_position = [value / 2 for value in position]
        local = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, *local_position, 1]
        descriptor = [3000 + index] * 8 + local + [4000 + index] * 38
        events.append({
            "event": MODULE.SCOPE.ENTRY, "session": "test",
            "snapshot_key": f"{index + 1:016X}",
            "snapshot_hash": f"{index + 1001:016X}",
            "child_address": child_address, "descriptor_address": descriptor_address,
            "calls": "1", "first_frame": "1", "last_frame": "2",
            "snapshot_variations": "0", "child_word_count": "16",
            "child_words": words([5000 + index] * 16),
            "descriptor_word_count": "62", "descriptor_words": words(descriptor),
            **safety(),
        })
        events.append({
            "event": MODULE.REFERENCE_ENTRY, "session": "test",
            "snapshot_key": f"{index + 101:016X}",
            "scope_snapshot_hash": f"{index + 1001:016X}",
            "child_address": child_address, "descriptor_address": descriptor_address,
            "calls": "1", "first_frame": "1", "last_frame": "2",
            "object_matrix_word_count": "16", "object_matrix_words": words(object_reference),
            "composed_matrix_word_count": "16", "composed_matrix_words": words(bad_reference),
            **safety(),
        })
    events.extend([
        {
            "event": MODULE.SCOPE.SUMMARY, "session": "test", "checkpoint_kind": "final",
            "scope_spatial_entries": "8", "scope_spatial_observations": "8",
            "scope_spatial_table_overflow": "0", "scope_spatial_accounting_complete": "true",
            "reference_spatial_entries": "8", "reference_spatial_observations": "8",
            "reference_spatial_missing_stage": "0", "reference_spatial_table_overflow": "0",
            "reference_spatial_accounting_complete": "true", **safety(),
        },
        {"event": "process.shutdown", "session": "test"},
    ])
    return events


class TrackReferenceCompositionTests(unittest.TestCase):
    def test_proves_unique_local_reference_composition(self):
        document = MODULE.build(evidence(), catalog())
        self.assertEqual("complete", document["status"])
        self.assertEqual("descriptor", document["selected_mapping"]["local_source"])
        self.assertEqual(8, document["selected_mapping"]["word_offset"])
        self.assertEqual("object_matrix", document["selected_mapping"]["reference_source"])
        self.assertEqual("translation_words_12_13_14", document["selected_mapping"]["convention"])

    def test_rejects_missing_exact_stage(self):
        events = evidence()
        events[-2]["reference_spatial_missing_stage"] = "1"
        events[-2]["reference_spatial_accounting_complete"] = "false"
        with self.assertRaisesRegex(ValueError, "accounting is incomplete"):
            MODULE.build(events, catalog())

    def test_source_contract_is_exact_and_passive(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(encoding="utf-8")
        self.assertIn("kTrackWorldReferenceSpatialCapacity = 2048", source)
        self.assertIn("StageTrackWorldReferenceSpatial(r22.u32, r5.u32)", source)
        self.assertIn("ConsumeTrackWorldReferenceSpatial(child_address, descriptor_address,", source)
        self.assertNotIn("g_pending_track_world_reference_spatial = {};\n  if (!snapshot.valid)", source)
        self.assertIn(MODULE.REFERENCE_ENTRY, source)
        self.assertIn('"suppression_allowed", "false"', source)


if __name__ == "__main__":
    unittest.main()
