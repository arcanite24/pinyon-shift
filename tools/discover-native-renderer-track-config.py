"""Prove the title-owned track-render differential controls from AOT code."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-track-config.v3"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")

COMMAND_LINE_FUNCTION = 0x824F8150
RUNTIME_COPY_FUNCTION = 0x8259C7D8
COMMAND_LINE_VTABLE = 0x8200E724
COMMAND_LINE_TYPE = ".?AVCForzaCommandLineParameters@@"
TRACK_FAR_DEFAULT_FUNCTION = 0x824F7898
TRACK_FAR_DEFAULT_VALUE = 55.0
TRACK_FAR_DEFAULT_BITS = 0x425C0000

OPTIONS = {
    "perfmode": {
        "string": 0x8200FF44,
        "field": 4200,
        "field_instruction": (0x824F9544, "addi r29,r31,4200"),
        "name_instruction": (0x824F9548, "addi r4,r11,-188"),
        "parse_instruction": (0x824F9554, "bl 0x82c096e0"),
        "kind": "boolean_master",
    },
    "fasttrackrender": {
        "string": 0x8200FEB8,
        "field": 4204,
        "field_instruction": (0x824F965C, "addi r25,r31,4204"),
        "name_instruction": (0x824F9660, "addi r4,r11,-328"),
        "parse_instruction": (0x824F966C, "bl 0x82c096e0"),
        "kind": "boolean_family",
    },
    "trackfardistance": {
        "string": 0x8200FF30,
        "field": 4176,
        "field_instruction": (0x824F95AC, "addi r5,r31,4176"),
        "name_instruction": (0x824F95B0, "addi r4,r11,-208"),
        "parse_instruction": (0x824F95B8, "bl 0x82c09648"),
        "kind": "floating_distance",
    },
    "renderroaddetailblur": {
        "string": 0x82010004,
        "field": 4181,
        "field_instruction": (0x824F9448, "addi r5,r31,4181"),
        "name_instruction": (0x824F944C, "addi r4,r11,4"),
        "parse_instruction": (0x824F9454, "bl 0x82c096e0"),
        "kind": "boolean_effect",
    },
    "notrackcommandbuffers": {
        "string": 0x82010A88,
        "field": 2732,
        "field_instruction": (0x824F85AC, "addi r5,r31,2732"),
        "name_instruction": (0x824F85B0, "addi r4,r11,2696"),
        "parse_instruction": (0x824F85BC, "bl 0x82c096e0"),
        "kind": "boolean_command_buffer_control",
    },
}

RUNTIME_COPIES = {
    "fasttrackrender": {
        "source": (0x8259C830, "lbz r11,4204(r30)"),
        "destination": (0x8259C834, "stb r11,6297(r31)"),
        "runtime_offset": 6297,
        "transform": "identity",
    },
    "renderroaddetailblur": {
        "source": (0x8259C898, "lbz r11,4181(r30)"),
        "destination": (0x8259C89C, "stb r11,6035(r31)"),
        "runtime_offset": 6035,
        "transform": "identity",
    },
    "notrackcommandbuffers": {
        "source": (0x8259C8D0, "lbz r11,2732(r30)"),
        "destination": (0x8259C8DC, "stb r11,6232(r31)"),
        "runtime_offset": 6232,
        "transform": "boolean_inverted_before_store",
    },
}

PERFMODE_FANOUT = {
    0x824F956C: "stb r11,4201(r31)",
    0x824F9570: "stb r11,4202(r31)",
    0x824F9574: "stb r11,4203(r31)",
    0x824F9578: "stb r11,4204(r31)",
    0x824F957C: "stb r11,4205(r31)",
    0x824F9580: "stb r11,4206(r31)",
    0x824F9584: "stb r11,4207(r31)",
    0x824F9588: "stb r11,4208(r31)",
    0x824F958C: "stb r11,4209(r31)",
}


def parse_functions(paths: list[pathlib.Path]) -> dict[int, dict[int, str]]:
    functions: dict[int, dict[int, str]] = {}
    current: dict[int, str] | None = None
    address: int | None = None
    for path in sorted(paths, key=lambda item: item.as_posix()):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = FUNCTION_RE.match(line)
            if match:
                function_address = int(match.group(1), 16)
                current = {}
                functions[function_address] = current
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


def image_string(image: bytes, address: int) -> str:
    offset = address - IMAGE_BASE
    if offset < 0 or offset >= len(image):
        raise ValueError(f"image string is out of range: {address:08X}")
    end = image.find(b"\0", offset, min(offset + 128, len(image)))
    if end < 0:
        raise ValueError(f"image string is unterminated: {address:08X}")
    return image[offset:end].decode("ascii")


def require(function: dict[int, str], address: int, text: str, label: str) -> None:
    if function.get(address) != text:
        raise ValueError(f"{label} evidence drifted at {address:08X}")


def build(functions: dict[int, dict[int, str]], image: bytes) -> dict:
    command_line = functions.get(COMMAND_LINE_FUNCTION)
    runtime_copy = functions.get(RUNTIME_COPY_FUNCTION)
    track_far_default = functions.get(TRACK_FAR_DEFAULT_FUNCTION)
    if command_line is None or runtime_copy is None or track_far_default is None:
        raise ValueError("track configuration function set is incomplete")

    locator = image_u32(image, COMMAND_LINE_VTABLE - 4)
    type_descriptor = image_u32(image, locator + 12)
    decorated_name = image_string(image, type_descriptor + 8)
    slot_target = image_u32(image, COMMAND_LINE_VTABLE + 4 * 4)
    if decorated_name != COMMAND_LINE_TYPE or slot_target != COMMAND_LINE_FUNCTION:
        raise ValueError("command-line parameter RTTI/vtable evidence drifted")

    require(command_line, 0x824F815C, "mr r31,r3", "command-line receiver")
    option_rows = []
    for name, option in OPTIONS.items():
        if image_string(image, option["string"]) != name:
            raise ValueError(f"{name} string evidence drifted")
        for key in ("field_instruction", "name_instruction", "parse_instruction"):
            address, text = option[key]
            require(command_line, address, text, f"{name} {key}")
        option_rows.append(
            {
                "name": name,
                "string_address": f"{option['string']:08X}",
                "command_line_field_offset": option["field"],
                "registration_address": f"{option['name_instruction'][0]:08X}",
                "parser_kind": option["kind"],
            }
        )

    for address, text in PERFMODE_FANOUT.items():
        require(command_line, address, text, "perfmode fanout")

    require(
        track_far_default,
        0x824F7DB8,
        "lfs f0,-3056(r11)",
        "trackfardistance default source",
    )
    require(
        track_far_default,
        0x824F7DC0,
        "stfs f0,4176(r31)",
        "trackfardistance live option store",
    )
    if image_u32(image, 0x8200F410) != TRACK_FAR_DEFAULT_BITS:
        raise ValueError("trackfardistance default value drifted")

    require(runtime_copy, 0x8259C7E8, "bl 0x82479e88", "parameter lookup")
    require(runtime_copy, 0x8259C7EC, "mr r30,r3", "parameter receiver")
    copy_rows = []
    for name, copy in RUNTIME_COPIES.items():
        require(runtime_copy, *copy["source"], f"{name} runtime source")
        require(runtime_copy, *copy["destination"], f"{name} runtime destination")
        copy_rows.append(
            {
                "name": name,
                "command_line_field_offset": OPTIONS[name]["field"],
                "runtime_field_offset": copy["runtime_offset"],
                "transform": copy["transform"],
                "copy_address": f"{copy['source'][0]:08X}",
            }
        )

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "title_track_render_differential_control_proved",
        "command_line_parameters": {
            "class": "CForzaCommandLineParameters",
            "decorated_name": decorated_name,
            "vtable_address": f"{COMMAND_LINE_VTABLE:08X}",
            "registration_function": f"{COMMAND_LINE_FUNCTION:08X}",
            "registration_vtable_slot": 4,
        },
        "options": option_rows,
        "runtime_copies": copy_rows,
        "perfmode": {
            "fanout_fields": len(PERFMODE_FANOUT),
            "includes_fasttrackrender": True,
            "isolated_track_differential": False,
        },
        "capture_contract": {
            "baseline_arguments": [],
            "track_arguments": [],
            "runtime_control": (
                "exact_option_and_runtime_overrides_"
                "824F7DC0_8259C834_8259C89C_8259C8DC"
            ),
            "track_far_distance_control": {
                "command_line_field_offset": 4176,
                "default_source_address": "8200F410",
                "default_store_address": "824F7DC0",
                "baseline_value": TRACK_FAR_DEFAULT_VALUE,
                "isolated_value": 5.0,
                "downstream_consumer_proved": False,
            },
            "modes": {
                "baseline": {
                    "track_far_distance": TRACK_FAR_DEFAULT_VALUE,
                    "fast_track_render": False,
                    "road_detail_blur": True,
                    "track_command_buffers": True,
                },
                "fasttrackrender": {
                    "track_far_distance": TRACK_FAR_DEFAULT_VALUE,
                    "fast_track_render": True,
                    "road_detail_blur": True,
                    "track_command_buffers": True,
                },
                "noroaddetailblur": {
                    "track_far_distance": TRACK_FAR_DEFAULT_VALUE,
                    "fast_track_render": False,
                    "road_detail_blur": False,
                    "track_command_buffers": True,
                },
                "notrackcommandbuffers": {
                    "track_far_distance": TRACK_FAR_DEFAULT_VALUE,
                    "fast_track_render": False,
                    "road_detail_blur": True,
                    "track_command_buffers": False,
                },
                "trackfardistance": {
                    "track_far_distance": 5.0,
                    "fast_track_render": False,
                    "road_detail_blur": True,
                    "track_command_buffers": True,
                },
            },
            "scene_must_match": True,
            "compare_exact_prepared_signatures": True,
            "semantic_identity": "candidate_until_runtime_delta_and_visual_evidence",
        },
        "safety": {
            "static_analysis_reads_guest_payload": False,
            "runtime_capture_changes_title_render_configuration": True,
            "xenos_authority_required": True,
            "native_draw": False,
            "suppression_allowed": False,
            "save_mutation_required": False,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
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
        print(f"native renderer track-config discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
