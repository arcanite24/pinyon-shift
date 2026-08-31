#!/usr/bin/env python3
"""Prove exact SimpleModelResource payload-reset transition boundaries."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-streaming.v1"
IMAGE_BASE = 0x82000000
RESOURCE_VTABLE = 0x82229294
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")

RESOURCE_REFRESH = 0x82C46410
DIRECT_RESET = 0x82C46440
DIRECT_RESET_EXIT_HOOK = 0x82C46480
VIRTUAL_RESET = 0x82C222C8
VIRTUAL_RESET_EXIT_HOOK = 0x82C2231C
RESOURCE_PAYLOAD_OFFSET = 64
RESOURCE_GRAPH_OFFSET = 112
RESOURCE_BINDING_OFFSET = 76


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
    if image_u32(image, RESOURCE_VTABLE + 15 * 4) != RESOURCE_REFRESH:
        raise ValueError("SimpleModelResource refresh slot drifted")
    if image_u32(image, RESOURCE_VTABLE + 16 * 4) != DIRECT_RESET:
        raise ValueError("SimpleModelResource direct reset slot drifted")
    if image_u32(image, RESOURCE_VTABLE + 22 * 4) != VIRTUAL_RESET:
        raise ValueError("SimpleModelResource virtual reset slot drifted")

    require_instructions(
        functions,
        RESOURCE_REFRESH,
        {
            0x82C4641C: "addi r5,r3,76",
            0x82C46420: "addi r3,r3,112",
            0x82C46424: "bl 0x82c462d0",
            0x82C46428: "li r3,1",
        },
    )
    require_instructions(
        functions,
        DIRECT_RESET,
        {
            0x82C46450: "mr r31,r3",
            0x82C46454: "lwz r3,64(r3)",
            0x82C46460: "stw r11,64(r31)",
            0x82C4646C: "lwz r11,12(r11)",
            0x82C46474: "bctrl",
            0x82C46478: "addi r3,r31,112",
            0x82C4647C: "bl 0x82c240e0",
            DIRECT_RESET_EXIT_HOOK: "clrlwi r11,r3,24",
        },
    )
    require_instructions(
        functions,
        VIRTUAL_RESET,
        {
            0x82C222DC: "lwz r11,0(r3)",
            0x82C222E0: "mr r30,r3",
            0x82C222E4: "lwz r11,60(r11)",
            0x82C222EC: "bctrl",
            0x82C222F0: "lwz r11,64(r30)",
            0x82C222FC: "stw r10,64(r30)",
            0x82C22310: "lwz r11,12(r10)",
            0x82C22318: "bctrl",
            VIRTUAL_RESET_EXIT_HOOK: "mr r3,r31",
        },
    )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "exact_simple_model_resource_payload_reset_paths",
        "resource": {
            "class": "CSimpleModelResource",
            "vtable": f"{RESOURCE_VTABLE:08X}",
            "payload_reference_offset": RESOURCE_PAYLOAD_OFFSET,
            "graph_offset": RESOURCE_GRAPH_OFFSET,
            "binding_offset": RESOURCE_BINDING_OFFSET,
        },
        "refresh": {
            "slot": 15,
            "method": f"{RESOURCE_REFRESH:08X}",
            "graph_argument": "resource_plus_112",
            "binding_argument": "resource_plus_76",
        },
        "transitions": [
            {
                "kind": "direct_payload_reset",
                "slot": 16,
                "entry_hook": f"{DIRECT_RESET:08X}",
                "exit_hook": f"{DIRECT_RESET_EXIT_HOOK:08X}",
                "exit_resource_register": "r31",
            },
            {
                "kind": "refresh_then_payload_reset",
                "slot": 22,
                "entry_hook": f"{VIRTUAL_RESET:08X}",
                "exit_hook": f"{VIRTUAL_RESET_EXIT_HOOK:08X}",
                "exit_resource_register": "r30",
            },
        ],
        "claims": {
            "owned_payload_reference_field_proved": True,
            "balanced_payload_reset_boundaries_proved": True,
            "payload_generation_invalidation_boundary_proved": True,
            "complete_streaming_invalidation_coverage_proved": False,
            "concrete_building_or_prop_identity_proved": False,
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
        print(f"static-world streaming discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
