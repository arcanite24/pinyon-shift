import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-static-world-resource.py"
SPEC = importlib.util.spec_from_file_location("static_world_resource", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    image = bytearray(MODULE.RESOURCE_VTABLE + 4 - MODULE.IMAGE_BASE)
    offset = MODULE.RESOURCE_VTABLE - MODULE.IMAGE_BASE
    image[offset : offset + 4] = MODULE.RESOURCE_DELETING_DESTRUCTOR.to_bytes(
        4, "big"
    )
    functions = {
        MODULE.RENDERER_BIND: {
            0x82C48044: "mr r30,r3",
            0x82C480A8: "mr r5,r30",
            0x82C480B4: "bl 0x82c47f10",
            0x82C480C4: "lwz r30,0(r30)",
            0x82C480E4: "bl 0x82e4bff8",
        },
        MODULE.RESOURCE_FACTORY: {
            0x82C47F70: "lwz r11,0(r31)",
            0x82C47F78: "bne cr6,0x82c4802c",
            0x82C47F94: "li r3,320",
            0x82C47F98: "bl 0x82c0f6c0",
            0x82C47FA8: "bl 0x82c47da0",
            0x82C47FAC: "lis r11,-32221",
            0x82C47FB4: "addi r11,r11,-28012",
            0x82C47FB8: "stw r11,0(r29)",
            MODULE.RESOURCE_PUBLISH_HOOK: "b 0x82c47fc4",
            0x82C47FC4: "mr r3,r31",
            0x82C47FC8: "bl 0x824e81a8",
            0x82C4800C: "bl 0x82d842f8",
            0x82C48010: "lwz r11,0(r31)",
            MODULE.RESOURCE_REGISTRATION_HOOK: "mr r3,r27",
        },
        MODULE.RESOURCE_CONSTRUCTOR: {
            0x82C47DB4: "bl 0x82e45a78",
            0x82C47DC8: "stw r11,0(r31)",
            0x82C47DD8: "bl 0x82c47ca0",
        },
        MODULE.REFERENCE_ASSIGN: {
            0x824E81CC: "lwz r11,0(r4)",
            0x824E81D4: "lwz r11,8(r11)",
            0x824E81E0: "lwz r3,0(r30)",
            0x824E81E4: "stw r31,0(r30)",
            0x824E81F4: "lwz r11,12(r11)",
        },
        MODULE.RESOURCE_DELETING_DESTRUCTOR: {
            0x82C47EDC: "bl 0x82c47df8",
            0x82C47EE0: "clrlwi. r11,r30,31",
            0x82C47EEC: "bl 0x823fd208",
        },
        MODULE.RESOURCE_DESTRUCTOR: {
            0x82C47E10: "mr r30,r3",
            0x82C47E40: "bl 0x82e45b20",
            MODULE.RESOURCE_DESTRUCTOR_EXIT_HOOK: "addi r1,r1,112",
        },
    }
    return functions, bytes(image)


class StaticWorldResourceTests(unittest.TestCase):
    def test_proves_bound_graph_resource_type_and_lifetime(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertEqual("82229294", document["resource"]["vtable"])
        self.assertEqual(320, document["resource"]["object_bytes"])
        self.assertTrue(
            document["claims"]["bound_graph_dynamic_type_proved"]
        )
        self.assertFalse(
            document["claims"]["concrete_building_or_prop_identity_proved"]
        )
        self.assertFalse(document["safety"]["native_admission"])

    def test_rejects_resource_vtable_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        offset = MODULE.RESOURCE_VTABLE - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (0x82C47EC4).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "deleting destructor drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_factory_output_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.RENDERER_BIND][0x82C480A8] = "mr r5,r31"
        with self.assertRaisesRegex(ValueError, "82C480A8"):
            MODULE.build(corrupted, image)

    def test_rejects_registration_join_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.RESOURCE_FACTORY][0x82C48010] = "lwz r11,4(r31)"
        with self.assertRaisesRegex(ValueError, "82C48010"):
            MODULE.build(corrupted, image)


if __name__ == "__main__":
    unittest.main()
