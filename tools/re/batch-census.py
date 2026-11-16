#!/usr/bin/env python3
"""How far a renderer that owns the scene could merge its draws (FR-3).

Reads the ordered frame census (ShiftGlue `fh1_frame_census_ordered`, schema
`pinyon-shift.fh1-frame-order.v2`): every host draw of a frame, in order, with
its rendering instance, pipeline, a hash of the texture and of the vertex fetch
constants its shaders read, its guest index base and RB_BLENDCONTROL0.

For three keys, from loosest to strictest:

  pipe          the pipeline only (merging needs per-draw textures, vertex
                fetch and constants from tables: bindless);
  pipe+tex      pipeline and textures (per-draw vertex fetch and constants);
  pipe+tex+vtx  pipeline, textures and vertex fetch (per-draw constants only);

it counts the batches a frame would need, where opaque draws may be
reordered within their rendering instance (distinct keys) and blended draws
keep their order (runs of equal keys). It also counts the draws whose
pipeline, textures, vertex fetch and index base equal the same draw a frame
earlier (same rendering instance offset and ordinal), from the census's
consecutive frame pairs (`fh1_frame_census_ordered_every`).

    python -I tools/re/batch-census.py skip0.jsonl skip7.jsonl --from-frame 4700
"""
from __future__ import annotations

import argparse
import json
import statistics

KEYS = ("pipe", "pipe+tex", "pipe+tex+vtx")


def opaque(blend: int) -> bool:
    # Colour and alpha: source one, add, destination zero.
    return (blend & 0x1FFF1FFF) == 0x00010001


def key(draw: list, level: int) -> tuple:
    return tuple(draw[1:2 + level])


def frame_stats(draws: list) -> dict:
    passes: dict[int, list] = {}
    for draw in draws:
        passes.setdefault(draw[0], []).append(draw)
    out = {"draws": len(draws), "opaque": sum(opaque(d[5]) for d in draws), "passes": len(passes)}
    for level, name in enumerate(KEYS):
        batches = 0
        for items in passes.values():
            batches += len({key(d, level) for d in items if opaque(d[5])})
            previous = None
            for d in items:
                if opaque(d[5]):
                    continue
                k = key(d, level)
                if k != previous:
                    batches += 1
                previous = k
        out[name] = batches
    return out


def repeats(previous: list, current: list) -> int:
    def index(draws):
        first = draws[0][0] if draws else 0
        ordinal: dict[int, int] = {}
        table = {}
        for d in draws:
            n = ordinal.get(d[0], 0)
            ordinal[d[0]] = n + 1
            table[(d[0] - first, n)] = tuple(d[1:5])
        return table
    a, b = index(previous), index(current)
    return sum(1 for k, v in b.items() if a.get(k) == v)


def load(path: str, from_frame: int) -> dict:
    frames = {}
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            record = json.loads(line)
            if record.get("overflow") or record["output_frame"] < from_frame:
                continue
            frames[record["output_frame"]] = record["draws"]
    stats = [frame_stats(d) for d in frames.values()]
    same = [repeats(frames[f - 1], frames[f]) / max(1, len(frames[f]))
            for f in frames if f - 1 in frames]
    result = {name: statistics.mean(s[name] for s in stats) for name in stats[0]}
    result["frames"] = len(stats)
    result["repeat_share"] = statistics.mean(same) if same else float("nan")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("census", nargs="+", help="ordered census JSON Lines, one per run")
    parser.add_argument("--from-frame", type=int, default=0, help="first output frame counted")
    args = parser.parse_args()
    results = [load(path, args.from_frame) for path in args.census]
    names = ["frames", "draws", "opaque", "passes", *KEYS, "repeat_share"]
    print(f"{'':14}" + "".join(f"{p[-28:]:>30}" for p in args.census))
    for name in names:
        print(f"{name:14}" + "".join(f"{r[name]:>30.2f}" for r in results))
    if len(results) == 2:
        a, b = results
        print("difference (first minus second): what the second run's skip removed")
        for name in ("draws", "opaque", *KEYS):
            print(f"{name:14}{a[name] - b[name]:>30.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
