#!/usr/bin/env python3
"""Join exact procedural color targets to their contiguous resolve assembly."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-procedural-resolve-assembly.v1"
CONFIG = "native_renderer.discovery.command_buffer_lineage_config"
PROFILE = "native_renderer.discovery.procedural_color_target_profile_entry"
PROFILE_SUMMARY = (
    "native_renderer.discovery.procedural_color_target_profile_summary"
)
RESOLVE = "native_renderer.census.resolve_target"
SHUTDOWN = "process.shutdown"

# Xenos ColorFormat storage sizes for the formats useful to the native renderer.
COLOR_BYTES_PER_PIXEL = {
    2: 1,
    3: 2,
    4: 2,
    5: 2,
    6: 4,
    7: 4,
    8: 1,
    9: 1,
    10: 2,
    14: 4,
    15: 2,
    16: 4,
    17: 4,
    24: 2,
    25: 4,
    26: 8,
    30: 2,
    31: 4,
    32: 8,
    36: 4,
    37: 8,
    38: 16,
    50: 8,
    54: 8,
    55: 8,
    56: 8,
}


def integer(event, name):
    try:
        return int(event[name], 10)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {name}") from error


def hexadecimal(event, name):
    try:
        return int(event[name], 16)
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


def split_hex_words(value, count, name):
    if not isinstance(value, str):
        raise ValueError(f"invalid {name}")
    words = value.split(":")
    if len(words) != count:
        raise ValueError(f"invalid {name}")
    try:
        return tuple(int(word, 16) for word in words)
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error


def profile_sources(event):
    target = split_hex_words(event.get("target_state"), 6, "target_state")
    return {(target[0], source, target[source + 1]) for source in range(4)}


def copy_state(event):
    return split_hex_words(event.get("copy_state"), 4, "copy_state")


def latest_resolves(events):
    latest = {}
    for event in events:
        address = hexadecimal(event, "address")
        previous = latest.get(address)
        if previous is None or integer(event, "last_resolve_frame") >= integer(
            previous, "last_resolve_frame"
        ):
            latest[address] = event
    return latest


def contiguous_chains(rows):
    chains = []
    for row in sorted(rows, key=lambda item: item["address"]):
        if chains and chains[-1][-1]["address"] + chains[-1][-1]["length"] == row[
            "address"
        ]:
            chains[-1].append(row)
        else:
            chains.append([row])
    return chains


def build(events, session):
    configs = [event for event in events if event.get("event") == CONFIG]
    profiles = [event for event in events if event.get("event") == PROFILE]
    summaries = [event for event in events if event.get("event") == PROFILE_SUMMARY]
    shutdowns = [event for event in events if event.get("event") == SHUTDOWN]
    failures = []
    if len(configs) != 1:
        failures.append("expected one command-lineage config")
    elif configs[0].get("procedural_color_resolve_source_state") != "exact_backend_v1":
        failures.append("exact resolve source state was not armed")
    if len(summaries) != 1 or summaries[0].get("accounting_complete") != "true":
        failures.append("complete procedural color-target accounting was not observed")
    if not profiles:
        failures.append("procedural color-target profiles were not observed")
    if len(shutdowns) != 1:
        failures.append("clean process shutdown was not observed")

    profile_first = min(
        (integer(event, "first_frame") for event in profiles), default=0
    )
    profile_last = max((integer(event, "last_frame") for event in profiles), default=0)
    sources = set()
    for profile in profiles:
        sources.update(profile_sources(profile))

    resolve_events = [event for event in events if event.get("event") == RESOLVE]
    selected = []
    for event in latest_resolves(resolve_events).values():
        source = integer(event, "copy_source")
        if source >= 4:
            continue
        source_surface, source_info = split_hex_words(
            event.get("copy_source_state"), 2, "copy_source_state"
        )
        last_frame = integer(event, "last_resolve_frame")
        if (source_surface, source, source_info) not in sources:
            continue
        if not profile_first <= last_frame <= profile_last:
            continue
        control, destination_info, destination_pitch, surface = copy_state(event)
        selected.append(
            {
                "address": hexadecimal(event, "address"),
                "length": integer(event, "length"),
                "last_frame": last_frame,
                "source": source,
                "source_state": f"{source_surface:08X}:{source_info:08X}",
                "control": control,
                "destination_info": destination_info,
                "destination_pitch": destination_pitch,
                "surface": surface,
            }
        )

    groups = {}
    for row in selected:
        key = (
            row["source"],
            row["source_state"],
            row["destination_info"],
            row["destination_pitch"],
        )
        groups.setdefault(key, []).append(row)

    assemblies = []
    for key, rows in groups.items():
        source, source_state, destination_info, destination_pitch = key
        pitch_width = destination_pitch & 0x3FFF
        logical_height = (destination_pitch >> 16) & 0x3FFF
        color_format = (destination_info >> 7) & 0x3F
        bytes_per_pixel = COLOR_BYTES_PER_PIXEL.get(color_format)
        for chain in contiguous_chains(rows):
            total_bytes = sum(row["length"] for row in chain)
            padded_height = None
            if bytes_per_pixel and pitch_width:
                row_bytes = pitch_width * bytes_per_pixel
                if total_bytes % row_bytes == 0:
                    padded_height = total_bytes // row_bytes
            exact_full_frame = (
                len(chain) > 1
                and bytes_per_pixel is not None
                and pitch_width == 1280
                and logical_height == 720
                and padded_height is not None
                and logical_height <= padded_height < logical_height + 64
            )
            assemblies.append(
                {
                    "source": source,
                    "source_state": source_state,
                    "base_address": f"{chain[0]['address']:08X}",
                    "addresses": [f"{row['address']:08X}" for row in chain],
                    "lengths": [row["length"] for row in chain],
                    "copy_count": len(chain),
                    "total_bytes": total_bytes,
                    "destination_info": f"{destination_info:08X}",
                    "destination_pitch": f"{destination_pitch:08X}",
                    "color_format": color_format,
                    "bytes_per_pixel": bytes_per_pixel,
                    "pitch_width": pitch_width,
                    "logical_height": logical_height,
                    "padded_height": padded_height,
                    "padding_rows": (
                        padded_height - logical_height
                        if padded_height is not None
                        else None
                    ),
                    "exact_contiguous_full_frame": exact_full_frame,
                }
            )

    assemblies.sort(
        key=lambda row: (
            not row["exact_contiguous_full_frame"],
            -row["total_bytes"],
            row["base_address"],
        )
    )
    exact = [row for row in assemblies if row["exact_contiguous_full_frame"]]
    if not exact and not failures:
        failures.append("no exact contiguous full-frame color resolve assembly")
    complete = not failures
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if complete else "incomplete",
        "failures": failures,
        "profile_window": {"first_frame": profile_first, "last_frame": profile_last},
        "assemblies": assemblies,
        "qualification": {
            "exact_procedural_color_resolve_assembly": complete and bool(exact),
            "standalone_1280x256_publication_allowed": False,
            "logical_extent": "1280x720" if complete and exact else None,
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
        print(f"procedural resolve-assembly summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
