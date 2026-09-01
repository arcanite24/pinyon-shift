#!/usr/bin/env python3
"""Summarize bounded prepared layouts on the exact track-command lineage."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import struct
import sys


SCHEMA = "pinyon-shift.native-renderer-track-prepared-layout.v1"
ENTRY = "native_renderer.discovery.track_world_prepared_layout_entry"
SUMMARY = "native_renderer.discovery.track_render_model_runtime_join_summary"


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
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("track prepared-layout evidence violates safety")


def select_session(events, requested):
    sessions = {
        str(event.get("session"))
        for event in events
        if event.get("event") == SUMMARY and event.get("session")
    }
    if requested:
        if requested not in sessions:
            raise ValueError("requested session has no final track summary")
        session = requested
    elif len(sessions) == 1:
        session = next(iter(sessions))
    else:
        raise ValueError("input must contain exactly one candidate session")
    return session, [event for event in events if str(event.get("session")) == session]


def parse_float_constants(event, key):
    raw = event.get(key)
    if not isinstance(raw, str):
        raise ValueError(f"invalid {key}")
    result = {}
    if not raw:
        return result
    for item in raw.split(";"):
        parts = item.split(":")
        if len(parts) != 5:
            raise ValueError(f"invalid {key}")
        try:
            register = int(parts[0])
        except ValueError as error:
            raise ValueError(f"invalid {key} register") from error
        if register < 0 or register in result:
            raise ValueError(f"invalid {key} register")
        words = tuple(
            int(hexadecimal(word, 8, f"{key} word"), 16)
            for word in parts[1:]
        )
        values = tuple(
            struct.unpack(">f", word.to_bytes(4, "big"))[0] for word in words
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{key} contains a non-finite value")
        result[register] = {"words": words, "values": values}
    return result


def consecutive_runs(constants, minimum=4):
    registers = sorted(constants)
    runs = []
    start = 0
    while start < len(registers):
        end = start + 1
        while end < len(registers) and registers[end] == registers[end - 1] + 1:
            end += 1
        run = registers[start:end]
        if len(run) >= minimum:
            runs.append(run)
        start = end
    return runs


def build(events, requested_session=None):
    session, selected = select_session(events, requested_session)
    starts = [event for event in selected if event.get("event") == "process.start"]
    shutdowns = [event for event in selected if event.get("event") == "process.shutdown"]
    summaries = [event for event in selected if event.get("event") == SUMMARY]
    if len(starts) != 1 or len(shutdowns) != 1 or len(summaries) != 1:
        raise ValueError("track prepared-layout lifecycle is incomplete")
    summary = summaries[0]
    require_safety(summary)
    totals = {
        key: integer(summary, key)
        for key in (
            "command_prepared_draw_joins",
            "prepared_layout_observations",
            "prepared_layout_exact",
            "prepared_layout_entries",
            "prepared_layout_unbounded_geometry",
            "prepared_layout_parameter_overflows",
            "prepared_layout_table_overflow",
        )
    }
    entries = [event for event in selected if event.get("event") == ENTRY]
    seen = set()
    entry_calls = 0
    vertex_frequency = {}
    pixel_frequency = {}
    vertex_shader_frequency = {}
    candidate_runs = []
    for event in entries:
        require_safety(event)
        key = hexadecimal(event.get("layout_key", ""), 16, "layout key")
        vertex_shader = hexadecimal(
            event.get("vertex_shader", ""), 16, "vertex shader"
        )
        if key in seen:
            raise ValueError("duplicate track prepared layout key")
        seen.add(key)
        for address_key in (
            "track_render_root",
            "track_render_child",
            "track_render_descriptor",
            "track_render_descriptor_payload",
        ):
            hexadecimal(event.get(address_key, ""), 8, address_key)
        calls = integer(event, "calls")
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if not calls or first_frame > last_frame:
            raise ValueError("invalid track prepared layout lifetime")
        entry_calls += calls
        shader_item = vertex_shader_frequency.setdefault(
            vertex_shader, {"layouts": 0, "calls": 0}
        )
        shader_item["layouts"] += 1
        shader_item["calls"] += calls
        vertex = parse_float_constants(event, "vertex_float_constants")
        pixel = parse_float_constants(event, "pixel_float_constants")
        if integer(event, "vertex_float_constant_count") != len(vertex):
            raise ValueError("vertex float constant count drifted")
        if integer(event, "pixel_float_constant_count") != len(pixel):
            raise ValueError("pixel float constant count drifted")
        for register in vertex:
            item = vertex_frequency.setdefault(register, {"layouts": 0, "calls": 0})
            item["layouts"] += 1
            item["calls"] += calls
        for register in pixel:
            item = pixel_frequency.setdefault(register, {"layouts": 0, "calls": 0})
            item["layouts"] += 1
            item["calls"] += calls
        for run in consecutive_runs(vertex):
            candidate_runs.append(
                {
                    "layout_key": key,
                    "vertex_shader": vertex_shader,
                    "calls": calls,
                    "start_register": run[0],
                    "end_register": run[-1],
                    "register_count": len(run),
                    "registers": [
                        {
                            "index": register,
                            "words": [f"{word:08X}" for word in vertex[register]["words"]],
                            "values": list(vertex[register]["values"]),
                        }
                        for register in run
                    ],
                }
            )

    failures = []
    if summary.get("checkpoint_kind") != "final":
        failures.append("track summary is not final")
    if summary.get("prepared_layout_accounting_complete") != "true":
        failures.append("prepared layout accounting is incomplete")
    if totals["prepared_layout_observations"] != totals["command_prepared_draw_joins"]:
        failures.append("prepared observations do not match exact command joins")
    if totals["prepared_layout_observations"] != (
        totals["prepared_layout_exact"]
        + totals["prepared_layout_unbounded_geometry"]
        + totals["prepared_layout_parameter_overflows"]
    ):
        failures.append("prepared observation classification drifted")
    if totals["prepared_layout_entries"] != len(entries):
        failures.append("prepared layout entry count drifted")
    if totals["prepared_layout_exact"] != entry_calls:
        failures.append("prepared layout call accounting drifted")
    if not totals["prepared_layout_exact"] or not entries:
        failures.append("no exact track prepared layouts were observed")
    for key in (
        "prepared_layout_unbounded_geometry",
        "prepared_layout_parameter_overflows",
        "prepared_layout_table_overflow",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")

    def frequency_rows(frequency):
        return [
            {"register": register, **frequency[register]}
            for register in sorted(frequency)
        ]

    candidate_runs.sort(
        key=lambda item: (-item["calls"], item["layout_key"], item["start_register"])
    )
    status = "complete" if not failures else "incomplete"
    return {
        "schema": SCHEMA,
        "session": session,
        "status": status,
        "failures": failures,
        "totals": totals,
        "constant_register_frequency": {
            "vertex": frequency_rows(vertex_frequency),
            "pixel": frequency_rows(pixel_frequency),
        },
        "vertex_shader_layout_frequency": [
            {"vertex_shader": shader, **vertex_shader_frequency[shader]}
            for shader in sorted(vertex_shader_frequency)
        ],
        "vertex_consecutive_register_runs": candidate_runs,
        "qualification": {
            "exact_track_prepared_layouts_proved": not failures,
            "world_transform_constant_layout_proved": False,
            "terrain_or_road_identity_proved": False,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "next_step": (
            "compare recurring finite vertex constant runs against the static "
            "world transform catalog across changed camera and vehicle poses"
        ),
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
        print(f"track prepared-layout summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
