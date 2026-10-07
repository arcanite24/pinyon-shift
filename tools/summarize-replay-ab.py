#!/usr/bin/env python3
"""Compare the replay-on and replay-off frames of an in-run A/B capture.

Frames are classed by the perf capture's own replay columns: frames that
replayed draws are "on", frames that neither replayed nor recorded for a
replay are "off", and frames that only recorded (the first after switching
on) are reported apart. Within each draw band the medians of frame time,
recorder, decoder and title CPU, and the recorder's CPU a draw, are compared
(RECORDER_REPLAY_BACKLOG RR-0.4).

    summarize-replay-ab.py RUN.state [--band heavy] [--json out.json]
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

BANDS = {"heavy": (5000, 10**9), "gameplay": (2000, 5000), "all": (2000, 10**9)}
SETTLE_FRAMES = 120


def number(row: dict, column: str) -> float:
    try:
        return float(row.get(column) or 0)
    except ValueError:
        return 0.0


def summarize(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    def median(column: str, scale: float = 1e6) -> float:
        return round(statistics.median(number(row, column) for row in rows) / scale, 3)
    recorder_per_draw = [number(row, "gpu_recorder_cpu_ns") / max(number(row, "draw_calls"), 1)
                         for row in rows]
    return {
        "frames": len(rows),
        "draws_median": statistics.median(number(row, "draw_calls") for row in rows),
        "frame_ms": median("frame_time_us", 1e3),
        "recorder_cpu_ms": median("gpu_recorder_cpu_ns"),
        "recorder_busy_ms": median("gpu_recorder_busy_ns"),
        "recorder_ns_a_draw": round(statistics.median(recorder_per_draw), 1),
        "decoder_cpu_ms": median("gpu_decoder_cpu_ns"),
        "title_cpu_ms": median("fh1_title_thread_cpu_time_ns"),
        "replayed_draws": statistics.median(number(row, "replay_draws") for row in rows),
        "fallbacks": round(statistics.mean(number(row, "replay_fallbacks") for row in rows), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("state", type=Path)
    parser.add_argument("--band", choices=sorted(BANDS), default="heavy")
    parser.add_argument("--json", type=Path)
    arguments = parser.parse_args()
    logs = arguments.state / "logs" if (arguments.state / "logs").is_dir() else arguments.state
    capture = sorted(logs.glob("*.perf.csv"), key=lambda path: path.stat().st_mtime)[-1]
    with capture.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))[SETTLE_FRAMES:]
    low, high = BANDS[arguments.band]
    rows = [row for row in rows if low <= number(row, "draw_calls") < high]
    on = [row for row in rows if number(row, "replay_draws") > 0]
    off = [row for row in rows if number(row, "replay_draws") == 0 and
           number(row, "replay_captured_draws") == 0]
    capturing = [row for row in rows if number(row, "replay_draws") == 0 and
                 number(row, "replay_captured_draws") > 0]
    result = {"capture": capture.name, "band": arguments.band, "on": summarize(on),
              "off": summarize(off), "capturing_only": summarize(capturing)}
    if result["on"] and result["off"]:
        result["recorder_ns_a_draw_change_percent"] = round(
            100.0 * (result["on"]["recorder_ns_a_draw"] / result["off"]["recorder_ns_a_draw"] - 1), 1)
        result["recorder_cpu_change_percent"] = round(
            100.0 * (result["on"]["recorder_cpu_ms"] / result["off"]["recorder_cpu_ms"] - 1), 1)
    text = json.dumps(result, indent=2)
    if arguments.json:
        arguments.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
