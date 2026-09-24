"""Check one complete SNR-04 batch timing against its verified draw order."""

import json
from pathlib import Path
import sys


def verify(timing_path: Path, order_path: Path):
    timing = json.loads(timing_path.read_text(encoding="utf-8"))
    order = json.loads(order_path.read_text(encoding="utf-8"))
    assert timing["schema"] == "pinyon-shift.snr04-batch-timing.v1"
    assert timing["source_frame"] == order["source_frame"]
    assert timing["draws"] == order["selected_draws"]
    assert timing["intermediate_target_readbacks"] == 0
    assert timing["target_setup_us"] > 0
    stages = timing["stages"]
    assert stages and stages[0]["first_id"] == 1
    for previous, current in zip(stages, stages[1:]):
        assert current["first_id"] == previous["first_id"] + previous["draws"]
    assert stages[-1]["first_id"] + stages[-1]["draws"] - 1 == timing["draws"]
    for stage_metric, total_metric in (("upload_bytes", "upload_bytes"),
                                       ("gpu_draw_us", "gpu_draw_us"),
                                       ("wall_us", "stage_wall_us")):
        assert sum(stage[stage_metric] for stage in stages) == timing[total_metric]
    if "queue_wait_us" in timing:
        assert sum(stage["queue_wait_us"] for stage in stages) == timing["queue_wait_us"]
        assert timing["queue_wait_us"] < timing["stage_wall_us"]
    assert all(stage["draws"] > 0 and stage["gpu_draw_us"] > 0 and
               stage["upload_cpu_us"] <= stage["wall_us"] for stage in stages)
    stage_upload_us = sum(stage["upload_cpu_us"] for stage in stages)
    assert stage_upload_us <= timing["upload_cpu_us"] <= stage_upload_us + len(stages)
    assert timing["upload_cpu_us"] < timing["stage_wall_us"]
    return {key: timing[key] for key in ("source_frame", "draws", "upload_bytes",
                                         "upload_cpu_us", "gpu_draw_us", "stage_wall_us")}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-snr04-batch-timing.py TIMING_JSON ORDER_JSON")
    print(json.dumps(verify(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True))
