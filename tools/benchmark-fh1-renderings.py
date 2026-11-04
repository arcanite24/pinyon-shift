#!/usr/bin/env python3
"""Measure a target-filtered draw knock-out in interleaved frame replays.

The result is a marginal cost with a deliberately wrong image, not a promise
that a replacement pass can save it. Inputs and all output stay local.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import statistics
import sys
from pathlib import Path


def load_replay():
    path = Path(__file__).with_name("replay-fh1-frame.py")
    spec = importlib.util.spec_from_file_location("replay_fh1_frame", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def timings(path: Path, warmup: int, minimum: int, metric: str = "gpu") -> dict:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))[warmup:]
    complete = [r for r in rows if None not in r and all(v is not None for v in r.values())]
    gpu = [r for r in complete if int(r["guest_frame_gpu_timing_samples"]) == 1
             and int(r["native_gpu_timing_drops"]) == 0
             and int(r["guest_frame_gpu_time_ns"]) > 0]
    valid = gpu if metric == "gpu" else [r for r in complete if int(r["frame_time_us"]) > 0]
    if len(valid) < minimum:
        raise ValueError(f"{path}: only {len(valid)} valid {metric} samples; need {minimum}")
    return {
        "samples": len(valid), "excluded": len(rows) - len(valid),
        "gpu_median_ms": (statistics.median(int(r["guest_frame_gpu_time_ns"]) / 1e6 for r in gpu)
                          if len(gpu) >= minimum else None),
        "frame_median_ms": statistics.median(int(r["frame_time_us"]) / 1e3 for r in valid),
        "decoded_draws_median": statistics.median(int(r["gpu_decoded_draws"]) for r in valid),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dump", type=Path)
    parser.add_argument("--state-root", type=Path, required=True, help="read-only pinned seed")
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    parser.add_argument("--build-directory", type=Path, required=True)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--renderings", required=True, help="comma-separated exact profile labels")
    parser.add_argument("--pairs", type=int, default=3, help="disjoint off/on/off blocks")
    parser.add_argument("--repeat", type=int, default=610)
    parser.add_argument("--warmup", type=int, default=300)
    parser.add_argument("--minimum-samples", type=int, default=100)
    parser.add_argument("--metric", choices=("gpu", "frame"), default="gpu",
                        help="frame measures end-to-end replay latency, including CPU/idle time")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--game-argument", action="append", default=[])
    args = parser.parse_args()
    if args.pairs < 1 or args.warmup < 0 or args.minimum_samples < 1 or not (
            args.warmup + args.minimum_samples <= args.repeat <= 100000):
        parser.error("need positive blocks and samples, and warmup + minimum <= repeat <= 100000")
    if not args.renderings or any(not r for r in args.renderings.split(",")):
        parser.error("rendering labels must be nonempty")
    if args.output.resolve().is_relative_to(args.state_root.resolve()):
        parser.error("output must be outside the read-only seed")
    if not all((args.state_root / name).exists() for name in ("user", "config", "seed.json")):
        parser.error("state root must be a pinned render seed (user, config, seed.json)")
    # Replay writes its result beside the dump: use a private copy too.
    args.output.mkdir(parents=True, exist_ok=False)
    dump = args.output.resolve() / "input.fh1frame"
    shutil.copyfile(args.dump, dump)
    replay = load_replay()
    runner = replay.load_runner()
    report = {
        "schema": "pinyon-shift.rendering-knockout.v1",
        "dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
        "seed_manifest_sha256": hashlib.sha256((args.state_root / "seed.json").read_bytes()).hexdigest(),
        "renderings": args.renderings,
        "settings": vars(args) | {"method": "disjoint off/on/off blocks; per-pass timestamps off"},
        "build": runner.build_provenance(args.build_directory.resolve(), None),
        "runs": [], "blocks": [],
    }
    for name in ("rexgpu-fh1.dll", "librexgpu-fh1.so", "librexgpu-fh1.dylib"):
        module = args.build_directory / name
        if module.is_file():
            report["build"]["gpu_module_sha256"] = hashlib.sha256(module.read_bytes()).hexdigest()
    reference = None
    reference_work = None
    for block in range(args.pairs):
        measured = []
        for phase, enabled in enumerate((False, True, False)):
            name = f"block{block + 1}-{phase}-{'on' if enabled else 'off'}"
            work = args.output.resolve() / name
            options = argparse.Namespace(
                dump=dump, state_root=args.state_root, work=work,
                shader_pack=None, configuration=None, build_directory=args.build_directory,
                hidden=True, timeout=args.timeout, max_differing_words=None, write_golden=False,
                game_root=args.game_root,
                game_argument=args.game_argument + [
                    "--gpu_backend=vulkan", f"--fh1_frame_replay_repeat={args.repeat}",
                    "--fh1_frame_replay_present=false",
                    "--vsync=false", "--host_present_fps_limit=0",
                    "--pinyon_shift_fh1_render_fps_limit=0", "--audio_mute=true",
                    "--fh1_native_gpu_profile=false", "--fh1_native_gpu_profile_draws=false",
                    f"--fh1_debug_skip_renderings={args.renderings}",
                    f"--fh1_debug_skip_rendering_draws={str(enabled).lower()}",
                ])
            result = replay.replay(options)
            if result.get("failure") or not result.get("executed") or not result.get("readback"):
                raise RuntimeError(f"{name}: replay failed: {result}")
            actual = Path(f"{dump}.replay.bin").read_bytes()
            (work / "front.bin").write_bytes(actual)
            if not enabled:
                if reference is not None and actual != reference:
                    raise RuntimeError(f"{name}: control replay changed; comparison invalid")
                reference = actual
            log = (work / "logs/runtime.log").read_text(encoding="utf-8", errors="replace")
            sessions = list((work / "logs").glob("*.jsonl"))
            if len(sessions) != 1:
                raise RuntimeError(f"{name}: expected one session log")
            events = [json.loads(line) for line in sessions[0].read_text(encoding="utf-8").splitlines()
                      if line.strip()]
            device = next(e for e in events if e.get("event") == "graphics.device.selected")
            device = {k: device[k] for k in ("backend", "name", "vendor_id", "device_id",
                                             "api_version", "driver_version")}
            if report.get("device", device) != device:
                raise RuntimeError(f"{name}: graphics device changed; comparison invalid")
            report["device"] = device
            counts = re.findall(r"debug_rendering_draw_skipped=(\d+)", log)
            skipped = int(counts[-1]) if counts else 0
            if enabled != bool(skipped):
                raise RuntimeError(f"{name}: selected draw count {skipped}; check labels and probe build")
            counters = re.findall(
                r"FH1 native executor \(Vulkan\) frame=\d+ draws=(\d+) resolves=(\d+)", log)
            if not counters or not all(int(n) > 0 for n in counters[-1]):
                raise RuntimeError(f"{name}: missing native draw/resolve census")
            if reference_work is not None and counters[-1] != reference_work:
                raise RuntimeError(f"{name}: draw/resolve work changed; comparison invalid")
            reference_work = counters[-1]
            captures = list((work / "logs").glob("*.perf.csv"))
            if len(captures) != 1:
                raise RuntimeError(f"{name}: expected one performance CSV")
            timing = timings(captures[0], args.warmup, args.minimum_samples, args.metric)
            measured.append(timing[f"{args.metric}_median_ms"])
            report["runs"].append({"name": name, "enabled": enabled, "skipped": skipped,
                                   "front_sha256": hashlib.sha256(actual).hexdigest(), **timing})
            print(json.dumps(report["runs"][-1]), flush=True)
        report["blocks"].append((measured[0] + measured[2]) / 2 - measured[1])
        report["saving_mean_ms"] = statistics.mean(report["blocks"])
        report["saving_standard_error_ms"] = (
            statistics.stdev(report["blocks"]) / len(report["blocks"]) ** 0.5
            if len(report["blocks"]) > 1 else None)
        (args.output / "result.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
