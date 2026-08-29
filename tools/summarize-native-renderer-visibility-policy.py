#!/usr/bin/env python3
"""Qualify passive title visibility-policy input/outcome correlation."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-policy.v1"
CONFIG = "native_renderer.discovery.semantic_visibility_policy_config"
CATEGORY = (
    "native_renderer.discovery.semantic_visibility_policy_category_summary"
)
EXPONENT = (
    "native_renderer.discovery.semantic_visibility_spatial_exponent_summary"
)
SUMMARY = "native_renderer.discovery.semantic_visibility_policy_summary"
VISIBILITY_CATEGORY = (
    "native_renderer.discovery.semantic_visibility_category_summary"
)
OUTCOMES = ("early_rejected", "rejected", "selected")


def read_events(paths):
    events = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def integer(event, key):
    try:
        value = int(event[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if value < 0:
        raise ValueError(f"negative {key}")
    return value


def exact_event(events, name):
    matches = [event for event in events if event.get("event") == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} event")
    return matches[0]


def select_session(events, requested):
    sessions = {
        event.get("session") for event in events if event.get("event") == CONFIG
    }
    sessions.discard(None)
    if requested:
        if requested not in sessions:
            raise ValueError("requested session has no visibility-policy config")
        return requested
    if len(sessions) != 1:
        raise ValueError("visibility-policy input contains multiple sessions")
    return next(iter(sessions))


def static_contract(document):
    try:
        contract = document["procedural_model_receiver_lifecycle"][
            "visibility_policy_inputs"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("static visibility-policy contract is missing") from error
    expected = {
        "spatial_prefilter_address": "82E1FEF0",
        "receiver_spatial_context_pointer_offset": 4,
        "receiver_spatial_vector_offsets": [16, 32],
        "category_spatial_argument_register": "r4",
        "category_spatial_stride": 192,
        "category_spatial_scalar_offsets": [160, 164, 168],
        "category_query_argument_register": "r5",
        "category_query_stride": 32,
        "spatial_helper_address": "8243F9A0",
        "category_helper_address": "82441048",
        "descriptor_distance_scalar_offset": 60,
        "runtime_distance_scalar_offset": 44,
        "squared_distance_register": "f26",
        "threshold_register": "f0",
        "runtime_threshold_hook_address": "82E20134",
        "descriptor_threshold_hook_address": "82E201B0",
        "structural_derivation_proved": True,
        "camera_semantics_proved": False,
        "frustum_plane_layout_proved": False,
        "bounds_shape_semantics_proved": False,
        "native_policy_execution_enabled": False,
        "guest_state_changed": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("static visibility-policy contract drifted")
    if not contract.get("passive_input_outcome_correlation_required"):
        raise ValueError("static visibility-policy correlation is not required")
    expected_spatial_helper = {
        "distance_helper_address": "8243FD70",
        "query_vector_offset": 0,
        "query_scalar_offsets": [16, 20, 24],
        "segment_endpoint_registers": ["v1", "v2"],
        "squared_delta_operation": "vmsum3fp128",
        "distance_test_structure_proved": True,
        "world_space_semantics_proved": False,
    }
    expected_category_helper = {
        "vector_block_offsets": [0, 16, 32, 48, 64, 80],
        "vector_block_count": 6,
        "input_registers": ["v1", "v2"],
        "return_domain": [0, 1, 2],
        "six_vector_classifier_structure_proved": True,
        "frustum_semantics_proved": False,
    }
    if contract.get("spatial_helper_contract") != expected_spatial_helper or (
        contract.get("category_helper_contract") != expected_category_helper
    ):
        raise ValueError("static visibility-policy helper contract drifted")
    return contract


def build(events, static, requested_session=None):
    contract = static_contract(static)
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary = exact_event(selected, SUMMARY)

    expected_config = {
        "status": "armed",
        "class": "proceduralGeometry::CProceduralModels",
        "visibility_function": "82E1FD00",
        "record_entry_hook": "82E20094",
        "runtime_threshold_hook": "82E20134",
        "descriptor_threshold_hook": "82E201B0",
        "spatial_distance_source": "f26",
        "threshold_source": "f0",
        "runtime_distance_scalar_offset": "44",
        "descriptor_distance_scalar_offset": "60",
        "outcomes": "early_rejected,rejected,selected",
        "classification": "title_spatial_policy_input_outcome_correlation",
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_policy_execution": "false",
        "native_culling": "false",
        "native_lod": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("visibility-policy runtime configuration drifted")
    if integer(config, "spatial_exponent_capacity") != 256:
        raise ValueError("visibility-policy exponent capacity drifted")

    expected_summary = {
        "status": "complete",
        "accounting_complete": "true",
        "scope": "active_title_record_only",
        "unscoped_continuations_excluded": "true",
        "classification": "title_spatial_policy_input_outcome_correlation",
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_policy_execution": "false",
        "native_culling": "false",
        "native_lod": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("visibility-policy summary is incomplete or unsafe")
    total_keys = (
        "records",
        "spatial_samples",
        "runtime_threshold_observations",
        "runtime_distance_less",
        "descriptor_threshold_observations",
        "descriptor_distance_exceeded",
        "spatial_histogram_records",
        "invalid_spatial_values",
        "invalid_threshold_values",
        "hook_faults",
        "runtime_threshold_without_record",
        "duplicate_runtime_threshold",
        "descriptor_threshold_without_record",
        "duplicate_descriptor_threshold",
    )
    totals = {key: integer(summary, key) for key in total_keys}
    if (
        totals["records"] <= 0
        or totals["spatial_samples"] != totals["records"]
        or totals["spatial_histogram_records"] != totals["records"]
        or totals["runtime_distance_less"]
        > totals["runtime_threshold_observations"]
        or totals["descriptor_distance_exceeded"]
        > totals["descriptor_threshold_observations"]
        or any(
            totals[key]
            for key in (
                "invalid_spatial_values",
                "invalid_threshold_values",
                "hook_faults",
                "duplicate_runtime_threshold",
                "duplicate_descriptor_threshold",
            )
        )
    ):
        raise ValueError("visibility-policy aggregate accounting failed")

    visibility = {}
    for event in selected:
        if event.get("event") != VISIBILITY_CATEGORY:
            continue
        category = integer(event, "category")
        if category in visibility or event.get("status") != "complete":
            raise ValueError("visibility category evidence drifted")
        visibility[category] = {
            outcome: integer(event, outcome if outcome != "early_rejected" else "early_rejected")
            for outcome in OUTCOMES
        }

    categories = {}
    category_totals = {key: 0 for key in total_keys[:6]}
    for event in selected:
        if event.get("event") != CATEGORY:
            continue
        category = integer(event, "category")
        outcome = event.get("outcome")
        key = (category, outcome)
        if (
            key in categories
            or category not in visibility
            or outcome not in OUTCOMES
            or event.get("status") != "complete"
            or event.get("native_policy_execution") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("visibility-policy category evidence drifted")
        item = {key: integer(event, key) for key in total_keys[:6]}
        if (
            item["records"] != visibility[category][outcome]
            or item["spatial_samples"] != item["records"]
            or item["runtime_distance_less"]
            > item["runtime_threshold_observations"]
            or item["descriptor_distance_exceeded"]
            > item["descriptor_threshold_observations"]
        ):
            raise ValueError("visibility-policy category accounting failed")
        categories[key] = item
        for field in category_totals:
            category_totals[field] += item[field]
    expected_nonzero = {
        (category, outcome)
        for category, counts in visibility.items()
        for outcome, count in counts.items()
        if count
    }
    if set(categories) != expected_nonzero or any(
        category_totals[key] != totals[key] for key in category_totals
    ):
        raise ValueError("visibility-policy category totals drifted")

    histograms = {outcome: {} for outcome in OUTCOMES}
    for event in selected:
        if event.get("event") != EXPONENT:
            continue
        outcome = event.get("outcome")
        exponent = integer(event, "float_exponent")
        if (
            outcome not in OUTCOMES
            or exponent >= 256
            or exponent in histograms[outcome]
            or event.get("status") != "complete"
            or event.get("source")
            != "title_shared_spatial_distance_squared_f26"
            or event.get("native_policy_execution") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("visibility-policy exponent evidence drifted")
        records = integer(event, "records")
        if not records:
            raise ValueError("visibility-policy exponent bin is empty")
        histograms[outcome][exponent] = records
    histogram_totals = {
        outcome: sum(histograms[outcome].values()) for outcome in OUTCOMES
    }
    for outcome in OUTCOMES:
        expected = sum(
            item["spatial_samples"]
            for (category, item_outcome), item in categories.items()
            if item_outcome == outcome
        )
        if histogram_totals[outcome] != expected:
            raise ValueError("visibility-policy exponent accounting failed")

    return {
        "schema": SCHEMA,
        "status": "complete",
        "session": session,
        "static_contract": contract,
        "totals": totals,
        "categories": {
            f"{category}:{outcome}": item
            for (category, outcome), item in sorted(categories.items())
        },
        "spatial_exponent_histograms": {
            outcome: {
                str(exponent): count
                for exponent, count in sorted(histograms[outcome].items())
            }
            for outcome in OUTCOMES
        },
        "qualification": {
            "structural_policy_inputs_proved": True,
            "title_input_outcome_correlation_proved": True,
            "ready_for_semantic_hypothesis_testing": True,
            "unscoped_continuation_observations_excluded": True,
            "camera_semantics_proved": False,
            "frustum_plane_layout_proved": False,
            "native_policy_execution_enabled": False,
        },
        "safety": {
            "guest_payload_read": False,
            "guest_state_changed": False,
            "control_flow_changed": False,
            "native_culling": False,
            "native_lod": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("events", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(
            read_events(args.events),
            json.loads(args.static.read_text(encoding="utf-8")),
            args.session,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"native renderer visibility policy summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
