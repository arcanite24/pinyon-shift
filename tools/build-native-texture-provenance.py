#!/usr/bin/env python3
"""Build a bounded cross-capture NR-02 texture provenance contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SCHEMA = "pinyon-shift.native-texture-provenance.v1"
CENSUS_SCHEMA = "pinyon-shift.native-renderer-census.v1"


def integer(record: dict[str, Any], field: str) -> int:
    try:
        return int(record[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"texture fingerprint has invalid {field}") from exc


def build(captures: list[dict[str, Any]], signature: str) -> dict[str, Any]:
    if len(captures) < 2:
        raise ValueError("texture provenance requires at least two captures")
    if len(signature) != 16 or any(character not in "0123456789abcdefABCDEF" for character in signature):
        raise ValueError("texture provenance requires a 16-digit signature")
    signature = signature.upper()

    normalized: list[dict[int, dict[str, Any]]] = []
    sessions: list[str] = []
    for capture in captures:
        if capture.get("schema") != CENSUS_SCHEMA:
            raise ValueError("unsupported census schema")
        sessions.append(str(capture.get("session", "")))
        scans = [
            record for record in capture.get("texture_scans", [])
            if record.get("signature") == signature and record.get("status") == "scanned"
        ]
        if len(scans) != 1:
            raise ValueError("each capture must contain one successful texture scan")
        expected = integer(scans[0], "resources")
        records = [
            record for record in capture.get("texture_fingerprints", [])
            if record.get("signature") == signature
        ]
        if len(records) != expected or not 1 <= expected <= 4:
            raise ValueError("texture fingerprint count does not match the scan")
        by_fetch: dict[int, dict[str, Any]] = {}
        for record in records:
            fetch = integer(record, "fetch_constant")
            if fetch in by_fetch or not 0 <= fetch < 32:
                raise ValueError("texture fingerprints have duplicate or invalid fetch constants")
            base_bytes = integer(record, "base_bytes")
            mip_bytes = integer(record, "mip_bytes")
            base_hash = str(record.get("base_hash", ""))
            mip_hash = str(record.get("mip_hash", ""))
            if base_bytes <= 0 or len(base_hash) != 16:
                raise ValueError("texture fingerprint has invalid base content")
            if (mip_bytes == 0 and mip_hash) or (mip_bytes > 0 and len(mip_hash) != 16):
                raise ValueError("texture fingerprint has invalid mip content")
            by_fetch[fetch] = {
                "base_address": str(record.get("base_address", "")),
                "base_bytes": base_bytes,
                "base_hash": base_hash,
                "mip_address": str(record.get("mip_address", "")),
                "mip_bytes": mip_bytes,
                "mip_hash": mip_hash,
            }
        normalized.append(by_fetch)

    fetches = sorted(normalized[0])
    if any(sorted(capture) != fetches for capture in normalized[1:]):
        raise ValueError("texture fetch identities differ across captures")

    resources: list[dict[str, Any]] = []
    for fetch in fetches:
        observations = [capture[fetch] for capture in normalized]
        content_keys = {
            (
                item["base_bytes"], item["base_hash"],
                item["mip_bytes"], item["mip_hash"],
            )
            for item in observations
        }
        if len(content_keys) != 1:
            raise ValueError(f"texture fetch {fetch} content differs across captures")
        addresses = {
            (item["base_address"], item["mip_address"])
            for item in observations
        }
        first = observations[0]
        resources.append({
            "fetch_constant": fetch,
            "base_bytes": first["base_bytes"],
            "base_hash": first["base_hash"],
            "mip_bytes": first["mip_bytes"],
            "mip_hash": first["mip_hash"],
            "addresses_relocated_across_captures": len(addresses) > 1,
        })

    return {
        "schema": SCHEMA,
        "candidate_signature": signature,
        "capture_count": len(captures),
        "sessions": sessions,
        "resource_count": len(resources),
        "resources": resources,
        "qualification": {
            "content_stable_across_captures": True,
            "source_texture_candidate": True,
            "visual_identity_confirmed": False,
            "dynamic_render_target_exclusion_required": True,
        },
        "safety": {
            "guest_payload_read": "bounded_texture_only",
            "payload_persisted": False,
            "native_upload": False,
            "native_draw": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    captures = [json.loads(path.read_text(encoding="utf-8")) for path in args.captures]
    result = build(captures, args.signature)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
