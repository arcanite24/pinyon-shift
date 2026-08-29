#!/usr/bin/env python3
"""Build deterministic evidence from exact consumer attachment readbacks."""

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
CORPUS_SCHEMA = "pinyon-shift.consumer-family-contribution-corpus.v1"
SUPPORTED_COLOR_FORMATS = {10: 8, 28: 4}
DEPTH_ENCODINGS = {
    "depth32_stencil8_sample_tuples",
    "d3d12_planar_depth_stencil",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _attachment_root(root: Path, attachment: str, phase: str) -> Path:
    return root / phase if attachment == "color" else root / "depth" / phase


def _validate_safety(metadata: dict) -> None:
    safety = metadata.get("safety", {})
    _require(safety.get("output_authority") == "xenos", "Xenos authority missing")
    _require(safety.get("xenos_draw_preserved") is True, "Xenos draw not preserved")
    _require(safety.get("draw_suppression") is False, "draw suppression present")
    _require(safety.get("resolve_suppression") is False, "resolve suppression present")
    _require(safety.get("suppression_allowed") is False, "suppression unexpectedly allowed")


def _load_readback(root: Path, phase: str, attachment: str) -> tuple[dict, bytes]:
    phase_root = _attachment_root(root, attachment, phase)
    metadata_path = phase_root / "readback.json"
    payload_path = phase_root / "target.bin"
    _require(metadata_path.is_file(), f"missing {attachment} {phase} metadata")
    _require(payload_path.is_file(), f"missing {attachment} {phase} payload")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    _require(metadata.get("schema") == READBACK_SCHEMA, f"invalid {phase} schema")
    _require(metadata.get("phase") == phase, f"invalid {phase} phase")
    _require(metadata.get("attachment", attachment) == attachment, "attachment mismatch")
    _validate_safety(metadata)
    source = metadata.get("source", {})
    width = source.get("width")
    height = source.get("height")
    _require(isinstance(width, int) and width > 0, f"invalid {phase} width")
    _require(isinstance(height, int) and height > 0, f"invalid {phase} height")
    payload = payload_path.read_bytes()
    _require(source.get("bytes") == len(payload), f"invalid {phase} byte count")

    if attachment == "color":
        dxgi_format = source.get("dxgi_format")
        row_pitch = source.get("row_pitch")
        _require(dxgi_format in SUPPORTED_COLOR_FORMATS, f"unsupported {phase} format")
        bytes_per_pixel = SUPPORTED_COLOR_FORMATS[dxgi_format]
        _require(source.get("bytes_per_pixel") == bytes_per_pixel, f"invalid {phase} pixel size")
        _require(source.get("sample_count", 1) == 1, "multisampled color is unsupported")
        source_sample_count = source.get("source_sample_count", 1)
        _require(
            isinstance(source_sample_count, int) and source_sample_count > 0,
            "invalid color source sample count",
        )
        _require(
            isinstance(row_pitch, int) and row_pitch >= width * bytes_per_pixel,
            f"invalid {phase} row pitch",
        )
        _require(len(payload) == row_pitch * height, f"invalid {phase} payload size")
    else:
        encoding = source.get("encoding")
        sample_count = source.get("sample_count")
        plane_count = source.get("plane_count")
        planes = source.get("planes")
        _require(encoding in DEPTH_ENCODINGS, f"unsupported {phase} depth encoding")
        _require(isinstance(sample_count, int) and sample_count > 0, "invalid depth sample count")
        _require(isinstance(plane_count, int) and 0 < plane_count <= 2, "invalid depth plane count")
        _require(isinstance(planes, list) and len(planes) == plane_count, "invalid depth planes")
        for plane in planes:
            offset = plane.get("offset")
            row_pitch = plane.get("row_pitch")
            row_size = plane.get("row_size")
            row_count = plane.get("row_count")
            _require(
                all(isinstance(value, int) for value in (offset, row_pitch, row_size, row_count))
                and offset >= 0
                and row_pitch >= row_size > 0
                and row_count > 0
                and offset + row_pitch * (row_count - 1) + row_size <= len(payload),
                "invalid depth plane layout",
            )
        if encoding == "depth32_stencil8_sample_tuples":
            plane = planes[0]
            _require(sample_count > 1 and plane_count == 1, "invalid tuple depth topology")
            _require(plane["row_size"] == width * sample_count * 8, "invalid tuple depth row size")
            _require(plane["row_count"] == height, "invalid tuple depth row count")
        else:
            _require(sample_count == 1, "planar depth must be single-sampled")
    return metadata, payload


def _validate_pair(before: dict, after: dict) -> None:
    for field in ("consumer_family", "frame", "draw", "sample", "attachment"):
        _require(before.get(field) == after.get(field), f"readback {field} mismatch")
    for field in (
        "width",
        "height",
        "row_pitch",
        "dxgi_format",
        "bytes_per_pixel",
        "sample_count",
        "source_sample_count",
        "plane_count",
        "planes",
        "encoding",
        "bytes",
    ):
        _require(
            before["source"].get(field) == after["source"].get(field),
            f"readback source {field} mismatch",
        )


def _to_rgb(metadata: dict, payload: bytes) -> bytes:
    source = metadata["source"]
    width, height = source["width"], source["height"]
    row_pitch = source["row_pitch"]
    dxgi_format = source["dxgi_format"]
    bytes_per_pixel = SUPPORTED_COLOR_FORMATS[dxgi_format]
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
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _write_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    _require(len(pixels) == width * height * 3, "invalid PNG pixel count")
    rows = b"".join(b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(rows, 9)) + _png_chunk(b"IEND", b""))


