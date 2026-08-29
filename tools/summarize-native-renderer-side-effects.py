"""Summarize query, memexport, resolve, and binning census evidence."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-side-effects.v1"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
DISPATCH_PREFIX = "native_renderer.discovery.dispatch_"
WINDOW_EVENT = "native_renderer.census.resolve_window"


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
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error}"
                ) from error
            name = str(event.get("event", ""))
            if name.startswith(DISPATCH_PREFIX) or name == WINDOW_EVENT:
                events.append(event)
    return events


def select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"side-effect session not found: {requested}")
        return requested
    armed = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == f"{DISPATCH_PREFIX}config"
        and event.get("status") == "armed"
    ]
    if not armed or not armed[-1]:
        raise ValueError("no armed side-effect session found")
    return armed[-1]


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static side-effect inventory schema")
    session = select_session(events, requested)
    selected = [event for event in events if event.get("session") == session]
    configs = [
        event
        for event in selected
        if event.get("event") == f"{DISPATCH_PREFIX}config"
        and event.get("status") == "armed"
    ]
    summaries = [
        event
        for event in selected
        if event.get("event") == f"{DISPATCH_PREFIX}summary"
    ]
    if len(configs) != 1 or len(summaries) != 1:
        raise ValueError("side-effect session requires one config and summary")
    required_safety = {
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(
        str(summaries[0].get(key)).lower() != value
        for key, value in required_safety.items()
    ):
        raise ValueError("side-effect summary does not prove passive safety")

    windows = []
    for event in selected:
        if event.get("event") != WINDOW_EVENT:
            continue
        first_frame = int(event.get("first_frame", 0))
        last_frame = int(event.get("last_frame", 0))
        if first_frame <= 0 or last_frame < first_frame:
            raise ValueError("invalid side-effect census window")
        windows.append(
            {
                "first_frame": first_frame,
                "last_frame": last_frame,
                "resolves": int(event.get("resolves", 0)),
                "resolve_bytes": int(event.get("resolve_bytes", 0)),
                "query_draws": int(event.get("query_draws", 0)),
                "memexport_draws": int(event.get("memexport_draws", 0)),
                "target_overflow": int(event.get("target_overflow", 0)),
                "page_overflow": int(event.get("page_overflow", 0)),
            }
        )
    windows.sort(key=lambda item: (item["first_frame"], item["last_frame"]))
    for previous, current in zip(windows, windows[1:]):
        if current["first_frame"] <= previous["last_frame"]:
            raise ValueError("overlapping side-effect census windows")

    wrapper_calls = collections.Counter()
    wrapper_callers = collections.Counter()
    for event in selected:
        if event.get("event") != f"{DISPATCH_PREFIX}caller":
            continue
        wrapper = str(event.get("wrapper", "unknown"))
        wrapper_calls[wrapper] += int(event.get("calls", 0))
        wrapper_callers[wrapper] += 1
    reviewed = [
        str(item["kind"]) for item in static.get("reviewed_wrappers", [])
    ]
    wrapper_summary = {
        kind: {
            "calls": wrapper_calls[kind],
            "callers": wrapper_callers[kind],
        }
        for kind in reviewed
    }

    query_draws = sum(item["query_draws"] for item in windows)
    memexport_draws = sum(item["memexport_draws"] for item in windows)
    return {
        "schema": SCHEMA,
        "session": session,
        "scene": str(configs[0].get("scene", "unmarked")),
        "windows": windows,
        "totals": {
            "windows": len(windows),
            "resolves": sum(item["resolves"] for item in windows),
            "resolve_bytes": sum(item["resolve_bytes"] for item in windows),
            "query_draws": query_draws,
            "memexport_draws": memexport_draws,
            "target_overflow": sum(
                item["target_overflow"] for item in windows
            ),
            "page_overflow": sum(item["page_overflow"] for item in windows),
        },
        "wrapper_activity": wrapper_summary,
        "query": {
            "owner": static.get("query_owner_lifecycle"),
            "draw_observation": (
                "observed" if query_draws else "unobserved_not_absent"
            ),
            "semantic_identity": "unknown",
            "guest_side_effect": "preserved_on_xenos",
        },
        "memexport": {
            "draw_observation": (
                "observed" if memexport_draws else "unobserved_not_absent"
            ),
            "semantic_identity": "unknown",
            "guest_side_effect": "preserved_on_xenos",
        },
        "resolve_and_binning_packets": static.get("side_effect_packets"),
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
        print(
            "native renderer side-effect summary failed: {}".format(error),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
