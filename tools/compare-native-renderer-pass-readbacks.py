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
DEPTH_CHECKPOINT_SCHEMA = (
    "pinyon-shift.native-renderer-depth-checkpoint-analysis.v2"
)
DEPTH_EFFECT_SCHEMA = (
    "pinyon-shift.native-renderer-draw-effect-comparison.v1"
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
) -> dict[str, Any]:
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


def _compare_depth_tuple_components(
    native_data: bytes,
    xenos_data: bytes,
    width: int,
    height: int,
    sample_count: int,
    plane: dict[str, Any],
) -> dict[str, Any]:
    changed_pixels = 0
    changed_samples = 0
    depth_tuple_changes = 0
    stencil_tuple_changes = 0
    depth_different_bytes = 0
    stencil_different_bytes = 0
    changed_sample_histogram = [0] * sample_count
    left, top, right, bottom = width, height, -1, -1
    first_changed_samples: list[dict[str, int | str]] = []
    for y in range(height):
        row = int(plane["offset"]) + y * int(plane["row_pitch"])
        for x in range(width):
            pixel_changed = False
            for sample in range(sample_count):
                offset = row + (x * sample_count + sample) * 8
                native_depth = native_data[offset : offset + 4]
                xenos_depth = xenos_data[offset : offset + 4]
                native_stencil = native_data[offset + 4 : offset + 8]
                xenos_stencil = xenos_data[offset + 4 : offset + 8]
                depth_changed = native_depth != xenos_depth
                stencil_changed = native_stencil != xenos_stencil
                if not depth_changed and not stencil_changed:
                    continue
                changed_samples += 1
                changed_sample_histogram[sample] += 1
                pixel_changed = True
                depth_tuple_changes += depth_changed
                stencil_tuple_changes += stencil_changed
                depth_different_bytes += sum(
                    left_byte != right_byte
                    for left_byte, right_byte in zip(
                        native_depth, xenos_depth, strict=True
                    )
                )
                stencil_different_bytes += sum(
                    left_byte != right_byte
                    for left_byte, right_byte in zip(
                        native_stencil, xenos_stencil, strict=True
                    )
                )
                if len(first_changed_samples) < 16:
                    first_changed_samples.append(
                        {
                            "x": x,
                            "y": y,
                            "sample": sample,
                            "native_depth_word": format(
                                int.from_bytes(native_depth, "little"), "08X"
                            ),
                            "xenos_depth_word": format(
                                int.from_bytes(xenos_depth, "little"), "08X"
                            ),
                            "native_stencil": int.from_bytes(
                                native_stencil, "little"
                            ),
                            "xenos_stencil": int.from_bytes(
                                xenos_stencil, "little"
                            ),
                        }
                    )
            if pixel_changed:
                changed_pixels += 1
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
    return {
        "changed_pixels": changed_pixels,
        "total_pixels": width * height,
        "changed_samples": changed_samples,
        "total_samples": width * height * sample_count,
        "depth_tuple_changes": depth_tuple_changes,
        "stencil_tuple_changes": stencil_tuple_changes,
        "depth_different_bytes": depth_different_bytes,
        "stencil_different_bytes": stencil_different_bytes,
        "changed_sample_histogram": changed_sample_histogram,
        "exact_depth": depth_tuple_changes == 0,
        "exact_stencil": stencil_tuple_changes == 0,
        "changed_bounds": (
            {"left": left, "top": top, "right": right, "bottom": bottom}
            if changed_pixels
            else None
        ),
        "first_changed_samples": first_changed_samples,
    }


def _compare_planar_depth_components(
    native_data: bytes,
    xenos_data: bytes,
    planes: list[dict[str, Any]],
) -> dict[str, Any]:
    components: dict[str, Any] = {}
    for index, plane in enumerate(planes):
        rows = [
            (
                int(plane["offset"]) + row * int(plane["row_pitch"]),
                int(plane["row_pitch"]),
                int(plane["row_size"]),
            )
            for row in range(int(plane["row_count"]))
        ]
        components["depth" if index == 0 else "stencil"] = _compare_rows(
            native_data, xenos_data, rows
        )
    return components


