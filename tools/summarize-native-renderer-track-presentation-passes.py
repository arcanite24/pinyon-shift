#!/usr/bin/env python3
"""Summarize unified track-presentation passes and prepared target shapes."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-track-presentation-passes.v1"
SUMMARY = "native_renderer.discovery.track_presentation_pass_summary"
ENTRY = "native_renderer.discovery.track_presentation_prepared_target_entry"
RECEIVER = "native_renderer.discovery.track_presentation_receiver_entry"
SLOTS = (78, 79, 80, 81)


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


def hexadecimal(event, key, width):
    value = str(event.get(key, "")).upper()
    if len(value) != width or any(c not in "0123456789ABCDEF" for c in value):
        raise ValueError(f"invalid {key}")
    return int(value, 16)


def require_safety(event):
    expected = {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("track presentation evidence violates safety")


def target_shape(bits):
    return {
        1: "depth_only",
        2: "color_only",
        3: "color_and_depth",
    }.get(bits, "other")


def hexadecimal_tuple(event, key, count):
    parts = str(event.get(key, "")).upper().split(":")
    if len(parts) != count or any(
        len(part) != 8 or any(c not in "0123456789ABCDEF" for c in part)
        for part in parts
    ):
        raise ValueError(f"invalid {key}")
    return tuple(int(part, 16) for part in parts)


def scissor_extent(scissor):
    tl, br = scissor
    left, top = tl & 0x7FFF, (tl >> 16) & 0x7FFF
    right, bottom = br & 0x7FFF, (br >> 16) & 0x7FFF
    if right < left or bottom < top:
        return "invalid"
    return f"{right - left}x{bottom - top}"


def build(events, requested_session=None):
    summaries = [event for event in events if event.get("event") == SUMMARY]
    sessions = {
        str(event.get("session")) for event in summaries if event.get("session")
    }
    if requested_session:
        session = requested_session
        if session not in sessions:
            raise ValueError("requested session has no track presentation summary")
    elif len(sessions) == 1:
        session = next(iter(sessions))
    else:
        raise ValueError("input must contain exactly one candidate session")
    selected = [event for event in events if str(event.get("session")) == session]
    starts = [event for event in selected if event.get("event") == "process.start"]
    shutdowns = [event for event in selected if event.get("event") == "process.shutdown"]
    summaries = [event for event in selected if event.get("event") == SUMMARY]
    if len(starts) != 1 or len(shutdowns) != 1 or len(summaries) != 1:
        raise ValueError("track presentation lifecycle is incomplete")
    summary = summaries[0]
    require_safety(summary)

    slot_totals = {}
    total_slot_entries = 0
    for slot in SLOTS:
        adapter_first_target = hexadecimal(
            summary, f"slot_{slot}_adapter_first_target", 8
        )
        adapter_last_target = hexadecimal(
            summary, f"slot_{slot}_adapter_last_target", 8
        )
        row = {
            "function": str(summary.get(f"slot_{slot}_function", "")),
            "entries": integer(summary, f"slot_{slot}_entries"),
            "exits": integer(summary, f"slot_{slot}_exits"),
            "exact": integer(summary, f"slot_{slot}_exact"),
            "invalid_root": integer(summary, f"slot_{slot}_invalid_root"),
            "dispatcher_routes": {
                "direct": integer(summary, f"slot_{slot}_dispatcher_direct"),
                "context": integer(summary, f"slot_{slot}_dispatcher_context"),
            },
            "adapter_route": {
                "entries": integer(summary, f"slot_{slot}_adapter_entries"),
                "enabled": integer(summary, f"slot_{slot}_adapter_enabled"),
                "eligible": integer(summary, f"slot_{slot}_adapter_eligible"),
                "dispatches": integer(summary, f"slot_{slot}_adapter_dispatches"),
                "first_target": f"{adapter_first_target:08X}",
                "last_target": f"{adapter_last_target:08X}",
                "target_changes": integer(
                    summary, f"slot_{slot}_adapter_target_changes"
                ),
            },
        }
        slot_totals[str(slot)] = row
        total_slot_entries += row["entries"]

    prepared_observations = integer(summary, "prepared_target_observations")
    prepared_entries = integer(summary, "prepared_target_entries")
    prepared_overflow = integer(summary, "prepared_target_overflow")
    entries = [event for event in selected if event.get("event") == ENTRY]
    seen = set()
    entry_calls = 0
    per_slot = {
        str(slot): {
            "calls": 0,
            "attribution_sources": {},
            "target_shapes": {},
            "shader_pairs": {},
            "spatial_states": {},
            "target_states": {},
        }
        for slot in SLOTS
    }
    for event in entries:
        require_safety(event)
        key = hexadecimal(event, "entry_key", 16)
        if key in seen:
            raise ValueError("duplicate prepared target entry key")
        seen.add(key)
        pass_mask = hexadecimal(event, "pass_mask", 8)
        if not pass_mask or pass_mask & ~0xF:
            raise ValueError("invalid pass mask")
        direct_scope_mask = hexadecimal(event, "direct_scope_mask", 8)
        packet_lineage_mask = hexadecimal(event, "packet_lineage_mask", 8)
        if (
            direct_scope_mask & ~0xF
            or packet_lineage_mask & ~0xF
            or direct_scope_mask | packet_lineage_mask != pass_mask
        ):
            raise ValueError("invalid attribution masks")
        bits = hexadecimal(event, "bound_render_target_bits", 8)
        viewport = hexadecimal_tuple(event, "viewport", 4)
        viewport_control = hexadecimal(event, "viewport_transform_control", 8)
        scissor = hexadecimal_tuple(event, "scissor", 2)
        target_state = hexadecimal_tuple(event, "target_state", 6)
        vertex_shader = str(event.get("vertex_shader", "")).upper()
        pixel_shader = str(event.get("pixel_shader", "")).upper()
        if len(vertex_shader) != 16 or len(pixel_shader) != 16:
            raise ValueError("invalid shader hash")
        calls = integer(event, "calls")
        if not calls:
            raise ValueError("empty prepared target entry")
        entry_calls += calls
        for index, slot in enumerate(SLOTS):
            if not pass_mask & (1 << index):
                continue
            row = per_slot[str(slot)]
            row["calls"] += calls
            direct = bool(direct_scope_mask & (1 << index))
            packet = bool(packet_lineage_mask & (1 << index))
            source = (
                "direct_scope_and_packet_lineage"
                if direct and packet
                else "direct_scope"
                if direct
                else "packet_lineage"
            )
            row["attribution_sources"][source] = (
                row["attribution_sources"].get(source, 0) + calls
            )
            shape = target_shape(bits)
            row["target_shapes"][shape] = row["target_shapes"].get(shape, 0) + calls
            pair = f"{vertex_shader}:{pixel_shader}"
            row["shader_pairs"][pair] = row["shader_pairs"].get(pair, 0) + calls
            spatial = (
                f"{scissor_extent(scissor)}:"
                f"{':'.join(f'{value:08X}' for value in viewport)}:"
                f"{viewport_control:08X}"
            )
            row["spatial_states"][spatial] = (
                row["spatial_states"].get(spatial, 0) + calls
            )
            target = ":".join(f"{value:08X}" for value in target_state)
            row["target_states"][target] = (
                row["target_states"].get(target, 0) + calls
            )

    receiver_observations = integer(summary, "receiver_observations")
    receiver_entry_count = integer(summary, "receiver_entries")
    receiver_read_faults = integer(summary, "receiver_read_faults")
    receiver_overflow = integer(summary, "receiver_overflow")
    receiver_entries = [
        event for event in selected if event.get("event") == RECEIVER
    ]
    receiver_calls = 0
    receiver_profiles = {str(slot): {} for slot in SLOTS}
    for event in receiver_entries:
        require_safety(event)
        pass_mask = hexadecimal(event, "pass_mask", 8)
        if not pass_mask or pass_mask & ~0xF or pass_mask.bit_count() != 1:
            raise ValueError("invalid receiver pass mask")
        receiver_vtable = str(event.get("receiver_vtable", "")).upper()
        if len(receiver_vtable) != 8 or any(
            c not in "0123456789ABCDEF" for c in receiver_vtable
        ):
            raise ValueError("invalid receiver vtable")
        calls = integer(event, "calls")
        if not calls:
            raise ValueError("empty receiver entry")
        receiver_calls += calls
        slot = SLOTS[pass_mask.bit_length() - 1]
        receiver_profiles[str(slot)][receiver_vtable] = calls

    failures = []
    if summary.get("status") not in ("complete", "not_observed"):
        failures.append("track presentation summary is incomplete")
    if summary.get("accounting_complete") != "true":
        failures.append("track presentation accounting is incomplete")
    if summary.get("prepared_target_accounting_complete") != "true":
        failures.append("prepared target accounting is incomplete")
    if prepared_entries != len(entries):
        failures.append("prepared target entry count drifted")
    if prepared_observations != entry_calls + prepared_overflow:
        failures.append("prepared target call accounting drifted")
    if prepared_overflow:
        failures.append("prepared target table overflowed")
    if summary.get("receiver_accounting_complete") != "true":
        failures.append("receiver accounting is incomplete")
    if receiver_entry_count != len(receiver_entries):
        failures.append("receiver entry count drifted")
    if receiver_observations != receiver_calls + receiver_overflow:
        failures.append("receiver call accounting drifted")
    if receiver_read_faults:
        failures.append("presentation receiver reads faulted")
    if receiver_overflow:
        failures.append("presentation receiver table overflowed")
    if not total_slot_entries:
        failures.append("no unified track presentation pass was observed")
    for slot, row in slot_totals.items():
        adapter = row["adapter_route"]
        if not (
            adapter["dispatches"]
            <= adapter["eligible"]
            <= adapter["enabled"]
            <= adapter["entries"]
        ):
            failures.append(f"slot {slot} adapter stage accounting drifted")
        has_target = adapter["first_target"] != "00000000"
        if has_target != bool(adapter["dispatches"]):
            failures.append(f"slot {slot} adapter target accounting drifted")
        if adapter["target_changes"] >= max(adapter["dispatches"], 1):
            failures.append(f"slot {slot} adapter target changes drifted")

    live_slots = [slot for slot in SLOTS if slot_totals[str(slot)]["entries"]]
    accepted_slots = [slot for slot in SLOTS if slot_totals[str(slot)]["exact"]]
    color_slots = [
        slot
        for slot in SLOTS
        if per_slot[str(slot)]["target_shapes"].get("color_only", 0)
        or per_slot[str(slot)]["target_shapes"].get("color_and_depth", 0)
    ]
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "slot_totals": slot_totals,
        "prepared_target_totals": {
            "observations": prepared_observations,
            "entries": prepared_entries,
            "overflow": prepared_overflow,
        },
        "prepared_targets_by_slot": per_slot,
        "runtime_receivers_by_slot": receiver_profiles,
        "qualification": {
            "live_slots": live_slots,
            "accepted_receiver_slots": accepted_slots,
            "color_target_slots": color_slots,
            "opaque_world_slot_proved": False,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "next_step": (
            "follow a live adapter target or extend exact packet lineage only "
            "through a live color-producing slot, then visually qualify its "
            "private replay"
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
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if document["status"] != "complete":
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"track presentation summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
