import csv
import importlib.util
import math
import pathlib
import random
import statistics
import subprocess
import sys
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "summarize-inrun-ab.py"
SPEC = importlib.util.spec_from_file_location("summarize_inrun_ab", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def window_list(values):
    return [{"side": index % 2, "m": value} for index, value in enumerate(values)]


class BlockEstimatorTests(unittest.TestCase):
    def test_linear_drift_cancels_inside_blocks(self):
        # Side 1 costs 2 more; every window drifts up by 0.5.
        values = [index * 0.5 + 2 * (index % 2) for index in range(9)]
        blocks = MODULE.block_differences(window_list(values), ["m"])
        self.assertEqual(len(blocks), 3)
        for block in blocks:
            self.assertAlmostEqual(block["m"], 2.0)

    def test_blocks_share_no_window_and_skip_broken_alternation(self):
        means = [{"side": side, "m": 0.0} for side in (0, 1, 0, 0, 1, 0, 1)]
        blocks = MODULE.block_differences(means, ["m"])
        # 0 1 0 | 0 1 0 | 1 left over.
        self.assertEqual(len(blocks), 2)

    def test_standard_error_matches_the_spread_of_the_estimate(self):
        # Independent window noise, a known effect and a slow drift: the
        # reported standard error should match the actual spread of the
        # estimate over many simulated runs (the old overlapping-pair
        # estimator reported about 1/1.4 of it).
        generator = random.Random(747)
        estimates, errors = [], []
        for _ in range(3000):
            drift = generator.uniform(-0.2, 0.2)
            values = [index * drift + 1.0 * (index % 2) + generator.gauss(0, 1)
                      for index in range(15)]
            means = window_list(values)
            blocks = MODULE.block_differences(means, ["m"])
            summary = MODULE.summarize(means, blocks, ["m"])["m"]
            estimates.append(summary["difference"])
            errors.append(summary["standard_error"])
        self.assertAlmostEqual(statistics.fmean(estimates), 1.0, delta=0.05)
        actual = statistics.stdev(estimates)
        reported = math.sqrt(statistics.fmean(error * error for error in errors))
        self.assertLess(abs(reported / actual - 1), 0.1)


class CaptureTests(unittest.TestCase):
    def run_script(self, rows, *arguments):
        with tempfile.TemporaryDirectory() as directory:
            capture = pathlib.Path(directory) / "run.perf.csv"
            with capture.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            return subprocess.run([sys.executable, str(SCRIPT), str(capture), "--settle", "0",
                                   "--min-frames", "1", *arguments],
                                  capture_output=True, text=True, encoding="utf-8")

    def rows(self):
        return [{"aa_toggle": str(side), "frame_time_us": str(16000 + 2000 * side)}
                for side in (0, 1, 0, 1, 0, 1) for _ in range(3)]

    def test_reports_the_effect(self):
        result = self.run_script(self.rows())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"difference": 2.0', result.stdout)

    def test_cut_off_last_row_is_counted_not_read(self):
        rows = self.rows() + [{"aa_toggle": "", "frame_time_us": ""}]
        result = self.run_script(rows)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"incomplete_rows": 1', result.stdout)

    def test_non_numeric_value_fails(self):
        rows = self.rows()
        rows[4]["frame_time_us"] = "n/a"
        result = self.run_script(rows)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frame_time_us", result.stderr)

    def test_missing_requested_metric_fails(self):
        result = self.run_script(self.rows(), "--metrics", "frame_time_us", "process_cpu_ns")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("process_cpu_ns", result.stderr)


if __name__ == "__main__":
    unittest.main()
