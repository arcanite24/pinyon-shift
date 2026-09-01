import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-static-world-streaming.py"
SPEC = importlib.util.spec_from_file_location("static_world_streaming", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture():
    image = bytearray(
        MODULE.RESOURCE_VTABLE
        + len(MODULE.RESOURCE_VTABLE_TARGETS) * 4
        - MODULE.IMAGE_BASE
    )
    for slot, target in enumerate(MODULE.RESOURCE_VTABLE_TARGETS):
        offset = MODULE.RESOURCE_VTABLE + slot * 4 - MODULE.IMAGE_BASE
        image[offset : offset + 4] = target.to_bytes(4, "big")
    functions = {
        MODULE.RESOURCE_REFRESH: {
            0x82C4641C: "addi r5,r3,76",
            0x82C46420: "addi r3,r3,112",
            0x82C46424: "bl 0x82c462d0",
            0x82C46428: "li r3,1",
        },
        MODULE.DIRECT_RESET: {
            0x82C46450: "mr r31,r3",
            0x82C46454: "lwz r3,64(r3)",
            0x82C46460: "stw r11,64(r31)",
            0x82C4646C: "lwz r11,12(r11)",
            0x82C46474: "bctrl",
            0x82C46478: "addi r3,r31,112",
            0x82C4647C: "bl 0x82c240e0",
            MODULE.DIRECT_RESET_EXIT_HOOK: "clrlwi r11,r3,24",
        },
        MODULE.VIRTUAL_RESET: {
            0x82C222DC: "lwz r11,0(r3)",
            0x82C222E0: "mr r30,r3",
            0x82C222E4: "lwz r11,60(r11)",
            0x82C222EC: "bctrl",
            0x82C222F0: "lwz r11,64(r30)",
            0x82C222FC: "stw r10,64(r30)",
            0x82C22310: "lwz r11,12(r10)",
            0x82C22318: "bctrl",
            MODULE.VIRTUAL_RESET_EXIT_HOOK: "mr r3,r31",
        },
        MODULE.RESOURCE_DESTRUCTOR: {
            0x82C47E3C: "mr r3,r30",
            0x82C47E40: "bl 0x82e45b20",
        },
        MODULE.BASE_RESOURCE_DESTRUCTOR: {
            0x82E45BB4: "addi r3,r31,64",
            0x82E45BB8: "bl 0x82de7330",
        },
    }
    return functions, bytes(image)


class StaticWorldStreamingTests(unittest.TestCase):
    def test_proves_exact_payload_reset_paths(self):
        functions, image = fixture()
        document = MODULE.build(functions, image)
        self.assertEqual("complete", document["status"])
        self.assertEqual(64, document["resource"]["payload_reference_offset"])
        self.assertEqual(2, len(document["transitions"]))
        self.assertTrue(
            document["claims"]["payload_generation_invalidation_boundary_proved"]
        )
        self.assertTrue(
            document["claims"][
                "complete_class_vtable_invalidation_coverage_proved"
            ]
        )
        self.assertEqual(
            [16, 22],
            document["invalidation_surface"]["live_payload_reset_slots"],
        )
        self.assertFalse(
            document["claims"]["complete_streaming_invalidation_coverage_proved"]
        )

    def test_rejects_reset_slot_drift(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        offset = MODULE.RESOURCE_VTABLE + 16 * 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (MODULE.DIRECT_RESET + 4).to_bytes(
            4, "big"
        )
        with self.assertRaisesRegex(ValueError, "complete vtable drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_payload_clear_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.VIRTUAL_RESET][0x82C222FC] = "stw r10,68(r30)"
        with self.assertRaisesRegex(ValueError, "82C222FC"):
            MODULE.build(corrupted, image)

    def test_rejects_unclassified_vtable_slot(self):
        functions, image = fixture()
        corrupted = bytearray(image)
        offset = MODULE.RESOURCE_VTABLE + 19 * 4 - MODULE.IMAGE_BASE
        corrupted[offset : offset + 4] = (0x82C462C4).to_bytes(4, "big")
        with self.assertRaisesRegex(ValueError, "complete vtable drifted"):
            MODULE.build(functions, bytes(corrupted))

    def test_rejects_refresh_graph_drift(self):
        functions, image = fixture()
        corrupted = copy.deepcopy(functions)
        corrupted[MODULE.RESOURCE_REFRESH][0x82C46420] = "addi r3,r3,116"
        with self.assertRaisesRegex(ValueError, "82C46420"):
            MODULE.build(corrupted, image)


if __name__ == "__main__":
    unittest.main()
