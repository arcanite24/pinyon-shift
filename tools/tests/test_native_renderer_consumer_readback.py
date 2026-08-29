import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "analyze-native-renderer-consumer-readback.py"
SPEC = importlib.util.spec_from_file_location("consumer_readback", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


FAMILY = (
    "2E5E0A854BE00027/BDFFA72B7ED2FBA4/"
    "000000000000003F/000000000016003F"
)


def write_readback(root: Path, phase: str, payload: bytes, *, width=2, height=1):
    phase_root = root / phase
    phase_root.mkdir(parents=True)
    metadata = {
        "schema": MODULE.READBACK_SCHEMA,
        "consumer_family": FAMILY,
        "frame": 42,
        "draw": 7,
        "phase": phase,
        "source": {
            "width": width,
            "height": height,
            "row_pitch": len(payload) // height,
            "dxgi_format": 28,
            "bytes_per_pixel": 4,
            "bytes": len(payload),
            "hash": "0000000000000000",
        },
        "payload": {"file": "target.bin"},
        "safety": {
            "output_authority": "xenos",
            "xenos_draw_preserved": True,
            "draw_suppression": False,
            "resolve_suppression": False,
            "suppression_allowed": False,
        },
    }
    (phase_root / "readback.json").write_text(json.dumps(metadata))
    (phase_root / "target.bin").write_bytes(payload)


class ConsumerReadbackTests(unittest.TestCase):
    def test_reports_exact_draw_contribution_and_writes_pngs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            output = Path(temporary) / "report"
            write_readback(root, "before", bytes([10, 20, 30, 255, 1, 2, 3, 255]))
            write_readback(root, "after", bytes([10, 25, 30, 255, 1, 2, 3, 255]))

            report = MODULE.analyze(root, output)

            self.assertEqual(MODULE.REPORT_SCHEMA, report["schema"])
            self.assertEqual(FAMILY, report["consumer_family"])
            self.assertEqual(1, report["contribution"]["changed_pixels"])
            self.assertEqual(5, report["contribution"]["maximum_channel_delta"])
            self.assertEqual(
                {"left": 0, "top": 0, "right": 0, "bottom": 0},
                report["contribution"]["bounds"],
            )
            self.assertFalse(report["safety"]["suppression_allowed"])
            for name in ("before.png", "after.png", "difference-4x.png", "changed-mask.png"):
                self.assertTrue((output / name).read_bytes().startswith(b"\x89PNG"))

    def test_ignores_row_padding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            output = Path(temporary) / "report"
            before = bytes([10, 20, 30, 255, 90, 91, 92, 93])
            after = bytes([10, 20, 30, 255, 1, 2, 3, 4])
            write_readback(root, "before", before, width=1)
            write_readback(root, "after", after, width=1)

            report = MODULE.analyze(root, output)

            self.assertEqual(0, report["contribution"]["changed_pixels"])
            self.assertIsNone(report["contribution"]["bounds"])

    def test_decodes_half_float_color(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            for phase, red in (("before", 0.0), ("after", 1.0)):
                phase_root = root / phase
                phase_root.mkdir(parents=True)
                payload = struct.pack("<eeee", red, 0.5, 0.0, 1.0)
                metadata = {
                    "schema": MODULE.READBACK_SCHEMA,
                    "consumer_family": FAMILY,
                    "frame": 42,
                    "draw": 7,
                    "phase": phase,
                    "source": {
                        "width": 1,
                        "height": 1,
                        "row_pitch": 8,
                        "dxgi_format": 10,
                        "bytes_per_pixel": 8,
                        "bytes": 8,
                        "hash": "0000000000000000",
                    },
                    "payload": {"file": "target.bin"},
                    "safety": {
                        "output_authority": "xenos",
                        "xenos_draw_preserved": True,
                        "draw_suppression": False,
                        "resolve_suppression": False,
                        "suppression_allowed": False,
                    },
                }
                (phase_root / "readback.json").write_text(json.dumps(metadata))
                (phase_root / "target.bin").write_bytes(payload)

            report = MODULE.analyze(root, Path(temporary) / "report")

            self.assertEqual(255, report["contribution"]["maximum_channel_delta"])

    def test_rejects_unsafe_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "readback"
            payload = bytes([0, 0, 0, 255])
            write_readback(root, "before", payload, width=1)
            write_readback(root, "after", payload, width=1)
            path = root / "after" / "readback.json"
            metadata = json.loads(path.read_text())
            metadata["safety"]["draw_suppression"] = True
            path.write_text(json.dumps(metadata))

            with self.assertRaisesRegex(ValueError, "draw suppression"):
                MODULE.analyze(root, Path(temporary) / "report")


if __name__ == "__main__":
    unittest.main()
