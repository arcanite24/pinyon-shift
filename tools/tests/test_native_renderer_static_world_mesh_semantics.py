import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-static-world-mesh-semantics.py"
SPEC = importlib.util.spec_from_file_location("static_world_mesh_semantics", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    table_bytes = len(MODULE.EXPECTED_SCALE_BIAS) * 8
    image = bytearray(
        MODULE.PRIMITIVE_SCALE_BIAS_TABLE + table_bytes - MODULE.IMAGE_BASE
    )
    for index, pair in enumerate(MODULE.EXPECTED_SCALE_BIAS):
        for field, value in enumerate(pair):
            offset = (
                MODULE.PRIMITIVE_SCALE_BIAS_TABLE
                + index * 8
                + field * 4
                - MODULE.IMAGE_BASE
            )
            image[offset : offset + 4] = value.to_bytes(4, "big")
    functions = {
        MODULE.PRIMITIVE_COUNT_HELPER: {
            0x82C48558: "mr r11,r3",
            0x82C48568: "cmpwi cr6,r3,1",
            0x82C48570: "cmpwi cr6,r3,2",
            0x82C48578: "cmpwi cr6,r3,3",
            0x82C48580: "cmpwi cr6,r3,4",
            0x82C48588: "li r11,3",
            0x82C4858C: "divw r3,r4,r11",
            0x82C48594: "addi r3,r4,-1",
            0x82C4859C: "srawi r11,r4,1",
            0x82C485A8: "mr r3,r4",
            0x82C485B0: "cmpwi cr6,r11,6",
            0x82C485B8: "cmpwi cr6,r11,8",
            0x82C485C0: "cmpwi cr6,r11,13",
            0x82C485D0: "srawi r11,r4,2",
            0x82C485D8: "addi r3,r4,-2",
        },
        MODULE.RENDERER_DISPATCH: {
            0x82C4DAF8: "bctrl",
            0x82C4DAFC: "lbz r11,112(r3)",
            0x82C4DB0C: "lbz r7,39(r3)",
            0x82C4DB14: "lwz r5,32(r3)",
            0x82C4DB24: "bl 0x82410a70",
            0x82C4DB3C: "bctrl",
            0x82C4DB5C: "bctrl",
            0x82C4DB60: "lwz r11,128(r3)",
            0x82C4DB6C: "addi r4,r3,128",
            0x82C4DB90: "lwz r3,168(r11)",
            0x82C4DB9C: "lwz r11,20(r11)",
            0x82C4DBB4: "bl 0x8244e728",
            0x82C4DBE4: "bl 0x8244e728",
            0x82C4DC10: "lwz r4,96(r28)",
            0x82C4DC14: "bl 0x8244d760",
            0x82C4DC20: "lwz r3,36(r28)",
            0x82C4DC24: "lwz r4,100(r28)",
            0x82C4DC28: "bl 0x82c48558",
            0x82C4DC2C: "lwz r4,36(r28)",
            0x82C4DC38: "rlwinm r10,r4,3,0,28",
            0x82C4DC40: "lwzx r9,r10,r25",
            0x82C4DC44: "lwzx r11,r10,r11",
            0x82C4DC48: "mullw r10,r9,r3",
            0x82C4DC4C: "add r7,r10,r11",
            0x82C4DC54: "bl 0x82416380",
            0x82C4DC58: "li r4,0",
            0x82C4DC60: "bl 0x8244d760",
        },
        MODULE.INDEX_BUFFER_BIND: {
            0x8244D76C: "lwz r30,12812(r3)",
            0x8244D774: "mr r29,r4",
            0x8244D7E4: "stw r29,12812(r31)",
        },
    }
    return functions, bytes(image)


class StaticWorldMeshSemanticsTests(unittest.TestCase):
    def test_proves_draw_and_material_binding_fields(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertEqual(36, document["geometry"]["primitive_type_offset"])
        self.assertEqual(96, document["geometry"]["index_buffer_binding_offset"])
        self.assertEqual(100, document["geometry"]["source_element_count_offset"])
        self.assertTrue(
            document["claims"]["index_buffer_bind_draw_clear_sequence_proved"]
        )
        self.assertTrue(
            document["claims"]["optional_material_resource_branch_proved"]
        )
        self.assertFalse(document["claims"]["native_draw_admission_proved"])

    def test_rejects_primitive_table_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        offset = MODULE.PRIMITIVE_SCALE_BIAS_TABLE - MODULE.IMAGE_BASE + 8
        corrupted[offset : offset + 4] = (2).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "scale/bias table drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_index_buffer_offset_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.RENDERER_DISPATCH][0x82C4DC10] = "lwz r4,92(r28)"
        with self.assertRaisesRegex(ValueError, "82C4DC10"):
            MODULE.build(corrupted, image)

    def test_rejects_material_reference_offset_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.RENDERER_DISPATCH][0x82C4DB60] = "lwz r11,124(r3)"
        with self.assertRaisesRegex(ValueError, "82C4DB60"):
            MODULE.build(corrupted, image)


if __name__ == "__main__":
    unittest.main()
