#!/usr/bin/env python3
"""Lock the title-owned vehicle tire/wheel asset-material binding edge."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-vehicle-asset-material.v1"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
INSTRUCTION_RE = re.compile(r"^\s*// (.+)$")
PATH_BUILDER = 0x82543558
BINDING_FUNCTION = 0x82549670
CAR_RESOURCE_CONSTRUCTOR = 0x824D11B0
EXPECTED_TYPES = (
    (
        ".?AVCCarMaterialSettingsResourceType@@",
        0x8322C978,
        0x822EC784,
        0x82020B4C,
        9,
    ),
    (
        ".?AVCCarModelResourceType@@",
        0x8322CD44,
        0x822ECC3C,
        0x82020CB8,
        9,
    ),
    (
        ".?AVCCarMaterialSettingsResource@@",
        0x832B41D0,
        0x8235E0B4,
        0x8223FEDC,
        23,
    ),
    (
        ".?AVCCarModelResource@@",
        0x832B43A0,
        0x8235E470,
        0x82240B54,
        23,
    ),
)
EXPECTED_STRINGS = (
    (0x8201A254, ";game:\\media\\cars\\shared\\ShaderSettings\\Tire\\ui.xml"),
    (0x8201A288, "\\ShaderSettings\\Tire\\"),
    (0x8201A2C0, "game:\\media\\Wheels\\"),
    (0x8201A2D4, "game:\\media\\cars\\shared\\ShaderSettings\\Tire\\Slod.xml;"),
    (0x8201A30C, "game:\\media\\cars\\shared\\ShaderSettings\\Tire\\Normal.xml;"),
    (0x82021CEC, "CarMaterialSettings Resources"),
    (0x82021D8C, "CarModel Resources"),
)


def image_u32(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise ValueError(f"image address is out of range: {address:08X}")
    return int.from_bytes(image[offset : offset + 4], "big")


def image_string(image: bytes, address: int) -> str:
    offset = address - IMAGE_BASE
    if offset < 0 or offset >= len(image):
        raise ValueError(f"image string is out of range: {address:08X}")
    end = image.find(b"\0", offset, min(offset + 512, len(image)))
    if end < 0:
        raise ValueError(f"image string is unterminated: {address:08X}")
    return image[offset:end].decode("ascii")


def parse_sources(paths: list[pathlib.Path]) -> tuple[set[int], dict[int, list[str]]]:
    functions: set[int] = set()
    bodies: dict[int, list[str]] = {}
    for path in sorted(paths, key=lambda item: item.as_posix()):
        active = None
        for line in path.read_text(encoding="utf-8").splitlines():
            match = FUNCTION_RE.match(line)
            if match:
                active = int(match.group(1), 16)
                functions.add(active)
                bodies[active] = []
                continue
            instruction = INSTRUCTION_RE.match(line)
            if active is not None and instruction:
                bodies[active].append(instruction.group(1).strip())
    return functions, bodies


def require_ordered(body: list[str], expected: tuple[str, ...], label: str) -> None:
    cursor = 0
    for instruction in body:
        if cursor < len(expected) and instruction == expected[cursor]:
            cursor += 1
    if cursor != len(expected):
        raise ValueError(f"{label} instruction contract drifted")


def build(functions: set[int], bodies: dict[int, list[str]], image: bytes) -> dict:
    missing = sorted(
        {PATH_BUILDER, BINDING_FUNCTION, CAR_RESOURCE_CONSTRUCTOR} - functions
    )
    if missing:
        raise ValueError(
            "vehicle asset-material functions are missing: "
            + ",".join(f"{value:08X}" for value in missing)
        )
    for address, expected in EXPECTED_STRINGS:
        if image_string(image, address) != expected:
            raise ValueError(f"title string drifted at {address:08X}")

    require_ordered(
        bodies[PATH_BUILDER],
        (
            "mr r29,r3",
            "mr r31,r4",
            "mr r30,r5",
            "addi r5,r11,-23796",
            "addi r5,r11,-23852",
            "addi r5,r11,-23872",
            "addi r5,r31,1712",
            "addi r31,r11,-23880",
            "addi r5,r11,-23896",
            "addi r5,r11,-23904",
            "addi r4,r1,80",
            "bl 0x82450f48",
            "mr r3,r29",
        ),
        "tire/wheel path builder",
    )
    require_ordered(
        bodies[BINDING_FUNCTION],
        (
            "mr r31,r4",
            "mr r30,r5",
            "mr r4,r3",
            "mr r5,r6",
            "bl 0x82543558",
            "mr r3,r31",
            "bl 0x82480fc0",
            "mr r3,r31",
            "bl 0x825434a0",
        ),
        "vehicle material binding",
    )
    constructor = bodies[CAR_RESOURCE_CONSTRUCTOR]
    if constructor.count("bl 0x82549670") != 2:
        raise ValueError("car resource binding call count drifted")
    require_ordered(
        constructor,
        (
            "addi r4,r31,1056",
            "mr r3,r31",
            "bl 0x82549670",
            "addi r29,r31,1056",
            "mr r4,r29",
            "mr r3,r31",
            "bl 0x82549670",
        ),
        "car resource owner relation",
    )

    types = []
    for name, descriptor, locator, vtable, slot_count in EXPECTED_TYPES:
        if image_string(image, descriptor + 8) != name:
            raise ValueError(f"{name} type descriptor drifted")
        if image_u32(image, locator + 12) != descriptor:
            raise ValueError(f"{name} complete-object locator drifted")
        if any(
            image_u32(image, vtable + index * 4) not in functions
            for index in range(slot_count)
        ):
            raise ValueError(f"{name} vtable drifted")
        types.append(
            {
                "decorated_name": name,
                "type_descriptor": f"{descriptor:08X}",
                "complete_object_locator": f"{locator:08X}",
                "primary_vtable": f"{vtable:08X}",
                "slot_count": slot_count,
            }
        )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "exact_title_owned_vehicle_asset_material_binding",
        "types": types,
        "contracts": {
            "path_builder": f"{PATH_BUILDER:08X}",
            "binding_function": f"{BINDING_FUNCTION:08X}",
            "car_resource_constructor": f"{CAR_RESOURCE_CONSTRUCTOR:08X}",
            "binding_object_offset": 1056,
            "asset_key_offset": 1712,
            "binding_call_count": 2,
            "title_semantic": "tire_wheel_shader_settings",
            "runtime_hook": "82549670:r3_root,r4_binding,r5_load_ui,r6_slod",
            "draw_join": "exact_title_draw_argument_address",
        },
        "summary": {
            "resource_type_count": len(types),
            "title_owned_asset_material_discriminator_proved": True,
            "tire_wheel_material_family_proved": True,
            "semantic_mesh_material_roles_proved": False,
            "geometry_resource_join_proved": False,
            "runtime_qualification_required": True,
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
        functions, bodies = parse_sources(paths)
        document = build(functions, bodies, args.image.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"vehicle asset-material discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
