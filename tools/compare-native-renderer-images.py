#!/usr/bin/env python3
"""Compare an isolated native draw with an exported reference image."""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import math
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


SCHEMA = "pinyon-shift.native-renderer-image-comparison.v1"


@dataclass(frozen=True)
class PpmImage:
    width: int
    height: int
    pixels: bytes
    channels: int = 3
    encoding: str = "ppm-p6-8bit"


def _token(data: bytes, offset: int) -> tuple[bytes, int]:
    while offset < len(data):
        if data[offset] == ord("#"):
            newline = data.find(b"\n", offset)
            if newline < 0:
                raise ValueError("unterminated PPM comment")
            offset = newline + 1
        elif chr(data[offset]).isspace():
            offset += 1
        else:
            break
    end = offset
    while end < len(data) and not chr(data[end]).isspace():
        end += 1
    if end == offset:
        raise ValueError("missing PPM header token")
    return data[offset:end], end


def read_ppm(path: Path) -> PpmImage:
    data = path.read_bytes()
    offset = 0
    values: list[bytes] = []
    for _ in range(4):
        value, offset = _token(data, offset)
        values.append(value)
    if values[0] != b"P6":
        raise ValueError(f"{path}: expected binary PPM P6")
    try:
        width, height, maximum = (int(value) for value in values[1:])
    except ValueError as error:
        raise ValueError(f"{path}: invalid PPM dimensions") from error
    if width <= 0 or height <= 0 or maximum != 255:
        raise ValueError(f"{path}: unsupported PPM dimensions or maximum")
    if offset >= len(data) or not chr(data[offset]).isspace():
        raise ValueError(f"{path}: missing PPM pixel separator")
    offset += 2 if data[offset : offset + 2] == b"\r\n" else 1
    pixels = data[offset:]
    expected = width * height * 3
    if len(pixels) != expected:
        raise ValueError(
            f"{path}: expected {expected} pixel bytes, found {len(pixels)}"
        )
    return PpmImage(width, height, pixels)


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    diagonal_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= diagonal_distance:
        return left
    return above if above_distance <= diagonal_distance else upper_left


