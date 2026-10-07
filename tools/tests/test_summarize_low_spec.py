import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "summarize-low-spec.py"
SPEC = importlib.util.spec_from_file_location("summarize_low_spec", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


def write_run(logs: Path, frame_ms: list[float], draws: int = 6000) -> None:
    logs.mkdir(parents=True)
    columns = ["frame_time_us", "draw_calls", "present_count", "present_deadline_misses",
               "gpu_decoder_cpu_ns", "gpu_recorder_cpu_ns", "fh1_title_thread_cpu_time_ns",
               "memory_device_usage_mb", "memory_device_budget_mb", "fh1_surface_count",
               "fh1_surface_mb", "texture_cache_mb", "process_resident_mb"]
    with (logs / "s.perf.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, columns)
        writer.writeheader()
        # Loading frames, excluded by the settle window.
        for _ in range(MODULE.SETTLE_FRAMES):
            writer.writerow({"frame_time_us": 1000, "draw_calls": 100, "present_count": 1})
        for index, ms in enumerate(frame_ms):
            writer.writerow({
                "frame_time_us": int(ms * 1000), "draw_calls": draws, "present_count": 1,
                "gpu_decoder_cpu_ns": 2_000_000, "gpu_recorder_cpu_ns": 7_000_000,
                "fh1_title_thread_cpu_time_ns": 4_000_000,
                "memory_device_usage_mb": 1000 + index, "memory_device_budget_mb": 4000,
                "fh1_surface_count": 30, "fh1_surface_mb": 250, "texture_cache_mb": 150,
                "process_resident_mb": 2000,
            })
    (logs / "s.jsonl").write_text(
        json.dumps({"event": "graphics.device.selected", "name": "Test GPU"}) + "\n" +
        json.dumps({"event": "logging.ready", "renderer": "vulkan", "vsync": ""}) + "\n",
        encoding="utf-8")


class SummarizeLowSpecTests(unittest.TestCase):
    def test_record_measures_bands_memory_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = [16.67] * 98 + [30.0, 30.0]
            write_run(root / "run.state/logs", frames)
            (root / "run.json").write_text(json.dumps({
                "low_spec_simulation": {"kind": "sensitivity", "host_cpus": "0-7"},
                "game_arguments": ["--pinyon_shift_fh1_render_fps_limit=60",
                                   "--fh1_msaa_single_sample=true"],
            }), encoding="utf-8")
            output = root / "record.json"
            subprocess.run([sys.executable, str(SCRIPT), "record", str(root / "run.state"),
                            "--label", "4C/8T", "--run-result", str(root / "run.json"),
                            "--output", str(output)], check=True, capture_output=True)
            record = json.loads(output.read_text(encoding="utf-8"))
            heavy = record["bands"]["heavy"]
            self.assertEqual(heavy["frames"], 100)
            self.assertAlmostEqual(heavy["over_25ms_share"], 0.02)
            self.assertFalse(heavy["gate_cadence"])  # 2 % of frames over 25 ms
            self.assertAlmostEqual(heavy["recorder_cpu_ms"], 7.0)
            self.assertEqual(record["memory"]["memory_device_usage_mb_peak"], 1099)
            self.assertEqual(record["settings"]["fh1_render_fps_limit"], "60")
            self.assertEqual(record["settings"]["renderer"], "vulkan")
            self.assertNotIn("vsync", record["settings"])  # logged empty
            self.assertEqual(record["simulation"]["host_cpus"], "0-7")
            self.assertEqual(record["machine"]["gpu"], "Test GPU")

            table = subprocess.run([sys.executable, str(SCRIPT), "table", str(output)],
                                   check=True, capture_output=True, text=True).stdout
            self.assertIn("| 4C/8T (simulated) |", table)
            self.assertIn("1099 of 4000 MB", table)

    def test_steady_run_passes_the_cadence_gate(self):
        metrics = MODULE.band_metrics([
            {"frame_time_us": "16667", "draw_calls": "6000", "present_count": "1"}
            for _ in range(600)])
        self.assertTrue(metrics["gate_cadence"])
        self.assertAlmostEqual(metrics["presents_per_second"], 60.0, places=1)


if __name__ == "__main__":
    unittest.main()
