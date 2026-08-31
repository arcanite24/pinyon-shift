import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-vehicle-asset-material.py"
SPEC = importlib.util.spec_from_file_location("vehicle_asset_material", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def store_u32(image, address, value):
    offset = address - MODULE.IMAGE_BASE
    image[offset : offset + 4] = value.to_bytes(4, "big")


def store_string(image, address, value):
    offset = address - MODULE.IMAGE_BASE
    encoded = value.encode("ascii") + b"\0"
    image[offset : offset + len(encoded)] = encoded


def fixture():
    image = bytearray(0x01400000)
    functions = {
        MODULE.PATH_BUILDER,
        MODULE.BINDING_FUNCTION,
        MODULE.CAR_RESOURCE_CONSTRUCTOR,
        0x82450F48,
    }
    for address, value in MODULE.EXPECTED_STRINGS:
        store_string(image, address, value)
    for name, descriptor, locator, vtable, slot_count in MODULE.EXPECTED_TYPES:
        store_string(image, descriptor + 8, name)
        store_u32(image, locator + 12, descriptor)
        for index in range(slot_count):
            store_u32(image, vtable + index * 4, 0x82450F48)
    bodies = {
        MODULE.PATH_BUILDER: [
            "mr r29,r3",
            "mr r31,r4",
            "mr r30,r5",
            "addi r5,r11,-23796",
            "addi r5,r11,-23852",
            "addi r5,r11,-23872",
            "addi r5,r31,1712",
            "addi r31,r11,-23880",
            "addi r5,r11,-23896",
            "addi r5,r11,-23904",
            "addi r4,r1,80",
            "bl 0x82450f48",
            "mr r3,r29",
        ],
        MODULE.BINDING_FUNCTION: [
            "mr r31,r4",
            "mr r30,r5",
            "mr r4,r3",
            "mr r5,r6",
            "bl 0x82543558",
            "mr r3,r31",
            "bl 0x82480fc0",
            "mr r3,r31",
            "bl 0x825434a0",
        ],
        MODULE.CAR_RESOURCE_CONSTRUCTOR: [
            "addi r4,r31,1056",
            "mr r3,r31",
            "bl 0x82549670",
            "addi r29,r31,1056",
            "mr r4,r29",
            "mr r3,r31",
            "bl 0x82549670",
        ],
    }
    return functions, bodies, bytes(image)


class VehicleAssetMaterialTests(unittest.TestCase):
    def test_locks_title_owned_binding(self):
        report = MODULE.build(*fixture())
        self.assertEqual("complete", report["status"])
        self.assertTrue(
            report["summary"][
                "title_owned_asset_material_discriminator_proved"
            ]
        )
        self.assertEqual(
            "tire_wheel_shader_settings",
            report["contracts"]["title_semantic"],
        )
        self.assertFalse(
            report["summary"]["semantic_mesh_material_roles_proved"]
        )

    def test_rejects_owner_offset_drift(self):
        functions, bodies, image = fixture()
        bodies[MODULE.CAR_RESOURCE_CONSTRUCTOR][0] = "addi r4,r31,1052"
        with self.assertRaisesRegex(ValueError, "owner relation"):
            MODULE.build(functions, bodies, image)

    def test_runtime_hook_is_passive_and_exact(self):
        config = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("address = 0x82549670", config)
        self.assertIn("PinyonShiftObserveVehicleMaterialBinding", config)
        self.assertIn("kVehicleMaterialBindingObjectOffset = 1056", source)
        self.assertIn("kVehicleMaterialAssetKeyOffset = 1712", source)
        self.assertIn("guest_payload_exported", source)
        self.assertIn('{"xenos_authority", "true"}', source)
        self.assertIn('{"suppression_allowed", "false"}', source)


if __name__ == "__main__":
    unittest.main()
