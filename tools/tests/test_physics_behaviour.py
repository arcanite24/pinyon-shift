import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "physics-behaviour.py"


def trace(path: Path, player_accel: float, ai_speed: float, race_time: float | None = None) -> Path:
    """Player launches at frame 60 with a constant acceleration (m/s^2), one
    AI car holds a constant speed; samples every 6 frames at 60 Hz."""
    lines = []
    for frame in range(0, 901, 6):
        t = frame / 60
        gas = 1.0 if frame >= 60 else 0.0
        speed = max(0.0, (t - 1.0) * player_accel)
        cars = f"0:40001000:0:{speed:.3f}:3000:2:{gas:.2f}:0.00:0.00|1:40002000:1:{ai_speed:.3f}:4000:3:0.80:0.00:0.00"
        lines.append(json.dumps({"event": "fh1.physics_trace", "frame": str(frame), "t_ms": f"{1000 * t:.1f}", "mode": "3",
                                 "count": "2", "cars": cars}))
    if race_time is not None:
        lines.append(json.dumps({"event": "dlc.rally.race_trace", "started": "1", "ended": "1",
                                 "end_reason": "1", "time_72": str(race_time)}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class PhysicsBehaviourTests(unittest.TestCase):
    def run_tool(self, *args, check=True):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, check=check)

    def test_summary_times_and_distances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            run = trace(path / "a.jsonl", player_accel=5.0, ai_speed=20.0, race_time=95.5)
            self.run_tool("summary", str(run), "--output", str(path / "r.json"))
            report = json.loads((path / "r.json").read_text(encoding="utf-8"))
        player = report["player"]
        # 100 km/h = 27.78 m/s at 5 m/s^2: 5.56 s after the launch.
        self.assertAlmostEqual(player["zero_to_100_kmh_s"], 27.7778 / 5.0, places=2)
        self.assertAlmostEqual(player["zero_to_60_kmh_s"], 16.6667 / 5.0, places=2)
        self.assertEqual(player["race_seconds"], 95.5)
        ai = next(c for c in report["cars"] if c["index"] == 1)
        self.assertAlmostEqual(ai["distance_m"], 20.0 * 15.0, places=1)
        # Player: 0.5 * 5 * 14^2 = 490 m, ahead of the AI's 300 m.
        self.assertEqual(report["order"], [0, 1])

    def test_compare_flags_slower_ai_and_passes_within_tolerance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            reference = trace(path / "a.jsonl", 5.0, 20.0)
            close = trace(path / "b.jsonl", 5.05, 20.3)
            slow = trace(path / "c.jsonl", 5.0, 18.0)
            self.assertEqual(self.run_tool("compare", str(reference), str(close), check=False).returncode, 0)
            result = self.run_tool("compare", str(reference), str(slow), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("AI mean distance", result.stdout)


if __name__ == "__main__":
    unittest.main()