def read_png(path: Path) -> PpmImage:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"{path}: invalid PNG signature")
    offset = 8
    header = None
    compressed = bytearray()
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError(f"{path}: truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_start = offset + 8
        chunk_end = chunk_start + length
        if chunk_end + 4 > len(data):
            raise ValueError(f"{path}: truncated PNG chunk payload")
        payload = data[chunk_start:chunk_end]
        expected_crc = struct.unpack_from(">I", data, chunk_end)[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            raise ValueError(f"{path}: PNG chunk CRC mismatch")
        if chunk_type == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            break
        offset = chunk_end + 4
    if header is None:
        raise ValueError(f"{path}: PNG has no IHDR")
    width, height, bit_depth, color_type, compression, filtering, interlace = header
    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    if (
        width <= 0
        or height <= 0
        or bit_depth != 8
        or color_type not in channels_by_type
        or compression != 0
        or filtering != 0
        or interlace != 0
    ):
        raise ValueError(f"{path}: unsupported PNG encoding")
    channels = channels_by_type[color_type]
    row_bytes = width * channels
    try:
        scanlines = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ValueError(f"{path}: invalid PNG image data") from error
    expected = height * (row_bytes + 1)
    if len(scanlines) != expected:
        raise ValueError(
            f"{path}: expected {expected} decoded bytes, found {len(scanlines)}"
        )
    pixels = bytearray(width * height * channels)
    previous = bytearray(row_bytes)
    for row in range(height):
        source_offset = row * (row_bytes + 1)
        filter_type = scanlines[source_offset]
        encoded = scanlines[source_offset + 1 : source_offset + 1 + row_bytes]
        decoded = bytearray(row_bytes)
        for index, value in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise ValueError(f"{path}: unsupported PNG filter {filter_type}")
            decoded[index] = (value + predictor) & 0xFF
        start = row * row_bytes
        pixels[start : start + row_bytes] = decoded
        previous = decoded
    return PpmImage(width, height, bytes(pixels), channels, "png-8bit")


@functools.lru_cache(maxsize=4)
def read_image(path: Path) -> PpmImage:
    return read_png(path) if path.suffix.lower() == ".png" else read_ppm(path)


def crop_image(image: PpmImage, crop: tuple[int, int, int, int] | None) -> PpmImage:
    if crop is None:
        return image
    left, top, width, height = crop
    if (
        left < 0
        or top < 0
        or width <= 0
        or height <= 0
        or left + width > image.width
        or top + height > image.height
    ):
        raise ValueError(
            f"crop {left},{top},{width},{height} exceeds "
            f"{image.width}x{image.height} image"
        )
    row_bytes = image.width * image.channels
    crop_row_bytes = width * image.channels
    pixels = bytearray(crop_row_bytes * height)
    for row in range(height):
        source = (top + row) * row_bytes + left * image.channels
        destination = row * crop_row_bytes
        pixels[destination : destination + crop_row_bytes] = image.pixels[
            source : source + crop_row_bytes
        ]
    return PpmImage(width, height, bytes(pixels), image.channels, image.encoding)


def compare_images(
    native: PpmImage,
    reference: PpmImage,
    *,
    channel_tolerance: int,
    coverage_threshold: int,
    native_before: PpmImage | None = None,
    reference_before: PpmImage | None = None,
) -> dict[str, float | int]:
    if (native.width, native.height) != (reference.width, reference.height):
        raise ValueError(
            "image dimensions differ: "
            f"native={native.width}x{native.height}, "
            f"reference={reference.width}x{reference.height}"
        )
    if native.channels != reference.channels:
        raise ValueError(
            "image channel counts differ: "
            f"native={native.channels}, reference={reference.channels}"
        )
    if (native_before is None) != (reference_before is None):
        raise ValueError("both before-draw images are required for delta comparison")
    for label, before in (
        ("native", native_before),
        ("reference", reference_before),
    ):
        if before is not None and (
            before.width != native.width
            or before.height != native.height
            or before.channels != native.channels
        ):
            raise ValueError(f"{label} before-draw image layout differs")

    pixel_count = native.width * native.height
    channel_errors: list[int] = []
    different_pixels = 0
    compared_pixels = 0
    native_coverage = 0
    reference_coverage = 0
    coverage_intersection = 0
    coverage_union = 0
    for index in range(pixel_count):
        start = index * native.channels
        end = start + native.channels
        native_pixel = native.pixels[start:end]
        reference_pixel = reference.pixels[start:end]
        if native_before is None:
            coverage_channels = 3 if native.channels >= 3 else 1
            native_present = any(
                value > coverage_threshold for value in native_pixel[:coverage_channels]
            )
            reference_present = any(
                value > coverage_threshold
                for value in reference_pixel[:coverage_channels]
            )
        else:
            native_before_pixel = native_before.pixels[start:end]
            reference_before_pixel = reference_before.pixels[start:end]
            native_present = any(
                abs(after - before) > coverage_threshold
                for after, before in zip(native_pixel, native_before_pixel, strict=True)
            )
            reference_present = any(
                abs(after - before) > coverage_threshold
                for after, before in zip(
                    reference_pixel, reference_before_pixel, strict=True
                )
            )
        native_coverage += native_present
        reference_coverage += reference_present
        coverage_intersection += native_present and reference_present
        coverage_union += native_present or reference_present
        if native_before is None or native_present or reference_present:
            errors = [
                abs(left - right)
                for left, right in zip(native_pixel, reference_pixel, strict=True)
            ]
            channel_errors.extend(errors)
            compared_pixels += 1
            if any(error > channel_tolerance for error in errors):
                different_pixels += 1
    squared = sum(error * error for error in channel_errors)
    return {
        "mean_absolute_error": (
            sum(channel_errors) / len(channel_errors) if channel_errors else 0.0
        ),
        "root_mean_square_error": (
            math.sqrt(squared / len(channel_errors)) if channel_errors else 0.0
        ),
        "maximum_channel_error": max(channel_errors, default=0),
        "compared_pixels": compared_pixels,
        "different_pixels": different_pixels,
        "different_pixel_ratio": (
            different_pixels / compared_pixels if compared_pixels else 0.0
        ),
        "native_coverage_pixels": native_coverage,
        "reference_coverage_pixels": reference_coverage,
        "coverage_intersection_pixels": coverage_intersection,
        "coverage_union_pixels": coverage_union,
        "coverage_iou": (
            coverage_intersection / coverage_union if coverage_union else 1.0
        ),
    }


def write_difference_ppm(
    path: Path, native: PpmImage, reference: PpmImage, amplification: int
) -> None:
    if (native.width, native.height) != (reference.width, reference.height):
        raise ValueError("cannot write a difference image for mismatched dimensions")
    if native.channels != reference.channels:
        raise ValueError("cannot write a difference image for mismatched channels")
    difference = bytearray()
    for index in range(native.width * native.height):
        start = index * native.channels
        errors = [
            min(
                255,
                abs(native.pixels[start + channel] - reference.pixels[start + channel])
                * amplification,
            )
            for channel in range(native.channels)
        ]
        if native.channels == 1:
            difference.extend(errors * 3)
        elif native.channels == 2:
            difference.extend((max(errors), errors[0], errors[0]))
        else:
            rgb = errors[:3]
            if native.channels == 4:
                rgb[0] = max(rgb[0], errors[3])
            difference.extend(rgb)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        f"P6\n{native.width} {native.height}\n255\n".encode("ascii") + bytes(difference)
    )


def build_report(args: argparse.Namespace) -> dict[str, object]:
    native_path = args.native.resolve()
    reference_path = args.reference.resolve()
    native_source = read_image(native_path)
    reference_source = read_image(reference_path)
    native = crop_image(native_source, args.crop)
    reference = crop_image(reference_source, args.crop)
    native_before_path = args.native_before.resolve() if args.native_before else None
    reference_before_path = (
        args.reference_before.resolve() if args.reference_before else None
    )
    native_before = (
        crop_image(read_image(native_before_path), args.crop)
        if native_before_path
        else None
    )
    reference_before = (
        crop_image(read_image(reference_before_path), args.crop)
        if reference_before_path
        else None
    )
    metrics = compare_images(
        native,
        reference,
        channel_tolerance=args.channel_tolerance,
        coverage_threshold=args.coverage_threshold,
        native_before=native_before,
        reference_before=reference_before,
    )
    checks = {
        "mean_absolute_error": metrics["mean_absolute_error"]
        <= args.mean_absolute_error_max,
        "root_mean_square_error": metrics["root_mean_square_error"]
        <= args.root_mean_square_error_max,
        "different_pixel_ratio": metrics["different_pixel_ratio"]
        <= args.different_pixel_ratio_max,
        "coverage_iou": metrics["coverage_iou"] >= args.coverage_iou_min,
    }
    return {
        "schema": SCHEMA,
        "result": "pass" if all(checks.values()) else "fail",
        "inputs": {
            "native": {
                "path": str(native_path),
                "sha256": hashlib.sha256(native_path.read_bytes()).hexdigest().upper(),
            },
            "reference": {
                "path": str(reference_path),
                "sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest().upper(),
            },
            "native_before": (
                {
                    "path": str(native_before_path),
                    "sha256": hashlib.sha256(
                        native_before_path.read_bytes()
                    ).hexdigest().upper(),
                }
                if native_before_path
                else None
            ),
            "reference_before": (
                {
                    "path": str(reference_before_path),
                    "sha256": hashlib.sha256(
                        reference_before_path.read_bytes()
                    ).hexdigest().upper(),
                }
                if reference_before_path
                else None
            ),
            "width": native.width,
            "height": native.height,
            "source_width": native_source.width,
            "source_height": native_source.height,
            "crop": (
                dict(zip(("left", "top", "width", "height"), args.crop))
                if args.crop is not None
                else None
            ),
            "encoding": native.encoding,
            "channels": native.channels,
            "color_space": args.color_space,
            "comparison_mode": "draw_delta" if native_before else "post_draw",
        },
        "thresholds": {
            "channel_tolerance": args.channel_tolerance,
            "coverage_threshold": args.coverage_threshold,
            "mean_absolute_error_max": args.mean_absolute_error_max,
            "root_mean_square_error_max": args.root_mean_square_error_max,
            "different_pixel_ratio_max": args.different_pixel_ratio_max,
            "coverage_iou_min": args.coverage_iou_min,
        },
        "metrics": metrics,
        "checks": checks,
        "scope": {
            "geometry_coverage": args.content == "color",
            "output_color": args.content == "color",
            "depth": args.content == "depth",
            "alpha": args.content == "color" and native.channels in (2, 4),
            "texture_orientation": args.content == "color",
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--native-before", type=Path)
    parser.add_argument("--reference-before", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--difference-output", type=Path)
    parser.add_argument("--difference-amplification", type=int, default=16)
    parser.add_argument("--channel-tolerance", type=int, default=4)
    parser.add_argument("--coverage-threshold", type=int, default=1)
    parser.add_argument("--mean-absolute-error-max", type=float, default=2.0)
    parser.add_argument("--root-mean-square-error-max", type=float, default=4.0)
    parser.add_argument("--different-pixel-ratio-max", type=float, default=0.01)
    parser.add_argument("--coverage-iou-min", type=float, default=0.99)
    parser.add_argument("--color-space", choices=("linear", "srgb"), default="linear")
    parser.add_argument("--content", choices=("color", "depth"), default="color")
    parser.add_argument(
        "--crop",
        type=lambda value: tuple(int(part) for part in value.split(",")),
        metavar="LEFT,TOP,WIDTH,HEIGHT",
    )
    args = parser.parse_args(argv)
    if not 0 <= args.channel_tolerance <= 255:
        parser.error("--channel-tolerance must be between 0 and 255")
    if not 0 <= args.coverage_threshold <= 255:
        parser.error("--coverage-threshold must be between 0 and 255")
    if not 0 <= args.different_pixel_ratio_max <= 1:
        parser.error("--different-pixel-ratio-max must be between 0 and 1")
    if not 0 <= args.coverage_iou_min <= 1:
        parser.error("--coverage-iou-min must be between 0 and 1")
    if args.mean_absolute_error_max < 0 or args.root_mean_square_error_max < 0:
        parser.error("error thresholds must be non-negative")
    if args.difference_amplification < 1:
        parser.error("--difference-amplification must be at least 1")
    if args.crop is not None and len(args.crop) != 4:
        parser.error("--crop must contain left,top,width,height")
    if (args.native_before is None) != (args.reference_before is None):
        parser.error("--native-before and --reference-before must be used together")
    return args


def main(argv: list[str] | None = None) -> int:
    read_image.cache_clear()
    args = parse_args(argv)
    try:
        report = build_report(args)
        if args.difference_output:
            write_difference_ppm(
                args.difference_output,
                crop_image(read_image(args.native.resolve()), args.crop),
                crop_image(read_image(args.reference.resolve()), args.crop),
                args.difference_amplification,
            )
            report["difference"] = {
                "path": str(args.difference_output.resolve()),
                "amplification": args.difference_amplification,
            }
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["result"] == "pass" else 2
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
