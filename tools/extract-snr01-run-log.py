#!/usr/bin/env python3
"""Extract one process's SNR-01 trace from rotating runtime logs."""

import argparse
from datetime import datetime, timezone
from pathlib import Path


def extract(session: Path, output: Path, include_scene: bool = False,
            include_bc3_source: bool = False) -> int:
    started = datetime.strptime(session.name[:16], "%Y%m%dT%H%M%SZ").replace(
        tzinfo=timezone.utc
    ).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    ended = datetime.fromtimestamp(session.stat().st_mtime).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    assert started <= ended, "session ended before it started"
    logs = session.parent
    rotated = sorted(logs.glob("runtime.*.log"),
                     key=lambda path: int(path.name.split(".")[1]), reverse=True)
    paths = rotated + [logs / "runtime.log"]
    markers = ("FH1 SNR01 ", "FH1 SNR02 ", "FH1 clear producer ")
    if include_scene:
        markers += ("FH1 SNR03 ", "FH1 scene binding ")
    if include_bc3_source:
        markers += ("FH1 SNR04 BC3 ", "FH1 SNR04 bound pixel ",
                    "FH1 texture reload attempt ", "FH1 texture invalidated ")
    count = 0
    with output.open("w", encoding="utf-8") as destination:
        for path in paths:
            if not path.is_file():
                continue
            with path.open(encoding="utf-8", errors="replace") as source:
                for line in source:
                    if (line.startswith("[") and started <= line[1:20] <= ended
                            and any(marker in line for marker in markers)):
                        destination.write(line)
                        count += 1
    assert count, "no SNR-01 records found in the session window"
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="process-specific *-pPID.jsonl")
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-scene", action="store_true")
    parser.add_argument("--include-bc3-source", action="store_true")
    args = parser.parse_args()
    print(f"records: {extract(args.session, args.output, args.include_scene,
                               args.include_bc3_source)}")
