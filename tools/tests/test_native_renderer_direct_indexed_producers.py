import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "discover-native-renderer-direct-indexed-producers.py"
SPEC = importlib.util.spec_from_file_location("direct_indexed_producers", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    functions = {}
    for function, call, _return, _classification in MODULE.EXPECTED_CALLS:
        functions.setdefault(function, {})[call] = "bl 0x82416380"
    functions[MODULE.TRACK_HELPER].update(
        {
            0x82C5ADD8: "mr r26,r6",
            0x82C5ADE4: "mr r31,r7",
            0x82C5AE04: "lfs f0,48(r31)",
            0x82C5AE68: "lfs f0,16(r31)",
            0x82C5AE98: "lfs f0,0(r31)",
            0x82C5B014: "lwz r4,96(r26)",
            0x82C5B024: "lwz r7,100(r26)",
            0x82C5B02C: "lwz r4,36(r26)",
        }
    )
    functions[0x82DED198] = {
        0x82DEDA2C: "addi r8,r1,688",
        0x82DEDA30: "addi r7,r1,240",
        0x82DEDA34: "mr r6,r29",
        0x82DEDA44: "bl 0x82c5adc0",
    }
    functions[0x82436468] = {
        0x82436500: "mr r7,r25",
        0x82436504: "mr r6,r27",
        0x82436514: "bl 0x82ded198",
    }
    presentation_dispatch = (0x8240E7B0, 0x82439B70, 0x82DEEEE0, 0x82DEF2B0)
    for target in presentation_dispatch:
        functions[target] = {target: "bl 0x82436468"}

    image = bytearray(0x310000)

    def put_u32(address, value):
        offset = address - MODULE.IMAGE_BASE
        image[offset : offset + 4] = value.to_bytes(4, "big")

    def put_rtti(vtable, locator, descriptor, name):
        put_u32(vtable - 4, locator)
        put_u32(locator, 0)
        put_u32(locator + 12, descriptor)
        encoded = name.encode("ascii") + b"\0"
        offset = descriptor + 8 - MODULE.IMAGE_BASE
        image[offset : offset + len(encoded)] = encoded

    put_rtti(
        MODULE.TRACK_MESH_VTABLE,
        0x82300000,
        0x82300100,
        ".?AVCTrackMesh@@",
    )
    put_rtti(
        MODULE.TRACK_PRESENTATION_VTABLE,
        0x82300200,
        0x82300300,
        ".?AVCTrackPresentation@Presentation_Unified@@",
    )
    for slot, target in zip((79, 75, 78, 80), presentation_dispatch):
        put_u32(MODULE.TRACK_PRESENTATION_VTABLE + slot * 4, target)
    return functions, bytes(image)


class DirectIndexedProducerTests(unittest.TestCase):
    def test_proves_inventory_and_track_mesh_candidate(self):
        functions, image = fixture()
        report = MODULE.build(functions, image)
        self.assertEqual("complete", report["status"])
        self.assertEqual(13, len(report["producers"]))
        candidate = report["c2_live_candidate"]
        self.assertEqual("82C5ADC0", candidate["producer"])
        self.assertEqual("CTrackMesh", candidate["mesh_class"])
        self.assertEqual(16, candidate["transform_words"])
        self.assertFalse(report["claims"]["runtime_activity_proved"])
        self.assertFalse(report["claims"]["building_or_prop_identity_proved"])

    def test_rejects_a_missing_draw_producer(self):
        functions, image = fixture()
        del functions[0x8240EE98][0x8240F01C]
        with self.assertRaisesRegex(ValueError, "inventory drifted"):
            MODULE.build(functions, image)

    def test_rejects_track_transform_drift(self):
        functions, image = fixture()
        functions[MODULE.TRACK_HELPER][0x82C5ADE4] = "mr r30,r7"
        with self.assertRaisesRegex(ValueError, "instruction drift"):
            MODULE.build(functions, image)

    def test_runtime_hook_is_bounded_and_passive(self):
        analysis = (
            ROOT / "config" / "rexglue" / "analysis" / "main-xex.toml"
        ).read_text(encoding="utf-8")
        hooks = (ROOT / "src" / "native_renderer" / "graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("address = 0x82416380", analysis)
        self.assertIn(
            'name = "PinyonShiftObserveDirectIndexedDrawProducer"', analysis
        )
        self.assertIn('registers = ["r26", "r31", "lr"]', analysis)
        self.assertIn("kDirectIndexedDrawProducerCount = 13", hooks)
        self.assertIn("kUnifiedTrackMeshTransformCapacity = 4096", hooks)
        self.assertIn("bounded_64_byte_live_transform", hooks)
        self.assertIn('{"guest_state_changed", "false"}', hooks)
        self.assertIn('{"native_admission", "false"}', hooks)
        self.assertIn('{"xenos_authority", "true"}', hooks)


if __name__ == "__main__":
    unittest.main()
