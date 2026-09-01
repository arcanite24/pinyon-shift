#!/usr/bin/env python3
"""Qualify the direct indexed-draw producer census and C2 track-mesh lead."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
import sys


SCHEMA = "pinyon-shift.native-renderer-direct-indexed-runtime.v1"
CONFIG = "native_renderer.discovery.static_world_runtime_join_config"
PRODUCER = "native_renderer.discovery.direct_indexed_draw_producer_entry"
TRANSFORM = "native_renderer.discovery.unified_track_mesh_transform_entry"
SUMMARY = "native_renderer.discovery.direct_indexed_draw_producer_summary"
EXPECTED_RETURNS = (
    "823F59C8", "8240F020", "82412D90", "824131F4", "8243C8FC",
    "82473BDC", "82C4DC58", "82C5B038", "82C8E79C", "82D841DC",
    "82DA154C", "82DA1678", "82DA1754",
)
MINIMUM_TRANSFORMS = 8


def read_events(paths):
    events = []
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"invalid JSON at {path}:{line_number}: {error}"
                    ) from error
                if isinstance(event, dict):
                    events.append(event)
    return events


def integer(event, key):
    try:
        value = int(event[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if value < 0:
        raise ValueError(f"negative {key}")
    return value


def hexadecimal(value, width, label):
    value = str(value).upper()
    if len(value) != width or any(c not in "0123456789ABCDEF" for c in value):
        raise ValueError(f"invalid {label}")
    return value


def require_safety(event):
    expected = {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("direct indexed producer evidence violates safety")


def select_session(events, requested):
    sessions = {
        str(event.get("session"))
        for event in events
        if event.get("event") == CONFIG and event.get("session")
    }
    if requested:
        if requested not in sessions:
            raise ValueError("requested session is missing")
        session = requested
    elif len(sessions) == 1:
        session = next(iter(sessions))
    else:
        raise ValueError("input must contain exactly one candidate session")
    return session, [event for event in events if str(event.get("session")) == session]


def parse_words(event):
    raw = str(event.get("transform_words", "")).split(",")
    if len(raw) != 16:
        raise ValueError("track mesh transform does not contain 16 words")
    words = tuple(int(hexadecimal(word, 8, "transform word"), 16) for word in raw)
    if not all(math.isfinite(struct.unpack(">f", word.to_bytes(4, "big"))[0]) for word in words):
        raise ValueError("track mesh transform contains a non-finite word")
    return words


def build(events, requested_session=None, minimum_transforms=MINIMUM_TRANSFORMS):
    if minimum_transforms < 1:
        raise ValueError("minimum transforms must be positive")
    session, selected = select_session(events, requested_session)
    configs = [event for event in selected if event.get("event") == CONFIG]
    summaries = [event for event in selected if event.get("event") == SUMMARY]
    starts = [event for event in selected if event.get("event") == "process.start"]
    shutdowns = [event for event in selected if event.get("event") == "process.shutdown"]
    if len(configs) != 1 or len(summaries) != 1:
        raise ValueError("direct indexed producer lifecycle is incomplete")
    if len(starts) != 1 or len(shutdowns) != 1:
        raise ValueError("process lifecycle is incomplete")
    config = configs[0]
    summary = summaries[0]
    expected_config = {
        "status": "armed",
        "direct_indexed_draw_emitter": "82416380",
        "direct_indexed_draw_producer_count": "13",
        "direct_indexed_draw_producer_hook": "82416380:r26,r31,lr",
        "direct_indexed_draw_producer_exit_hook": "824167EC",
        "direct_indexed_draw_producer_census": "armed",
        "unified_track_mesh_draw_return": "82C5B038",
        "unified_track_mesh_draw_producer": "82C5ADC0",
        "unified_track_mesh_vtable": "8200143C",
        "unified_track_mesh_transform": "live_r31_16_be_u32_at_exact_draw_entry",
        "unified_track_mesh_transform_capacity": "4096",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("direct indexed producer config drifted")
    require_safety(summary)

    producers = [event for event in selected if event.get("event") == PRODUCER]
    if len(producers) != len(EXPECTED_RETURNS):
        raise ValueError("direct indexed producer entry count drifted")
    by_return = {}
    classified = 0
    for event in producers:
        require_safety(event)
        if event.get("emitter") != "82416380":
            raise ValueError("direct indexed producer emitter drifted")
        address = hexadecimal(event.get("return_address", ""), 8, "return address")
        if address in by_return:
            raise ValueError("duplicate direct indexed producer")
        by_return[address] = event
        classified += integer(event, "observations")
    if tuple(sorted(by_return)) != tuple(sorted(EXPECTED_RETURNS)):
        raise ValueError("direct indexed producer inventory drifted")

    transforms = [event for event in selected if event.get("event") == TRANSFORM]
    transform_keys = set()
    transform_observations = 0
    for event in transforms:
        require_safety(event)
        if (
            event.get("emitter") != "82416380"
            or event.get("return_address") != "82C5B038"
            or event.get("producer_function") != "82C5ADC0"
            or event.get("mesh_vtable") != "8200143C"
            or event.get("classification") != "exact_unified_track_mesh_draw_transform"
        ):
            raise ValueError("unified track mesh transform boundary drifted")
        key = (
            hexadecimal(event.get("mesh_address", ""), 8, "mesh address"),
            hexadecimal(event.get("transform_hash", ""), 16, "transform hash"),
        )
        words = parse_words(event)
        if key in transform_keys:
            raise ValueError("duplicate unified track mesh transform")
        transform_keys.add(key)
        observations = integer(event, "observations")
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if not observations or first_frame > last_frame or not any(words):
            raise ValueError("invalid unified track mesh transform entry")
        transform_observations += observations

    totals = {
        key: integer(summary, key)
        for key in (
            "observations", "classified_observations", "unknown_callers",
            "producer_count", "unified_track_mesh_observations",
            "unified_track_mesh_exact", "unified_track_mesh_read_faults",
            "unified_track_mesh_vtable_mismatches",
            "unified_track_mesh_nonfinite_transforms",
            "unified_track_mesh_transform_entries",
            "unified_track_mesh_transform_collisions",
            "unified_track_mesh_transform_overflow",
            "direct_indexed_draw_scope_entries",
            "direct_indexed_draw_scope_exits",
            "direct_indexed_draw_scope_overlaps",
            "direct_indexed_draw_scope_exit_without_entry",
            "unified_track_mesh_scopes_exact",
            "unified_track_mesh_scopes_with_packets",
            "unified_track_mesh_scopes_without_packets",
            "unified_track_mesh_packet_origins",
            "unified_track_mesh_prepared_matches",
            "unified_track_mesh_unprepared_matches",
        )
    }
    failures = []
    if summary.get("status") != "complete" or summary.get("accounting_complete") != "true":
        failures.append("runtime accounting is incomplete")
    if (
        summary.get("scope_accounting_complete") != "true"
        or summary.get("prepared_join_accounting_complete") != "true"
    ):
        failures.append("prepared provenance accounting is incomplete")
    if totals["observations"] != classified or totals["classified_observations"] != classified:
        failures.append("producer observation accounting does not balance")
    if totals["producer_count"] != len(EXPECTED_RETURNS):
        failures.append("producer count drifted")
    if totals["unknown_callers"]:
        failures.append("unknown direct indexed-draw callers were observed")
    track_calls = integer(by_return["82C5B038"], "observations")
    if not track_calls or track_calls != totals["unified_track_mesh_observations"]:
        failures.append("unified track mesh producer was not observed exactly")
    if totals["unified_track_mesh_exact"] != track_calls or transform_observations != track_calls:
        failures.append("unified track mesh exact accounting does not balance")
    for key in (
        "unified_track_mesh_read_faults",
        "unified_track_mesh_vtable_mismatches",
        "unified_track_mesh_nonfinite_transforms",
        "unified_track_mesh_transform_collisions",
        "unified_track_mesh_transform_overflow",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
    if totals["unified_track_mesh_transform_entries"] != len(transforms):
        failures.append("unified track mesh transform entry count does not balance")
    if (
        totals["direct_indexed_draw_scope_entries"]
        != totals["direct_indexed_draw_scope_exits"]
        or totals["direct_indexed_draw_scope_entries"] != totals["observations"]
        or totals["direct_indexed_draw_scope_overlaps"]
        or totals["direct_indexed_draw_scope_exit_without_entry"]
    ):
        failures.append("direct indexed draw scope lifecycle does not balance")
    if (
        totals["unified_track_mesh_scopes_exact"] != track_calls
        or totals["unified_track_mesh_scopes_with_packets"] != track_calls
        or totals["unified_track_mesh_scopes_without_packets"]
        or totals["unified_track_mesh_packet_origins"] != track_calls
        or totals["unified_track_mesh_prepared_matches"] != track_calls
        or totals["unified_track_mesh_unprepared_matches"]
    ):
        failures.append("unified track mesh prepared provenance does not balance")
    if len(transforms) < minimum_transforms:
        failures.append("too few distinct unified track mesh transforms")

    status = "complete" if not failures else "incomplete"
    return {
        "schema": SCHEMA,
        "session": session,
        "status": status,
        "failures": failures,
        "totals": totals,
        "qualification": {
            "direct_indexed_draw_producer_inventory_proved": not failures,
            "unified_track_mesh_draw_activity_proved": not failures,
            "unified_track_mesh_transform_boundary_proved": not failures,
            "unified_track_mesh_prepared_provenance_proved": not failures,
            "building_or_prop_instance_identity_proved": False,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "guest_state_changed": False,
            "control_flow_changed": False,
            "native_admission": False,
            "native_draw": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", nargs="+", type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--minimum-transforms", type=int, default=MINIMUM_TRANSFORMS)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(read_events(args.events), args.session, args.minimum_transforms)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if document["status"] != "complete":
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"direct indexed producer qualification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
