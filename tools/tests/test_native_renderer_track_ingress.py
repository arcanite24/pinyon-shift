import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-track-ingress.py"
SPEC = importlib.util.spec_from_file_location("native_track_ingress", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    next_locator = 0x82370000
    next_type = 0x832C0000
    highest = next_type + len(MODULE.CLASSES) * 0x100 + 0x200
    image = bytearray(highest - MODULE.IMAGE_BASE)
    functions = set()

    def u32(address, value):
        offset = address - MODULE.IMAGE_BASE
        image[offset : offset + 4] = value.to_bytes(4, "big")

    tables = {}
    for class_index, (name, spec) in enumerate(MODULE.CLASSES.items()):
        slots = [
            0x82800000 + class_index * 0x1000 + index * 4
            for index in range(spec["slots"])
        ]
        slots[0] = spec["destructor"]
        for index, target in MODULE.KEY_SLOTS.get(name, {}).items():
            slots[index] = target
        tables[name] = slots

    for derived, baseline, _ in MODULE.RELATIONSHIPS:
        if tables[derived] == tables[baseline]:
            tables[derived][1] += 4

    for class_index, (name, spec) in enumerate(MODULE.CLASSES.items()):
        locator = next_locator + class_index * 0x20
        type_descriptor = next_type + class_index * 0x100
        u32(spec["vtable"] - 4, locator)
        u32(locator + 12, type_descriptor)
        encoded = spec["decorated_name"].encode() + b"\0"
        offset = type_descriptor + 8 - MODULE.IMAGE_BASE
        image[offset : offset + len(encoded)] = encoded
        for index, target in enumerate(tables[name]):
            u32(spec["vtable"] + index * 4, target)
            functions.add(target)
    return functions, bytes(image)


class NativeRendererTrackIngressTests(unittest.TestCase):
    def test_proves_title_track_world_ingress_without_admission(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            "title_track_world_ingress_statically_proved",
            document["classification"],
        )
        self.assertEqual(
            135,
            document["classes"]["track_presentation_unified"]["vtable_slot_count"],
        )
        self.assertEqual(64, document["runtime_graph_probe"]["child_bytes"])
        self.assertEqual(248, document["runtime_graph_probe"]["descriptor_bytes"])
        self.assertEqual(
            7, len(document["runtime_graph_probe"]["direct_vtable_classes"])
        )
        self.assertFalse(document["runtime_graph_probe"]["native_admission"])
        self.assertEqual(
            "heap_readable_and_host_page_mapped",
            document["runtime_graph_probe"]["pointer_validation"],
        )
        self.assertEqual(
            "82DF3F00",
            next(
                row["target"]
                for row in document["passive_observation_candidates"][
                    "track_presentation_unified"
                ]
                if row["slot"] == 132
            ),
        )
        self.assertFalse(document["next_runtime_join"]["proved"])
        self.assertFalse(document["safety"]["runtime_hook_enabled"])
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_rejects_rtti_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        spec = MODULE.CLASSES["track_mesh"]
        locator = MODULE.image_u32(image, spec["vtable"] - 4)
        type_descriptor = MODULE.image_u32(image, locator + 12)
        corrupted[type_descriptor + 8 - MODULE.IMAGE_BASE] = ord("!")
        with self.assertRaisesRegex(ValueError, "track_mesh RTTI evidence drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_key_slot_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        spec = MODULE.CLASSES["track_presentation_unified"]
        offset = spec["vtable"] + 132 * 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (0x82DF3F04).to_bytes(4, "big")
        functions.add(0x82DF3F04)
        with self.assertRaisesRegex(ValueError, "key slot 132 drifted"):
            MODULE.build(functions, bytes(corrupted))


if __name__ == "__main__":
    unittest.main()
