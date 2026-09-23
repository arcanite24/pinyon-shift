#!/usr/bin/env python3
"""Compare sample-0 RenderDoc depth tiles with a private 1280x720 replay."""

import argparse
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


def check(report_path, private_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["stage"] == "done" and len(report["rows"]) == 3
    private = private_path.read_bytes()
    assert len(private) == 1280 * 720 * 4
    private_values = [value[0] for value in struct.iter_unpack("<f", private)]
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
        bands.append({"event": row["event"], "private_row": offset,
                      "height": band_height, **measure(reference, native)})
        reference_all.extend(reference)
        private_all.extend(native)
        offset += band_height
    assert offset == 720
    return {"scope": "sample-0 target-space diagnostic; not pixel/depth parity",
            "bands": bands, "total": measure(reference_all, private_all)}


def self_test():
    result = measure([0, 1, 2, 3], [0, 1, 2, 0])
    assert result["reference_covered"] == 3
    assert result["private_covered"] == 2
    assert result["overlap"] == 2
    assert result["coverage_iou"] == 2 / 3
    assert result["median_abs_depth_error"] == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, nargs="?")
    parser.add_argument("private_depth", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        assert args.report and args.private_depth
        print(json.dumps(check(args.report, args.private_depth), indent=2))
