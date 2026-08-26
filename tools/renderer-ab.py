#!/usr/bin/env python3
"""Prepare and compare one-variable renderer experiments without changing shipping defaults."""
from __future__ import annotations

import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

VARIABLES = {"readback_memexport": ("true", "false"), "clear_memory_page_state": ("true", "false"),
             "d3d12_submit_on_primary_buffer_end": ("true", "false")}
MEMEXPORT_COUNTERS = ("memexport_draws", "memexport_bytes", "memexport_sync_fallbacks", "memexport_queue_waits", "memexport_fence_waits")

def prepare(root: Path, variable: str, fingerprint: Path) -> Path:
    build = json.loads(fingerprint.read_text(encoding="utf-8")); stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session = root / f"{stamp}-{variable}"; session.mkdir(parents=True)
    manifest = {"schema": "pinyon-shift.renderer-ab.v1", "variable": variable, "shipping_defaults_unchanged": True,
                "build": build, "variants": [{"name": "control", "value": VARIABLES[variable][0]}, {"name": "candidate", "value": VARIABLES[variable][1]}],
                "required_evidence": ["performance-summary.json", "visual-validation.json"],
                "required_memexport_counters": list(MEMEXPORT_COUNTERS) if variable == "readback_memexport" else []}
    (session / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for variant in manifest["variants"]:
        folder = session / variant["name"]; folder.mkdir()
        (folder / "override.toml").write_text(f"# Temporary A/B override; do not ship.\n{variable} = {variant['value']}\n", encoding="utf-8")
    return session

def compare(session: Path) -> dict:
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8")); summaries = {}
    for variant in ("control", "candidate"):
        folder = session / variant
        perf = json.loads((folder / "performance-summary.json").read_text(encoding="utf-8"))
        visual = json.loads((folder / "visual-validation.json").read_text(encoding="utf-8"))
        if visual.get("missing"): raise ValueError(f"{variant} visual evidence is incomplete")
        if manifest["variable"] == "readback_memexport":
            counters = perf.get("memexport_counters", {})
            missing = [name for name in MEMEXPORT_COUNTERS if name not in counters]
            if missing: raise ValueError("memexport evidence lacks counters: " + ", ".join(missing))
        summaries[variant] = perf
    result = {"schema": manifest["schema"], "variable": manifest["variable"], "build": manifest["build"],
              "control_sha256": hashlib.sha256(json.dumps(summaries["control"], sort_keys=True).encode()).hexdigest(),
              "candidate_sha256": hashlib.sha256(json.dumps(summaries["candidate"], sort_keys=True).encode()).hexdigest(),
              "comparison": {"median_frame_time_us_delta": summaries["candidate"]["frame_time_us"]["median"] - summaries["control"]["frame_time_us"]["median"],
                             "p95_frame_time_us_delta": summaries["candidate"]["frame_time_us"]["p95"] - summaries["control"]["frame_time_us"]["p95"]}}
    (session / "comparison.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8"); return result

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("action", choices=("prepare", "compare")); parser.add_argument("path", type=Path)
    parser.add_argument("--variable", choices=VARIABLES); parser.add_argument("--build-fingerprint", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            if not args.variable or not args.build_fingerprint: raise ValueError("prepare requires --variable and --build-fingerprint")
            result = {"path": str(prepare(args.path, args.variable, args.build_fingerprint))}
        else: result = compare(args.path)
        print(json.dumps(result, indent=2)); return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc: parser.exit(2, f"renderer A/B error: {exc}\n")
if __name__ == "__main__": raise SystemExit(main())
