#!/usr/bin/env python3
"""Rank exact unified track-presentation slots by graphics call paths."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-track-presentation-callgraph.v1"
IMAGE_BASE = 0x82000000
UNIFIED_VTABLE = 0x82243774
WRAPPER_VTABLE = 0x82003CCC
SLOT_COUNT = 135
MAXIMUM_DEPTH = 6
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")
CALL_RE = re.compile(r"\bsub_([0-9A-F]{8})\(ctx, base\)")
SINKS = {
    0x82416380: "direct_indexed_draw",
    0x82436468: "track_dispatcher",
    0x824365B0: "track_command_context",
    0x82417BC0: "procedural_model_dispatch",
    0x82C4CCC8: "simple_model_renderer",
    0x82C5ADC0: "unified_track_mesh_draw",
}


def image_u32(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise ValueError(f"image address is out of range: {address:08X}")
    return int.from_bytes(image[offset : offset + 4], "big")


def read_vtable(image: bytes, address: int) -> list[int]:
    return [image_u32(image, address + 4 * slot) for slot in range(SLOT_COUNT)]


def parse_generated(paths: list[pathlib.Path]):
    graph = collections.defaultdict(set)
    indirect_calls = collections.Counter()
    current = None
    for path in sorted(paths, key=lambda item: item.as_posix()):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = FUNCTION_RE.match(line)
            if match:
                current = int(match.group(1), 16)
                graph[current]
                continue
            if current is None:
                continue
            graph[current].update(int(value, 16) for value in CALL_RE.findall(line))
            if "REX_CALL_INDIRECT_FUNC" in line:
                indirect_calls[current] += 1
    return {key: tuple(sorted(value)) for key, value in graph.items()}, indirect_calls


def trace(source: int, graph, indirect_calls):
    queue = collections.deque([(source, (source,))])
    visited = {source}
    sink_paths = {}
    reachable_indirect_calls = 0
    while queue:
        address, path = queue.popleft()
        reachable_indirect_calls += indirect_calls.get(address, 0)
        if address in SINKS and address != source:
            sink_paths.setdefault(SINKS[address], path)
        if len(path) > MAXIMUM_DEPTH:
            continue
        for target in graph.get(address, ()):
            if target in visited:
                continue
            visited.add(target)
            queue.append((target, (*path, target)))
    return {
        "reachable_function_count": len(visited),
        "reachable_indirect_calls": reachable_indirect_calls,
        "sink_paths": {
            name: [f"{address:08X}" for address in path]
            for name, path in sorted(sink_paths.items())
        },
    }


def build(graph, indirect_calls, unified_slots, wrapper_slots):
    if len(unified_slots) != SLOT_COUNT or len(wrapper_slots) != SLOT_COUNT:
        raise ValueError("track-presentation vtable length drifted")
    rows = []
    for slot, (unified, wrapper) in enumerate(zip(unified_slots, wrapper_slots)):
        evidence = trace(wrapper, graph, indirect_calls)
        rows.append(
            {
                "slot": slot,
                "unified_target": f"{unified:08X}",
                "wrapper_target": f"{wrapper:08X}",
                "wrapper_matches_unified": wrapper == unified,
                **evidence,
            }
        )
    candidates = [
        row
        for row in rows
        if row["sink_paths"] or row["reachable_indirect_calls"]
    ]
    candidates.sort(
        key=lambda row: (
            not bool(row["sink_paths"]),
            min(
                (len(path) for path in row["sink_paths"].values()),
                default=UINT_MAX,
            ),
            -row["reachable_indirect_calls"],
            row["slot"],
        )
    )
    return {
        "schema": SCHEMA,
        "status": "complete",
        "maximum_call_depth": MAXIMUM_DEPTH,
        "slot_count": SLOT_COUNT,
        "candidate_count": len(candidates),
        "sinks": {f"{address:08X}": name for address, name in SINKS.items()},
        "candidates": candidates,
        "slots": rows,
        "qualification": {
            "exact_runtime_wrapper_vtable_enumerated": True,
            "direct_static_graphics_paths_ranked": True,
            "runtime_activity_proved": False,
            "color_target_proved": False,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "static_analysis_only": True,
            "guest_payload_exported": False,
            "runtime_hook_enabled": False,
            "xenos_authority_required": True,
        },
    }


UINT_MAX = (1 << 63) - 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated_root", type=pathlib.Path)
    parser.add_argument("--image", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        paths = list(args.generated_root.glob("pinyon_shift_recomp.*.cpp"))
        if not paths:
            raise ValueError("no generated AOT C++ files found")
        graph, indirect_calls = parse_generated(paths)
        image = args.image.read_bytes()
        document = build(
            graph,
            indirect_calls,
            read_vtable(image, UNIFIED_VTABLE),
            read_vtable(image, WRAPPER_VTABLE),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"track-presentation callgraph discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
