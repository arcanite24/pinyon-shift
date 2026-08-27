import csv
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-performance.py"
SPEC = importlib.util.spec_from_file_location("summarize_performance", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


FIELDS = [
    "frame_time_us", "fps", "draw_calls", "command_buffer_stalls",
    "texture_cache_hits", "texture_cache_misses", "pipeline_cache_hits",
    "pipeline_cache_misses",
]


class PerformanceSummaryTests(unittest.TestCase):
    def test_emits_complete_optional_xma_stall_totals(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = pathlib.Path(temporary) / "capture.csv"
            capture.write_text(
                "frame_time_us,fps,draw_calls,command_buffer_stalls,texture_cache_hits,texture_cache_misses,"
                "pipeline_cache_hits,pipeline_cache_misses,xma_no_space_stalls,"
                "xma_no_progress_stalls,xma_stall_recoveries\n"
                "10000,100,1,0,1,0,1,0,2,1,0\n"
                "11000,90,1,0,1,0,1,0,3,0,1\n",
                encoding="utf-8",
            )
            result = MODULE.summarize(capture)
            self.assertEqual(5, result["xma_stall_counters"]["xma_no_space_stalls"])
            self.assertEqual(1, result["xma_stall_counters"]["xma_no_progress_stalls"])
            self.assertEqual(1, result["xma_stall_counters"]["xma_stall_recoveries"])

    def test_emits_complete_optional_memexport_totals(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = pathlib.Path(temporary) / "capture.csv"
            capture.write_text(
                "frame_time_us,fps,draw_calls,command_buffer_stalls,texture_cache_hits,texture_cache_misses,"
                "pipeline_cache_hits,pipeline_cache_misses,memexport_draws,memexport_bytes,"
                "memexport_sync_fallbacks,memexport_queue_waits,memexport_fence_waits\n"
                "10000,100,1,0,1,0,1,0,2,64,1,1,1\n"
                "11000,90,1,0,1,0,1,0,3,96,0,0,0\n",
                encoding="utf-8",
            )
            result = MODULE.summarize(capture)
            self.assertEqual(5, result["memexport_counters"]["memexport_draws"])
            self.assertEqual(160, result["memexport_counters"]["memexport_bytes"])

    def write_capture(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_summarizes_runtime_csv_and_ignores_initialization_row(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = pathlib.Path(temporary) / "frames.csv"
            self.write_capture(capture, [
                dict.fromkeys(FIELDS, 0),
                {"frame_time_us": 10_000, "fps": 100, "draw_calls": 10,
                 "command_buffer_stalls": 1, "texture_cache_hits": 9,
                 "texture_cache_misses": 1, "pipeline_cache_hits": 20,
                 "pipeline_cache_misses": 0},
                {"frame_time_us": 20_000, "fps": 50, "draw_calls": 20,
                 "command_buffer_stalls": 2, "texture_cache_hits": 8,
                 "texture_cache_misses": 2, "pipeline_cache_hits": 18,
                 "pipeline_cache_misses": 2},
            ])
            result = MODULE.summarize(capture)
            self.assertEqual(result["frames"]["sample_count"], 2)
            self.assertEqual(result["frames"]["measured_duration_seconds"], 0.03)
            self.assertEqual(result["frames"]["frame_time_us"]["median"], 15_000)
            self.assertEqual(result["frames"]["counter_totals"]["draw_calls"], 30)
            self.assertEqual(result["frames"]["cache_hit_rate_percent"]["texture"], 85.0)

    def test_rejects_incomplete_and_truncated_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture = pathlib.Path(temporary) / "frames.csv"
            capture.write_text("frame_time_us,fps\n10000,100\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(TOOL), str(capture)], capture_output=True, text=True
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("missing required columns", completed.stderr)

    def test_compares_with_baseline_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            baseline_csv = root / "baseline.csv"
            candidate_csv = root / "candidate.csv"
            row = {"fps": 0, "draw_calls": 1, "command_buffer_stalls": 0,
                   "texture_cache_hits": 1, "texture_cache_misses": 0,
                   "pipeline_cache_hits": 1, "pipeline_cache_misses": 0}
            self.write_capture(baseline_csv, [row | {"frame_time_us": 20_000}, row | {"frame_time_us": 20_000}])
            self.write_capture(candidate_csv, [row | {"frame_time_us": 10_000}, row | {"frame_time_us": 10_000}])
            baseline = root / "baseline.json"
            baseline.write_text(json.dumps(MODULE.summarize(baseline_csv)), encoding="utf-8")
            result = MODULE.summarize(candidate_csv)
            MODULE.add_comparison(result, json.loads(baseline.read_text(encoding="utf-8")))
            metric = result["comparison"]["metrics"]["median_frame_time_us"]
            self.assertEqual(metric["delta_percent"], -50.0)


if __name__ == "__main__":
    unittest.main()
