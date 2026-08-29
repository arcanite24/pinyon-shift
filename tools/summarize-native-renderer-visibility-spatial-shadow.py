#!/usr/bin/env python3
"""Qualify the independent scalar mirror of the title spatial helper."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-spatial-shadow.v1"
CONFIG = "native_renderer.discovery.semantic_visibility_spatial_shadow_config"
CATEGORY = (
    "native_renderer.discovery."
    "semantic_visibility_spatial_shadow_category_summary"
)
SUMMARY = (
    "native_renderer.discovery.semantic_visibility_spatial_shadow_summary"
)
ORACLE_CATEGORY = (
    "native_renderer.discovery.semantic_visibility_oracle_category_summary"
)
OUTCOMES = ("early_rejected", "rejected", "selected")
COUNT_KEYS = (
    "records",
    "input_observations",
    "comparisons",
    "matches",
    "false_positive",
    "false_negative",
    "invalid_inputs",
)


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
            raise ValueError("requested session has no spatial-shadow config")
        return requested
    if len(sessions) != 1:
        raise ValueError("spatial-shadow input contains multiple sessions")
    return next(iter(sessions))


def static_contract(document):
    try:
        contract = document["procedural_model_receiver_lifecycle"][
            "visibility_spatial_shadow"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("static spatial-shadow contract is missing") from error
    expected = {
        "input_hook_address": "82E2034C",
        "result_hook_address": "82E20350",
        "helper_address": "8243F9A0",
        "distance_helper_address": "8243FD70",
        "query_vector_offsets": [0, 4, 8],
        "query_scalar_offsets": [16, 20, 24],
        "endpoint_vector_offsets": [0, 4, 8],
        "interpolation_factor": 0.5,
        "shortcut": "query_scalar_20_less_than_zero_selects",
        "comparison": "query_scalar_16_times_distance_squared_le_"
        "query_scalar_24_times_half_segment_squared",
        "bounded_guest_payload_bytes": 52,
        "scope": "active_title_record_only",
        "title_result_comparison_required": True,
        "guest_payload_read": "bounded_spatial_helper_inputs",
        "guest_state_changed": False,
        "control_flow_changed": False,
        "native_policy_execution": "shadow_only",
        "native_culling_enabled": False,
        "native_lod_enabled": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("static spatial-shadow contract drifted")
    return contract


def validate_counts(item):
    if (
        item["comparisons"] != item["input_observations"]
        or item["matches"]
        + item["false_positive"]
        + item["false_negative"]
        != item["comparisons"]
        or item["false_positive"]
        or item["false_negative"]
        or item["invalid_inputs"]
    ):
        raise ValueError("spatial-shadow comparison failed")


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
        "input_hook": "82E2034C",
        "result_hook": "82E20350",
        "helper": "8243F9A0",
        "distance_helper": "8243FD70",
        "query_vector_offsets": "0,4,8",
        "query_scalar_offsets": "16,20,24",
        "endpoint_vector_offsets": "0,4,8",
        "interpolation_factor": "0.5",
        "shortcut": "query_scalar_20_less_than_zero_selects",
        "comparison": "query_scalar_16_times_distance_squared_le_"
        "query_scalar_24_times_half_segment_squared",
        "bounded_guest_payload_bytes": "52",
        "scope": "active_title_record_only",
        "classification": "independent_spatial_helper_shadow",
        "guest_payload_read": "bounded_spatial_helper_inputs",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_policy_execution": "shadow_only",
        "native_culling": "false",
        "native_lod": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("spatial-shadow runtime configuration drifted")
    expected_summary = {
        "status": "complete",
        "accounting_complete": "true",
        "model": "bounded_title_spatial_helper_scalar_mirror",
        "scope": "active_title_record_only",
        "unscoped_continuations_excluded": "true",
        "classification": "independent_spatial_helper_shadow",
        "guest_payload_read": "bounded_spatial_helper_inputs",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_policy_execution": "shadow_only",
        "native_culling": "false",
        "native_lod": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("spatial-shadow summary is incomplete or unsafe")
    totals = {key: integer(summary, key) for key in COUNT_KEYS}
    diagnostics = {
        "input_without_record": integer(summary, "input_without_record"),
        "result_without_input": integer(summary, "result_without_input"),
    }
    validate_counts(totals)
    if totals["records"] <= 0 or totals["comparisons"] <= 0:
        raise ValueError("spatial-shadow has no qualifying comparisons")

    oracle = {}
    for event in selected:
        if event.get("event") != ORACLE_CATEGORY:
            continue
        category = integer(event, "category")
        outcome = event.get("outcome")
        key = (category, outcome)
        if (
            key in oracle
            or outcome not in OUTCOMES
            or event.get("status") != "complete"
        ):
            raise ValueError("visibility-oracle category evidence drifted")
        oracle[key] = {
            "records": integer(event, "records"),
            "input_observations": integer(
                event, "spatial_helper_observations"
            ),
        }

    categories = {}
    sums = {key: 0 for key in COUNT_KEYS}
    for event in selected:
        if event.get("event") != CATEGORY:
            continue
        category = integer(event, "category")
        outcome = event.get("outcome")
        key = (category, outcome)
        if (
            key in categories
            or key not in oracle
            or event.get("status") != "complete"
            or event.get("native_policy_execution") != "shadow_only"
            or event.get("guest_payload_read")
            != "bounded_spatial_helper_inputs"
            or event.get("guest_state_changed") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("spatial-shadow category evidence drifted")
        item = {field: integer(event, field) for field in COUNT_KEYS}
        validate_counts(item)
        if (
            item["records"] != oracle[key]["records"]
            or item["input_observations"]
            != oracle[key]["input_observations"]
        ):
            raise ValueError("spatial-shadow oracle reconciliation failed")
        categories[key] = item
        for field in COUNT_KEYS:
            sums[field] += item[field]
    if set(categories) != set(oracle) or any(
        sums[key] != totals[key] for key in COUNT_KEYS
    ):
        raise ValueError("spatial-shadow category totals drifted")

    return {
        "schema": SCHEMA,
        "status": "complete",
        "session": session,
        "static_contract": contract,
        "totals": {**totals, **diagnostics},
        "categories": {
            f"{category}:{outcome}": item
            for (category, outcome), item in sorted(categories.items())
        },
        "qualification": {
            "independent_spatial_helper_shadow_proved": True,
            "zero_title_mismatches": True,
            "bounded_input_reads_proved": True,
            "ready_for_category_classifier_shadow": True,
            "native_policy_execution_enabled": False,
        },
        "safety": {
            "guest_payload_read": "bounded_spatial_helper_inputs",
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
        print(
            f"native renderer spatial shadow summary failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
