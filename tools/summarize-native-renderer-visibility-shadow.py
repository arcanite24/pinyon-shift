#!/usr/bin/env python3
"""Qualify the passive title-result visibility shadow model."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-shadow.v1"
CONFIG = "native_renderer.discovery.semantic_visibility_shadow_config"
CATEGORY = (
    "native_renderer.discovery.semantic_visibility_shadow_category_summary"
)
SUMMARY = "native_renderer.discovery.semantic_visibility_shadow_summary"
VISIBILITY_CATEGORY = (
    "native_renderer.discovery.semantic_visibility_category_summary"
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
    "result_1_records",
    "result_2_records",
    "mixed_nonzero_records",
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
            raise ValueError("requested session has no visibility-shadow config")
        return requested
    if len(sessions) != 1:
        raise ValueError("visibility-shadow input contains multiple sessions")
    return next(iter(sessions))


def static_contract(document):
    try:
        contract = document["procedural_model_receiver_lifecycle"][
            "visibility_shadow_policy"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("static visibility-shadow contract is missing") from error
    expected = {
        "record_entry_hook_address": "82E20094",
        "category_helper_result_hook_address": "82E20368",
        "title_result_hook_address": "82E206F8",
        "record_exit_hook_address": "82E2084C",
        "model": "any_nonzero_category_result_selects",
        "category_result_domain": [0, 1, 2],
        "scope": "active_title_record_only",
        "title_outcome_comparison_required": True,
        "guest_payload_read": False,
        "guest_state_changed": False,
        "control_flow_changed": False,
        "native_policy_execution": "shadow_only",
        "native_culling_enabled": False,
        "native_lod_enabled": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("static visibility-shadow contract drifted")
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
        or item["result_1_records"] > item["modelled_records"]
        or item["result_2_records"] > item["modelled_records"]
        or item["mixed_nonzero_records"] > item["result_1_records"]
        or item["mixed_nonzero_records"] > item["result_2_records"]
    ):
        raise ValueError("visibility-shadow accounting failed")


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
        "category_helper_result_hook": "82E20368",
        "title_result_hook": "82E206F8",
        "record_completion_hook": "82E2084C",
        "model": "any_nonzero_category_result_selects",
        "category_result_domain": "0,1,2",
        "outcomes": "early_rejected,rejected,selected",
        "scope": "active_title_record_only",
        "classification": "title_result_domain_shadow_selection",
        "guest_payload_read": "false",
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
        raise ValueError("visibility-shadow runtime configuration drifted")
    expected_summary = {
        "status": "complete",
        "accounting_complete": "true",
        "model": "any_nonzero_category_result_selects",
        "scope": "active_title_record_only",
        "classification": "title_result_domain_shadow_selection",
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_policy_execution": "shadow_only",
        "native_culling": "false",
        "native_lod": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("visibility-shadow summary is incomplete or unsafe")
    totals = {key: integer(summary, key) for key in COUNT_KEYS}
    unmodelled_records = integer(summary, "unmodelled_records")
    validate_counts(totals)
    if (
        totals["records"] <= 0
        or totals["modelled_records"] <= 0
        or unmodelled_records
        != totals["records"] - totals["modelled_records"]
        or totals["false_positive"]
        or totals["false_negative"]
    ):
        raise ValueError("visibility-shadow aggregate qualification failed")

    visibility = {}
    for event in selected:
        if event.get("event") != VISIBILITY_CATEGORY:
            continue
        category = integer(event, "category")
        if category in visibility or event.get("status") != "complete":
            raise ValueError("visibility category evidence drifted")
        visibility[category] = {
            outcome: integer(event, outcome) for outcome in OUTCOMES
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
            or category not in visibility
            or outcome not in OUTCOMES
            or event.get("status") != "complete"
            or event.get("native_policy_execution") != "shadow_only"
            or event.get("guest_state_changed") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("visibility-shadow category evidence drifted")
        item = {field: integer(event, field) for field in COUNT_KEYS}
        validate_counts(item)
        if (
            item["records"] != visibility[category][outcome]
            or item["false_positive"]
            or item["false_negative"]
        ):
            raise ValueError("visibility-shadow title comparison failed")
        categories[key] = item
        for field in COUNT_KEYS:
            sums[field] += item[field]
    expected_nonzero = {
        (category, outcome)
        for category, counts in visibility.items()
        for outcome, count in counts.items()
        if count
    }
    if set(categories) != expected_nonzero or any(
        sums[key] != totals[key] for key in COUNT_KEYS
    ):
        raise ValueError("visibility-shadow category totals drifted")

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
            "title_result_shadow_model_proved": True,
            "zero_title_mismatches": True,
            "modelled_records": totals["modelled_records"],
            "ready_for_independent_spatial_shadow_model": True,
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
        print(
            f"native renderer visibility shadow summary failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
