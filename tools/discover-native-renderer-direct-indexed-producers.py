#!/usr/bin/env python3
"""Prove the bounded direct indexed-draw producer inventory and C2 track lead."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-direct-indexed-producers.v1"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")
DRAW_EMITTER = 0x82416380
DRAW_EMITTER_EXIT = 0x824167EC
TRACK_MESH_VTABLE = 0x8200143C
TRACK_PRESENTATION_VTABLE = 0x82243774
TRACK_HELPER = 0x82C5ADC0
TRACK_HELPER_RETURN = 0x82C5B038

EXPECTED_CALLS = (
    (0x823F5980, 0x823F59C4, 0x823F59C8, "d3d9_device"),
    (0x8240EE98, 0x8240F01C, 0x8240F020, "navigation_map_renderer"),
    (0x82412A28, 0x82412D8C, 0x82412D90, "vector_font"),
    (0x824131B8, 0x824131F0, 0x824131F4, "d3d9_device"),
    (0x8243C050, 0x8243C8F8, 0x8243C8FC, "title_graphics_helper"),
    (0x82473868, 0x82473BD8, 0x82473BDC, "mirror_renderer"),
    (0x82C4CCC8, 0x82C4DC54, 0x82C4DC58, "simple_model_renderer"),
    (TRACK_HELPER, 0x82C5B034, TRACK_HELPER_RETURN,
     "unified_track_presentation_mesh"),
    (0x82C8E610, 0x82C8E798, 0x82C8E79C, "livery_renderer"),
    (0x82D83350, 0x82D841D8, 0x82D841DC, "title_graphics_helper"),
    (0x82DA1148, 0x82DA1548, 0x82DA154C, "title_graphics_helper"),
    (0x82DA1148, 0x82DA1674, 0x82DA1678, "title_graphics_helper"),
    (0x82DA1148, 0x82DA1750, 0x82DA1754, "title_graphics_helper"),
)


def parse_functions(paths: list[pathlib.Path]) -> dict[int, dict[int, str]]:
    functions: dict[int, dict[int, str]] = {}
    for path in sorted(paths, key=lambda item: item.as_posix()):
        current = None
        address = None
        for line in path.read_text(encoding="utf-8").splitlines():
            match = FUNCTION_RE.match(line)
            if match:
                current = functions.setdefault(int(match.group(1), 16), {})
                address = int(match.group(1), 16)
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


def image_u32(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise ValueError(f"image address is out of range: {address:08X}")
    return int.from_bytes(image[offset : offset + 4], "big")


def image_string(image: bytes, address: int) -> str:
    offset = address - IMAGE_BASE
    if offset < 0 or offset >= len(image):
        raise ValueError(f"image string is out of range: {address:08X}")
    end = image.find(b"\0", offset, min(offset + 192, len(image)))
    if end < 0:
        raise ValueError(f"image string is unterminated: {address:08X}")
    return image[offset:end].decode("ascii")


def require_instructions(functions, function_address, expected):
    instructions = functions.get(function_address)
    if instructions is None:
        raise ValueError(f"missing function {function_address:08X}")
    for address, text in expected.items():
        if instructions.get(address) != text:
            raise ValueError(
                f"instruction drift at {address:08X}: "
                f"expected {text!r}, got {instructions.get(address)!r}"
            )


def rtti_name(image: bytes, vtable: int) -> str:
    locator = image_u32(image, vtable - 4)
    if image_u32(image, locator) != 0:
        raise ValueError(f"invalid complete-object locator at {locator:08X}")
    descriptor = image_u32(image, locator + 12)
    return image_string(image, descriptor + 8)


def build(functions: dict[int, dict[int, str]], image: bytes) -> dict:
    observed = sorted(
        (function, address, address + 4)
        for function, instructions in functions.items()
        for address, text in instructions.items()
        if text == f"bl 0x{DRAW_EMITTER:08x}"
    )
    expected = sorted((function, call, ret) for function, call, ret, _ in EXPECTED_CALLS)
    if observed != expected:
        raise ValueError("direct indexed-draw producer inventory drifted")
    require_instructions(
        functions,
        DRAW_EMITTER,
        {DRAW_EMITTER_EXIT: "addi r1,r1,208"},
    )

    if rtti_name(image, TRACK_MESH_VTABLE) != ".?AVCTrackMesh@@":
        raise ValueError("CTrackMesh RTTI evidence drifted")
    if rtti_name(image, TRACK_PRESENTATION_VTABLE) != (
        ".?AVCTrackPresentation@Presentation_Unified@@"
    ):
        raise ValueError("unified CTrackPresentation RTTI evidence drifted")

    require_instructions(
        functions,
        TRACK_HELPER,
        {
            0x82C5ADD8: "mr r26,r6",
            0x82C5ADE4: "mr r31,r7",
            0x82C5AE04: "lfs f0,48(r31)",
            0x82C5AE68: "lfs f0,16(r31)",
            0x82C5AE98: "lfs f0,0(r31)",
            0x82C5B014: "lwz r4,96(r26)",
            0x82C5B024: "lwz r7,100(r26)",
            0x82C5B02C: "lwz r4,36(r26)",
            0x82C5B034: "bl 0x82416380",
        },
    )
    require_instructions(
        functions,
        0x82DED198,
        {
            0x82DEDA2C: "addi r8,r1,688",
            0x82DEDA30: "addi r7,r1,240",
            0x82DEDA34: "mr r6,r29",
            0x82DEDA44: "bl 0x82c5adc0",
        },
    )
    require_instructions(
        functions,
        0x82436468,
        {
            0x82436500: "mr r7,r25",
            0x82436504: "mr r6,r27",
            0x82436514: "bl 0x82ded198",
        },
    )

    presentation_dispatch = (0x8240E7B0, 0x82439B70, 0x82DEEEE0, 0x82DEF2B0)
    for target in presentation_dispatch:
        if not any(
            text == "bl 0x82436468"
            for text in functions.get(target, {}).values()
        ):
            raise ValueError(
                f"unified track presentation caller {target:08X} drifted"
            )
    for slot, target in zip((79, 75, 78, 80), presentation_dispatch):
        if image_u32(image, TRACK_PRESENTATION_VTABLE + slot * 4) != target:
            raise ValueError(f"unified track presentation slot {slot} drifted")

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "bounded_direct_indexed_draw_producer_inventory",
        "draw_emitter": f"{DRAW_EMITTER:08X}",
        "draw_emitter_common_exit": f"{DRAW_EMITTER_EXIT:08X}",
        "producers": [
            {
                "function": f"{function:08X}",
                "callsite": f"{call:08X}",
                "return_address": f"{ret:08X}",
                "classification": classification,
            }
            for function, call, ret, classification in EXPECTED_CALLS
        ],
        "c2_live_candidate": {
            "producer": f"{TRACK_HELPER:08X}",
            "return_address": f"{TRACK_HELPER_RETURN:08X}",
            "mesh_class": "CTrackMesh",
            "mesh_vtable": f"{TRACK_MESH_VTABLE:08X}",
            "mesh_register": "r26",
            "transform_register": "r31",
            "transform_words": 16,
            "upstream_owner": "Presentation_Unified::CTrackPresentation",
            "upstream_owner_vtable": f"{TRACK_PRESENTATION_VTABLE:08X}",
            "runtime_observation_pending": True,
        },
        "claims": {
            "all_direct_callers_enumerated": True,
            "unified_track_mesh_draw_edge_proved": True,
            "unified_track_mesh_transform_edge_proved": True,
            "runtime_activity_proved": False,
            "building_or_prop_identity_proved": False,
        },
        "safety": {
            "static_analysis_only": True,
            "guest_payload_exported": False,
            "native_admission": False,
            "suppression_allowed": False,
            "xenos_authority_required": True,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated", type=pathlib.Path)
    parser.add_argument("--image", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(
            parse_functions(list(args.generated.glob("*.cpp"))),
            args.image.read_bytes(),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, UnicodeDecodeError) as error:
        print(f"direct indexed producer discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
