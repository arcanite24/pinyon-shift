#!/usr/bin/env python3
"""Qualify the native visibility workset and semantic-instance handoff."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-workset.v2"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
CONFIG = "native_renderer.discovery.semantic_visibility_workset_config"
ENTRY = "native_renderer.discovery.semantic_visibility_workset_entry"
SUMMARY = "native_renderer.discovery.semantic_visibility_workset_summary"
ASSEMBLY = (
    "native_renderer.discovery.semantic_visibility_assembly_shadow_summary"
)
SEMANTIC_INSTANCES = "native_renderer.discovery.semantic_instance_summary"


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


def hexadecimal(mapping, key, width):
    value = str(mapping.get(key, "")).upper()
    if len(value) != width:
        raise ValueError(f"invalid {key}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid {key}") from error
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
            raise ValueError("requested session has no visibility-workset config")
        return requested
    if len(sessions) != 1:
        raise ValueError("visibility-workset input contains multiple sessions")
    return next(iter(sessions))


def static_contract(document):
    if document.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    try:
        contract = document["procedural_model_receiver_lifecycle"][
            "visibility_policy_workset"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("static visibility-workset contract is missing") from error
    expected = {
        "record_completion_hook_address": "82E2084C",
        "title_lod_write_hook_addresses": ["82E205E4", "82E206DC"],
        "semantic_instance_hook_address": "8241741C",
        "capacity": 4096,
        "model": "independent_policy_to_semantic_candidate_handoff",
        "identity": "receiver_generation_record_index",
        "title_lod_lineage": "latest_exact_title_record_observation",
        "selection_rule": "any_nonzero_predicted_category_result_selects",
        "execution": "bounded_host_visibility_workset",
        "guest_payload_read": "qualified_policy_inputs_only",
        "guest_state_changed": False,
        "control_flow_changed": False,
        "title_culling_changed": False,
        "native_lod_enabled": False,
        "native_draw_enabled": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("static visibility-workset contract drifted")
    return contract


def require_safety(event, *, entry=False):
    expected = {
        "execution": "bounded_host_visibility_workset",
        "guest_state_changed": "false",
        "title_culling_changed": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if not entry:
        expected.update(
            {
                "control_flow_changed": "false",
                "native_lod": "false",
            }
        )
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("visibility-workset evidence violates the safety boundary")


def build(events, static, requested_session=None):
    contract = static_contract(static)
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary = exact_event(selected, SUMMARY)
    assembly = exact_event(selected, ASSEMBLY)
    semantic_instances = exact_event(selected, SEMANTIC_INSTANCES)
    expected_config = {
        "status": "armed",
        "class": "proceduralGeometry::CProceduralModels",
        "record_completion_hook": "82E2084C",
        "title_lod_write_hooks": "82E205E4,82E206DC",
        "semantic_instance_hook": "8241741C",
        "capacity": "4096",
        "model": "independent_policy_to_semantic_candidate_handoff",
        "identity": "receiver_generation_record_index",
        "title_lod_lineage": "latest_exact_title_record_observation",
        "selection_rule": "any_nonzero_predicted_category_result_selects",
        "execution": "bounded_host_visibility_workset",
        "guest_payload_read": "qualified_policy_inputs_only",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "title_culling_changed": "false",
        "native_lod": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("visibility-workset runtime configuration drifted")
    require_safety(summary)
    if (
        summary.get("status") != "complete"
        or summary.get("accounting_complete") != "true"
        or summary.get("model")
        != "independent_policy_to_semantic_candidate_handoff"
        or summary.get("identity") != "receiver_generation_record_index"
        or summary.get("title_lod_lineage")
        != "latest_exact_title_record_observation"
    ):
        raise ValueError("visibility-workset summary is incomplete")

    count_keys = (
        "modelled_records",
        "predicted_selected",
        "predicted_rejected",
        "title_matches",
        "title_mismatches",
        "invalid_records",
        "entries",
        "entry_observations",
        "title_lod_records",
        "entry_title_lod_observations",
        "capacity",
        "overflow",
        "semantic_instance_lookups",
        "selected_joins",
        "rejected_joins",
        "missing_joins",
    )
    totals = {key: integer(summary, key) for key in count_keys}
    entries = []
    seen_keys = set()
    seen_identities = set()
    sums = {
        "observations": 0,
        "predicted_selected": 0,
        "predicted_rejected": 0,
        "title_matches": 0,
        "title_mismatches": 0,
        "semantic_instance_joins": 0,
        "title_lod_observations": 0,
    }
    for event in selected:
        if event.get("event") != ENTRY:
            continue
        require_safety(event, entry=True)
        key = hexadecimal(event, "key", 16)
        identity = (
            hexadecimal(event, "receiver_address", 8),
            integer(event, "receiver_generation"),
            integer(event, "record_index"),
        )
        item = {
            field: integer(event, field)
            for field in (
                "observations",
                "predicted_selected",
                "predicted_rejected",
                "title_matches",
                "title_mismatches",
                "semantic_instance_joins",
                "title_lod_observations",
            )
        }
        latest_title_lod_valid = event.get("latest_title_lod_valid") == "true"
        if (
            event.get("status") != "complete"
            or key in seen_keys
            or identity in seen_identities
            or not item["observations"]
            or item["observations"]
            != item["predicted_selected"] + item["predicted_rejected"]
            or item["observations"]
            != item["title_matches"] + item["title_mismatches"]
            or integer(event, "first_frame") > integer(event, "last_frame")
            or integer(event, "latest_category_result_mask") > 7
            or event.get("latest_selected") not in ("true", "false")
            or event.get("latest_title_lod_valid") not in ("true", "false")
            or event.get("title_lod_lineage")
            != "latest_exact_title_record_observation"
            or item["title_lod_observations"] > item["observations"]
            or (
                latest_title_lod_valid
                and integer(event, "latest_title_lod_index") >= 32
            )
        ):
            raise ValueError("visibility-workset entry evidence drifted")
        seen_keys.add(key)
        seen_identities.add(identity)
        entries.append(
            {
                "key": key,
                "identity": identity,
                "latest_title_lod_index": integer(
                    event, "latest_title_lod_index"
                ),
                "latest_title_lod_valid": latest_title_lod_valid,
                **item,
            }
        )
        for field in sums:
            sums[field] += item[field]

    assembly_totals = {
        key: integer(assembly, key)
        for key in (
            "modelled_records",
            "predicted_selected",
            "predicted_rejected",
            "title_matches",
            "false_positive",
            "false_negative",
            "invalid_inputs",
        )
    }
    semantic_live = integer(semantic_instances, "live_observations")
    failures = []
    if totals["modelled_records"] <= 0 or totals["selected_joins"] <= 0:
        failures.append("visibility workset did not exercise policy handoff")
    if totals["predicted_selected"] + totals["predicted_rejected"] != totals["modelled_records"]:
        failures.append("policy decision accounting drifted")
    if totals["title_matches"] + totals["title_mismatches"] != totals["modelled_records"]:
        failures.append("title comparison accounting drifted")
    if totals["semantic_instance_lookups"] != totals["selected_joins"] + totals["rejected_joins"] + totals["missing_joins"]:
        failures.append("semantic-instance join accounting drifted")
    if totals["entries"] != len(entries) or totals["capacity"] != 4096:
        failures.append("workset capacity accounting drifted")
    for field in sums:
        summary_field = "entry_observations" if field == "observations" else field
        if field == "semantic_instance_joins":
            expected = totals["selected_joins"] + totals["rejected_joins"]
        elif field == "title_lod_observations":
            expected = totals["entry_title_lod_observations"]
        else:
            expected = totals[summary_field]
        if sums[field] != expected:
            failures.append(f"entry {field} totals drifted")
    if totals["entry_observations"] + totals["overflow"] != totals["modelled_records"]:
        failures.append("workset observation accounting drifted")
    if totals["title_lod_records"] != totals["entry_title_lod_observations"]:
        failures.append("title LOD lineage accounting drifted")
    if semantic_live != totals["semantic_instance_lookups"]:
        failures.append("semantic-instance summary did not reconcile")
    if (
        assembly_totals["modelled_records"] != totals["modelled_records"]
        or assembly_totals["predicted_selected"] != totals["predicted_selected"]
        or assembly_totals["predicted_rejected"] != totals["predicted_rejected"]
        or assembly_totals["title_matches"] != totals["title_matches"]
        or assembly_totals["false_positive"] + assembly_totals["false_negative"]
        != totals["title_mismatches"]
    ):
        failures.append("assembled policy did not reconcile with workset")
    for key in (
        "title_mismatches",
        "invalid_records",
        "overflow",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
    if assembly_totals["invalid_inputs"]:
        failures.append("assembled policy contains invalid inputs")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "static_contract": contract,
        "totals": totals,
        "entries": entries,
        "qualification": {
            "independent_policy_materialized": not failures,
            "semantic_candidate_handoff_proved": not failures,
            "superset_filter_accounting_proved": not failures,
            "native_draw_enabled": False,
            "title_culling_changed": False,
        },
        "safety": {
            "guest_state_changed": False,
            "control_flow_changed": False,
            "title_culling_changed": False,
            "native_lod": False,
            "native_draw": False,
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
        if document["status"] != "complete":
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"native renderer visibility workset summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
