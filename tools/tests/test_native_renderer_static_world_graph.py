import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-static-world-graph.py"
SPEC = importlib.util.spec_from_file_location("static_world_graph", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    image = bytearray(MODULE.MODEL_VTABLE + 5 * 4 - MODULE.IMAGE_BASE)
    for vtable, slot, target in (
        (MODULE.MODEL_VTABLE, 2, 0x824385D0),
        (MODULE.MODEL_VTABLE, 4, 0x82C25388),
        (MODULE.SUBMODEL_VTABLE, 3, 0x82C256D0),
        (MODULE.SUBMODEL_VTABLE, 5, 0x82C256E8),
    ):
        offset = vtable + slot * 4 - MODULE.IMAGE_BASE
        image[offset : offset + 4] = target.to_bytes(4, "big")
    functions = {
        MODULE.RESOURCE_CONSTRUCTOR: {
            0x82C47DD4: "addi r3,r31,112",
            0x82C47DD8: "bl 0x82c47ca0",
        },
        MODULE.MODEL_CONSTRUCTOR: {
            0x82C47CB4: "bl 0x82c46760",
            0x82C47CE0: "addi r9,r9,-28152",
            0x82C47CE4: "addi r8,r8,-28184",
            0x82C47CF0: "stw r9,0(r31)",
            0x82C47CF4: "stw r8,132(r31)",
            0x82C47D00: "stw r11,176(r31)",
            0x82C47D10: "stw r11,192(r31)",
        },
        MODULE.RENDERER_DISPATCH: {
            0x82C4CCF4: "addi r4,r3,72",
            0x82C4CD00: "lwz r11,0(r4)",
            0x82C4CD50: "addi r3,r1,112",
            0x82C4CD54: "bl 0x82e61748",
            0x82C4CEDC: "lwz r24,112(r1)",
            0x82C4DAB8: "addi r26,r24,112",
            0x82C4DAC8: "lwz r11,8(r11)",
            0x82C4DAD0: "bctrl",
            0x82C4DAF0: "lwz r11,16(r11)",
            0x82C4DAF8: "bctrl",
            0x82C4DB34: "lwz r11,12(r11)",
            0x82C4DB3C: "bctrl",
            0x82C4DB54: "lwz r11,20(r11)",
            0x82C4DB5C: "bctrl",
            0x82C4DB60: "lwz r11,128(r3)",
            0x82C4DC10: "lwz r4,96(r28)",
            0x82C4DC20: "lwz r3,36(r28)",
            0x82C4DC24: "lwz r4,100(r28)",
            0x82C4DC50: "mr r3,r23",
            MODULE.DRAW_MEMBER_ENTRY_HOOK: "bl 0x82416380",
            MODULE.DRAW_MEMBER_EXIT_HOOK: "li r4,0",
        },
    }
    return functions, bytes(image)


class StaticWorldGraphTests(unittest.TestCase):
    def test_proves_resource_to_mesh_draw_graph(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertTrue(document["claims"]["mesh_to_indexed_draw_proved"])
        self.assertFalse(
            document["claims"]["concrete_building_or_prop_identity_proved"]
        )

    def test_rejects_model_embedding_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.RESOURCE_CONSTRUCTOR][0x82C47DD4] = "addi r3,r31,116"
        with self.assertRaisesRegex(ValueError, "82C47DD4"):
            MODULE.build(corrupted, image)

    def test_rejects_submodel_dispatch_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        offset = MODULE.SUBMODEL_VTABLE + 5 * 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (0x82C256EC).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "graph dispatch slot drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_draw_emitter_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.RENDERER_DISPATCH][
            MODULE.DRAW_MEMBER_ENTRY_HOOK
        ] = "bl 0x82416384"
        with self.assertRaisesRegex(ValueError, "82C4DC54"):
            MODULE.build(corrupted, image)


if __name__ == "__main__":
    unittest.main()
