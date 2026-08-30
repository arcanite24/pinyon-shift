#!/usr/bin/env python3
"""Qualify the read-only vehicle-instance semantic seed."""

import argparse
import json
import math
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-vehicle-pose.v1"
CONFIG = "native_renderer.discovery.vehicle_pose_config"
SUMMARY = "native_renderer.discovery.vehicle_pose_summary"
IDENTITY = "native_renderer.discovery.vehicle_pose_identity"
OWNER_METHOD = "native_renderer.discovery.vehicle_owner_method"
OWNER_INDIRECT_TARGET = (
    "native_renderer.discovery.vehicle_owner_indirect_target"
)
DRAW_ARGUMENT_CORRELATION = (
    "native_renderer.discovery.vehicle_draw_argument_correlation"
)
DRAW_OBJECT_CORRELATION = (
    "native_renderer.discovery.vehicle_draw_object_correlation"
)
RENDER_CONTEXT_CALLEE = (
    "native_renderer.discovery.vehicle_render_context_callee"
)
VEHICLE_MATRIX_CORRELATION = (
    "native_renderer.discovery.vehicle_matrix_correlation"
)
TYPED_RENDER_ITEM_PROFILE = (
    "native_renderer.discovery.vehicle_typed_render_item_profile"
)
TYPED_DESCRIPTOR_CORRELATION = (
    "native_renderer.discovery.vehicle_typed_descriptor_correlation"
)
TITLE_PROVENANCE_CONFIG = (
    "native_renderer.discovery.title_provenance_config"
)
OWNER_METHOD_CANDIDATES = {
    "82BCC368": (14, "82BCCD30"),
    "82BD2DE0": (20, "82BD35B0"),
    "82BC8410": (22, "82BC86F0"),
}
OWNER_INDIRECT_CALLSITES = {
    "82BC8468",
    "82BC84A4",
    "82BC84DC",
    "82BC8688",
    "82BC86BC",
    "82BC86E4",
}
DRAW_PROVENANCE_LAYERS = {
    "direct_arguments",
    "semantic_receiver",
    "semantic_descriptor",
    "semantic_runtime",
    "indirect_constructor_arguments",
    "indirect_owner_arguments",
    "indirect_producer_arguments",
    "indirect_context_arguments",
    "indirect_context_root",
    "indirect_semantic_receiver",
}
DRAW_IDENTITY_FIELDS = {"owner", "position", "forward"}
VEHICLE_MATRIX_LAYOUTS = {
    "row_major_translation_row3_forward_row2",
    "column_major_translation_column3_forward_column2",
}
VEHICLE_MATRIX_FORWARD_SIGNS = {"positive", "negative"}


