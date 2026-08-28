#!/usr/bin/env python3
"""Build the bounded NR-02D pipeline-state contract for one candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "pinyon-shift.native-pso-contract.v1"
SELECTION_SCHEMA = "pinyon-shift.native-renderer-candidate-selection.v1"
GEOMETRY_SCHEMA = "pinyon-shift.native-geometry-contract.v1"
DRAW_STATE_SCHEMA = "pinyon-shift.native-draw-state-contract.v1"
TEXTURE_SCHEMA = "pinyon-shift.native-texture-provenance.v1"


def integer(value: Any, field: str, base: int = 10) -> int:
    try:
        return int(str(value), base)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}") from exc


def require_schema(document: dict[str, Any], schema: str) -> None:
    if document.get("schema") != schema:
        raise ValueError(f"expected {schema}")


def false_gate(document: dict[str, Any], field: str) -> bool:
    safety = document.get("safety", {})
    return safety.get(field) is False


def true_gate(document: dict[str, Any], field: str) -> bool:
    safety = document.get("safety", {})
    return safety.get(field) is True


def build(
    selection: dict[str, Any],
    geometry: dict[str, Any],
    draw_state: dict[str, Any],
    texture: dict[str, Any],
    signature: str,
) -> dict[str, Any]:
    require_schema(selection, SELECTION_SCHEMA)
    require_schema(geometry, GEOMETRY_SCHEMA)
    require_schema(draw_state, DRAW_STATE_SCHEMA)
    require_schema(texture, TEXTURE_SCHEMA)
    if len(signature) != 16 or any(
        character not in "0123456789abcdefABCDEF" for character in signature
    ):
        raise ValueError("signature must be 16 hexadecimal digits")
    signature = signature.upper()
    candidates = [
        item for item in selection.get("candidates", [])
        if str(item.get("signature", "")).upper() == signature
    ]
    if len(candidates) != 1:
        raise ValueError("selection must contain the exact candidate once")
    candidate = candidates[0]
    for name, document in (
        ("geometry", geometry), ("draw state", draw_state), ("texture", texture)
    ):
        if str(document.get("candidate_signature", "")).upper() != signature:
            raise ValueError(f"{name} signature does not match")

    pipeline_hash = str(candidate.get("prepared_pipeline_hash", "")).upper()
    if len(pipeline_hash) != 16 or any(
        character not in "0123456789ABCDEF" for character in pipeline_hash
    ):
        raise ValueError("candidate lacks a prepared pipeline observation")
    formats_text = str(candidate.get("bound_render_target_formats", ""))
    format_parts = formats_text.split(":")
    if len(format_parts) != 5:
        raise ValueError("prepared render-target format set is malformed")
    formats = [integer(value, "render-target format", 16) for value in format_parts]
    bound_bits = integer(candidate.get("bound_render_target_bits"), "bound targets", 16)
    flags = integer(candidate.get("prepared_pipeline_flags"), "pipeline flags", 16)

    unsupported: list[str] = []
    host_primitive = integer(candidate.get("host_primitive"), "host primitive")
    host_vertex_type = integer(
        candidate.get("host_vertex_shader_type"), "host vertex shader type"
    )
    tessellation = integer(candidate.get("tessellation_mode"), "tessellation mode")
    host_index_buffer = integer(
        candidate.get("host_index_buffer_type"), "host index buffer type"
    )
    host_index_format = integer(candidate.get("host_index_format"), "host index format")
    host_reset = candidate.get("host_primitive_reset") is True
    if host_primitive != integer(geometry.get("primitive"), "guest primitive"):
        unsupported.append("primitive_conversion")
    if host_vertex_type != 0:
        unsupported.append("special_host_vertex_shader")
    # PrimitiveProcessor documents tessellation_mode as meaningful only for a
    # non-kVertex host shader. Ordinary vertex draws may retain any guest
    # VGT_HOS_CNTL mode without enabling tessellation.
    if host_vertex_type != 0:
        unsupported.append("tessellation")
    if geometry.get("indexed") is not True or host_index_buffer != 1:
        unsupported.append("non_direct_guest_index_buffer")
    if host_index_format != integer(geometry.get("index", {}).get("format"), "index format"):
        unsupported.append("host_index_format_conversion")
    if host_reset:
        unsupported.append("host_primitive_restart")
    if flags != 3:
        unsupported.append("unrecognized_prepared_pipeline_flags")
    if not bound_bits:
        unsupported.append("no_bound_render_target")
    normalized_color_mask = integer(
        candidate.get("normalized_color_mask"), "normalized color mask", 16
    )
    if not normalized_color_mask:
        unsupported.append("no_color_output")
    if geometry.get("bounds", {}).get("validated") is not True:
        unsupported.append("geometry_not_bounded")
    qualification = texture.get("qualification", {})
    if qualification.get("content_stable_across_captures") is not True:
        unsupported.append("texture_content_not_stable")

    key = {
        "vertex_shader": str(candidate.get("vertex_shader", "")).upper(),
        "pixel_shader": str(candidate.get("pixel_shader", "")).upper(),
        "vertex_specialization_mask": str(
            candidate.get("vertex_specialization_mask", "")
        ).upper(),
        "pixel_specialization_mask": str(
            candidate.get("pixel_specialization_mask", "")
        ).upper(),
        "prepared_pipeline_hash": pipeline_hash,
        "host_primitive": host_primitive,
        "host_vertex_shader_type": host_vertex_type,
        "tessellation_mode": tessellation,
        "host_index_buffer_type": host_index_buffer,
        "host_index_format": host_index_format,
        "host_primitive_reset": host_reset,
        "normalized_depth_control": integer(
            candidate.get("normalized_depth_control"), "normalized depth", 16
        ),
        "normalized_color_mask": normalized_color_mask,
        "bound_render_target_bits": bound_bits,
        "bound_render_target_formats": [
            {"slot": slot, "format": value}
            for slot, value in zip(("depth", "color0", "color1", "color2", "color3"), formats)
        ],
        "raw_pipeline_state": candidate.get("pipeline_state"),
    }
    key_json = json.dumps(key, sort_keys=True, separators=(",", ":")).encode()
    contract_hash = hashlib.sha256(key_json).hexdigest().upper()
    safety_valid = (
        false_gate(geometry, "native_upload")
        and false_gate(geometry, "native_draw")
        and false_gate(geometry, "suppression_allowed")
        and true_gate(geometry, "xenos_authority")
        and false_gate(draw_state, "native_upload")
        and false_gate(draw_state, "native_draw")
        and false_gate(draw_state, "suppression_allowed")
        and true_gate(draw_state, "xenos_authority")
        and false_gate(texture, "native_upload")
        and false_gate(texture, "native_draw")
        and false_gate(texture, "suppression_allowed")
        and true_gate(texture, "xenos_authority")
    )
    if not safety_valid:
        raise ValueError("input contracts do not preserve the isolated safety gates")

    return {
        "schema": SCHEMA,
        "candidate_signature": signature,
        "pso_key_sha256": contract_hash,
        "pso_key": key,
        "support": {
            "ready_for_pso_creation": not unsupported,
            "unsupported_or_unknown": unsupported,
            "draw_state_stable_across_captures": bool(
                draw_state.get("state_stable_across_captures")
            ),
            "visual_identity_confirmed": bool(
                qualification.get("visual_identity_confirmed")
            ),
            "dynamic_render_target_exclusion_required": bool(
                qualification.get("dynamic_render_target_exclusion_required")
            ),
        },
        "safety": {
            "native_pso_created": False,
            "native_upload": False,
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection", type=Path)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("draw_state", type=Path)
    parser.add_argument("texture", type=Path)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (args.selection, args.geometry, args.draw_state, args.texture)
    ]
    result = build(*documents, args.signature)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
