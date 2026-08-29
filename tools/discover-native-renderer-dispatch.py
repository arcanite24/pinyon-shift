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


def build(paths: list[pathlib.Path]) -> dict:
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
    constructor_argument_leads = argument_leads_for_calls(
        functions, constructor_calls, "constructor_function_address"
    )
    owner_argument_leads = argument_leads_for_calls(
        functions, owner_calls, "owner_function_address"
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
