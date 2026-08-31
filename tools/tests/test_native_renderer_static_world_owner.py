import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-static-world-owner.py"
SPEC = importlib.util.spec_from_file_location("static_world_owner", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    highest = max(
        MODULE.PRESENTATION_VTABLE + MODULE.PRESENTATION_SLOT_COUNT * 4,
        MODULE.RENDERER_VTABLE + 17 * 4,
    )
    image = bytearray(highest - MODULE.IMAGE_BASE)
    presentation_slots = [0x82800000 + index * 4 for index in range(18)]
    presentation_slots[0] = MODULE.PRESENTATION_DELETING_DESTRUCTOR
    presentation_slots[12] = MODULE.PRESENTATION_DRAW
    renderer_slots = [0x82900000 + index * 4 for index in range(17)]
    renderer_slots[0] = 0x82C4C838
    renderer_slots[12] = 0x82C4CCC8
    for base, slots in (
        (MODULE.PRESENTATION_VTABLE, presentation_slots),
        (MODULE.RENDERER_VTABLE, renderer_slots),
    ):
        for index, target in enumerate(slots):
            offset = base + index * 4 - MODULE.IMAGE_BASE
            image[offset : offset + 4] = target.to_bytes(4, "big")
    functions = {
        MODULE.PRESENTATION_CONSTRUCTOR: {
            0x82DE9864: "lis r11,-32220",
            0x82DE9878: "addi r10,r10,13012",
            0x82DE9884: "stw r10,0(r31)",
            0x82DE98E0: "stw r30,144(r31)",
            0x82DE98E4: "stw r30,148(r31)",
            0x82DE993C: "stw r30,1608(r31)",
        },
        MODULE.PRESENTATION_DESTRUCTOR: {
            0x82DEA230: "addi r11,r11,13012",
            0x82DEA238: "stw r11,0(r3)",
            0x82DEA244: "bl 0x82de9f10",
            0x82DEA260: "addi r3,r31,148",
            0x82DEA264: "bl 0x82de7330",
        },
        MODULE.PRESENTATION_DELETING_DESTRUCTOR: {
            0x82DEA524: "bl 0x82dea218",
            0x82DEA530: "mr r3,r31",
            0x82DEA534: "bl 0x823fd208",
        },
        MODULE.PRESENTATION_PREPARE: {
            0x823F89A4: "lwz r11,148(r24)",
            0x823F89A8: "addi r31,r24,148",
            0x823F8A14: "bl 0x82c4e3a0",
            0x823F8A18: "stw r3,1608(r24)",
            0x823F8A28: "lwz r3,1608(r24)",
            0x823F8A34: "lwz r11,0(r11)",
            0x823F8A3C: "bctrl",
            0x823F8A44: "stw r11,144(r24)",
        },
        MODULE.PRESENTATION_DRAW: {
            0x823F8DC4: "mr r31,r3",
            0x823F8DDC: "bl 0x823f8980",
            0x823F8E20: "lwz r11,1608(r31)",
            0x823F8F0C: "lwz r3,1608(r31)",
            0x823F8F18: "lwz r11,48(r11)",
            0x823F8F20: "bctrl",
            MODULE.PRESENTATION_DRAW_EXIT: "addi r1,r1,160",
        },
    }
    return functions, bytes(image)


class StaticWorldOwnerTests(unittest.TestCase):
    def test_proves_exact_presentation_to_renderer_owner(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            148, document["presentation"]["resource_reference_offset"]
        )
        self.assertEqual(1608, document["presentation"]["renderer_field_offset"])
        self.assertEqual("82C4CCC8", document["renderer_join"]["draw_target"])
        self.assertTrue(
            document["claims"]["exact_model_presentation_owner_proved"]
        )
        self.assertFalse(
            document["claims"]["concrete_building_or_prop_identity_proved"]
        )
        self.assertFalse(document["safety"]["native_admission"])

    def test_rejects_presentation_draw_slot_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        offset = MODULE.PRESENTATION_VTABLE + 12 * 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (0x823F8DBC).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "draw slot drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_renderer_field_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.PRESENTATION_PREPARE][0x823F8A18] = (
            "stw r3,1604(r24)"
        )
        with self.assertRaisesRegex(ValueError, "823F8A18"):
            MODULE.build(corrupted, image)

    def test_rejects_unbalanced_exit_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.PRESENTATION_DRAW][MODULE.PRESENTATION_DRAW_EXIT] = (
            "addi r1,r1,156"
        )
        with self.assertRaisesRegex(ValueError, "823F8FA0"):
            MODULE.build(corrupted, image)


if __name__ == "__main__":
    unittest.main()
