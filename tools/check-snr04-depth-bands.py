#!/usr/bin/env python3
"""Compare sample-0 RenderDoc depth tiles with a private 1280x720 replay."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
import struct


def measure(reference, private):
    ref_covered = sum(value != 0 for value in reference)
    private_covered = sum(value != 0 for value in private)
    errors = sorted(abs(a - b) for a, b in zip(reference, private)
                    if a != 0 and b != 0)
    overlap = len(errors)
    union = ref_covered + private_covered - overlap
    return {"reference_covered": ref_covered,
            "private_covered": private_covered,
            "overlap": overlap,
            "coverage_iou": overlap / union if union else 1.0,
            "median_abs_depth_error": statistics.median(errors) if errors else None,
            "p90_abs_depth_error": errors[int(.9 * len(errors))] if errors else None,
            "within_1e-4": sum(error < 1e-4 for error in errors)}


def tally(families, draws, family, identity, reference, private):
    large = abs(reference - private) >= .005
    nearer = large and private > reference
    for counts in (families[family], draws[identity]):
        counts[0] += 1
        counts[1] += large
        counts[2] += nearer


def check(report_path, private_path, order_path=None, color_paths=None):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["stage"] == "done" and len(report["rows"]) == 3
    assert (order_path is None) == (color_paths is None)
    private = private_path.read_bytes()
    assert len(private) == 1280 * 720 * 4
    private_values = [value[0] for value in struct.iter_unpack("<f", private)]
    order = json.loads(order_path.read_text(encoding="utf-8"))["order"] if order_path else None
    color_buffers = [path.read_bytes() for path in color_paths] if color_paths else None
    if color_buffers is not None:
        assert len(color_buffers) == 3 and len(order) < 65536
        assert all(len(colors) == len(private) for colors in color_buffers)
    families = defaultdict(lambda: [0, 0, 0])
    draws = defaultdict(lambda: [0, 0, 0])
    reference_all, private_all, bands = [], [], []
    offset = 0
    for row in report["rows"]:
        width, height = row["depth"]["size"]
        x, y, scissor_width, band_height = row["scissor"]
        assert (width, height, x, y, scissor_width) == (1280, 512, 0, 0, 1280)
        assert row["depth"]["format"] == "D32S8_TYPELESS"
        assert row["depth_output"] and offset + band_height <= 720
        data = (report_path.parent / row["depth_output"]["file"]).read_bytes()
        assert len(data) == width * height * 8
        reference = [value[0] for value in struct.iter_unpack("<fI", data[:width * band_height * 8])]
        native = private_values[offset * width:(offset + band_height) * width]
        if color_buffers is not None:
            colors = color_buffers[len(bands)]
            for pixel, (a, b) in enumerate(zip(reference, native)):
                if a == 0 or b == 0:
                    continue
                color = (offset * width + pixel) * 4
                identity = colors[color] | colors[color + 1] << 8
                assert 1 <= identity <= len(order)
                tally(families, draws, order[identity - 1]["family"], identity, a, b)
        bands.append({"event": row["event"], "private_row": offset,
                      "height": band_height, **measure(reference, native)})
        reference_all.extend(reference)
        private_all.extend(native)
        offset += band_height
    assert offset == 720
    result = {"scope": "sample-0 target-space diagnostic; not pixel/depth parity",
              "bands": bands, "total": measure(reference_all, private_all)}
    if color_buffers is not None:
        result["large_error_threshold"] = .005
        result["families"] = [dict(family=family, pixels=counts[0],
                                   large_errors=counts[1], large_private_nearer=counts[2])
                              for family, counts in sorted(families.items(),
                                                           key=lambda row: -row[1][1])]
        result["top_draws"] = [dict(id=identity,
                                    family=order[identity - 1]["family"],
                                    pixels=counts[0], large_errors=counts[1],
                                    large_private_nearer=counts[2])
                                for identity, counts in sorted(draws.items(),
                                                               key=lambda row: -row[1][1])[:8]]
    return result


def self_test():
    result = measure([0, 1, 2, 3], [0, 1, 2, 0])
    assert result["reference_covered"] == 3
    assert result["private_covered"] == 2
    assert result["overlap"] == 2
    assert result["coverage_iou"] == 2 / 3
    assert result["median_abs_depth_error"] == 0
    families = defaultdict(lambda: [0, 0, 0])
    draws = defaultdict(lambda: [0, 0, 0])
    tally(families, draws, "vegetation", 7, .01, .02)
    assert families["vegetation"] == draws[7] == [1, 1, 1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, nargs="?")
    parser.add_argument("private_depth", type=Path, nargs="?")
    parser.add_argument("--order", type=Path)
    parser.add_argument("--band-colors", type=Path, nargs=3)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        assert args.report and args.private_depth
        print(json.dumps(check(args.report, args.private_depth,
                               args.order, args.band_colors), indent=2))
