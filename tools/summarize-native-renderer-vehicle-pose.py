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
    expected_config = {
        "status": "armed",
        "hook": "82BC5A3C",
        "identity": "title_generation,source,owner,active_slot",
        "transform": "exact_active_slot_position_and_forward",
        "capacity": "64",
        "summary_limit": "64",
        "classification": "unclassified_vehicle_pose_stream",
        "player_priority_admitted": "false",
        "guest_payload_read": "existing_title_pose_hook_values",
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("vehicle-pose configuration drifted")
    expected_summary = {
        "status": "complete",
        "accounting_complete": "true",
        "identity": "title_generation,source,owner,active_slot",
        "transform": "exact_active_slot_position_and_forward",
        "classification": "vehicle_instance_semantic_seed",
        "player_priority_admitted": "false",
        "capacity": "64",
        "summary_limit": "64",
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("vehicle-pose summary drifted")

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

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "totals": totals,
        "identities": identities,
        "qualification": {
            "vehicle_instance_semantic_seed_proved": not failures,
            "player_vehicle_identity_proved": False,
            "vehicle_draw_identity_proved": False,
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
