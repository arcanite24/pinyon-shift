#!/usr/bin/env python3
"""Rank the guest call chains above the title's D3D draws, from a perf profile.

Reads folded stacks (one `frame;frame;... count` line per stack, as
`perf script | stackcollapse-perf.pl` or the Deck's fold.py write them) from a
frame-pointer build (preset linux-amd64-v3-fp), finds in each stack the first
D3D draw entry or the display-list executor, and counts the guest functions
above it, nearest first, weighted by samples. The census entry points are the
ones `src/native_renderer/d3d_census.cpp` hooks.

The guest stack in memory can't give these chains: the generated code keeps
saved registers and return addresses in host locals, so the guest frames'
return-address slots are never written (FULL_FRAME_RENDERER.md, FR-3). Guest
functions that Clang inlined into their caller don't appear.

    python tools/re/draw-chains.py cg.folded --depth 6 --top 10
"""
from __future__ import annotations

import argparse
import collections
import re

ENTRIES = {
    "82416380": "draw0", "82415F68": "draw1", "8240DC70": "draw2", "82408B70": "draw3",
    "82460998": "draw4", "8240F4D8": "draw5", "829F7C70": "draw6", "824610C0": "draw7",
    "823FA0A8": "draw8", "82416A00": "list-exec",
}
GUEST = re.compile(r"(?:__imp__)?sub_([0-9A-F]{8})$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folded", help="folded stacks of a frame-pointer build")
    parser.add_argument("--depth", type=int, default=6, help="guest callers per chain")
    parser.add_argument("--top", type=int, default=10, help="chains listed per entry")
    args = parser.parse_args()

    chains: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    totals: collections.Counter = collections.Counter()
    with open(args.folded, encoding="utf-8", errors="replace") as stacks:
        for line in stacks:
            stack, _, count = line.rstrip("\n").rpartition(" ")
            if not count.isdigit():
                continue
            frames = [m.group(1) for f in stack.split(";") if (m := GUEST.match(f))]
            for i, frame in enumerate(frames):
                if frame in ENTRIES:
                    callers = frames[max(0, i - args.depth):i][::-1]
                    chains[ENTRIES[frame]]["<".join(callers)] += int(count)
                    totals[ENTRIES[frame]] += int(count)
                    break
    for entry, total in totals.most_common():
        print(f"== {entry} (weight {total})")
        for chain, count in chains[entry].most_common(args.top):
            print(f"  {100 * count / total:5.1f}% {chain}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
