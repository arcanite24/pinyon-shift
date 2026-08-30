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
OWNER_METHOD = "native_renderer.discovery.vehicle_owner_method"
OWNER_INDIRECT_TARGET = (
    "native_renderer.discovery.vehicle_owner_indirect_target"
)
OWNER_METHOD_CANDIDATES = {
    "82BCC368": (14, "82BCCD30"),
    "82BD2DE0": (20, "82BD35B0"),
    "82BC8410": (22, "82BC86F0"),
}
OWNER_INDIRECT_CALLSITES = {
    "82BC8468",
    "82BC84A4",
    "82BC84DC",
    "82BC8688",
    "82BC86BC",
    "82BC86E4",
}


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


def hexadecimal64(mapping, key):
    value = str(mapping.get(key, "")).upper()
    if len(value) != 16:
        raise ValueError(f"invalid {key}")
    try:
        parsed = int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid {key}") from error
    if not parsed:
        raise ValueError(f"zero {key}")
    return value


def hexadecimal_words(mapping, key, expected_count):
    values = str(mapping.get(key, "")).upper().split(",")
    if len(values) != expected_count:
        raise ValueError(f"invalid {key} count")
    for value in values:
        if len(value) != 8:
            raise ValueError(f"invalid {key}")
        try:
            int(value, 16)
        except ValueError as error:
            raise ValueError(f"invalid {key}") from error
    return values


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
        "owner_vtable_method_count": "32",
        "owner_method_candidates": "82BCC368:14,82BD2DE0:20,82BC8410:22",
        "owner_method_exit_hooks": "82BCCD30,82BD35B0,82BC86F0",
        "owner_method_stack_capacity": "8",
        "owner_indirect_callsites": (
            "82BC8468,82BC84A4,82BC84DC,82BC8688,82BC86BC,82BC86E4"
        ),
        "owner_indirect_target_capacity": "64",
        "guest_payload_read": (
            "existing_title_pose_hook_values_and_bounded_owner_vtable"
        ),
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
        "owner_vtable_method_count": "32",
        "owner_method_candidates": "82BCC368:14,82BD2DE0:20,82BC8410:22",
        "owner_method_exit_hooks": "82BCCD30,82BD35B0,82BC86F0",
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
    totals["owner_method_stack_faults"] = integer(
        summary, "owner_method_stack_faults"
    )
    for key in (
        "owner_indirect_observations",
        "owner_indirect_valid_observations",
        "owner_indirect_invalid_observations",
        "owner_indirect_targets",
        "owner_indirect_target_capacity",
        "owner_indirect_target_overflow",
    ):
        totals[key] = integer(summary, key)
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
                "owner_vtable": hexadecimal(event, "owner_vtable"),
                "owner_vtable_hash": hexadecimal64(
                    event, "owner_vtable_hash"
                ),
                "owner_vtable_methods": hexadecimal_words(
                    event, "owner_vtable_methods", 32
                ),
                "owner_vtable_mismatches": integer(
                    event, "owner_vtable_mismatches"
                ),
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

    owner_classes_by_vtable = {}
    owner_class_drift = False
    for identity in identities:
        vtable = identity["owner_vtable"]
        snapshot = (
            identity["owner_vtable_hash"],
            tuple(identity["owner_vtable_methods"]),
        )
        owner_class = owner_classes_by_vtable.get(vtable)
        if owner_class is None:
            owner_classes_by_vtable[vtable] = {
                "owner_vtable": vtable,
                "owner_vtable_hash": snapshot[0],
                "owner_vtable_methods": list(snapshot[1]),
                "identity_count": 1,
            }
        else:
            owner_class["identity_count"] += 1
            if (
                owner_class["owner_vtable_hash"],
                tuple(owner_class["owner_vtable_methods"]),
            ) != snapshot:
                owner_class_drift = True
    owner_classes = sorted(
        owner_classes_by_vtable.values(), key=lambda item: item["owner_vtable"]
    )

    method_correlations = []
    method_events = [
        event for event in selected if event.get("event") == OWNER_METHOD
    ]
    if len(method_events) != len(OWNER_METHOD_CANDIDATES):
        raise ValueError("vehicle owner method coverage drifted")
    seen_methods = set()
    for event in method_events:
        method = hexadecimal(event, "method_address")
        if method in seen_methods or method not in OWNER_METHOD_CANDIDATES:
            raise ValueError("invalid vehicle owner method candidate")
        seen_methods.add(method)
        expected_slot, expected_exit = OWNER_METHOD_CANDIDATES[method]
        if (
            event.get("status") not in ("complete", "incomplete")
            or hexadecimal(event, "exit_address") != expected_exit
            or integer(event, "vtable_slot") != expected_slot
            or event.get("player_vehicle_identity_proved") != "false"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle owner method violates safety boundary")
        calls = integer(event, "calls")
        matched_owner_calls = integer(event, "matched_owner_calls")
        exits = integer(event, "exits")
        direct_draw_origins = integer(event, "direct_draw_origins")
        backend_draw_matches = integer(event, "backend_draw_matches")
        candidate_proved = backend_draw_matches > 0
        if event.get("vehicle_render_method_candidate_proved") != (
            "true" if candidate_proved else "false"
        ):
            raise ValueError("vehicle owner method qualification drifted")
        method_correlations.append(
            {
                "method_address": method,
                "exit_address": expected_exit,
                "vtable_slot": expected_slot,
                "status": event["status"],
                "calls": calls,
                "matched_owner_calls": matched_owner_calls,
                "exits": exits,
                "direct_draw_origins": direct_draw_origins,
                "backend_draw_matches": backend_draw_matches,
                "vehicle_render_method_candidate_proved": candidate_proved,
            }
        )
    method_correlations.sort(key=lambda item: item["vtable_slot"])

    indirect_targets = []
    seen_indirect_targets = set()
    for event in selected:
        if event.get("event") != OWNER_INDIRECT_TARGET:
            continue
        method = hexadecimal(event, "method_address")
        callsite = hexadecimal(event, "callsite_address")
        target = hexadecimal(event, "target_address")
        object_vtable = hexadecimal(event, "object_vtable")
        key = (method, callsite, target, object_vtable)
        if (
            key in seen_indirect_targets
            or method != "82BC8410"
            or callsite not in OWNER_INDIRECT_CALLSITES
            or event.get("classification")
            != "vehicle_owner_component_dispatch_seed"
            or event.get("vehicle_render_method_identity_proved") != "false"
            or event.get("vehicle_draw_identity_proved") != "false"
            or event.get("guest_state_changed") != "false"
            or event.get("native_draw") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("vehicle owner indirect target violates boundary")
        seen_indirect_targets.add(key)
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if first_frame > last_frame:
            raise ValueError("invalid vehicle indirect target frame range")
        indirect_targets.append(
            {
                "method_address": method,
                "callsite_address": callsite,
                "target_address": target,
                "object_address": hexadecimal(event, "object_address"),
                "object_vtable": object_vtable,
                "observations": integer(event, "observations"),
                "first_frame": first_frame,
                "last_frame": last_frame,
            }
        )
    indirect_targets.sort(
        key=lambda item: (
            item["callsite_address"],
            item["target_address"],
            item["object_vtable"],
        )
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
    if any(item["owner_vtable_mismatches"] for item in identities):
        failures.append("vehicle owner vtable changed")
    if owner_class_drift:
        failures.append("vehicle owner vtable snapshot drifted")
    if not owner_classes:
        failures.append("no vehicle owner class seed")
    if totals["owner_method_stack_faults"]:
        failures.append("vehicle owner method stack faulted")
    if totals["owner_indirect_observations"] != (
        totals["owner_indirect_valid_observations"]
        + totals["owner_indirect_invalid_observations"]
    ):
        failures.append("vehicle owner indirect accounting drifted")
    if totals["owner_indirect_invalid_observations"]:
        failures.append("invalid vehicle owner indirect observations occurred")
    if totals["owner_indirect_target_overflow"]:
        failures.append("vehicle owner indirect target table overflowed")
    if len(indirect_targets) != totals["owner_indirect_targets"]:
        failures.append("vehicle owner indirect target coverage drifted")
    if sum(item["observations"] for item in indirect_targets) != totals[
        "owner_indirect_valid_observations"
    ]:
        failures.append("vehicle owner indirect target totals drifted")
    for method in method_correlations:
        if method["status"] != "complete" or method["calls"] != method["exits"]:
            failures.append(
                f"vehicle owner method {method['method_address']} was unbalanced"
            )
        if method["matched_owner_calls"] > method["calls"]:
            failures.append(
                f"vehicle owner method {method['method_address']} owner accounting drifted"
            )
        if method["backend_draw_matches"] > method["direct_draw_origins"]:
            failures.append(
                f"vehicle owner method {method['method_address']} draw accounting drifted"
            )

    render_candidate_proved = any(
        item["vehicle_render_method_candidate_proved"]
        for item in method_correlations
    )

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "totals": totals,
        "identities": identities,
        "owner_classes": owner_classes,
        "method_correlations": method_correlations,
        "indirect_targets": indirect_targets,
        "qualification": {
            "vehicle_instance_semantic_seed_proved": not failures,
            "vehicle_owner_class_seed_proved": not failures,
            "vehicle_render_method_candidate_proved": (
                not failures and render_candidate_proved
            ),
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
