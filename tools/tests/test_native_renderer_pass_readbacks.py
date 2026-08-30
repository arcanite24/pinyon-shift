import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "compare-native-renderer-pass-readbacks.py"
SPEC = importlib.util.spec_from_file_location("native_pass_readbacks", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_readback(root: Path, role: str, data: bytes, *, row_pitch: int = 8) -> None:
    root.mkdir()
    metadata = {
        "schema": "pinyon-shift.isolated-draw-readback.v1",
        "signature": "747837906D0BF484",
        "frame": 100,
        "draw": 42,
        "capture_role": role,
        "source": {
            "width": 1,
            "height": 1,
            "row_pitch": row_pitch,
            "dxgi_format": 10,
            "bytes": len(data),
        },
        "safety": {
            "output_authority": "xenos",
            "suppression_allowed": False,
        },
    }
    (root / "readback.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "isolated.bin").write_bytes(data)


def write_depth_readback(root: Path, role: str, data: bytes) -> None:
    root.mkdir()
    metadata = {
        "schema": "pinyon-shift.isolated-depth-readback.v1",
        "signature": "747837906D0BF484",
        "frame": 100,
        "draw": 42,
        "capture_role": role,
        "capture_content": "depth_stencil",
        "source": {
            "width": 1,
            "height": 2,
            "dxgi_format": 19,
            "sample_count": 1,
            "encoding": "d3d12_texture_planes",
            "bytes": len(data),
            "planes": [
                {
                    "index": 0,
                    "offset": 0,
                    "row_pitch": 8,
                    "row_size": 4,
                    "row_count": 2,
                },
                {
                    "index": 1,
                    "offset": 16,
                    "row_pitch": 4,
                    "row_size": 1,
                    "row_count": 2,
                },
            ],
        },
        "safety": {
            "output_authority": "xenos",
            "suppression_allowed": False,
        },
    }
    (root / "readback.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "isolated.bin").write_bytes(data)


def write_msaa_depth_readback(root: Path, role: str, data: bytes) -> None:
    root.mkdir()
    metadata = {
        "schema": "pinyon-shift.isolated-depth-readback.v1",
        "signature": "747837906D0BF484",
        "frame": 100,
        "draw": 42,
        "capture_role": role,
        "capture_content": "depth_stencil",
        "source": {
            "width": 2,
            "height": 2,
            "dxgi_format": 19,
            "sample_count": 2,
            "encoding": "depth32_stencil8_sample_tuples",
            "bytes": len(data),
            "planes": [
                {
                    "index": 0,
                    "offset": 0,
                    "row_pitch": 32,
                    "row_size": 32,
                    "row_count": 2,
                }
            ],
        },
        "safety": {
            "output_authority": "xenos",
            "suppression_allowed": False,
        },
    }
    (root / "readback.json").write_text(json.dumps(metadata), encoding="utf-8")
    (root / "isolated.bin").write_bytes(data)


class NativeRendererPassReadbackTests(unittest.TestCase):
    def test_exact_active_bytes_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass"
            xenos = Path(str(native) + ".xenos")
            write_readback(native, "native", bytes(range(8)))
            write_readback(xenos, "xenos", bytes(range(8)))
            report = MODULE.compare(native, xenos)
            self.assertEqual(report["result"], "pass")
            self.assertTrue(report["metrics"]["exact_active_bytes"])
            self.assertFalse(report["safety"]["suppression_allowed"])

    def test_padding_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass"
            xenos = Path(str(native) + ".xenos")
            write_readback(native, "native", bytes(range(8)) + b"\x00" * 8, row_pitch=16)
            write_readback(xenos, "xenos", bytes(range(8)) + b"\xFF" * 8, row_pitch=16)
            self.assertEqual(MODULE.compare(native, xenos)["result"], "pass")

    def test_active_difference_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass"
            xenos = Path(str(native) + ".xenos")
            write_readback(native, "native", bytes(range(8)))
            write_readback(xenos, "xenos", bytes([99]) + bytes(range(1, 8)))
            report = MODULE.compare(native, xenos)
            self.assertEqual(report["result"], "fail")
            self.assertEqual(report["metrics"]["different_bytes"], 1)

    def test_mismatched_frame_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass"
            xenos = Path(str(native) + ".xenos")
            write_readback(native, "native", bytes(range(8)))
            write_readback(xenos, "xenos", bytes(range(8)))
            metadata_path = xenos / "readback.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["frame"] += 1
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frame values differ"):
                MODULE.compare(native, xenos)

    def test_exact_depth_and_stencil_planes_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            data = bytes(range(21))
            write_depth_readback(native, "native", data)
            write_depth_readback(xenos, "xenos", data)
            report = MODULE.compare(native, xenos, "depth-stencil")
            self.assertEqual(report["result"], "pass")
            self.assertEqual(report["scope"]["content"], "depth-stencil")
            self.assertEqual(report["metrics"]["compared_bytes"], 10)
            components = report["metrics"]["components"]
            self.assertTrue(components["depth"]["exact_active_bytes"])
            self.assertTrue(components["stencil"]["exact_active_bytes"])

    def test_depth_padding_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            native_data = bytearray(range(21))
            xenos_data = bytearray(native_data)
            for index in (4, 5, 6, 7, 12, 13, 14, 15, 17, 18, 19):
                xenos_data[index] = 255
            write_depth_readback(native, "native", bytes(native_data))
            write_depth_readback(xenos, "xenos", bytes(xenos_data))
            report = MODULE.compare(native, xenos, "depth-stencil")
            self.assertEqual(report["result"], "pass")

    def test_stencil_difference_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            native_data = bytes(range(21))
            xenos_data = bytearray(native_data)
            xenos_data[20] ^= 0xFF
            write_depth_readback(native, "native", native_data)
            write_depth_readback(xenos, "xenos", bytes(xenos_data))
            report = MODULE.compare(native, xenos, "depth-stencil")
            self.assertEqual(report["result"], "fail")
            self.assertEqual(report["metrics"]["different_bytes"], 1)
            components = report["metrics"]["components"]
            self.assertTrue(components["depth"]["exact_active_bytes"])
            self.assertEqual(components["stencil"]["different_bytes"], 1)

    def test_exact_msaa_depth_sample_tuples_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            data = bytes(range(64))
            write_msaa_depth_readback(native, "native", data)
            write_msaa_depth_readback(xenos, "xenos", data)
            report = MODULE.compare(native, xenos, "depth-stencil")
            self.assertEqual(report["result"], "pass")
            self.assertEqual(report["metrics"]["compared_bytes"], 64)
            self.assertEqual(report["layout"]["sample_count"], 2)
            components = report["metrics"]["components"]
            self.assertTrue(components["exact_depth"])
            self.assertTrue(components["exact_stencil"])
            self.assertEqual(components["changed_samples"], 0)

    def test_msaa_depth_and_stencil_deltas_are_classified(self):
        with tempfile.TemporaryDirectory() as directory:
            native = Path(directory) / "pass.depth"
            xenos = Path(str(native) + ".xenos")
            native_data = bytes(64)
            xenos_data = bytearray(native_data)
            xenos_data[0] = 1
            xenos_data[28] = 2
            write_msaa_depth_readback(native, "native", native_data)
            write_msaa_depth_readback(xenos, "xenos", bytes(xenos_data))
            report = MODULE.compare(native, xenos, "depth-stencil")
            components = report["metrics"]["components"]
            self.assertFalse(components["exact_depth"])
            self.assertFalse(components["exact_stencil"])
            self.assertEqual(components["depth_tuple_changes"], 1)
            self.assertEqual(components["stencil_tuple_changes"], 1)
            self.assertEqual(components["depth_different_bytes"], 1)
            self.assertEqual(components["stencil_different_bytes"], 1)
            self.assertEqual(components["changed_samples"], 2)
            self.assertEqual(components["changed_sample_histogram"], [1, 1])
            self.assertEqual(
                components["changed_bounds"],
                {"left": 0, "top": 0, "right": 1, "bottom": 0},
            )
            self.assertEqual(len(components["first_changed_samples"]), 2)


if __name__ == "__main__":
    unittest.main()