def _compare_color(metadata: dict, before_payload: bytes, after_payload: bytes, output: Path) -> dict:
    width, height = metadata["source"]["width"], metadata["source"]["height"]
    before, after = _to_rgb(metadata, before_payload), _to_rgb(metadata, after_payload)
    differences, mask = bytearray(len(before)), bytearray(len(before))
    changed_pixels = absolute_sum = squared_sum = maximum = 0
    left, top, right, bottom = width, height, 0, 0
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
            left, top, right, bottom = min(left, x), min(top, y), max(right, x), max(bottom, y)
            mask[pixel * 3 : pixel * 3 + 3] = b"\xff\xff\xff"
    _write_png(output / "before.png", width, height, before)
    _write_png(output / "after.png", width, height, after)
    _write_png(output / "difference-4x.png", width, height, bytes(differences))
    _write_png(output / "changed-mask.png", width, height, bytes(mask))
    channels = width * height * 3
    return {
        "changed_pixels": changed_pixels,
        "total_pixels": width * height,
        "changed_fraction": changed_pixels / (width * height),
        "mae_8bit_rgb": absolute_sum / channels,
        "rmse_8bit_rgb": math.sqrt(squared_sum / channels),
        "maximum_channel_delta": maximum,
        "bounds": {"left": left, "top": top, "right": right, "bottom": bottom} if changed_pixels else None,
        "semantic_role": "operator_review_required",
    }


def _active_plane_bytes(metadata: dict, payload: bytes) -> bytes:
    active = bytearray()
    for plane in metadata["source"]["planes"]:
        for row in range(plane["row_count"]):
            start = plane["offset"] + row * plane["row_pitch"]
            active += payload[start : start + plane["row_size"]]
    return bytes(active)


def _depth_tuple_visuals(metadata: dict, before: bytes, after: bytes, output: Path) -> dict:
    source = metadata["source"]
    width, height, samples = source["width"], source["height"], source["sample_count"]
    plane = source["planes"][0]
    before_image, after_image = bytearray(width * height * 3), bytearray(width * height * 3)
    mask = bytearray(width * height * 3)
    changed_pixels = changed_samples = depth_changes = stencil_changes = 0
    for y in range(height):
        row = plane["offset"] + y * plane["row_pitch"]
        for x in range(width):
            pixel_changed = False
            for sample in range(samples):
                offset = row + x * samples * 8 + sample * 8
                before_tuple = before[offset : offset + 8]
                after_tuple = after[offset : offset + 8]
                if before_tuple != after_tuple:
                    changed_samples += 1
                    pixel_changed = True
                    depth_changes += before_tuple[:4] != after_tuple[:4]
                    stencil_changes += before_tuple[4:8] != after_tuple[4:8]
            for payload, image in ((before, before_image), (after, after_image)):
                depth = struct.unpack_from("<f", payload, row + x * samples * 8)[0]
                if not math.isfinite(depth):
                    depth = 0.0
                value = round(max(0.0, min(1.0, depth)) * 255)
                image[(y * width + x) * 3 : (y * width + x + 1) * 3] = bytes((value, value, value))
            if pixel_changed:
                changed_pixels += 1
                mask[(y * width + x) * 3 : (y * width + x + 1) * 3] = b"\xff\xff\xff"
    _write_png(output / "depth-before.png", width, height, bytes(before_image))
    _write_png(output / "depth-after.png", width, height, bytes(after_image))
    _write_png(output / "depth-changed-mask.png", width, height, bytes(mask))
    return {
        "encoding": source["encoding"],
        "changed_pixels": changed_pixels,
        "total_pixels": width * height,
        "changed_samples": changed_samples,
        "total_samples": width * height * samples,
        "depth_tuple_changes": depth_changes,
        "stencil_tuple_changes": stencil_changes,
        "semantic_role": "operator_review_required",
        "images": {"before": "depth-before.png", "after": "depth-after.png", "changed_mask": "depth-changed-mask.png"},
    }


def _compare_depth(metadata: dict, before: bytes, after: bytes, output: Path) -> dict:
    if metadata["source"]["encoding"] == "depth32_stencil8_sample_tuples":
        return _depth_tuple_visuals(metadata, before, after, output)
    before_active, after_active = _active_plane_bytes(metadata, before), _active_plane_bytes(metadata, after)
    changed = sum(left != right for left, right in zip(before_active, after_active))
    return {
        "encoding": metadata["source"]["encoding"],
        "active_bytes": len(before_active),
        "changed_active_bytes": changed,
        "exact_match": changed == 0,
        "visual_decode": "unsupported_planar_layout",
        "semantic_role": "operator_review_required",
    }


