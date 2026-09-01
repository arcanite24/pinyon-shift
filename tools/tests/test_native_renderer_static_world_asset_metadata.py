import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = (
    ROOT
    / "tools"
    / "discover-native-renderer-static-world-asset-metadata.py"
)
SPEC = importlib.util.spec_from_file_location("static_world_asset_metadata", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    highest = max(
        MODULE.EFFECT_SUFFIX_ADDRESS + 4,
        MODULE.TEXTURE_FORMAT_ADDRESS + 18,
        MODULE.TEXTURE_ID_MARKER_ADDRESS + 4,
    )
    image = bytearray(highest - MODULE.IMAGE_BASE)
    for address, value in (
        (MODULE.EFFECT_SUFFIX_ADDRESS, b".fx\0"),
        (MODULE.TEXTURE_FORMAT_ADDRESS, b"%s%stextures\\%s\0"),
        (MODULE.TEXTURE_ID_MARKER_ADDRESS, b"Id=\0"),
    ):
        offset = address - MODULE.IMAGE_BASE
        image[offset : offset + len(value)] = value
    functions = {
        MODULE.PRESENTATION_INITIALIZE: {
            0x82DEA2B0: "addi r30,r31,16",
            0x82DEA2B4: "mr r4,r29",
            0x82DEA2B8: "mr r3,r30",
            0x82DEA2BC: "bl 0x82d8e3f0",
            0x82DEA364: "stw r11,152(r31)",
            0x82DEA368: "lwz r11,20(r30)",
            0x82DEA374: "lwz r4,0(r30)",
            0x82DEA37C: "mr r4,r30",
            0x82DEA380: "lis r5,6",
            0x82DEA384: "addi r3,r31,148",
            0x82DEA388: "bl 0x82c48038",
        },
        MODULE.PRESENTATION_PREPARE: {
            0x823F89A4: "lwz r11,148(r24)",
            0x823F89F8: "mr r4,r31",
            0x823F89FC: "addi r3,r1,112",
            0x823F8A00: "bl 0x82e61748",
            0x823F8A04: "lwz r26,112(r1)",
            0x823F8A08: "lhz r11,128(r26)",
            0x823F8A8C: "addi r27,r24,1568",
            0x823F8A94: "lhz r29,128(r26)",
            0x823F8AAC: "lis r11,-32220",
            0x823F8AB4: "addi r25,r11,13100",
            0x823F8ABC: "lwz r10,124(r26)",
            0x823F8AC0: "mulli r11,r11,28",
            0x823F8AC8: "lwz r10,20(r11)",
            0x823F8ACC: "cmplwi cr6,r10,16",
            0x823F8AD4: "lwz r11,0(r11)",
            0x823F8B30: "bl 0x82a7f710",
            0x823F8B38: "bne 0x823f8b40",
            0x823F8B3C: "stb r23,0(r31)",
            0x823F8B48: "addi r4,r1,128",
            0x823F8B50: "bl 0x82c39b78",
            0x823F8B64: "addi r26,r26,288",
            0x823F8B74: "lwz r10,4(r26)",
            0x823F8B78: "lwz r9,0(r26)",
            0x823F8B80: "divw r31,r10,r11",
            0x823F8B94: "lis r10,-32220",
            0x823F8B98: "lis r11,-32255",
            0x823F8BA4: "addi r28,r10,13084",
            0x823F8BA8: "addi r27,r11,-16120",
            0x823F8BAC: "lwz r11,0(r26)",
            0x823F8BB4: "lwz r11,20(r3)",
            0x823F8BB8: "cmplwi cr6,r11,16",
            0x823F8BC0: "lwz r3,0(r3)",
            0x823F8BE8: "addi r3,r1,1168",
            0x823F8BEC: "bl 0x830f6520",
            0x823F8BF4: "addi r7,r1,1168",
            0x823F8C04: "bl 0x8247cf40",
            0x823F8C3C: "bl 0x82c39730",
        },
    }
    return functions, bytes(image)


class StaticWorldAssetMetadataTests(unittest.TestCase):
    def test_proves_bounded_resource_and_material_reference_metadata(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertEqual(16, document["resource_key"]["stored_name_offset"])
        self.assertEqual(124, document["effect_references"]["records_pointer_offset"])
        self.assertEqual(288, document["texture_references"]["records_vector_offset"])
        self.assertTrue(
            document["claims"]["presentation_name_to_resource_key_proved"]
        )
        self.assertFalse(
            document["claims"]["concrete_building_or_prop_category_proved"]
        )
        self.assertFalse(document["next_boundary"]["plaintext_asset_names_allowed"])

    def test_rejects_resource_key_offset_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.PRESENTATION_INITIALIZE][0x82DEA2B0] = (
            "addi r30,r31,20"
        )
        with self.assertRaisesRegex(ValueError, "82DEA2B0"):
            MODULE.build(corrupted, image)

    def test_rejects_effect_record_stride_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.PRESENTATION_PREPARE][0x823F8AC0] = (
            "mulli r11,r11,32"
        )
        with self.assertRaisesRegex(ValueError, "823F8AC0"):
            MODULE.build(corrupted, image)

    def test_rejects_texture_path_format_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        offset = MODULE.TEXTURE_FORMAT_ADDRESS - MODULE.IMAGE_BASE
        corrupted[offset : offset + 2] = b"%d"
        with self.assertRaisesRegex(ValueError, "metadata string drift"):
            MODULE.build(functions, bytes(corrupted))


if __name__ == "__main__":
    unittest.main()
