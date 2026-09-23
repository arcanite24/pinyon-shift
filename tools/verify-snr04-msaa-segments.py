#!/usr/bin/env python3
"""Verify that split four-sample vegetation replay equals one full segment."""

import argparse
import filecmp
import hashlib
import json
from pathlib import Path


FILES = {
    "coverage.u8": 1280 * 720,
    "identity.u16x4": 1280 * 720 * 4 * 2,
    "depth.f32x4": 1280 * 720 * 4 * 4,
    "depth.f32": 1280 * 720 * 4,
}


def verify(single, segments):
    assert len(segments) >= 2
    summaries = [json.loads((directory / "summary.json").read_text())
                 for directory in [single, *segments]]
    assert all(row["schema"] == "pinyon-shift.snr04-segment.v1" for row in summaries)
    full = summaries[0]
    assert full["first_id"] == summaries[1]["first_id"]
    assert full["first_sequence"] == summaries[1]["first_sequence"]
    assert full["last_sequence"] == summaries[-1]["last_sequence"]
    assert full["draws"] == sum(row["draws"] for row in summaries[1:])
    assert all(row["source_frame"] == full["source_frame"] and
               row["fixture_sha256"] == full["fixture_sha256"]
               for row in summaries)
    assert all(left["last_sequence"] < right["first_sequence"] and
               left["first_id"] + left["draws"] == right["first_id"]
               for left, right in zip(summaries[1:], summaries[2:]))
    result = {}
    for name, size in FILES.items():
        first, last = single / name, segments[-1] / name
        assert first.stat().st_size == last.stat().st_size == size
        assert filecmp.cmp(first, last, shallow=False), name
        result[name] = hashlib.sha256(first.read_bytes()).hexdigest()
    for directory in (single, segments[-1]):
        image = (directory / "identity.ppm").read_bytes()
        assert image.startswith(b"P6\n1280 720\n255\n")
    assert filecmp.cmp(single / "identity.ppm",
                       segments[-1] / "identity.ppm", shallow=False)
    return {"source_frame": full["source_frame"], "draws": full["draws"],
            "segments": len(segments), "sha256": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("single", type=Path)
    parser.add_argument("segments", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps(verify(args.single, args.segments), sort_keys=True))
