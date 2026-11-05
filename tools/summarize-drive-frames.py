#!/usr/bin/env python3
"""Summarize the driving frames of a free-roam performance capture.

The free-roam routes spend most of their frames on the title screen and the
loading screen, where a frame has 50-90 draw calls. Driving frames have more
than 800. A whole-run median therefore measures the menus, not the drive. This
reads the per-frame performance CSV a render test leaves under
``<out>.state/logs``, keeps only frames whose draw count is above the
threshold, and reports their GPU and frame time with the counters that rise
in the drive.

With ``--runtime-log`` it also prints the FH1 executor stats lines (renderings
a frame and what ended them) whose frame falls inside the drive window, so
the rendering count can be read for the drive rather than the menu phase.
Lower ``fh1_native_stats_frames`` (default 600) so a window lands there.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import statistics
import sys

COUNTERS = (
    "gpu_thread_fence_wait_ns",
    "title_gpu_fence_wait_count",
    "title_gpu_fence_wait_ns",
    "gpu_thread_idle_ns",
    "gpu_submission_busy_ns",
    "texture_resolve_reloads",
    "texture_resolve_reload_bytes",
    "texture_band_reloads",
    "texture_cache_misses",
    "command_buffer_stalls",
)


def percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * share)))]


def summarize(path: pathlib.Path, min_draws: int) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if rows and None in rows[-1].values():
        rows.pop()
    # Rows are frames; the first row is the initialization row (frame_time 0).
    frames = []
    for index, row in enumerate(rows):
        frame_time = int(row["frame_time_us"])
        if frame_time <= 0:
            continue
        frames.append((index, row))
    drive = [(i, r) for i, r in frames if int(r["draw_calls"]) > min_draws]
    menus = [(i, r) for i, r in frames if int(r["draw_calls"]) <= min_draws]
    if len(drive) < 10:
        raise SystemExit(f"error: only {len(drive)} frames have more than {min_draws} draws")

    def ms(rows_, key, samples=None):
        values = [
            int(r[key]) / 1e6
            for _, r in rows_
            if samples is None or int(r[samples]) > 0
        ]
        return values

    gpu = ms(drive, "guest_frame_gpu_time_ns", "guest_frame_gpu_timing_samples")
    frame = [int(r["frame_time_us"]) / 1e3 for _, r in drive]
    indices = [i for i, _ in drive]
    # The CSV row index is the output frame number; stats lines use the
    # executor's frame counter, which advances once per guest frame too.
    result = {
        "schema": "pinyon-shift.drive-frames-summary.v1",
        "source": path.name,
        "min_draws": min_draws,
        "frames_total": len(frames),
        "drive_frames": len(drive),
        "drive_row_range": [indices[0], indices[-1]],
        "draws_per_frame": {
            "median": statistics.median(int(r["draw_calls"]) for _, r in drive),
            "max": max(int(r["draw_calls"]) for _, r in drive),
        },
        "gpu_ms": {
            "samples": len(gpu),
            "median": round(statistics.median(gpu), 2) if gpu else None,
            "p95": round(percentile(gpu, 0.95), 2) if gpu else None,
        },
        "frame_ms": {
            "median": round(statistics.median(frame), 2),
            "p95": round(percentile(frame, 0.95), 2),
            "fps_median": round(1000.0 / statistics.median(frame), 1),
        },
        "menu_frame_ms_median": (
            round(statistics.median(int(r["frame_time_us"]) / 1e3 for _, r in menus), 2)
            if menus else None
        ),
        "counters_per_drive_frame": {},
    }
    for key in COUNTERS:
        if key not in rows[0]:
            continue
        values = [float(r[key]) for _, r in drive]
        entry = {"median": statistics.median(values), "mean": round(sum(values) / len(values), 1)}
        if key.endswith("_ns"):
            entry = {k: round(v / 1e6, 2) for k, v in entry.items()}
            entry["unit"] = "ms"
        elif key.endswith("_bytes"):
            entry = {k: round(v / 1e6, 2) for k, v in entry.items()}
            entry["unit"] = "MB"
        result["counters_per_drive_frame"][key] = entry
    return result


STATS = re.compile(r"FH1 native executor \(Vulkan\) frame=(\d+) draws=(\d+) resolves=(\d+)")
RENDERINGS = re.compile(r"per frame over (\d+) frames: renderings ([0-9.]+)")
ENDERS = re.compile(r"renderings ended by other work, per frame: (.*)$")


def stats_windows(log: pathlib.Path, first: int, last: int) -> list[dict]:
    """Executor stats windows whose frame range overlaps the drive rows."""
    windows = []
    current = None
    previous_frame = 0
    previous_draws = 0
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = STATS.search(line)
        if match:
            frame, draws = int(match.group(1)), int(match.group(2))
            current = {
                "frame": frame,
                "window_start": previous_frame,
                "draws_per_frame": round((draws - previous_draws) / max(1, frame - previous_frame), 1),
            }
            previous_frame, previous_draws = frame, draws
            windows.append(current)
            continue
        if current is None:
            continue
        match = RENDERINGS.search(line)
        if match:
            current["window_frames"] = int(match.group(1))
            current["renderings_per_frame"] = float(match.group(2))
            continue
        match = ENDERS.search(line)
        if match:
            enders = []
            for part in match.group(1).split("; "):
                count, _, name = part.partition(" ")
                short = re.sub(r"\(.*", "", name).split("::")[-1]
                enders.append({"per_frame": float(count), "ender": short})
            current["enders"] = enders[:3]
    inside = []
    for window in windows:
        start, end = window["window_start"], window["frame"]
        if end <= first or start >= last:
            continue
        window["fully_in_drive"] = start >= first and end <= last
        inside.append(window)
    return inside


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("perf_csv", type=pathlib.Path)
    parser.add_argument("--min-draws", type=int, default=800)
    parser.add_argument("--runtime-log", type=pathlib.Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    result = summarize(args.perf_csv, args.min_draws)
    if args.runtime_log:
        first, last = result["drive_row_range"]
        result["executor_stats_in_drive"] = stats_windows(args.runtime_log, first, last)
    if args.format == "json":
        print(json.dumps(result, indent=2))
        return 0
    g, f = result["gpu_ms"], result["frame_ms"]
    print(f"drive frames {result['drive_frames']} (rows {result['drive_row_range'][0]}-{result['drive_row_range'][1]}),"
          f" draws/frame median {result['draws_per_frame']['median']:.0f}")
    print(f"GPU ms median {g['median']} p95 {g['p95']}; frame ms median {f['median']} p95 {f['p95']} ({f['fps_median']} fps)")
    for key, entry in result["counters_per_drive_frame"].items():
        print(f"  {key}: median {entry['median']} {entry.get('unit', '')}")
    for window in result.get("executor_stats_in_drive", []):
        full = "in drive" if window["fully_in_drive"] else "overlaps drive edge"
        print(f"stats window {window['window_start']}-{window['frame']} ({full}): draws/frame {window['draws_per_frame']},"
              f" renderings/frame {window.get('renderings_per_frame')}")
        for e in window.get("enders", []):
            print(f"    {e['per_frame']:5.1f} {e['ender']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
