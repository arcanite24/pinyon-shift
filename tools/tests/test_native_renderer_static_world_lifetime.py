import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-static-world-lifetime.py"
SPEC = importlib.util.spec_from_file_location("static_world_lifetime", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    highest = MODULE.RENDERER_VTABLE + 17 * 4
    image = bytearray(highest - MODULE.IMAGE_BASE)
    slots = [0x82800000 + index * 4 for index in range(17)]
    slots[1] = MODULE.GRAPH_BIND
    slots[12] = MODULE.DRAW_DISPATCH
    slots[15] = MODULE.GRAPH_RELEASE
    slots[16] = MODULE.DELETING_DESTRUCTOR
    for index, target in enumerate(slots):
        offset = MODULE.RENDERER_VTABLE + index * 4 - MODULE.IMAGE_BASE
        image[offset : offset + 4] = target.to_bytes(4, "big")
    functions = {
        MODULE.CONSTRUCTOR_WRAPPER: {
            0x82C4E3B0: "li r3,368",
            0x82C4E3B4: "bl 0x82c0f6c0",
            0x82C4E3C0: "bl 0x82c4df78",
            0x82C4E3EC: "li r4,1",
            0x82C4E3F4: "lwz r11,64(r11)",
            0x82C4E3FC: "bctrl",
        },
        MODULE.CONSTRUCTOR: {
            0x82C4DF88: "lis r11,-32256",
            0x82C4DF90: "addi r11,r11,7012",
            0x82C4DF98: "stw r11,0(r31)",
            0x82C4DFCC: "stw r30,72(r31)",
            MODULE.CONSTRUCTOR_PUBLISH_HOOK: "addi r1,r1,112",
        },
        MODULE.DELETING_DESTRUCTOR: {
            0x82C4E43C: "bl 0x82c4e1f8",
            0x82C4E440: "clrlwi. r11,r30,31",
            0x82C4E44C: "bl 0x823fd208",
        },
        MODULE.DESTRUCTOR: {
            0x82C4E210: "addi r11,r11,7012",
            0x82C4E214: "stw r11,0(r3)",
            0x82C4E218: "bl 0x82c4e0a0",
            MODULE.DESTRUCTOR_EXIT_HOOK: "addi r1,r1,96",
        },
        MODULE.CLEANUP: {
            0x82C4E0DC: "lwz r3,72(r31)",
            0x82C4E0E0: "stw r30,72(r31)",
            0x82C4E0F0: "lwz r11,12(r11)",
            0x82C4E0F8: "bctrl",
        },
        MODULE.GRAPH_BIND: {
            0x82C4CC64: "mr r30,r3",
            0x82C4CC98: "addi r3,r30,72",
            0x82C4CC9C: "bl 0x82c48038",
            MODULE.GRAPH_BIND_HOOK: "addi r1,r1,112",
        },
        MODULE.GRAPH_RELEASE: {
            0x82C4C6AC: "lwz r3,72(r3)",
            0x82C4C6B8: "stw r10,72(r11)",
            0x82C4C6C4: "lwz r11,12(r11)",
            0x82C4C6CC: "bctr",
        },
    }
    return functions, bytes(image)


class StaticWorldLifetimeTests(unittest.TestCase):
    def test_proves_renderer_generation_and_owned_graph_field(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertEqual(368, document["renderer"]["object_bytes"])
        self.assertEqual(16, document["renderer"]["deleting_destructor_slot"])
        self.assertEqual(72, document["graph_ownership"]["field_offset"])
        self.assertTrue(
            document["claims"]["renderer_generation_boundary_proved"]
        )
        self.assertFalse(
            document["claims"]["concrete_building_or_prop_identity_proved"]
        )
        self.assertFalse(document["safety"]["native_admission"])

    def test_rejects_vtable_slot_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        offset = MODULE.RENDERER_VTABLE + 16 * 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (0x82C4E424).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "lifecycle vtable drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_graph_bind_field_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.GRAPH_BIND][0x82C4CC98] = "addi r3,r30,76"
        with self.assertRaisesRegex(ValueError, "82C4CC98"):
            MODULE.build(corrupted, image)

    def test_rejects_constructor_extent_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.CONSTRUCTOR_WRAPPER][0x82C4E3B0] = "li r3,364"
        with self.assertRaisesRegex(ValueError, "82C4E3B0"):
            MODULE.build(corrupted, image)


if __name__ == "__main__":
    unittest.main()
