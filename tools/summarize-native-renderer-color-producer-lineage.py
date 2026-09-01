#!/usr/bin/env python3
"""Rank live command-buffer origins by prepared color-target activity."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-color-producer-lineage.v1"
CONFIG = "native_renderer.discovery.command_buffer_lineage_config"
ENTRY = "native_renderer.discovery.command_buffer_lineage_entry"
SUMMARY = "native_renderer.discovery.command_buffer_lineage_summary"
SHUTDOWN = "process.shutdown"


def integer(event, name):
    try:
        return int(event[name], 10)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {name}") from error


def exact_address(event, name):
    value = event.get(name)
    if value == "unknown":
        return None
    if not isinstance(value, str) or len(value) != 8:
        raise ValueError(f"invalid {name}")
    int(value, 16)
    return value


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


def build(events, session):
    configs = [event for event in events if event.get("event") == CONFIG]
    summaries = [event for event in events if event.get("event") == SUMMARY]
    entries = [event for event in events if event.get("event") == ENTRY]
    shutdowns = [event for event in events if event.get("event") == SHUTDOWN]
    failures = []
    if len(configs) != 1:
        failures.append("expected one command-lineage config")
    elif configs[0].get("prepared_target_shape_census") != "bounded_aggregate_v1":
        failures.append("prepared target-shape census was not armed")
    if len(summaries) != 1:
        failures.append("expected one command-lineage summary")
    if len(shutdowns) != 1:
        failures.append("clean process shutdown was not observed")
    if not summaries:
        return document(session, failures, [], {})

    summary = summaries[0]
    expected_entries = integer(summary, "entries")
    prepared_draws = integer(summary, "prepared_draws")
    if expected_entries != len(entries):
        failures.append("entry count does not match command-lineage summary")
    for name in ("invalid_lineages", "overflow", "indirect_buffer_stack_faults",
                 "indirect_draw_stack_faults", "indirect_constructor_stack_faults",
                 "indirect_constructor_owner_mismatches", "indirect_owner_stack_faults",
                 "indirect_owner_producer_mismatches", "indirect_producer_stack_faults",
                 "indirect_producer_context_mismatches", "indirect_context_stack_faults"):
        if integer(summary, name):
            failures.append(f"nonzero {name}")

    rows = []
    observed_draws = 0
    for event in entries:
        calls = integer(event, "calls")
        depth_only = integer(event, "depth_only_draws")
        color_only = integer(event, "color_only_draws")
        color_depth = integer(event, "color_depth_draws")
        other = integer(event, "other_target_draws")
        other_color = integer(event, "other_color_draws")
        opaque = integer(event, "opaque_color_draws")
        bounded = integer(event, "bounded_color_draws")
        resolved = integer(event, "resolved_input_color_draws")
        color = color_only + color_depth + other_color
        observed_draws += calls
        if depth_only + color_only + color_depth + other != calls:
            failures.append("entry target-shape accounting is incomplete")
        if opaque > color or bounded > color or resolved > color:
            failures.append("entry color counters exceed color draws")
        if other_color > other:
            failures.append("entry other-color counter exceeds other targets")
        sample = event.get("sample_color_prepared_signature")
        if color and (not isinstance(sample, str) or len(sample) != 16):
            failures.append("color entry lacks an exact prepared sample")
        if not color:
            continue
        row = {
            "calls": calls,
            "color_draws": color,
            "color_only_draws": color_only,
            "color_depth_draws": color_depth,
            "other_color_draws": other_color,
            "depth_only_draws": depth_only,
            "other_target_draws": other,
            "opaque_color_draws": opaque,
            "bounded_color_draws": bounded,
            "resolved_input_color_draws": resolved,
            "color_share": round(color / calls, 6) if calls else 0.0,
            "constructor_function": exact_address(event, "constructor_function_address"),
            "owner_function": exact_address(event, "owner_function_address"),
            "producer_function": exact_address(event, "producer_function_address"),
            "context_function": exact_address(event, "context_function_address"),
            "semantic_receiver_class": event.get("semantic_receiver_class"),
            "semantic_receiver_exact": event.get("semantic_receiver_class") != "unknown",
            "track_command_lineage": event.get("track_command_lineage") == "true",
            "sample_color_prepared_signature": sample,
            "color_sample_varied": event.get("color_sample_varied") == "true",
            "sample_color_vertex_shader": event.get("sample_color_vertex_shader"),
            "sample_color_pixel_shader": event.get("sample_color_pixel_shader"),
            "sample_color_bound_render_target_bits": event.get(
                "sample_color_bound_render_target_bits"
            ),
            "sample_color_bound_render_target_formats": event.get(
                "sample_color_bound_render_target_formats"
            ),
            "sample_color_prepared_pipeline_flags": event.get(
                "sample_color_prepared_pipeline_flags"
            ),
            "sample_color_target_state": event.get("sample_color_target_state"),
            "sample_color_scissor": event.get("sample_color_scissor"),
        }
        rows.append(row)
    if observed_draws != prepared_draws:
        failures.append("entry draws do not match prepared-draw summary")
    rows.sort(
        key=lambda row: (
            not row["semantic_receiver_exact"],
            -row["opaque_color_draws"],
            -row["bounded_color_draws"],
            -row["color_draws"],
            row["context_function"] or "FFFFFFFF",
        )
    )
    totals = {
        "entries": len(entries),
        "prepared_draws": prepared_draws,
        "color_candidates": len(rows),
        "color_draws": sum(row["color_draws"] for row in rows),
        "opaque_color_draws": sum(row["opaque_color_draws"] for row in rows),
        "bounded_color_draws": sum(row["bounded_color_draws"] for row in rows),
        "semantic_color_candidates": sum(
            1 for row in rows if row["semantic_receiver_exact"]
        ),
    }
    return document(session, failures, rows, totals)


def document(session, failures, candidates, totals):
    complete = not failures
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if complete else "incomplete",
        "failures": failures,
        "totals": totals,
        "candidates": candidates,
        "qualification": {
            "runtime_target_shape_accounting_proved": complete,
            "live_color_producers_ranked": complete and bool(candidates),
            "semantic_color_candidate_observed": complete
            and any(row["semantic_receiver_exact"] for row in candidates),
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
        print(f"color-producer lineage summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
