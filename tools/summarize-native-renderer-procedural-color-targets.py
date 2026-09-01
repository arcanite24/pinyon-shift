#!/usr/bin/env python3
"""Classify exact procedural-model color draws by render-target role."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-procedural-color-targets.v1"
CONFIG = "native_renderer.discovery.command_buffer_lineage_config"
ENTRY = "native_renderer.discovery.procedural_color_target_profile_entry"
SUMMARY = "native_renderer.discovery.procedural_color_target_profile_summary"
SHUTDOWN = "process.shutdown"


def integer(event, name):
    try:
        return int(event[name], 10)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {name}") from error


def read_events(path, session):
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON at line {line_number}") from error
        if event.get("session") == session:
            events.append(event)
    return events


def extent(event):
    value = event.get("scissor_extent")
    if not isinstance(value, str):
        raise ValueError("invalid scissor_extent")
    parts = value.split(":")
    if len(parts) != 4:
        raise ValueError("invalid scissor_extent")
    try:
        return tuple(int(part, 10) for part in parts)
    except ValueError as error:
        raise ValueError("invalid scissor_extent") from error


def build(events, session):
    configs = [event for event in events if event.get("event") == CONFIG]
    summaries = [event for event in events if event.get("event") == SUMMARY]
    entries = [event for event in events if event.get("event") == ENTRY]
    shutdowns = [event for event in events if event.get("event") == SHUTDOWN]
    failures = []
    if len(configs) != 1:
        failures.append("expected one command-lineage config")
    elif configs[0].get("procedural_color_target_profile_census") != "bounded_exact_v1":
        failures.append("procedural color-target profiler was not armed")
    if len(summaries) != 1:
        failures.append("expected one procedural color-target summary")
    if len(shutdowns) != 1:
        failures.append("clean process shutdown was not observed")
    if not summaries:
        return document(session, failures, [], {})

    summary = summaries[0]
    observations = integer(summary, "observations")
    accounted = integer(summary, "accounted")
    overflow = integer(summary, "overflow")
    expected_entries = integer(summary, "entries")
    if expected_entries != len(entries):
        failures.append("entry count does not match target-profile summary")
    if summary.get("accounting_complete") != "true":
        failures.append("target-profile accounting is incomplete")
    if overflow:
        failures.append("target-profile table overflowed")
    if observations != accounted + overflow:
        failures.append("observations do not match accounted profiles")

    profiles = []
    observed_calls = 0
    for event in entries:
        calls = integer(event, "calls")
        opaque = integer(event, "opaque_calls")
        bounded = integer(event, "bounded_calls")
        resolved = integer(event, "resolved_input_calls")
        observed_calls += calls
        if opaque > calls or bounded > calls or resolved > calls:
            failures.append("profile counters exceed calls")
        signature = event.get("prepared_signature")
        if not isinstance(signature, str) or len(signature) != 16:
            failures.append("profile lacks an exact prepared signature")
        left, top, right, bottom = extent(event)
        exact_full_preview = left == 0 and top == 0 and right == 1280 and bottom == 720
        reduced_preview_width = (
            left == 0 and top == 0 and right == 1280 and 0 < bottom < 720
        )
        if exact_full_preview:
            role = "full_preview_extent"
        elif reduced_preview_width:
            role = "reduced_preview_width"
        else:
            role = "other_extent"
        profiles.append(
            {
                "prepared_signature": signature,
                "calls": calls,
                "opaque_calls": opaque,
                "bounded_calls": bounded,
                "resolved_input_calls": resolved,
                "vertex_shader": event.get("vertex_shader"),
                "pixel_shader": event.get("pixel_shader"),
                "target_bits": event.get("bound_render_target_bits"),
                "target_formats": event.get("bound_render_target_formats"),
                "target_state": event.get("target_state"),
                "viewport": event.get("viewport"),
                "scissor": event.get("scissor"),
                "extent": {"left": left, "top": top, "right": right, "bottom": bottom},
                "role": role,
                "semantic_receiver_varied": event.get("semantic_receiver_varied") == "true",
            }
        )
    if observed_calls != accounted:
        failures.append("entry calls do not match accounted profiles")
    profiles.sort(
        key=lambda row: (
            row["role"] != "full_preview_extent",
            row["resolved_input_calls"] != 0,
            -row["bounded_calls"],
            -row["opaque_calls"],
            -row["calls"],
            row["prepared_signature"] or "",
        )
    )
    totals = {
        "observations": observations,
        "profiles": len(profiles),
        "full_preview_profiles": sum(1 for row in profiles if row["role"] == "full_preview_extent"),
        "full_preview_calls": sum(row["calls"] for row in profiles if row["role"] == "full_preview_extent"),
        "reduced_preview_width_profiles": sum(1 for row in profiles if row["role"] == "reduced_preview_width"),
        "other_extent_profiles": sum(1 for row in profiles if row["role"] == "other_extent"),
    }
    return document(session, failures, profiles, totals)


def document(session, failures, profiles, totals):
    complete = not failures
    full_clean = [
        row
        for row in profiles
        if row["role"] == "full_preview_extent"
        and row["bounded_calls"] == row["calls"]
        and row["opaque_calls"] == row["calls"]
        and not row["resolved_input_calls"]
    ]
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if complete else "incomplete",
        "failures": failures,
        "totals": totals,
        "profiles": profiles,
        "qualification": {
            "exact_semantic_target_profiles_accounted": complete,
            "full_preview_color_profile_observed": complete and bool(full_clean),
            "eligible_for_isolated_capture_selection": complete and bool(full_clean),
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "guest_payload_exported": False,
            "guest_state_changed": False,
            "control_flow_changed": False,
            "native_draw": False,
            "xenos_authority": True,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        result = build(read_events(args.log, args.session), args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 0 if result["status"] == "complete" else 1
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"procedural color-target summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
