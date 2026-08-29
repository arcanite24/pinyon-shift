"""Correlate bounded title graphics-wrapper telemetry with static call sites."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-dispatch-runtime.v3"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
PREFIX = "native_renderer.discovery.dispatch_"


def read_events(paths: list[pathlib.Path]) -> list[dict]:
    events = []
    for path in paths:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if str(event.get("event", "")).startswith(PREFIX):
                events.append(event)
    return events


def select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"dispatch discovery session not found: {requested}")
        return requested
    armed = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == f"{PREFIX}config"
        and event.get("status") == "armed"
    ]
    if not armed or not armed[-1]:
        raise ValueError("no armed dispatch discovery session found")
    return armed[-1]


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    session = select_session(events, requested)
    selected = [event for event in events if event.get("session") == session]
    configs = [
        event
        for event in selected
        if event.get("event") == f"{PREFIX}config"
        and event.get("status") == "armed"
    ]
    if len(configs) != 1:
        raise ValueError("dispatch session must contain exactly one armed config")
    scene = str(configs[0].get("scene", "unmarked"))
    summaries = [
        event for event in selected if event.get("event") == f"{PREFIX}summary"
    ]
    if len(summaries) != 1:
        raise ValueError("dispatch session must contain exactly one summary")
    summary = summaries[0]
    required_safety = {
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(str(summary.get(key)).lower() != value for key, value in required_safety.items()):
        raise ValueError("dispatch summary does not prove the read-only safety boundary")

    static_calls = {
        (item["wrapper"], item["return_address"]): item
        for item in static.get(
            "runtime_correlation_calls", static.get("direct_calls", [])
        )
    }
    callers = []
    for event in selected:
        if event.get("event") != f"{PREFIX}caller":
            continue
        wrapper = str(event.get("wrapper_address", "")).upper()
        caller = str(event.get("caller", "")).upper()
        callsite = static_calls.get((wrapper, caller))
        callers.append(
            {
                "wrapper": str(event.get("wrapper", "unknown")),
                "wrapper_address": wrapper,
                "caller": caller,
                "calls": int(event.get("calls", 0)),
                "first_frame": int(event.get("first_frame", 0)),
                "first_arguments": {
                    f"r{index}": str(
                        event.get(f"first_r{index}", "")
                    ).upper()
                    for index in range(3, 11)
                },
                "static_match": (
                    {
                        "caller_function": callsite["caller_function"],
                        "caller_function_address": callsite[
                            "caller_function_address"
                        ],
                        "callsite": callsite["callsite"],
                        "wrapper_layer": callsite.get(
                            "wrapper_layer", "unknown"
                        ),
                        "dispatch_edge": callsite.get(
                            "dispatch_edge", "direct"
                        ),
                        "forwarder_function": callsite.get(
                            "forwarder_function"
                        ),
                    }
                    if callsite
                    else None
                ),
                "semantic_identity": "unknown",
                "suppression_eligible": False,
            }
        )
    callers.sort(key=lambda item: (-item["calls"], item["wrapper"], item["caller"]))
    observed_calls = sum(item["calls"] for item in callers)
    observed_callers = len(callers)
    if observed_calls != int(summary.get("tracked_calls", 0)):
        raise ValueError("dispatch caller counts do not match the runtime summary")
    if observed_callers != int(summary.get("tracked_callers", 0)):
        raise ValueError("dispatch caller cardinality does not match the runtime summary")
    return {
        "schema": SCHEMA,
        "session": session,
        "scene": scene,
        "frames_observed": max(
            (int(event.get("frame_sequence", 0)) for event in selected),
            default=0,
        ),
        "callers": callers,
        "totals": {
            "tracked_callers": observed_callers,
            "tracked_calls": observed_calls,
            "static_matches": sum(
                item["static_match"] is not None for item in callers
            ),
            "unknown_callers": sum(
                item["static_match"] is None for item in callers
            ),
            "overflow_calls": int(summary.get("overflow_calls", 0)),
        },
        "resolve_boundary": static.get("resolve_boundary"),
        "query_owner_lifecycle": static.get("query_owner_lifecycle"),
        "side_effect_packets": static.get("side_effect_packets"),
        "qualification": (
            "wrapper_layer_side_effect_boundary_and_frequency_only"
        ),
        "safety": {
            "metadata_only": True,
            "guest_payload_read": False,
            "guest_state_changed": False,
            "control_flow_changed": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        static = json.loads(args.static.read_text(encoding="utf-8"))
        document = build(read_events(args.logs), static, args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print("native renderer dispatch summary failed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
