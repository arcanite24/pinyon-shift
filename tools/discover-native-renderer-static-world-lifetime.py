#!/usr/bin/env python3
"""Prove the SimpleModel renderer lifetime and graph ownership boundary."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-lifetime.v1"
IMAGE_BASE = 0x82000000
RENDERER_VTABLE = 0x82001B64
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")

CONSTRUCTOR_WRAPPER = 0x82C4E3A0
CONSTRUCTOR = 0x82C4DF78
CONSTRUCTOR_PUBLISH_HOOK = 0x82C4E094
DELETING_DESTRUCTOR = 0x82C4E420
DESTRUCTOR = 0x82C4E1F8
DESTRUCTOR_EXIT_HOOK = 0x82C4E264
CLEANUP = 0x82C4E0A0
GRAPH_BIND = 0x82C4CC50
GRAPH_BIND_HOOK = 0x82C4CCB0
GRAPH_RELEASE = 0x82C4C6A8
DRAW_DISPATCH = 0x82C4CCC8


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


def require_instructions(
    functions: dict[int, dict[int, str]],
    function_address: int,
    expected: dict[int, str],
) -> None:
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
    slots = [image_u32(image, RENDERER_VTABLE + index * 4) for index in range(17)]
    expected_slots = {
        1: GRAPH_BIND,
        12: DRAW_DISPATCH,
        15: GRAPH_RELEASE,
        16: DELETING_DESTRUCTOR,
    }
    if any(slots[index] != target for index, target in expected_slots.items()):
        raise ValueError("SimpleModel renderer lifecycle vtable drifted")

    require_instructions(
        functions,
        CONSTRUCTOR_WRAPPER,
        {
            0x82C4E3B0: "li r3,368",
            0x82C4E3B4: "bl 0x82c0f6c0",
            0x82C4E3C0: "bl 0x82c4df78",
            0x82C4E3EC: "li r4,1",
            0x82C4E3F4: "lwz r11,64(r11)",
            0x82C4E3FC: "bctrl",
        },
    )
    require_instructions(
        functions,
        CONSTRUCTOR,
        {
            0x82C4DF88: "lis r11,-32256",
            0x82C4DF90: "addi r11,r11,7012",
            0x82C4DF98: "stw r11,0(r31)",
            0x82C4DFCC: "stw r30,72(r31)",
            CONSTRUCTOR_PUBLISH_HOOK: "addi r1,r1,112",
        },
    )
    require_instructions(
        functions,
        DELETING_DESTRUCTOR,
        {
            0x82C4E43C: "bl 0x82c4e1f8",
            0x82C4E440: "clrlwi. r11,r30,31",
            0x82C4E44C: "bl 0x823fd208",
        },
    )
    require_instructions(
        functions,
        DESTRUCTOR,
        {
            0x82C4E210: "addi r11,r11,7012",
            0x82C4E214: "stw r11,0(r3)",
            0x82C4E218: "bl 0x82c4e0a0",
            DESTRUCTOR_EXIT_HOOK: "addi r1,r1,96",
        },
    )
    require_instructions(
        functions,
        CLEANUP,
        {
            0x82C4E0DC: "lwz r3,72(r31)",
            0x82C4E0E0: "stw r30,72(r31)",
            0x82C4E0F0: "lwz r11,12(r11)",
            0x82C4E0F8: "bctrl",
        },
    )
    require_instructions(
        functions,
        GRAPH_BIND,
        {
            0x82C4CC64: "mr r30,r3",
            0x82C4CC98: "addi r3,r30,72",
            0x82C4CC9C: "bl 0x82c48038",
            GRAPH_BIND_HOOK: "addi r1,r1,112",
        },
    )
    require_instructions(
        functions,
        GRAPH_RELEASE,
        {
            0x82C4C6AC: "lwz r3,72(r3)",
            0x82C4C6B8: "stw r10,72(r11)",
            0x82C4C6C4: "lwz r11,12(r11)",
            0x82C4C6CC: "bctr",
        },
    )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "exact_simple_model_renderer_lifetime_and_graph_owner",
        "renderer": {
            "class": "CSimpleModelRenderer",
            "vtable": f"{RENDERER_VTABLE:08X}",
            "object_bytes": 368,
            "constructor_wrapper": f"{CONSTRUCTOR_WRAPPER:08X}",
            "constructor": f"{CONSTRUCTOR:08X}",
            "constructor_publish_hook": f"{CONSTRUCTOR_PUBLISH_HOOK:08X}",
            "deleting_destructor_slot": 16,
            "deleting_destructor": f"{DELETING_DESTRUCTOR:08X}",
            "destructor": f"{DESTRUCTOR:08X}",
            "destructor_entry_hook": f"{DESTRUCTOR:08X}",
            "destructor_exit_hook": f"{DESTRUCTOR_EXIT_HOOK:08X}",
        },
        "graph_ownership": {
            "field_offset": 72,
            "constructor_initial_value": 0,
            "bind_slot": 1,
            "bind_method": f"{GRAPH_BIND:08X}",
            "bind_completion_hook": f"{GRAPH_BIND_HOOK:08X}",
            "bind_helper": "82C48038",
            "release_slot": 15,
            "release_method": f"{GRAPH_RELEASE:08X}",
            "destructor_cleanup": f"{CLEANUP:08X}",
            "release_dispatch_slot": 3,
            "draw_slot": 12,
            "draw_dispatch": f"{DRAW_DISPATCH:08X}",
        },
        "claims": {
            "renderer_generation_boundary_proved": True,
            "renderer_to_owned_graph_field_proved": True,
            "concrete_building_or_prop_identity_proved": False,
            "graph_dynamic_type_proved": False,
            "streaming_lifetime_proved": False,
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
        print(f"static-world lifetime discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
