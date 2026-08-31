#!/usr/bin/env python3
"""Qualify unified track render-model scopes joined to semantic submissions."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-track-model-runtime-join.v1"
CONFIG = "native_renderer.discovery.track_render_model_runtime_join_config"
SUMMARY = "native_renderer.discovery.track_render_model_runtime_join_summary"

RELATIONS = (
    "shared_descriptor",
    "shared_descriptor_payload_bound_resource",
    "shared_descriptor_payload_provider",
    "shared_descriptor_payload_runtime_object",
    "shared_root_receiver",
    "shared_child_receiver",
    "shared_root_runtime_object",
    "shared_child_runtime_object",
)


def integer(mapping, key):
    try:
        value = int(mapping[key])
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


def read_events(paths):
    events = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def select_session(events, requested):
    sessions = {
        event.get("session") for event in events if event.get("event") == CONFIG
    }
    sessions.discard(None)
    if requested:
        if requested not in sessions:
            raise ValueError("requested session has no track-model join config")
        return requested
    if len(sessions) != 1:
        raise ValueError("track-model join input contains multiple sessions")
    return next(iter(sessions))


def require_safety(event):
    expected = {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("track-model join violates its safety boundary")


def build(events, requested_session=None):
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary = exact_event(selected, SUMMARY)
    expected_config = {
        "status": "armed",
        "entry_hook": "8240EC80",
        "exit_hook": "8240ECAC",
        "nested_dispatch": "82436468",
        "instance_vtable": "820019CC",
        "model_vtable": "82001D74",
        "instance_to_model": "root_plus_4",
        "model_to_descriptor": "child_plus_48_then_plus_128",
        "descriptor_type": "21",
        "descriptor_flag": "1",
        "join": "synchronous_scope_to_procedural_model_submission",
        "shared_identity": "descriptor_payload_or_object_address_exact_equality",
        "guest_payload_read": "bounded_308_bytes_per_scope",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("track-model runtime configuration drifted")
    require_safety(config)
    require_safety(summary)
    if (
        summary.get("status") not in ("complete", "incomplete", "not_observed")
        or summary.get("classification")
        != "exact_unified_track_render_model_nested_submission_join"
    ):
        raise ValueError("track-model runtime summary drifted")

    keys = (
        "scope_entries",
        "scope_exits",
        "exact_scopes",
        "invalid_root",
        "invalid_child",
        "invalid_descriptor",
        "contract_mismatches",
        "joined_scopes",
        "unjoined_scopes",
        "submission_joins",
        "shared_identity_joins",
        "scope_overlaps",
        "exit_without_entry",
        *RELATIONS,
    )
    totals = {key: integer(summary, key) for key in keys}
    failures = []
    classified = (
        totals["exact_scopes"]
        + totals["invalid_root"]
        + totals["invalid_child"]
        + totals["invalid_descriptor"]
        + totals["contract_mismatches"]
    )
    if summary.get("accounting_complete") != "true":
        failures.append("runtime accounting is incomplete")
    if totals["scope_entries"] != totals["scope_exits"]:
        failures.append("track-model scope entry/exit accounting drifted")
    if totals["scope_entries"] != classified:
        failures.append("track-model scope classification drifted")
    if totals["exact_scopes"] != (
        totals["joined_scopes"] + totals["unjoined_scopes"]
    ):
        failures.append("exact scope outcome accounting drifted")
    if not totals["exact_scopes"]:
        failures.append("no exact unified track render-model scope was observed")
    if not totals["joined_scopes"] or not totals["submission_joins"]:
        failures.append("no exact scope joined a procedural-model submission")
    for key in (
        "invalid_root",
        "invalid_child",
        "invalid_descriptor",
        "contract_mismatches",
        "scope_overlaps",
        "exit_without_entry",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
    if totals["shared_identity_joins"] > totals["submission_joins"]:
        failures.append("shared identity joins exceed submission joins")
    if totals["shared_identity_joins"] and not any(
        totals[key] for key in RELATIONS
    ):
        failures.append("shared identity relation accounting is empty")
    expected_status = "complete" if not failures else "incomplete"
    if summary.get("status") != expected_status:
        failures.append("runtime status does not match qualification outcome")
    if summary.get("qualification_complete") != (
        "true" if not failures else "false"
    ):
        failures.append("runtime qualification flag does not match outcome")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "totals": totals,
        "shared_identity_relations": {
            key: totals[key] for key in RELATIONS
        },
        "qualification": {
            "track_render_model_scope_to_submission_proved": not failures,
            "shared_object_or_resource_identity_proved": (
                not failures and totals["shared_identity_joins"] > 0
            ),
            "terrain_or_road_visual_identity_proved": False,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "guest_state_changed": False,
            "control_flow_changed": False,
            "native_admission": False,
            "native_draw": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
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
        print(f"native renderer track-model join failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
