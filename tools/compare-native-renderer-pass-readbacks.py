#!/usr/bin/env python3
"""Compare same-frame native and authoritative Xenos pass readbacks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "pinyon-shift.native-renderer-pass-readback-comparison.v1"
READBACK_SCHEMA = "pinyon-shift.isolated-draw-readback.v1"
BYTES_PER_PIXEL = {10: 8, 28: 4}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _load(root: Path, expected_role: str) -> tuple[dict[str, Any], bytes]:
    metadata_path = root / "readback.json"
    binary_path = root / "isolated.bin"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("schema") != READBACK_SCHEMA:
        raise ValueError(f"{metadata_path}: unsupported readback schema")
    if metadata.get("capture_role") != expected_role:
        raise ValueError(
            f"{metadata_path}: expected capture_role {expected_role!r}"
        )
    safety = metadata.get("safety", {})
    if safety.get("output_authority") != "xenos" or safety.get(
        "suppression_allowed"
    ) is not False:
        raise ValueError(f"{metadata_path}: unsafe readback metadata")
    data = binary_path.read_bytes()
    source = metadata.get("source", {})
    if source.get("bytes") != len(data):
        raise ValueError(f"{binary_path}: byte count does not match metadata")
    return metadata, data


def compare(native_root: Path, xenos_root: Path) -> dict[str, Any]:
    native, native_data = _load(native_root, "native")
    xenos, xenos_data = _load(xenos_root, "xenos")
    for field in ("signature", "frame", "draw"):
        if native.get(field) != xenos.get(field):
            raise ValueError(f"readback {field} values differ")

    native_source = native["source"]
    xenos_source = xenos["source"]
    layout_fields = ("width", "height", "row_pitch", "dxgi_format")
    for field in layout_fields:
        if native_source.get(field) != xenos_source.get(field):
            raise ValueError(f"readback source {field} values differ")

    width = int(native_source["width"])
    height = int(native_source["height"])
    row_pitch = int(native_source["row_pitch"])
    dxgi_format = int(native_source["dxgi_format"])
    bytes_per_pixel = BYTES_PER_PIXEL.get(dxgi_format)
    if bytes_per_pixel is None:
        raise ValueError(f"unsupported DXGI format {dxgi_format}")
    active_row_bytes = width * bytes_per_pixel
    required_bytes = row_pitch * height
    if (
        width <= 0
        or height <= 0
        or active_row_bytes > row_pitch
        or len(native_data) < required_bytes
        or len(xenos_data) < required_bytes
    ):
        raise ValueError("invalid readback layout")

    compared_bytes = 0
    different_bytes = 0
    absolute_error = 0
    maximum_error = 0
    for row in range(height):
        start = row * row_pitch
        end = start + active_row_bytes
        for left, right in zip(
            native_data[start:end], xenos_data[start:end], strict=True
        ):
            error = abs(left - right)
            compared_bytes += 1
            different_bytes += error != 0
            absolute_error += error
            maximum_error = max(maximum_error, error)

    exact = different_bytes == 0
    return {
        "schema": SCHEMA,
        "result": "pass" if exact else "fail",
        "identity": {
            "signature": native["signature"],
            "frame": native["frame"],
            "follower_draw": native["draw"],
            "same_guest_frame": True,
        },
        "layout": {
            "width": width,
            "height": height,
            "row_pitch": row_pitch,
            "active_row_bytes": active_row_bytes,
            "dxgi_format": dxgi_format,
        },
        "metrics": {
            "compared_bytes": compared_bytes,
            "different_bytes": different_bytes,
            "different_byte_ratio": (
                different_bytes / compared_bytes if compared_bytes else 0.0
            ),
            "mean_absolute_byte_error": (
                absolute_error / compared_bytes if compared_bytes else 0.0
            ),
            "maximum_byte_error": maximum_error,
            "exact_active_bytes": exact,
        },
        "artifacts": {
            "native": {
                "root": str(native_root),
                "binary_sha256": _sha256(native_data),
            },
            "xenos": {
                "root": str(xenos_root),
                "binary_sha256": _sha256(xenos_data),
            },
        },
        "safety": {
            "xenos_draw_preserved": True,
            "output_authority": "xenos",
            "suppression_allowed": False,
            "gpu_wait_added": False,
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native_root", type=Path)
    parser.add_argument(
        "--xenos-root",
        type=Path,
        help="defaults to the native root with '.xenos' appended",
    )
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    xenos_root = args.xenos_root or Path(str(args.native_root) + ".xenos")
    report = compare(args.native_root, xenos_root)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["result"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
