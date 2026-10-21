#!/usr/bin/env python3
"""Compare the two sides of an in-run A/A or A/B capture window by window.

Frames are classed by the perf capture's `aa_toggle` column, which a route
made with `tools/make-ab-route.py --mark` (or an A/A route) sets to 0 or 1
for each window. The first --settle frames of every window are left out.
Each window gets the mean of every metric over its frames. The windows are
cut into disjoint blocks of three alternating windows (A B A or B A B); each
block's difference (side 1 minus side 0) takes the middle window against the
mean of its neighbours, so a linear thermal drift cancels inside the block
(NEAR_NATIVE_RESEARCH NN-0.3). Blocks share no window, so their spread gives
an honest standard error; the earlier method paired every adjacent window,
and those overlapping pairs understated it (#747).

A metric named with --metrics that the capture lacks, and a value that is not
a number, stop the script. A row without an aa_toggle value (a capture cut off
mid-row) is left out and counted.

    summarize-inrun-ab.py RUN_STATE_OR_CSV [--from-row N] [--json out.json]

Metrics are in ms per frame for `*_ns` columns and per frame otherwise.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

DEFAULT_METRICS = [
    "frame_time_us",
    "process_cpu_ns",
    "gpu_decoder_cpu_ns",
    "gpu_recorder_cpu_ns",
    "gpu_submission_busy_ns",
    "fh1_title_thread_cpu_time_ns",
    "injected_cpu_ns",
    "gpu_decoded_draws",
    "fh1_untile_skipped_draws",
    "replay_probe_ibs",
    "replay_probe_repeat_ibs",
    "replay_probe_skipped_ibs",
    "replay_probe_drawn_in_ibs",
    "replay_probe_drawn_in_repeat_ibs",
    "replay_probe_drawn_in_skippable_repeat_ibs",
    "replay_probe_skipped_drawn_draws",
    "replay_probe_hash_ns",
    "replay_probe_apply_ns",
    "replay_probe_exit_registers",
]


def find_capture(path: Path) -> Path:
    if path.is_file():
        return path
    logs = path / "logs" if (path / "logs").is_dir() else path
    captures = sorted(logs.rglob("*.perf.csv"), key=lambda item: item.stat().st_mtime)
    if not captures:
        raise SystemExit(f"no *.perf.csv under {path}")
    return captures[-1]


class CaptureError(ValueError):
    pass


def number(row: dict, column: str) -> float:
    value = row.get(column)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise CaptureError(f"{column}: {value!r} is not a number") from None


def scale(column: str) -> float:
    if column.endswith("_ns"):
        return 1e6
    if column.endswith("_us"):
        return 1e3
    return 1.0


def windows(rows: list[dict], settle: int) -> list[tuple[int, int, list[dict]]]:
    """Runs of equal aa_toggle as (side, first row, rows after settling)."""
    result = []
    current = None
    start = 0
    run: list[dict] = []
    for index, row in enumerate(rows):
        if not row.get("aa_toggle"):
            continue
        side = int(number(row, "aa_toggle"))
        if side != current:
            if current is not None:
                result.append((current, start, run[settle:]))
            current, start, run = side, index, []
        run.append(row)
    if current is not None:
        result.append((current, start, run[settle:]))
    return [window for window in result if window[2]]


# Two-sided 95 % Student t quantiles by degrees of freedom: a run has few
# blocks (15 windows give 5), so the normal 1.96 would be too narrow.
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
       2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086]


def t95(degrees: int) -> float:
    return T95[degrees - 1] if degrees <= len(T95) else 1.96


def window_means(found: list[tuple[int, int, list[dict]]], metrics: list[str],
                 from_row: int = 0) -> list[dict]:
    return [{
        "side": side,
        "first_row": start + from_row,
        "frames": len(frames),
        **{column: statistics.fmean(number(row, column) for row in frames) / scale(column)
           for column in metrics},
    } for side, start, frames in found]


def block_differences(means: list[dict], metrics: list[str]) -> list[dict]:
    """Side 1 minus side 0 for disjoint A B A / B A B blocks of windows.

    The middle window is compared with the mean of its two neighbours, which
    cancels a drift that is linear across the block. A block whose sides do
    not alternate (a window dropped by --min-frames) is skipped by one window.
    """
    blocks = []
    index = 0
    while index + 2 < len(means):
        first, middle, last = means[index:index + 3]
        if first["side"] == last["side"] != middle["side"]:
            sign = 1.0 if middle["side"] == 1 else -1.0
            blocks.append({column: sign * (middle[column] - (first[column] + last[column]) / 2)
                           for column in metrics})
            index += 3
        else:
            index += 1
    return blocks


def summarize(means: list[dict], blocks: list[dict], metrics: list[str]) -> dict:
    summary = {}
    for column in metrics:
        sides = {side: [window[column] for window in means if window["side"] == side]
                 for side in (0, 1)}
        differences = [block[column] for block in blocks]
        entry = {
            "side0": round(statistics.fmean(sides[0]), 4) if sides[0] else None,
            "side1": round(statistics.fmean(sides[1]), 4) if sides[1] else None,
        }
        if differences:
            mean = statistics.fmean(differences)
            deviation = statistics.stdev(differences) if len(differences) > 1 else None
            entry.update({
                "difference": round(mean, 4),
                "block_sd": round(deviation, 4) if deviation is not None else None,
                "standard_error": (round(deviation / math.sqrt(len(differences)), 4)
                                   if deviation is not None else None),
                "ci95": (round(t95(len(differences) - 1) * deviation
                               / math.sqrt(len(differences)), 4)
                         if deviation is not None else None),
                "block_min": round(min(differences), 4),
                "block_max": round(max(differences), 4),
            })
        summary[column] = entry
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", type=Path, help="a run's state directory or its perf CSV")
    parser.add_argument("--from-row", type=int, default=0,
                        help="ignore rows before this one (menus, loading)")
    parser.add_argument("--settle", type=int, default=30)
    parser.add_argument("--min-frames", type=int, default=60,
                        help="ignore windows with fewer frames after settling")
    parser.add_argument("--metrics", nargs="*", default=None)
    parser.add_argument("--json", type=Path)
    arguments = parser.parse_args()

    capture = find_capture(arguments.capture)
    with capture.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))[arguments.from_row:]
    if not rows or "aa_toggle" not in rows[0]:
        raise SystemExit(f"{capture.name}: no aa_toggle column (a build without NN-0.3?)")
    if arguments.metrics:
        missing = [column for column in arguments.metrics if column not in rows[0]]
        if missing:
            raise SystemExit(f"{capture.name}: no column {', '.join(missing)}")
        metrics = arguments.metrics
    else:
        metrics = [column for column in DEFAULT_METRICS if column in rows[0]]
    incomplete = sum(1 for row in rows if not row.get("aa_toggle"))

    try:
        found = windows(rows, arguments.settle)
        found = [window for window in found if len(window[2]) >= arguments.min_frames]
        means = window_means(found, metrics, arguments.from_row)
    except CaptureError as error:
        raise SystemExit(f"{capture.name}: {error}") from None
    blocks = block_differences(means, metrics)
    summary = summarize(means, blocks, metrics)

    result = {
        "capture": capture.name,
        "rows": len(rows),
        "incomplete_rows": incomplete,
        "windows": len(means),
        "blocks": len(blocks),
        "units": "ms a frame for *_ns and *_us columns, count a frame otherwise",
        "summary": summary,
        "windows_detail": [{key: (round(value, 4) if isinstance(value, float) else value)
                            for key, value in window.items()} for window in means],
    }
    text = json.dumps(result, indent=2)
    if arguments.json:
        arguments.json.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("capture", "rows", "incomplete_rows", "windows", "blocks",
                                                   "units", "summary")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
