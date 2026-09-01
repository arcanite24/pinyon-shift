#!/usr/bin/env python3
"""Prove the SimpleModelResource factory, registration, and lifetime path."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-resource.v1"
IMAGE_BASE = 0x82000000
RESOURCE_VTABLE = 0x82229294
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")

RENDERER_BIND = 0x82C48038
RESOURCE_FACTORY = 0x82C47F10
RESOURCE_CONSTRUCTOR = 0x82C47DA0
RESOURCE_PUBLISH_HOOK = 0x82C47FBC
RESOURCE_REGISTRATION_HOOK = 0x82C4802C
RESOURCE_DELETING_DESTRUCTOR = 0x82C47EC0
RESOURCE_DESTRUCTOR = 0x82C47DF8
RESOURCE_DESTRUCTOR_EXIT_HOOK = 0x82C47E44
REFERENCE_ASSIGN = 0x824E81A8


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
    if image_u32(image, RESOURCE_VTABLE) != RESOURCE_DELETING_DESTRUCTOR:
        raise ValueError("SimpleModelResource deleting destructor drifted")

    require_instructions(
        functions,
        RENDERER_BIND,
        {
            0x82C48044: "mr r30,r3",
            0x82C480A8: "mr r5,r30",
            0x82C480B4: "bl 0x82c47f10",
            0x82C480C4: "lwz r30,0(r30)",
            0x82C480E4: "bl 0x82e4bff8",
        },
    )
    require_instructions(
        functions,
        RESOURCE_FACTORY,
        {
            0x82C47F70: "lwz r11,0(r31)",
            0x82C47F78: "bne cr6,0x82c4802c",
            0x82C47F94: "li r3,320",
            0x82C47F98: "bl 0x82c0f6c0",
            0x82C47FA8: "bl 0x82c47da0",
            0x82C47FAC: "lis r11,-32221",
            0x82C47FB4: "addi r11,r11,-28012",
            0x82C47FB8: "stw r11,0(r29)",
            RESOURCE_PUBLISH_HOOK: "b 0x82c47fc4",
            0x82C47FC4: "mr r3,r31",
            0x82C47FC8: "bl 0x824e81a8",
            0x82C4800C: "bl 0x82d842f8",
            0x82C48010: "lwz r11,0(r31)",
            RESOURCE_REGISTRATION_HOOK: "mr r3,r27",
        },
    )
    require_instructions(
        functions,
        RESOURCE_CONSTRUCTOR,
        {
            0x82C47DB4: "bl 0x82e45a78",
            0x82C47DC8: "stw r11,0(r31)",
            0x82C47DD8: "bl 0x82c47ca0",
        },
    )
    require_instructions(
        functions,
        REFERENCE_ASSIGN,
        {
            0x824E81CC: "lwz r11,0(r4)",
            0x824E81D4: "lwz r11,8(r11)",
            0x824E81E0: "lwz r3,0(r30)",
            0x824E81E4: "stw r31,0(r30)",
            0x824E81F4: "lwz r11,12(r11)",
        },
    )
    require_instructions(
        functions,
        RESOURCE_DELETING_DESTRUCTOR,
        {
            0x82C47EDC: "bl 0x82c47df8",
            0x82C47EE0: "clrlwi. r11,r30,31",
            0x82C47EEC: "bl 0x823fd208",
        },
    )
    require_instructions(
        functions,
        RESOURCE_DESTRUCTOR,
        {
            0x82C47E10: "mr r30,r3",
            0x82C47E40: "bl 0x82e45b20",
            RESOURCE_DESTRUCTOR_EXIT_HOOK: "addi r1,r1,112",
        },
    )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "exact_simple_model_resource_factory_and_lifetime",
        "resource": {
            "class": "CSimpleModelResource",
            "vtable": f"{RESOURCE_VTABLE:08X}",
            "object_bytes": 320,
            "factory": f"{RESOURCE_FACTORY:08X}",
            "constructor": f"{RESOURCE_CONSTRUCTOR:08X}",
            "publish_hook": f"{RESOURCE_PUBLISH_HOOK:08X}",
            "registration_hook": f"{RESOURCE_REGISTRATION_HOOK:08X}",
            "deleting_destructor_slot": 0,
            "deleting_destructor": f"{RESOURCE_DELETING_DESTRUCTOR:08X}",
            "destructor": f"{RESOURCE_DESTRUCTOR:08X}",
            "destructor_entry_hook": f"{RESOURCE_DESTRUCTOR:08X}",
            "destructor_exit_hook": f"{RESOURCE_DESTRUCTOR_EXIT_HOOK:08X}",
        },
        "binding": {
            "renderer_bind": f"{RENDERER_BIND:08X}",
            "renderer_graph_field_offset": 72,
            "factory_output_argument": "r5",
            "reference_assignment": f"{REFERENCE_ASSIGN:08X}",
            "existing_resource_path_join": f"{RESOURCE_REGISTRATION_HOOK:08X}",
            "new_resource_path_join": f"{RESOURCE_REGISTRATION_HOOK:08X}",
        },
        "claims": {
            "bound_graph_dynamic_type_proved": True,
            "resource_generation_boundary_proved": True,
            "factory_registration_boundary_proved": True,
            "concrete_building_or_prop_identity_proved": False,
            "streaming_invalidation_proved": False,
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
        print(f"static-world resource discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
