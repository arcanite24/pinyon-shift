#!/usr/bin/env python3
"""Promote a stable adjacent pass follower from independent census captures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "pinyon-shift.native-renderer-pass-follower.v1"
CONTRACT_FIELDS = (
    "follower_signature",
    "vertex_shader",
    "pixel_shader",
    "vertex_specialization_mask",
    "pixel_specialization_mask",
    "prepared_pipeline_hash",
    "host_primitive",
    "host_index_buffer_type",
    "host_index_format",
    "host_primitive_reset",
    "prepared_pipeline_flags",
    "bound_render_target_bits",
    "primitive",
    "source_select",
    "indexed",
    "index_count",
    "index_state",
    "vertex_binding_count",
    "vertex_attribute_count",
    "texture_fetch_count",
    "pipeline_state",
    "query",
    "memexport",
    "resolved_input",
    "mechanically_eligible",
)


def load_capture(path: Path, anchor: str) -> dict[str, Any]:
    summary = json.loads(path.read_text(encoding="utf-8"))
    followers = [
        item
        for item in summary.get("pass_followers", [])
        if item.get("anchor_signature") == anchor and item.get("status") != "not_observed"
    ]
    if len(followers) != 1:
        raise ValueError(f"{path}: expected exactly one observed follower, found {len(followers)}")
    follower = followers[0]
    if int(follower["follower_frame"]) != int(follower["anchor_frame"]):
        raise ValueError(f"{path}: follower crosses a frame boundary")
    if int(follower["follower_draw"]) != int(follower["anchor_draw"]) + 1:
        raise ValueError(f"{path}: follower is not draw-adjacent")
    for field in ("query", "memexport", "resolved_input", "suppression_eligible"):
        if follower.get(field) != "false":
            raise ValueError(f"{path}: unsafe follower field {field}={follower.get(field)!r}")
    if follower.get("native_draw") != "false" or follower.get("xenos_draw") != "preserved":
        raise ValueError(f"{path}: Xenos authority was not preserved")
    return follower


def select(paths: list[Path], anchor: str) -> dict[str, Any]:
    if len(paths) < 2:
        raise ValueError("at least two independent captures are required")
    records = [load_capture(path, anchor) for path in paths]
    contract = {field: records[0].get(field) for field in CONTRACT_FIELDS}
    for path, record in zip(paths[1:], records[1:]):
        drift = [field for field, expected in contract.items() if record.get(field) != expected]
        if drift:
            raise ValueError(f"{path}: follower contract drift: {', '.join(drift)}")
    return {
        "schema": SCHEMA,
        "anchor_signature": anchor,
        "follower_signature": contract["follower_signature"],
        "captures": len(paths),
        "contract": contract,
        "qualification": "stable_adjacent_metadata_contract",
        "safety": {
            "guest_payload_read": False,
            "native_upload": False,
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
        "sources": [str(path) for path in paths],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = select(args.captures, args.anchor.upper())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
