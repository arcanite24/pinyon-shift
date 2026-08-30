#!/usr/bin/env python3
"""Qualify continuous multi-draw native world-workset accumulation."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-continuous-world-workset.v1"
CONFIG = "native_renderer.continuous_world_workset.config"
SUMMARY = "native_renderer.continuous_world_workset.summary"


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
            raise ValueError("requested session has no workset config")
        return requested
    if len(sessions) != 1:
        raise ValueError("workset input contains multiple sessions")
    return next(iter(sessions))


def require_safety(event):
    expected = {
        "readback": "disabled",
        "native_draw": "continuous_world_workset",
        "xenos_draw": "preserved",
        "output_authority": "renderer_selector",
        "draw_suppression": "false",
        "suppression_eligible": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("workset evidence violates safety boundary")


def build(events, requested_session=None):
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary = exact_event(selected, SUMMARY)
    expected_config = {
        "status": "armed_deferred_private_composition",
        "activation": "startup_environment_only",
        "default_enabled": "false",
        "selection": "fresh_visibility_and_mechanical",
        "maximum_draws_per_frame": "64",
        "target_lifetime": "one_guest_frame",
        "freshness_commit": "matching_swap_after_complete_accumulation",
        "semantic_lineage": "armed",
        "readback": "disabled",
        "native_draw": "continuous_world_workset",
        "xenos_draw": "preserved",
        "output_authority": "renderer_selector",
        "draw_suppression": "false",
        "suppression_eligible": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("workset runtime configuration drifted")
    require_safety(summary)
    if (
        summary.get("accounting_complete") != "true"
        or summary.get("selection_accounting_complete") != "true"
        or summary.get("freshness_commit")
        != "matching_swap_after_complete_accumulation"
        or summary.get("maximum_draws_per_frame") != "64"
    ):
        raise ValueError("workset summary is incomplete")

    keys = (
        "prepared_observations",
        "requests",
        "recorded",
        "target_creation_failures",
        "unsupported",
        "mechanical_rejections",
        "stale_or_unselected_rejections",
        "per_frame_quota_yields",
        "fail_closed_yields",
        "reused_target_requests",
        "frames_started",
        "frames_completed",
        "frames_failed",
        "maximum_draws_per_frame",
    )
    totals = {key: integer(summary, key) for key in keys}
    failures = []
    selections = (
        totals["requests"]
        + totals["mechanical_rejections"]
        + totals["stale_or_unselected_rejections"]
        + totals["per_frame_quota_yields"]
        + totals["fail_closed_yields"]
    )
    outcomes = (
        totals["recorded"]
        + totals["target_creation_failures"]
        + totals["unsupported"]
    )
    if selections != totals["prepared_observations"]:
        failures.append("prepared selection accounting drifted")
    if outcomes != totals["requests"]:
        failures.append("replay outcome accounting drifted")
    if totals["frames_started"] != (
        totals["frames_completed"] + totals["frames_failed"]
    ):
        failures.append("frame accounting drifted")
    if not totals["frames_completed"]:
        failures.append("no complete continuous workset frame was recorded")
    if totals["frames_failed"]:
        failures.append("one or more workset frames failed closed")
    if totals["fail_closed_yields"]:
        failures.append("workset requests yielded after a frame failure")
    if totals["target_creation_failures"] or totals["unsupported"]:
        failures.append("one or more private replays failed")
    if not totals["reused_target_requests"]:
        failures.append("no frame accumulated multiple native draws")
    if totals["maximum_draws_per_frame"] != 64:
        failures.append("per-frame workset bound drifted")
    if summary.get("status") != "complete":
        failures.append("runtime did not report complete worksets")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "totals": totals,
        "qualification": {
            "continuous_multi_draw_workset_proved": not failures,
            "swap_committed_freshness_proved": not failures,
            "suppression_allowed": False,
        },
        "safety": {
            "readback": False,
            "xenos_draw_preserved": True,
            "output_authority": "renderer_selector",
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
        print(
            f"native renderer continuous workset summary failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