def _compare_depth_effects(
    native_seed_data: bytes,
    native_post_data: bytes,
    xenos_seed_data: bytes,
    xenos_post_data: bytes,
    layout: dict[str, Any],
) -> dict[str, Any]:
    encoding = str(layout["encoding"])
    segments: list[tuple[str | None, int, int, int]] = []
    for plane_index, plane in enumerate(layout["planes"]):
        component = None
        if encoding == "d3d12_texture_planes":
            component = "depth" if plane_index == 0 else "stencil"
        for row in range(int(plane["row_count"])):
            segments.append(
                (
                    component,
                    row,
                    int(plane["offset"]) + row * int(plane["row_pitch"]),
                    int(plane["row_size"]),
                )
            )

    compared_bytes = 0
    mismatch_bytes = 0
    native_changed_bytes = 0
    xenos_changed_bytes = 0
    depth_mismatch_bytes = 0
    stencil_mismatch_bytes = 0
    first_mismatches: list[dict[str, int | str]] = []
    for planar_component, row, offset, row_size in segments:
        for byte_in_row in range(row_size):
            index = offset + byte_in_row
            native_seed = native_seed_data[index]
            native_post = native_post_data[index]
            xenos_seed = xenos_seed_data[index]
            xenos_post = xenos_post_data[index]
            native_changed = native_seed != native_post
            xenos_changed = xenos_seed != xenos_post
            native_changed_bytes += native_changed
            xenos_changed_bytes += xenos_changed
            compared_bytes += 1
            effect_matches = native_changed == xenos_changed and (
                not native_changed or native_post == xenos_post
            )
            if effect_matches:
                continue
            mismatch_bytes += 1
            component = planar_component
            if component is None:
                component = "depth" if byte_in_row % 8 < 4 else "stencil"
            if component == "depth":
                depth_mismatch_bytes += 1
            else:
                stencil_mismatch_bytes += 1
            if len(first_mismatches) < 16:
                first_mismatches.append(
                    {
                        "component": component,
                        "row": row,
                        "byte_in_row": byte_in_row,
                        "native_seed": native_seed,
                        "native_post": native_post,
                        "xenos_seed": xenos_seed,
                        "xenos_post": xenos_post,
                    }
                )

    return {
        "schema": DEPTH_EFFECT_SCHEMA,
        "result": "pass" if mismatch_bytes == 0 else "fail",
        "metrics": {
            "compared_bytes": compared_bytes,
            "mismatch_bytes": mismatch_bytes,
            "mismatch_byte_ratio": (
                mismatch_bytes / compared_bytes if compared_bytes else 0.0
            ),
            "native_changed_bytes": native_changed_bytes,
            "xenos_changed_bytes": xenos_changed_bytes,
            "depth_mismatch_bytes": depth_mismatch_bytes,
            "stencil_mismatch_bytes": stencil_mismatch_bytes,
            "exact_draw_effect": mismatch_bytes == 0,
            "first_mismatches": first_mismatches,
        },
    }


def _analyze_stencil_seed_probe(
    native_seed_data: bytes,
    xenos_seed_data: bytes,
    layout: dict[str, Any],
    sentinel: int,
) -> dict[str, Any]:
    encoding = str(layout["encoding"])
    native_sentinel_values = 0
    xenos_sentinel_values = 0
    sentinel_survivors = 0
    inspected_stencil_values = 0

    def inspect(index: int) -> None:
        nonlocal native_sentinel_values
        nonlocal xenos_sentinel_values
        nonlocal sentinel_survivors
        nonlocal inspected_stencil_values
        native_value = native_seed_data[index]
        xenos_value = xenos_seed_data[index]
        inspected_stencil_values += 1
        native_sentinel_values += native_value == sentinel
        xenos_sentinel_values += xenos_value == sentinel
        sentinel_survivors += (
            native_value == sentinel and xenos_value != sentinel
        )

    if encoding == "depth32_stencil8_sample_tuples":
        plane = layout["planes"][0]
        width = int(layout["width"])
        height = int(layout["height"])
        sample_count = int(layout["sample_count"])
        for y in range(height):
            row = int(plane["offset"]) + y * int(plane["row_pitch"])
            for value_index in range(width * sample_count):
                inspect(row + value_index * 8 + 4)
    elif encoding == "d3d12_texture_planes":
        planes = layout["planes"]
        if len(planes) < 2:
            raise ValueError("stencil seed probe requires a stencil plane")
        plane = planes[1]
        for row_index in range(int(plane["row_count"])):
            row = int(plane["offset"]) + row_index * int(plane["row_pitch"])
            for byte_index in range(int(plane["row_size"])):
                inspect(row + byte_index)
    else:
        raise ValueError("unsupported stencil seed probe encoding")

    return {
        "enabled": True,
        "sentinel": sentinel,
        "inspected_stencil_values": inspected_stencil_values,
        "native_sentinel_values": native_sentinel_values,
        "xenos_sentinel_values": xenos_sentinel_values,
        "sentinel_survivors": sentinel_survivors,
        "evidence": (
            "sentinel_survived_guest_copy"
            if sentinel_survivors
            else "sentinel_overwritten"
        ),
    }


