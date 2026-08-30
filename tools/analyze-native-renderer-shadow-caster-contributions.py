"""Measure exact local-only shadow depth deltas by capture-bound family."""

import argparse
import binascii
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path


EXPORT_SCHEMA = "pinyon-shift.native-renderer-shadow-caster-contributions.v1"
CENSUS_SCHEMA = "pinyon-shift.native-renderer-effect-pass-census.v1"
SCHEMA = "pinyon-shift.native-renderer-shadow-caster-contribution-report.v1"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def paeth(left, up, upper_left):
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def decode_rgba_png(path):
    data = path.read_bytes()
    require(data.startswith(PNG_SIGNATURE), f"{path}: invalid PNG signature")
    position = len(PNG_SIGNATURE)
    width = height = None
    compressed = bytearray()
    while position < len(data):
        require(position + 12 <= len(data), f"{path}: truncated PNG chunk")
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        chunk_start = position + 8
        chunk_end = chunk_start + length
        require(chunk_end + 4 <= len(data), f"{path}: truncated PNG payload")
        payload = data[chunk_start:chunk_end]
        expected_crc = struct.unpack(">I", data[chunk_end : chunk_end + 4])[0]
        actual_crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        require(expected_crc == actual_crc, f"{path}: PNG CRC mismatch")
        position = chunk_end + 4
        if chunk_type == b"IHDR":
            require(len(payload) == 13, f"{path}: invalid IHDR")
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", payload)
            require(
                bit_depth == 8 and color_type == 6,
                f"{path}: expected an 8-bit RGBA PNG",
            )
            require(
                compression == 0 and filter_method == 0 and interlace == 0,
                f"{path}: unsupported PNG encoding",
            )
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            break
    require(width and height and compressed, f"{path}: incomplete PNG")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        result = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(path),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgba",
                "-",
            ],
            check=False,
            capture_output=True,
        )
        require(result.returncode == 0, f"{path}: ffmpeg PNG decode failed")
        require(
            len(result.stdout) == width * height * 4,
            f"{path}: unexpected ffmpeg RGBA size",
        )
        return width, height, result.stdout
    stride = width * 4
    raw = zlib.decompress(bytes(compressed))
    require(
        len(raw) == height * (stride + 1),
        f"{path}: unexpected decompressed PNG size",
    )
    pixels = bytearray(width * height * 4)
    previous = bytearray(stride)
    raw_offset = 0
    output_offset = 0
    for _ in range(height):
        filter_type = raw[raw_offset]
        row = bytearray(raw[raw_offset + 1 : raw_offset + 1 + stride])
        require(filter_type <= 4, f"{path}: unsupported PNG filter")
        for index in range(stride):
            left = row[index - 4] if index >= 4 else 0
            up = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            predictor = 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                predictor = paeth(left, up, upper_left)
            row[index] = (row[index] + predictor) & 0xFF
        pixels[output_offset : output_offset + stride] = row
        output_offset += stride
        raw_offset += stride + 1
        previous = row
    return width, height, bytes(pixels)


def png_chunk(chunk_type, payload):
    checksum = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", checksum)
    )


def write_rgba_png(path, width, height, pixels):
    require(len(pixels) == width * height * 4, "invalid RGBA payload size")
    stride = width * 4
    rows = b"".join(
        b"\x00" + pixels[offset : offset + stride]
        for offset in range(0, len(pixels), stride)
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        PNG_SIGNATURE
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(rows, 9))
        + png_chunk(b"IEND", b"")
    )


def local_image(root, item):
    name = item.get("path")
    require(isinstance(name, str) and Path(name).name == name, "unsafe image path")
    path = root / name
    require(path.is_file(), f"missing contribution image: {name}")
    require(sha256(path) == item.get("sha256"), f"image hash drifted: {name}")
    return path


def family_inventory(census):
    inventory = {}
    for family in census.get("families", []):
        signature = family.get("signature", {})
        signature_summary = {
            key: signature.get(key)
            for key in (
                "pipeline_name",
                "vertex_shader_name",
                "pixel_shader_name",
                "viewport",
                "scissor",
            )
        }
        for event_id in family.get("event_ids", []):
            require(event_id not in inventory, "duplicate census event id")
            inventory[event_id] = {
                "family_sha256": family.get("sha256"),
                "classifier_rule": family.get("classifier_rule"),
                "semantic_role": family.get(
                    "semantic_role", "unknown_unclassified"
                ),
                "caster_class": family.get("caster_class"),
                "atlas_region": family.get("atlas_region"),
                "signature": signature_summary,
            }
    return inventory