def _analyze_sample(root: Path, output: Path) -> dict:
    before_metadata, before_payload = _load_readback(root, "before", "color")
    after_metadata, after_payload = _load_readback(root, "after", "color")
    _validate_pair(before_metadata, after_metadata)
    _require(not output.exists(), f"output already exists: {output}")
    output.mkdir(parents=True)
    color = _compare_color(before_metadata, before_payload, after_payload, output)
    depth_before_exists = (root / "depth" / "before" / "readback.json").is_file()
    depth_after_exists = (root / "depth" / "after" / "readback.json").is_file()
    _require(depth_before_exists == depth_after_exists, "incomplete depth readback pair")
    depth = None
    if depth_before_exists:
        depth_before_metadata, depth_before_payload = _load_readback(root, "before", "depth_stencil")
        depth_after_metadata, depth_after_payload = _load_readback(root, "after", "depth_stencil")
        _validate_pair(depth_before_metadata, depth_after_metadata)
        for field in ("consumer_family", "frame", "draw", "sample"):
            default = 1 if field == "sample" else None
            _require(
                before_metadata.get(field, default)
                == depth_before_metadata.get(field, default),
                f"attachment {field} mismatch",
            )
        depth = _compare_depth(depth_before_metadata, depth_before_payload, depth_after_payload, output)
    source = {
        **before_metadata["source"],
        "before_sha256": _sha256(root / "before" / "target.bin"),
        "after_sha256": _sha256(root / "after" / "target.bin"),
    }
    report = {
        "schema": REPORT_SCHEMA,
        "consumer_family": before_metadata["consumer_family"],
        "frame": before_metadata["frame"],
        "draw": before_metadata["draw"],
        "sample": before_metadata.get("sample", 1),
        "source": source,
        "contribution": color,
        "attachments": {"color": color, "depth_stencil": depth},
        "images": {"before": "before.png", "after": "after.png", "difference_4x": "difference-4x.png", "changed_mask": "changed-mask.png"},
        "safety": {"output_authority": "xenos", "xenos_draw_preserved": True, "draw_suppression": False, "resolve_suppression": False, "suppression_allowed": False},
    }
    (output / "consumer-contribution.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _attachment_changed(report: dict) -> bool | None:
    color_changed = report["attachments"]["color"]["changed_pixels"] > 0
    depth = report["attachments"]["depth_stencil"]
    if depth is None:
        return None
    depth_changed = depth.get("changed_pixels", 0) > 0 or depth.get("changed_active_bytes", 0) > 0
    return color_changed or depth_changed


def analyze(root: Path, output: Path) -> dict:
    samples = sorted(path for path in root.glob("sample-*") if path.is_dir())
    if not samples:
        return _analyze_sample(root, output)
    _require(not output.exists(), f"output already exists: {output}")
    output.mkdir(parents=True)
    reports = []
    for expected, sample_root in enumerate(samples, 1):
        _require(sample_root.name == f"sample-{expected:04d}", "non-contiguous sample corpus")
        reports.append(_analyze_sample(sample_root, output / sample_root.name))
    family = reports[0]["consumer_family"]
    _require(all(report["consumer_family"] == family for report in reports), "consumer family mismatch")
    attachment_deltas = [_attachment_changed(item) for item in reports]
    report = {
        "schema": CORPUS_SCHEMA,
        "consumer_family": family,
        "sample_count": len(reports),
        "samples": [
            {
                "sample": item["sample"],
                "frame": item["frame"],
                "draw": item["draw"],
                "report": f"sample-{index:04d}/consumer-contribution.json",
                "attachments_complete": item["attachments"]["depth_stencil"] is not None,
                "attachment_delta": attachment_deltas[index - 1],
            }
            for index, item in enumerate(reports, 1)
        ],
        "aggregate": {
            "samples_with_complete_attachments": sum(delta is not None for delta in attachment_deltas),
            "samples_with_color_delta": sum(item["attachments"]["color"]["changed_pixels"] > 0 for item in reports),
            "samples_with_depth_stencil_delta": sum(
                bool(item["attachments"]["depth_stencil"] and (
                    item["attachments"]["depth_stencil"].get("changed_pixels", 0) > 0
                    or item["attachments"]["depth_stencil"].get("changed_active_bytes", 0) > 0
                )) for item in reports
            ),
            "all_samples_complete": all(delta is not None for delta in attachment_deltas),
            "all_samples_no_attachment_delta": all(delta is False for delta in attachment_deltas),
            "semantic_role": "operator_review_required",
        },
        "safety": {"output_authority": "xenos", "xenos_draw_preserved": True, "draw_suppression": False, "resolve_suppression": False, "suppression_allowed": False},
    }
    (output / "consumer-contribution-corpus.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
