#!/usr/bin/env python3
"""Replay one vegetation draw against its captured four-sample prior depth."""

from array import array
import argparse
import json
from pathlib import Path
import struct
import subprocess


WIDTH, HEIGHT = 1280, 720


def reference_depths(probe_path, rows):
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    assert (probe["stage"], probe["format"], probe["width"], probe["samples"]) == (
        "done", "D32S8_TYPELESS", WIDTH, 4)
    assert 0 < rows <= min(probe["height"], HEIGHT)
    before, after = [], []
    for sample in range(4):
        suffix = f"-s{sample}" if sample else ""
        paths = [probe_path.with_name(f"{probe_path.stem}-{state}{suffix}.depth")
                 for state in ("before", "after")]
        values = []
        for path in paths:
            data = path.read_bytes()
            assert len(data) == WIDTH * probe["height"] * 8
            values.append(array("f", (depth for depth, _ in
                                      struct.iter_unpack("<fI", data[:WIDTH * rows * 8]))))
        before.append(values[0])
        after.append(values[1])
        assert sum(a != b for a, b in zip(*values)) == (
            probe["sample_details"][sample]["changed_depth_samples"])
    return probe, before, after


def check(args):
    output = args.output.resolve()
    assert ".local" in output.parts, "diagnostic output must stay under .local"
    probe, reference_before, reference_after = reference_depths(args.probe, args.rows)
    assert 0 <= args.tile_y and args.tile_y + args.rows <= HEIGHT
    prior, result = output / "compat-before", output / "private-after"
    prior.mkdir(parents=True, exist_ok=True)
    result.mkdir(parents=True, exist_ok=True)
    (prior / "identity.u16x4").write_bytes(bytes(WIDTH * HEIGHT * 4 * 2))
    depths = array("f", [0]) * (WIDTH * HEIGHT * 4)
    for pixel in range(WIDTH * args.rows):
        for sample in range(4):
            depths[(pixel + WIDTH * args.tile_y) * 4 + sample] = (
                reference_before[sample][pixel])
    (prior / "depth.f32x4").write_bytes(depths.tobytes())
    command = [str(args.executable.resolve()), str(args.fixture.resolve()),
               str(args.shader.resolve()), str(result), "--msaa4", "--segment",
               str(args.sequence), str(args.sequence), str(args.draw_id), "1",
               str(prior)]
    if args.alpha_bc3:
        command += ["--alpha-bc3", str(args.alpha_bc3.resolve())]
    run = subprocess.run(command, capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stderr.strip())
    private_after = array("f")
    private_after.frombytes((result / "depth.f32x4").read_bytes())
    assert len(private_after) == len(depths)
    summary = json.loads((result / "summary.json").read_text(encoding="utf-8"))
    assert (summary["source_frame"], summary["draws"], summary["first_id"]) == (
        args.frame, 1, args.draw_id)
    assert summary.get("alpha_probe", False) == bool(args.alpha_bc3)
    totals = [dict(reference=0, private=0, overlap=0, nonexact_depth=0)
              for _ in range(4)]
    errors = [[] for _ in range(4)]
    any_reference = any_private = any_overlap = 0
    for pixel in range(WIDTH * args.rows):
        reference_mask = private_mask = 0
        for sample in range(4):
            private_index = (pixel + WIDTH * args.tile_y) * 4 + sample
            ref_changed = (reference_before[sample][pixel] !=
                           reference_after[sample][pixel])
            private_changed = depths[private_index] != private_after[private_index]
            reference_mask |= ref_changed << sample
            private_mask |= private_changed << sample
            count = totals[sample]
            count["reference"] += ref_changed
            count["private"] += private_changed
            count["overlap"] += ref_changed and private_changed
            if ref_changed != private_changed:
                key = "first_reference_only" if ref_changed else "first_private_only"
                count.setdefault(key, [pixel % WIDTH, pixel // WIDTH + args.tile_y])
            if ref_changed and private_changed:
                error = abs(reference_after[sample][pixel] -
                            private_after[private_index])
                errors[sample].append(error)
                if error:
                    count["nonexact_depth"] += 1
                    count.setdefault("first_nonexact_depth",
                                     [pixel % WIDTH, pixel // WIDTH + args.tile_y])
        any_reference += bool(reference_mask)
        any_private += bool(private_mask)
        any_overlap += bool(reference_mask) and bool(private_mask)
    assert any_reference == probe["coverage"]["pixels"]
    for count, values in zip(totals, errors):
        values.sort()
        count["private_only"] = count["private"] - count["overlap"]
        count["reference_only"] = count["reference"] - count["overlap"]
        count["depth_p50"] = values[len(values) // 2] if values else None
        count["depth_p90"] = values[int(len(values) * .9)] if values else None
        count["depth_max"] = values[-1] if values else None
    report = {"event": probe["event"], "source_frame": args.frame,
              "draw_id": args.draw_id, "rows": args.rows,
              "tile_y": args.tile_y,
              "reference_any": any_reference, "private_any": any_private,
              "overlap_any": any_overlap,
              "any_iou": any_overlap / (any_reference + any_private - any_overlap)
              if any_reference + any_private - any_overlap else 1.0,
              "alpha_bc3": bool(args.alpha_bc3), "samples": totals}
    (output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n",
                                            encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("probe", "fixture", "shader", "executable", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--draw-id", type=int, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--tile-y", type=int, default=0)
    parser.add_argument("--alpha-bc3", type=Path)
    print(json.dumps(check(parser.parse_args()), sort_keys=True))
