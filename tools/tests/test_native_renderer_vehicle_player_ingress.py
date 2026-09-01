import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-vehicle-player-ingress.py"
SPEC = importlib.util.spec_from_file_location("vehicle_player_ingress", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SUMMARY_TOOL = (
    ROOT / "tools" / "summarize-native-renderer-vehicle-player-ingress.py"
)
SUMMARY_SPEC = importlib.util.spec_from_file_location(
    "vehicle_player_ingress_summary", SUMMARY_TOOL
)
assert SUMMARY_SPEC and SUMMARY_SPEC.loader
SUMMARY_MODULE = importlib.util.module_from_spec(SUMMARY_SPEC)
sys.modules[SUMMARY_SPEC.name] = SUMMARY_MODULE
SUMMARY_SPEC.loader.exec_module(SUMMARY_MODULE)


def fixture():
    functions = {
        target
        for expected in MODULE.EXPECTED_TYPES
        for target in ((expected[6],) + MODULE.COMMON_METHODS[1:])
    } | {
        MODULE.BASE_CONSTRUCTOR,
        MODULE.AI_CONSTRUCTOR,
        MODULE.PLAYER_LOCAL_CONSTRUCTOR,
        MODULE.VEHICLE_MAP_POOL_CONSTRUCTOR,
        MODULE.VEHICLE_MAP_POOL_INSTALLER,
    }
    bodies = {
        MODULE.GET_VEHICLE_ID: ["lwz r3,12(r3)", "blr"],
        MODULE.GET_TYPE_NAME: ["lwz r3,16(r3)", "blr"],
        MODULE.SET_VEHICLE_ID: ["stw r4,12(r3)", "stfs f0,8(r3)", "blr"],
        MODULE.BASE_CONSTRUCTOR: ["stw r30,16(r31)", "stw r9,0(r31)"],
        MODULE.AI_CONSTRUCTOR: [
            "addi r4,r11,-11268",
            "bl 0x82558510",
            "addi r11,r11,-11320",
            "stw r11,0(r31)",
        ],
        MODULE.PLAYER_LOCAL_CONSTRUCTOR: [
            "lis r11,-32254",
            "addi r4,r11,-11340",
            "bl 0x82558510",
            "lis r9,-32254",
            "addi r9,r9,-11392",
            "stw r9,0(r31)",
        ],
        MODULE.VEHICLE_MAP_POOL_CONSTRUCTOR: [
            "stw r4,16(r3)",
            "addi r3,r3,32",
            "bl 0x82558620",
            "addi r29,r31,144",
            "li r30,6",
            "bl 0x82558698",
        ],
        MODULE.VEHICLE_MAP_POOL_INSTALLER: [
            "li r3,1792",
            "bl 0x82c0f6c0",
            "lwz r4,4(r31)",
            "bl 0x8255b238",
            "stw r3,24(r31)",
        ],
    }
    words = {}
    strings = {}
    for name, descriptor, locator, vtable, type_address, type_name, slot_zero in MODULE.EXPECTED_TYPES:
        words[locator + 12] = descriptor
        strings[descriptor + 8] = name
        strings[type_address] = type_name
        methods = (slot_zero,) + MODULE.COMMON_METHODS[1:]
        for index, target in enumerate(methods):
            words[vtable + index * 4] = target
    return functions, bodies, words, strings


class VehiclePlayerIngressTests(unittest.TestCase):
    def test_locks_exact_player_and_traffic_semantic_types(self):
        functions, bodies, words, strings = fixture()
        with mock.patch.object(
            MODULE, "image_u32", side_effect=lambda _image, address: words[address]
        ), mock.patch.object(
            MODULE, "image_string", side_effect=lambda _image, address: strings[address]
        ):
            document = MODULE.build(functions, bodies, b"")
        self.assertEqual("complete", document["status"])
        self.assertEqual(5, document["summary"]["type_count"])
        self.assertTrue(document["summary"]["exact_player_discriminator_proved"])
        self.assertFalse(document["summary"]["player_pose_relation_proved"])
        self.assertEqual(
            "player_local",
            next(
                item["type_name"]
                for item in document["types"]
                if item["primary_vtable"] == "8201D380"
            ),
        )

    def test_rejects_vehicle_id_getter_drift(self):
        functions, bodies, words, strings = fixture()
        bodies[MODULE.GET_VEHICLE_ID] = ["lwz r3,16(r3)", "blr"]
        with mock.patch.object(
            MODULE, "image_u32", side_effect=lambda _image, address: words[address]
        ), mock.patch.object(
            MODULE, "image_string", side_effect=lambda _image, address: strings[address]
        ):
            with self.assertRaisesRegex(ValueError, "vehicle ID getter"):
                MODULE.build(functions, bodies, b"")

    def test_runtime_observer_is_passive_and_fail_closed(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        runtime = (ROOT / "src/pinyon_shift_runtime_hooks.cpp").read_text(
            encoding="utf-8"
        )
        config = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ObserveVehicleMapEntity", hooks)
        self.assertIn("vehicle_map_pose_correlation", hooks)
        self.assertIn('player_vehicle_identity_proved", "false"', hooks)
        self.assertIn("PinyonShiftObserveVehicleMapEntity", runtime)
        self.assertIn("PinyonShiftObserveVehicleMapEntityIdAssignment", runtime)
        self.assertIn("PinyonShiftObserveVehiclePlayerPool", runtime)
        self.assertIn("UINT32_MAX - kPlayerEntityOffset", runtime)
        self.assertIn("UINT32_MAX - kPoolContextOffset", runtime)
        self.assertIn("address = 0x82BBA010", config)
        self.assertIn('registers = ["r3"]', config)
        self.assertIn("address = 0x82CCF228", config)
        self.assertIn('registers = ["r3", "r4"]', config)
        self.assertIn("address = 0x826291A8", config)
        self.assertIn('registers = ["r3", "r31"]', config)

    def test_runtime_qualifier_promotes_one_direct_player_pose_relation(self):
        safety = {
            "xenos_authority": "true",
            "suppression_allowed": "false",
            "native_draw": "false",
        }
        events = [
            {
                "event": SUMMARY_MODULE.SUMMARY_EVENT,
                "status": "complete",
                "accounting_complete": "true",
                "observations": "50",
                "valid_observations": "40",
                "unrecognized_observations": "10",
                "invalid_observations": "0",
                "entities": "1",
                "overflow": "0",
                "pose_correlations": "1",
                "pose_correlation_overflow": "0",
                **safety,
            },
            {
                "event": SUMMARY_MODULE.POSE_SUMMARY_EVENT,
                "status": "complete",
            },
            {
                "event": SUMMARY_MODULE.ENTITY_EVENT,
                "entity": "40001000",
                "class": "player_local",
                "vtable": "8201D380",
                "vehicle_id": "00000003",
                "type_name_address": "8201D3B4",
                "expected_type_name_address": "8201D3B4",
                "observations": "40",
                "vtable_mismatches": "0",
                "type_name_mismatches": "0",
                "pose_comparisons": "100",
                **safety,
            },
            {
                "event": SUMMARY_MODULE.CORRELATION_EVENT,
                "entity": "40001000",
                "entity_class": "player_local",
                "relation": "entity_is_pose_owner",
                "identity_generation": "00000001",
                "identity_source": "40002000",
                "identity_owner": "40001000",
                "identity_slot": "3",
                **safety,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            report = SUMMARY_MODULE.summarize(path)
        self.assertEqual("qualified", report["status"])
        self.assertTrue(report["qualification"]["player_pose_relation_proved"])
        self.assertEqual(
            "entity_is_pose_owner",
            report["summary"]["direct_player_pose_relation"],
        )

    def test_runtime_qualifier_accepts_equivalent_exact_relations(self):
        safety = {
            "xenos_authority": "true",
            "suppression_allowed": "false",
            "native_draw": "false",
        }
        identity = {
            "identity_generation": "00000001",
            "identity_source": "40002000",
            "identity_owner": "40001000",
            "identity_slot": "3",
        }
        events = [
            {
                "event": SUMMARY_MODULE.SUMMARY_EVENT,
                "status": "complete",
                "accounting_complete": "true",
                "observations": "50",
                "valid_observations": "40",
                "unrecognized_observations": "10",
                "invalid_observations": "0",
                "entities": "1",
                "overflow": "0",
                "pose_correlations": "2",
                "pose_correlation_overflow": "0",
                **safety,
            },
            {"event": SUMMARY_MODULE.POSE_SUMMARY_EVENT, "status": "complete"},
            {
                "event": SUMMARY_MODULE.ENTITY_EVENT,
                "entity": "40001000",
                "class": "player_local",
                "vtable": "8201D380",
                "vehicle_id": "FFFFFFFF",
                "type_name_address": "8201D3B4",
                "expected_type_name_address": "8201D3B4",
                "observations": "40",
                "vtable_mismatches": "0",
                "type_name_mismatches": "0",
                "pose_comparisons": "100",
                **safety,
            },
            {
                "event": SUMMARY_MODULE.CORRELATION_EVENT,
                "entity": "40001000",
                "entity_class": "player_local",
                "relation": "entity_is_pose_owner",
                **identity,
                **safety,
            },
            {
                "event": SUMMARY_MODULE.CORRELATION_EVENT,
                "entity": "40001000",
                "entity_class": "player_local",
                "relation": "pool_manager_is_pose_owner",
                **identity,
                **safety,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )
            report = SUMMARY_MODULE.summarize(path)
        self.assertEqual("qualified", report["status"])
        self.assertEqual(
            ["entity_is_pose_owner", "pool_manager_is_pose_owner"],
            report["summary"]["direct_player_pose_relations"],
        )


if __name__ == "__main__":
    unittest.main()
