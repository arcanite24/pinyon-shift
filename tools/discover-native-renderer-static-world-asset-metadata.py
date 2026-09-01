#!/usr/bin/env python3
"""Prove bounded static-world resource-name and material-reference metadata."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-asset-metadata.v1"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")

PRESENTATION_INITIALIZE = 0x82DEA298
PRESENTATION_PREPARE = 0x823F8980
RESOURCE_BIND = 0x82C48038
EFFECT_BIND = 0x82C39B78
TEXTURE_BIND = 0x82C39730
EFFECT_SUFFIX_ADDRESS = 0x8224332C
TEXTURE_FORMAT_ADDRESS = 0x8224331C
TEXTURE_ID_MARKER_ADDRESS = 0x8201C108


def parse_functions(paths: list[pathlib.Path]) -> dict[int, dict[int, str]]:
    functions = {}
    for path in sorted(paths, key=lambda item: item.as_posix()):
        current = None
        address = None
        for line in path.read_text(encoding="utf-8").splitlines():
            match = FUNCTION_RE.match(line)
            if match:
                function_address = int(match.group(1), 16)
                current = functions.setdefault(function_address, {})
                address = function_address
                continue
            label = LABEL_RE.match(line)
            if current is not None and label:
                address = int(label.group(1), 16)
                continue
            comment = COMMENT_RE.match(line)
            if current is not None and comment and address is not None:
                current[address] = comment.group(1)
                address += 4
    return functions


def image_c_string(image: bytes, address: int, maximum: int = 64) -> str:
    offset = address - IMAGE_BASE
    if offset < 0 or offset >= len(image):
        raise ValueError(f"image address is out of range: {address:08X}")
    end = image.find(b"\0", offset, min(len(image), offset + maximum))
    if end < 0:
        raise ValueError(f"unterminated image string at {address:08X}")
    try:
        return image[offset:end].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError(f"non-ASCII image string at {address:08X}") from error


def require_instructions(functions, function_address, expected) -> None:
    instructions = functions.get(function_address)
    if instructions is None:
        raise ValueError(f"missing function {function_address:08X}")
    for address, text in expected.items():
        if instructions.get(address) != text:
            raise ValueError(
                f"instruction drift at {address:08X}: "
                f"expected {text!r}, got {instructions.get(address)!r}"
            )


def build(functions: dict[int, dict[int, str]], image: bytes) -> dict:
    expected_strings = {
        EFFECT_SUFFIX_ADDRESS: ".fx",
        TEXTURE_FORMAT_ADDRESS: "%s%stextures\\%s",
        TEXTURE_ID_MARKER_ADDRESS: "Id=",
    }
    for address, expected in expected_strings.items():
        actual = image_c_string(image, address)
        if actual != expected:
            raise ValueError(
                f"metadata string drift at {address:08X}: "
                f"expected {expected!r}, got {actual!r}"
            )

    require_instructions(
        functions,
        PRESENTATION_INITIALIZE,
        {
            0x82DEA2B0: "addi r30,r31,16",
            0x82DEA2B4: "mr r4,r29",
            0x82DEA2B8: "mr r3,r30",
            0x82DEA2BC: "bl 0x82d8e3f0",
            0x82DEA364: "stw r11,152(r31)",
            0x82DEA368: "lwz r11,20(r30)",
            0x82DEA374: "lwz r4,0(r30)",
            0x82DEA37C: "mr r4,r30",
            0x82DEA380: "lis r5,6",
            0x82DEA384: "addi r3,r31,148",
            0x82DEA388: "bl 0x82c48038",
        },
    )
    require_instructions(
        functions,
        PRESENTATION_PREPARE,
        {
            0x823F89A4: "lwz r11,148(r24)",
            0x823F89F8: "mr r4,r31",
            0x823F89FC: "addi r3,r1,112",
            0x823F8A00: "bl 0x82e61748",
            0x823F8A04: "lwz r26,112(r1)",
            0x823F8A08: "lhz r11,128(r26)",
            0x823F8A8C: "addi r27,r24,1568",
            0x823F8A94: "lhz r29,128(r26)",
            0x823F8AAC: "lis r11,-32220",
            0x823F8AB4: "addi r25,r11,13100",
            0x823F8ABC: "lwz r10,124(r26)",
            0x823F8AC0: "mulli r11,r11,28",
            0x823F8AC8: "lwz r10,20(r11)",
            0x823F8ACC: "cmplwi cr6,r10,16",
            0x823F8AD4: "lwz r11,0(r11)",
            0x823F8B30: "bl 0x82a7f710",
            0x823F8B38: "bne 0x823f8b40",
            0x823F8B3C: "stb r23,0(r31)",
            0x823F8B48: "addi r4,r1,128",
            0x823F8B50: "bl 0x82c39b78",
            0x823F8B64: "addi r26,r26,288",
            0x823F8B74: "lwz r10,4(r26)",
            0x823F8B78: "lwz r9,0(r26)",
            0x823F8B80: "divw r31,r10,r11",
            0x823F8B94: "lis r10,-32220",
            0x823F8B98: "lis r11,-32255",
            0x823F8BA4: "addi r28,r10,13084",
            0x823F8BA8: "addi r27,r11,-16120",
            0x823F8BAC: "lwz r11,0(r26)",
            0x823F8BB4: "lwz r11,20(r3)",
            0x823F8BB8: "cmplwi cr6,r11,16",
            0x823F8BC0: "lwz r3,0(r3)",
            0x823F8BE8: "addi r3,r1,1168",
            0x823F8BEC: "bl 0x830f6520",
            0x823F8BF4: "addi r7,r1,1168",
            0x823F8C04: "bl 0x8247cf40",
            0x823F8C3C: "bl 0x82c39730",
        },
    )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "bounded_simple_model_asset_reference_metadata",
        "resource_key": {
            "presentation_class": "Presentation_Unified::CModelPresentation",
            "initialize_method": f"{PRESENTATION_INITIALIZE:08X}",
            "stored_name_offset": 16,
            "string_layout": "msvc_string_28_bytes_inline_capacity_below_16",
            "resource_reference_offset": 148,
            "resource_bind": f"{RESOURCE_BIND:08X}",
            "resource_type_argument": "00060000",
            "address_equation": (
                "resource_bind_key_equals_presentation_plus_16_string_bytes"
            ),
        },
        "effect_references": {
            "resource_class": "CSimpleModelResource",
            "prepare_helper": f"{PRESENTATION_PREPARE:08X}",
            "records_pointer_offset": 124,
            "record_count_offset": 128,
            "record_count_width_bits": 16,
            "record_stride": 28,
            "record_layout": "msvc_string_28_bytes_inline_capacity_below_16",
            "suffix": expected_strings[EFFECT_SUFFIX_ADDRESS],
            "suffix_address": f"{EFFECT_SUFFIX_ADDRESS:08X}",
            "lookup": f"{EFFECT_BIND:08X}",
            "lookup_type_argument": "00060000",
        },
        "texture_references": {
            "resource_class": "CSimpleModelResource",
            "records_vector_offset": 288,
            "vector_begin_offset": 0,
            "vector_end_offset": 4,
            "record_stride": 28,
            "record_layout": "msvc_string_28_bytes_inline_capacity_below_16",
            "id_marker": expected_strings[TEXTURE_ID_MARKER_ADDRESS],
            "id_marker_address": f"{TEXTURE_ID_MARKER_ADDRESS:08X}",
            "path_format": expected_strings[TEXTURE_FORMAT_ADDRESS],
            "path_format_address": f"{TEXTURE_FORMAT_ADDRESS:08X}",
            "lookup": f"{TEXTURE_BIND:08X}",
        },
        "claims": {
            "presentation_name_to_resource_key_proved": True,
            "bounded_effect_reference_table_proved": True,
            "bounded_texture_reference_table_proved": True,
            "effect_and_texture_path_construction_proved": True,
            "concrete_building_or_prop_category_proved": False,
            "mesh_vertex_or_index_layout_proved": False,
        },
        "next_boundary": {
            "runtime_export": "hash_and_structural_category_only",
            "plaintext_asset_names_allowed": False,
            "category_assignment_requires_runtime_observation": True,
        },
        "safety": {
            "static_analysis_only": True,
            "game_asset_files_opened": False,
            "guest_payload_exported": False,
            "native_admission": False,
            "suppression_allowed": False,
            "xenos_authority_required": True,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated_root", type=pathlib.Path)
    parser.add_argument("--image", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        paths = list(args.generated_root.glob("pinyon_shift_recomp.*.cpp"))
        if not paths:
            raise ValueError("no generated AOT C++ files found")
        document = build(parse_functions(paths), args.image.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"static-world asset metadata discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
