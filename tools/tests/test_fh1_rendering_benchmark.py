import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys


SPEC = importlib.util.spec_from_file_location(
    "rendering_benchmark", Path(__file__).resolve().parents[1] / "benchmark-fh1-renderings.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RenderingBenchmarkTests(unittest.TestCase):
    def test_output_cannot_write_into_the_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            seed = Path(directory)
            output = seed / "evidence"
            result = subprocess.run([
                sys.executable, str(SPEC.origin), str(seed / "frame.fh1frame"),
                "--state-root", str(seed), "--output", str(output),
                "--build-directory", str(seed / "build"), "--renderings=0/2/1x/c3",
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("output must be outside the read-only seed", result.stderr)
            self.assertFalse(output.exists())

    def test_missing_and_dropped_timestamps_cannot_look_like_a_speedup(self):
        fields = ["guest_frame_gpu_timing_samples", "native_gpu_timing_drops",
                  "guest_frame_gpu_time_ns", "frame_time_us", "gpu_decoded_draws"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "perf.csv"
            with path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(fields)
                writer.writerows([
                    [1, 0, 99000000, 99000, 100],  # warm-up
                    [0, 0, 0, 1000, 100],
                    [1, 1, 100, 1000, 100],
                    [1, 0, 2000000, 3000, 100],
                    [1, 0, 4000000, 5000, 100],
                    [1, 0, 100, 1000],  # a torn last row must not enter the result
                ])
            result = MODULE.timings(path, warmup=1, minimum=2)
            self.assertEqual(result, {"samples": 2, "excluded": 3, "gpu_median_ms": 3,
                                      "frame_median_ms": 4, "decoded_draws_median": 100})
            with self.assertRaisesRegex(ValueError, "only 2 valid gpu samples"):
                MODULE.timings(path, warmup=1, minimum=3)
            # A deliberate latency measurement must not invent a GPU median.
            latency = MODULE.timings(path, warmup=1, minimum=3, metric="frame")
            self.assertIsNone(latency["gpu_median_ms"])
            self.assertEqual(latency["samples"], 4)


if __name__ == "__main__":
    unittest.main()
