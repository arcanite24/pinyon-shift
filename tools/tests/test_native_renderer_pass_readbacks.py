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


if __name__ == "__main__":
    unittest.main()
