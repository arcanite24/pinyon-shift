#!/usr/bin/env python3
"""Lock the retail player/traffic map-entity semantic ingress."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-vehicle-player-ingress.v1"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
INSTRUCTION_RE = re.compile(r"^\s*// (.+)$")
GET_VEHICLE_ID = 0x82BBA010
GET_TYPE_NAME = 0x82BBA1B8
SET_VEHICLE_ID = 0x82CCF228
BASE_CONSTRUCTOR = 0x82558510
AI_CONSTRUCTOR = 0x82558698
PLAYER_LOCAL_CONSTRUCTOR = 0x82558620
VEHICLE_MAP_POOL_CONSTRUCTOR = 0x8255B238
VEHICLE_MAP_POOL_INSTALLER = 0x82629088
COMMON_METHODS = (
    0x82559FE0,
    0x82611B80,
    0x82558590,
    GET_TYPE_NAME,
    0x82CD1900,
    0x825585A0,
    0x825585B8,
    0x825585E0,
    0x825585F8,
    SET_VEHICLE_ID,
    0x82CCF240,
    GET_VEHICLE_ID,
    0x82CCF260,
)

# name, type descriptor, complete-object locator, primary vtable,
# title-owned type-name pointer, title-owned type name, slot-zero target.
EXPECTED_TYPES = (
    (
        ".?AVCMapEntityVehicleBase@@",
        0x83227960,
        0x822E7924,
        0x8201D338,
        0x8201D36C,
        "vehicle_type",
        0x82559FE0,
    ),
    (
        ".?AVCMapEntityVehiclePlayerLocal@@",
        0x83227984,
        0x822E7970,
        0x8201D380,
        0x8201D3B4,
        "player_local",
        0x82559FE0,
    ),
    (
        ".?AVCMapEntityVehicleAI@@",
        0x832279B0,
        0x822E79C0,
        0x8201D3C8,
        0x8201D3FC,
        "ai",
        0x82559FE0,
    ),
    (
        ".?AVCMapEntityVehicleFestivalTraffic@@",
        0x83227A20,
        0x822E7AA4,
        0x8201D430,
        0x8201D464,
        "traffic",
        0x82559FE0,
    ),
    (
        ".?AVCMapEntityVehicleRemotePlayer@@",
        0x83227A9C,
        0x822E7B88,
        0x8201D4B0,
        0x8201D4E4,
        "player_remote",
        0x8255A7C8,
    ),
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
    end = image.find(b"\0", offset, min(offset + 256, len(image)))
    if end < 0:
        raise ValueError(f"image string is unterminated: {address:08X}")
    return image[offset:end].decode("ascii")


def parse_function_sources(paths: list[pathlib.Path]) -> tuple[set[int], dict[int, list[str]]]:
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
    required_functions = {
        target
        for expected in EXPECTED_TYPES
        for target in ((expected[6],) + COMMON_METHODS[1:])
    } | {
        BASE_CONSTRUCTOR,
        AI_CONSTRUCTOR,
        PLAYER_LOCAL_CONSTRUCTOR,
        VEHICLE_MAP_POOL_CONSTRUCTOR,
        VEHICLE_MAP_POOL_INSTALLER,
    }
    missing = sorted(required_functions - functions)
    if missing:
        raise ValueError(
            "vehicle ingress functions are missing: "
            + ",".join(f"{value:08X}" for value in missing)
        )

    require_ordered(
        bodies.get(GET_VEHICLE_ID, []),
        ("lwz r3,12(r3)", "blr"),
        "vehicle ID getter",
    )
    require_ordered(
        bodies.get(GET_TYPE_NAME, []),
        ("lwz r3,16(r3)", "blr"),
        "vehicle type-name getter",
    )
    require_ordered(
        bodies.get(SET_VEHICLE_ID, []),
        ("stw r4,12(r3)", "stfs f0,8(r3)", "blr"),
        "vehicle ID setter",
    )
    require_ordered(
        bodies.get(BASE_CONSTRUCTOR, []),
        ("stw r30,16(r31)", "stw r9,0(r31)"),
        "vehicle base constructor",
    )
    require_ordered(
        bodies.get(AI_CONSTRUCTOR, []),
        (
            "addi r4,r11,-11268",
            "bl 0x82558510",
            "addi r11,r11,-11320",
            "stw r11,0(r31)",
        ),
        "AI constructor",
    )
    require_ordered(
        bodies.get(PLAYER_LOCAL_CONSTRUCTOR, []),
        (
            "lis r11,-32254",
            "addi r4,r11,-11340",
            "bl 0x82558510",
            "lis r9,-32254",
            "addi r9,r9,-11392",
            "stw r9,0(r31)",
        ),
        "player-local constructor",
    )
    require_ordered(
        bodies.get(VEHICLE_MAP_POOL_CONSTRUCTOR, []),
        (
            "stw r4,16(r3)",
            "addi r3,r3,32",
            "bl 0x82558620",
            "addi r29,r31,144",
            "li r30,6",
            "bl 0x82558698",
        ),
        "vehicle-map pool constructor",
    )
    require_ordered(
        bodies.get(VEHICLE_MAP_POOL_INSTALLER, []),
        (
            "li r3,1792",
            "bl 0x82c0f6c0",
            "lwz r4,4(r31)",
            "bl 0x8255b238",
            "stw r3,24(r31)",
        ),
        "vehicle-map pool installer",
    )

    types = []
    for (
        decorated_name,
        type_descriptor,
        locator,
        vtable,
        type_name_address,
        type_name,
        slot_zero,
    ) in EXPECTED_TYPES:
        if image_u32(image, locator + 12) != type_descriptor:
            raise ValueError(f"{decorated_name} locator drifted")
        if image_string(image, type_descriptor + 8) != decorated_name:
            raise ValueError(f"{decorated_name} descriptor drifted")
        observed_methods = tuple(image_u32(image, vtable + index * 4) for index in range(13))
        expected_methods = (slot_zero,) + COMMON_METHODS[1:]
        if observed_methods != expected_methods:
            raise ValueError(f"{decorated_name} vtable drifted")
        if image_string(image, type_name_address) != type_name:
            raise ValueError(f"{decorated_name} type-name pointer drifted")
        types.append(
            {
                "decorated_name": decorated_name,
                "type_descriptor": f"{type_descriptor:08X}",
                "complete_object_locator": f"{locator:08X}",
                "primary_vtable": f"{vtable:08X}",
                "slot_count": 13,
                "type_name_address": f"{type_name_address:08X}",
                "type_name": type_name,
                "vehicle_id_offset": 12,
                "type_name_pointer_offset": 16,
                "methods": [f"{target:08X}" for target in observed_methods],
            }
        )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "exact_vehicle_player_traffic_semantic_ingress",
        "types": types,
        "contracts": {
            "vehicle_id_getter": f"{GET_VEHICLE_ID:08X}",
            "vehicle_id_getter_behavior": "return_u32_at_receiver_plus_12",
            "type_name_getter": f"{GET_TYPE_NAME:08X}",
            "type_name_getter_behavior": "return_pointer_at_receiver_plus_16",
            "vehicle_id_setter": f"{SET_VEHICLE_ID:08X}",
            "base_constructor": f"{BASE_CONSTRUCTOR:08X}",
            "ai_constructor": f"{AI_CONSTRUCTOR:08X}",
            "player_local_constructor": f"{PLAYER_LOCAL_CONSTRUCTOR:08X}",
            "vehicle_map_pool_constructor": f"{VEHICLE_MAP_POOL_CONSTRUCTOR:08X}",
            "vehicle_map_pool_installer": f"{VEHICLE_MAP_POOL_INSTALLER:08X}",
            "vehicle_map_pool_install_store": "826291A8",
            "player_local_pool_offset": 32,
            "pool_context_offset": 16,
            "pool_root_pointer_offset": 24,
            "runtime_join_required": True,
        },
        "summary": {
            "type_count": len(types),
            "player_local_type_count": sum(
                item[5] == "player_local" for item in EXPECTED_TYPES
            ),
            "shared_method_count": 12,
            "exact_player_discriminator_proved": True,
            "player_pose_relation_proved": False,
            "mesh_material_role_identity_proved": False,
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
        functions, bodies = parse_function_sources(paths)
        document = build(functions, bodies, args.image.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"vehicle player ingress discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
