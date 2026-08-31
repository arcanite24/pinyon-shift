#!/usr/bin/env python3
"""Qualify SimpleModel renderer scopes joined to prepared PM4 draws."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-runtime-join.v1"
STATIC_SCHEMA = "pinyon-shift.native-renderer-static-world-ingress.v1"
CONFIG = "native_renderer.discovery.static_world_runtime_join_config"
SUMMARY = "native_renderer.discovery.static_world_runtime_join_summary"
CHECKPOINT = "native_renderer.discovery.static_world_runtime_join_checkpoint"


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
            raise ValueError("requested session has no static-world join config")
        return requested
    if len(sessions) != 1:
        raise ValueError("static-world join input contains multiple sessions")
    return next(iter(sessions))


def select_runtime_evidence(events, allow_checkpoint):
    summaries = [event for event in events if event.get("event") == SUMMARY]
    if len(summaries) > 1:
        raise ValueError(f"expected at most one {SUMMARY} event")
    if summaries:
        return summaries[0], True
    if not allow_checkpoint:
        raise ValueError(f"expected exactly one {SUMMARY} event")
    checkpoints = [
        event for event in events if event.get("event") == CHECKPOINT
    ]
    if not checkpoints:
        raise ValueError("no static-world runtime summary or checkpoint")
    return max(
        checkpoints, key=lambda event: integer(event, "frame_sequence")
    ), False


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
        raise ValueError("static-world join violates its safety boundary")


def validate_static_ingress(document):
    if (
        document.get("schema") != STATIC_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "title_simple_model_static_world_ingress_proved"
    ):
        raise ValueError("static-world ingress proof drifted")
    try:
        model_renderer = document["classes"]["simple_model_renderer"]
        primary = next(
            surface
            for surface in model_renderer["surfaces"]
            if surface.get("label") == "primary"
        )
    except (KeyError, StopIteration, TypeError) as error:
        raise ValueError("static-world renderer surface is missing") from error
    slot_targets = primary.get("slot_targets")
    if (
        model_renderer.get("decorated_name") != ".?AVCSimpleModelRenderer@@"
        or primary.get("vtable_address") != "82001B64"
        or primary.get("vtable_slot_count") != 17
        or not isinstance(slot_targets, list)
        or len(slot_targets) != 17
        or slot_targets[12] != "82C4CCC8"
    ):
        raise ValueError("static-world renderer dispatch proof drifted")


def build(static_ingress, events, requested_session=None, allow_checkpoint=False):
    validate_static_ingress(static_ingress)
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary, final_summary = select_runtime_evidence(
        selected, allow_checkpoint
    )
    expected_config = {
        "status": "armed",
        "class": "CSimpleModelRenderer",
        "vtable": "82001B64",
        "vtable_slot": "12",
        "dispatch": "82C4CCC8",
        "entry_hook": "82C4CCC8",
        "exit_hook": "82C4DEA0",
        "model_graph_field": "renderer_plus_72",
        "draw_emitter": "82416380",
        "packet_hooks": "82416260,824162F4",
        "join": "synchronous_scope_to_physical_pm4_prepared_draw",
        "guest_payload_read": "two_host_mapped_u32_fields_per_scope",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("static-world runtime configuration drifted")
    require_safety(config)
    require_safety(summary)
    expected_kinds = (
        ("complete", "incomplete", "not_observed")
        if final_summary
        else (
            "checkpoint_complete",
            "checkpoint_incomplete",
            "checkpoint_not_observed",
        )
    )
    if (
        summary.get("status") not in expected_kinds
        or summary.get("checkpoint_kind")
        != ("final" if final_summary else "periodic")
        or summary.get("classification")
        != "exact_simple_model_renderer_scope_to_pm4_prepared_draw"
    ):
        raise ValueError("static-world runtime summary drifted")

    keys = (
        "scope_entries",
        "scope_exits",
        "exact_scopes",
        "invalid_root",
        "vtable_mismatches",
        "invalid_graph_field",
        "scopes_with_packets",
        "scopes_without_packets",
        "packets_recorded",
        "packet_matches",
        "pending_packets",
        "prepared_matches",
        "unprepared_matches",
        "scope_overlaps",
        "exit_without_entry",
    )
    totals = {key: integer(summary, key) for key in keys}
    frame_sequence = integer(summary, "frame_sequence")
    failures = []
    classified = (
        totals["exact_scopes"]
        + totals["invalid_root"]
        + totals["vtable_mismatches"]
        + totals["invalid_graph_field"]
    )
    if summary.get("accounting_complete") != "true":
        failures.append("runtime accounting is incomplete")
    if totals["scope_entries"] != totals["scope_exits"]:
        failures.append("static-world scope entry/exit accounting drifted")
    if totals["scope_entries"] != classified:
        failures.append("static-world scope classification drifted")
    if totals["exact_scopes"] != (
        totals["scopes_with_packets"] + totals["scopes_without_packets"]
    ):
        failures.append("static-world scope outcome accounting drifted")
    if not totals["exact_scopes"]:
        failures.append("no exact SimpleModel renderer scope was observed")
    if not totals["scopes_with_packets"] or not totals["packets_recorded"]:
        failures.append("no exact scope emitted a PM4 draw packet")
    if totals["packet_matches"] + totals["pending_packets"] != totals[
        "packets_recorded"
    ]:
        failures.append("static-world packet outcome accounting drifted")
    if totals["packet_matches"] != (
        totals["prepared_matches"] + totals["unprepared_matches"]
    ):
        failures.append("static-world prepared accounting drifted")
    if not totals["prepared_matches"]:
        failures.append("no static-world PM4 packet joined a prepared draw")
    for key in (
        "invalid_root",
        "vtable_mismatches",
        "invalid_graph_field",
        "unprepared_matches",
        "scope_overlaps",
        "exit_without_entry",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
    expected_status = (
        "complete" if not failures else "incomplete"
    ) if final_summary else (
        "checkpoint_complete" if not failures else "checkpoint_incomplete"
    )
    if summary.get("status") != expected_status:
        failures.append("runtime status does not match qualification outcome")
    if summary.get("qualification_complete") != (
        "true" if not failures else "false"
    ):
        failures.append("runtime qualification flag does not match outcome")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": expected_status,
        "evidence": {
            "kind": "final_summary" if final_summary else "periodic_checkpoint",
            "frame_sequence": frame_sequence,
            "session_exit_proved": final_summary,
            "native_admission_evidence": False,
        },
        "failures": failures,
        "totals": totals,
        "qualification": {
            "simple_model_renderer_scope_proved": not failures,
            "static_world_scope_to_pm4_proved": not failures,
            "static_world_pm4_to_prepared_draw_proved": not failures,
            "building_or_prop_instance_identity_proved": False,
            "streaming_lifetime_proved": False,
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
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--allow-checkpoint", action="store_true")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(
            json.loads(args.static.read_text(encoding="utf-8")),
            read_events(args.events),
            args.session,
            args.allow_checkpoint,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if document["status"] not in ("complete", "checkpoint_complete"):
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"static-world runtime join failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
