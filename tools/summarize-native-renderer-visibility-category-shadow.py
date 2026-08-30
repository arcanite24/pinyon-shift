#!/usr/bin/env python3
"""Qualify the independent six-plane category-classifier mirror."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-category-shadow.v1"
CONFIG = "native_renderer.discovery.semantic_visibility_category_shadow_config"
CATEGORY = (
    "native_renderer.discovery."
    "semantic_visibility_category_shadow_category_summary"
)
SUMMARY = "native_renderer.discovery.semantic_visibility_category_shadow_summary"
ORACLE_CATEGORY = (
    "native_renderer.discovery.semantic_visibility_oracle_category_summary"
)
OUTCOMES = ("early_rejected", "rejected", "selected")
COUNT_KEYS = (
    "records",
    "input_observations",
    "comparisons",
    "matches",
    "false_result",
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
            raise ValueError("requested session has no category-shadow config")
        return requested
    if len(sessions) != 1:
        raise ValueError("category-shadow input contains multiple sessions")
    return next(iter(sessions))


def static_contract(document):
    try:
        contract = document["procedural_model_receiver_lifecycle"][
            "visibility_category_shadow"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("static category-shadow contract is missing") from error
    expected = {
        "input_hook_address": "82E20364",
        "result_hook_address": "82E20368",
        "helper_address": "82441048",
        "plane_vector_offsets": [0, 16, 32, 48, 64, 80],
        "plane_vector_count": 6,
        "endpoint_registers": ["v1", "v2"],
        "axis_signs": [1, 1, -1],
        "support_rule": "plane_axis_nonnegative_selects_v2_for_positive",
        "positive_comparison": "greater_equal_zero_sets_intersection_bit",
        "negative_comparison": "greater_zero_sets_outside_bits",
        "result_mapping": "bits_3_to_0_bits_1_to_1_other_to_2",
        "bounded_guest_payload_bytes": 96,
        "scope": "active_title_record_only",
        "title_result_comparison_required": True,
        "guest_payload_read": "bounded_category_planes",
        "guest_state_changed": False,
        "control_flow_changed": False,
        "native_policy_execution": "shadow_only",
        "native_culling_enabled": False,
        "native_lod_enabled": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("static category-shadow contract drifted")
    return contract


def validate_counts(item):
    if (
        item["comparisons"] != item["input_observations"]
        or item["matches"] + item["false_result"] != item["comparisons"]
        or item["false_result"]
        or item["invalid_inputs"]
    ):
        raise ValueError("category-shadow comparison failed")


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
        "input_hook": "82E20364",
        "result_hook": "82E20368",
        "helper": "82441048",
        "plane_vector_offsets": "0,16,32,48,64,80",
        "plane_vector_count": "6",
        "endpoint_registers": "v1,v2",
        "axis_signs": "1,1,-1",
        "support_rule": "plane_axis_nonnegative_selects_v2_for_positive",
        "positive_comparison": "greater_equal_zero_sets_intersection_bit",
        "negative_comparison": "greater_zero_sets_outside_bits",
        "result_mapping": "bits_3_to_0_bits_1_to_1_other_to_2",
        "bounded_guest_payload_bytes": "96",
        "scope": "active_title_record_only",
        "classification": "independent_category_helper_shadow",
        "guest_payload_read": "bounded_category_planes",
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
        raise ValueError("category-shadow runtime configuration drifted")
    expected_summary = {
        "status": "complete",
        "accounting_complete": "true",
        "model": "six_plane_support_point_classifier",
        "scope": "active_title_record_only",
        "unscoped_continuations_excluded": "true",
        "classification": "independent_category_helper_shadow",
        "guest_payload_read": "bounded_category_planes",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_policy_execution": "shadow_only",
        "native_culling": "false",
        "native_lod": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("category-shadow summary is incomplete or unsafe")
    totals = {key: integer(summary, key) for key in COUNT_KEYS}
    diagnostics = {
        "input_without_record": integer(summary, "input_without_record"),
        "result_without_input": integer(summary, "result_without_input"),
    }
    validate_counts(totals)
    if totals["records"] <= 0 or totals["comparisons"] <= 0:
        raise ValueError("category-shadow has no qualifying comparisons")

    oracle = {}
    for event in selected:
        if event.get("event") != ORACLE_CATEGORY:
            continue
        key = (integer(event, "category"), event.get("outcome"))
        if (
            key in oracle
            or key[1] not in OUTCOMES
            or event.get("status") != "complete"
        ):
            raise ValueError("visibility-oracle category evidence drifted")
        oracle[key] = {
            "records": integer(event, "records"),
            "input_observations": integer(event, "category_helper_observations"),
        }

    categories = {}
    sums = {key: 0 for key in COUNT_KEYS}
    for event in selected:
        if event.get("event") != CATEGORY:
            continue
        key = (integer(event, "category"), event.get("outcome"))
        if (
            key in categories
            or key not in oracle
            or event.get("status") != "complete"
            or event.get("native_policy_execution") != "shadow_only"
            or event.get("guest_payload_read") != "bounded_category_planes"
            or event.get("guest_state_changed") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("category-shadow category evidence drifted")
        item = {field: integer(event, field) for field in COUNT_KEYS}
        validate_counts(item)
        if item["records"] != oracle[key]["records"] or item[
            "input_observations"
        ] != oracle[key]["input_observations"]:
            raise ValueError("category-shadow oracle reconciliation failed")
        categories[key] = item
        for field in COUNT_KEYS:
            sums[field] += item[field]
    if set(categories) != set(oracle) or any(
        sums[key] != totals[key] for key in COUNT_KEYS
    ):
        raise ValueError("category-shadow category totals drifted")

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
            "independent_category_classifier_shadow_proved": True,
            "zero_title_mismatches": True,
            "bounded_plane_reads_proved": True,
            "ready_for_native_visibility_policy_assembly": True,
            "native_policy_execution_enabled": False,
        },
        "safety": {
            "guest_payload_read": "bounded_category_planes",
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
            f"native renderer category shadow summary failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
