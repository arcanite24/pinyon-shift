#!/usr/bin/env python3
"""Build deterministic visual evidence from an exact consumer draw readback."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import zlib
from pathlib import Path


READBACK_SCHEMA = "pinyon-shift.consumer-family-readback.v1"
REPORT_SCHEMA = "pinyon-shift.consumer-family-contribution.v1"
SUPPORTED_FORMATS = {10: 8, 28: 4}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _load_readback(root: Path, phase: str) -> tuple[dict, bytes]:
    phase_root = root / phase
    metadata_path = phase_root / "readback.json"
    payload_path = phase_root / "target.bin"
    _require(metadata_path.is_file(), f"missing {phase} metadata")
    _require(payload_path.is_file(), f"missing {phase} payload")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    _require(metadata.get("schema") == READBACK_SCHEMA, f"invalid {phase} schema")
    _require(metadata.get("phase") == phase, f"invalid {phase} phase")
    safety = metadata.get("safety", {})
    _require(safety.get("output_authority") == "xenos", "Xenos authority missing")
    _require(safety.get("xenos_draw_preserved") is True, "Xenos draw not preserved")
    _require(safety.get("draw_suppression") is False, "draw suppression present")
    _require(safety.get("resolve_suppression") is False, "resolve suppression present")
    _require(safety.get("suppression_allowed") is False, "suppression unexpectedly allowed")
    source = metadata.get("source", {})
    width = source.get("width")
    height = source.get("height")
    row_pitch = source.get("row_pitch")
    dxgi_format = source.get("dxgi_format")
    _require(isinstance(width, int) and width > 0, f"invalid {phase} width")
    _require(isinstance(height, int) and height > 0, f"invalid {phase} height")
    _require(dxgi_format in SUPPORTED_FORMATS, f"unsupported {phase} format")
    bytes_per_pixel = SUPPORTED_FORMATS[dxgi_format]
    _require(source.get("bytes_per_pixel") == bytes_per_pixel, f"invalid {phase} pixel size")
    _require(
        isinstance(row_pitch, int) and row_pitch >= width * bytes_per_pixel,
        f"invalid {phase} row pitch",
    )
    payload = payload_path.read_bytes()
    _require(len(payload) == row_pitch * height, f"invalid {phase} payload size")
    _require(source.get("bytes") == len(payload), f"invalid {phase} byte count")
    return metadata, payload


def _to_rgb(metadata: dict, payload: bytes) -> bytes:
    source = metadata["source"]
    width = source["width"]
    height = source["height"]
    row_pitch = source["row_pitch"]
    dxgi_format = source["dxgi_format"]
    bytes_per_pixel = SUPPORTED_FORMATS[dxgi_format]
    pixels = bytearray(width * height * 3)
    destination = 0
    for y in range(height):
        row = y * row_pitch
        for x in range(width):
            offset = row + x * bytes_per_pixel
            if dxgi_format == 28:
                pixels[destination : destination + 3] = payload[offset : offset + 3]
            else:
                for channel in range(3):
                    value = struct.unpack_from("<e", payload, offset + channel * 2)[0]
                    if not math.isfinite(value):
                        value = 0.0
                    pixels[destination + channel] = round(max(0.0, min(1.0, value)) * 255)
            destination += 3
    return bytes(pixels)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _write_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    _require(len(pixels) == width * height * 3, "invalid PNG pixel count")
    rows = b"".join(
        b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3]
        for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(rows, 9))
        + _png_chunk(b"IEND", b"")
    )


def analyze(root: Path, output: Path) -> dict:
    before_metadata, before_payload = _load_readback(root, "before")
    after_metadata, after_payload = _load_readback(root, "after")
    for field in ("consumer_family", "frame", "draw"):
        _require(
            before_metadata.get(field) == after_metadata.get(field),
            f"readback {field} mismatch",
        )
    for field in (
        "width",
        "height",
        "row_pitch",
        "dxgi_format",
        "bytes_per_pixel",
        "bytes",
    ):
        _require(
            before_metadata["source"].get(field)
            == after_metadata["source"].get(field),
            f"readback source {field} mismatch",
        )
    _require(not output.exists(), f"output already exists: {output}")
    output.mkdir(parents=True)

    width = before_metadata["source"]["width"]
    height = before_metadata["source"]["height"]
    before = _to_rgb(before_metadata, before_payload)
    after = _to_rgb(after_metadata, after_payload)
    differences = bytearray(len(before))
    mask = bytearray(len(before))
    changed_pixels = 0
    left, top, right, bottom = width, height, 0, 0
    squared_sum = 0
    absolute_sum = 0
    maximum = 0
    for pixel in range(width * height):
        changed = False
        for channel in range(3):
            index = pixel * 3 + channel
            delta = abs(after[index] - before[index])
            differences[index] = min(255, delta * 4)
            absolute_sum += delta
            squared_sum += delta * delta
            maximum = max(maximum, delta)
            changed |= delta != 0
        if changed:
            changed_pixels += 1
            x, y = pixel % width, pixel // width
            left, top = min(left, x), min(top, y)
            right, bottom = max(right, x), max(bottom, y)
            mask[pixel * 3 : pixel * 3 + 3] = b"\xff\xff\xff"

    _write_png(output / "before.png", width, height, before)
    _write_png(output / "after.png", width, height, after)
    _write_png(output / "difference-4x.png", width, height, bytes(differences))
    _write_png(output / "changed-mask.png", width, height, bytes(mask))
    channel_count = width * height * 3
    report = {
        "schema": REPORT_SCHEMA,
        "consumer_family": before_metadata["consumer_family"],
        "frame": before_metadata["frame"],
        "draw": before_metadata["draw"],
        "source": {
            **before_metadata["source"],
            "before_sha256": _sha256(root / "before" / "target.bin"),
            "after_sha256": _sha256(root / "after" / "target.bin"),
        },
        "contribution": {
            "changed_pixels": changed_pixels,
            "total_pixels": width * height,
            "changed_fraction": changed_pixels / (width * height),
            "mae_8bit_rgb": absolute_sum / channel_count,
            "rmse_8bit_rgb": math.sqrt(squared_sum / channel_count),
            "maximum_channel_delta": maximum,
            "bounds": (
                {"left": left, "top": top, "right": right, "bottom": bottom}
                if changed_pixels
                else None
            ),
            "semantic_role": "operator_review_required",
        },
        "images": {
            "before": "before.png",
            "after": "after.png",
            "difference_4x": "difference-4x.png",
            "changed_mask": "changed-mask.png",
        },
        "safety": {
            "output_authority": "xenos",
            "xenos_draw_preserved": True,
            "draw_suppression": False,
            "resolve_suppression": False,
            "suppression_allowed": False,
        },
    }
    report_path = output / "consumer-contribution.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("readback_root", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    report = analyze(arguments.readback_root.resolve(), arguments.output.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
