#!/usr/bin/env python3
"""Compare same-frame native and authoritative Xenos pass readbacks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


COLOR_SCHEMA = "pinyon-shift.native-renderer-pass-readback-comparison.v1"
DEPTH_SCHEMA = (
    "pinyon-shift.native-renderer-pass-depth-readback-comparison.v1"
)
COLOR_READBACK_SCHEMA = "pinyon-shift.isolated-draw-readback.v1"
DEPTH_READBACK_SCHEMA = "pinyon-shift.isolated-depth-readback.v1"
BYTES_PER_PIXEL = {10: 8, 28: 4}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _load(
    root: Path, expected_role: str, content: str
) -> tuple[dict[str, Any], bytes]:
    metadata_path = root / "readback.json"
    binary_path = root / "isolated.bin"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_schema = (
        COLOR_READBACK_SCHEMA if content == "color" else DEPTH_READBACK_SCHEMA
    )
    if metadata.get("schema") != expected_schema:
        raise ValueError(f"{metadata_path}: unsupported readback schema")
    if metadata.get("capture_role") != expected_role:
        raise ValueError(
            f"{metadata_path}: expected capture_role {expected_role!r}"
        )
    if content == "depth-stencil" and metadata.get("capture_content") != (
        "depth_stencil"
    ):
        raise ValueError(f"{metadata_path}: expected depth_stencil content")
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


def _compare_rows(
    native_data: bytes,
    xenos_data: bytes,
    rows: list[tuple[int, int, int]],
) -> dict[str, int | float | bool]:
    compared_bytes = 0
    different_bytes = 0
    absolute_error = 0
    maximum_error = 0
    for offset, row_pitch, row_size in rows:
        for left, right in zip(
            native_data[offset : offset + row_size],
            xenos_data[offset : offset + row_size],
            strict=True,
        ):
            error = abs(left - right)
            compared_bytes += 1
            different_bytes += error != 0
            absolute_error += error
            maximum_error = max(maximum_error, error)
    exact = different_bytes == 0
    return {
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
    }


def compare(
    native_root: Path, xenos_root: Path, content: str = "color"
) -> dict[str, Any]:
    native, native_data = _load(native_root, "native", content)
    xenos, xenos_data = _load(xenos_root, "xenos", content)
    for field in ("signature", "frame", "draw"):
        if native.get(field) != xenos.get(field):
            raise ValueError(f"readback {field} values differ")

    native_source = native["source"]
    xenos_source = xenos["source"]
    layout_fields = ("width", "height", "dxgi_format")
    if content == "color":
        layout_fields += ("row_pitch",)
    else:
        layout_fields += ("sample_count", "encoding")
    for field in layout_fields:
        if native_source.get(field) != xenos_source.get(field):
            raise ValueError(f"readback source {field} values differ")

    width = int(native_source["width"])
    height = int(native_source["height"])
    dxgi_format = int(native_source["dxgi_format"])
    if width <= 0 or height <= 0:
        raise ValueError("invalid readback dimensions")

    rows: list[tuple[int, int, int]] = []
    if content == "color":
        bytes_per_pixel = BYTES_PER_PIXEL.get(dxgi_format)
        if bytes_per_pixel is None:
            raise ValueError(f"unsupported DXGI format {dxgi_format}")
        row_pitch = int(native_source["row_pitch"])
        active_row_bytes = width * bytes_per_pixel
        required_bytes = row_pitch * height
        if (
            active_row_bytes > row_pitch
            or len(native_data) < required_bytes
            or len(xenos_data) < required_bytes
        ):
            raise ValueError("invalid readback layout")
        rows.extend(
            (row * row_pitch, row_pitch, active_row_bytes)
            for row in range(height)
        )
        layout: dict[str, Any] = {
            "width": width,
            "height": height,
            "row_pitch": row_pitch,
            "active_row_bytes": active_row_bytes,
            "dxgi_format": dxgi_format,
        }
    else:
        sample_count = int(native_source["sample_count"])
        encoding = str(native_source["encoding"])
        if sample_count <= 0:
            raise ValueError("invalid depth sample count")
        if encoding not in (
            "d3d12_texture_planes",
            "depth32_stencil8_sample_tuples",
        ):
            raise ValueError("unsupported depth encoding")
        if encoding == "d3d12_texture_planes" and sample_count != 1:
            raise ValueError("invalid texture-plane sample count")
        if encoding == "depth32_stencil8_sample_tuples" and sample_count <= 1:
            raise ValueError("invalid multisample tuple count")
        native_planes = native_source.get("planes")
        xenos_planes = xenos_source.get("planes")
        if native_planes != xenos_planes or not isinstance(native_planes, list):
            raise ValueError("readback depth plane layouts differ")
        if not 1 <= len(native_planes) <= 2:
            raise ValueError("invalid depth plane count")
        if encoding == "depth32_stencil8_sample_tuples" and (
            len(native_planes) != 1
            or int(native_planes[0].get("offset", -1)) != 0
            or int(native_planes[0].get("row_size", -1))
            != width * sample_count * 8
            or int(native_planes[0].get("row_count", -1)) != height
        ):
            raise ValueError("invalid multisample depth tuple layout")
        for expected_index, plane in enumerate(native_planes):
            if plane.get("index") != expected_index:
                raise ValueError("invalid depth plane index")
            offset = int(plane["offset"])
            row_pitch = int(plane["row_pitch"])
            row_size = int(plane["row_size"])
            row_count = int(plane["row_count"])
            end = offset + (row_count - 1) * row_pitch + row_size
            if (
                offset < 0
                or row_count <= 0
                or row_size <= 0
                or row_size > row_pitch
                or end > len(native_data)
                or end > len(xenos_data)
            ):
                raise ValueError("invalid depth plane layout")
            rows.extend(
                (offset + row * row_pitch, row_pitch, row_size)
                for row in range(row_count)
            )
        layout = {
            "width": width,
            "height": height,
            "dxgi_format": dxgi_format,
            "sample_count": sample_count,
            "encoding": encoding,
            "planes": native_planes,
        }

    metrics = _compare_rows(native_data, xenos_data, rows)
    exact = bool(metrics["exact_active_bytes"])
    return {
        "schema": COLOR_SCHEMA if content == "color" else DEPTH_SCHEMA,
        "result": "pass" if exact else "fail",
        "scope": {"content": content},
        "identity": {
            "signature": native["signature"],
            "frame": native["frame"],
            "follower_draw": native["draw"],
            "same_guest_frame": True,
        },
        "layout": layout,
        "metrics": metrics,
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
    parser.add_argument(
        "--content", choices=("color", "depth-stencil"), default="color"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    xenos_root = args.xenos_root or Path(str(args.native_root) + ".xenos")
    report = compare(args.native_root, xenos_root, args.content)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["result"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
