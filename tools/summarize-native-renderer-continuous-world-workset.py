#!/usr/bin/env python3
"""Qualify continuous multi-draw native world-workset accumulation."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-continuous-world-workset.v2"
CONFIG = "native_renderer.continuous_world_workset.config"
SUMMARY = "native_renderer.continuous_world_workset.summary"
OUTPUT_FRAME = "native_renderer.output.frame"
OUTPUT_WAITING = "native_renderer.output.waiting"


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
        "selection": "fresh_visibility_or_qualified_sky_horizon_and_mechanical",
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
        "qualified_retained_family_requests",
        "reused_target_requests",
        "frames_started",
        "frames_completed",
        "frames_failed",
        "maximum_draws_per_frame",
    )
    totals = {key: integer(summary, key) for key in keys}
    output_frames = [
        event for event in selected if event.get("event") == OUTPUT_FRAME
    ]
    output_waiting = [
        event for event in selected if event.get("event") == OUTPUT_WAITING
    ]
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
    if totals["frames_failed"] != (
        totals["target_creation_failures"] + totals["unsupported"]
    ):
        failures.append("failed frames do not reconcile with replay fallbacks")
    if not totals["qualified_retained_family_requests"]:
        failures.append("qualified retained-family seed was not observed")
    if not totals["reused_target_requests"]:
        failures.append("no frame accumulated multiple native draws")
    if totals["maximum_draws_per_frame"] != 64:
        failures.append("per-frame workset bound drifted")
    expected_summary_status = (
        "fallback_observed" if totals["frames_failed"] else "complete"
    )
    if summary.get("status") != expected_summary_status:
        failures.append("runtime workset status does not match its outcomes")

    exact_output_frames = []
    for event in output_frames:
        try:
            exact_frame = integer(event, "frame") == integer(
                event, "retained_frame"
            )
            callback = integer(event, "callback")
        except ValueError:
            exact_frame = False
            callback = 0
        safe = (
            exact_frame
            and event.get("selected_output") == "native"
            and event.get("authority") == "native"
            and event.get("xenos_draw") == "preserved"
            and event.get("suppression") == "disabled"
        )
        if safe:
            exact_output_frames.append((callback, event))
        else:
            failures.append("native output marker violates freshness or safety")
            break
    if len(exact_output_frames) < 3:
        failures.append("fewer than three exact native output markers were observed")
    elif any(
        right[0] <= left[0]
        for left, right in zip(exact_output_frames, exact_output_frames[1:])
    ):
        failures.append("native output callbacks are not strictly increasing")

    for event in output_waiting:
        if (
            event.get("fallback") != "xenos"
            or event.get("suppression") != "disabled"
        ):
            failures.append("waiting output marker violates fallback safety")
            break

    clean_fallback_proved = not any(
        message
        in failures
        for message in (
            "failed frames do not reconcile with replay fallbacks",
            "runtime workset status does not match its outcomes",
            "waiting output marker violates fallback safety",
        )
    )
    accumulation_proved = not any(
        message
        in failures
        for message in (
            "prepared selection accounting drifted",
            "replay outcome accounting drifted",
            "frame accounting drifted",
            "no complete continuous workset frame was recorded",
            "qualified retained-family seed was not observed",
            "no frame accumulated multiple native draws",
            "per-frame workset bound drifted",
        )
    )
    freshness_proved = not any(
        message
        in failures
        for message in (
            "native output marker violates freshness or safety",
            "fewer than three exact native output markers were observed",
            "native output callbacks are not strictly increasing",
        )
    )

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "totals": totals,
        "qualification": {
            "continuous_multi_draw_workset_proved": accumulation_proved,
            "swap_committed_freshness_proved": freshness_proved,
            "clean_xenos_fallback_proved": clean_fallback_proved,
            "native_output_markers": len(exact_output_frames),
            "xenos_fallback_markers": len(output_waiting),
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
