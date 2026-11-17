#!/usr/bin/env python3
"""How far a renderer that owns the scene could merge its draws (FR-3).

Reads the ordered frame census (ShiftGlue `fh1_frame_census_ordered`, schema
`pinyon-shift.fh1-frame-order.v2` or `v3`): every host draw of a frame, in
order, with its rendering instance, pipeline, a hash of the texture and of the
vertex fetch constants its shaders read, its guest index base and
RB_BLENDCONTROL0; v3 adds the innermost indirect buffer the draw came from and
a hash of its dynamic state (viewport, scissors, window offset, depth bias,
stencil reference, face mode).

For each key, from loosest to strictest:

  pipe          the pipeline only (merging needs per-draw textures, vertex
                fetch and constants from tables: bindless);
  pipe+tex      pipeline and textures (per-draw vertex fetch and constants);
  pipe+tex+vtx  pipeline, textures and vertex fetch (per-draw constants only);
  +dyn          (v3) any of those that also shares the dynamic state, which
                a merged draw can't vary per draw;

it counts the batches a frame would need, where opaque draws may be
reordered within their rendering instance (distinct keys) and blended draws
keep their order (runs of equal keys). `repeat` is the share of draws whose
pipeline, textures, vertex fetch and index base also occur in the previous
frame (a multiset match: the order changes from frame to frame), from the
census's consecutive frame pairs (`fh1_frame_census_ordered_every`).

With `--ab-start` (an in-run A/B route that sets the skip on every second
`--ab-window` frames from that frame, as `tools/make-ab-route.py` writes),
the owned set is the draws of indirect buffers that run on the skip-off side
and never on the skip-on side, and the counts cover only those draws, on the
skip-off side, in the same scene.

    python -I tools/re/batch-census.py b0.jsonl b7.jsonl --from-frame 4700
    python -I tools/re/batch-census.py sw1.jsonl --ab-start 4600 --ab-window 240
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics

KEYS = ("pipe", "pipe+tex", "pipe+tex+vtx")


def opaque(blend: int) -> bool:
    # Colour and alpha: source one, add, destination zero.
    return (blend & 0x1FFF1FFF) == 0x00010001


def key(draw: list, level: int, dynamic: bool) -> tuple:
    k = tuple(draw[1:2 + level])
    return k + (draw[7],) if dynamic else k


def batches(passes: dict, level: int, dynamic: bool) -> int:
    count = 0
    for items in passes.values():
        count += len({key(d, level, dynamic) for d in items if opaque(d[5])})
        previous = None
        for d in items:
            if opaque(d[5]):
                continue
            k = key(d, level, dynamic)
            if k != previous:
                count += 1
            previous = k
    return count


def frame_stats(draws: list, v3: bool) -> dict:
    passes: dict[int, list] = {}
    for draw in draws:
        passes.setdefault(draw[0], []).append(draw)
    out = {"draws": len(draws), "opaque": sum(opaque(d[5]) for d in draws), "passes": len(passes)}
    for level, name in enumerate(KEYS):
        out[name] = batches(passes, level, False)
        if v3:
            out[name + "+dyn"] = batches(passes, level, True)
    return out


def repeat(previous: list, current: list) -> float:
    a = collections.Counter(tuple(d[1:5]) for d in previous)
    b = collections.Counter(tuple(d[1:5]) for d in current)
    return sum((a & b).values()) / max(1, len(current))


def read(path: str) -> dict:
    frames = {}
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            record = json.loads(line)
            if not record.get("overflow"):
                frames[record["output_frame"]] = record["draws"]
    return frames


def summarize(frames: dict, keep=lambda d: True) -> dict:
    v3 = any(len(d) > 6 for draws in frames.values() for d in draws[:1])
    kept = {f: [d for d in draws if keep(d)] for f, draws in frames.items()}
    stats = [frame_stats(d, v3) for d in kept.values() if d]
    if not stats:
        return {}
    result = {name: statistics.mean(s[name] for s in stats) for name in stats[0]}
    result["frames"] = len(stats)
    same = [repeat(kept[f - 1], kept[f]) for f in kept if f - 1 in kept and kept[f]]
    result["repeat"] = statistics.mean(same) if same else float("nan")
    return result


def print_table(labels: list, results: list) -> None:
    names = [n for n in ["frames", "draws", "opaque", "passes", *KEYS,
                         *(k + "+dyn" for k in KEYS), "repeat"] if n in results[0]]
    print(f"{'':16}" + "".join(f"{label[-26:]:>28}" for label in labels))
    for name in names:
        print(f"{name:16}" + "".join(f"{r.get(name, float('nan')):>28.2f}" for r in results))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("census", nargs="+", help="ordered census JSON Lines, one per run")
    parser.add_argument("--from-frame", type=int, default=0, help="first output frame counted")
    parser.add_argument("--ab-start", type=int, help="in-run A/B: first frame of the skip-off side")
    parser.add_argument("--ab-window", type=int, default=240, help="in-run A/B: frames per side")
    args = parser.parse_args()

    if args.ab_start is not None:
        for path in args.census:
            frames = read(path)

            def side(frame: int) -> int:
                return ((frame - args.ab_start) // args.ab_window) % 2

            # Skip the first frames of each window, while the switch settles.
            ab = {f: d for f, d in frames.items()
                  if f >= args.ab_start and (f - args.ab_start) % args.ab_window >= 8}
            off = {f: d for f, d in ab.items() if side(f) == 0}
            on = {f: d for f, d in ab.items() if side(f) == 1}
            lists_on = {d[6] for draws in on.values() for d in draws}
            owned = {d[6] for draws in off.values() for d in draws} - lists_on
            print(f"{path}: {len(off)} skip-off and {len(on)} skip-on frames, "
                  f"{len(owned)} owned buffers")
            print_table(["skip off, all", "skip off, owned", "skip on, all"],
                        [summarize(off), summarize(off, lambda d: d[6] in owned), summarize(on)])
        return 0

    results = [summarize({f: d for f, d in read(p).items() if f >= args.from_frame})
               for p in args.census]
    print_table(args.census, results)
    if len(results) == 2:
        a, b = results
        print("difference (first minus second): what the second run's skip removed, "
              "a lower bound on batches")
        for name in ("draws", "opaque", *KEYS):
            print(f"{name:16}{a[name] - b[name]:>28.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
