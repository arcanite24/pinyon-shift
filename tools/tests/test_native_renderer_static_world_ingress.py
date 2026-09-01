import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-static-world-ingress.py"
SPEC = importlib.util.spec_from_file_location("static_world_ingress", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    highest = max(
        spec["type_descriptor"] for spec in MODULE.CLASSES.values()
    ) + 0x200
    image = bytearray(highest - MODULE.IMAGE_BASE)
    functions = set()

    def u32(address, value):
        offset = address - MODULE.IMAGE_BASE
        image[offset : offset + 4] = value.to_bytes(4, "big")

    for class_index, spec in enumerate(MODULE.CLASSES.values()):
        type_descriptor = spec["type_descriptor"]
        encoded = spec["decorated_name"].encode() + b"\0"
        offset = type_descriptor + 8 - MODULE.IMAGE_BASE
        image[offset : offset + len(encoded)] = encoded
        for surface_index, surface in enumerate(spec["surfaces"]):
            _, locator, vtable, slot_count, slot_zero_target = surface
            u32(locator + 12, type_descriptor)
            u32(vtable - 4, locator)
            slots = [
                0x82800000
                + class_index * 0x1000
                + surface_index * 0x100
                + index * 4
                for index in range(slot_count)
            ]
            slots[0] = slot_zero_target
            for index, target in enumerate(slots):
                u32(vtable + index * 4, target)
                if target not in MODULE.REVIEWED_THUNKS:
                    functions.add(target)

    for address, body in MODULE.REVIEWED_THUNKS.items():
        offset = address - MODULE.IMAGE_BASE
        image[offset : offset + len(body)] = body
    return functions, bytes(image)


class StaticWorldIngressTests(unittest.TestCase):
    def test_proves_simple_model_surfaces_without_runtime_claims(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertEqual(7, len(document["classes"]))
        self.assertEqual(
            6,
            document["classes"]["simple_mesh"]["surfaces"][0][
                "vtable_slot_count"
            ],
        )
        self.assertEqual(
            [0],
            document["classes"]["simple_model_renderer_deferred"][
                "surfaces"
            ][0]["reviewed_thunk_slots"],
        )
        renderer_surface = document["classes"]["simple_model_renderer"][
            "surfaces"
        ][0]
        self.assertEqual("82C4C838", renderer_surface["slot_zero_target"])
        self.assertNotIn("deleting_destructor", renderer_surface)
        self.assertFalse(
            document["topology"]["building_or_prop_instance_identity_proved"]
        )
        self.assertFalse(document["next_runtime_join"]["proved"])
        self.assertFalse(document["safety"]["runtime_hook_enabled"])
        self.assertFalse(document["safety"]["native_admission"])
        self.assertTrue(document["safety"]["xenos_authority_required"])

    def test_rejects_rtti_name_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        type_descriptor = MODULE.CLASSES["simple_mesh"]["type_descriptor"]
        corrupted[type_descriptor + 8 - MODULE.IMAGE_BASE] = ord("!")
        with self.assertRaisesRegex(ValueError, "simple_mesh RTTI evidence"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_vtable_locator_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        surface = MODULE.CLASSES["simple_model"]["surfaces"][1]
        _, _, vtable, _, _ = surface
        offset = vtable - 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (0).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "vtable locator drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_unknown_slot_target(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        surface = MODULE.CLASSES["simple_model_renderer"]["surfaces"][0]
        _, _, vtable, _, _ = surface
        offset = vtable + 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (0x82000004).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "unknown slot target"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_vtable_extent_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        surface = MODULE.CLASSES["simple_mesh"]["surfaces"][0]
        _, _, vtable, slot_count, _ = surface
        target = 0x8287F000
        offset = vtable + slot_count * 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = target.to_bytes(4, "big")
        functions.add(target)
        with self.assertRaisesRegex(ValueError, "vtable extent drifted"):
            MODULE.build(functions, bytes(corrupted))


if __name__ == "__main__":
    unittest.main()