def read_events(paths):
    events = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def integer(mapping, key):
    try:
        value = int(mapping[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if value < 0:
        raise ValueError(f"negative {key}")
    return value


def finite_number(mapping, key):
    try:
        value = float(mapping[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"invalid {key}")
    return value


def hexadecimal(mapping, key):
    value = str(mapping.get(key, "")).upper()
    if len(value) != 8:
        raise ValueError(f"invalid {key}")
    try:
        parsed = int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid {key}") from error
    if not parsed:
        raise ValueError(f"zero {key}")
    return value


def hexadecimal64(mapping, key):
    value = str(mapping.get(key, "")).upper()
    if len(value) != 16:
        raise ValueError(f"invalid {key}")
    try:
        parsed = int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid {key}") from error
    if not parsed:
        raise ValueError(f"zero {key}")
    return value


def hexadecimal_allow_zero(mapping, key):
    value = str(mapping.get(key, "")).upper()
    if len(value) != 8:
        raise ValueError(f"invalid {key}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid {key}") from error
    return value


def hexadecimal_words(mapping, key, expected_count):
    values = str(mapping.get(key, "")).upper().split(",")
    if len(values) != expected_count:
        raise ValueError(f"invalid {key} count")
    for value in values:
        if len(value) != 8:
            raise ValueError(f"invalid {key}")
        try:
            int(value, 16)
        except ValueError as error:
            raise ValueError(f"invalid {key}") from error
    return values


def exact(events, name):
    matches = [event for event in events if event.get("event") == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name}")
    return matches[0]


def build(events, requested_session=None):
    sessions = {
        event.get("session") for event in events if event.get("event") == CONFIG
    }
    sessions.discard(None)
    if requested_session:
        if requested_session not in sessions:
            raise ValueError("requested session has no vehicle-pose config")
        session = requested_session
    elif len(sessions) == 1:
        session = next(iter(sessions))
    else:
        raise ValueError("vehicle-pose input contains multiple sessions")
    selected = [event for event in events if event.get("session") == session]
    config = exact(selected, CONFIG)
    summary = exact(selected, SUMMARY)
    title_provenance_config = exact(selected, TITLE_PROVENANCE_CONFIG)
    expected_config = {
        "status": "armed",
        "hook": "82BC5A3C",
        "identity": "title_generation,source,owner,active_slot",
        "transform": "exact_active_slot_position_and_forward",
        "capacity": "64",
        "summary_limit": "64",
        "classification": "unclassified_vehicle_pose_stream",
        "player_priority_admitted": "false",
        "owner_vtable_method_count": "32",
        "owner_method_candidates": "82BCC368:14,82BD2DE0:20,82BC8410:22",
        "owner_method_exit_hooks": "82BCCD30,82BD35B0,82BC86F0",
        "owner_method_stack_capacity": "8",
        "owner_indirect_callsites": (
            "82BC8468,82BC84A4,82BC84DC,82BC8688,82BC86BC,82BC86E4"
        ),
        "owner_indirect_target_capacity": "64",
        "draw_correlation_capacity": "1024",
        "identity_address_capacity": "512",
        "draw_correlation": (
            "exact_backend_signature_and_provenance_argument_to_vehicle_address"
        ),
        "object_scan_word_count": "128",
        "object_scan_cache_capacity": "16384",
        "object_correlation_capacity": "2048",
        "object_correlation": "sampled_one_hop_pointer_to_vehicle_address",
        "targeted_render_context_arguments": "824365B0:r7,r8",
        "targeted_render_context_static_contract": (
            "r7_vtable_slot_8_and_r8_vector_source"
        ),
        "render_context_callee_contract": (
            "824365B0:r6_le_2,r7_vtable_slot_8,r8_32_byte_vector"
        ),
        "render_context_dispatcher_hook": "82436468:r8,r9,r10,r12",
        "render_context_callee_profile_capacity": "32",
        "vehicle_matrix_caller_contract": "8240E7B0:r6_4x4_matrix,r12",
        "vehicle_matrix_layouts": (
            "row_major_translation_row3_forward_row2,"
            "column_major_translation_column3_forward_column2"
        ),
        "vehicle_matrix_forward_signs": "positive,negative",
        "vehicle_matrix_match_thresholds": (
            "position_delta_squared<=0.25,forward_delta_squared<=0.04"
        ),
        "vehicle_matrix_correlation_capacity": "512",
        "typed_render_item_hook": "8240EC18:r11_descriptor,r31_root",
        "typed_render_item_contract": (
            "eligible_root_child_and_descriptor_through_offset_244"
        ),
        "typed_render_item_profile_capacity": "32",
        "typed_descriptor_word_count": "62",
        "typed_descriptor_correlation_capacity": "512",
        "guest_payload_read": (
            "existing_pose_values,bounded_owner_vtable,typed_context_entry,"
            "typed_4x4_caller_matrix,typed_render_item_descriptor"
        ),
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("vehicle-pose configuration drifted")
    if config.get("title_provenance_requested") not in ("true", "false"):
        raise ValueError("vehicle title provenance configuration drifted")
    title_provenance_requested = (
        config["title_provenance_requested"] == "true"
    )
    title_provenance_armed = title_provenance_config.get("status") == "armed"
    if (
        title_provenance_config.get("guest_state_changed") != "false"
        or title_provenance_config.get("control_flow_changed") != "false"
        or title_provenance_config.get("xenos_authority") != "true"
        or title_provenance_config.get("suppression_allowed") != "false"
        or title_provenance_armed != title_provenance_requested
    ):
        raise ValueError("vehicle title provenance arm state drifted")
    expected_summary = {
        "status": "complete",
        "accounting_complete": "true",
        "identity": "title_generation,source,owner,active_slot",
        "transform": "exact_active_slot_position_and_forward",
        "classification": "vehicle_instance_semantic_seed",
        "player_priority_admitted": "false",
        "owner_vtable_method_count": "32",
        "owner_method_candidates": "82BCC368:14,82BD2DE0:20,82BC8410:22",
        "owner_method_exit_hooks": "82BCCD30,82BD35B0,82BC86F0",
        "capacity": "64",
        "summary_limit": "64",
        "draw_correlation_capacity": "1024",
        "identity_address_capacity": "512",
        "object_scan_word_count": "128",
        "object_scan_cache_capacity": "16384",
        "object_correlation_capacity": "2048",
        "render_context_callee_profile_capacity": "32",
        "vehicle_matrix_correlation_capacity": "512",
        "typed_render_item_profile_capacity": "32",
        "typed_descriptor_word_count": "62",
        "typed_descriptor_correlation_capacity": "512",
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("vehicle-pose summary drifted")
    if summary.get("title_provenance_requested") != config.get(
        "title_provenance_requested"
    ) or summary.get("draw_provenance_coverage_complete") not in (
        "true",
        "false",
    ):
        raise ValueError("vehicle draw provenance coverage drifted")

    totals = {
        key: integer(summary, key)
        for key in (
            "observations",
            "valid_observations",
            "invalid_observations",
            "identities",
            "capacity",
            "summary_limit",
            "overflow",
        )
    }
    totals["owner_method_stack_faults"] = integer(
        summary, "owner_method_stack_faults"
    )
    for key in (
        "owner_indirect_observations",
        "owner_indirect_valid_observations",
        "owner_indirect_invalid_observations",
        "owner_indirect_targets",
        "owner_indirect_target_capacity",
        "owner_indirect_target_overflow",
        "draws_examined",
        "direct_draws_examined",
        "indirect_draws_examined",
        "draw_argument_probes",
        "direct_argument_probes",
        "semantic_argument_probes",
        "indirect_argument_probes",
        "draw_argument_matches",
        "draw_correlations",
        "draw_correlation_capacity",
        "draw_correlation_overflow",
        "identity_addresses",
        "identity_address_capacity",
        "identity_address_overflow",
        "object_scan_requests",
        "object_scans",
        "object_scan_words",
        "object_scan_word_count",
        "object_scan_cache_entries",
        "object_scan_cache_capacity",
        "object_scan_cache_overflow",
        "object_argument_matches",
        "object_correlations",
        "object_correlation_capacity",
        "object_correlation_overflow",
        "targeted_render_context_r7_scan_requests",
        "targeted_render_context_r7_scans",
        "targeted_render_context_r8_scan_requests",
        "targeted_render_context_r8_scans",
        "render_context_callee_observations",
        "render_context_callee_eligible_observations",
        "render_context_callee_ineligible_observations",
        "render_context_callee_valid_observations",
        "render_context_callee_invalid_root",
        "render_context_callee_invalid_vtable",
        "render_context_callee_invalid_vector",
        "render_context_callee_profiles",
        "render_context_callee_profile_capacity",
        "render_context_callee_profile_overflow",
        "render_context_dispatcher_observations",
        "render_context_dispatcher_eligible_observations",
        "render_context_dispatcher_matches",
        "render_context_dispatcher_mismatches",
        "vehicle_matrix_caller_observations",
        "vehicle_matrix_caller_valid_observations",
        "vehicle_matrix_caller_invalid_range",
        "vehicle_matrix_caller_non_finite",
        "vehicle_matrix_identity_comparisons",
        "vehicle_matrix_candidate_observations",
        "vehicle_matrix_routes_without_identity",
        "vehicle_matrix_tight_matches",
        "vehicle_matrix_correlations",
        "vehicle_matrix_correlation_capacity",
        "vehicle_matrix_correlation_overflow",
        "typed_render_item_observations",
        "typed_render_item_valid_observations",
        "typed_render_item_invalid_root",
        "typed_render_item_invalid_child",
        "typed_render_item_invalid_descriptor",
        "typed_render_item_profiles",
        "typed_render_item_profile_capacity",
        "typed_render_item_profile_overflow",
        "typed_descriptor_scan_words",
        "typed_descriptor_word_count",
        "typed_descriptor_matches",
        "typed_descriptor_correlations",
        "typed_descriptor_correlation_capacity",
        "typed_descriptor_correlation_overflow",
    ):
        totals[key] = integer(summary, key)
    for key in (
        "vehicle_matrix_caller_accounting_complete",
        "vehicle_matrix_route_accounting_complete",
        "typed_render_item_accounting_complete",
    ):
        if summary.get(key) not in ("true", "false"):
            raise ValueError(f"invalid {key}")
        totals[key] = summary[key] == "true"
    identities = []
    seen = set()
    for event in selected:
        if event.get("event") != IDENTITY:
            continue
        if (
            event.get("classification") != "vehicle_instance_semantic_seed"
            or event.get("player_priority_admitted") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle identity violates safety boundary")
        key = (
            hexadecimal(event, "generation"),
            hexadecimal(event, "source"),
            hexadecimal(event, "owner"),
            integer(event, "slot"),
        )
        if key in seen:
            raise ValueError("duplicate vehicle identity")
        seen.add(key)
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if first_frame > last_frame:
            raise ValueError("invalid vehicle frame range")
        identities.append(
            {
                "generation": key[0],
                "source": key[1],
                "owner": key[2],
                "owner_vtable": hexadecimal(event, "owner_vtable"),
                "owner_vtable_hash": hexadecimal64(
                    event, "owner_vtable_hash"
                ),
                "owner_vtable_methods": hexadecimal_words(
                    event, "owner_vtable_methods", 32
                ),
                "owner_vtable_mismatches": integer(
                    event, "owner_vtable_mismatches"
                ),
                "slot": key[3],
                "position_address": hexadecimal(event, "position_address"),
                "forward_address": hexadecimal(event, "forward_address"),
                "observations": integer(event, "observations"),
                "first_frame": first_frame,
                "last_frame": last_frame,
                "position_changes": integer(event, "position_changes"),
                "forward_changes": integer(event, "forward_changes"),
                "stabilized_observations": integer(
                    event, "stabilized_observations"
                ),
                "address_mismatches": integer(event, "address_mismatches"),
                "maximum_position_delta_squared": finite_number(
                    event, "maximum_position_delta_squared"
                ),
            }
        )

    owner_classes_by_vtable = {}
    owner_class_drift = False
    for identity in identities:
        vtable = identity["owner_vtable"]
        snapshot = (
            identity["owner_vtable_hash"],
            tuple(identity["owner_vtable_methods"]),
        )
        owner_class = owner_classes_by_vtable.get(vtable)
        if owner_class is None:
            owner_classes_by_vtable[vtable] = {
                "owner_vtable": vtable,
                "owner_vtable_hash": snapshot[0],
                "owner_vtable_methods": list(snapshot[1]),
                "identity_count": 1,
            }
        else:
            owner_class["identity_count"] += 1
            if (
                owner_class["owner_vtable_hash"],
                tuple(owner_class["owner_vtable_methods"]),
            ) != snapshot:
                owner_class_drift = True
    owner_classes = sorted(
        owner_classes_by_vtable.values(), key=lambda item: item["owner_vtable"]
    )

    method_correlations = []
    method_events = [
        event for event in selected if event.get("event") == OWNER_METHOD
    ]
    if len(method_events) != len(OWNER_METHOD_CANDIDATES):
        raise ValueError("vehicle owner method coverage drifted")
    seen_methods = set()
    for event in method_events:
        method = hexadecimal(event, "method_address")
        if method in seen_methods or method not in OWNER_METHOD_CANDIDATES:
            raise ValueError("invalid vehicle owner method candidate")
        seen_methods.add(method)
        expected_slot, expected_exit = OWNER_METHOD_CANDIDATES[method]
        if (
            event.get("status") not in ("complete", "incomplete")
            or hexadecimal(event, "exit_address") != expected_exit
            or integer(event, "vtable_slot") != expected_slot
            or event.get("player_vehicle_identity_proved") != "false"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle owner method violates safety boundary")
        calls = integer(event, "calls")
        matched_owner_calls = integer(event, "matched_owner_calls")
        exits = integer(event, "exits")
        direct_draw_origins = integer(event, "direct_draw_origins")
        backend_draw_matches = integer(event, "backend_draw_matches")
        candidate_proved = backend_draw_matches > 0
        if event.get("vehicle_render_method_candidate_proved") != (
            "true" if candidate_proved else "false"
        ):
            raise ValueError("vehicle owner method qualification drifted")
        method_correlations.append(
            {
                "method_address": method,
                "exit_address": expected_exit,
                "vtable_slot": expected_slot,
                "status": event["status"],
                "calls": calls,
                "matched_owner_calls": matched_owner_calls,
                "exits": exits,
                "direct_draw_origins": direct_draw_origins,
                "backend_draw_matches": backend_draw_matches,
                "vehicle_render_method_candidate_proved": candidate_proved,
            }
        )
    method_correlations.sort(key=lambda item: item["vtable_slot"])

    indirect_targets = []
    seen_indirect_targets = set()
    for event in selected:
        if event.get("event") != OWNER_INDIRECT_TARGET:
            continue
        method = hexadecimal(event, "method_address")
        callsite = hexadecimal(event, "callsite_address")
        target = hexadecimal(event, "target_address")
        object_vtable = hexadecimal(event, "object_vtable")
        key = (method, callsite, target, object_vtable)
        if (
            key in seen_indirect_targets
            or method != "82BC8410"
            or callsite not in OWNER_INDIRECT_CALLSITES
            or event.get("classification")
            != "vehicle_owner_component_dispatch_seed"
            or event.get("vehicle_render_method_identity_proved") != "false"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle owner indirect target violates boundary")
        seen_indirect_targets.add(key)
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if first_frame > last_frame:
            raise ValueError("invalid vehicle indirect target frame range")
        indirect_targets.append(
            {
                "method_address": method,
                "callsite_address": callsite,
                "target_address": target,
                "object_address": hexadecimal(event, "object_address"),
                "object_vtable": object_vtable,
                "observations": integer(event, "observations"),
                "first_frame": first_frame,
                "last_frame": last_frame,
            }
        )
    indirect_targets.sort(
        key=lambda item: (
            item["callsite_address"],
            item["target_address"],
            item["object_vtable"],
        )
    )

    identities_by_key = {
        (item["generation"], item["owner"], item["slot"]): item
        for item in identities
    }
    draw_correlations = []
    seen_draw_correlations = set()
    for event in selected:
        if event.get("event") != DRAW_ARGUMENT_CORRELATION:
            continue
        layer = str(event.get("provenance_layer", ""))
        identity_field = str(event.get("identity_field", ""))
        identity_key = (
            hexadecimal(event, "identity_generation"),
            hexadecimal(event, "identity_owner"),
            integer(event, "identity_slot"),
        )
        identity = identities_by_key.get(identity_key)
        matched_address = hexadecimal(event, "matched_address")
        if identity and identity_field in ("position", "forward"):
            expected_address = identity.get(f"{identity_field}_address")
        elif identity and identity_field == "owner":
            expected_address = identity_key[1]
        else:
            expected_address = None
        key = (
            hexadecimal64(event, "backend_signature"),
            layer,
            hexadecimal_allow_zero(event, "function_address"),
            hexadecimal_allow_zero(event, "return_address"),
            integer(event, "argument_index"),
            identity_field,
            matched_address,
            identity_key,
        )
        if (
            key in seen_draw_correlations
            or layer not in DRAW_PROVENANCE_LAYERS
            or identity_field not in DRAW_IDENTITY_FIELDS
            or identity is None
            or matched_address != expected_address
            or key[4] > 8
            or event.get("classification")
            != "vehicle_draw_argument_correlation_candidate"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle draw correlation violates boundary")
        seen_draw_correlations.add(key)
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if first_frame > last_frame:
            raise ValueError("invalid vehicle draw correlation frame range")
        draw_correlations.append(
            {
                "backend_signature": key[0],
                "provenance_layer": layer,
                "function_address": key[2],
                "return_address": key[3],
                "argument_index": key[4],
                "identity_field": identity_field,
                "matched_address": matched_address,
                "identity_generation": identity_key[0],
                "identity_owner": identity_key[1],
                "identity_slot": identity_key[2],
                "observations": integer(event, "observations"),
                "first_frame": first_frame,
                "last_frame": last_frame,
            }
        )
    draw_correlations.sort(
        key=lambda item: (
            item["backend_signature"],
            item["provenance_layer"],
            item["function_address"],
            item["return_address"],
            item["argument_index"],
            item["identity_owner"],
            item["identity_slot"],
        )
    )

    object_correlations = []
    seen_object_correlations = set()
    for event in selected:
        if event.get("event") != DRAW_OBJECT_CORRELATION:
            continue
        layer = str(event.get("provenance_layer", ""))
        identity_field = str(event.get("identity_field", ""))
        identity_key = (
            hexadecimal(event, "identity_generation"),
            hexadecimal(event, "identity_owner"),
            integer(event, "identity_slot"),
        )
        identity = identities_by_key.get(identity_key)
        matched_address = hexadecimal(event, "matched_address")
        if identity and identity_field in ("position", "forward"):
            expected_address = identity.get(f"{identity_field}_address")
        elif identity and identity_field == "owner":
            expected_address = identity_key[1]
        else:
            expected_address = None
        key = (
            hexadecimal64(event, "backend_signature"),
            layer,
            hexadecimal_allow_zero(event, "function_address"),
            hexadecimal_allow_zero(event, "return_address"),
            integer(event, "argument_index"),
            hexadecimal(event, "container_address"),
            integer(event, "pointer_offset"),
            identity_field,
            matched_address,
            identity_key,
        )
        if (
            key in seen_object_correlations
            or layer not in DRAW_PROVENANCE_LAYERS
            or identity_field not in DRAW_IDENTITY_FIELDS
            or identity is None
            or matched_address != expected_address
            or key[4] > 8
            or key[6] >= totals["object_scan_word_count"] * 4
            or key[6] % 4
            or integer(event, "relationship_depth") != 1
            or event.get("classification")
            != "vehicle_draw_object_correlation_candidate"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle draw object correlation violates boundary")
        seen_object_correlations.add(key)
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if first_frame > last_frame:
            raise ValueError("invalid vehicle object correlation frame range")
        object_correlations.append(
            {
                "backend_signature": key[0],
                "provenance_layer": layer,
                "function_address": key[2],
                "return_address": key[3],
                "argument_index": key[4],
                "container_address": key[5],
                "pointer_offset": key[6],
                "identity_field": identity_field,
                "matched_address": matched_address,
                "identity_generation": identity_key[0],
                "identity_owner": identity_key[1],
                "identity_slot": identity_key[2],
                "observations": integer(event, "observations"),
                "first_frame": first_frame,
                "last_frame": last_frame,
            }
        )
    object_correlations.sort(
        key=lambda item: (
            item["backend_signature"],
            item["provenance_layer"],
            item["function_address"],
            item["argument_index"],
            item["container_address"],
            item["pointer_offset"],
            item["identity_owner"],
        )
    )

    render_context_callees = []
    seen_render_context_callees = set()
    for event in selected:
        if event.get("event") != RENDER_CONTEXT_CALLEE:
            continue
        key = (
            hexadecimal(event, "root_vtable"),
            hexadecimal(event, "slot_8_target"),
            hexadecimal(event, "dispatcher_return_address"),
        )
        if (
            key in seen_render_context_callees
            or event.get("function_address") != "824365B0"
            or event.get("mode_contract") != "r6_le_2"
            or event.get("classification")
            != "typed_vehicle_render_context_callee_seed"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle render-context callee violates boundary")
        seen_render_context_callees.add(key)
        render_context_callees.append(
            {
                "function_address": "824365B0",
                "root_address": hexadecimal(event, "root_address"),
                "root_vtable": key[0],
                "slot_8_target": key[1],
                "dispatcher_return_address": key[2],
                "root_field_4": hexadecimal_allow_zero(
                    event, "root_field_4"
                ),
                "root_field_16": hexadecimal_allow_zero(
                    event, "root_field_16"
                ),
                "vector_address": hexadecimal(event, "vector_address"),
                "vector_hash": hexadecimal64(event, "vector_hash"),
                "observations": integer(event, "observations"),
                "root_address_changes": integer(
                    event, "root_address_changes"
                ),
                "root_field_4_changes": integer(
                    event, "root_field_4_changes"
                ),
                "root_field_16_changes": integer(
                    event, "root_field_16_changes"
                ),
                "vector_address_changes": integer(
                    event, "vector_address_changes"
                ),
                "vector_hash_changes": integer(
                    event, "vector_hash_changes"
                ),
            }
        )
    render_context_callees.sort(
        key=lambda item: (
            item["root_vtable"],
            item["slot_8_target"],
            item["dispatcher_return_address"],
        )
    )

    matrix_correlations = []
    seen_matrix_correlations = set()
    for event in selected:
        if event.get("event") != VEHICLE_MATRIX_CORRELATION:
            continue
        layout = event.get("matrix_layout")
        forward_sign = event.get("forward_sign")
        identity_key = (
            hexadecimal(event, "identity_generation"),
            hexadecimal(event, "identity_owner"),
            integer(event, "identity_slot"),
        )
        key = (
            hexadecimal(event, "caller_return_address"),
            layout,
            forward_sign,
            *identity_key,
        )
        observations = integer(event, "observations")
        tight_matches = integer(event, "tight_matches")
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        candidate_proved = tight_matches > 0
        if (
            key in seen_matrix_correlations
            or event.get("function_address") != "8240E7B0"
            or layout not in VEHICLE_MATRIX_LAYOUTS
            or forward_sign not in VEHICLE_MATRIX_FORWARD_SIGNS
            or identity_key not in identities_by_key
            or not observations
            or tight_matches > observations
            or first_frame > last_frame
            or event.get("classification")
            != "vehicle_render_matrix_correlation_candidate"
            or event.get("vehicle_render_transform_candidate_proved")
            != ("true" if candidate_proved else "false")
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle matrix correlation violates boundary")
        seen_matrix_correlations.add(key)
        matrix_correlations.append(
            {
                "function_address": "8240E7B0",
                "caller_return_address": key[0],
                "matrix_layout": layout,
                "forward_sign": forward_sign,
                "identity_generation": identity_key[0],
                "identity_owner": identity_key[1],
                "identity_slot": identity_key[2],
                "observations": observations,
                "tight_matches": tight_matches,
                "first_frame": first_frame,
                "last_frame": last_frame,
                "matrix_address_changes": integer(
                    event, "matrix_address_changes"
                ),
                "matrix_hash_changes": integer(event, "matrix_hash_changes"),
                "last_matrix_address": hexadecimal(
                    event, "last_matrix_address"
                ),
                "last_matrix_hash": hexadecimal64(event, "last_matrix_hash"),
                "best_matrix_address": hexadecimal(
                    event, "best_matrix_address"
                ),
                "best_matrix_hash": hexadecimal64(event, "best_matrix_hash"),
                "best_position_delta_squared": finite_number(
                    event, "best_position_delta_squared"
                ),
                "best_forward_delta_squared": finite_number(
                    event, "best_forward_delta_squared"
                ),
                "best_normalized_score": finite_number(
                    event, "best_normalized_score"
                ),
                "vehicle_render_transform_candidate_proved": (
                    candidate_proved
                ),
            }
        )
    matrix_correlations.sort(
        key=lambda item: (
            item["caller_return_address"],
            item["matrix_layout"],
            item["forward_sign"],
            item["identity_owner"],
            item["identity_slot"],
        )
    )

    typed_render_item_profiles = []
    seen_typed_render_item_profiles = set()
    for event in selected:
        if event.get("event") != TYPED_RENDER_ITEM_PROFILE:
            continue
        descriptor_type = integer(event, "descriptor_type")
        descriptor_flag = integer(event, "descriptor_flag")
        key = (
            hexadecimal(event, "root_vtable"),
            hexadecimal(event, "child_vtable"),
            descriptor_type,
        )
        if (
            key in seen_typed_render_item_profiles
            or descriptor_type > 0xFFFF
            or descriptor_flag > 0xFF
            or event.get("function_address") != "8240E7B0"
            or event.get("hook_address") != "8240EC18"
            or event.get("classification")
            != "typed_render_item_descriptor_profile"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("typed render-item profile violates boundary")
        seen_typed_render_item_profiles.add(key)
        typed_render_item_profiles.append(
            {
                "function_address": "8240E7B0",
                "hook_address": "8240EC18",
                "root_address": hexadecimal(event, "root_address"),
                "root_vtable": key[0],
                "child_address": hexadecimal(event, "child_address"),
                "child_vtable": key[1],
                "descriptor_address": hexadecimal(
                    event, "descriptor_address"
                ),
                "descriptor_type": descriptor_type,
                "descriptor_payload": hexadecimal_allow_zero(
                    event, "descriptor_payload"
                ),
                "descriptor_flag": descriptor_flag,
                "descriptor_hash": hexadecimal64(event, "descriptor_hash"),
                "observations": integer(event, "observations"),
                "root_address_changes": integer(
                    event, "root_address_changes"
                ),
                "child_address_changes": integer(
                    event, "child_address_changes"
                ),
                "descriptor_address_changes": integer(
                    event, "descriptor_address_changes"
                ),
                "descriptor_hash_changes": integer(
                    event, "descriptor_hash_changes"
                ),
            }
        )
    typed_render_item_profiles.sort(
        key=lambda item: (
            item["root_vtable"],
            item["child_vtable"],
            item["descriptor_type"],
        )
    )

    typed_descriptor_correlations = []
    seen_typed_descriptor_correlations = set()
    for event in selected:
        if event.get("event") != TYPED_DESCRIPTOR_CORRELATION:
            continue
        identity_field = str(event.get("identity_field", ""))
        identity_key = (
            hexadecimal(event, "identity_generation"),
            hexadecimal(event, "identity_owner"),
            integer(event, "identity_slot"),
        )
        identity = identities_by_key.get(identity_key)
        matched_address = hexadecimal(event, "matched_address")
        if identity and identity_field in ("position", "forward"):
            expected_address = identity.get(f"{identity_field}_address")
        elif identity and identity_field == "owner":
            expected_address = identity_key[1]
        else:
            expected_address = None
        descriptor_type = integer(event, "descriptor_type")
        pointer_offset = integer(event, "pointer_offset")
        key = (
            hexadecimal(event, "root_vtable"),
            hexadecimal(event, "child_vtable"),
            descriptor_type,
            pointer_offset,
            identity_field,
            identity_key,
        )
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if (
            key in seen_typed_descriptor_correlations
            or descriptor_type > 0xFFFF
            or pointer_offset >= 248
            or pointer_offset % 4
            or identity_field not in DRAW_IDENTITY_FIELDS
            or identity is None
            or matched_address != expected_address
            or first_frame > last_frame
            or event.get("function_address") != "8240E7B0"
            or event.get("hook_address") != "8240EC18"
            or event.get("classification")
            != "typed_vehicle_descriptor_correlation_candidate"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError(
                "typed vehicle descriptor correlation violates boundary"
            )
        seen_typed_descriptor_correlations.add(key)
        typed_descriptor_correlations.append(
            {
                "function_address": "8240E7B0",
                "hook_address": "8240EC18",
                "root_vtable": key[0],
                "child_vtable": key[1],
                "descriptor_type": descriptor_type,
                "pointer_offset": pointer_offset,
                "identity_field": identity_field,
                "matched_address": matched_address,
                "identity_generation": identity_key[0],
                "identity_owner": identity_key[1],
                "identity_slot": identity_key[2],
                "observations": integer(event, "observations"),
                "first_frame": first_frame,
                "last_frame": last_frame,
            }
        )
    typed_descriptor_correlations.sort(
        key=lambda item: (
            item["root_vtable"],
            item["child_vtable"],
            item["descriptor_type"],
            item["pointer_offset"],
            item["identity_owner"],
        )
    )

    failures = []
    if totals["observations"] != (
        totals["valid_observations"] + totals["invalid_observations"]
    ):
        failures.append("observation accounting drifted")
    if not totals["observations"] or not totals["valid_observations"]:
        failures.append("no valid vehicle-pose observation")
    if totals["invalid_observations"]:
        failures.append("invalid vehicle-pose observations occurred")
    if totals["overflow"]:
        failures.append("vehicle identity table overflowed")
    if totals["identities"] > totals["summary_limit"]:
        failures.append("vehicle identity evidence was truncated")
    if len(identities) != totals["identities"]:
        failures.append("vehicle identity coverage drifted")
    if sum(item["observations"] for item in identities) != totals[
        "valid_observations"
    ]:
        failures.append("identity observation accounting drifted")
    if any(item["address_mismatches"] for item in identities):
        failures.append("vehicle transform addresses changed")
    if any(item["owner_vtable_mismatches"] for item in identities):
        failures.append("vehicle owner vtable changed")
    if owner_class_drift:
        failures.append("vehicle owner vtable snapshot drifted")
    if not owner_classes:
        failures.append("no vehicle owner class seed")
    if totals["owner_method_stack_faults"]:
        failures.append("vehicle owner method stack faulted")
    if totals["owner_indirect_observations"] != (
        totals["owner_indirect_valid_observations"]
        + totals["owner_indirect_invalid_observations"]
    ):
        failures.append("vehicle owner indirect accounting drifted")
    if totals["owner_indirect_invalid_observations"]:
        failures.append("invalid vehicle owner indirect observations occurred")
    if totals["owner_indirect_target_overflow"]:
        failures.append("vehicle owner indirect target table overflowed")
    if len(indirect_targets) != totals["owner_indirect_targets"]:
        failures.append("vehicle owner indirect target coverage drifted")
    if sum(item["observations"] for item in indirect_targets) != totals[
        "owner_indirect_valid_observations"
    ]:
        failures.append("vehicle owner indirect target totals drifted")
    if not totals["draws_examined"] or not totals["draw_argument_probes"]:
        failures.append("no title draw arguments were examined")
    if totals["draw_argument_matches"] != sum(
        item["observations"] for item in draw_correlations
    ):
        failures.append("vehicle draw correlation observation accounting drifted")
    if totals["draw_argument_probes"] != (
        totals["direct_argument_probes"]
        + totals["semantic_argument_probes"]
        + totals["indirect_argument_probes"]
    ):
        failures.append("vehicle draw provenance probe accounting drifted")
    if (
        totals["direct_draws_examined"] > totals["draws_examined"]
        or totals["indirect_draws_examined"] > totals["draws_examined"]
    ):
        failures.append("vehicle draw provenance coverage accounting drifted")
    if len(draw_correlations) != totals["draw_correlations"]:
        failures.append("vehicle draw correlation coverage drifted")
    if totals["draw_correlation_overflow"]:
        failures.append("vehicle draw correlation table overflowed")
    if totals["identity_address_overflow"]:
        failures.append("vehicle identity address index overflowed")
    if totals["identity_addresses"] != totals["identities"] * 3:
        failures.append("vehicle identity address index coverage drifted")
    if totals["draw_correlations"] > totals["draw_correlation_capacity"]:
        failures.append("vehicle draw correlation capacity drifted")
    if totals["object_scans"] > totals["object_scan_requests"]:
        failures.append("vehicle object scan request accounting drifted")
    if totals["object_scan_words"] != (
        totals["object_scans"] * totals["object_scan_word_count"]
    ):
        failures.append("vehicle object scan word accounting drifted")
    if totals["object_scan_cache_entries"] != totals["object_scans"]:
        failures.append("vehicle object scan cache accounting drifted")
    if totals["object_scan_cache_overflow"]:
        failures.append("vehicle object scan cache overflowed")
    if totals["object_argument_matches"] != sum(
        item["observations"] for item in object_correlations
    ):
        failures.append("vehicle object correlation accounting drifted")
    if len(object_correlations) != totals["object_correlations"]:
        failures.append("vehicle object correlation coverage drifted")
    if totals["object_correlation_overflow"]:
        failures.append("vehicle object correlation table overflowed")
    if totals["object_correlations"] > totals["object_correlation_capacity"]:
        failures.append("vehicle object correlation capacity drifted")
    for register in ("r7", "r8"):
        requests = totals[f"targeted_render_context_{register}_scan_requests"]
        scans = totals[f"targeted_render_context_{register}_scans"]
        if not requests or not scans:
            failures.append(
                f"targeted render-context {register} coverage was absent"
            )
        if scans > requests:
            failures.append(
                f"targeted render-context {register} accounting drifted"
            )
    if totals["render_context_callee_observations"] != (
        totals["render_context_callee_eligible_observations"]
        + totals["render_context_callee_ineligible_observations"]
    ):
        failures.append("render-context callee mode accounting drifted")
    if totals["render_context_callee_eligible_observations"] != (
        totals["render_context_callee_valid_observations"]
        + totals["render_context_callee_invalid_root"]
        + totals["render_context_callee_invalid_vtable"]
        + totals["render_context_callee_invalid_vector"]
    ):
        failures.append("render-context callee payload accounting drifted")
    if (
        not totals["render_context_callee_observations"]
        or not totals["render_context_callee_eligible_observations"]
        or not totals["render_context_callee_valid_observations"]
        or not render_context_callees
    ):
        failures.append("render-context callee coverage was absent")
    if (
        totals["render_context_callee_invalid_root"]
        or totals["render_context_callee_invalid_vtable"]
        or totals["render_context_callee_invalid_vector"]
    ):
        failures.append("render-context callee payload was invalid")
    if totals["render_context_callee_profile_overflow"]:
        failures.append("render-context callee profile table overflowed")
    if len(render_context_callees) != totals["render_context_callee_profiles"]:
        failures.append("render-context callee profile coverage drifted")
    if sum(item["observations"] for item in render_context_callees) != totals[
        "render_context_callee_valid_observations"
    ]:
        failures.append("render-context callee profile totals drifted")
    if totals["render_context_callee_profiles"] > totals[
        "render_context_callee_profile_capacity"
    ]:
        failures.append("render-context callee profile capacity drifted")
    if totals["render_context_dispatcher_eligible_observations"] > totals[
        "render_context_dispatcher_observations"
    ]:
        failures.append("render-context dispatcher path accounting drifted")
    if totals["render_context_dispatcher_matches"] + totals[
        "render_context_dispatcher_mismatches"
    ] != totals["render_context_callee_observations"]:
        failures.append("render-context dispatcher match accounting drifted")
    if totals["render_context_dispatcher_matches"] > totals[
        "render_context_dispatcher_eligible_observations"
    ]:
        failures.append("render-context dispatcher coverage drifted")
    if totals["render_context_dispatcher_mismatches"]:
        failures.append("render-context dispatcher lineage mismatched")
    matrix_caller_accounting_complete = totals[
        "vehicle_matrix_caller_valid_observations"
    ] + totals["vehicle_matrix_caller_invalid_range"] + totals[
        "vehicle_matrix_caller_non_finite"
    ] == totals["vehicle_matrix_caller_observations"]
    if (
        not matrix_caller_accounting_complete
        or not totals["vehicle_matrix_caller_accounting_complete"]
    ):
        failures.append("vehicle matrix caller accounting drifted")
    matrix_route_accounting_complete = totals[
        "vehicle_matrix_candidate_observations"
    ] + totals["vehicle_matrix_routes_without_identity"] == (
        totals["vehicle_matrix_caller_valid_observations"] * 4
    )
    if (
        not matrix_route_accounting_complete
        or not totals["vehicle_matrix_route_accounting_complete"]
    ):
        failures.append("vehicle matrix route accounting drifted")
    if (
        not totals["vehicle_matrix_caller_observations"]
        or not totals["vehicle_matrix_caller_valid_observations"]
        or not totals["vehicle_matrix_identity_comparisons"]
        or not totals["vehicle_matrix_candidate_observations"]
        or not matrix_correlations
    ):
        failures.append("vehicle matrix caller coverage was absent")
    if (
        totals["vehicle_matrix_caller_invalid_range"]
        or totals["vehicle_matrix_caller_non_finite"]
    ):
        failures.append("vehicle matrix caller payload was invalid")
    if sum(item["observations"] for item in matrix_correlations) != totals[
        "vehicle_matrix_candidate_observations"
    ]:
        failures.append("vehicle matrix candidate totals drifted")
    if sum(item["tight_matches"] for item in matrix_correlations) != totals[
        "vehicle_matrix_tight_matches"
    ]:
        failures.append("vehicle matrix tight-match totals drifted")
    if len(matrix_correlations) != totals["vehicle_matrix_correlations"]:
        failures.append("vehicle matrix correlation coverage drifted")
    if totals["vehicle_matrix_correlation_overflow"]:
        failures.append("vehicle matrix correlation table overflowed")
    if totals["vehicle_matrix_correlations"] > totals[
        "vehicle_matrix_correlation_capacity"
    ]:
        failures.append("vehicle matrix correlation capacity drifted")
    typed_render_item_accounting_complete = totals[
        "typed_render_item_valid_observations"
    ] + totals["typed_render_item_invalid_root"] + totals[
        "typed_render_item_invalid_child"
    ] + totals["typed_render_item_invalid_descriptor"] == totals[
        "typed_render_item_observations"
    ]
    if (
        not typed_render_item_accounting_complete
        or not totals["typed_render_item_accounting_complete"]
    ):
        failures.append("typed render-item accounting drifted")
    if (
        not totals["typed_render_item_observations"]
        or not totals["typed_render_item_valid_observations"]
        or not typed_render_item_profiles
    ):
        failures.append("typed render-item coverage was absent")
    if (
        totals["typed_render_item_invalid_root"]
        or totals["typed_render_item_invalid_child"]
        or totals["typed_render_item_invalid_descriptor"]
    ):
        failures.append("typed render-item payload was invalid")
    if sum(item["observations"] for item in typed_render_item_profiles) != totals[
        "typed_render_item_valid_observations"
    ]:
        failures.append("typed render-item profile totals drifted")
    if len(typed_render_item_profiles) != totals["typed_render_item_profiles"]:
        failures.append("typed render-item profile coverage drifted")
    if totals["typed_render_item_profile_overflow"]:
        failures.append("typed render-item profile table overflowed")
    if totals["typed_render_item_profiles"] > totals[
        "typed_render_item_profile_capacity"
    ]:
        failures.append("typed render-item profile capacity drifted")
    if totals["typed_descriptor_scan_words"] != (
        totals["typed_render_item_valid_observations"]
        * totals["typed_descriptor_word_count"]
    ):
        failures.append("typed descriptor scan accounting drifted")
    if sum(
        item["observations"] for item in typed_descriptor_correlations
    ) != totals["typed_descriptor_matches"]:
        failures.append("typed descriptor match totals drifted")
    if len(typed_descriptor_correlations) != totals[
        "typed_descriptor_correlations"
    ]:
        failures.append("typed descriptor correlation coverage drifted")
    if totals["typed_descriptor_correlation_overflow"]:
        failures.append("typed descriptor correlation table overflowed")
    if totals["typed_descriptor_correlations"] > totals[
        "typed_descriptor_correlation_capacity"
    ]:
        failures.append("typed descriptor correlation capacity drifted")
    for method in method_correlations:
        if method["status"] != "complete" or method["calls"] != method["exits"]:
            failures.append(
                f"vehicle owner method {method['method_address']} was unbalanced"
            )
        if method["matched_owner_calls"] > method["calls"]:
            failures.append(
                f"vehicle owner method {method['method_address']} owner accounting drifted"
            )
        if method["backend_draw_matches"] > method["direct_draw_origins"]:
            failures.append(
                f"vehicle owner method {method['method_address']} draw accounting drifted"
            )

    render_candidate_proved = any(
        item["vehicle_render_method_candidate_proved"]
        for item in method_correlations
    )
    draw_argument_candidate_proved = bool(draw_correlations)
    object_candidate_proved = bool(object_correlations)
    matrix_candidate_proved = any(
        item["vehicle_render_transform_candidate_proved"]
        for item in matrix_correlations
    )
    typed_descriptor_candidate_proved = bool(typed_descriptor_correlations)
    draw_provenance_coverage_complete = (
        title_provenance_requested
        and title_provenance_armed
        and totals["direct_draws_examined"] > 0
        and totals["indirect_draws_examined"] > 0
        and totals["direct_argument_probes"] > 0
        and totals["indirect_argument_probes"] > 0
    )
    if summary["draw_provenance_coverage_complete"] != (
        "true" if draw_provenance_coverage_complete else "false"
    ):
        failures.append("vehicle draw provenance coverage result drifted")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "totals": totals,
        "identities": identities,
        "owner_classes": owner_classes,
        "method_correlations": method_correlations,
        "indirect_targets": indirect_targets,
        "draw_argument_correlations": draw_correlations,
        "draw_object_correlations": object_correlations,
        "render_context_callees": render_context_callees,
        "vehicle_matrix_correlations": matrix_correlations,
        "typed_render_item_profiles": typed_render_item_profiles,
        "typed_descriptor_correlations": typed_descriptor_correlations,
        "coverage": {
            "title_provenance_requested": title_provenance_requested,
            "title_provenance_armed": title_provenance_armed,
            "draw_provenance_coverage_complete": (
                draw_provenance_coverage_complete
            ),
        },
        "qualification": {
            "vehicle_instance_semantic_seed_proved": not failures,
            "vehicle_owner_class_seed_proved": not failures,
            "vehicle_render_method_candidate_proved": (
                not failures and render_candidate_proved
            ),
            "player_vehicle_identity_proved": False,
            "vehicle_draw_identity_proved": False,
            "vehicle_draw_argument_candidate_proved": (
                not failures
                and draw_provenance_coverage_complete
                and draw_argument_candidate_proved
            ),
            "vehicle_draw_object_candidate_proved": (
                not failures
                and draw_provenance_coverage_complete
                and object_candidate_proved
            ),
            "render_context_callee_contract_proved": (
                not failures and bool(render_context_callees)
            ),
            "vehicle_render_matrix_candidate_proved": (
                not failures and matrix_candidate_proved
            ),
            "typed_render_item_contract_proved": (
                not failures and bool(typed_render_item_profiles)
            ),
            "typed_vehicle_descriptor_candidate_proved": (
                not failures and typed_descriptor_candidate_proved
            ),
            "native_vehicle_rendering_admitted": False,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("events", nargs="+", type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(read_events(args.events), args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if document["status"] != "complete":
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"vehicle-pose summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
