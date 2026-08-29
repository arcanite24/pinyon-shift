"""Inventory reviewed FH1 draw-packet constructors from generated AOT code.

This tool is intentionally payload-free.  It reads generated C++ instruction
comments, identifies stores of PM4_DRAW_INDX_2 packet headers, and records the
direct title call sites for the two reviewed runtime wrappers.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v1"
DRAW_OPCODE = 0x36
DRAW_OPCODE_IMMEDIATE = 0x22
REVIEWED_WRAPPERS = {
    0x8240F4D8: "draw_indexed",
    0x829F7C70: "draw_immediate",
}
INITIALIZATION_CONSTRUCTORS = {
    0x829E82D0,
    0x829E8428,
    0x829EDB68,
}

FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")
ORI_RE = re.compile(r"ori (r\d+),\1,(\d+)$")
STORE_RE = re.compile(r"stw(?:u|x|ux)? (r\d+),.*$")
LIS_RE = re.compile(r"lis (r\d+),(-?\d+)$")
ORIS_RE = re.compile(r"oris (r\d+),\1,(\d+)$")
CALL_RE = re.compile(r"bl 0x([0-9a-fA-F]{8})$")


def parse_functions(paths: list[pathlib.Path]) -> list[dict]:
    functions: list[dict] = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        current = None
        address = None
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            match = FUNCTION_RE.match(line)
            if match:
                address = int(match.group(1), 16)
                current = {
                    "address": address,
                    "name": "sub_{}".format(match.group(1)),
                    "source": path.as_posix(),
                    "line": line_number,
                    "instructions": [],
                }
                functions.append(current)
                continue
            label = LABEL_RE.match(line)
            if current and label:
                address = int(label.group(1), 16)
                continue
            comment = COMMENT_RE.match(line)
            if current and comment and address is not None:
                current["instructions"].append(
                    {"address": address, "text": comment.group(1)}
                )
                address += 4
    return functions


def find_prior(
    instructions: list[dict], index: int, pattern: re.Pattern, register: str
):
    for instruction in reversed(instructions[max(0, index - 24) : index]):
        match = pattern.fullmatch(instruction["text"])
        if match and match.group(1) == register:
            return instruction, match
    return None, None


def packet_constructors(functions: list[dict]) -> list[dict]:
    constructors = []
    for function in functions:
        instructions = function["instructions"]
        for index, instruction in enumerate(instructions):
            match = ORI_RE.fullmatch(instruction["text"])
            if not match or int(match.group(2)) != DRAW_OPCODE << 8:
                continue
            register = match.group(1)
            stored = any(
                (store := STORE_RE.fullmatch(item["text"]))
                and store.group(1) == register
                for item in instructions[index + 1 : index + 13]
            )
            if not stored:
                continue
            lis_instruction, lis = find_prior(
                instructions, index, LIS_RE, register
            )
            oris_instruction, oris = find_prior(
                instructions, index, ORIS_RE, register
            )
            header_source = "unknown"
            if lis and int(lis.group(2)) == -16384:
                header_source = "fixed_type3_count_1"
            elif (
                oris
                and int(oris.group(2)) == 49152
            ):
                header_source = "dynamic_type3_count"
            role = "unreviewed"
            if function["address"] in REVIEWED_WRAPPERS:
                role = "runtime_wrapper"
            elif function["address"] in INITIALIZATION_CONSTRUCTORS:
                role = "initialization_template"
            constructors.append(
                {
                    "function": function["name"],
                    "function_address": "{:08X}".format(function["address"]),
                    "constructor_address": "{:08X}".format(
                        instruction["address"]
                    ),
                    "opcode": "PM4_DRAW_INDX_2",
                    "opcode_value": "{:02X}".format(DRAW_OPCODE),
                    "header_source": header_source,
                    "role": role,
                    "source": function["source"],
                    "source_line": function["line"],
                }
            )
    return sorted(
        constructors,
        key=lambda item: (item["function_address"], item["constructor_address"]),
    )


def direct_calls(functions: list[dict], targets: set[int]) -> list[dict]:
    calls = []
    for function in functions:
        for instruction in function["instructions"]:
            match = CALL_RE.fullmatch(instruction["text"])
            if not match:
                continue
            target = int(match.group(1), 16)
            if target not in targets:
                continue
            calls.append(
                {
                    "wrapper": "{:08X}".format(target),
                    "wrapper_kind": REVIEWED_WRAPPERS[target],
                    "caller_function": function["name"],
                    "caller_function_address": "{:08X}".format(
                        function["address"]
                    ),
                    "callsite": "{:08X}".format(instruction["address"]),
                    "return_address": "{:08X}".format(
                        instruction["address"] + 4
                    ),
                }
            )
    return sorted(calls, key=lambda item: (item["wrapper"], item["callsite"]))


def build(paths: list[pathlib.Path]) -> dict:
    functions = parse_functions(paths)
    constructors = packet_constructors(functions)
    constructor_addresses = {
        int(item["function_address"], 16) for item in constructors
    }
    missing = set(REVIEWED_WRAPPERS) - constructor_addresses
    if missing:
        raise ValueError(
            "reviewed draw wrapper packet evidence missing: {}".format(
                ", ".join("{:08X}".format(address) for address in sorted(missing))
            )
        )
    calls = direct_calls(functions, set(REVIEWED_WRAPPERS))
    return {
        "schema": SCHEMA,
        "input": {
            "generated_files": len(paths),
            "functions": len(functions),
        },
        "packet_constructors": constructors,
        "reviewed_wrappers": [
            {
                "address": "{:08X}".format(address),
                "kind": kind,
                "packet_evidence": "PM4_DRAW_INDX_2",
                "runtime_trace": "entry_lr_and_bounded_argument_metadata",
            }
            for address, kind in sorted(REVIEWED_WRAPPERS.items())
        ],
        "direct_calls": calls,
        "totals": {
            "packet_constructors": len(constructors),
            "reviewed_wrappers": len(REVIEWED_WRAPPERS),
            "direct_calls": len(calls),
        },
        "safety": {
            "guest_payload_read": False,
            "guest_state_changed": False,
            "control_flow_changed": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generated_root", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        paths = list(args.generated_root.glob("pinyon_shift_recomp.*.cpp"))
        if not paths:
            raise ValueError("no generated AOT C++ files found")
        document = build(paths)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError) as error:
        print("native renderer dispatch discovery failed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
