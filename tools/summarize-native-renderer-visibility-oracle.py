#!/usr/bin/env python3
"""Qualify the ordered passive title visibility-helper trace."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-oracle.v1"
CONFIG = "native_renderer.discovery.semantic_visibility_oracle_config"
CATEGORY = (
    "native_renderer.discovery.semantic_visibility_oracle_category_summary"
)
SUMMARY = "native_renderer.discovery.semantic_visibility_oracle_summary"
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
            raise ValueError("requested session has no visibility-oracle config")
        return requested
    if len(sessions) != 1:
        raise ValueError("visibility-oracle input contains multiple sessions")
    return next(iter(sessions))


def static_contract(document):
    try:
        contract = document["procedural_model_receiver_lifecycle"][
            "visibility_policy_inputs"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("static visibility-policy contract is missing") from error
    expected = {
        "spatial_helper_address": "8243F9A0",
        "category_helper_address": "82441048",
        "spatial_helper_result_hook_address": "82E20350",
        "category_helper_result_hook_address": "82E20368",
        "helper_result_capture": "ordered_per_record_return_trace",
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
        raise ValueError("static visibility-oracle contract drifted")
    if contract.get("category_helper_contract", {}).get("return_domain") != [
        0,
        1,
        2,
    ]:
        raise ValueError("static category-helper return domain drifted")
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
        "spatial_helper": "8243F9A0",
        "spatial_helper_result_hook": "82E20350",
        "category_helper": "82441048",
        "category_helper_result_hook": "82E20368",
        "category_result_domain": "0,1,2",
        "outcomes": "early_rejected,rejected,selected",
        "classification": "title_ordered_visibility_helper_oracle",
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
        raise ValueError("visibility-oracle runtime configuration drifted")

    expected_summary = {
        "status": "complete",
        "accounting_complete": "true",
        "classification": "title_ordered_visibility_helper_oracle",
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
        raise ValueError("visibility-oracle summary is incomplete or unsafe")
    count_keys = (
        "records",
        "spatial_helper_observations",
        "spatial_helper_passes",
        "category_helper_observations",
        "category_result_0",
        "category_result_1",
        "category_result_2",
    )
    fault_keys = (
        "spatial_helper_without_record",
        "category_helper_without_record",
        "category_helper_without_spatial_pass",
        "category_helper_invalid_result",
    )
    totals = {key: integer(summary, key) for key in count_keys + fault_keys}
    if (
        totals["records"] <= 0
        or totals["category_helper_observations"]
        != sum(totals[f"category_result_{value}"] for value in range(3))
        or totals["category_helper_observations"]
        > totals["spatial_helper_passes"]
        or totals["spatial_helper_passes"]
        > totals["spatial_helper_observations"]
        or any(totals[key] for key in fault_keys)
    ):
        raise ValueError("visibility-oracle aggregate accounting failed")

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
    sums = {key: 0 for key in count_keys}
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
            raise ValueError("visibility-oracle category evidence drifted")
        item = {field: integer(event, field) for field in count_keys}
        if (
            item["records"] != visibility[category][outcome]
            or item["category_helper_observations"]
            != sum(item[f"category_result_{value}"] for value in range(3))
            or item["category_helper_observations"]
            > item["spatial_helper_passes"]
            or item["spatial_helper_passes"]
            > item["spatial_helper_observations"]
        ):
            raise ValueError("visibility-oracle category accounting failed")
        categories[key] = item
        for field in count_keys:
            sums[field] += item[field]
    expected_nonzero = {
        (category, outcome)
        for category, counts in visibility.items()
        for outcome, count in counts.items()
        if count
    }
    if set(categories) != expected_nonzero or any(
        sums[key] != totals[key] for key in count_keys
    ):
        raise ValueError("visibility-oracle category totals drifted")

    selected_helper_passes = sum(
        item["category_result_1"] + item["category_result_2"]
        for (category, outcome), item in categories.items()
        if outcome == "selected"
    )
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
        "qualification": {
            "ordered_helper_trace_proved": True,
            "title_helper_result_domain_proved": True,
            "selected_nonzero_helper_results": selected_helper_passes,
            "ready_for_shadow_policy_modeling": selected_helper_passes > 0,
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
        print(f"native renderer visibility oracle summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
