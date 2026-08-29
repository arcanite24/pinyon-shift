"""Summarize exact backend draw-to-command-buffer lineage evidence."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-command-lineage.v1"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
PREFIX = "native_renderer.discovery.command_buffer_lineage_"
SEMANTIC_RECEIVER_PREFIX = "native_renderer.discovery.semantic_receiver_"
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
            event_name = str(event.get("event", ""))
            if event_name.startswith(PREFIX) or event_name.startswith(
                SEMANTIC_RECEIVER_PREFIX
            ):
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
        raise ValueError(f"invalid argument vector: {key}")
    for value in values:
        if len(value) != 8:
            raise ValueError(f"invalid argument vector: {key}")
        try:
            int(value, 16)
        except ValueError as error:
            raise ValueError(
                f"invalid argument vector: {key}"
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
    static_owner_calls = static.get("indirect_owner_calls", [])
    owner_calls_by_return = {
        (
            str(item.get("owner_function_address", "")).upper(),
            str(item.get("return_address", "")).upper(),
        ): item
        for item in static_owner_calls
    }
    static_producer_calls = static.get("indirect_producer_calls", [])
    producer_calls_by_return = {
        (
            str(item.get("producer_function_address", "")).upper(),
            str(item.get("return_address", "")).upper(),
        ): item
        for item in static_producer_calls
    }
    static_context_roots = static.get("indirect_context_roots", [])
    static_semantic_receiver = static.get(
        "procedural_model_receiver_lifecycle", {}
    )
    if static_semantic_receiver and not static_semantic_receiver.get(
        "rtti_vtable_identity_proved"
    ):
        raise ValueError("procedural-model receiver RTTI identity is unproved")
    if static_semantic_receiver and not all(
        static_semantic_receiver.get(key)
        for key in (
            "object_extent_proved",
            "visibility_preparation_boundary_proved",
            "render_state_boundary_proved",
            "transform_matrix_ranges_proved",
        )
    ):
        raise ValueError("procedural-model preparation layout is unproved")
    context_roots_by_producer_return = {
        (
            str(item.get("producer_function_address", "")).upper(),
            str(item.get("producer_return_address", "")).upper(),
        ): item
        for item in static_context_roots
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
    semantic_configs = [
        event
        for event in selected
        if event.get("event") == f"{SEMANTIC_RECEIVER_PREFIX}config"
        and event.get("status") == "armed"
    ]
    if static_semantic_receiver and len(semantic_configs) != 1:
        raise ValueError("lineage session needs one semantic receiver config")
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
        owner_function_address = _optional_hex(
            event, "owner_function_address", 8
        )
        owner_return_address = _optional_hex(
            event, "owner_return_address", 8
        )
        if (owner_function_address is None) != (owner_return_address is None):
            raise ValueError("lineage entry has a partial owner origin")
        owner_call = None
        owner_arguments = None
        owner_argument_varying_mask = None
        if owner_function_address is not None:
            if constructor_call is None:
                raise ValueError(
                    "lineage entry has an owner without a proved constructor caller"
                )
            if (
                str(constructor_call.get("caller_function_address", "")).upper()
                != owner_function_address
            ):
                raise ValueError(
                    "lineage owner does not contain the constructor callsite"
                )
            owner_call = owner_calls_by_return.get(
                (owner_function_address, owner_return_address)
            )
            owner_arguments = _hex_arguments(event, "sample_owner_arguments")
            owner_argument_varying_mask = int(
                _hex(event, "owner_argument_varying_mask", 2), 16
            )
        producer_function_address = _optional_hex(
            event, "producer_function_address", 8
        )
        producer_return_address = _optional_hex(
            event, "producer_return_address", 8
        )
        if (producer_function_address is None) != (
            producer_return_address is None
        ):
            raise ValueError("lineage entry has a partial producer origin")
        producer_call = None
        producer_arguments = None
        producer_argument_varying_mask = None
        if producer_function_address is not None:
            if owner_call is None:
                raise ValueError(
                    "lineage entry has a producer without a proved owner caller"
                )
            if (
                str(owner_call.get("caller_function_address", "")).upper()
                != producer_function_address
            ):
                raise ValueError(
                    "lineage producer does not contain the owner callsite"
                )
            producer_call = producer_calls_by_return.get(
                (producer_function_address, producer_return_address)
            )
            producer_arguments = _hex_arguments(
                event, "sample_producer_arguments"
            )
            producer_argument_varying_mask = int(
                _hex(event, "producer_argument_varying_mask", 2), 16
            )
        context_function_address = None
        context_return_address = None
        context_arguments = None
        context_argument_varying_mask = None
        context_root_address = None
        context_root_address_varied = None
        context_root = None
        semantic_receiver_class = None
        semantic_receiver_address = None
        semantic_receiver_generation = None
        semantic_visibility_epoch = None
        semantic_render_state_epoch = None
        semantic_render_state_visibility_epoch = None
        semantic_preparation_epoch_varied = None
        if static_context_roots:
            context_function_address = _optional_hex(
                event, "context_function_address", 8
            )
            context_return_address = _optional_hex(
                event, "context_return_address", 8
            )
            context_root_address = _optional_hex(
                event, "sample_context_root_address", 8
            )
            if (
                (context_function_address is None)
                != (context_return_address is None)
                or (context_function_address is None)
                != (context_root_address is None)
            ):
                raise ValueError("lineage entry has a partial context origin")
            if context_function_address is not None:
                if producer_call is None or producer_arguments is None:
                    raise ValueError(
                        "lineage entry has a context without a proved producer caller"
                    )
                context_root = context_roots_by_producer_return.get(
                    (producer_function_address, producer_return_address)
                )
                if context_root is None:
                    raise ValueError(
                        "lineage context has no proved producer-root edge"
                    )
                if (
                    str(context_root.get("context_function_address", "")).upper()
                    != context_function_address
                ):
                    raise ValueError(
                        "lineage context does not contain the producer callsite"
                    )
                context_arguments = _hex_arguments(
                    event, "sample_context_arguments"
                )
                context_argument_varying_mask = int(
                    _hex(event, "context_argument_varying_mask", 2), 16
                )
                context_root_address_varied = (
                    str(event.get("context_root_address_varied", "")).lower()
                    == "true"
                )
                register = str(context_root.get("root_entry_register", ""))
                if register not in {f"r{index}" for index in range(3, 11)}:
                    raise ValueError("static context root has an invalid register")
                argument_index = int(register[1:]) - 3
                expected_root = (
                    int(context_arguments[argument_index], 16)
                    + int(context_root.get("root_offset", 0))
                ) & 0xFFFFFFFF
                if (
                    int(context_root_address, 16) != expected_root
                    or int(producer_arguments[0], 16) != expected_root
                ):
                    raise ValueError(
                        "runtime context root does not match its static derivation"
                    )
                if static_semantic_receiver and (
                    context_function_address
                    == static_semantic_receiver["dispatch_function_address"]
                ):
                    semantic_receiver_class = str(
                        event.get("semantic_receiver_class", "unknown")
                    )
                    semantic_receiver_address = _optional_hex(
                        event, "semantic_receiver_address", 8
                    )
                    generation_text = str(
                        event.get("semantic_receiver_generation", "unknown")
                    )
                    if generation_text != "unknown":
                        try:
                            semantic_receiver_generation = int(generation_text)
                        except ValueError as error:
                            raise ValueError(
                                "invalid semantic receiver generation"
                            ) from error
                    epoch_fields = []
                    for key in (
                        "semantic_visibility_epoch",
                        "semantic_render_state_epoch",
                        "semantic_render_state_visibility_epoch",
                    ):
                        text = str(event.get(key, "unknown"))
                        try:
                            epoch_fields.append(
                                None if text == "unknown" else int(text)
                            )
                        except ValueError as error:
                            raise ValueError(
                                "invalid procedural-model preparation epoch"
                            ) from error
                    (
                        semantic_visibility_epoch,
                        semantic_render_state_epoch,
                        semantic_render_state_visibility_epoch,
                    ) = epoch_fields
                    semantic_preparation_epoch_varied = (
                        str(
                            event.get(
                                "semantic_preparation_epoch_varied", "false"
                            )
                        ).lower()
                        == "true"
                    )
                    if (
                        semantic_receiver_class
                        != static_semantic_receiver["class_name"]
                        or semantic_receiver_address is None
                        or not semantic_receiver_generation
                        or semantic_receiver_address != context_arguments[0]
                        or (
                            semantic_render_state_visibility_epoch
                            and not semantic_render_state_epoch
                        )
                        or (
                            semantic_render_state_visibility_epoch
                            and (
                                not semantic_visibility_epoch
                                or semantic_render_state_visibility_epoch
                                > semantic_visibility_epoch
                            )
                        )
                    ):
                        raise ValueError(
                            "procedural-model receiver has no exact stage-history join"
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
                "owner_function_address": owner_function_address,
                "owner_return_address": owner_return_address,
                "owner_callsite": (
                    owner_call.get("callsite") if owner_call is not None else None
                ),
                "owner_caller_function": (
                    owner_call.get("caller_function")
                    if owner_call is not None
                    else None
                ),
                "owner_caller_function_address": (
                    owner_call.get("caller_function_address")
                    if owner_call is not None
                    else None
                ),
                "owner_callsite_proved": owner_call is not None,
                "sample_owner_arguments": owner_arguments,
                "owner_argument_varying_mask": owner_argument_varying_mask,
                "producer_function_address": producer_function_address,
                "producer_return_address": producer_return_address,
                "producer_callsite": (
                    producer_call.get("callsite")
                    if producer_call is not None
                    else None
                ),
                "producer_caller_function": (
                    producer_call.get("caller_function")
                    if producer_call is not None
                    else None
                ),
                "producer_caller_function_address": (
                    producer_call.get("caller_function_address")
                    if producer_call is not None
                    else None
                ),
                "producer_callsite_proved": producer_call is not None,
                "sample_producer_arguments": producer_arguments,
                "producer_argument_varying_mask": (
                    producer_argument_varying_mask
                ),
                "context_function_address": context_function_address,
                "context_return_address": context_return_address,
                "context_root_derivation": (
                    context_root.get("derivation")
                    if context_root is not None
                    else None
                ),
                "context_root_proved": context_root is not None,
                "sample_context_arguments": context_arguments,
                "context_argument_varying_mask": (
                    context_argument_varying_mask
                ),
                "sample_context_root_address": context_root_address,
                "context_root_address_varied": context_root_address_varied,
                "semantic_receiver_class": semantic_receiver_class,
                "semantic_receiver_address": semantic_receiver_address,
                "semantic_receiver_generation": semantic_receiver_generation,
                "semantic_visibility_epoch": semantic_visibility_epoch,
                "semantic_render_state_epoch": semantic_render_state_epoch,
                "semantic_render_state_visibility_epoch": (
                    semantic_render_state_visibility_epoch
                ),
                "semantic_preparation_epoch_varied": (
                    semantic_preparation_epoch_varied
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
            item["owner_return_address"] or "",
            item["producer_return_address"] or "",
            item["context_return_address"] or "",
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
    owner_entries = _integer(summary, "indirect_owner_entries")
    owner_exits = _integer(summary, "indirect_owner_exits")
    owner_open = _integer(
        summary, "indirect_owner_invocations_open_at_shutdown"
    )
    owner_stack_faults = _integer(summary, "indirect_owner_stack_faults")
    constructors_without_owner_origin = _integer(
        summary, "indirect_constructors_without_owner_origin"
    )
    constructor_owner_mismatches = _integer(
        summary, "indirect_constructor_owner_mismatches"
    )
    producer_entries = _integer(summary, "indirect_producer_entries")
    producer_exits = _integer(summary, "indirect_producer_exits")
    producer_open = _integer(
        summary, "indirect_producer_invocations_open_at_shutdown"
    )
    producer_stack_faults = _integer(
        summary, "indirect_producer_stack_faults"
    )
    owners_without_producer_origin = _integer(
        summary, "indirect_owners_without_producer_origin"
    )
    owner_producer_mismatches = _integer(
        summary, "indirect_owner_producer_mismatches"
    )
    context_entries = _integer(summary, "indirect_context_entries")
    context_exits = _integer(summary, "indirect_context_exits")
    context_open = _integer(
        summary, "indirect_context_invocations_open_at_shutdown"
    )
    context_stack_faults = _integer(
        summary, "indirect_context_stack_faults"
    )
    producers_without_context_origin = _integer(
        summary, "indirect_producers_without_context_origin"
    )
    producer_context_mismatches = _integer(
        summary, "indirect_producer_context_mismatches"
    )
    open_at_shutdown = _integer(
        summary, "indirect_buffers_open_at_shutdown"
    )
    semantic_lifecycle_entries = []
    semantic_constructor_entries = 0
    semantic_constructor_exits = 0
    semantic_constructor_open = 0
    semantic_destructor_entries = 0
    semantic_destructor_exits = 0
    semantic_destructor_open = 0
    semantic_stack_faults = 0
    semantic_instances_published = 0
    semantic_instances_destroyed = 0
    semantic_address_reuses = 0
    semantic_table_overflow = 0
    semantic_dispatches = 0
    semantic_live_dispatches = 0
    semantic_unregistered_dispatches = 0
    semantic_destroying_dispatches = 0
    semantic_destroyed_dispatches = 0
    semantic_destructors_without_instance = 0
    semantic_receivers_tracked = 0
    semantic_receivers_live = 0
    semantic_receivers_destroying = 0
    semantic_receivers_destroyed = 0
    semantic_visibility_entries = 0
    semantic_visibility_exits = 0
    semantic_visibility_open = 0
    semantic_render_state_entries = 0
    semantic_render_state_exits = 0
    semantic_render_state_open = 0
    semantic_stage_stack_faults = 0
    semantic_stage_unknown_receivers = 0
    if static_semantic_receiver:
        seen_receiver_addresses = set()
        for event in selected:
            if event.get("event") != f"{SEMANTIC_RECEIVER_PREFIX}lifecycle_entry":
                continue
            receiver_class = str(event.get("class", "unknown"))
            address = _hex(event, "address", 8)
            generation = _integer(event, "generation")
            state = str(event.get("state", ""))
            dispatches = _integer(event, "dispatches")
            visibility_preparations = _integer(
                event, "visibility_preparations"
            )
            render_state_preparations = _integer(
                event, "render_state_preparations"
            )
            visibility_epoch = _integer(event, "visibility_epoch")
            render_state_epoch = _integer(event, "render_state_epoch")
            render_state_visibility_epoch = _integer(
                event, "render_state_visibility_epoch"
            )
            dispatches_with_preparation = _integer(
                event, "dispatches_with_preparation"
            )
            dispatches_without_preparation = _integer(
                event, "dispatches_without_preparation"
            )
            dispatches_without_visibility = _integer(
                event, "dispatches_without_visibility"
            )
            dispatches_without_render_state = _integer(
                event, "dispatches_without_render_state"
            )
            if (
                receiver_class != static_semantic_receiver["class_name"]
                or address in seen_receiver_addresses
                or not generation
                or state not in {"live", "destroying", "destroyed"}
                or dispatches < 0
                or min(
                    visibility_preparations,
                    render_state_preparations,
                    visibility_epoch,
                    render_state_epoch,
                    render_state_visibility_epoch,
                    dispatches_with_preparation,
                    dispatches_without_preparation,
                    dispatches_without_visibility,
                    dispatches_without_render_state,
                )
                < 0
                or visibility_preparations != visibility_epoch
                or render_state_preparations != render_state_epoch
                or render_state_visibility_epoch > visibility_epoch
                or dispatches
                != dispatches_with_preparation
                + dispatches_without_preparation
                or str(event.get("identity_join"))
                != "exact_constructor_receiver_address"
                or str(event.get("guest_payload_read")).lower() != "false"
                or str(event.get("xenos_authority")).lower() != "true"
                or str(event.get("suppression_allowed")).lower() != "false"
            ):
                raise ValueError("invalid semantic receiver lifecycle entry")
            seen_receiver_addresses.add(address)
            semantic_lifecycle_entries.append(
                {
                    "class": receiver_class,
                    "address": address,
                    "generation": generation,
                    "state": state,
                    "dispatches": dispatches,
                    "visibility_preparations": visibility_preparations,
                    "render_state_preparations": render_state_preparations,
                    "visibility_epoch": visibility_epoch,
                    "render_state_epoch": render_state_epoch,
                    "render_state_visibility_epoch": (
                        render_state_visibility_epoch
                    ),
                    "dispatches_with_preparation": (
                        dispatches_with_preparation
                    ),
                    "dispatches_without_preparation": (
                        dispatches_without_preparation
                    ),
                    "dispatches_without_visibility": (
                        dispatches_without_visibility
                    ),
                    "dispatches_without_render_state": (
                        dispatches_without_render_state
                    ),
                }
            )
        semantic_constructor_entries = _integer(
            summary, "semantic_receiver_constructor_entries"
        )
        semantic_constructor_exits = _integer(
            summary, "semantic_receiver_constructor_exits"
        )
        semantic_constructor_open = _integer(
            summary, "semantic_receiver_constructor_open_at_shutdown"
        )
        semantic_destructor_entries = _integer(
            summary, "semantic_receiver_destructor_entries"
        )
        semantic_destructor_exits = _integer(
            summary, "semantic_receiver_destructor_exits"
        )
        semantic_destructor_open = _integer(
            summary, "semantic_receiver_destructor_open_at_shutdown"
        )
        semantic_stack_faults = _integer(
            summary, "semantic_receiver_stack_faults"
        )
        semantic_instances_published = _integer(
            summary, "semantic_receiver_instances_published"
        )
        semantic_instances_destroyed = _integer(
            summary, "semantic_receiver_instances_destroyed"
        )
        semantic_address_reuses = _integer(
            summary, "semantic_receiver_address_reuses"
        )
        semantic_table_overflow = _integer(
            summary, "semantic_receiver_table_overflow"
        )
        semantic_dispatches = _integer(
            summary, "semantic_receiver_dispatches"
        )
        semantic_live_dispatches = _integer(
            summary, "semantic_receiver_live_dispatches"
        )
        semantic_unregistered_dispatches = _integer(
            summary, "semantic_receiver_unregistered_dispatches"
        )
        semantic_destroying_dispatches = _integer(
            summary, "semantic_receiver_destroying_dispatches"
        )
        semantic_destroyed_dispatches = _integer(
            summary, "semantic_receiver_destroyed_dispatches"
        )
        semantic_destructors_without_instance = _integer(
            summary, "semantic_receiver_destructors_without_instance"
        )
        semantic_receivers_tracked = _integer(
            summary, "semantic_receivers_tracked"
        )
        semantic_receivers_live = _integer(
            summary, "semantic_receivers_live_at_shutdown"
        )
        semantic_receivers_destroying = _integer(
            summary, "semantic_receivers_destroying_at_shutdown"
        )
        semantic_receivers_destroyed = _integer(
            summary, "semantic_receivers_destroyed"
        )
        semantic_visibility_entries = _integer(
            summary, "semantic_visibility_entries"
        )
        semantic_visibility_exits = _integer(
            summary, "semantic_visibility_exits"
        )
        semantic_visibility_open = _integer(
            summary, "semantic_visibility_open_at_shutdown"
        )
        semantic_render_state_entries = _integer(
            summary, "semantic_render_state_entries"
        )
        semantic_render_state_exits = _integer(
            summary, "semantic_render_state_exits"
        )
        semantic_render_state_open = _integer(
            summary, "semantic_render_state_open_at_shutdown"
        )
        semantic_stage_stack_faults = _integer(
            summary, "semantic_stage_stack_faults"
        )
        semantic_stage_unknown_receivers = _integer(
            summary, "semantic_stage_unknown_receivers"
        )
        semantic_lifecycle_entries.sort(
            key=lambda item: (item["address"], item["generation"])
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
        and owner_entries == owner_exits + owner_open
        and not owner_stack_faults
        and not constructor_owner_mismatches
        and producer_entries == producer_exits + producer_open
        and not producer_stack_faults
        and not owner_producer_mismatches
        and context_entries == context_exits + context_open
        and not context_stack_faults
        and not producer_context_mismatches
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
        and (
            not static_owner_calls
            or (
                owner_entries > 0
                and any(
                    item["owner_return_address"] is not None
                    for item in entries
                )
            )
        )
        and (
            not static_producer_calls
            or (
                producer_entries > 0
                and any(
                    item["producer_return_address"] is not None
                    for item in entries
                )
            )
        )
        and (
            not static_context_roots
            or (
                context_entries > 0
                and any(
                    item["context_return_address"] is not None
                    for item in entries
                )
            )
        )
        and (
            not static_semantic_receiver
            or (
                semantic_constructor_entries
                == semantic_constructor_exits + semantic_constructor_open
                and semantic_destructor_entries
                == semantic_destructor_exits + semantic_destructor_open
                and semantic_constructor_exits == semantic_instances_published
                and semantic_destructor_exits == semantic_instances_destroyed
                and semantic_instances_published
                == semantic_instances_destroyed
                + semantic_receivers_live
                + semantic_receivers_destroying
                and not semantic_stack_faults
                and not semantic_table_overflow
                and not semantic_unregistered_dispatches
                and not semantic_destroying_dispatches
                and not semantic_destroyed_dispatches
                and not semantic_destructors_without_instance
                and semantic_dispatches == semantic_live_dispatches
                and semantic_live_dispatches > 0
                and semantic_visibility_entries
                == semantic_visibility_exits + semantic_visibility_open
                and semantic_render_state_entries
                == semantic_render_state_exits + semantic_render_state_open
                and semantic_visibility_exits > 0
                and semantic_render_state_exits > 0
                and not semantic_stage_stack_faults
                and not semantic_stage_unknown_receivers
                and semantic_receivers_tracked == len(semantic_lifecycle_entries)
                and semantic_receivers_live
                == sum(
                    item["state"] == "live"
                    for item in semantic_lifecycle_entries
                )
                and semantic_receivers_destroying
                == sum(
                    item["state"] == "destroying"
                    for item in semantic_lifecycle_entries
                )
                and semantic_receivers_destroyed
                == sum(
                    item["state"] == "destroyed"
                    for item in semantic_lifecycle_entries
                )
                and semantic_live_dispatches
                == sum(
                    item["dispatches"] for item in semantic_lifecycle_entries
                )
                and semantic_visibility_exits
                == sum(
                    item["visibility_preparations"]
                    for item in semantic_lifecycle_entries
                )
                and semantic_render_state_exits
                == sum(
                    item["render_state_preparations"]
                    for item in semantic_lifecycle_entries
                )
                and any(
                    item["semantic_receiver_address"] is not None
                    and item["semantic_visibility_epoch"]
                    and item["semantic_render_state_epoch"]
                    and item["semantic_render_state_visibility_epoch"]
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
                "owner_function_address": entry["owner_function_address"],
                "owner_return_address": entry["owner_return_address"],
                "owner_callsite": entry["owner_callsite"],
                "owner_caller_function": entry["owner_caller_function"],
                "owner_callsite_proved": entry["owner_callsite_proved"],
                "sample_owner_arguments": entry["sample_owner_arguments"],
                "owner_argument_varying_mask": entry[
                    "owner_argument_varying_mask"
                ],
                "producer_function_address": entry[
                    "producer_function_address"
                ],
                "producer_return_address": entry["producer_return_address"],
                "producer_callsite": entry["producer_callsite"],
                "producer_caller_function": entry[
                    "producer_caller_function"
                ],
                "producer_callsite_proved": entry[
                    "producer_callsite_proved"
                ],
                "sample_producer_arguments": entry[
                    "sample_producer_arguments"
                ],
                "producer_argument_varying_mask": entry[
                    "producer_argument_varying_mask"
                ],
                "context_function_address": entry[
                    "context_function_address"
                ],
                "context_return_address": entry["context_return_address"],
                "context_root_derivation": entry[
                    "context_root_derivation"
                ],
                "context_root_proved": entry["context_root_proved"],
                "sample_context_arguments": entry[
                    "sample_context_arguments"
                ],
                "context_argument_varying_mask": entry[
                    "context_argument_varying_mask"
                ],
                "sample_context_root_address": entry[
                    "sample_context_root_address"
                ],
                "context_root_address_varied": entry[
                    "context_root_address_varied"
                ],
                "semantic_receiver_class": entry[
                    "semantic_receiver_class"
                ],
                "semantic_receiver_address": entry[
                    "semantic_receiver_address"
                ],
                "semantic_receiver_generation": entry[
                    "semantic_receiver_generation"
                ],
                "semantic_visibility_epoch": entry[
                    "semantic_visibility_epoch"
                ],
                "semantic_render_state_epoch": entry[
                    "semantic_render_state_epoch"
                ],
                "semantic_render_state_visibility_epoch": entry[
                    "semantic_render_state_visibility_epoch"
                ],
                "semantic_preparation_epoch_varied": entry[
                    "semantic_preparation_epoch_varied"
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
            item["owner_return_address"] or "",
            item["producer_return_address"] or "",
            item["context_return_address"] or "",
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
        "static_indirect_owner_calls": static_owner_calls,
        "static_indirect_producer_calls": static_producer_calls,
        "static_indirect_context_roots": static_context_roots,
        "static_procedural_model_receiver_lifecycle": (
            static_semantic_receiver
        ),
        "semantic_receiver_lifecycles": semantic_lifecycle_entries,
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
            "indirect_owner_entries": owner_entries,
            "indirect_owner_exits": owner_exits,
            "indirect_owner_invocations_open_at_shutdown": owner_open,
            "indirect_owner_stack_faults": owner_stack_faults,
            "indirect_constructors_without_owner_origin": (
                constructors_without_owner_origin
            ),
            "indirect_constructor_owner_mismatches": (
                constructor_owner_mismatches
            ),
            "indirect_producer_entries": producer_entries,
            "indirect_producer_exits": producer_exits,
            "indirect_producer_invocations_open_at_shutdown": producer_open,
            "indirect_producer_stack_faults": producer_stack_faults,
            "indirect_owners_without_producer_origin": (
                owners_without_producer_origin
            ),
            "indirect_owner_producer_mismatches": (
                owner_producer_mismatches
            ),
            "indirect_context_entries": context_entries,
            "indirect_context_exits": context_exits,
            "indirect_context_invocations_open_at_shutdown": context_open,
            "indirect_context_stack_faults": context_stack_faults,
            "indirect_producers_without_context_origin": (
                producers_without_context_origin
            ),
            "indirect_producer_context_mismatches": (
                producer_context_mismatches
            ),
            "semantic_receiver_constructor_entries": (
                semantic_constructor_entries
            ),
            "semantic_receiver_constructor_exits": semantic_constructor_exits,
            "semantic_receiver_constructor_open_at_shutdown": (
                semantic_constructor_open
            ),
            "semantic_receiver_destructor_entries": semantic_destructor_entries,
            "semantic_receiver_destructor_exits": semantic_destructor_exits,
            "semantic_receiver_destructor_open_at_shutdown": (
                semantic_destructor_open
            ),
            "semantic_receiver_stack_faults": semantic_stack_faults,
            "semantic_receiver_instances_published": (
                semantic_instances_published
            ),
            "semantic_receiver_instances_destroyed": (
                semantic_instances_destroyed
            ),
            "semantic_receiver_address_reuses": semantic_address_reuses,
            "semantic_receiver_table_overflow": semantic_table_overflow,
            "semantic_receiver_dispatches": semantic_dispatches,
            "semantic_receiver_live_dispatches": semantic_live_dispatches,
            "semantic_receiver_unregistered_dispatches": (
                semantic_unregistered_dispatches
            ),
            "semantic_receiver_destroying_dispatches": (
                semantic_destroying_dispatches
            ),
            "semantic_receiver_destroyed_dispatches": (
                semantic_destroyed_dispatches
            ),
            "semantic_receiver_destructors_without_instance": (
                semantic_destructors_without_instance
            ),
            "semantic_receivers_tracked": semantic_receivers_tracked,
            "semantic_receivers_live_at_shutdown": semantic_receivers_live,
            "semantic_receivers_destroying_at_shutdown": (
                semantic_receivers_destroying
            ),
            "semantic_receivers_destroyed": semantic_receivers_destroyed,
            "semantic_visibility_entries": semantic_visibility_entries,
            "semantic_visibility_exits": semantic_visibility_exits,
            "semantic_visibility_open_at_shutdown": (
                semantic_visibility_open
            ),
            "semantic_render_state_entries": semantic_render_state_entries,
            "semantic_render_state_exits": semantic_render_state_exits,
            "semantic_render_state_open_at_shutdown": (
                semantic_render_state_open
            ),
            "semantic_stage_stack_faults": semantic_stage_stack_faults,
            "semantic_stage_unknown_receivers": (
                semantic_stage_unknown_receivers
            ),
            "semantic_dispatches_after_both_observed_stages": sum(
                item["dispatches_with_preparation"]
                for item in semantic_lifecycle_entries
            ),
            "semantic_dispatches_before_both_observed_stages": sum(
                item["dispatches_without_preparation"]
                for item in semantic_lifecycle_entries
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
            "owner_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["owner_return_address"] is not None
            ),
            "statically_resolved_owner_origin_draws": sum(
                item["calls"] for item in entries if item["owner_callsite_proved"]
            ),
            "unresolved_owner_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["owner_return_address"] is not None
                and not item["owner_callsite_proved"]
            ),
            "producer_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["producer_return_address"] is not None
            ),
            "statically_resolved_producer_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["producer_callsite_proved"]
            ),
            "unresolved_producer_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["producer_return_address"] is not None
                and not item["producer_callsite_proved"]
            ),
            "context_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["context_return_address"] is not None
            ),
            "statically_resolved_context_origin_draws": sum(
                item["calls"] for item in entries if item["context_root_proved"]
            ),
            "unresolved_context_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["context_return_address"] is not None
                and not item["context_root_proved"]
            ),
            "procedural_model_receiver_origin_draws": sum(
                item["calls"]
                for item in entries
                if item["semantic_receiver_address"] is not None
            ),
        },
        "qualification": "exact_title_store_to_backend_nested_command_buffer_lineage",
        "semantic_identity": (
            "procedural_model_receiver_stage_history"
            if static_semantic_receiver
            else "unknown"
        ),
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
