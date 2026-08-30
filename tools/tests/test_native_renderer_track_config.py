import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-track-config.py"
SPEC = importlib.util.spec_from_file_location("native_track_config", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def image_fixture():
    size = 0x8322322C + 8 + len(MODULE.COMMAND_LINE_TYPE) + 1 - MODULE.IMAGE_BASE
    image = bytearray(size)

    def u32(address, value):
        offset = address - MODULE.IMAGE_BASE
        image[offset : offset + 4] = value.to_bytes(4, "big")

    locator = 0x822E2FBC
    type_descriptor = 0x8322322C
    u32(MODULE.COMMAND_LINE_VTABLE - 4, locator)
    u32(locator + 12, type_descriptor)
    u32(MODULE.COMMAND_LINE_VTABLE + 16, MODULE.COMMAND_LINE_FUNCTION)
    encoded = MODULE.COMMAND_LINE_TYPE.encode() + b"\0"
    offset = type_descriptor + 8 - MODULE.IMAGE_BASE
    image[offset : offset + len(encoded)] = encoded
    for name, option in MODULE.OPTIONS.items():
        encoded = name.encode() + b"\0"
        offset = option["string"] - MODULE.IMAGE_BASE
        image[offset : offset + len(encoded)] = encoded
    return bytes(image)


def function_fixture():
    command_line = {0x824F815C: "mr r31,r3", **MODULE.PERFMODE_FANOUT}
    for option in MODULE.OPTIONS.values():
        for key in ("field_instruction", "name_instruction", "parse_instruction"):
            address, text = option[key]
            command_line[address] = text
    runtime_copy = {
        0x8259C7E8: "bl 0x82479e88",
        0x8259C7EC: "mr r30,r3",
    }
    for copy in MODULE.RUNTIME_COPIES.values():
        runtime_copy[copy["source"][0]] = copy["source"][1]
        runtime_copy[copy["destination"][0]] = copy["destination"][1]
    return {
        MODULE.COMMAND_LINE_FUNCTION: command_line,
        MODULE.RUNTIME_COPY_FUNCTION: runtime_copy,
    }


class NativeRendererTrackConfigTests(unittest.TestCase):
    def test_proves_isolated_title_track_differential(self):
        document = MODULE.build(function_fixture(), image_fixture())
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            "title_track_render_differential_control_proved",
            document["classification"],
        )
        self.assertEqual(["-fasttrackrender"], document["capture_contract"]["track_arguments"])
        self.assertEqual(
            6297,
            next(
                row["runtime_field_offset"]
                for row in document["runtime_copies"]
                if row["name"] == "fasttrackrender"
            ),
        )
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_rejects_registration_drift(self):
        functions = function_fixture()
        functions[MODULE.COMMAND_LINE_FUNCTION][0x824F9660] = "addi r4,r11,-327"
        with self.assertRaisesRegex(ValueError, "fasttrackrender name_instruction"):
            MODULE.build(functions, image_fixture())

    def test_capture_wrapper_passes_only_the_explicit_title_argument(self):
        capture = (ROOT / "tools/capture-native-renderer-census.ps1").read_text(
            encoding="utf-8"
        )
        launch = (ROOT / "tools/launch-preview.ps1").read_text(encoding="utf-8")
        self.assertIn("[ValidateSet('baseline', 'fasttrackrender')]", capture)
        self.assertIn("@('-fasttrackrender')", capture)
        self.assertIn("-GameArguments $gameArguments", capture)
        self.assertIn(
            "$env:PINYON_SHIFT_NATIVE_RENDERER_TRACK_RENDER_MODE = $TrackRenderMode",
            capture,
        )
        self.assertIn("[string[]]$GameArguments = @()", launch)
        self.assertIn("$start.ArgumentList = $GameArguments", launch)

    def test_runtime_hook_reports_title_acceptance_without_native_admission(self):
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        for address, name in (
            ("0x8259C834", "PinyonShiftObserveFastTrackRenderConfiguration"),
            ("0x8259C89C", "PinyonShiftObserveRoadDetailBlurConfiguration"),
            ("0x8259C8DC", "PinyonShiftObserveTrackCommandBufferConfiguration"),
        ):
            self.assertIn(f"address = {address}", analysis)
            self.assertIn(f'name = "{name}"', analysis)
            self.assertIn(f"void {name}", hooks)
        self.assertIn('"native_renderer.discovery.track_render_config"', hooks)
        self.assertIn('{"xenos_authority", "true"}', hooks)
        self.assertIn('{"native_draw", "false"}', hooks)
        self.assertIn('{"suppression_allowed", "false"}', hooks)


if __name__ == "__main__":
    unittest.main()
