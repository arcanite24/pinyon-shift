#!/usr/bin/env python3
"""Shortlist repeatable NR-02 draw candidates from local census inventories."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA = "pinyon-shift.native-renderer-candidate-selection.v1"
CENSUS_SCHEMA = "pinyon-shift.native-renderer-census.v1"
SHADER_SCHEMA = "pinyon-shift.native-shader-pack.v1"
PHYSICAL_MASK = 0x1FFFFFFF
MAX_TEXTURE_RESOURCES = 4


def boolean(record: dict[str, Any], key: str) -> bool:
    value = record.get(key)
    if value not in ("true", "false", True, False):
        raise ValueError(f"draw signature has invalid {key}: {value!r}")
    return value in ("true", True)


def load_json(path: Path, schema: str) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != schema:
        raise ValueError(f"unsupported schema in {path}: {document.get('schema')}")
    return document


def shader_identities(manifest: dict[str, Any]) -> set[tuple[str, str, str]]:
    identities: set[tuple[str, str, str]] = set()
    for entry in manifest.get("entries", []):
        stage = str(entry.get("stage", ""))
        guest_hash = str(entry.get("guest_hash", "")).upper()
        specialization = str(entry.get("specialization_mask", "")).upper()
        if (
            stage not in ("vertex", "pixel")
            or len(guest_hash) != 16
            or len(specialization) != 16
        ):
            raise ValueError("shader manifest contains an invalid identity")
        identity = (stage, guest_hash, specialization)
        if identity in identities:
            raise ValueError("shader manifest contains a duplicate identity")
        identities.add(identity)
    return identities


def rejection_reasons(record: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not boolean(record, "opaque"):
        reasons.append("non_opaque")
    if boolean(record, "query"):
        reasons.append("query_state")
    if boolean(record, "memexport"):
        reasons.append("memexport")
    if boolean(record, "resolved_input"):
        reasons.append("dynamic_render_target_input")
    if boolean(record, "vertex_overflow"):
        reasons.append("vertex_binding_overflow")
    if boolean(record, "vertex_attribute_overflow"):
        reasons.append("vertex_attribute_overflow")
    if boolean(record, "constant_overflow"):
        reasons.append("constant_observer_overflow")
    if boolean(record, "texture_state_overflow"):
        reasons.append("texture_state_observer_overflow")
    if int(record.get("vertex_binding_count", 0)) != 1:
        reasons.append("vertex_binding_count_not_one")
    texture_count = int(record.get("texture_fetch_count", 0))
    if texture_count < 1 or texture_count > MAX_TEXTURE_RESOURCES:
        reasons.append("texture_count_outside_1_to_4")
    return reasons


def texture_addresses(record: dict[str, Any]) -> set[int]:
    count = int(record.get("texture_state_count", 0))
    values = str(record.get("texture_states") or "").split(";") if count else []
    if len(values) != count:
        raise ValueError("candidate texture-state count is inconsistent")
    addresses: set[int] = set()
    for value in values:
        fields = value.split(":")
        if len(fields) != 18:
            raise ValueError(f"candidate has invalid texture state: {value!r}")
        words = [int(field, 16) for field in fields[2:8]]
        addresses.add(((words[1] >> 12) << 12) & PHYSICAL_MASK)
        mip_address = ((words[5] >> 12) << 12) & PHYSICAL_MASK
        if mip_address:
            addresses.add(mip_address)
    return addresses


def resolve_ranges(census: dict[str, Any]) -> list[tuple[int, int]]:
    ranges = []
    for target in census.get("resolve_targets", []):
        start = int(str(target.get("address", "0")), 16) & PHYSICAL_MASK
        length = int(target.get("length", 0))
        if length <= 0 or start + length > PHYSICAL_MASK + 1:
            raise ValueError("resolve target has an invalid physical range")
        ranges.append((start, start + length))
    return ranges


def reads_known_resolve_target(
    record: dict[str, Any], ranges: list[tuple[int, int]]
) -> bool:
    return any(
        start <= address < end
        for address in texture_addresses(record)
        for start, end in ranges
    )


def prepared_pairs(census: dict[str, Any]) -> dict[tuple[str, str], set[tuple[str, str]]]:
    result: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for record in census.get("prepared_shader_pairs", []):
        shader_pair = (
            str(record.get("vertex_shader", "")).upper(),
            str(record.get("pixel_shader", "")).upper(),
        )
        specialization_pair = (
            str(record.get("vertex_specialization_mask", "")).upper(),
            str(record.get("pixel_specialization_mask", "")).upper(),
        )
        if any(len(value) != 16 for value in shader_pair + specialization_pair):
            raise ValueError("prepared shader pair contains an invalid identity")
        result.setdefault(shader_pair, set()).add(specialization_pair)
    return result


def select(census_paths: list[Path], shader_manifest_path: Path) -> dict[str, Any]:
    if len(census_paths) < 2:
        raise ValueError("at least two census inventories are required")
    censuses = [load_json(path, CENSUS_SCHEMA) for path in census_paths]
    scenes = {str(item.get("classification", {}).get("scene", "unmarked")) for item in censuses}
    if len(scenes) != 1:
        raise ValueError("candidate inventories must use the same scene marker")
    shaders = shader_identities(load_json(shader_manifest_path, SHADER_SCHEMA))
    prepared_by_capture = [prepared_pairs(census) for census in censuses]
    resolve_ranges_by_capture = [resolve_ranges(census) for census in censuses]

    by_capture: list[dict[str, dict[str, Any]]] = []
    for census in censuses:
        by_capture.append(
            {str(record["signature"]): record for record in census.get("draw_candidates", [])}
        )
    repeated = set(by_capture[0])
    for capture in by_capture[1:]:
        repeated.intersection_update(capture)

    candidates: list[dict[str, Any]] = []
    rejection_counts: Counter[str] = Counter()
    for signature in sorted(repeated):
        records = [capture[signature] for capture in by_capture]
        reasons = rejection_reasons(records[0])
        if any(
            reads_known_resolve_target(record, ranges)
            for record, ranges in zip(records, resolve_ranges_by_capture)
        ) and "dynamic_render_target_input" not in reasons:
            reasons.append("dynamic_render_target_input")
        for reason in reasons:
            rejection_counts[reason] += 1
        if reasons:
            continue
        if any(rejection_reasons(record) for record in records[1:]):
            rejection_counts["state_changed_across_captures"] += 1
            continue
        shader_pair = (
            str(records[0].get("vertex_shader", "")).upper(),
            str(records[0].get("pixel_shader", "")).upper(),
        )
        candidate_specializations = [
            (
                str(record.get("vertex_specialization_mask", "")).upper(),
                str(record.get("pixel_specialization_mask", "")).upper(),
            )
            for record in records
        ]
        if any(
            len(value) != 16
            for specialization in candidate_specializations
            for value in specialization
        ):
            rejection_counts["missing_candidate_specialization"] += 1
            continue
        if len(set(candidate_specializations)) != 1:
            rejection_counts["specialization_changed_across_captures"] += 1
            continue
        vertex_specialization, pixel_specialization = candidate_specializations[0]
        if any(
            candidate_specializations[index]
            not in prepared_by_capture[index].get(shader_pair, set())
            for index in range(len(censuses))
        ):
            rejection_counts["missing_prepared_shader_pair"] += 1
            continue
        if ("vertex", shader_pair[0], vertex_specialization) not in shaders:
            rejection_counts["missing_vertex_shader_specialization"] += 1
            continue
        if shader_pair[1] != "0000000000000000" and (
            "pixel", shader_pair[1], pixel_specialization
        ) not in shaders:
            rejection_counts["missing_pixel_shader_specialization"] += 1
            continue
        total_draws = sum(int(record.get("draws", 0)) for record in records)
        sample = records[0]
        candidates.append(
            {
                "signature": signature,
                "captures": len(records),
                "total_draws": total_draws,
                "vertex_shader": sample["vertex_shader"],
                "pixel_shader": sample["pixel_shader"],
                "vertex_specialization_mask": vertex_specialization,
                "pixel_specialization_mask": pixel_specialization,
                "primitive": sample.get("primitive"),
                "indexed": boolean(sample, "indexed"),
                "source_select": int(sample.get("source_select", 0)),
                "index_count_min": min(
                    int(record.get("index_count_min", 0)) for record in records
                ),
                "index_count_max": max(
                    int(record.get("index_count_max", 0)) for record in records
                ),
                "index_state": sample.get("index_state"),
                "index_buffer_address": sample.get("index_buffer_address"),
                "index_buffer_length_min": min(
                    int(record.get("index_buffer_length_min", 0))
                    for record in records
                ),
                "vertex_index_range": sample.get("vertex_index_range"),
                "vertex_binding_count": int(
                    sample.get("vertex_binding_count", 0)
                ),
                "vertex_fetches": sample.get("vertex_fetches"),
                "vertex_attribute_count": int(
                    sample.get("vertex_attribute_count", 0)
                ),
                "vertex_attributes": sample.get("vertex_attributes"),
                "texture_fetch_count": int(sample.get("texture_fetch_count", 0)),
                "draw_state_hashes": [
                    str(record.get("draw_state_hash", "")).upper()
                    for record in records
                ],
                "vertex_float_constant_count": int(
                    sample.get("vertex_float_constant_count", 0)
                ),
                "vertex_float_constants": sample.get("vertex_float_constants"),
                "pixel_float_constant_count": int(
                    sample.get("pixel_float_constant_count", 0)
                ),
                "pixel_float_constants": sample.get("pixel_float_constants"),
                "bool_constants": sample.get("bool_constants"),
                "loop_constants": sample.get("loop_constants"),
                "texture_state_count": int(sample.get("texture_state_count", 0)),
                "texture_states": sample.get("texture_states"),
                "pipeline_state": sample.get("pipeline_state"),
                "qualification": "metadata_shortlist_only",
            }
        )
    candidates.sort(key=lambda item: (-item["captures"], -item["total_draws"], item["signature"]))
    return {
        "schema": SCHEMA,
        "scene": next(iter(scenes)),
        "capture_count": len(censuses),
        "repeated_signature_count": len(repeated),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rejections": [
            {"reason": reason, "signatures": count}
            for reason, count in sorted(rejection_counts.items())
        ],
        "safety": {
            "selection_status": "needs_visual_and_dependency_review",
            "suppression_allowed": False,
            "xenos_authority": True,
            "absence_of_resolved_input_is_not_static_texture_proof": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("census", nargs="+", type=Path)
    parser.add_argument("--shader-manifest", required=True, type=Path)
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = select(args.census, args.shader_manifest)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
