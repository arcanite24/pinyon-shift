#!/usr/bin/env python3
"""Prove the CModelPresentation owner above the SimpleModel renderer."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-owner.v1"
IMAGE_BASE = 0x82000000
PRESENTATION_VTABLE = 0x822432D4
PRESENTATION_SLOT_COUNT = 18
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")

PRESENTATION_CONSTRUCTOR = 0x82DE9840
PRESENTATION_DESTRUCTOR = 0x82DEA218
PRESENTATION_DELETING_DESTRUCTOR = 0x82DEA508
PRESENTATION_DRAW_SLOT = 12
PRESENTATION_DRAW = 0x823F8DB8
PRESENTATION_DRAW_EXIT = 0x823F8FA0
PRESENTATION_PREPARE = 0x823F8980
PRESENTATION_INITIALIZE = 0x82DEA298
RENDERER_CONSTRUCTOR_WRAPPER = 0x82C4E3A0
RENDERER_VTABLE = 0x82001B64
RENDERER_BIND = 0x82C4C838
RESOURCE_BIND = 0x82C48038
BINDING_CONSTRUCTOR = 0x824AFB20
REFERENCE_ASSIGN = 0x826E1B10
RENDERER_BIND_SLOT = 0
RENDERER_DRAW_SLOT = 12
RESOURCE_REFERENCE_OFFSET = 148
RENDERER_FIELD_OFFSET = 1608
STATE_FIELD_OFFSET = 144


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


def image_u32(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise ValueError(f"image address is out of range: {address:08X}")
    return int.from_bytes(image[offset : offset + 4], "big")


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
    slots = [
        image_u32(image, PRESENTATION_VTABLE + index * 4)
        for index in range(PRESENTATION_SLOT_COUNT)
    ]
    if slots[0] != PRESENTATION_DELETING_DESTRUCTOR:
        raise ValueError("CModelPresentation deleting destructor drifted")
    if slots[PRESENTATION_DRAW_SLOT] != PRESENTATION_DRAW:
        raise ValueError("CModelPresentation draw slot drifted")
    if slots[7] != PRESENTATION_INITIALIZE:
        raise ValueError("CModelPresentation initialize slot drifted")
    renderer_slots = [
        image_u32(image, RENDERER_VTABLE + index * 4) for index in range(17)
    ]

    require_instructions(
        functions,
        PRESENTATION_CONSTRUCTOR,
        {
            0x82DE9864: "lis r11,-32220",
            0x82DE9878: "addi r10,r10,13012",
            0x82DE9884: "stw r10,0(r31)",
            0x82DE98E0: "stw r30,144(r31)",
            0x82DE98E4: "stw r30,148(r31)",
            0x82DE993C: "stw r30,1608(r31)",
        },
    )
    require_instructions(
        functions,
        PRESENTATION_DESTRUCTOR,
        {
            0x82DEA230: "addi r11,r11,13012",
            0x82DEA238: "stw r11,0(r3)",
            0x82DEA244: "bl 0x82de9f10",
            0x82DEA260: "addi r3,r31,148",
            0x82DEA264: "bl 0x82de7330",
        },
    )
    require_instructions(
        functions,
        PRESENTATION_DELETING_DESTRUCTOR,
        {
            0x82DEA524: "bl 0x82dea218",
            0x82DEA530: "mr r3,r31",
            0x82DEA534: "bl 0x823fd208",
        },
    )
    require_instructions(
        functions,
        PRESENTATION_INITIALIZE,
        {
            0x82DEA2A4: "mr r31,r3",
            0x82DEA384: "addi r3,r31,148",
            0x82DEA388: "bl 0x82c48038",
            0x82DEA390: "stw r11,144(r31)",
        },
    )
    require_instructions(
        functions,
        PRESENTATION_PREPARE,
        {
            0x823F89A4: "lwz r11,148(r24)",
            0x823F89A8: "addi r31,r24,148",
            0x823F8A14: "bl 0x82c4e3a0",
            0x823F8A18: "stw r3,1608(r24)",
            0x823F8A24: "bl 0x824afb20",
            0x823F8A28: "lwz r3,1608(r24)",
            0x823F8A34: "lwz r11,0(r11)",
            0x823F8A3C: "bctrl",
            0x823F8A44: "stw r11,144(r24)",
        },
    )
    require_instructions(
        functions,
        BINDING_CONSTRUCTOR,
        {
            0x824AFB40: "lwz r31,0(r4)",
            0x824AFB60: "stw r31,0(r30)",
        },
    )
    require_instructions(
        functions,
        RENDERER_BIND,
        {
            0x82C4C848: "addi r3,r3,72",
            0x82C4C84C: "mr r31,r4",
            0x82C4C850: "bl 0x826e1b10",
        },
    )
    require_instructions(
        functions,
        REFERENCE_ASSIGN,
        {
            0x826E1B24: "lwz r31,0(r4)",
            0x826E1B48: "lwz r3,0(r30)",
            0x826E1B4C: "stw r31,0(r30)",
        },
    )
    require_instructions(
        functions,
        PRESENTATION_DRAW,
        {
            0x823F8DC4: "mr r31,r3",
            0x823F8DDC: "bl 0x823f8980",
            0x823F8E20: "lwz r11,1608(r31)",
            0x823F8F0C: "lwz r3,1608(r31)",
            0x823F8F18: "lwz r11,48(r11)",
            0x823F8F20: "bctrl",
            PRESENTATION_DRAW_EXIT: "addi r1,r1,160",
        },
    )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "exact_model_presentation_to_simple_model_renderer_owner",
        "presentation": {
            "class": "Presentation_Unified::CModelPresentation",
            "vtable": f"{PRESENTATION_VTABLE:08X}",
            "constructor": f"{PRESENTATION_CONSTRUCTOR:08X}",
            "destructor": f"{PRESENTATION_DESTRUCTOR:08X}",
            "deleting_destructor_slot": 0,
            "deleting_destructor": f"{PRESENTATION_DELETING_DESTRUCTOR:08X}",
            "draw_slot": PRESENTATION_DRAW_SLOT,
            "draw_method": f"{PRESENTATION_DRAW:08X}",
            "draw_entry_hook": f"{PRESENTATION_DRAW:08X}",
            "draw_exit_hook": f"{PRESENTATION_DRAW_EXIT:08X}",
            "state_field_offset": STATE_FIELD_OFFSET,
            "resource_reference_offset": RESOURCE_REFERENCE_OFFSET,
            "renderer_field_offset": RENDERER_FIELD_OFFSET,
        },
        "renderer_join": {
            "prepare_helper": f"{PRESENTATION_PREPARE:08X}",
            "constructor_wrapper": f"{RENDERER_CONSTRUCTOR_WRAPPER:08X}",
            "renderer_vtable": f"{RENDERER_VTABLE:08X}",
            "bind_slot": RENDERER_BIND_SLOT,
            "bind_target": f"{renderer_slots[RENDERER_BIND_SLOT]:08X}",
            "draw_slot": RENDERER_DRAW_SLOT,
            "draw_target": f"{renderer_slots[RENDERER_DRAW_SLOT]:08X}",
            "join_kind": "balanced_synchronous_presentation_draw_scope",
        },
        "resource_join": {
            "initialize_slot": 7,
            "initialize_method": f"{PRESENTATION_INITIALIZE:08X}",
            "resource_bind": f"{RESOURCE_BIND:08X}",
            "presentation_resource_field_offset": RESOURCE_REFERENCE_OFFSET,
            "binding_constructor": f"{BINDING_CONSTRUCTOR:08X}",
            "renderer_bind": f"{RENDERER_BIND:08X}",
            "reference_assignment": f"{REFERENCE_ASSIGN:08X}",
            "renderer_resource_field_offset": 72,
            "address_equation": (
                "presentation_plus_148_equals_renderer_plus_72"
            ),
        },
        "claims": {
            "exact_model_presentation_owner_proved": True,
            "presentation_to_renderer_field_proved": True,
            "presentation_to_resource_reference_proved": True,
            "renderer_bind_and_draw_dispatch_proved": True,
            "presentation_to_renderer_resource_identity_proved": True,
            "concrete_building_or_prop_identity_proved": False,
            "mesh_or_material_semantics_proved": False,
        },
        "safety": {
            "static_analysis_only": True,
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
        print(f"static-world owner discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
