#!/usr/bin/env python3
"""Prove bounded SimpleMesh draw and material-binding field semantics."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-mesh-semantics.v2"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")

RENDERER_DISPATCH = 0x82C4CCC8
PRIMITIVE_COUNT_HELPER = 0x82C48558
PRIMITIVE_SCALE_BIAS_TABLE = 0x820023F0
INDEX_BUFFER_BIND = 0x8244D760
DRAW_STATE_FLUSH = 0x8240BB40
MATERIAL_STATE_BIND = 0x82410A70
MATERIAL_RESOURCE_BIND = 0x8244E728
DRAW_EMITTER = 0x82416380

EXPECTED_SCALE_BIAS = (
    (0, 0),
    (1, 0),
    (2, 0),
    (1, 1),
    (3, 0),
    (1, 2),
    (1, 2),
    (0, 0),
    (3, 0),
    (0, 0),
    (0, 0),
    (0, 0),
    (0, 0),
    (4, 0),
)


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
    scale_bias = tuple(
        (
            image_u32(image, PRIMITIVE_SCALE_BIAS_TABLE + index * 8),
            image_u32(image, PRIMITIVE_SCALE_BIAS_TABLE + index * 8 + 4),
        )
        for index in range(len(EXPECTED_SCALE_BIAS))
    )
    if scale_bias != EXPECTED_SCALE_BIAS:
        raise ValueError("primitive scale/bias table drifted")

    require_instructions(
        functions,
        PRIMITIVE_COUNT_HELPER,
        {
            0x82C48558: "mr r11,r3",
            0x82C48568: "cmpwi cr6,r3,1",
            0x82C48570: "cmpwi cr6,r3,2",
            0x82C48578: "cmpwi cr6,r3,3",
            0x82C48580: "cmpwi cr6,r3,4",
            0x82C48588: "li r11,3",
            0x82C4858C: "divw r3,r4,r11",
            0x82C48594: "addi r3,r4,-1",
            0x82C4859C: "srawi r11,r4,1",
            0x82C485A8: "mr r3,r4",
            0x82C485B0: "cmpwi cr6,r11,6",
            0x82C485B8: "cmpwi cr6,r11,8",
            0x82C485C0: "cmpwi cr6,r11,13",
            0x82C485D0: "srawi r11,r4,2",
            0x82C485D8: "addi r3,r4,-2",
        },
    )
    require_instructions(
        functions,
        RENDERER_DISPATCH,
        {
            0x82C4DAF8: "bctrl",
            0x82C4DAFC: "lbz r11,112(r3)",
            0x82C4DB0C: "lbz r7,39(r3)",
            0x82C4DB14: "lwz r5,32(r3)",
            0x82C4DB24: "bl 0x82410a70",
            0x82C4DB3C: "bctrl",
            0x82C4DB5C: "bctrl",
            0x82C4DB60: "lwz r11,128(r3)",
            0x82C4DB6C: "addi r4,r3,128",
            0x82C4DB90: "lwz r3,168(r11)",
            0x82C4DB9C: "lwz r11,20(r11)",
            0x82C4DBB4: "bl 0x8244e728",
            0x82C4DBE4: "bl 0x8244e728",
            0x82C4DC10: "lwz r4,96(r28)",
            0x82C4DC14: "bl 0x8244d760",
            0x82C4DC18: "lwz r3,68(r30)",
            0x82C4DC1C: "bl 0x8240bb40",
            0x82C4DC20: "lwz r3,36(r28)",
            0x82C4DC24: "lwz r4,100(r28)",
            0x82C4DC28: "bl 0x82c48558",
            0x82C4DC2C: "lwz r4,36(r28)",
            0x82C4DC38: "rlwinm r10,r4,3,0,28",
            0x82C4DC40: "lwzx r9,r10,r25",
            0x82C4DC44: "lwzx r11,r10,r11",
            0x82C4DC48: "mullw r10,r9,r3",
            0x82C4DC4C: "add r7,r10,r11",
            0x82C4DC54: "bl 0x82416380",
            0x82C4DC58: "li r4,0",
            0x82C4DC60: "bl 0x8244d760",
        },
    )
    require_instructions(
        functions,
        INDEX_BUFFER_BIND,
        {
            0x8244D76C: "lwz r30,12812(r3)",
            0x8244D774: "mr r29,r4",
            0x8244D7E4: "stw r29,12812(r31)",
        },
    )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "bounded_simple_mesh_draw_and_material_binding",
        "geometry": {
            "class": "CSimpleMesh",
            "vtable": "822291A0",
            "primitive_type_offset": 36,
            "index_buffer_binding_offset": 96,
            "source_element_count_offset": 100,
            "primitive_count_helper": f"{PRIMITIVE_COUNT_HELPER:08X}",
            "primitive_scale_bias_table": f"{PRIMITIVE_SCALE_BIAS_TABLE:08X}",
            "primitive_scale_bias": [
                {"primitive_type": index, "scale": scale, "bias": bias}
                for index, (scale, bias) in enumerate(scale_bias)
            ],
            "index_buffer_bind": f"{INDEX_BUFFER_BIND:08X}",
            "index_buffer_context_offset": 12812,
            "draw_emitter": f"{DRAW_EMITTER:08X}",
            "draw_arguments": {
                "r3": "graphics_context",
                "r4": "mesh_plus_36_primitive_type",
                "r5": "zero_base_index",
                "r6": "zero_index_offset",
                "r7": "scale_times_primitive_count_plus_bias",
            },
            "index_buffer_clear_after_draw": True,
        },
        "material_binding": {
            "class": "CSimpleSubModel_and_CSimpleMesh",
            "submodel_state_enabled_offset": 112,
            "submodel_state_selector_offset": 39,
            "submodel_state_object_offset": 32,
            "state_bind": f"{MATERIAL_STATE_BIND:08X}",
            "mesh_optional_reference_offset": 128,
            "optional_reference_resource_offset": 168,
            "optional_reference_dispatch_slot": 5,
            "resource_bind": f"{MATERIAL_RESOURCE_BIND:08X}",
            "fallback_source": "renderer_r22",
        },
        "prepared_layout_boundary": {
            "draw_state_flush": f"{DRAW_STATE_FLUSH:08X}",
            "flush_after_index_buffer_bind": True,
            "flush_before_draw_emitter": True,
            "runtime_source": "xenos_decoded_draw_observation",
            "runtime_join": "exact_physical_pm4_header_origin",
            "vertex_binding_limit": 8,
            "vertex_attribute_limit": 32,
            "float_constant_limit_per_stage": 64,
            "texture_state_limit": 16,
            "payload_bytes_exported": False,
        },
        "claims": {
            "primitive_and_element_count_fields_proved": True,
            "index_buffer_bind_draw_clear_sequence_proved": True,
            "submodel_state_binding_fields_proved": True,
            "optional_material_resource_branch_proved": True,
            "complete_vertex_layout_runtime_boundary_proved": True,
            "bounded_material_parameter_runtime_boundary_proved": True,
            "complete_vertex_layout_decoding_proved": False,
            "complete_material_parameter_decoding_proved": False,
            "native_draw_admission_proved": False,
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
        print(f"static-world mesh semantics discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
