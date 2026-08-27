#!/usr/bin/env python3
"""Summarize and compare Pinyon Shift per-frame performance captures."""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import sys
from typing import Any


SCHEMA = "pinyon-shift.performance-summary.v1"
REQUIRED_COLUMNS = {
    "frame_time_us",
    "fps",
    "draw_calls",
    "command_buffer_stalls",
    "texture_cache_hits",
    "texture_cache_misses",
    "pipeline_cache_hits",
    "pipeline_cache_misses",
}
TOTAL_COLUMNS = (
    "draw_calls",
    "command_buffer_stalls",
    "texture_cache_hits",
    "texture_cache_misses",
    "pipeline_cache_hits",
    "pipeline_cache_misses",
)
MEMEXPORT_COLUMNS = (
    "memexport_draws",
    "memexport_bytes",
    "memexport_sync_fallbacks",
    "memexport_queue_waits",
    "memexport_fence_waits",
)
XMA_STALL_COLUMNS = (
    "xma_no_space_stalls",
    "xma_no_progress_stalls",
    "xma_stall_recoveries",
)


class CaptureError(ValueError):
    """Raised when a capture cannot produce a trustworthy summary."""


def percentile(values: list[float], percentage: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise CaptureError("capture has no usable frame samples")
    position = (len(ordered) - 1) * percentage
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def finite_number(value: str, *, column: str, row_number: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise CaptureError(f"row {row_number}: {column} is not numeric") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise CaptureError(f"row {row_number}: {column} must be a finite non-negative number")
    return parsed


def hit_rate(hits: float, misses: float) -> float | None:
    total = hits + misses
    return round(hits * 100.0 / total, 6) if total else None


def summarize(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        raise CaptureError(f"capture does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or ())
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise CaptureError(f"capture is missing required columns: {', '.join(missing)}")
        available_memexport = columns.intersection(MEMEXPORT_COLUMNS)
        if available_memexport and available_memexport != set(MEMEXPORT_COLUMNS):
            missing_memexport = sorted(set(MEMEXPORT_COLUMNS) - available_memexport)
            raise CaptureError("capture has an incomplete memexport counter set: " + ", ".join(missing_memexport))
        available_xma_stalls = columns.intersection(XMA_STALL_COLUMNS)
        if available_xma_stalls and available_xma_stalls != set(XMA_STALL_COLUMNS):
            missing_xma_stalls = sorted(set(XMA_STALL_COLUMNS) - available_xma_stalls)
            raise CaptureError("capture has an incomplete XMA stall counter set: " + ", ".join(missing_xma_stalls))

        frame_times: list[float] = []
        totals = {name: 0.0 for name in TOTAL_COLUMNS}
        memexport_totals = {name: 0.0 for name in MEMEXPORT_COLUMNS} if available_memexport else None
        xma_stall_totals = {name: 0.0 for name in XMA_STALL_COLUMNS} if available_xma_stalls else None
        rows_seen = 0
        for row_number, row in enumerate(reader, start=2):
            rows_seen += 1
            frame_time = finite_number(row["frame_time_us"], column="frame_time_us", row_number=row_number)
            row_totals = {
                name: finite_number(row[name], column=name, row_number=row_number)
                for name in TOTAL_COLUMNS
            }
            row_memexport = ({name: finite_number(row[name], column=name, row_number=row_number)
                              for name in MEMEXPORT_COLUMNS} if memexport_totals is not None else {})
            row_xma_stalls = ({name: finite_number(row[name], column=name, row_number=row_number)
                               for name in XMA_STALL_COLUMNS} if xma_stall_totals is not None else {})
            # The runtime writes one initialization row with frame_time_us == 0.
            # It is valid CSV, but not a displayed frame and must not skew latency.
            if frame_time == 0:
                continue
            frame_times.append(frame_time)
            for name, value in row_totals.items():
                totals[name] += value
            for name, value in row_memexport.items():
                memexport_totals[name] += value
            for name, value in row_xma_stalls.items():
                xma_stall_totals[name] += value

    if rows_seen == 0:
        raise CaptureError("capture contains a header but no rows")
    if len(frame_times) < 2:
        raise CaptureError("capture must contain at least two non-zero frame samples")

    p50 = percentile(frame_times, 0.50)
    p95 = percentile(frame_times, 0.95)
    p99 = percentile(frame_times, 0.99)
    texture_rate = hit_rate(totals["texture_cache_hits"], totals["texture_cache_misses"])
    pipeline_rate = hit_rate(totals["pipeline_cache_hits"], totals["pipeline_cache_misses"])
    normalized_totals = {
        name: int(value) if value.is_integer() else value for name, value in totals.items()
    }
    result = {
        "schema": SCHEMA,
        "source": path.name,
        "frames": {
            "sample_count": len(frame_times),
            "measured_duration_seconds": round(sum(frame_times) / 1_000_000.0, 6),
            "frame_time_us": {
                "median": round(p50, 3),
                "p95": round(p95, 3),
                "p99": round(p99, 3),
            },
            "derived_fps": {
                "median": round(1_000_000.0 / p50, 3),
                "one_percent_low": round(1_000_000.0 / p99, 3),
            },
            "counter_totals": normalized_totals,
            "cache_hit_rate_percent": {
                "texture": texture_rate,
                "pipeline": pipeline_rate,
            },
        },
    }
    if memexport_totals is not None:
        result["memexport_counters"] = {
            name: int(value) if value.is_integer() else value for name, value in memexport_totals.items()
        }
    if xma_stall_totals is not None:
        result["xma_stall_counters"] = {
            name: int(value) if value.is_integer() else value for name, value in xma_stall_totals.items()
        }
    return result


def metric(summary: dict[str, Any], *keys: str) -> float:
    value: Any = summary
    for key in keys:
        value = value[key]
    return float(value)


def add_comparison(candidate: dict[str, Any], baseline: dict[str, Any]) -> None:
    if baseline.get("schema") != SCHEMA:
        raise CaptureError(f"baseline does not use {SCHEMA}")
    pairs = {
        "median_frame_time_us": (("frames", "frame_time_us", "median"), "lower_is_better"),
        "p95_frame_time_us": (("frames", "frame_time_us", "p95"), "lower_is_better"),
        "median_fps": (("frames", "derived_fps", "median"), "higher_is_better"),
        "one_percent_low_fps": (("frames", "derived_fps", "one_percent_low"), "higher_is_better"),
    }
    comparison: dict[str, Any] = {"baseline_source": baseline.get("source", "unknown"), "metrics": {}}
    for name, (path, direction) in pairs.items():
        before = metric(baseline, *path)
        after = metric(candidate, *path)
        if before == 0:
            raise CaptureError(f"baseline metric is zero: {name}")
        comparison["metrics"][name] = {
            "baseline": before,
            "candidate": after,
            "delta_percent": round((after - before) * 100.0 / before, 3),
            "direction": direction,
        }
    candidate["comparison"] = comparison


def markdown(summary: dict[str, Any]) -> str:
    frames = summary["frames"]
    latency = frames["frame_time_us"]
    fps = frames["derived_fps"]
    cache = frames["cache_hit_rate_percent"]
    lines = [
        f"# Performance summary: {summary['source']}",
        "",
        f"- Samples: {frames['sample_count']}",
        f"- Duration: {frames['measured_duration_seconds']:.3f} s",
        f"- Median frame time: {latency['median']:.3f} us",
        f"- P95 frame time: {latency['p95']:.3f} us",
        f"- Median FPS: {fps['median']:.3f}",
        f"- 1% low: {fps['one_percent_low']:.3f} FPS",
        f"- Draw calls: {frames['counter_totals']['draw_calls']}",
        f"- Command-buffer stalls: {frames['counter_totals']['command_buffer_stalls']}",
        f"- Texture cache hit rate: {cache['texture'] if cache['texture'] is not None else 'n/a'}%",
        f"- Pipeline cache hit rate: {cache['pipeline'] if cache['pipeline'] is not None else 'n/a'}%",
    ]
    if "comparison" in summary:
        lines.extend(["", "## Baseline comparison", "", "| Metric | Baseline | Candidate | Delta |", "| --- | ---: | ---: | ---: |"])
        for name, values in summary["comparison"]["metrics"].items():
            lines.append(
                f"| {name.replace('_', ' ')} | {values['baseline']:.3f} | "
                f"{values['candidate']:.3f} | {values['delta_percent']:+.3f}% |"
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=pathlib.Path, help="per-frame CSV capture")
    parser.add_argument("--baseline", type=pathlib.Path, help="summary JSON to compare against")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", type=pathlib.Path, help="write output to this file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = summarize(args.capture)
        if args.baseline:
            with args.baseline.open("r", encoding="utf-8") as stream:
                add_comparison(result, json.load(stream))
        rendered = json.dumps(result, indent=2) + "\n" if args.format == "json" else markdown(result)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (CaptureError, json.JSONDecodeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