def compare(
    native_root: Path,
    xenos_root: Path,
    content: str = "color",
    native_role: str = "native",
    xenos_role: str = "xenos",
) -> dict[str, Any]:
    native, native_data = _load(native_root, native_role, content)
    xenos, xenos_data = _load(xenos_root, xenos_role, content)
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
    component_metrics: dict[str, Any] | None = None
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
        if encoding == "depth32_stencil8_sample_tuples":
            component_metrics = _compare_depth_tuple_components(
                native_data,
                xenos_data,
                width,
                height,
                sample_count,
                native_planes[0],
            )
        else:
            component_metrics = _compare_planar_depth_components(
                native_data, xenos_data, native_planes
            )

    metrics = _compare_rows(native_data, xenos_data, rows)
    if component_metrics is not None:
        metrics["components"] = component_metrics
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


def compare_depth_checkpoints(
    native_root: Path,
    xenos_root: Path,
    native_seed_root: Path,
    xenos_seed_root: Path,
) -> dict[str, Any]:
    seed_copy = compare(
        native_seed_root,
        xenos_seed_root,
        "depth-stencil",
        "native_seed",
        "xenos_seed",
    )
    native_effect = compare(
        native_seed_root,
        native_root,
        "depth-stencil",
        "native_seed",
        "native",
    )
    xenos_effect = compare(
        xenos_seed_root,
        xenos_root,
        "depth-stencil",
        "xenos_seed",
        "xenos",
    )
    final_parity = compare(
        native_root, xenos_root, "depth-stencil", "native", "xenos"
    )
    native_seed_metadata, native_seed_data = _load(
        native_seed_root, "native_seed", "depth-stencil"
    )
    native_post_metadata, native_post_data = _load(
        native_root, "native", "depth-stencil"
    )
    xenos_seed_metadata, xenos_seed_data = _load(
        xenos_seed_root, "xenos_seed", "depth-stencil"
    )
    xenos_post_metadata, xenos_post_data = _load(
        xenos_root, "xenos", "depth-stencil"
    )
    draw_effect_parity = _compare_depth_effects(
        native_seed_data,
        native_post_data,
        xenos_seed_data,
        xenos_post_data,
        final_parity["layout"],
    )
    seed_exact = seed_copy["result"] == "pass"
    parity_exact = final_parity["result"] == "pass"
    effect_exact = draw_effect_parity["result"] == "pass"
    diagnostic_metadata = [
        metadata.get("diagnostic", {})
        for metadata in (
            native_seed_metadata,
            native_post_metadata,
            xenos_seed_metadata,
            xenos_post_metadata,
        )
    ]
    probe_flags = [
        diagnostic.get("stencil_seed_probe") is True
        for diagnostic in diagnostic_metadata
    ]
    if any(probe_flags) and not all(probe_flags):
        raise ValueError("stencil seed probe metadata is inconsistent")
    if all(probe_flags):
        probe_values = {
            diagnostic.get("stencil_seed_probe_value")
            for diagnostic in diagnostic_metadata
        }
        probe_value = next(iter(probe_values))
        if (
            len(probe_values) != 1
            or type(probe_value) is not int
            or not 0 <= probe_value <= 255
        ):
            raise ValueError("stencil seed probe value metadata is inconsistent")
        stencil_seed_probe = _analyze_stencil_seed_probe(
            native_seed_data,
            xenos_seed_data,
            final_parity["layout"],
            probe_value,
        )
    else:
        stencil_seed_probe = {"enabled": False}
    if parity_exact:
        diagnosis = "exact_post_draw_parity"
    elif stencil_seed_probe.get("sentinel_survivors", 0) > 0:
        diagnosis = "stencil_copy_omission_confirmed"
    elif seed_exact:
        diagnosis = "draw_effect_divergence"
    elif effect_exact:
        diagnosis = "seed_divergence_with_exact_draw_effect"
    else:
        diagnosis = "seed_and_draw_effect_divergence"
    return {
        "schema": DEPTH_CHECKPOINT_SCHEMA,
        "result": "pass" if parity_exact else "fail",
        "diagnosis": diagnosis,
        "stencil_seed_probe": stencil_seed_probe,
        "comparisons": {
            "seed_copy": seed_copy,
            "native_draw_effect": native_effect,
            "xenos_draw_effect": xenos_effect,
            "draw_effect_parity": draw_effect_parity,
            "post_draw_parity": final_parity,
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
    parser.add_argument("--native-seed-root", type=Path)
    parser.add_argument("--xenos-seed-root", type=Path)
    parser.add_argument(
        "--content", choices=("color", "depth-stencil"), default="color"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    xenos_root = args.xenos_root or Path(str(args.native_root) + ".xenos")
    if bool(args.native_seed_root) != bool(args.xenos_seed_root):
        raise ValueError("both seed roots are required for checkpoint analysis")
    if args.native_seed_root:
        if args.content != "depth-stencil":
            raise ValueError("seed checkpoint analysis requires depth-stencil")
        report = compare_depth_checkpoints(
            args.native_root,
            xenos_root,
            args.native_seed_root,
            args.xenos_seed_root,
        )
    else:
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
