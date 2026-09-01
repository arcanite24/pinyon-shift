#!/usr/bin/env python3
"""Qualify exact private procedural full-frame accumulation from one run."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-procedural-frame-accumulator.v1"
CONFIG = "native_renderer.discovery.command_buffer_lineage_config"
RESOLVE_ONLY_CONFIG = "native_renderer.resolve_only.config"
PLAN = "native_renderer.discovery.procedural_frame_accumulator_plan"
PLAN_SUMMARY = (
    "native_renderer.discovery.procedural_frame_accumulator_plan_summary"
)
RESULT = "native_renderer.procedural_frame_accumulator.result"
RESULT_SUMMARY = "native_renderer.procedural_frame_accumulator.result_summary"
SHUTDOWN = "process.shutdown"
QUALIFIED_SOURCE_STATES = {"14020500:00030000", "14020500:000C0000"}


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


def exact_plan_frames(events):
    grouped = {}
    for event in events:
        grouped.setdefault(integer(event, "frame"), []).append(event)
    exact = []
    expected = (
        ("begin_and_append", 0, 256, 256),
        ("append", 256, 256, 512),
        ("append_and_commit", 512, 224, 736),
    )
    for frame, rows in grouped.items():
        observed = tuple(
            (
                row.get("operation"),
                integer(row, "destination_row"),
                integer(row, "storage_row_count"),
                integer(row, "padded_height"),
            )
            for row in rows
            if row.get("operation") != "cancel"
        )
        if observed == expected and all(
            row.get("logical_extent") == "1280x720"
            and row.get("source_state") in QUALIFIED_SOURCE_STATES
            and row.get("backend_resource_action") == "private_only"
            and row.get("xenos_authority") == "true"
            and row.get("suppression_allowed") == "false"
            for row in rows
            if row.get("operation") != "cancel"
        ):
            exact.append(frame)
    return exact


def exact_result_frames(events):
    grouped = {}
    for event in events:
        grouped.setdefault(integer(event, "frame"), []).append(event)
    exact = []
    for frame, rows in grouped.items():
        recorded = [row for row in rows if row.get("status") == "recorded"]
        if [integer(row, "appended_row_end") for row in recorded] != [256, 512, 736]:
            continue
        if [row.get("committed") for row in recorded] != ["false", "false", "true"]:
            continue
        if not all(
            row.get("resource_extent") == "1280x736"
            and row.get("logical_extent") == "1280x720"
            and row.get("resource_scope") == "private_d3d12"
            and row.get("guest_memory_publication") == "false"
            and row.get("xenos_resolve") == "preserved_and_completed_first"
            and row.get("draw_suppression") == "false"
            for row in recorded
        ):
            continue
        exact.append(frame)
    return exact


def build(events, session):
    configs = [
        event
        for event in events
        if event.get("event") in (CONFIG, RESOLVE_ONLY_CONFIG)
    ]
    plans = [event for event in events if event.get("event") == PLAN]
    plan_summaries = [event for event in events if event.get("event") == PLAN_SUMMARY]
    results = [event for event in events if event.get("event") == RESULT]
    result_summaries = [
        event for event in events if event.get("event") == RESULT_SUMMARY
    ]
    shutdowns = [event for event in events if event.get("event") == SHUTDOWN]
    failures = []

    if len(configs) != 1:
        failures.append("expected one accumulator ingress config")
    elif configs[0].get("procedural_color_frame_accumulator_backend") != (
        "armed_private_d3d12_v1"
    ):
        failures.append("private D3D12 accumulator was not armed")
    if len(plan_summaries) != 1:
        failures.append("expected one frame-accumulator plan summary")
    if len(result_summaries) != 1:
        failures.append("expected one frame-accumulator result summary")
    if len(shutdowns) != 1:
        failures.append("clean process shutdown was not observed")

    plan_frames = exact_plan_frames(plans)
    result_frames = exact_result_frames(results)
    qualified_frames = sorted(set(plan_frames) & set(result_frames))
    if not qualified_frames:
        failures.append("no exact planned and committed 1280x720 frame was observed")

    status_counts = {}
    ingress_counts = {}
    ingress_accounting_complete = False
    if len(plan_summaries) == 1 and any(
        name in plan_summaries[0]
        for name in (
            "qualified_resolve_ingress_arms",
            "qualified_resolve_source_mode_3",
            "qualified_resolve_source_mode_12",
        )
    ):
        summary = plan_summaries[0]
        ingress_counts = {
            "arms": integer(summary, "qualified_resolve_ingress_arms"),
            "source_mode_3": integer(
                summary, "qualified_resolve_source_mode_3"
            ),
            "source_mode_12": integer(
                summary, "qualified_resolve_source_mode_12"
            ),
        }
        ingress_accounting_complete = ingress_counts["arms"] == (
            ingress_counts["source_mode_3"]
            + ingress_counts["source_mode_12"]
        )
        if not ingress_accounting_complete:
            failures.append("qualified resolve ingress accounting is incomplete")
    accounting_complete = False
    hard_failures = 0
    if len(result_summaries) == 1:
        summary = result_summaries[0]
        if summary.get("status") != "armed":
            failures.append("result summary did not remain armed")
        names = (
            "recorded",
            "cancelled",
            "invalid_request",
            "unavailable",
            "unsupported_target",
            "allocation_failed",
        )
        status_counts = {name: integer(summary, name) for name in names}
        detail_events = integer(summary, "detail_events")
        detail_overflow = integer(summary, "detail_overflow")
        accounting_complete = sum(status_counts.values()) == (
            detail_events + detail_overflow
        )
        if not accounting_complete:
            failures.append("backend result accounting is incomplete")
        hard_failures = sum(
            status_counts[name]
            for name in (
                "invalid_request",
                "unavailable",
                "unsupported_target",
                "allocation_failed",
            )
        )
        if hard_failures:
            failures.append("backend reported a hard failure")
        for name, expected in (
            ("resource_scope", "private_d3d12"),
            ("guest_memory_publication", "false"),
            ("xenos_resolve", "preserved_and_completed_first"),
            ("draw_suppression", "false"),
        ):
            if summary.get(name) != expected:
                failures.append(f"unsafe or missing summary field: {name}")

    complete = not failures
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if complete else "incomplete",
        "failures": failures,
        "evidence": {
            "plan_events": len(plans),
            "result_events": len(results),
            "exact_plan_frames": plan_frames,
            "exact_result_frames": result_frames,
            "qualified_frames": qualified_frames,
            "qualified_resolve_ingress": ingress_counts,
            "qualified_resolve_ingress_accounting_complete": (
                ingress_accounting_complete
            ),
            "status_counts": status_counts,
            "result_accounting_complete": accounting_complete,
            "hard_failures": hard_failures,
        },
        "qualification": {
            "exact_private_padded_frame_accumulator": complete,
            "logical_extent": "1280x720" if complete else None,
            "storage_extent": "1280x736" if complete else None,
            "native_output_eligible": complete,
            "guest_memory_publication": False,
            "draw_suppression": False,
        },
        "safety": {
            "xenos_resolve_completed_first": True,
            "xenos_draws_preserved": True,
            "guest_memory_changed": False,
            "suppression_allowed": False,
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
        print(f"procedural frame-accumulator summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
