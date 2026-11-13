import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "subsystem-cpu.py"

GROUPS = """
[[group]]
name = "physics"
base = ["82D4E2E0"]
v4 = ["82E10560"]

[[group]]
name = "audio logic"
base = ["82BAF5C8"]
v4 = []

[[group]]
name = "scene"
base = ["825A6208"]
v4 = []
"""


class SubsystemCpuTests(unittest.TestCase):
    def run_tool(self, *args):
        result = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, check=True)
        return result.stdout

    def test_folded_profile_splits_by_first_matching_group(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "groups.toml").write_text(GROUPS, encoding="utf-8")
            (path / "p.folded").write_text(
                "Guest 8255AE10 -1/2;__start;sub_823ED888;sub_82D4E2E0;sub_82D2F348 300\n"
                "Guest 8255AE10 -1/2;__start;sub_823ED888;sub_823E40D8 100\n"
                # v4 root on a worker thread
                "Guest 82CCC368 -1/3;__start;sub_82E10560;sub_82DE3D10 200\n"
                "Guest 825A6320 -1/4;__start;sub_825A6208;sub_8259F3E8 400\n"
                # matched by the thread's start address alone
                "Guest 82BAF5C8 -1/6;__start;sub_82BAD518 110\n"
                "GPU Commands -1/5;__start;rex::Decode 999\n",
                encoding="utf-8")
            self.run_tool(str(path / "p.folded"), "--groups", str(path / "groups.toml"),
                          "--seconds", "1", "--output", str(path / "r.json"))
            report = json.loads((path / "r.json").read_text(encoding="utf-8"))
        shares = {g["name"]: round(g["share"]) for g in report["groups"]}
        self.assertEqual(shares, {"physics": 45, "scene": 36, "audio logic": 10, "other: Guest 8255AE10": 9})

    def test_sampler_drops_waits_and_sleeping_threads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "groups.toml").write_text(GROUPS, encoding="utf-8")
            (path / "threads.csv").write_text(
                "thread,name\n1,Guest 8255AE10 (F8000058)\n2,Guest 82E4B2D0 (F8001148)\n", encoding="utf-8")
            (path / "stacks.csv").write_text(
                "stack_id,stack\n"
                '0,"x!__imp__sub_823ED888;x!__imp__sub_82D4E2E0"\n'
                '1,"x!__imp__sub_823ED888;ntdll!NtWaitForSingleObject"\n'
                '2,"x!__imp__sub_82E4B2D0;x!__imp__sub_82A6DD50"\n', encoding="utf-8")
            rows = ["t_ms,thread,cycles,stack_id"]
            for i in range(10):
                t = 10.0 * i
                rows.append(f"{t},1,40000000,{0 if i % 2 else 1}")
                rows.append(f"{t + 1},2,100,2")
            (path / "samples.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
            self.run_tool(str(path), "--groups", str(path / "groups.toml"), "--output", str(path / "r.json"))
            report = json.loads((path / "r.json").read_text(encoding="utf-8"))
        self.assertEqual([g["name"] for g in report["groups"]], ["physics"])
        self.assertEqual(report["left_out_sleeping_threads"], ["Guest 82E4B2D0 (F8001148)"])


if __name__ == "__main__":
    unittest.main()
