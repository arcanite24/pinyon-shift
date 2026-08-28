import importlib.util
import contextlib
import io
import sys
import tempfile
import unittest
import struct
import zlib
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "compare-native-renderer-images.py"
SPEC = importlib.util.spec_from_file_location("native_visual_compare", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_ppm(path: Path, width: int, height: int, pixels: bytes) -> None:
    path.write_bytes(f"P6\n# fixture\n{width} {height}\n255\n".encode() + pixels)


def write_png(path: Path, width: int, height: int, channels: int, pixels: bytes) -> None:
    color_type = {1: 0, 3: 2, 4: 6}[channels]

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(
        b"\0" + pixels[row * width * channels : (row + 1) * width * channels]
        for row in range(height)
    )
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


class NativeRendererVisualCompareTests(unittest.TestCase):
    def test_exact_images_pass_all_checks(self):
        image = MODULE.PpmImage(2, 2, bytes([0, 0, 0, 20, 30, 40] * 2))
        metrics = MODULE.compare_images(
            image, image, channel_tolerance=0, coverage_threshold=1
        )
        self.assertEqual(metrics["mean_absolute_error"], 0)
        self.assertEqual(metrics["different_pixel_ratio"], 0)
        self.assertEqual(metrics["coverage_iou"], 1)

    def test_channel_and_coverage_differences_are_independent(self):
        native = MODULE.PpmImage(2, 1, bytes([8, 8, 8, 0, 0, 0]))
        reference = MODULE.PpmImage(2, 1, bytes([10, 10, 10, 9, 0, 0]))
        metrics = MODULE.compare_images(
            native, reference, channel_tolerance=2, coverage_threshold=1
        )
        self.assertEqual(metrics["different_pixels"], 1)
        self.assertEqual(metrics["different_pixel_ratio"], 0.5)
        self.assertEqual(metrics["coverage_iou"], 0.5)

    def test_dimension_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "dimensions differ"):
            MODULE.compare_images(
                MODULE.PpmImage(1, 1, b"\0\0\0"),
                MODULE.PpmImage(2, 1, b"\0" * 6),
                channel_tolerance=0,
                coverage_threshold=0,
            )

    def test_difference_image_amplifies_channel_error(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "difference.ppm"
            MODULE.write_difference_ppm(
                output,
                MODULE.PpmImage(1, 1, bytes([10, 20, 30])),
                MODULE.PpmImage(1, 1, bytes([12, 18, 40])),
                4,
            )
            self.assertEqual(MODULE.read_ppm(output).pixels, bytes([8, 8, 40]))

    def test_report_exit_code_distinguishes_pass_and_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / "native.ppm"
            reference = root / "reference.ppm"
            output = root / "report.json"
            write_ppm(native, 1, 1, bytes([1, 2, 3]))
            write_ppm(reference, 1, 1, bytes([1, 2, 3]))
            self.assertEqual(
                MODULE.main([str(native), str(reference), "--output", str(output)]),
                0,
            )
            write_ppm(reference, 1, 1, bytes([255, 255, 255]))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(MODULE.main([str(native), str(reference)]), 2)

    def test_rgba_png_comparison_includes_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / "native.png"
            reference = root / "reference.png"
            write_png(native, 1, 1, 4, bytes([10, 20, 30, 40]))
            write_png(reference, 1, 1, 4, bytes([10, 20, 30, 50]))
            left = MODULE.read_image(native)
            right = MODULE.read_image(reference)
            self.assertEqual(left.channels, 4)
            metrics = MODULE.compare_images(
                left, right, channel_tolerance=0, coverage_threshold=1
            )
            self.assertEqual(metrics["maximum_channel_error"], 10)
            self.assertEqual(metrics["different_pixels"], 1)

    def test_depth_png_report_declares_depth_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / "native-depth.png"
            reference = root / "reference-depth.png"
            write_png(native, 1, 1, 1, bytes([128]))
            write_png(reference, 1, 1, 1, bytes([128]))
            args = MODULE.parse_args(
                [str(native), str(reference), "--content", "depth"]
            )
            report = MODULE.build_report(args)
            self.assertTrue(report["scope"]["depth"])
            self.assertFalse(report["scope"]["output_color"])

    def test_crop_selects_identical_region_and_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / "native.ppm"
            reference = root / "reference.ppm"
            write_ppm(native, 2, 1, bytes([255, 0, 0, 1, 2, 3]))
            write_ppm(reference, 2, 1, bytes([0, 255, 0, 1, 2, 3]))
            args = MODULE.parse_args(
                [str(native), str(reference), "--crop", "1,0,1,1"]
            )
            report = MODULE.build_report(args)
            self.assertEqual(report["result"], "pass")
            self.assertEqual(
                report["inputs"]["crop"],
                {"left": 1, "top": 0, "width": 1, "height": 1},
            )

    def test_draw_delta_ignores_unchanged_background(self):
        native_before = MODULE.PpmImage(2, 1, bytes([0, 0, 0, 0, 0, 0]))
        native_after = MODULE.PpmImage(2, 1, bytes([10, 20, 30, 0, 0, 0]))
        reference_before = MODULE.PpmImage(
            2, 1, bytes([100, 100, 100, 200, 200, 200])
        )
        reference_after = MODULE.PpmImage(
            2, 1, bytes([10, 20, 30, 200, 200, 200])
        )
        metrics = MODULE.compare_images(
            native_after,
            reference_after,
            channel_tolerance=0,
            coverage_threshold=0,
            native_before=native_before,
            reference_before=reference_before,
        )
        self.assertEqual(metrics["compared_pixels"], 1)
        self.assertEqual(metrics["coverage_iou"], 1)
        self.assertEqual(metrics["mean_absolute_error"], 0)


if __name__ == "__main__":
    unittest.main()