def compare_event(before_path, after_path, output_path):
    before_width, before_height, before = decode_rgba_png(before_path)
    after_width, after_height, after = decode_rgba_png(after_path)
    require(
        (before_width, before_height) == (after_width, after_height),
        "before/after dimensions differ",
    )
    before_words = memoryview(before).cast("I")
    after_words = memoryview(after).cast("I")
    changed_pixels = 0
    min_x = before_width
    min_y = before_height
    max_x = max_y = -1
    for pixel, (before_pixel, after_pixel) in enumerate(
        zip(before_words, after_words)
    ):
        if before_pixel == after_pixel:
            continue
        x = pixel % before_width
        y = pixel // before_width
        changed_pixels += 1
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
    if not changed_pixels:
        return {
            "changed_pixels": 0,
            "changed_fraction": 0.0,
            "bounding_box": None,
            "delta_image": None,
        }
    width = max_x - min_x + 1
    height = max_y - min_y + 1
    delta = bytearray(width * height * 4)
    for y in range(min_y, max_y + 1):
        source_row = y * before_width
        target_row = (y - min_y) * width
        for x in range(min_x, max_x + 1):
            pixel = source_row + x
            if before_words[pixel] == after_words[pixel]:
                continue
            source_offset = pixel * 4
            target_offset = (target_row + x - min_x) * 4
            delta[target_offset : target_offset + 3] = after[
                source_offset : source_offset + 3
            ]
            delta[target_offset + 3] = 255
    write_rgba_png(output_path, width, height, bytes(delta))
    return {
        "changed_pixels": changed_pixels,
        "changed_fraction": changed_pixels / (before_width * before_height),
        "bounding_box": {
            "x": min_x,
            "y": min_y,
            "width": width,
            "height": height,
        },
        "delta_image": output_path.name,
    }


def analyze(export_path, census_path, output_dir):
    export = json.loads(export_path.read_text(encoding="utf-8"))
    census = json.loads(census_path.read_text(encoding="utf-8"))
    require(export.get("schema") == EXPORT_SCHEMA, "unsupported export schema")
    require(census.get("schema") == CENSUS_SCHEMA, "unsupported census schema")
    require(
        str(export.get("capture", {}).get("sha256", "")).upper()
        == str(census.get("capture", {}).get("sha256", "")).upper(),
        "export and census captures differ",
    )
    census_safety = census.get("safety", {})
    require(
        census_safety.get("metadata_only") is True
        and census_safety.get("resource_payload_exported") is False
        and census_safety.get("xenos_authority") is True
        and census_safety.get("suppression_allowed") is False,
        "census safety boundary is incomplete",
    )
    safety = export.get("safety", {})
    require(
        safety.get("local_resource_payload_exported") is True
        and safety.get("tracked_payload_allowed") is False
        and safety.get("xenos_authority") is True
        and safety.get("native_rendering_changed") is False
        and safety.get("suppression_allowed") is False,
        "export safety boundary is incomplete",
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    inventory = family_inventory(census)
    events = []
    aggregates = {}
    previous_event = 0
    for item in export.get("events", []):
        event_id = item.get("event_id")
        require(
            isinstance(event_id, int) and event_id > previous_event,
            "export events are not ordered",
        )
        previous_event = event_id
        before_path = local_image(export_path.parent, item.get("before", {}))
        after_path = local_image(export_path.parent, item.get("after", {}))
        delta_path = output_dir / f"event-{event_id:04d}-delta.png"
        contribution = compare_event(before_path, after_path, delta_path)
        family = inventory.get(
            event_id,
            {
                "family_sha256": None,
                "classifier_rule": None,
                "semantic_role": "unknown_unclassified",
                "caster_class": None,
                "atlas_region": None,
                "signature": None,
            },
        )
        record = {"event_id": event_id, **family, **contribution}
        events.append(record)
        key = family["family_sha256"] or "unclassified"
        aggregate = aggregates.setdefault(
            key,
            {
                **family,
                "events": [],
                "draws": 0,
                "draws_with_delta": 0,
                "changed_pixels": 0,
            },
        )
        aggregate["events"].append(event_id)
        aggregate["draws"] += 1
        aggregate["draws_with_delta"] += contribution["changed_pixels"] > 0
        aggregate["changed_pixels"] += contribution["changed_pixels"]
    ordered_aggregates = sorted(
        aggregates.values(),
        key=lambda item: (
            item["family_sha256"] is None,
            str(item["family_sha256"]),
        ),
    )
    report = {
        "schema": SCHEMA,
        "capture": export.get("capture"),
        "resource": export.get("resource"),
        "events": events,
        "families": ordered_aggregates,
        "totals": {
            "events": len(events),
            "events_with_delta": sum(item["changed_pixels"] > 0 for item in events),
            "families": len(ordered_aggregates),
            "families_with_delta": sum(
                item["draws_with_delta"] > 0 for item in ordered_aggregates
            ),
            "changed_pixels": sum(item["changed_pixels"] for item in events),
        },
        "qualification": {
            "exact_event_inventory_joined": True,
            "visual_review_required": True,
            "caster_classification_allowed_without_review": False,
        },
        "safety": {
            "payloads_local_only": True,
            "tracked_payload_allowed": False,
            "xenos_authority": True,
            "native_rendering_changed": False,
            "suppression_allowed": False,
        },
    }
    report_path = output_dir / "shadow-caster-contribution-report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report_path, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", required=True, type=Path)
    parser.add_argument("--effect-census", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    report_path, _ = analyze(
        arguments.export, arguments.effect_census, arguments.output_dir
    )
    print(report_path)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"shadow caster contribution analysis failed: {error}", file=sys.stderr)
        sys.exit(1)
