#!/usr/bin/env python3
"""Qualify the assembled independent visibility-policy shadow."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-assembly-shadow.v1"
CONFIG = (
    "native_renderer.discovery.semantic_visibility_assembly_shadow_config"
)
CATEGORY = (
    "native_renderer.discovery."
    "semantic_visibility_assembly_shadow_category_summary"
)
SUMMARY = (
    "native_renderer.discovery.semantic_visibility_assembly_shadow_summary"
)
ORACLE_CATEGORY = (
    "native_renderer.discovery.semantic_visibility_oracle_category_summary"
)
SPATIAL_CATEGORY = (
    "native_renderer.discovery."
    "semantic_visibility_spatial_shadow_category_summary"
)
CATEGORY_SHADOW_CATEGORY = (
    "native_renderer.discovery."
    "semantic_visibility_category_shadow_category_summary"
)
OUTCOMES = ("early_rejected", "rejected", "selected")
COUNT_KEYS = (
    "records",
    "modelled_records",
    "predicted_selected",
    "predicted_rejected",
    "title_matches",
    "false_positive",
    "false_negative",
    "spatial_input_observations",
    "spatial_predicted_passes",
    "category_input_observations",
    "category_result_0",
    "category_result_1",
    "category_result_2",
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
            raise ValueError("requested session has no assembly-shadow config")
        return requested
    if len(sessions) != 1:
        raise ValueError("assembly-shadow input contains multiple sessions")
    return next(iter(sessions))


def static_contract(document):
    try:
        contract = document["procedural_model_receiver_lifecycle"][
            "visibility_policy_assembly_shadow"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("static assembly-shadow contract is missing") from error
    expected = {
        "record_entry_hook_address": "82E20094",
        "spatial_input_hook_address": "82E2034C",
        "spatial_result_hook_address": "82E20350",
        "category_input_hook_address": "82E20364",
        "category_result_hook_address": "82E20368",
        "title_result_hook_address": "82E206F8",
        "record_exit_hook_address": "82E2084C",
        "model": "independent_spatial_then_category_selection",
        "selection_rule": "any_nonzero_predicted_category_result_selects",
        "bounded_guest_payload_bytes_per_candidate": 148,
        "scope": "active_title_record_only",
        "title_outcome_comparison_required": True,
        "guest_payload_read": "bounded_spatial_and_category_inputs",
        "guest_state_changed": False,
        "control_flow_changed": False,
        "native_policy_execution": "shadow_only",
        "native_culling_enabled": False,
        "native_lod_enabled": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("static assembly-shadow contract drifted")
    return contract


def validate_counts(item):
    if (
        item["modelled_records"] > item["records"]
        or item["predicted_selected"] + item["predicted_rejected"]
        != item["modelled_records"]
        or item["title_matches"]
        + item["false_positive"]
        + item["false_negative"]
        != item["modelled_records"]
        or item["spatial_predicted_passes"]
        > item["spatial_input_observations"]
        or item["category_input_observations"]
        != item["spatial_predicted_passes"]
        or item["category_result_0"]
        + item["category_result_1"]
        + item["category_result_2"]
        != item["category_input_observations"]
        or item["false_positive"]
        or item["false_negative"]
        or item["invalid_inputs"]
    ):
        raise ValueError("assembly-shadow comparison failed")


def indexed(events, name, fields):
    result = {}
    for event in events:
        if event.get("event") != name:
            continue
        key = (integer(event, "category"), event.get("outcome"))
        if key in result or key[1] not in OUTCOMES or event.get("status") != "complete":
            raise ValueError(f"{name} evidence drifted")
        result[key] = {field: integer(event, field) for field in fields}
    return result


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
        "spatial_input_hook": "82E2034C",
        "spatial_result_hook": "82E20350",
        "category_input_hook": "82E20364",
        "category_result_hook": "82E20368",
        "title_result_hook": "82E206F8",
        "record_completion_hook": "82E2084C",
        "model": "independent_spatial_then_category_selection",
        "selection_rule": "any_nonzero_predicted_category_result_selects",
        "bounded_guest_payload_bytes_per_candidate": "148",
        "scope": "active_title_record_only",
        "classification": "independent_visibility_policy_assembly_shadow",
        "guest_payload_read": "bounded_spatial_and_category_inputs",
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
        raise ValueError("assembly-shadow runtime configuration drifted")
    expected_summary = {
        "status": "complete",
        "accounting_complete": "true",
        "model": "independent_spatial_then_category_selection",
        "scope": "active_title_record_only",
        "classification": "independent_visibility_policy_assembly_shadow",
        "guest_payload_read": "bounded_spatial_and_category_inputs",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_policy_execution": "shadow_only",
        "native_culling": "false",
        "native_lod": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("assembly-shadow summary is incomplete or unsafe")
    totals = {key: integer(summary, key) for key in COUNT_KEYS}
    unmodelled_records = integer(summary, "unmodelled_records")
    validate_counts(totals)
    if (
        totals["records"] <= 0
        or totals["modelled_records"] <= 0
        or unmodelled_records != totals["records"] - totals["modelled_records"]
    ):
        raise ValueError("assembly-shadow aggregate qualification failed")

    oracle = indexed(
        selected,
        ORACLE_CATEGORY,
        ("records", "category_result_0", "category_result_1", "category_result_2"),
    )
    spatial = indexed(selected, SPATIAL_CATEGORY, ("input_observations",))
    category_shadow = indexed(
        selected, CATEGORY_SHADOW_CATEGORY, ("input_observations",)
    )
    categories = {}
    sums = {key: 0 for key in COUNT_KEYS}
    for event in selected:
        if event.get("event") != CATEGORY:
            continue
        key = (integer(event, "category"), event.get("outcome"))
        if (
            key in categories
            or key not in oracle
            or key not in spatial
            or key not in category_shadow
            or event.get("status") != "complete"
            or event.get("native_policy_execution") != "shadow_only"
            or event.get("guest_payload_read")
            != "bounded_spatial_and_category_inputs"
            or event.get("guest_state_changed") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("assembly-shadow category evidence drifted")
        item = {field: integer(event, field) for field in COUNT_KEYS}
        validate_counts(item)
        if (
            item["records"] != oracle[key]["records"]
            or item["spatial_input_observations"]
            != spatial[key]["input_observations"]
            or item["category_input_observations"]
            != category_shadow[key]["input_observations"]
            or any(
                item[f"category_result_{result}"]
                != oracle[key][f"category_result_{result}"]
                for result in range(3)
            )
        ):
            raise ValueError("assembly-shadow oracle reconciliation failed")
        categories[key] = item
        for field in COUNT_KEYS:
            sums[field] += item[field]
    if set(categories) != set(oracle) or any(
        sums[key] != totals[key] for key in COUNT_KEYS
    ):
        raise ValueError("assembly-shadow category totals drifted")

    return {
        "schema": SCHEMA,
        "status": "complete",
        "session": session,
        "static_contract": contract,
        "totals": {**totals, "unmodelled_records": unmodelled_records},
        "categories": {
            f"{category}:{outcome}": item
            for (category, outcome), item in sorted(categories.items())
        },
        "qualification": {
            "independent_visibility_policy_assembly_shadow_proved": True,
            "zero_title_mismatches": True,
            "ready_for_conservative_native_policy_execution_design": True,
            "native_policy_execution_enabled": False,
        },
        "safety": {
            "guest_payload_read": "bounded_spatial_and_category_inputs",
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
            f"native renderer visibility assembly shadow summary failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
