#!/usr/bin/env python3
"""Commit-tagged low-spec benchmark records (LOW_SPEC_BACKLOG LS-0.2, LS-0.6).

`record` reads one render-test run (its isolated state directory) and writes a
JSON record: the commit and SDK, the machine, the effective settings the game
logged, any low-end simulation the runner applied, and the frame metrics of
the race's draw bands. `table` renders records as the markdown table the
README's performance section uses, so prose never drifts from measurements.

    summarize-low-spec.py record RUN.state --label "4C/8T" --output r.json
    summarize-low-spec.py table benchmarks/results/*.json
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "pinyon-shift.low-spec-benchmark.v1"
ROOT = Path(__file__).resolve().parents[1]
# The 60 fps frame budget and the release gate's limits (LOW_SPEC_BACKLOG).
BUDGET_MS = 1000.0 / 60.0
GATE_P95_MS = 16.9
GATE_LONG_MS = 25.0
GATE_PRESENTS = 59.0
# Draw bands (DR's method): the race's heavy start, and gameplay in general.
BANDS = {"heavy": (5000, None), "gameplay": (2000, None)}
# Frames after loading (output frames run uncapped while loading).
SETTLE_FRAMES = 120
SETTINGS = (
    "renderer", "vsync", "host_present_fps_limit", "fh1_render_fps_limit",
    "draw_resolution_scale_x", "anisotropic_override", "swap_post_effect",
    "disable_bloom", "disable_motion_blur", "disable_depth_of_field",
)
CPU_COLUMNS = {
    "decoder_cpu_ms": "gpu_decoder_cpu_ns",
    "recorder_cpu_ms": "gpu_recorder_cpu_ns",
    "recorder_busy_ms": "gpu_recorder_busy_ns",
    "title_thread_cpu_ms": "fh1_title_thread_cpu_time_ns",
    "reg_mem_wait_ms": "gpu_thread_reg_mem_wait_ns",
    "title_fence_wait_ms": "title_gpu_fence_wait_ns",
}
MEMORY_COLUMNS = (
    "memory_device_usage_mb", "memory_device_budget_mb", "fh1_surface_count",
    "fh1_surface_mb", "texture_cache_mb", "process_resident_mb",
)


def git(*arguments: str, cwd: Path = ROOT) -> str:
    result = subprocess.run(["git", *arguments], cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip()


def revision(cwd: Path) -> str:
    head = git("rev-parse", "--short=12", "HEAD", cwd=cwd)
    dirty = git("status", "--porcelain", "--untracked-files=no", cwd=cwd)
    return head + ("-dirty" if dirty else "")


def cpu_name() -> str:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor()


def newest(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime)
    if not files:
        raise SystemExit(f"no {pattern} in {directory}")
    return files[-1]


def load_events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def event_fields(events: list[dict], name: str) -> dict:
    for event in events:
        if event.get("event") == name:
            fields = event.get("fields", event)
            return {key: value for key, value in fields.items() if key != "event"}
    return {}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def number(row: dict, column: str) -> float:
    try:
        return float(row.get(column) or 0)
    except ValueError:
        return 0.0


def band_metrics(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    frame_ms = [number(row, "frame_time_us") / 1000.0 for row in rows]
    seconds = sum(frame_ms) / 1000.0
    presents = sum(number(row, "present_count") for row in rows)
    metrics = {
        "frames": len(rows),
        "draws_median": statistics.median(number(row, "draw_calls") for row in rows),
        "frame_ms_p50": round(percentile(frame_ms, 0.50), 3),
        "frame_ms_p95": round(percentile(frame_ms, 0.95), 3),
        "frame_ms_p99": round(percentile(frame_ms, 0.99), 3),
        "over_budget_share": round(sum(ms > GATE_P95_MS for ms in frame_ms) / len(rows), 4),
        "over_25ms_share": round(sum(ms > GATE_LONG_MS for ms in frame_ms) / len(rows), 4),
        "presents_per_second": round(presents / seconds, 2) if seconds else None,
        "deadline_misses_per_second": round(
            sum(number(row, "present_deadline_misses") for row in rows) / seconds, 3)
        if seconds else None,
    }
    for name, column in CPU_COLUMNS.items():
        metrics[name] = round(statistics.median(number(row, column) for row in rows) / 1e6, 3)
    # Runtime overheads that cost more on slow cores (LS-5.4), per frame.
    for name, column in (("write_watch_protect_calls", "write_watch_protect_calls"),
                         ("clock_mutex_contentions", "clock_mutex_contentions"),
                         ("reg_mem_waits", "gpu_reg_mem_wait_count")):
        metrics[name] = round(statistics.mean(number(row, column) for row in rows), 2)
    # CPU time of the measured threads per second of play, in cores.
    busy = sum(number(row, CPU_COLUMNS[name]) for row in rows
               for name in ("decoder_cpu_ms", "recorder_cpu_ms", "title_thread_cpu_ms"))
    metrics["measured_threads_cores"] = round(busy / 1e9 / seconds, 3) if seconds else None
    # Source frames jitter about +-1.5 ms around the budget even on the
    # reference machine while every one is presented on time, so the gate
    # counts delivered frames and long frames rather than the p95.
    metrics["gate_cadence"] = bool(metrics["presents_per_second"] and
                                   metrics["presents_per_second"] >= GATE_PRESENTS and
                                   metrics["over_25ms_share"] <= 0.01)
    return metrics


def record(arguments: argparse.Namespace) -> int:
    state = arguments.state
    logs = state / "logs" if (state / "logs").is_dir() else state
    perf = newest(logs, "*.perf.csv")
    events = load_events(perf.with_name(perf.name.replace(".perf.csv", ".jsonl")))
    with perf.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    played = rows[SETTLE_FRAMES:]
    bands = {}
    for name, (low, high) in BANDS.items():
        selected = [row for row in played
                    if number(row, "draw_calls") >= low
                    and (high is None or number(row, "draw_calls") < high)]
        bands[name] = band_metrics(selected)
    memory = {}
    for column in MEMORY_COLUMNS:
        values = [number(row, column) for row in rows if column in row]
        memory[f"{column}_peak"] = max(values) if values else None
        memory[f"{column}_end"] = values[-1] if values else None
    budget = memory.get("memory_device_budget_mb_end") or 0
    peak = memory.get("memory_device_usage_mb_peak") or 0
    memory["peak_share_of_budget"] = round(peak / budget, 3) if budget else None
    simulation = None
    game_arguments: list[str] = []
    if arguments.run_result and arguments.run_result.is_file():
        run_result = json.loads(arguments.run_result.read_text(encoding="utf-8"))
        simulation = run_result.get("low_spec_simulation")
        game_arguments = run_result.get("game_arguments") or []
    device = event_fields(events, "graphics.device.selected")
    # The config file's values as logged, then the command line's overrides
    # (GPU settings register after logging starts and log empty there).
    settings = {key: value for key, value in event_fields(events, "logging.ready").items()
                if value != ""}
    for argument in game_arguments:
        name, _, value = argument.lstrip("-").partition("=")
        settings[name.removeprefix("pinyon_shift_")] = value
    result = {
        "schema": SCHEMA,
        "label": arguments.label,
        "recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": revision(ROOT),
        "sdk": revision(ROOT / "thirdparty/shiftglue-sdk"),
        "route": arguments.route,
        "machine": {"cpu": cpu_name(), "gpu": device.get("name"),
                    "driver_version": device.get("driver_version"), "os": platform.platform()},
        "simulation": simulation,
        "settings": {key: settings.get(key) for key in SETTINGS + ("fh1_msaa_single_sample", "present_effect", "host_cpu_simulation") if key in settings},
        "bands": bands,
        "memory": memory,
        "capture": str(perf),
    }
    text = json.dumps(result, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def cell(value: object, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def table(arguments: argparse.Namespace) -> int:
    records = [json.loads(path.read_text(encoding="utf-8")) for path in arguments.records]
    band = arguments.band
    lines = [
        f"| Configuration | Machine | Median | p95 | Over 16.9 ms | Over 25 ms | "
        f"Decoder CPU | Recorder CPU | Title CPU | Peak VRAM | Commit |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in records:
        metrics = (item.get("bands") or {}).get(band) or {}
        memory = item.get("memory") or {}
        simulated = " (simulated)" if item.get("simulation") else ""
        vram = memory.get("memory_device_usage_mb_peak")
        budget = memory.get("memory_device_budget_mb_end")
        lines.append(
            f"| {item['label']}{simulated} | {item['machine'].get('cpu')}, "
            f"{item['machine'].get('gpu')} | {cell(metrics.get('frame_ms_p50'), 2)} ms | "
            f"{cell(metrics.get('frame_ms_p95'), 2)} ms | "
            f"{cell(100 * metrics['over_budget_share'] if 'over_budget_share' in metrics else None)} % | "
            f"{cell(100 * metrics['over_25ms_share'] if 'over_25ms_share' in metrics else None)} % | "
            f"{cell(metrics.get('decoder_cpu_ms'), 2)} ms | {cell(metrics.get('recorder_cpu_ms'), 2)} ms | "
            f"{cell(metrics.get('title_thread_cpu_ms'), 2)} ms | "
            f"{cell(vram, 0)} of {cell(budget, 0)} MB | `{item['commit']}` |")
    print("\n".join(lines))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    record_parser = commands.add_parser("record", help="write one run's record")
    record_parser.add_argument("state", type=Path, help="the run's isolated state (or logs) directory")
    record_parser.add_argument("--label", required=True)
    record_parser.add_argument("--route", default="fh1-race-start-wait")
    record_parser.add_argument("--run-result", type=Path,
                               help="the runner's JSON output (for the simulation it applied)")
    record_parser.add_argument("--output", type=Path)
    table_parser = commands.add_parser("table", help="markdown table of records")
    table_parser.add_argument("records", type=Path, nargs="+")
    table_parser.add_argument("--band", default="heavy", choices=sorted(BANDS))
    arguments = parser.parse_args()
    return record(arguments) if arguments.command == "record" else table(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
