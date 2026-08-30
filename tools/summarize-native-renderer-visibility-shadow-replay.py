#!/usr/bin/env python3
"""Qualify bounded private replay of visibility-selected prepared draws."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-shadow-replay.v1"
CONFIG = "native_renderer.visibility_shadow_replay.config"
SUMMARY = "native_renderer.visibility_shadow_replay.summary"
SIGNATURE = "native_renderer.visibility_shadow_replay.signature"
SIGNATURE_SUMMARY_LIMIT = 16


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


def hexadecimal(mapping, key, width=16):
    value = str(mapping.get(key, "")).upper()
    if len(value) != width:
        raise ValueError(f"invalid {key}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid {key}") from error
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
            raise ValueError("requested session has no shadow-replay config")
        return requested
    if len(sessions) != 1:
        raise ValueError("shadow-replay input contains multiple sessions")
    return next(iter(sessions))


def require_safety(event):
    expected = {
        "readback": "disabled",
        "native_draw": "private_shadow_replay",
        "xenos_draw": "preserved",
        "output_authority": "xenos",
        "draw_suppression": "false",
        "suppression_eligible": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("shadow-replay evidence violates safety boundary")


def build(events, requested_session=None):
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary = exact_event(selected, SUMMARY)
    expected_config = {
        "status": "armed_private_replay",
        "activation": "startup_environment_only",
        "default_enabled": "false",
        "selection": "fresh_visibility_and_mechanical",
        "title_lod": "optional_exact_metadata_no_inference",
        "maximum_draws_per_frame": "1",
        "signature_capacity": "256",
        "semantic_lineage": "armed",
        "readback": "disabled",
        "publication": "disabled",
        "native_draw": "private_shadow_replay",
        "xenos_draw": "preserved",
        "output_authority": "xenos",
        "draw_suppression": "false",
        "suppression_eligible": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("shadow-replay runtime configuration drifted")
    require_safety(summary)
    if (
        summary.get("status") != "complete"
        or summary.get("accounting_complete") != "true"
        or summary.get("selection_accounting_complete") != "true"
        or summary.get("title_lod_accounting_complete") != "true"
        or summary.get("selection") != "fresh_visibility_and_mechanical"
        or summary.get("title_lod")
        != "optional_exact_metadata_no_inference"
        or summary.get("maximum_draws_per_frame") != "1"
        or summary.get("signature_capacity") != "256"
    ):
        raise ValueError("shadow-replay summary is incomplete")

    count_keys = (
        "prepared_observations",
        "requests",
        "recorded",
        "target_creation_failures",
        "unsupported",
        "mechanical_rejections",
        "stale_or_unselected_rejections",
        "requests_with_title_lod",
        "requests_without_title_lod",
        "per_frame_quota_yields",
        "unique_signatures",
        "signature_capacity",
        "signature_overflow",
        "maximum_draws_per_frame",
    )
    totals = {key: integer(summary, key) for key in count_keys}
    signatures = []
    seen = set()
    for event in selected:
        if event.get("event") != SIGNATURE:
            continue
        expected_safety = {
            "native_draw": "private_shadow_replay",
            "xenos_draw": "preserved",
            "output_authority": "xenos",
            "suppression_eligible": "false",
        }
        if any(event.get(key) != value for key, value in expected_safety.items()):
            raise ValueError("signature evidence violates safety boundary")
        signature = hexadecimal(event, "signature")
        if signature in seen:
            raise ValueError("duplicate shadow-replay signature")
        seen.add(signature)
        title_lod_observations = integer(event, "title_lod_observations")
        missing_title_lod_requests = integer(
            event, "missing_title_lod_requests"
        )
        minimum_lod = None
        maximum_lod = None
        if title_lod_observations:
            minimum_lod = integer(event, "minimum_title_lod")
            maximum_lod = integer(event, "maximum_title_lod")
            if minimum_lod > maximum_lod:
                raise ValueError("invalid title LOD range")
        elif event.get("minimum_title_lod") or event.get("maximum_title_lod"):
            raise ValueError("title LOD range exists without observations")
        requests = integer(event, "requests")
        if title_lod_observations + missing_title_lod_requests != requests:
            raise ValueError("signature title LOD accounting drifted")
        signatures.append(
            {
                "signature": signature,
                "requests": requests,
                "first_frame": integer(event, "first_frame"),
                "last_frame": integer(event, "last_frame"),
                "minimum_title_lod": minimum_lod,
                "maximum_title_lod": maximum_lod,
                "title_lod_observations": title_lod_observations,
                "missing_title_lod_requests": missing_title_lod_requests,
            }
        )

    failures = []
    selections = (
        totals["requests"]
        + totals["mechanical_rejections"]
        + totals["stale_or_unselected_rejections"]
        + totals["per_frame_quota_yields"]
    )
    if selections != totals["prepared_observations"]:
        failures.append("prepared selection accounting drifted")
    outcomes = (
        totals["recorded"]
        + totals["target_creation_failures"]
        + totals["unsupported"]
    )
    if outcomes != totals["requests"]:
        failures.append("replay outcome accounting drifted")
    if (
        totals["requests_with_title_lod"]
        + totals["requests_without_title_lod"]
        != totals["requests"]
    ):
        failures.append("title LOD accounting drifted")
    if not totals["requests"] or not totals["recorded"]:
        failures.append("no visibility-selected private replay was recorded")
    if totals["target_creation_failures"] or totals["unsupported"]:
        failures.append("one or more private replays failed")
    if totals["signature_overflow"]:
        failures.append("signature table overflowed")
    expected_signature_events = min(
        totals["unique_signatures"], SIGNATURE_SUMMARY_LIMIT
    )
    if len(signatures) != expected_signature_events:
        failures.append("signature summary coverage drifted")
    if totals["unique_signatures"] > totals["requests"]:
        failures.append("unique signatures exceed replay requests")
    if totals["signature_capacity"] != 256:
        failures.append("signature capacity drifted")
    if totals["maximum_draws_per_frame"] != 1:
        failures.append("per-frame replay bound drifted")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "totals": totals,
        "signatures": signatures,
        "qualification": {
            "broad_visibility_workset_replay_proved": not failures,
            "publication_admitted": False,
            "suppression_allowed": False,
        },
        "safety": {
            "readback": False,
            "native_publication": False,
            "native_draw_private_only": True,
            "xenos_draw_preserved": True,
            "output_authority": "xenos",
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
            f"native renderer visibility shadow replay summary failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
