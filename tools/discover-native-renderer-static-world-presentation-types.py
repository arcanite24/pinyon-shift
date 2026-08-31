#!/usr/bin/env python3
"""Enumerate exact RTTI types derived from unified CModelPresentation."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-presentation-types.v1"
IMAGE_BASE = 0x82000000
MODEL_PRESENTATION_TYPE = 0x832B9550
MODEL_PRESENTATION_DRAW = 0x823F8DB8
MODEL_PRESENTATION_SLOT = 12
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
MODEL_PRESENTATION_NAME = ".?AVCModelPresentation@Presentation_Unified@@"
REFCOUNTED_PRESENTATION_NAME = (
    ".?AV?$TRefCountedObjectThreadSafe@"
    "VCModelPresentation@Presentation_Unified@@@@"
)
EXPECTED_SURFACES = {
    0x823633E8: (MODEL_PRESENTATION_NAME, 0, 0x822432D4, 18, True),
    0x82363464: (MODEL_PRESENTATION_NAME, 8, 0x822432C8, 1, False),
    0x82363534: (REFCOUNTED_PRESENTATION_NAME, 0, 0x82002464, 18, True),
    0x82363598: (REFCOUNTED_PRESENTATION_NAME, 8, 0x822433A0, 1, False),
}


def parse_function_addresses(paths: list[pathlib.Path]) -> set[int]:
    functions = set()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = FUNCTION_RE.match(line)
            if match:
                functions.add(int(match.group(1), 16))
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
    end = image.find(b"\0", offset, min(offset + 256, len(image)))
    if end < 0:
        raise ValueError(f"image string is unterminated: {address:08X}")
    return image[offset:end].decode("ascii")


def parse_locator(image: bytes, locator: int) -> dict | None:
    try:
        if image_u32(image, locator) != 0:
            return None
        object_offset = image_u32(image, locator + 4)
        constructor_displacement = image_u32(image, locator + 8)
        type_descriptor = image_u32(image, locator + 12)
        hierarchy = image_u32(image, locator + 16)
        decorated_name = image_string(image, type_descriptor + 8)
        if not decorated_name.startswith(".?A"):
            return None
        if image_u32(image, hierarchy) != 0:
            return None
        hierarchy_attributes = image_u32(image, hierarchy + 4)
        base_count = image_u32(image, hierarchy + 8)
        base_array = image_u32(image, hierarchy + 12)
        if not 1 <= base_count <= 128:
            return None
        bases = []
        for index in range(base_count):
            descriptor = image_u32(image, base_array + index * 4)
            base_type = image_u32(image, descriptor)
            bases.append(
                {
                    "type_descriptor": base_type,
                    "decorated_name": image_string(image, base_type + 8),
                    "contained_bases": image_u32(image, descriptor + 4),
                    "member_displacement": image_u32(image, descriptor + 8),
                    "vbtable_displacement": image_u32(image, descriptor + 12),
                    "vbase_displacement": image_u32(image, descriptor + 16),
                    "attributes": image_u32(image, descriptor + 20),
                }
            )
        if bases[0]["type_descriptor"] != type_descriptor:
            return None
        return {
            "locator": locator,
            "object_offset": object_offset,
            "constructor_displacement": constructor_displacement,
            "type_descriptor": type_descriptor,
            "decorated_name": decorated_name,
            "hierarchy": hierarchy,
            "hierarchy_attributes": hierarchy_attributes,
            "bases": bases,
        }
    except (UnicodeDecodeError, ValueError):
        return None


def find_locators(image: bytes) -> list[dict]:
    locators = []
    for offset in range(0, len(image) - 20, 4):
        if image[offset : offset + 4] != b"\0\0\0\0":
            continue
        locator = parse_locator(image, IMAGE_BASE + offset)
        if locator is not None:
            locators.append(locator)
    return locators


def find_vtables(
    image: bytes, functions: set[int], locator: int
) -> list[dict]:
    needle = locator.to_bytes(4, "big")
    results = []
    offset = image.find(needle)
    while offset >= 0:
        if offset % 4 == 0:
            vtable = IMAGE_BASE + offset + 4
            slots = []
            for index in range(64):
                try:
                    target = image_u32(image, vtable + index * 4)
                except ValueError:
                    break
                if target not in functions:
                    break
                slots.append(target)
            if slots:
                slot_12_target = (
                    slots[MODEL_PRESENTATION_SLOT]
                    if len(slots) > MODEL_PRESENTATION_SLOT
                    else None
                )
                results.append(
                    {
                        "vtable": vtable,
                        "slot_count": len(slots),
                        "slot_zero_target": slots[0],
                        "slot_12_target": slot_12_target,
                        "inherits_model_presentation_draw": (
                            slot_12_target == MODEL_PRESENTATION_DRAW
                        ),
                    }
                )
        offset = image.find(needle, offset + 1)
    return results


def build(functions: set[int], image: bytes) -> dict:
    target_name = image_string(image, MODEL_PRESENTATION_TYPE + 8)
    if target_name != MODEL_PRESENTATION_NAME:
        raise ValueError("CModelPresentation RTTI evidence drifted")
    types = []
    for locator in find_locators(image):
        base_types = {base["type_descriptor"] for base in locator["bases"]}
        if MODEL_PRESENTATION_TYPE not in base_types:
            continue
        vtables = find_vtables(image, functions, locator["locator"])
        types.append(
            {
                "decorated_name": locator["decorated_name"],
                "type_descriptor": f"{locator['type_descriptor']:08X}",
                "complete_object_locator": f"{locator['locator']:08X}",
                "object_offset": locator["object_offset"],
                "constructor_displacement": locator[
                    "constructor_displacement"
                ],
                "hierarchy": f"{locator['hierarchy']:08X}",
                "base_count": len(locator["bases"]),
                "base_names": [base["decorated_name"] for base in locator["bases"]],
                "vtables": [
                    {
                        "address": f"{surface['vtable']:08X}",
                        "slot_count": surface["slot_count"],
                        "slot_zero_target": f"{surface['slot_zero_target']:08X}",
                        "slot_12_target": (
                            f"{surface['slot_12_target']:08X}"
                            if surface["slot_12_target"] is not None
                            else None
                        ),
                        "inherits_model_presentation_draw": surface[
                            "inherits_model_presentation_draw"
                        ],
                    }
                    for surface in vtables
                ],
            }
        )
    types.sort(
        key=lambda item: (
            item["decorated_name"],
            item["complete_object_locator"],
        )
    )
    exact_base = [
        item
        for item in types
        if item["type_descriptor"] == f"{MODEL_PRESENTATION_TYPE:08X}"
        and item["object_offset"] == 0
    ]
    if len(exact_base) != 1:
        raise ValueError("exact CModelPresentation primary surface drifted")
    observed = {}
    for item in types:
        if len(item["vtables"]) != 1:
            raise ValueError("presentation surface vtable count drifted")
        surface = item["vtables"][0]
        observed[int(item["complete_object_locator"], 16)] = (
            item["decorated_name"],
            item["object_offset"],
            int(surface["address"], 16),
            surface["slot_count"],
            surface["inherits_model_presentation_draw"],
        )
    if observed != EXPECTED_SURFACES:
        raise ValueError("unified model-presentation type census drifted")
    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "exact_unified_model_presentation_type_census",
        "base_class": {
            "decorated_name": target_name,
            "type_descriptor": f"{MODEL_PRESENTATION_TYPE:08X}",
            "draw_slot": MODEL_PRESENTATION_SLOT,
            "draw_target": f"{MODEL_PRESENTATION_DRAW:08X}",
        },
        "types": types,
        "summary": {
            "locator_count": len(types),
            "unique_type_count": len(
                {item["type_descriptor"] for item in types}
            ),
            "inherited_draw_surface_count": sum(
                surface["inherits_model_presentation_draw"]
                for item in types
                for surface in item["vtables"]
            ),
            "concrete_building_or_prop_identity_proved": False,
        },
        "safety": {
            "static_analysis_only": True,
            "guest_payload_exported": False,
            "runtime_hook_enabled": False,
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
        document = build(
            parse_function_addresses(paths), args.image.read_bytes()
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(
            f"static-world presentation type discovery failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
