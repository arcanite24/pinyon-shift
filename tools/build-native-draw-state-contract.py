#!/usr/bin/env python3
"""Build a bounded NR-02 constant, texture, and sampler contract."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any


SCHEMA = "pinyon-shift.native-draw-state-contract.v1"
SELECTION_SCHEMA = "pinyon-shift.native-renderer-candidate-selection.v1"
PHYSICAL_MASK = 0x1FFFFFFF
TEXTURE_FORMATS = [
    "1_REVERSE", "1", "8", "1_5_5_5", "5_6_5", "6_5_5", "8_8_8_8",
    "2_10_10_10", "8_A", "8_B", "8_8", "Cr_Y1_Cb_Y0_REP",
    "Y1_Cr_Y0_Cb_REP", "16_16_EDRAM", "8_8_8_8_A", "4_4_4_4",
    "10_11_11", "11_11_10", "DXT1", "DXT2_3", "DXT4_5",
    "16_16_16_16_EDRAM", "24_8", "24_8_FLOAT", "16", "16_16",
    "16_16_16_16", "16_EXPAND", "16_16_EXPAND", "16_16_16_16_EXPAND",
    "16_FLOAT", "16_16_FLOAT", "16_16_16_16_FLOAT", "32", "32_32",
    "32_32_32_32", "32_FLOAT", "32_32_FLOAT", "32_32_32_32_FLOAT",
    "32_AS_8", "32_AS_8_8", "16_MPEG", "16_16_MPEG", "8_INTERLACED",
    "32_AS_8_INTERLACED", "32_AS_8_8_INTERLACED", "16_INTERLACED",
    "16_MPEG_INTERLACED", "16_16_MPEG_INTERLACED", "DXN",
    "8_8_8_8_AS_16_16_16_16", "DXT1_AS_16_16_16_16",
    "DXT2_3_AS_16_16_16_16", "DXT4_5_AS_16_16_16_16",
    "2_10_10_10_AS_16_16_16_16", "10_11_11_AS_16_16_16_16",
    "11_11_10_AS_16_16_16_16", "32_32_32_FLOAT", "DXT3A", "DXT5A",
    "CTX1", "DXT3A_AS_1_1_1_1", "8_8_8_8_GAMMA_EDRAM",
    "2_10_10_10_FLOAT_EDRAM",
]
DIMENSIONS = ["1d", "2d_or_stacked", "3d", "cube"]
FETCH_DIMENSIONS = ["1d", "2d", "3d_or_stacked", "cube"]
ENDIANNESS = ["none", "8in16", "8in32", "16in32"]
CLAMP = [
    "repeat", "mirrored_repeat", "clamp_to_edge", "mirror_clamp_to_edge",
    "clamp_to_halfway", "mirror_clamp_to_halfway", "clamp_to_border",
    "mirror_clamp_to_border",
]
FILTER = ["point", "linear", "base_map", "use_fetch_constant"]
ANISO = {
    0: "disabled", 1: "max_1_1", 2: "max_2_1", 3: "max_4_1",
    4: "max_8_1", 5: "max_16_1", 7: "use_fetch_constant",
}


def parse_hex_words(value: Any, fields: int, label: str) -> list[int]:
    parts = str(value or "").split(":")
    if len(parts) != fields:
        raise ValueError(f"invalid {label}: {value!r}")
    try:
        return [int(part, 16) for part in parts]
    except ValueError as error:
        raise ValueError(f"invalid {label}: {value!r}") from error


def parse_float_constants(value: Any, expected: int) -> list[dict[str, Any]]:
    if not value and expected == 0:
        return []
    result = []
    for item in str(value).split(";"):
        fields = item.split(":")
        if len(fields) != 5:
            raise ValueError(f"invalid float constant: {item!r}")
        index = int(fields[0])
        words = [int(word, 16) for word in fields[1:]]
        result.append(
            {
                "index": index,
                "words": [f"{word:08X}" for word in words],
                "values": [struct.unpack("<f", word.to_bytes(4, "little"))[0] for word in words],
            }
        )
    if len(result) != expected or len({item["index"] for item in result}) != expected:
        raise ValueError("float constant count or indices are inconsistent")
    if any(item["index"] < 0 or item["index"] >= 256 for item in result):
        raise ValueError("float constant index is outside the shader bank")
    return result


def parse_bool_constants(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    result = []
    for item in str(value).split(";"):
        word, bitmap, packed = parse_hex_words(item, 3, "bool constant word")
        if word >= 8 or not bitmap:
            raise ValueError("invalid bool constant word")
        result.append({"word": word, "used_bitmap": f"{bitmap:08X}", "value": f"{packed:08X}"})
    if len({item["word"] for item in result}) != len(result):
        raise ValueError("duplicate bool constant word")
    return result


def parse_loop_constants(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    result = []
    for item in str(value).split(";"):
        fields = item.split(":")
        if len(fields) != 2:
            raise ValueError(f"invalid loop constant: {item!r}")
        index, word = int(fields[0]), int(fields[1], 16)
        if index < 0 or index >= 32:
            raise ValueError("loop constant index is outside the register bank")
        result.append({"index": index, "word": f"{word:08X}"})
    if len({item["index"] for item in result}) != len(result):
        raise ValueError("duplicate loop constant")
    return result


def signed(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def effective_filter(override: int, fetch: int, names: Any) -> str:
    value = fetch if override == 3 else override
    return names[value]


def decode_texture(value: Any) -> dict[str, Any]:
    parts = str(value or "").split(":")
    if len(parts) != 18:
        raise ValueError(f"invalid texture state: {value!r}")
    stage, fetch_constant = int(parts[0]), int(parts[1])
    words = [int(part, 16) for part in parts[2:8]]
    opcode, fetch_dimension = int(parts[8]), int(parts[9])
    overrides, flags = int(parts[10], 16), int(parts[11], 16)
    instruction_lod_bias, offsets = int(parts[12], 16), int(parts[13], 16)
    result_target, result_index = int(parts[14]), int(parts[15])
    result_mask, result_components = int(parts[16], 16), int(parts[17], 16)
    if stage not in (1, 2) or fetch_constant >= 32 or fetch_dimension >= 4:
        raise ValueError("invalid texture instruction identity")
    word0, word1, word2, word3, word4, word5 = words
    if (word0 & 0x3) not in (2, 3):
        raise ValueError("texture fetch constant is not a texture")
    texture_format = word1 & 0x3F
    dimension = (word5 >> 9) & 0x3
    base_address = ((word1 >> 12) << 12) & PHYSICAL_MASK
    mip_address = ((word5 >> 12) << 12) & PHYSICAL_MASK
    if dimension == 0:
        size = {"width": (word2 & 0xFFFFFF) + 1, "height": 1, "depth": 1}
    elif dimension in (1, 3):
        size = {
            "width": (word2 & 0x1FFF) + 1,
            "height": ((word2 >> 13) & 0x1FFF) + 1,
            "depth": ((word2 >> 26) & 0x3F) + 1 if word0 >> 10 & 1 else 1,
        }
    else:
        size = {
            "width": (word2 & 0x7FF) + 1,
            "height": ((word2 >> 11) & 0x7FF) + 1,
            "depth": ((word2 >> 22) & 0x3FF) + 1,
        }
    fetch_filters = [(word3 >> shift) & 0x3 for shift in (19, 21, 23)]
    override_filters = [(overrides >> shift) & 0xF for shift in (0, 4, 8)]
    if any(value >= 4 for value in override_filters):
        raise ValueError("texture instruction filter override is invalid")
    fetch_aniso, override_aniso = (word3 >> 25) & 0x7, (overrides >> 12) & 0xF
    if fetch_aniso not in ANISO or override_aniso not in ANISO:
        raise ValueError("anisotropic filter is invalid")
    return {
        "stage": "vertex" if stage == 1 else "pixel",
        "fetch_constant": fetch_constant,
        "raw_words": [f"{word:08X}" for word in words],
        "format": {"code": texture_format, "name": TEXTURE_FORMATS[texture_format]},
        "dimension": DIMENSIONS[dimension],
        "fetch_dimension": FETCH_DIMENSIONS[fetch_dimension],
        "size": size,
        "base_address": f"{base_address:08X}",
        "mip_address": f"{mip_address:08X}",
        "pitch_pixels": ((word0 >> 22) & 0x1FF) << 5,
        "tiled": bool(word0 >> 31),
        "stacked": bool((word1 >> 10) & 1),
        "endianness": ENDIANNESS[(word1 >> 6) & 0x3],
        "sign": [(word0 >> shift) & 0x3 for shift in (2, 4, 6, 8)],
        "swizzle": [(word3 >> (1 + component * 3)) & 0x7 for component in range(4)],
        "number_format": "integer" if word3 & 1 else "fractional",
        "exponent_adjust": signed((word3 >> 13) & 0x3F, 6),
        "clamp": [CLAMP[(word0 >> shift) & 0x7] for shift in (10, 13, 16)],
        "filter": {
            "mag": effective_filter(override_filters[0], fetch_filters[0], FILTER),
            "min": effective_filter(override_filters[1], fetch_filters[1], FILTER),
            "mip": effective_filter(override_filters[2], fetch_filters[2], FILTER),
            "anisotropic": ANISO[fetch_aniso if override_aniso == 7 else override_aniso],
        },
        "mip_range": {"minimum": (word4 >> 2) & 0xF, "maximum": (word4 >> 6) & 0xF},
        "fetch_lod_bias": signed((word4 >> 12) & 0x3FF, 10) / 32.0,
        "instruction_lod_bias": struct.unpack("<f", instruction_lod_bias.to_bytes(4, "little"))[0],
        "instruction_offsets_half_texel": [
            signed((offsets >> shift) & 0xFF, 8) for shift in (0, 8, 16)
        ],
        "instruction_flags": flags,
        "result": {
            "storage_target": result_target,
            "storage_index": result_index,
            "write_mask": result_mask,
            "components": result_components,
        },
        "opcode": opcode,
    }


def build(selection: dict[str, Any], signature: str | None = None) -> dict[str, Any]:
    if selection.get("schema") != SELECTION_SCHEMA:
        raise ValueError("unsupported candidate selection schema")
    candidates = selection.get("candidates", [])
    if signature:
        candidates = [item for item in candidates if item.get("signature") == signature]
    if len(candidates) != 1:
        raise ValueError("draw-state contract requires exactly one selected candidate")
    candidate = candidates[0]
    texture_count = int(candidate.get("texture_state_count", 0))
    texture_values = str(candidate.get("texture_states") or "").split(";") if texture_count else []
    if len(texture_values) != texture_count or texture_count < 1:
        raise ValueError("draw-state contract requires observed texture states")
    textures = [decode_texture(value) for value in texture_values]
    resources = {
        (texture["fetch_constant"], tuple(texture["raw_words"])) for texture in textures
    }
    if len(resources) != 1:
        raise ValueError("initial draw-state contract requires exactly one texture resource")
    hashes = candidate.get("draw_state_hashes", [])
    if not hashes or any(len(str(value)) != 16 for value in hashes):
        raise ValueError("candidate has invalid draw-state hashes")
    return {
        "schema": SCHEMA,
        "candidate_signature": candidate["signature"],
        "draw_state_hashes": hashes,
        "state_stable_across_captures": len(set(hashes)) == 1,
        "constants": {
            "vertex_float": parse_float_constants(
                candidate.get("vertex_float_constants"),
                int(candidate.get("vertex_float_constant_count", 0)),
            ),
            "pixel_float": parse_float_constants(
                candidate.get("pixel_float_constants"),
                int(candidate.get("pixel_float_constant_count", 0)),
            ),
            "bool": parse_bool_constants(candidate.get("bool_constants")),
            "loop": parse_loop_constants(candidate.get("loop_constants")),
        },
        "texture_resource_count": len(resources),
        "textures": textures,
        "half_pixel_behavior": {
            "pa_su_vtx_cntl": candidate.get("pipeline_state"),
            "requires_isolated_visual_comparison": True,
        },
        "safety": {
            "guest_resource_payload_read": False,
            "native_upload": False,
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selection", type=Path)
    parser.add_argument("--signature")
    parser.add_argument("--output", "-o", type=Path)
    args = parser.parse_args()
    result = build(json.loads(args.selection.read_text(encoding="utf-8")), args.signature)
    rendered = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
