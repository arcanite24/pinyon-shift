"""Summarize exact backend draw-to-command-buffer lineage evidence."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-command-lineage.v1"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
PREFIX = "native_renderer.discovery.command_buffer_lineage_"
INDIRECT_OPCODES = {"PM4_INDIRECT_BUFFER", "PM4_INDIRECT_BUFFER_PFD"}
PHYSICAL_APERTURE_SIZE = 0x20000000
KNOWN_PREPARED_FAMILIES = {
    "747837906D0BF484": "retained_sky_horizon_anchor",
    "1D253A52B55C9FB3": "retained_sky_horizon_follower",
}


def read_events(paths: list[pathlib.Path]) -> list[dict]:
    events = []
    for path in paths:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if str(event.get("event", "")).startswith(PREFIX):
                events.append(event)
    return events


def select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"command-buffer lineage session not found: {requested}")
        return requested
    armed = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == f"{PREFIX}config"
        and event.get("status") == "armed"
    ]
    if not armed or not armed[-1]:
        raise ValueError("no armed command-buffer lineage session found")
    return armed[-1]


def _integer(mapping: dict, key: str) -> int:
    try:
        return int(mapping.get(key, 0))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid integer field: {key}") from error


def _hex(mapping: dict, key: str, width: int) -> str:
    value = str(mapping.get(key, "")).upper()
    if len(value) != width:
        raise ValueError(f"invalid hexadecimal field: {key}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid hexadecimal field: {key}") from error
    return value


def _optional_hex(mapping: dict, key: str, width: int) -> str | None:
    value = str(mapping.get(key, "unknown")).upper()
    if value == "UNKNOWN":
        return None
    return _hex({key: value}, key, width)


def _hex_arguments(mapping: dict, key: str) -> list[str]:
    values = str(mapping.get(key, "")).upper().split(",")
    if len(values) != 8:
        raise ValueError(f"invalid constructor argument vector: {key}")
    for value in values:
        if len(value) != 8:
            raise ValueError(f"invalid constructor argument vector: {key}")
        try:
            int(value, 16)
        except ValueError as error:
            raise ValueError(
                f"invalid constructor argument vector: {key}"
            ) from error
    return values


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    constructors = [
        item
        for item in static.get("packet_constructors", [])
        if item.get("opcode") in INDIRECT_OPCODES
    ]
    if not constructors:
        raise ValueError("static inventory has no stored indirect-buffer constructors")
    constructor_store_addresses = {
        str(item.get("store_address", "")).upper() for item in constructors
    }
    constructor_functions_by_store = {
        str(item.get("store_address", "")).upper(): str(
            item.get("function_address", "")
        ).upper()
        for item in constructors
    }
    static_constructor_calls = static.get("indirect_constructor_calls", [])
    constructor_calls_by_return = {
        (
            str(item.get("constructor_function_address", "")).upper(),
            str(item.get("return_address", "")).upper(),
        ): item
        for item in static_constructor_calls
    }

    session = select_session(events, requested)
    selected = [event for event in events if event.get("session") == session]
    configs = [
        event
        for event in selected
        if event.get("event") == f"{PREFIX}config"
        and event.get("status") == "armed"
    ]
    summaries = [
        event for event in selected if event.get("event") == f"{PREFIX}summary"
    ]
    if len(configs) != 1 or len(summaries) != 1:
        raise ValueError("lineage session needs one armed config and summary")
    summary = summaries[0]
    required_safety = {
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(
        str(summary.get(key)).lower() != value
        for key, value in required_safety.items()
    ):
        raise ValueError("lineage summary does not prove the safety boundary")
    if (
        str(summary.get("correlation"))
        != "exact_title_store_to_backend_nested_command_buffer_shape"
    ):
        raise ValueError("lineage summary uses an unsupported correlation key")

    entries = []
    for event in selected:
        if event.get("event") != f"{PREFIX}entry":
            continue
        signature = _hex(event, "sample_prepared_signature", 16)
        packet = _hex(event, "sample_packet_physical_address", 8)
        current = _hex(event, "sample_command_buffer_physical_address", 8)
        parent = _hex(event, "sample_parent_packet_physical_address", 8)
        root = _hex(event, "sample_root_physical_address", 8)
        calls = _integer(event, "calls")
        sample_length = _integer(
            event, "sample_command_buffer_length_dwords"
        )
        min_length = _integer(event, "min_command_buffer_length_dwords")
        max_length = _integer(event, "max_command_buffer_length_dwords")
        min_packet_offset = _integer(event, "min_packet_offset_bytes")
        max_packet_offset = _integer(event, "max_packet_offset_bytes")
        depth = _integer(event, "depth")
        if (
            not calls
            or not sample_length
            or not min_length
            or not min_length <= sample_length <= max_length
            or depth < 0
        ):
            raise ValueError("lineage entry has invalid count, length, or depth")
        packet_value = int(packet, 16)
        current_value = int(current, 16)
        parent_value = int(parent, 16)
        root_value = int(root, 16)
        buffer_end = current_value + sample_length * 4
        if (
            current_value & 3
            or packet_value & 3
            or root_value & 3
            or buffer_end > PHYSICAL_APERTURE_SIZE
            or root_value >= PHYSICAL_APERTURE_SIZE
        ):
            raise ValueError("lineage entry has an invalid physical address")
        if not current_value <= packet_value < buffer_end:
            raise ValueError("lineage packet is outside its command buffer")
        sample_packet_offset = packet_value - current_value
        if not 0 <= min_packet_offset <= sample_packet_offset <= max_packet_offset:
            raise ValueError("lineage packet-offset bounds exclude their sample")
        if max_packet_offset >= max_length * 4:
            raise ValueError(
                "lineage packet-offset bounds exceed their maximum buffer"
            )
        min_parent_root_text = str(
            event.get("min_parent_root_offset_bytes", "")
        )
        max_parent_root_text = str(
            event.get("max_parent_root_offset_bytes", "")
        )
        constructor_text = str(
            event.get("constructor_store_address", "unknown")
        ).upper()
        if constructor_text == "UNKNOWN":
            constructor_store_address = None
        else:
            if constructor_text not in constructor_store_addresses:
                raise ValueError(
                    "lineage entry references an unproved constructor store"
                )
            constructor_store_address = constructor_text
        constructor_function_address = _optional_hex(
            event, "constructor_function_address", 8
        )
        constructor_return_address = _optional_hex(
            event, "constructor_return_address", 8
        )
        if (constructor_function_address is None) != (
            constructor_return_address is None
        ):
            raise ValueError("lineage entry has a partial constructor origin")
        constructor_call = None
        constructor_arguments = None
        constructor_argument_varying_mask = None
        if constructor_function_address is not None:
            if constructor_store_address is None:
                raise ValueError(
                    "lineage entry has an origin without a constructor store"
                )
            if (
                constructor_functions_by_store[constructor_store_address]
                != constructor_function_address
            ):
                raise ValueError(
                    "lineage entry constructor function does not own its store"
                )
            constructor_call = constructor_calls_by_return.get(
                (constructor_function_address, constructor_return_address)
            )
            constructor_arguments = _hex_arguments(
                event, "sample_constructor_arguments"
            )
            constructor_argument_varying_mask = int(
                _hex(event, "constructor_argument_varying_mask", 2), 16
            )
        if depth:
            if parent_value >= PHYSICAL_APERTURE_SIZE or parent_value & 3:
                raise ValueError("indirect lineage entry has no valid parent packet")
            if depth == 1 and root != current:
                raise ValueError("first indirect lineage root differs from its buffer")
            if depth == 1:
                if (
                    min_parent_root_text != "none"
                    or max_parent_root_text != "none"
                ):
                    raise ValueError(
                        "first indirect lineage has parent-root offset bounds"
                    )
                min_parent_root_offset = None
                max_parent_root_offset = None
            else:
                if parent_value < root_value:
                    raise ValueError("nested parent packet precedes its root buffer")
                try:
                    min_parent_root_offset = int(min_parent_root_text)
                    max_parent_root_offset = int(max_parent_root_text)
                except ValueError as error:
                    raise ValueError(
                        "invalid nested parent-root offset bounds"
                    ) from error
                sample_parent_root_offset = parent_value - root_value
                if not (
                    0
                    <= min_parent_root_offset
                    <= sample_parent_root_offset
                    <= max_parent_root_offset
                ):
                    raise ValueError(
                        "nested parent-root offset bounds exclude their sample"
                    )
        elif parent != "FFFFFFFF" or root != current:
            raise ValueError("direct lineage entry has invalid root or parent")
        else:
            if (
                min_parent_root_text != "none"
                or max_parent_root_text != "none"
            ):
                raise ValueError("direct lineage has parent-root offset bounds")
            min_parent_root_offset = None
            max_parent_root_offset = None
        entries.append(
            {
                "sample_prepared_signature": signature,
                "sample_prepared_family": KNOWN_PREPARED_FAMILIES.get(
                    signature, "unknown"
                ),
                "prepared_signature_varied": str(
                    event.get("prepared_signature_varied", "")
                ).lower()
                == "true",
                "calls": calls,
                "first_frame": _integer(event, "first_frame"),
                "last_frame": _integer(event, "last_frame"),
                "first_draw": _integer(event, "first_draw"),
                "last_draw": _integer(event, "last_draw"),
                "sample_packet_physical_address": packet,
                "sample_command_buffer_physical_address": current,
                "sample_command_buffer_length_dwords": sample_length,
                "min_command_buffer_length_dwords": min_length,
                "max_command_buffer_length_dwords": max_length,
                "min_packet_offset_bytes": min_packet_offset,
                "max_packet_offset_bytes": max_packet_offset,
                "sample_parent_packet_physical_address": parent,
                "sample_root_physical_address": root,
                "min_parent_root_offset_bytes": min_parent_root_offset,
                "max_parent_root_offset_bytes": max_parent_root_offset,
                "constructor_store_address": constructor_store_address,
                "constructor_function_address": constructor_function_address,
                "constructor_return_address": constructor_return_address,
                "constructor_callsite": (
                    constructor_call.get("callsite")
                    if constructor_call is not None
                    else None
                ),
                "constructor_caller_function": (
                    constructor_call.get("caller_function")
                    if constructor_call is not None
                    else None
                ),
                "constructor_caller_function_address": (
                    constructor_call.get("caller_function_address")
                    if constructor_call is not None
                    else None
                ),
                "constructor_callsite_proved": constructor_call is not None,
                "sample_constructor_arguments": constructor_arguments,
                "constructor_argument_varying_mask": (
                    constructor_argument_varying_mask
                ),
                "depth": depth,
            }
        )
    entries.sort(
        key=lambda item: (
            -item["calls"],
            item["depth"],
            item["min_command_buffer_length_dwords"],
            -1
            if item["min_parent_root_offset_bytes"] is None
            else item["min_parent_root_offset_bytes"],
            item["constructor_store_address"] or "",
            item["constructor_return_address"] or "",
        )
    )

    draws = _integer(summary, "draws")
    primary_draws = _integer(summary, "primary_draws")
    indirect_draws = _integer(summary, "indirect_draws")
    invalid = _integer(summary, "invalid_lineages")
    prepared_draws = _integer(summary, "prepared_draws")
    overflow = _integer(summary, "overflow")
    capacity = _integer(summary, "capacity")
    title_packets = _integer(summary, "title_indirect_packets_recorded")
    title_address_failures = _integer(
        summary, "title_indirect_packet_address_failures"
    )
    title_table_overflow = _integer(
        summary, "title_indirect_packet_table_overflow"
    )
    title_evictions = _integer(summary, "title_indirect_packet_evictions")
    indirect_enters = _integer(summary, "indirect_buffer_enters")
    indirect_exits = _integer(summary, "indirect_buffer_exits")
    constructor_matches = _integer(
        summary, "indirect_buffer_constructor_matches"
    )
    constructor_unmatched = _integer(
        summary, "indirect_buffer_constructor_unmatched"
    )
    indirect_stack_faults = _integer(summary, "indirect_buffer_stack_faults")
    draw_stack_faults = _integer(summary, "indirect_draw_stack_faults")
    constructor_entries = _integer(summary, "indirect_constructor_entries")
    constructor_exits = _integer(summary, "indirect_constructor_exits")
    constructor_open = _integer(
        summary, "indirect_constructor_invocations_open_at_shutdown"
    )
    constructor_stack_faults = _integer(
        summary, "indirect_constructor_stack_faults"
    )
    packets_without_constructor_origin = _integer(
        summary, "indirect_packets_without_constructor_origin"
    )
    open_at_shutdown = _integer(
        summary, "indirect_buffers_open_at_shutdown"
    )
    retained_title_generations = (
        title_packets - constructor_matches - title_evictions
    )
    if retained_title_generations < 0:
        raise ValueError("title indirect-buffer generation accounting underflow")
    complete = (
        draws == primary_draws + indirect_draws
        and prepared_draws == sum(item["calls"] for item in entries)
        and len(entries) == _integer(summary, "entries")
        and len(entries) <= capacity
        and not invalid
        and not overflow
        and title_packets > 0
        and constructor_matches > 0
        and indirect_enters == indirect_exits + open_at_shutdown
        and indirect_enters == constructor_matches + constructor_unmatched
        and not title_address_failures
        and not title_table_overflow
        and not indirect_stack_faults
        and not draw_stack_faults
        and constructor_entries == constructor_exits + constructor_open
        and not constructor_stack_faults
        and (
            not static_constructor_calls
            or (
                constructor_entries > 0
                and any(
                    item["constructor_return_address"] is not None
                    for item in entries
                )
            )
        )
    )

    shapes = []
    for entry in entries:
        shapes.append(
            {
                "calls": entry["calls"],
                "sample_command_buffer_length_dwords": entry[
                    "sample_command_buffer_length_dwords"
                ],
                "min_command_buffer_length_dwords": entry[
                    "min_command_buffer_length_dwords"
                ],
                "max_command_buffer_length_dwords": entry[
                    "max_command_buffer_length_dwords"
                ],
                "min_packet_offset_bytes": entry["min_packet_offset_bytes"],
                "max_packet_offset_bytes": entry["max_packet_offset_bytes"],
                "min_parent_root_offset_bytes": entry[
                    "min_parent_root_offset_bytes"
                ],
                "max_parent_root_offset_bytes": entry[
                    "max_parent_root_offset_bytes"
                ],
                "constructor_store_address": entry[
                    "constructor_store_address"
                ],
                "constructor_function_address": entry[
                    "constructor_function_address"
                ],
                "constructor_return_address": entry[
                    "constructor_return_address"
                ],
                "constructor_callsite": entry["constructor_callsite"],
                "constructor_caller_function": entry[
                    "constructor_caller_function"
                ],
                "constructor_callsite_proved": entry[
                    "constructor_callsite_proved"
                ],
                "sample_constructor_arguments": entry[
                    "sample_constructor_arguments"
                ],
                "constructor_argument_varying_mask": entry[
                    "constructor_argument_varying_mask"
                ],
                "depth": entry["depth"],
                "sample_prepared_signature": entry[
                    "sample_prepared_signature"
                ],
                "sample_prepared_family": entry["sample_prepared_family"],
                "prepared_signature_varied": entry[
                    "prepared_signature_varied"
                ],
            }
        )
    shapes.sort(
        key=lambda item: (
            -item["calls"],
            item["depth"],
            item["min_command_buffer_length_dwords"],
            -1
            if item["min_parent_root_offset_bytes"] is None
            else item["min_parent_root_offset_bytes"],
            item["constructor_store_address"] or "",
            item["constructor_return_address"] or "",
        )
    )

    return {
        "schema": SCHEMA,
        "session": session,
        "scene": str(configs[0].get("scene", "unmarked")),
        "status": "complete" if complete else "incomplete_fail_closed",
        "entries": entries,
        "shapes": shapes,
        "static_indirect_buffer_constructors": constructors,
        "static_indirect_constructor_calls": static_constructor_calls,
        "totals": {
            "draws": draws,
            "primary_draws": primary_draws,
            "indirect_draws": indirect_draws,
            "invalid_lineages": invalid,
            "prepared_draws": prepared_draws,
            "entries": len(entries),
            "shapes": len(shapes),
            "overflow": overflow,
            "capacity": capacity,
            "static_constructors": len(constructors),
            "title_indirect_packets_recorded": title_packets,
            "title_indirect_packet_address_failures": title_address_failures,
            "title_indirect_packet_table_overflow": title_table_overflow,
            "title_indirect_packet_evictions": title_evictions,
            "title_indirect_packets_retained_at_shutdown": (
                retained_title_generations
            ),
            "indirect_buffer_enters": indirect_enters,
            "indirect_buffer_exits": indirect_exits,
            "indirect_buffer_constructor_matches": constructor_matches,
            "indirect_buffer_constructor_unmatched": constructor_unmatched,
            "indirect_buffer_stack_faults": indirect_stack_faults,
            "indirect_draw_stack_faults": draw_stack_faults,
            "indirect_constructor_entries": constructor_entries,
            "indirect_constructor_exits": constructor_exits,
            "indirect_constructor_invocations_open_at_shutdown": (
                constructor_open
            ),
            "indirect_constructor_stack_faults": constructor_stack_faults,
            "indirect_packets_without_constructor_origin": (
                packets_without_constructor_origin
            ),
            "indirect_buffers_open_at_shutdown": open_at_shutdown,
            "constructor_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["constructor_return_address"] is not None
            ),
            "statically_resolved_constructor_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["constructor_callsite_proved"]
            ),
            "unresolved_constructor_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["constructor_return_address"] is not None
                and not item["constructor_callsite_proved"]
            ),
        },
        "qualification": "exact_title_store_to_backend_nested_command_buffer_lineage",
        "semantic_identity": "unknown",
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
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        static = json.loads(args.static.read_text(encoding="utf-8"))
        document = build(read_events(args.logs), static, args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"native renderer command lineage summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
