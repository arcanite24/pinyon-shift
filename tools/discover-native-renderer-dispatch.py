"""Inventory reviewed FH1 graphics wrappers from generated AOT code.

This tool is intentionally payload-free.  It reads generated C++ instruction
comments, identifies stored draw and visibility-query packet headers, records
the direct title and indirect-constructor call graphs, and proves the dirty-mask
transitions that happen inside the indexed draw wrapper.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
IMAGE_BASE = 0x82000000
PACKET_OPCODES = {
    0x3C: "PM4_WAIT_REG_MEM",
    0x3D: "PM4_MEM_WRITE",
    0x46: "PM4_EVENT_WRITE",
    0x5A: "PM4_EVENT_WRITE_EXT",
    0x5B: "PM4_EVENT_WRITE_ZPD",
    0x60: "PM4_SET_BIN_MASK_LO",
    0x61: "PM4_SET_BIN_MASK_HI",
    0x62: "PM4_SET_BIN_SELECT_LO",
    0x63: "PM4_SET_BIN_SELECT_HI",
    0x23: "PM4_VIZ_QUERY",
    0x36: "PM4_DRAW_INDX_2",
    0x37: "PM4_INDIRECT_BUFFER_PFD",
    0x3F: "PM4_INDIRECT_BUFFER",
}
REVIEWED_WRAPPERS = {
    0x824079B8: {
        "kind": "draw_adapter",
        "layer": "title_adapter",
        "evidence": "direct_call_to_8240F4D8",
        "hook_address": 0x824079BC,
        "stack_argument_offsets": [92, 100],
    },
    0x8240F4D8: {
        "kind": "draw_indexed",
        "layer": "packet_wrapper",
        "packet_opcode": 0x36,
        "hook_address": 0x8240F4DC,
    },
    0x824587D8: {
        "kind": "resolve_controller",
        "layer": "title_adapter",
        "evidence": "two_direct_calls_to_82458A88",
        "hook_address": 0x824587DC,
    },
    0x82458A88: {
        "kind": "resolve_setup",
        "layer": "state_packet_wrapper",
        "evidence": "RB_MODECONTROL_0x2208_written_kCopy_6",
        "hook_address": 0x82458A8C,
    },
    0x829F21A0: {
        "kind": "viz_query_begin",
        "layer": "packet_wrapper",
        "packet_opcode": 0x23,
        "hook_address": 0x829F21A4,
    },
    0x829F2280: {
        "kind": "viz_query_end",
        "layer": "packet_wrapper",
        "packet_opcode": 0x23,
        "hook_address": 0x829F2284,
    },
    0x829F7C70: {
        "kind": "draw_immediate",
        "layer": "packet_wrapper",
        "packet_opcode": 0x36,
        "hook_address": 0x829F7C74,
    },
    0x82D951E0: {
        "kind": "viz_query_owner",
        "layer": "query_pass_owner",
        "evidence": "begin_draw_end_lifecycle",
        "hook_address": 0x82D951E4,
    },
    0x82413AB8: {
        "kind": "binning_scissor_state",
        "layer": "state_packet_wrapper",
        "packet_opcodes": [0x60, 0x61],
        "hook_address": 0x82413ABC,
    },
    0x824736F0: {
        "kind": "binning_state_reset",
        "layer": "state_packet_wrapper",
        "packet_opcodes": [0x60, 0x61, 0x62, 0x63],
        "hook_address": 0x824736F4,
    },
}
INITIALIZATION_CONSTRUCTORS = {
    0x829E82D0,
    0x829E8428,
    0x829EDB68,
}
INDIRECT_CONSTRUCTOR_RUNTIME_HOOKS = {
    0x82409398: {"entry": 0x8240939C, "exit": 0x82409660},
    0x82416A00: {"entry": 0x82416A04, "exit": 0x82417054},
    0x8246FB98: {"entry": 0x8246FB9C, "exit": 0x8246FC78},
    0x8263BCB8: {"entry": 0x8263BCBC, "exit": 0x8263BDF0},
    0x829E8E00: {"entry": 0x829E8E04, "exit": 0x829E8ED4},
    0x829EC400: {"entry": 0x829EC404, "exit": 0x829EC5AC},
}
INDIRECT_OWNER_RUNTIME_HOOKS = {
    0x82409668: {"entry": 0x8240966C, "exit": 0x8240983C},
    0x824167F8: {"entry": 0x824167FC, "exit": 0x82416898},
    0x8246E8F8: {"entry": 0x8246E8FC, "exit": 0x8246E938},
    0x829F5FF0: {"entry": 0x829F5FF4, "exit": 0x829F6358},
}
INDIRECT_PRODUCER_RUNTIME_HOOKS = {
    0x8240D070: {"entry": 0x8240D074, "exit": 0x8240D1F0},
    0x82417060: {"entry": 0x82417064, "exit": 0x824170C0},
    0x829F6360: {"entry": 0x829F6364, "exit": 0x829F63FC},
}
INDIRECT_CONTEXT_RUNTIME_HOOKS = {
    0x8240CF68: {
        "entry": 0x8240CF6C,
        "exit": 0x8240D054,
        "root_entry_register": "r3",
        "root_offset": 0,
        "producer_edges": [(0x8240D070, 0x8240D000)],
        "proof": [
            (0x8240CF80, "mr r31,r3"),
            (0x8240CFF8, "mr r3,r31"),
        ],
    },
    0x82417BC0: {
        "entry": 0x82417BC4,
        "exit": 0x82418F38,
        "root_entry_register": "r6",
        "root_offset": 59712,
        "producer_edges": [
            (0x82417060, 0x82418A28),
            (0x82417060, 0x82418ECC),
        ],
        "proof": [
            (0x82417BF0, "stw r6,2156(r1)"),
            (0x82418058, "lwz r8,2156(r1)"),
            (0x82418068, "addis r24,r8,1"),
            (0x8241807C, "addi r24,r24,-5824"),
            (0x82418A20, "mr r3,r24"),
            (0x82418EC4, "mr r3,r24"),
        ],
    },
    0x824365B0: {
        "entry": 0x824365B4,
        "exit": 0x82437048,
        "root_entry_register": "r3",
        "root_offset": 59712,
        "producer_edges": [(0x82417060, 0x82437048)],
        "proof": [
            (0x824365C0, "mr r29,r3"),
            (0x8243667C, "addis r25,r29,1"),
            (0x82436688, "addi r25,r25,-5824"),
            (0x82436690, "stw r25,84(r1)"),
            (0x82437030, "lwz r25,84(r1)"),
            (0x82437040, "mr r3,r25"),
        ],
    },
    0x829F6620: {
        "entry": 0x829F6624,
        "exit": 0x829F67B8,
        "root_entry_register": "r3",
        "root_offset": 0,
        "producer_edges": [(0x829F6360, 0x829F67B0)],
        "proof": [
            (0x829F662C, "mr r28,r3"),
            (0x829F67A8, "mr r3,r28"),
        ],
    },
}

PROCEDURAL_MODEL_RECEIVER = {
    "class_name": "proceduralGeometry::CProceduralModels",
    "decorated_name": ".?AVCProceduralModels@proceduralGeometry@@",
    "vtable_address": 0x82002B5C,
    "vtable_slot": 41,
    "dispatch_function": 0x82417BC0,
    "constructor_function": 0x82E1C9A0,
    "constructor_entry": 0x82E1C9A4,
    "constructor_exit": 0x82E1CA0C,
    "destructor_function": 0x82E1CA28,
    "destructor_entry": 0x82E1CA2C,
    "destructor_exit": 0x82E1CBD0,
    "deleting_destructor_function": 0x82E1D9B0,
    "array_constructor_function": 0x82E1CDC8,
    "visibility_function": 0x82E1FD00,
    "visibility_vtable_slot": 14,
    "visibility_entry": 0x82E1FD04,
    "visibility_exit": 0x82E208CC,
    "render_state_function": 0x824170D8,
    "render_state_vtable_slot": 40,
    "render_state_entry": 0x824170DC,
    "render_state_exit": 0x82417410,
    "render_item_function": 0x82417418,
    "render_item_entry_hook": 0x8241741C,
    "render_item_exit_hook": 0x82417B80,
    "primary_resource_binding_hook": 0x82417A74,
    "secondary_resource_binding_hook": 0x82417A9C,
    "geometry_submission_hook": 0x82417B60,
    "resource_binding_function": 0x82415BF8,
    "resource_resolution_function": 0x82415AD0,
    "resource_lookup_function": 0x82410A58,
    "resource_provider_lookup_hook": 0x82415B64,
    "resource_provider_primary_predicate_hook": 0x82415B80,
    "resource_provider_fallback_predicate_hook": 0x82415BA4,
    "resource_provider_method_result_hook": 0x82415BC0,
    "resource_secondary_resolution_result_hook": 0x82415BE4,
    "resource_resolution_result_hook": 0x82415C50,
    "resource_bind_dispatch_hook": 0x82415C6C,
}

FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
LABEL_RE = re.compile(r"^loc_([0-9A-F]{8}):")
COMMENT_RE = re.compile(r"^\s*//\s+(.+?)\s*$")
ORI_RE = re.compile(r"ori (r\d+),(r\d+),(\d+)$")
STORE_RE = re.compile(r"stw(?:u|x|ux)? (r\d+),.*$")
LIS_RE = re.compile(r"lis (r\d+),(-?\d+)$")
ORIS_RE = re.compile(r"oris (r\d+),\1,(\d+)$")
CALL_RE = re.compile(r"bl 0x([0-9a-fA-F]{8})$")
CALL_BOUNDARY_RE = re.compile(r"(?:bl 0x[0-9a-fA-F]{8}|bctrl|blrl)$")
BRANCH_RE = re.compile(r"b 0x([0-9a-fA-F]{8})$")
DIRTY_STORE_RE = re.compile(r"std (r\d+),(16|24|32)\(r31\)$")
QUERY_STATE_STORE_RE = re.compile(r"std (r\d+),12424\(r31\)$")
REGISTER_DEFINITION_RE = re.compile(r"([a-z0-9.]+) (r(?:[3-9]|10))(?:,|$)")
MEMORY_LOAD_RE = re.compile(
    r"(lbz|lhz|lwz|ld|lfs) (r(?:[3-9]|10)),(-?\d+)\((r\d+)\)$"
)
DEFINITION_OPERATIONS = {
    "mr", "li", "lis", "mflr", "lbz", "lhz", "lwz", "ld", "lfs",
    "addi", "addis", "add", "subf", "neg", "extsw", "or", "ori",
    "oris", "and", "andc", "andi.", "andis.", "xor", "xori", "rlwinm",
    "rlwimi", "rldicr", "clrlwi", "slwi", "srwi", "srawi",
}


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
            if not match:
                continue
            opcode_value = int(match.group(3)) >> 8
            if (
                int(match.group(3)) & 0xFF
                or opcode_value not in PACKET_OPCODES
            ):
                continue
            register = match.group(1)
            source_register = match.group(2)
            store_instruction = next(
                (
                    item
                    for item in instructions[index + 1 : index + 65]
                    if (store := STORE_RE.fullmatch(item["text"]))
                    and store.group(1) == register
                ),
                None,
            )
            if store_instruction is None:
                continue
            lis_instruction, lis = find_prior(
                instructions, index, LIS_RE, source_register
            )
            oris_instruction, oris = find_prior(
                instructions, index, ORIS_RE, source_register
            )
            header_source = "unknown"
            if lis:
                upper = int(lis.group(2)) & 0xFFFF
                if upper & 0xC000 == 0xC000:
                    header_source = "fixed_type3_count_{}".format(
                        (upper & 0x3FFF) + 1
                    )
            elif (
                oris
                and int(oris.group(2)) == 49152
            ):
                header_source = "dynamic_type3_count"
            role = "unreviewed"
            reviewed = REVIEWED_WRAPPERS.get(function["address"])
            reviewed_opcodes = set(reviewed.get("packet_opcodes", [])) if reviewed else set()
            if reviewed and "packet_opcode" in reviewed:
                reviewed_opcodes.add(reviewed["packet_opcode"])
            if opcode_value in reviewed_opcodes:
                role = "runtime_wrapper"
            elif (
                opcode_value == 0x36
                and function["address"] in INITIALIZATION_CONSTRUCTORS
            ):
                role = "initialization_template"
            constructors.append(
                {
                    "function": function["name"],
                    "function_address": "{:08X}".format(function["address"]),
                    "constructor_address": "{:08X}".format(
                        instruction["address"]
                    ),
                    "constructor_instruction": instruction["text"],
                    "store_address": "{:08X}".format(
                        store_instruction["address"]
                    ),
                    "store_instruction": store_instruction["text"],
                    "packet_register": register,
                    "opcode": PACKET_OPCODES[opcode_value],
                    "opcode_value": "{:02X}".format(opcode_value),
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
                    "wrapper_kind": REVIEWED_WRAPPERS[target]["kind"],
                    "wrapper_layer": REVIEWED_WRAPPERS[target]["layer"],
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


def indirect_constructor_calls(
    functions: list[dict], constructors: list[dict]
) -> list[dict]:
    """Inventory direct callers of every stored indirect-buffer constructor."""
    indirect_by_function: dict[int, list[dict]] = collections.defaultdict(list)
    for constructor in constructors:
        if constructor["opcode"] in {
            "PM4_INDIRECT_BUFFER",
            "PM4_INDIRECT_BUFFER_PFD",
        }:
            indirect_by_function[int(constructor["function_address"], 16)].append(
                constructor
            )

    calls = []
    for function in functions:
        for instruction in function["instructions"]:
            match = CALL_RE.fullmatch(instruction["text"])
            if not match:
                continue
            target = int(match.group(1), 16)
            target_constructors = indirect_by_function.get(target)
            if not target_constructors:
                continue
            calls.append(
                {
                    "constructor_function": "sub_{:08X}".format(target),
                    "constructor_function_address": "{:08X}".format(target),
                    "constructor_opcodes": sorted(
                        {item["opcode"] for item in target_constructors}
                    ),
                    "constructor_store_addresses": sorted(
                        {item["store_address"] for item in target_constructors}
                    ),
                    "caller_function": function["name"],
                    "caller_function_address": "{:08X}".format(
                        function["address"]
                    ),
                    "callsite": "{:08X}".format(instruction["address"]),
                    "return_address": "{:08X}".format(
                        instruction["address"] + 4
                    ),
                    "classification": "direct_static_callsite",
                    "semantic_identity": "unknown",
                    "suppression_eligible": False,
                }
            )
    return sorted(
        calls,
        key=lambda item: (
            item["constructor_function_address"],
            item["callsite"],
        ),
    )


def indirect_constructor_runtime_hooks(
    functions_by_address: dict[int, dict], constructors: list[dict]
) -> list[dict]:
    indirect_functions = {
        int(item["function_address"], 16)
        for item in constructors
        if item["opcode"] in {
            "PM4_INDIRECT_BUFFER",
            "PM4_INDIRECT_BUFFER_PFD",
        }
    }
    observed_known = indirect_functions & set(INDIRECT_CONSTRUCTOR_RUNTIME_HOOKS)
    if observed_known and observed_known != set(INDIRECT_CONSTRUCTOR_RUNTIME_HOOKS):
        raise ValueError("known indirect-constructor function set drifted")
    result = []
    for address in sorted(observed_known):
        function = functions_by_address[address]
        hooks = INDIRECT_CONSTRUCTOR_RUNTIME_HOOKS[address]
        instructions = function["instructions"]
        if (
            not instructions
            or instructions[0] != {"address": address, "text": "mflr r12"}
            or hooks["entry"] != address + 4
            or len(instructions) < 2
            or instructions[-2]["address"] != hooks["exit"]
            or not instructions[-2]["text"].startswith("addi r1,r1,")
            or not BRANCH_RE.fullmatch(instructions[-1]["text"])
        ):
            raise ValueError(
                "indirect-constructor balanced hook evidence drifted: "
                "{:08X}".format(address)
            )
        result.append(
            {
                "function": function["name"],
                "function_address": "{:08X}".format(address),
                "entry_hook_address": "{:08X}".format(hooks["entry"]),
                "exit_hook_address": "{:08X}".format(hooks["exit"]),
                "caller_lr_register": "r12_after_opening_mflr",
                "entry_metadata": [
                    "r3",
                    "r4",
                    "r5",
                    "r6",
                    "r7",
                    "r8",
                    "r9",
                    "r10",
                ],
                "classification": "balanced_passive_constructor_origin",
                "suppression_eligible": False,
            }
        )
    return result


def indirect_owner_calls(functions: list[dict]) -> list[dict]:
    """Inventory direct callers of the runtime-qualified constructor owners."""
    calls = []
    for function in functions:
        for instruction in function["instructions"]:
            match = CALL_RE.fullmatch(instruction["text"])
            if not match:
                continue
            target = int(match.group(1), 16)
            if target not in INDIRECT_OWNER_RUNTIME_HOOKS:
                continue
            calls.append(
                {
                    "owner_function": "sub_{:08X}".format(target),
                    "owner_function_address": "{:08X}".format(target),
                    "caller_function": function["name"],
                    "caller_function_address": "{:08X}".format(
                        function["address"]
                    ),
                    "callsite": "{:08X}".format(instruction["address"]),
                    "return_address": "{:08X}".format(
                        instruction["address"] + 4
                    ),
                    "classification": "direct_static_owner_callsite",
                    "semantic_identity": "unknown",
                    "suppression_eligible": False,
                }
            )
    return sorted(
        calls,
        key=lambda item: (item["owner_function_address"], item["callsite"]),
    )


def indirect_owner_runtime_hooks(functions_by_address: dict[int, dict]) -> list[dict]:
    """Prove balanced passive hooks for the selected constructor owners."""
    observed_known = set(functions_by_address) & set(INDIRECT_OWNER_RUNTIME_HOOKS)
    if observed_known and observed_known != set(INDIRECT_OWNER_RUNTIME_HOOKS):
        raise ValueError("known indirect-owner function set drifted")
    result = []
    for address in sorted(observed_known):
        hooks = INDIRECT_OWNER_RUNTIME_HOOKS[address]
        function = functions_by_address[address]
        instructions = function["instructions"]
        exit_instruction = next(
            (
                item
                for item in instructions
                if item["address"] == hooks["exit"]
            ),
            None,
        )
        if (
            not instructions
            or instructions[0] != {"address": address, "text": "mflr r12"}
            or hooks["entry"] != address + 4
            or exit_instruction is None
            or not exit_instruction["text"].startswith("addi r1,r1,")
            or instructions[-1]["text"] not in {"blr", "blr "}
            and not BRANCH_RE.fullmatch(instructions[-1]["text"])
        ):
            raise ValueError(
                "indirect-owner balanced hook evidence drifted: "
                "{:08X}".format(address)
            )
        result.append(
            {
                "function": function["name"],
                "function_address": "{:08X}".format(address),
                "entry_hook_address": "{:08X}".format(hooks["entry"]),
                "exit_hook_address": "{:08X}".format(hooks["exit"]),
                "caller_lr_register": "r12_after_opening_mflr",
                "entry_metadata": [
                    "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"
                ],
                "classification": "balanced_passive_constructor_owner",
                "semantic_identity": "unknown",
                "suppression_eligible": False,
            }
        )
    return result


def indirect_producer_calls(functions: list[dict]) -> list[dict]:
    """Inventory direct callers of the dominant live owner-caller functions."""
    calls = []
    for function in functions:
        for instruction in function["instructions"]:
            match = CALL_RE.fullmatch(instruction["text"])
            if not match:
                continue
            target = int(match.group(1), 16)
            if target not in INDIRECT_PRODUCER_RUNTIME_HOOKS:
                continue
            calls.append(
                {
                    "producer_function": "sub_{:08X}".format(target),
                    "producer_function_address": "{:08X}".format(target),
                    "caller_function": function["name"],
                    "caller_function_address": "{:08X}".format(
                        function["address"]
                    ),
                    "callsite": "{:08X}".format(instruction["address"]),
                    "return_address": "{:08X}".format(
                        instruction["address"] + 4
                    ),
                    "classification": "direct_static_producer_callsite",
                    "semantic_identity": "unknown",
                    "object_identity_proved": False,
                    "lifetime_proved": False,
                    "suppression_eligible": False,
                }
            )
    return sorted(
        calls,
        key=lambda item: (
            item["producer_function_address"], item["callsite"]
        ),
    )


def indirect_producer_runtime_hooks(
    functions_by_address: dict[int, dict]
) -> list[dict]:
    """Prove balanced passive hooks for the dominant owner producers."""
    observed_known = set(functions_by_address) & set(
        INDIRECT_PRODUCER_RUNTIME_HOOKS
    )
    if observed_known and observed_known != set(INDIRECT_PRODUCER_RUNTIME_HOOKS):
        raise ValueError("known indirect-producer function set drifted")
    result = []
    for address in sorted(observed_known):
        hooks = INDIRECT_PRODUCER_RUNTIME_HOOKS[address]
        function = functions_by_address[address]
        instructions = function["instructions"]
        exit_instruction = next(
            (
                item for item in instructions
                if item["address"] == hooks["exit"]
            ),
            None,
        )
        if (
            not instructions
            or instructions[0] != {"address": address, "text": "mflr r12"}
            or hooks["entry"] != address + 4
            or exit_instruction is None
            or not exit_instruction["text"].startswith("addi r1,r1,")
        ):
            raise ValueError(
                "indirect-producer balanced hook evidence drifted: "
                "{:08X}".format(address)
            )
        result.append(
            {
                "function": function["name"],
                "function_address": "{:08X}".format(address),
                "entry_hook_address": "{:08X}".format(hooks["entry"]),
                "exit_hook_address": "{:08X}".format(hooks["exit"]),
                "caller_lr_register": "r12_after_opening_mflr",
                "entry_metadata": [
                    "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"
                ],
                "classification": "balanced_passive_owner_producer",
                "semantic_identity": "unknown",
                "object_identity_proved": False,
                "lifetime_proved": False,
                "suppression_eligible": False,
            }
        )
    return result


def indirect_context_runtime_hooks(
    functions_by_address: dict[int, dict]
) -> list[dict]:
    """Prove balanced scopes for the four live producer contexts."""
    observed_known = set(functions_by_address) & set(
        INDIRECT_CONTEXT_RUNTIME_HOOKS
    )
    if observed_known and observed_known != set(INDIRECT_CONTEXT_RUNTIME_HOOKS):
        raise ValueError("known indirect-context function set drifted")
    result = []
    for address in sorted(observed_known):
        hooks = INDIRECT_CONTEXT_RUNTIME_HOOKS[address]
        function = functions_by_address[address]
        by_address = {
            item["address"]: item["text"] for item in function["instructions"]
        }
        if (
            not function["instructions"]
            or function["instructions"][0]
            != {"address": address, "text": "mflr r12"}
            or hooks["entry"] != address + 4
            or not by_address.get(hooks["exit"], "").startswith("addi r1,r1,")
            or any(
                by_address.get(proof_address) != proof_text
                for proof_address, proof_text in hooks["proof"]
            )
        ):
            raise ValueError(
                "indirect-context root evidence drifted: {:08X}".format(address)
            )
        result.append(
            {
                "function": function["name"],
                "function_address": "{:08X}".format(address),
                "entry_hook_address": "{:08X}".format(hooks["entry"]),
                "exit_hook_address": "{:08X}".format(hooks["exit"]),
                "caller_lr_register": "r12_after_opening_mflr",
                "entry_metadata": [
                    "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"
                ],
                "root_entry_register": hooks["root_entry_register"],
                "root_offset": hooks["root_offset"],
                "classification": "balanced_passive_producer_context",
                "semantic_identity": "unknown",
                "object_identity_proved": False,
                "object_lifetime_proved": False,
                "invocation_scope_proved": True,
                "suppression_eligible": False,
            }
        )
    return result


def indirect_context_roots(functions_by_address: dict[int, dict]) -> list[dict]:
    """Describe exact entry-register roots for the five live producer edges."""
    if not set(functions_by_address) & set(INDIRECT_CONTEXT_RUNTIME_HOOKS):
        return []
    roots = []
    for address, hooks in sorted(INDIRECT_CONTEXT_RUNTIME_HOOKS.items()):
        function = functions_by_address[address]
        by_address = {
            item["address"]: item["text"] for item in function["instructions"]
        }
        for producer_function, producer_return in hooks["producer_edges"]:
            expected_call = "bl 0x{:08x}".format(producer_function)
            if by_address.get(producer_return - 4) != expected_call:
                raise ValueError(
                    "indirect-context producer edge drifted: "
                    "{:08X}->{:08X}".format(address, producer_return)
                )
            roots.append(
                {
                    "context_function": "sub_{:08X}".format(address),
                    "context_function_address": "{:08X}".format(address),
                    "producer_function": "sub_{:08X}".format(
                        producer_function
                    ),
                    "producer_function_address": "{:08X}".format(
                        producer_function
                    ),
                    "producer_return_address": "{:08X}".format(
                        producer_return
                    ),
                    "root_entry_register": hooks["root_entry_register"],
                    "root_offset": hooks["root_offset"],
                    "derivation": (
                        hooks["root_entry_register"]
                        if not hooks["root_offset"]
                        else "{}+{}".format(
                            hooks["root_entry_register"], hooks["root_offset"]
                        )
                    ),
                    "classification": "exact_producer_context_root",
                    "semantic_identity": "unknown",
                    "object_identity_proved": False,
                    "object_lifetime_proved": False,
                    "suppression_eligible": False,
                }
            )
    return roots


def _image_u32(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise ValueError(
            "semantic receiver image address is out of range: {:08X}".format(
                address
            )
        )
    return int.from_bytes(image[offset : offset + 4], "big")


def _image_c_string(image: bytes, address: int) -> str:
    offset = address - IMAGE_BASE
    if offset < 0 or offset >= len(image):
        raise ValueError(
            "semantic receiver type name is out of range: {:08X}".format(
                address
            )
        )
    end = image.find(b"\0", offset, min(len(image), offset + 256))
    if end < 0:
        raise ValueError("semantic receiver type name is not terminated")
    return image[offset:end].decode("ascii")


def procedural_model_receiver_lifecycle(
    functions_by_address: dict[int, dict], image: bytes | None = None
) -> dict:
    """Prove the first semantic receiver and its construction lifetime."""
    spec = PROCEDURAL_MODEL_RECEIVER
    required = {
        spec["dispatch_function"],
        spec["constructor_function"],
        spec["destructor_function"],
        spec["deleting_destructor_function"],
        spec["array_constructor_function"],
        spec["visibility_function"],
        spec["render_state_function"],
        spec["render_item_function"],
        spec["resource_binding_function"],
        spec["resource_resolution_function"],
        spec["resource_lookup_function"],
    }
    lifecycle_functions = required - {spec["dispatch_function"]}
    if not lifecycle_functions & set(functions_by_address):
        return {}
    if not required <= set(functions_by_address):
        raise ValueError("procedural-model receiver function set drifted")

    constructor = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["constructor_function"]][
            "instructions"
        ]
    }
    destructor = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["destructor_function"]][
            "instructions"
        ]
    }
    deleting_destructor = {
        item["address"]: item["text"]
        for item in functions_by_address[
            spec["deleting_destructor_function"]
        ]["instructions"]
    }
    array_constructor = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["array_constructor_function"]][
            "instructions"
        ]
    }
    visibility = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["visibility_function"]][
            "instructions"
        ]
    }
    render_state = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["render_state_function"]][
            "instructions"
        ]
    }
    render_item = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["render_item_function"]][
            "instructions"
        ]
    }
    resource_binding = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["resource_binding_function"]][
            "instructions"
        ]
    }
    resource_resolution = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["resource_resolution_function"]][
            "instructions"
        ]
    }
    resource_lookup = {
        item["address"]: item["text"]
        for item in functions_by_address[spec["resource_lookup_function"]][
            "instructions"
        ]
    }
    expected = {
        spec["constructor_function"]: "mflr r12",
        0x82E1C9B8: "bl 0x82e19478",
        0x82E1C9BC: "lis r11,-32256",
        0x82E1C9C4: "addi r11,r11,11100",
        0x82E1C9D0: "stw r11,0(r31)",
        spec["constructor_exit"]: "addi r1,r1,112",
    }
    if any(constructor.get(address) != text for address, text in expected.items()):
        raise ValueError("procedural-model constructor evidence drifted")
    expected = {
        spec["destructor_function"]: "mflr r12",
        0x82E1CA3C: "lis r11,-32256",
        0x82E1CA48: "addi r11,r11,11100",
        0x82E1CA50: "stw r11,0(r3)",
        0x82E1CBCC: "bl 0x82e1c0c0",
        spec["destructor_exit"]: "addi r1,r1,112",
    }
    if any(destructor.get(address) != text for address, text in expected.items()):
        raise ValueError("procedural-model destructor evidence drifted")
    if deleting_destructor.get(0x82E1D9CC) != "bl 0x82e1ca28":
        raise ValueError("procedural-model deleting destructor evidence drifted")

    array_expected = {
        0x82E1CDD8: "rlwinm r3,r3,9,0,22",
        0x82E1CDFC: "bl 0x82e1c9a0",
        0x82E1CE04: "addi r31,r31,512",
    }
    if any(
        array_constructor.get(address) != text
        for address, text in array_expected.items()
    ):
        raise ValueError("procedural-model object-size evidence drifted")

    visibility_expected = {
        spec["visibility_function"]: "mflr r12",
        0x82E1FD20: "mr r20,r3",
        0x82E1FD40: "lwz r11,124(r3)",
        0x82E1FD4C: "lwz r11,136(r3)",
        0x82E1FE10: "lwz r11,128(r20)",
        0x82E1FEB8: "lwz r9,128(r20)",
        0x82E20048: "lwz r11,124(r20)",
        0x82E20854: "addi r18,r18,92",
        0x82E20858: "addi r17,r17,68",
        spec["visibility_exit"]: "addi r1,r1,704",
    }
    if any(
        visibility.get(address) != text
        for address, text in visibility_expected.items()
    ):
        raise ValueError("procedural-model visibility evidence drifted")

    render_state_expected = {
        spec["render_state_function"]: "mflr r12",
        0x824172F8: "vmaddfp v1,v31,v0,v30",
        0x82417304: "mr r3,r31",
        0x82417410: "addi r1,r1,256",
    }
    render_item_expected = {
        spec["render_item_function"]: "mflr r12",
        0x8241742C: "mr r27,r3",
        0x82417494: "addi r30,r27,448",
        0x824174D8: "addi r30,r27,320",
        0x8241751C: "addi r30,r27,384",
        0x82417668: "lwz r10,124(r27)",
        0x8241766C: "lwz r9,356(r1)",
        0x82417670: "mulli r11,r9,92",
        0x82417674: "lwz r10,0(r10)",
        0x824176AC: "lwz r10,128(r27)",
        0x824176B0: "mulli r11,r9,68",
        0x824176B8: "add r26,r10,r11",
        0x824176C8: "lwz r24,24(r26)",
        0x8241767C: "lwz r8,36(r28)",
        0x82417680: "cmplwi cr6,r8,4",
        0x82417688: "cmplwi cr6,r8,5",
        0x82417694: "li r11,1",
        0x8241769C: "clrlwi r23,r11,24",
        0x824176D8: "cmplwi cr6,r8,1",
        0x824176E0: "cmplwi cr6,r8,3",
        0x824176EC: "li r11,1",
        0x824176F4: "clrlwi r21,r11,24",
        0x824176F8: "cmpwi cr6,r25,9",
        0x82417704: "cmpwi cr6,r25,11",
        0x8241770C: "cmpwi cr6,r25,6",
        0x82417758: "cmpwi cr6,r25,0",
        0x82417760: "cmpwi cr6,r25,5",
        0x824177C4: "lwz r22,28(r26)",
        0x824177C8: "lwz r24,32(r26)",
        0x824177F8: "lfs f13,40(r26)",
        0x82417870: "lwz r11,36(r28)",
        0x82417890: "cmpwi cr6,r25,9",
        0x824178C0: "cmpwi cr6,r25,11",
        0x824178F0: "cmpwi cr6,r25,24",
        0x824178F8: "cmpwi cr6,r25,27",
        0x82417928: "cmpwi cr6,r25,6",
        0x82417930: "cmpwi cr6,r25,8",
        0x82417984: "lwz r11,-14300(r30)",
        0x82417A58: "lwz r11,0(r28)",
        0x82417A60: "lwz r10,8(r27)",
        0x82417A64: "li r5,0",
        0x82417A68: "rlwinm r11,r11,3,0,28",
        0x82417A70: "lwzx r4,r11,r10",
        0x82417A74: "bl 0x82415bf8",
        0x82417A78: "lwz r11,4(r28)",
        0x82417A80: "blt cr6,0x82417aa0",
        0x82417A84: "lwz r10,8(r27)",
        0x82417A88: "rlwinm r11,r11,3,0,28",
        0x82417A90: "li r5,1",
        0x82417A98: "lwzx r4,r11,r10",
        0x82417A9C: "bl 0x82415bf8",
        0x82417B44: "lwz r11,0(r31)",
        0x82417B48: "li r4,0",
        0x82417B50: "lwz r5,0(r26)",
        0x82417B54: "lwz r11,124(r11)",
        0x82417B5C: "bctrl",
        0x82417B60: "lwz r11,0(r31)",
        0x82417B64: "mr r6,r24",
        0x82417B68: "rlwinm r5,r22,2,0,29",
        0x82417B6C: "li r4,13",
        0x82417B70: "mr r3,r31",
        0x82417B74: "lwz r11,160(r11)",
        0x82417B7C: "bctrl",
        spec["render_item_exit_hook"]: "addi r1,r1,272",
        0x82417B88: "b 0x82a7de34",
    }
    render_state_helper_expected = {
        0x824171AC: "lwz r11,4(r30)",
        0x824171C0: "lwz r3,0(r30)",
        0x824171D0: "stw r11,84(r1)",
        0x824171D4: "bl 0x82417418",
    }
    if any(
        render_state.get(address) != text
        for address, text in render_state_expected.items()
    ):
        raise ValueError("procedural-model render-state evidence drifted")
    if any(
        render_item.get(address) != text
        for address, text in render_item_expected.items()
    ):
        raise ValueError("procedural-model render-item evidence drifted")
    if any(
        render_state.get(address) != text
        for address, text in render_state_helper_expected.items()
    ):
        raise ValueError("procedural-model render-item call evidence drifted")

    resource_binding_expected = {
        spec["resource_binding_function"]: "mflr r12",
        0x82415C10: "mr r31,r5",
        0x82415C14: "cmpwi cr6,r4,0",
        0x82415C1C: "cmpwi cr6,r5,5",
        0x82415C28: "rlwinm r10,r5,2,0,29",
        0x82415C34: "cmpw cr6,r9,r4",
        0x82415C3C: "stwx r4,r10,r11",
        0x82415C44: "mr r5,r6",
        0x82415C4C: "bl 0x82415ad0",
        spec["resource_resolution_result_hook"]: "mr. r5,r3",
        0x82415C54: "beq 0x82415c70",
        0x82415C5C: "mr r4,r31",
        0x82415C60: "mr r3,r30",
        0x82415C64: "lwz r11,88(r11)",
        0x82415C68: "mtctr r11",
        spec["resource_bind_dispatch_hook"]: "bctrl",
    }
    if any(
        resource_binding.get(address) != text
        for address, text in resource_binding_expected.items()
    ):
        raise ValueError("procedural-model resource resolution evidence drifted")

    resource_lookup_expected = {
        spec["resource_lookup_function"]: "lwz r11,0(r4)",
        0x82410A5C: "lwz r10,2812(r3)",
        0x82410A60: "rlwinm r11,r11,2,0,29",
        0x82410A64: "lwzx r3,r11,r10",
        0x82410A68: "blr",
    }
    resource_resolution_expected = {
        spec["resource_resolution_function"]: "mflr r12",
        0x82415AE4: "mr r29,r5",
        0x82415AF8: "lwz r10,0(r11)",
        0x82415AFC: "lwz r8,-4(r11)",
        0x82415B04: "cmpw cr6,r8,r4",
        0x82415B10: "addi r9,r11,-8",
        0x82415B40: "lwz r3,0(r9)",
        0x82415B4C: "stw r4,4(r31)",
        0x82415B50: "mr r3,r29",
        0x82415B58: "addi r4,r1,80",
        0x82415B60: "bl 0x82410a58",
        spec["resource_provider_lookup_hook"]: "mr. r30,r3",
        0x82415B6C: "lwz r11,0(r30)",
        0x82415B74: "lwz r11,24(r11)",
        0x82415B7C: "bctrl",
        spec["resource_provider_primary_predicate_hook"]:
            "clrlwi. r11,r3,24",
        0x82415B90: "lwz r11,36(r11)",
        0x82415B98: "lwz r11,44(r11)",
        0x82415BA0: "bctrl",
        spec["resource_provider_fallback_predicate_hook"]:
            "clrlwi. r11,r3,24",
        0x82415BB4: "lwz r11,40(r11)",
        0x82415BBC: "bctrl",
        spec["resource_provider_method_result_hook"]: "stw r3,0(r31)",
        0x82415BC4: "lwz r11,0(r31)",
        0x82415BD0: "lwz r11,8(r30)",
        0x82415BE0: "bl 0x823e58d8",
        spec["resource_secondary_resolution_result_hook"]:
            "stw r3,0(r31)",
        0x82415BE8: "lwz r3,0(r31)",
    }
    if any(
        resource_lookup.get(address) != text
        for address, text in resource_lookup_expected.items()
    ):
        raise ValueError("procedural-model resource lookup evidence drifted")
    if any(
        resource_resolution.get(address) != text
        for address, text in resource_resolution_expected.items()
    ):
        raise ValueError("procedural-model provider chain evidence drifted")

    rtti_verified = False
    complete_object_locator = None
    type_descriptor = None
    decorated_name = None
    if image is not None:
        vtable = spec["vtable_address"]
        complete_object_locator = _image_u32(image, vtable - 4)
        type_descriptor = _image_u32(image, complete_object_locator + 12)
        decorated_name = _image_c_string(image, type_descriptor + 8)
        slot_target = _image_u32(image, vtable + spec["vtable_slot"] * 4)
        visibility_target = _image_u32(
            image, vtable + spec["visibility_vtable_slot"] * 4
        )
        render_state_target = _image_u32(
            image, vtable + spec["render_state_vtable_slot"] * 4
        )
        deleting_target = _image_u32(image, vtable)
        if (
            decorated_name != spec["decorated_name"]
            or slot_target != spec["dispatch_function"]
            or visibility_target != spec["visibility_function"]
            or render_state_target != spec["render_state_function"]
            or deleting_target != spec["deleting_destructor_function"]
        ):
            raise ValueError("procedural-model RTTI/vtable evidence drifted")
        rtti_verified = True

    return {
        "class_name": spec["class_name"] if rtti_verified else "unknown",
        "decorated_name": decorated_name or "unverified_without_image",
        "complete_object_locator": (
            "{:08X}".format(complete_object_locator)
            if complete_object_locator is not None
            else "unverified_without_image"
        ),
        "type_descriptor": (
            "{:08X}".format(type_descriptor)
            if type_descriptor is not None
            else "unverified_without_image"
        ),
        "vtable_address": "{:08X}".format(spec["vtable_address"]),
        "vtable_slot": spec["vtable_slot"],
        "dispatch_function_address": "{:08X}".format(
            spec["dispatch_function"]
        ),
        "receiver_entry_register": "r3",
        "command_root_derivation": "r6+59712",
        "receiver_is_command_root": False,
        "constructor_function_address": "{:08X}".format(
            spec["constructor_function"]
        ),
        "constructor_entry_hook_address": "{:08X}".format(
            spec["constructor_entry"]
        ),
        "constructor_exit_hook_address": "{:08X}".format(
            spec["constructor_exit"]
        ),
        "destructor_function_address": "{:08X}".format(
            spec["destructor_function"]
        ),
        "destructor_entry_hook_address": "{:08X}".format(
            spec["destructor_entry"]
        ),
        "destructor_exit_hook_address": "{:08X}".format(
            spec["destructor_exit"]
        ),
        "deleting_destructor_function_address": "{:08X}".format(
            spec["deleting_destructor_function"]
        ),
        "object_size": 512,
        "visibility_function_address": "{:08X}".format(
            spec["visibility_function"]
        ),
        "visibility_vtable_slot": spec["visibility_vtable_slot"],
        "visibility_entry_hook_address": "{:08X}".format(
            spec["visibility_entry"]
        ),
        "visibility_exit_hook_address": "{:08X}".format(
            spec["visibility_exit"]
        ),
        "render_state_function_address": "{:08X}".format(
            spec["render_state_function"]
        ),
        "render_state_vtable_slot": spec["render_state_vtable_slot"],
        "render_state_entry_hook_address": "{:08X}".format(
            spec["render_state_entry"]
        ),
        "render_state_exit_hook_address": "{:08X}".format(
            spec["render_state_exit"]
        ),
        "render_item_function_address": "{:08X}".format(
            spec["render_item_function"]
        ),
        "render_item_entry_hook_address": "{:08X}".format(
            spec["render_item_entry_hook"]
        ),
        "render_item_exit_hook_address": "{:08X}".format(
            spec["render_item_exit_hook"]
        ),
        "field_layout": {
            "descriptor_owner_pointer_offset": 124,
            "runtime_record_pointer_offset": 128,
            "auxiliary_allocation_pointer_offset": 132,
            "active_buffer_index_offset": 136,
            "per_record_resource_capacity_offset": 140,
            "descriptor_record_stride": 92,
            "runtime_record_stride": 68,
            "matrix_ranges": [
                {"offset": 320, "size": 64},
                {"offset": 384, "size": 64},
                {"offset": 448, "size": 64},
            ],
        },
        "rtti_vtable_identity_proved": rtti_verified,
        "constructor_destructor_pair_proved": True,
        "object_extent_proved": True,
        "visibility_preparation_boundary_proved": True,
        "render_state_boundary_proved": True,
        "render_item_layout_proved": True,
        "semantic_instance_extraction": {
            "hook_function_address": "{:08X}".format(
                spec["render_item_function"]
            ),
            "hook_address": "{:08X}".format(
                spec["render_item_entry_hook"]
            ),
            "receiver_register": "r3",
            "descriptor_index_caller_stack_offset": 84,
            "descriptor_index_callee_stack_offset": 356,
            "descriptor_count_owner_offset": 12,
            "descriptor_base_owner_offset": 0,
            "descriptor_kind_offset": 36,
            "descriptor_record_stride": 92,
            "runtime_record_stride": 68,
            "bounded_payload_bytes_per_observation": 380,
            "immutable_sample_words": 88,
            "fallback_policy": "replay_unclassified_material_or_state",
            "argument_mapping_proved": True,
            "record_address_derivation_proved": True,
            "native_rendering_enabled": False,
            "suppression_eligible": False,
        },
        "semantic_submission_extraction": {
            "primary_resource_binding_hook_address": "{:08X}".format(
                spec["primary_resource_binding_hook"]
            ),
            "secondary_resource_binding_hook_address": "{:08X}".format(
                spec["secondary_resource_binding_hook"]
            ),
            "geometry_submission_hook_address": "{:08X}".format(
                spec["geometry_submission_hook"]
            ),
            "receiver_register": "r27",
            "graphics_context_register": "r31",
            "descriptor_record_register": "r28",
            "runtime_record_register": "r26",
            "resource_lookup_context_register": "r20",
            "descriptor_primary_resource_index_offset": 0,
            "descriptor_secondary_resource_index_offset": 4,
            "receiver_resource_table_offset": 8,
            "receiver_resource_table_stride": 8,
            "resource_binding_helper_function_address": "82415BF8",
            "resource_resolution_function_address": "{:08X}".format(
                spec["resource_resolution_function"]
            ),
            "resource_lookup_function_address": "{:08X}".format(
                spec["resource_lookup_function"]
            ),
            "resource_provider_lookup_hook_address": "{:08X}".format(
                spec["resource_provider_lookup_hook"]
            ),
            "resource_provider_primary_predicate_hook_address":
                "{:08X}".format(
                    spec["resource_provider_primary_predicate_hook"]
                ),
            "resource_provider_fallback_predicate_hook_address":
                "{:08X}".format(
                    spec["resource_provider_fallback_predicate_hook"]
                ),
            "resource_provider_method_result_hook_address": "{:08X}".format(
                spec["resource_provider_method_result_hook"]
            ),
            "resource_secondary_resolution_result_hook_address":
                "{:08X}".format(
                    spec["resource_secondary_resolution_result_hook"]
                ),
            "resource_provider_vtable_method_offsets": [24, 36, 40, 44],
            "resource_resolution_cache_entry_count": 5,
            "resource_resolution_cache_entry_stride": 12,
            "resource_resolution_cache_bound_object_offset": 0,
            "resource_resolution_cache_key_offset": 4,
            "resource_resolution_cache_usage_offset": 8,
            "resource_resolution_cache_shared_across_binding_slots": True,
            "resource_provider_routes": {
                "primary_method_36": {
                    "predicate_offset": 24,
                    "method_offset": 36,
                },
                "fallback_method_40": {
                    "predicate_offset": 44,
                    "method_offset": 40,
                },
                "provider_unavailable": {
                    "predicate_offset": 44,
                    "secondary_resolution_function_address": "823E58D8",
                },
                "null_provider_method_result": {
                    "secondary_resolution_function_address": "823E58D8",
                },
            },
            "resource_resolution_result_hook_address": "{:08X}".format(
                spec["resource_resolution_result_hook"]
            ),
            "resource_bind_dispatch_hook_address": "{:08X}".format(
                spec["resource_bind_dispatch_hook"]
            ),
            "resource_bind_dispatch_vtable_offset": 88,
            "resource_binding_slots": [0, 1],
            "resource_binding_key_cache_address": "834AD4CC",
            "resource_binding_key_cache_entry_count": 5,
            "resource_binding_key_cache_entry_stride": 4,
            "resource_binding_key_cache_indexed_by_binding_slot": True,
            "resource_binding_key_cache_skips_unchanged_bind": True,
            "runtime_submission_object_offset": 0,
            "runtime_default_source_address_offset": 24,
            "runtime_count_units_offset": 28,
            "runtime_counted_source_address_offset": 32,
            "graphics_submission_vtable_offset": 160,
            "graphics_submission_primitive": 13,
            "graphics_submission_count_scale": 4,
            "descriptor_kind_groups": {
                "kind_4_5": [4, 5],
                "kind_1_3": [1, 3],
                "other": "all_remaining_values",
            },
            "helper_state_families": {
                "state_9_table_4_28": [9],
                "state_11_table_196_220": [11],
                "state_24_27_table_148_172": [24, 25, 26, 27],
                "state_6_8_table_100_124": [6, 7, 8],
                "default_table_52_76": "all_remaining_values",
            },
            "descriptor_scalar_offsets": [64, 68],
            "runtime_scalar_offsets": [40],
            "resource_binding_derivation_proved": True,
            "resolved_resource_object_derivation_proved": True,
            "resource_provider_chain_derivation_proved": True,
            "resource_provider_method_identity_runtime_join_required": True,
            "secondary_resolution_semantics_proved": False,
            "descriptor_kind_partition_proved": True,
            "helper_state_partition_proved": True,
            "record_join_proved": True,
            "geometry_submission_derivation_proved": True,
            "graphics_submission_vtable_runtime_join_required": True,
            "classification": "resolved_resource_state_variant_and_dispatch_submission",
            "fallback_policy": "replay_unclassified_material_or_state",
            "native_rendering_enabled": False,
            "suppression_eligible": False,
        },
        "semantic_draw_association": {
            "render_item_entry_hook_address": "{:08X}".format(
                spec["render_item_entry_hook"]
            ),
            "render_item_exit_hook_address": "{:08X}".format(
                spec["render_item_exit_hook"]
            ),
            "geometry_submission_hook_address": "{:08X}".format(
                spec["geometry_submission_hook"]
            ),
            "title_draw_packet_hook_addresses": ["82410328", "829F7CB0"],
            "title_indirect_packet_hook_addresses": [
                "824095B4",
                "82416EFC",
                "8246FC1C",
                "8263BD64",
                "829E8E88",
                "829EC49C",
            ],
            "graphics_submission_vtable_offset": 160,
            "graphics_submission_target_runtime_join_required": True,
            "render_item_invocation_scope_proved": True,
            "submission_before_draw_dispatch_proved": True,
            "direct_title_packet_overlap_probe": True,
            "indirect_packet_constructor_overlap_probe": True,
            "physical_pm4_packet_correlation_proved": False,
            "prepared_draw_lineage_proved": False,
            "classification": "procedural_submission_dispatch_boundary",
            "native_rendering_enabled": False,
            "suppression_eligible": False,
        },
        "runtime_address_join_required": True,
        "mesh_material_ownership_proved": False,
        "transform_matrix_ranges_proved": True,
        "visibility_runtime_join_required": True,
        "render_state_runtime_join_required": True,
        "lod_meaning_proved": False,
        "streaming_registration_proved": False,
        "suppression_eligible": False,
    }


def argument_leads_for_calls(
    functions: list[dict], calls: list[dict], target_key: str
) -> list[dict]:
    """Record bounded local r3-r10 definitions for an exact direct call."""
    functions_by_address = {item["address"]: item for item in functions}
    leads = []
    for call in calls:
        function = functions_by_address[int(call["caller_function_address"], 16)]
        instructions = function["instructions"]
        call_index = next(
            index
            for index, instruction in enumerate(instructions)
            if instruction["address"] == int(call["callsite"], 16)
        )
        definitions = []
        for register_index in range(3, 11):
            register = f"r{register_index}"
            definition = None
            crossed_call = False
            for instruction in reversed(instructions[:call_index]):
                if CALL_BOUNDARY_RE.fullmatch(instruction["text"]):
                    crossed_call = True
                    break
                match = REGISTER_DEFINITION_RE.match(instruction["text"])
                if (
                    not match
                    or match.group(2) != register
                    or match.group(1) not in DEFINITION_OPERATIONS
                ):
                    continue
                definition = instruction
                break
            if definition is None:
                definitions.append(
                    {
                        "register": register,
                        "status": (
                            "unknown_across_call_boundary"
                            if crossed_call
                            else "entry_register"
                        ),
                    }
                )
                continue
            text = definition["text"]
            operation = text.split(" ", 1)[0]
            operands = text.split(" ", 1)[1].split(",")
            source_registers = re.findall(r"r\d+", ",".join(operands[1:]))
            item = {
                "register": register,
                "status": "bounded_syntactic_definition",
                "address": "{:08X}".format(definition["address"]),
                "operation": operation,
                "instruction": text,
                "source_registers": source_registers,
            }
            memory = MEMORY_LOAD_RE.fullmatch(text)
            if memory:
                item["memory_load"] = {
                    "base_register": memory.group(4),
                    "offset": int(memory.group(3)),
                    "width": memory.group(1),
                }
            definitions.append(item)
        leads.append(
            {
                target_key: call[target_key],
                "caller_function": call["caller_function"],
                "caller_function_address": call["caller_function_address"],
                "callsite": call["callsite"],
                "return_address": call["return_address"],
                "arguments": definitions,
                "classification": "bounded_syntactic_object_lead_only",
                "interprocedural_dataflow": False,
                "object_identity_proved": False,
                "lifetime_proved": False,
                "suppression_eligible": False,
            }
        )
    return leads


def adapter_argument_leads(functions: list[dict], calls: list[dict]) -> list[dict]:
    functions_by_address = {item["address"]: item for item in functions}
    leads = []
    for call in calls:
        if call["wrapper"] != "824079B8":
            continue
        function = functions_by_address[int(call["caller_function_address"], 16)]
        instructions = function["instructions"]
        call_index = next(
            index
            for index, instruction in enumerate(instructions)
            if instruction["address"] == int(call["callsite"], 16)
        )
        definitions = []
        for register_index in range(3, 11):
            register = f"r{register_index}"
            definition = None
            crossed_call = False
            for instruction in reversed(instructions[:call_index]):
                if CALL_BOUNDARY_RE.fullmatch(instruction["text"]):
                    crossed_call = True
                    break
                match = REGISTER_DEFINITION_RE.match(instruction["text"])
                if not match or match.group(2) != register:
                    continue
                if match.group(1) not in DEFINITION_OPERATIONS:
                    continue
                definition = instruction
                break
            if definition is None:
                definitions.append(
                    {
                        "register": register,
                        "status": (
                            "unknown_across_call_boundary"
                            if crossed_call
                            else "entry_register"
                        ),
                    }
                )
                continue
            text = definition["text"]
            operation = text.split(" ", 1)[0]
            operands = text.split(" ", 1)[1].split(",")
            source_registers = re.findall(r"r\d+", ",".join(operands[1:]))
            item = {
                "register": register,
                "status": "bounded_syntactic_definition",
                "address": "{:08X}".format(definition["address"]),
                "operation": operation,
                "instruction": text,
                "source_registers": source_registers,
            }
            memory = MEMORY_LOAD_RE.fullmatch(text)
            if memory:
                item["memory_load"] = {
                    "base_register": memory.group(4),
                    "offset": int(memory.group(3)),
                    "width": memory.group(1),
                }
            definitions.append(item)
        leads.append(
            {
                "wrapper": call["wrapper"],
                "caller_function": call["caller_function"],
                "caller_function_address": call["caller_function_address"],
                "callsite": call["callsite"],
                "return_address": call["return_address"],
                "arguments": definitions,
                "classification": "bounded_syntactic_object_lead_only",
                "interprocedural_dataflow": False,
                "object_identity_proved": False,
                "lifetime_proved": False,
                "suppression_eligible": False,
            }
        )
    return leads


def tail_forwarded_calls(
    functions: list[dict], targets: set[int]
) -> list[dict]:
    forwarders = {}
    for function in functions:
        branches = [
            (instruction, int(match.group(1), 16))
            for instruction in function["instructions"]
            if (match := BRANCH_RE.fullmatch(instruction["text"]))
            and int(match.group(1), 16) in targets
        ]
        if len(branches) > 1:
            raise ValueError("reviewed wrapper tail-forwarder is ambiguous")
        if branches:
            forwarders[function["address"]] = branches[0]

    calls = []
    for function in functions:
        for instruction in function["instructions"]:
            match = CALL_RE.fullmatch(instruction["text"])
            if not match:
                continue
            forwarder_address = int(match.group(1), 16)
            forwarded = forwarders.get(forwarder_address)
            if not forwarded:
                continue
            branch, target = forwarded
            calls.append(
                {
                    "wrapper": "{:08X}".format(target),
                    "wrapper_kind": REVIEWED_WRAPPERS[target]["kind"],
                    "wrapper_layer": REVIEWED_WRAPPERS[target]["layer"],
                    "caller_function": function["name"],
                    "caller_function_address": "{:08X}".format(
                        function["address"]
                    ),
                    "callsite": "{:08X}".format(instruction["address"]),
                    "return_address": "{:08X}".format(
                        instruction["address"] + 4
                    ),
                    "dispatch_edge": "tail_forwarded",
                    "forwarder_function": "sub_{:08X}".format(
                        forwarder_address
                    ),
                    "forwarder_function_address": "{:08X}".format(
                        forwarder_address
                    ),
                    "forwarder_branch": "{:08X}".format(branch["address"]),
                }
            )
    return sorted(calls, key=lambda item: (item["wrapper"], item["callsite"]))


def dirty_state_clears(functions: list[dict]) -> list[dict]:
    """Find reviewed consume-then-clear writes in the indexed draw wrapper."""
    sites = []
    function = next(
        (item for item in functions if item["address"] == 0x8240F4D8), None
    )
    if function is None:
        return sites
    instructions = function["instructions"]
    for index, instruction in enumerate(instructions):
        store = DIRTY_STORE_RE.fullmatch(instruction["text"])
        if not store:
            continue
        register, offset = store.groups()
        prior = instructions[max(0, index - 7) : index]
        loaded = any(
            item["text"] == f"ld {register},{offset}(r31)" for item in prior
        )
        cleared = any(
            re.fullmatch(rf"(?:and|rldicr) {register},{register},.+", item["text"])
            for item in prior
        )
        if not loaded or not cleared:
            continue
        submission = next(
            (
                item
                for item in reversed(prior)
                if CALL_RE.fullmatch(item["text"])
            ),
            None,
        )
        sites.append(
            {
                "wrapper": "8240F4D8",
                "wrapper_kind": "draw_indexed",
                "address": "{:08X}".format(instruction["address"]),
                "mask_word_offset": int(offset),
                "transition": "consume_then_clear",
                "submission_callsite": (
                    "{:08X}".format(submission["address"])
                    if submission
                    else None
                ),
            }
        )
    return sites


def query_state_transitions(functions: list[dict]) -> list[dict]:
    sites = []
    for function in functions:
        reviewed = REVIEWED_WRAPPERS.get(function["address"])
        if not reviewed or not reviewed["kind"].startswith("viz_query_"):
            continue
        instructions = function["instructions"]
        for index, instruction in enumerate(instructions):
            store = QUERY_STATE_STORE_RE.fullmatch(instruction["text"])
            if not store:
                continue
            register = store.group(1)
            prior = instructions[max(0, index - 5) : index]
            operation = next(
                (
                    item["text"].split(" ", 1)[0]
                    for item in reversed(prior)
                    if re.fullmatch(rf"(?:or|andc) {register},.+", item["text"])
                ),
                None,
            )
            if operation not in ("or", "andc"):
                continue
            sites.append(
                {
                    "wrapper": "{:08X}".format(function["address"]),
                    "wrapper_kind": reviewed["kind"],
                    "address": "{:08X}".format(instruction["address"]),
                    "active_query_word_offset": 12424,
                    "transition": "set_active" if operation == "or" else "clear_active",
                }
            )
    return sites


def resolve_mode_writes(functions: list[dict]) -> list[dict]:
    function = next(
        (item for item in functions if item["address"] == 0x82458A88), None
    )
    if function is None:
        return []
    instructions = function["instructions"]
    sites = []
    for index, instruction in enumerate(instructions):
        register_match = re.fullmatch(r"li (r\d+),8712", instruction["text"])
        if not register_match:
            continue
        window = instructions[index + 1 : index + 10]
        value_load = next(
            (
                item
                for item in window
                if re.fullmatch(r"li (r\d+),6", item["text"])
            ),
            None,
        )
        register_store = next(
            (
                item
                for item in window
                if item["text"].startswith(f"stwu {register_match.group(1)},")
            ),
            None,
        )
        if value_load is None or register_store is None:
            continue
        value_register = value_load["text"].split(" ", 1)[1].split(",", 1)[0]
        value_store = next(
            (
                item
                for item in window
                if item["address"] > register_store["address"]
                and item["text"].startswith(f"stwu {value_register},")
            ),
            None,
        )
        if value_store is None:
            continue
        sites.append(
            {
                "wrapper": "82458A88",
                "wrapper_kind": "resolve_setup",
                "register_index": "2208",
                "register_name": "RB_MODECONTROL",
                "register_write_address": "{:08X}".format(
                    register_store["address"]
                ),
                "value": 6,
                "value_name": "EdramMode::kCopy",
                "value_write_address": "{:08X}".format(value_store["address"]),
            }
        )
    return sites


def query_owner_lifecycle(functions: list[dict]) -> dict:
    owner_address = 0x82D951E0
    begin_target = 0x829F21A0
    end_target = 0x829F2280
    function = next(
        (item for item in functions if item["address"] == owner_address), None
    )
    if function is None:
        return {}
    calls = []
    for instruction in function["instructions"]:
        match = CALL_RE.fullmatch(instruction["text"])
        if not match:
            continue
        calls.append(
            {
                "target": "{:08X}".format(int(match.group(1), 16)),
                "callsite": "{:08X}".format(instruction["address"]),
                "return_address": "{:08X}".format(
                    instruction["address"] + 4
                ),
            }
        )
    begin_calls = [item for item in calls if item["target"] == "829F21A0"]
    end_calls = [item for item in calls if item["target"] == "829F2280"]
    if len(begin_calls) != 1 or len(end_calls) != 1:
        raise ValueError("reviewed visibility-query owner lifecycle drifted")
    begin_address = int(begin_calls[0]["callsite"], 16)
    end_address = int(end_calls[0]["callsite"], 16)
    if begin_address >= end_address:
        raise ValueError("reviewed visibility-query owner order drifted")
    work_calls = [
        item
        for item in calls
        if begin_address < int(item["callsite"], 16) < end_address
    ]
    if not work_calls:
        raise ValueError("reviewed visibility-query owner has no enclosed work")
    return {
        "owner": "82D951E0",
        "owner_kind": "viz_query_owner",
        "begin_wrapper": "829F21A0",
        "begin_callsite": begin_calls[0]["callsite"],
        "end_wrapper": "829F2280",
        "end_callsite": end_calls[0]["callsite"],
        "work_calls_between": work_calls,
        "classification": "query_lifecycle_owner_proved_semantics_unknown",
        "suppression_eligible": False,
    }


def reviewed_side_effect_packets(constructors: list[dict]) -> dict:
    by_function = collections.defaultdict(list)
    for constructor in constructors:
        by_function[constructor["function_address"]].append(constructor)

    controller = by_function["824587D8"]
    setup = by_function["82458A88"]
    expected_controller = collections.Counter(
        {
            "PM4_EVENT_WRITE": 1,
            "PM4_MEM_WRITE": 2,
            "PM4_WAIT_REG_MEM": 2,
            "PM4_EVENT_WRITE_EXT": 1,
        }
    )
    expected_setup = collections.Counter(
        {
            "PM4_SET_BIN_MASK_LO": 2,
            "PM4_SET_BIN_MASK_HI": 2,
            "PM4_EVENT_WRITE_ZPD": 1,
        }
    )
    if collections.Counter(item["opcode"] for item in controller) != expected_controller:
        raise ValueError("reviewed resolve-controller packet sequence drifted")
    if collections.Counter(item["opcode"] for item in setup) != expected_setup:
        raise ValueError("reviewed resolve-setup packet sequence drifted")

    binning = {}
    for address, expected in {
        "82413AB8": {"PM4_SET_BIN_MASK_LO", "PM4_SET_BIN_MASK_HI"},
        "824736F0": {
            "PM4_SET_BIN_MASK_LO",
            "PM4_SET_BIN_MASK_HI",
            "PM4_SET_BIN_SELECT_LO",
            "PM4_SET_BIN_SELECT_HI",
        },
    }.items():
        observed = {item["opcode"] for item in by_function[address]}
        if not expected.issubset(observed):
            raise ValueError(
                "reviewed binning-state packet evidence drifted: {}".format(
                    address
                )
            )
        binning[address] = by_function[address]

    return {
        "resolve_controller": controller,
        "resolve_setup": setup,
        "binning_state_wrappers": binning,
        "semantic_identity": "unknown",
        "suppression_eligible": False,
    }


def draw_packet_provenance(constructors: list[dict], calls: list[dict]) -> dict:
    expected = {
        "8240F4D8": {
            "constructor_address": "82410320",
            "store_address": "82410328",
            "packet_hook_address": "82410328",
        },
        "829F7C70": {
            "constructor_address": "829F7CA8",
            "store_address": "829F7CB0",
            "packet_hook_address": "829F7CB0",
        },
    }
    packet_sites = []
    for wrapper, required in expected.items():
        matches = [
            item
            for item in constructors
            if item["function_address"] == wrapper
            and item["opcode"] == "PM4_DRAW_INDX_2"
            and item["role"] == "runtime_wrapper"
        ]
        if len(matches) != 1:
            raise ValueError(
                "reviewed draw wrapper must have one runtime packet store: {}".format(
                    wrapper
                )
            )
        packet = matches[0]
        for field in ("constructor_address", "store_address"):
            if packet[field] != required[field]:
                raise ValueError(
                    "reviewed draw packet {} drifted for {}".format(field, wrapper)
                )
        packet_sites.append(
            {
                "wrapper": wrapper,
                "wrapper_kind": REVIEWED_WRAPPERS[int(wrapper, 16)]["kind"],
                **required,
                "packet_opcode": "PM4_DRAW_INDX_2",
                "packet_address_expression": "physical(r3_plus_4_before_stwu)",
            }
        )
    adapter_forward = [
        item
        for item in calls
        if item["caller_function_address"] == "824079B8"
        and item["wrapper"] == "8240F4D8"
    ]
    if len(adapter_forward) != 1 or adapter_forward[0]["return_address"] != "824079FC":
        raise ValueError("draw adapter forwarding return address drifted")
    return {
        "packet_sites": packet_sites,
        "adapter_forward_return_address": "824079FC",
        "backend_observation_field": "packet_physical_address",
        "correlation": "exact_physical_pm4_header_address",
        "guest_payload_read": False,
        "guest_state_changed": False,
        "control_flow_changed": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }


def build(paths: list[pathlib.Path], image: bytes | None = None) -> dict:
    functions = parse_functions(paths)
    functions_by_address = {item["address"]: item for item in functions}
    for address, wrapper in REVIEWED_WRAPPERS.items():
        function = functions_by_address.get(address)
        if (
            function is None
            or not function["instructions"]
            or function["instructions"][0]["address"] != address
            or function["instructions"][0]["text"] != "mflr r12"
            or wrapper["hook_address"] != address + 4
        ):
            raise ValueError(
                "reviewed wrapper entry LR evidence missing: {:08X}".format(address)
            )
    constructors = packet_constructors(functions)
    constructor_calls = indirect_constructor_calls(functions, constructors)
    constructor_hooks = indirect_constructor_runtime_hooks(
        functions_by_address, constructors
    )
    owner_calls = indirect_owner_calls(functions)
    owner_hooks = indirect_owner_runtime_hooks(functions_by_address)
    producer_calls = indirect_producer_calls(functions)
    producer_hooks = indirect_producer_runtime_hooks(functions_by_address)
    context_hooks = indirect_context_runtime_hooks(functions_by_address)
    context_roots = indirect_context_roots(functions_by_address)
    semantic_receiver = procedural_model_receiver_lifecycle(
        functions_by_address, image
    )
    constructor_argument_leads = argument_leads_for_calls(
        functions, constructor_calls, "constructor_function_address"
    )
    owner_argument_leads = argument_leads_for_calls(
        functions, owner_calls, "owner_function_address"
    )
    producer_argument_leads = argument_leads_for_calls(
        functions, producer_calls, "producer_function_address"
    )
    constructor_evidence = {
        (int(item["function_address"], 16), int(item["opcode_value"], 16))
        for item in constructors
    }
    expected_packet_evidence = set()
    for address, wrapper in REVIEWED_WRAPPERS.items():
        if "packet_opcode" in wrapper:
            expected_packet_evidence.add((address, int(wrapper["packet_opcode"])))
        expected_packet_evidence.update(
            (address, int(opcode))
            for opcode in wrapper.get("packet_opcodes", [])
        )
    missing = expected_packet_evidence - constructor_evidence
    if missing:
        raise ValueError(
            "reviewed wrapper packet evidence missing: {}".format(
                ", ".join(
                    "{:08X}/0x{:02X}".format(address, opcode)
                    for address, opcode in sorted(missing)
                )
            )
        )
    calls = direct_calls(functions, set(REVIEWED_WRAPPERS))
    argument_leads = adapter_argument_leads(functions, calls)
    forwarded_calls = tail_forwarded_calls(
        functions, set(REVIEWED_WRAPPERS)
    )
    correlation_calls = sorted(
        [*calls, *forwarded_calls],
        key=lambda item: (item["wrapper"], item["callsite"]),
    )
    adapter_calls = [
        item
        for item in calls
        if item["caller_function_address"] == "824079B8"
        and item["wrapper"] == "8240F4D8"
    ]
    if len(adapter_calls) != 1:
        raise ValueError("draw adapter must directly call indexed wrapper once")
    resolve_controller_calls = [
        item
        for item in calls
        if item["caller_function_address"] == "824587D8"
        and item["wrapper"] == "82458A88"
    ]
    if len(resolve_controller_calls) != 2:
        raise ValueError("resolve controller must directly call setup wrapper twice")
    clears = dirty_state_clears(functions)
    observed_clear_words = collections.Counter(
        item["mask_word_offset"] for item in clears
    )
    if observed_clear_words != {16: 4, 24: 1, 32: 1}:
        raise ValueError("reviewed indexed-draw dirty-state clear evidence drifted")
    query_transitions = query_state_transitions(functions)
    expected_query_transitions = {
        ("viz_query_begin", "set_active"),
        ("viz_query_end", "clear_active"),
    }
    observed_query_transitions = {
        (item["wrapper_kind"], item["transition"])
        for item in query_transitions
    }
    if observed_query_transitions != expected_query_transitions:
        raise ValueError("reviewed visibility-query state evidence drifted")
    resolve_writes = resolve_mode_writes(functions)
    if len(resolve_writes) != 1:
        raise ValueError("reviewed title resolve-mode write evidence drifted")
    query_owner = query_owner_lifecycle(functions)
    side_effect_packets = reviewed_side_effect_packets(constructors)
    packet_provenance = draw_packet_provenance(constructors, calls)
    query_owner_callers = [
        item
        for item in calls
        if item["wrapper_kind"] == "viz_query_owner"
    ]
    if len(query_owner_callers) != 2:
        raise ValueError("reviewed visibility-query owner callers drifted")
    query_owner["direct_callers"] = query_owner_callers
    return {
        "schema": SCHEMA,
        "input": {
            "generated_files": len(paths),
            "functions": len(functions),
        },
        "packet_constructors": constructors,
        "indirect_constructor_calls": constructor_calls,
        "indirect_constructor_runtime_hooks": constructor_hooks,
        "indirect_constructor_argument_leads": constructor_argument_leads,
        "indirect_owner_calls": owner_calls,
        "indirect_owner_runtime_hooks": owner_hooks,
        "indirect_owner_argument_leads": owner_argument_leads,
        "indirect_producer_calls": producer_calls,
        "indirect_producer_runtime_hooks": producer_hooks,
        "indirect_producer_argument_leads": producer_argument_leads,
        "indirect_context_runtime_hooks": context_hooks,
        "indirect_context_roots": context_roots,
        "procedural_model_receiver_lifecycle": semantic_receiver,
        "reviewed_wrappers": [
            {
                "address": "{:08X}".format(address),
                "kind": wrapper["kind"],
                "layer": wrapper["layer"],
                "evidence": (
                    wrapper["evidence"]
                    if "evidence" in wrapper
                    else ",".join(
                        PACKET_OPCODES[opcode]
                        for opcode in (
                            [wrapper["packet_opcode"]]
                            if "packet_opcode" in wrapper
                            else wrapper["packet_opcodes"]
                        )
                    )
                ),
                "runtime_trace": "entry_lr_and_bounded_r3_r10_metadata",
                "hook_address": "{:08X}".format(wrapper["hook_address"]),
                "observed_entry_registers": [
                    "r3",
                    "r4",
                    "r5",
                    "r6",
                    "r7",
                    "r8",
                    "r9",
                    "r10",
                ],
                "caller_lr_register": "r12_after_opening_mflr",
                "stack_argument_offsets": wrapper.get(
                    "stack_argument_offsets", []
                ),
            }
            for address, wrapper in sorted(REVIEWED_WRAPPERS.items())
        ],
        "direct_calls": calls,
        "tail_forwarded_calls": forwarded_calls,
        "runtime_correlation_calls": correlation_calls,
        "adapter_argument_leads": argument_leads,
        "dirty_state_clears": clears,
        "query_state_transitions": query_transitions,
        "query_owner_lifecycle": query_owner,
        "resolve_mode_writes": resolve_writes,
        "side_effect_packets": side_effect_packets,
        "draw_packet_provenance": packet_provenance,
        "resolve_boundary": {
            "backend": "IssueCopy",
            "trigger": "RB_MODECONTROL.edram_mode == kCopy during Xenos draw",
            "title_controller": "824587D8",
            "title_wrapper": "82458A88",
            "classification": "title_resolve_setup_and_backend_copy_proved",
        },
        "totals": {
            "packet_constructors": len(constructors),
            "indirect_constructor_calls": len(constructor_calls),
            "indirect_constructor_runtime_hooks": len(constructor_hooks),
            "indirect_constructor_argument_leads": len(
                constructor_argument_leads
            ),
            "indirect_owner_calls": len(owner_calls),
            "indirect_owner_runtime_hooks": len(owner_hooks),
            "indirect_owner_argument_leads": len(owner_argument_leads),
            "indirect_producer_calls": len(producer_calls),
            "indirect_producer_runtime_hooks": len(producer_hooks),
            "indirect_producer_argument_leads": len(
                producer_argument_leads
            ),
            "indirect_context_runtime_hooks": len(context_hooks),
            "indirect_context_roots": len(context_roots),
            "procedural_model_receiver_lifecycles": bool(semantic_receiver),
            "reviewed_wrappers": len(REVIEWED_WRAPPERS),
            "direct_calls": len(calls),
            "tail_forwarded_calls": len(forwarded_calls),
            "runtime_correlation_calls": len(correlation_calls),
            "adapter_argument_leads": len(argument_leads),
            "dirty_state_clears": len(clears),
            "query_state_transitions": len(query_transitions),
            "resolve_mode_writes": len(resolve_writes),
            "query_owner_callers": len(query_owner_callers),
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
    parser.add_argument("--image", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        paths = list(args.generated_root.glob("pinyon_shift_recomp.*.cpp"))
        if not paths:
            raise ValueError("no generated AOT C++ files found")
        image = args.image.read_bytes() if args.image else None
        document = build(paths, image)
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
