#!/usr/bin/env python3
"""Prove title-owned SimpleModel static-world ingress surfaces."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-ingress.v2"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
REVIEWED_THUNKS = {
    0x82585FB8: bytes.fromhex("38 63 FF FC 48 00 01 64"),
}


CLASSES = {
    "simple_mesh": {
        "decorated_name": ".?AVCSimpleMesh@@",
        "type_descriptor": 0x832A62B0,
        "role": "static_world_mesh_resource",
        "surfaces": (
            ("primary", 0x823521C4, 0x822291A0, 6, 0x82C46A08),
        ),
    },
    "simple_sub_model": {
        "decorated_name": ".?AVCSimpleSubModel@@",
        "type_descriptor": 0x832A62CC,
        "role": "static_world_submodel_resource",
        "surfaces": (
            ("primary", 0x82352214, 0x822291BC, 7, 0x82C47A90),
        ),
    },
    "simple_model": {
        "decorated_name": ".?AVCSimpleModel@@",
        "type_descriptor": 0x832A62EC,
        "role": "static_world_model_resource_graph",
        "surfaces": (
            ("secondary", 0x823522C0, 0x822291E8, 7, 0x82C47D98),
            ("primary", 0x82352268, 0x82229208, 9, 0x82C46758),
        ),
    },
    "simple_model_resource": {
        "decorated_name": ".?AVCSimpleModelResource@@",
        "type_descriptor": 0x832A635C,
        "role": "streamed_static_world_model_resource",
        "surfaces": (
            ("primary", 0x82352328, 0x82229294, 23, 0x82C47EC0),
        ),
    },
    "simple_model_renderer": {
        "decorated_name": ".?AVCSimpleModelRenderer@@",
        "type_descriptor": 0x832A671C,
        "role": "static_world_model_renderer",
        "surfaces": (
            ("primary", 0x8235275C, 0x82001B64, 17, 0x82C4C838),
        ),
    },
    "simple_model_renderer_deferred": {
        "decorated_name": ".?AVCSimpleModelRendererDeferred@@",
        "type_descriptor": 0x8322F2AC,
        "role": "deferred_static_world_model_renderer",
        "surfaces": (
            ("secondary", 0x822EF198, 0x82021328, 1, 0x82585FB8),
            ("primary", 0x822EF148, 0x82021334, 16, 0x82596C70),
        ),
    },
    "model_presentation_unified": {
        "decorated_name": ".?AVCModelPresentation@Presentation_Unified@@",
        "type_descriptor": 0x832B9550,
        "role": "unified_static_model_presentation",
        "surfaces": (
            ("secondary", 0x82363464, 0x822432C8, 1, 0x82DE9960),
            ("primary", 0x823633E8, 0x822432D4, 18, 0x82DEA508),
        ),
    },
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
    end = image.find(b"\0", offset, min(offset + 192, len(image)))
    if end < 0:
        raise ValueError(f"image string is unterminated: {address:08X}")
    return image[offset:end].decode("ascii")


def reviewed_thunk_matches(image: bytes, address: int) -> bool:
    expected = REVIEWED_THUNKS.get(address)
    if expected is None:
        return False
    offset = address - IMAGE_BASE
    return image[offset : offset + len(expected)] == expected


def build(functions: set[int], image: bytes) -> dict:
    classes = {}
    all_vtables = set()
    for name, spec in CLASSES.items():
        type_descriptor = spec["type_descriptor"]
        decorated_name = image_string(image, type_descriptor + 8)
        if decorated_name != spec["decorated_name"]:
            raise ValueError(f"{name} RTTI evidence drifted")
        surfaces = []
        for (
            label,
            locator,
            vtable,
            slot_count,
            slot_zero_target,
        ) in spec["surfaces"]:
            if vtable in all_vtables:
                raise ValueError(f"duplicate static-world vtable: {vtable:08X}")
            all_vtables.add(vtable)
            if image_u32(image, locator + 12) != type_descriptor:
                raise ValueError(f"{name} {label} locator drifted")
            if image_u32(image, vtable - 4) != locator:
                raise ValueError(f"{name} {label} vtable locator drifted")
            slots = [
                image_u32(image, vtable + index * 4)
                for index in range(slot_count)
            ]
            if slots[0] != slot_zero_target:
                raise ValueError(f"{name} {label} slot-zero target drifted")
            ungenerated = [
                target
                for target in slots
                if target not in functions
                and not reviewed_thunk_matches(image, target)
            ]
            if ungenerated:
                raise ValueError(f"{name} {label} has an unknown slot target")
            if image_u32(image, vtable + slot_count * 4) in functions:
                raise ValueError(f"{name} {label} vtable extent drifted")
            surfaces.append(
                {
                    "label": label,
                    "complete_object_locator": f"{locator:08X}",
                    "vtable_address": f"{vtable:08X}",
                    "vtable_slot_count": slot_count,
                    "slot_zero_target": f"{slot_zero_target:08X}",
                    "slot_targets": [f"{target:08X}" for target in slots],
                    "reviewed_thunk_slots": [
                        index
                        for index, target in enumerate(slots)
                        if target in REVIEWED_THUNKS
                    ],
                }
            )
        classes[name] = {
            "decorated_name": decorated_name,
            "type_descriptor": f"{type_descriptor:08X}",
            "role": spec["role"],
            "surfaces": surfaces,
        }

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "title_simple_model_static_world_ingress_proved",
        "classes": classes,
        "topology": {
            "mesh_submodel_model_resource_chain": [
                "simple_mesh",
                "simple_sub_model",
                "simple_model",
                "simple_model_resource",
            ],
            "renderer_presentation_chain": [
                "simple_model_renderer",
                "simple_model_renderer_deferred",
                "model_presentation_unified",
            ],
            "all_vtables_distinct": True,
            "all_slots_aot_or_reviewed_thunk_backed": True,
            "streaming_lifetime_proved": False,
            "building_or_prop_instance_identity_proved": False,
        },
        "next_runtime_join": {
            "source": "title_simple_model_renderer_and_presentation_lifetimes",
            "destination": "procedural_model_prepared_record_identity",
            "required_evidence": (
                "exact_shared_object_or_resource_identity_at_both_boundaries"
            ),
            "proved": False,
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
        print(f"static-world ingress discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
