#!/usr/bin/env python3
"""Prove the SimpleModel resource-to-mesh draw graph."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-graph.v1"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")

RESOURCE_VTABLE = 0x82229294
MODEL_VTABLE = 0x82229208
MODEL_SECONDARY_VTABLE = 0x822291E8
SUBMODEL_VTABLE = 0x822291BC
MESH_VTABLE = 0x822291A0
RESOURCE_CONSTRUCTOR = 0x82C47DA0
MODEL_CONSTRUCTOR = 0x82C47CA0
RENDERER_DISPATCH = 0x82C4CCC8
DRAW_MEMBER_ENTRY_HOOK = 0x82C4DC54
DRAW_MEMBER_EXIT_HOOK = 0x82C4DC58
DRAW_EMITTER = 0x82416380


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


def build(functions: dict[int, dict[int, str]], image: bytes) -> dict:
    expected_slots = (
        (MODEL_VTABLE, 2, 0x824385D0),
        (MODEL_VTABLE, 4, 0x82C25388),
        (SUBMODEL_VTABLE, 3, 0x82C256D0),
        (SUBMODEL_VTABLE, 5, 0x82C256E8),
    )
    for vtable, slot, target in expected_slots:
        if image_u32(image, vtable + slot * 4) != target:
            raise ValueError(
                f"graph dispatch slot drifted at {vtable:08X}[{slot}]"
            )

    require_instructions(
        functions,
        RESOURCE_CONSTRUCTOR,
        {
            0x82C47DD4: "addi r3,r31,112",
            0x82C47DD8: "bl 0x82c47ca0",
        },
    )
    require_instructions(
        functions,
        MODEL_CONSTRUCTOR,
        {
            0x82C47CB4: "bl 0x82c46760",
            0x82C47CE0: "addi r9,r9,-28152",
            0x82C47CE4: "addi r8,r8,-28184",
            0x82C47CF0: "stw r9,0(r31)",
            0x82C47CF4: "stw r8,132(r31)",
            0x82C47D00: "stw r11,176(r31)",
            0x82C47D10: "stw r11,192(r31)",
        },
    )
    require_instructions(
        functions,
        RENDERER_DISPATCH,
        {
            0x82C4CCF4: "addi r4,r3,72",
            0x82C4CD00: "lwz r11,0(r4)",
            0x82C4CD50: "addi r3,r1,112",
            0x82C4CD54: "bl 0x82e61748",
            0x82C4CEDC: "lwz r24,112(r1)",
            0x82C4DAB8: "addi r26,r24,112",
            0x82C4DAC8: "lwz r11,8(r11)",
            0x82C4DAD0: "bctrl",
            0x82C4DAF0: "lwz r11,16(r11)",
            0x82C4DAF8: "bctrl",
            0x82C4DB34: "lwz r11,12(r11)",
            0x82C4DB3C: "bctrl",
            0x82C4DB54: "lwz r11,20(r11)",
            0x82C4DB5C: "bctrl",
            0x82C4DB60: "lwz r11,128(r3)",
            0x82C4DC10: "lwz r4,96(r28)",
            0x82C4DC20: "lwz r3,36(r28)",
            0x82C4DC24: "lwz r4,100(r28)",
            0x82C4DC50: "mr r3,r23",
            DRAW_MEMBER_ENTRY_HOOK: "bl 0x82416380",
            DRAW_MEMBER_EXIT_HOOK: "li r4,0",
        },
    )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "exact_simple_model_resource_to_mesh_draw_graph",
        "objects": {
            "resource": {
                "class": "CSimpleModelResource",
                "vtable": f"{RESOURCE_VTABLE:08X}",
            },
            "model": {
                "class": "CSimpleModel",
                "resource_offset": 112,
                "primary_vtable": f"{MODEL_VTABLE:08X}",
                "secondary_vtable": f"{MODEL_SECONDARY_VTABLE:08X}",
            },
            "submodel": {
                "class": "CSimpleSubModel",
                "vtable": f"{SUBMODEL_VTABLE:08X}",
            },
            "mesh": {
                "class": "CSimpleMesh",
                "vtable": f"{MESH_VTABLE:08X}",
            },
        },
        "dispatch": {
            "renderer": f"{RENDERER_DISPATCH:08X}",
            "model_count_slot": 2,
            "model_submodel_slot": 4,
            "submodel_count_slot": 3,
            "submodel_mesh_slot": 5,
            "draw_member_entry_hook": f"{DRAW_MEMBER_ENTRY_HOOK:08X}",
            "draw_member_exit_hook": f"{DRAW_MEMBER_EXIT_HOOK:08X}",
            "draw_emitter": f"{DRAW_EMITTER:08X}",
            "entry_model_register": "r26",
            "entry_submodel_register": "r29",
            "entry_mesh_register": "r28",
        },
        "claims": {
            "resource_to_embedded_model_proved": True,
            "model_to_submodel_dispatch_proved": True,
            "submodel_to_mesh_dispatch_proved": True,
            "mesh_to_indexed_draw_proved": True,
            "concrete_building_or_prop_identity_proved": False,
            "mesh_material_semantics_proved": False,
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
        print(f"static-world graph discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
