#!/usr/bin/env python3
"""Write an in-run A/B variant of a render-test route.

Adds `cvar` steps that alternate a hot-reload setting every N output frames
between two values, merged into the route's own steps in frame order, so one
run measures both sides under the same thermal and scene conditions (the
backlogs' in-run A/B method).

    make-ab-route.py config/render-tests/fh1-race-start-wait.fh1test \
        --setting gpu_buffer_replay --values false true --every 300 \
        --from 600 --output config/render-tests/fh1-race-start-replay-ab.fh1test
"""

from __future__ import annotations

import argparse
from pathlib import Path


def step_frame(line: str) -> int | None:
    parts = line.split()
    if len(parts) >= 2 and not line.startswith("#") and parts[1].isdigit():
        return int(parts[1])
    return None


def make(route: str, setting: str, values: tuple[str, str], every: int, start: int) -> str:
    lines = route.splitlines()
    header = lines[0]
    body = lines[1:]
    stop = max((step_frame(line) or 0) for line in body if line.startswith("stop"))
    toggles = []
    index = 0
    for frame in range(start, stop, every):
        toggles.append((frame, f"cvar {frame} {setting} {values[index % 2]}"))
        index += 1
    merged = []
    pending = list(toggles)
    for line in body:
        frame = step_frame(line)
        while pending and frame is not None and pending[0][0] < frame:
            merged.append(pending.pop(0)[1])
        merged.append(line)
    insert_at = next(i for i, line in enumerate(merged) if line.startswith("stop"))
    for _, line in pending:
        merged.insert(insert_at, line)
        insert_at += 1
    note = (f"# In-run A/B: {setting} alternates {values[0]}/{values[1]} every {every} output "
            f"frames from frame {start} (tools/make-ab-route.py).")
    return "\n".join([header, note, *merged]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("route", type=Path)
    parser.add_argument("--setting", required=True)
    parser.add_argument("--values", nargs=2, required=True)
    parser.add_argument("--every", type=int, default=300)
    parser.add_argument("--from", dest="start", type=int, default=600)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    text = make(arguments.route.read_text(encoding="utf-8"), arguments.setting,
                tuple(arguments.values), arguments.every, arguments.start)
    arguments.output.write_text(text, encoding="utf-8")
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
