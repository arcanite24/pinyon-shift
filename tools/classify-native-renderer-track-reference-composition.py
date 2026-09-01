#!/usr/bin/env python3
"""Match track-local matrices composed with title reference matrices."""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import math
import pathlib
import struct
import sys


SCHEMA = "pinyon-shift.native-renderer-track-reference-composition-classification.v1"
REFERENCE_ENTRY = "native_renderer.discovery.track_world_reference_spatial_entry"
SOURCE_TOOL = pathlib.Path(__file__).with_name(
    "classify-native-renderer-track-scope-spatial.py"
)
SPEC = importlib.util.spec_from_file_location("track_scope_spatial", SOURCE_TOOL)
SCOPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOPE)


def floats(words):
    values = tuple(
        struct.unpack(">f", word.to_bytes(4, "big"))[0] for word in words
    )
    return values if all(math.isfinite(value) for value in values) else None


def multiply(left, right):
    result = tuple(
        sum(left[row * 4 + inner] * right[inner * 4 + column] for inner in range(4))
        for row in range(4)
        for column in range(4)
    )
    return result if all(math.isfinite(value) for value in result) else None


def parse_scope_entries(selected):
    result = {}
    calls = 0
    for event in selected:
        if event.get("event") != SCOPE.ENTRY:
            continue
        SCOPE.require_safety(event)
        child_address = SCOPE.hexadecimal(event.get("child_address", ""), 8, "child address")
        descriptor_address = SCOPE.hexadecimal(event.get("descriptor_address", ""), 8, "descriptor address")
        snapshot_hash = SCOPE.hexadecimal(event.get("snapshot_hash", ""), 16, "scope snapshot hash")
        key = (child_address, descriptor_address, snapshot_hash)
        if key in result or SCOPE.integer(event, "snapshot_variations"):
            raise ValueError("track-scope spatial source is duplicate or unstable")
        entry_calls = SCOPE.integer(event, "calls")
        calls += entry_calls
        result[key] = {
            "child": SCOPE.parse_words(event, "child", 16),
            "descriptor": SCOPE.parse_words(event, "descriptor", 62),
        }
    return result, calls


def parse_reference_entries(selected, scopes):
    result = []
    calls = 0
    seen = set()
    for event in selected:
        if event.get("event") != REFERENCE_ENTRY:
            continue
        SCOPE.require_safety(event)
        snapshot_key = SCOPE.hexadecimal(event.get("snapshot_key", ""), 16, "reference snapshot key")
        if snapshot_key in seen:
            raise ValueError("duplicate track reference snapshot key")
        seen.add(snapshot_key)
        source_key = (
            SCOPE.hexadecimal(event.get("child_address", ""), 8, "child address"),
            SCOPE.hexadecimal(event.get("descriptor_address", ""), 8, "descriptor address"),
            SCOPE.hexadecimal(event.get("scope_snapshot_hash", ""), 16, "scope snapshot hash"),
        )
        if source_key not in scopes:
            raise ValueError("track reference snapshot has no scope source")
        entry_calls = SCOPE.integer(event, "calls")
        if not entry_calls or SCOPE.integer(event, "first_frame") > SCOPE.integer(event, "last_frame"):
            raise ValueError("invalid track reference lifetime")
        calls += entry_calls
        result.append({
            "snapshot_key": snapshot_key,
            "scope": scopes[source_key],
            "object_matrix": SCOPE.parse_words(event, "object_matrix", 16),
            "composed_matrix": SCOPE.parse_words(event, "composed_matrix", 16),
        })
    return result, calls


def build(events, catalog, requested_session=None, tolerance=SCOPE.DEFAULT_TOLERANCE,
          minimum_matches=SCOPE.DEFAULT_MINIMUM_MATCHES):
    if not math.isfinite(tolerance) or tolerance <= 0 or tolerance > 1:
        raise ValueError("match tolerance is outside the safe range")
    if minimum_matches < 1:
        raise ValueError("minimum matches must be positive")
    instances = SCOPE.validate_catalog(catalog)
    session, selected = SCOPE.select_session(events, requested_session)
    starts = [event for event in selected if event.get("event") == "process.start"]
    shutdowns = [event for event in selected if event.get("event") == "process.shutdown"]
    summaries = [event for event in selected if event.get("event") == SCOPE.SUMMARY]
    if len(starts) != 1 or len(shutdowns) != 1 or len(summaries) != 1:
        raise ValueError("track reference-composition lifecycle is incomplete")
    summary = summaries[0]
    SCOPE.require_safety(summary)
    if summary.get("checkpoint_kind") != "final":
        raise ValueError("track reference-composition summary is not final")
    scopes, scope_calls = parse_scope_entries(selected)
    references, reference_calls = parse_reference_entries(selected, scopes)
    if (
        len(scopes) != SCOPE.integer(summary, "scope_spatial_entries")
        or scope_calls != SCOPE.integer(summary, "scope_spatial_observations")
        or SCOPE.integer(summary, "scope_spatial_table_overflow")
        or summary.get("scope_spatial_accounting_complete") != "true"
        or len(references) != SCOPE.integer(summary, "reference_spatial_entries")
        or reference_calls != SCOPE.integer(summary, "reference_spatial_observations")
        or SCOPE.integer(summary, "reference_spatial_missing_stage")
        or SCOPE.integer(summary, "reference_spatial_table_overflow")
        or summary.get("reference_spatial_accounting_complete") != "true"
    ):
        raise ValueError("track reference-composition accounting is incomplete")

    groups = collections.defaultdict(list)
    for reference in references:
        reference_matrices = {
            source: floats(reference[source])
            for source in ("object_matrix", "composed_matrix")
        }
        if any(matrix is None for matrix in reference_matrices.values()):
            raise ValueError("track reference matrix is non-finite")
        for local_source in ("child", "descriptor"):
            local_words = reference["scope"][local_source]
            for word_offset in range(len(local_words) - 15):
                local = floats(local_words[word_offset : word_offset + 16])
                if local is None:
                    continue
                for reference_source, reference_matrix in reference_matrices.items():
                    products = {
                        "reference_times_local": multiply(reference_matrix, local),
                        "local_times_reference": multiply(local, reference_matrix),
                    }
                    for order, product in products.items():
                        if product is None:
                            continue
                        for convention, indices in SCOPE.CONVENTIONS.items():
                            groups[(local_source, word_offset, reference_source, order, convention)].append(
                                (reference["snapshot_key"], tuple(product[index] for index in indices))
                            )

    spatial = SCOPE.spatial_index(instances, tolerance)
    reports = []
    qualified = []
    for key, candidates in sorted(groups.items()):
        local_source, word_offset, reference_source, order, convention = key
        matches = []
        unmatched = 0
        ambiguous = 0
        for snapshot_key, position in candidates:
            outcome, match = SCOPE.match_position(spatial, position, tolerance)
            if outcome == "unmatched":
                unmatched += 1
            elif outcome == "ambiguous":
                ambiguous += 1
            else:
                distance, instance = match
                matches.append({
                    "snapshot_key": snapshot_key,
                    "category": instance["category"],
                    "catalog_identity_hash": instance["identity_hash"],
                    "catalog_index": instance["catalog_index"],
                    "distance": round(distance, 9),
                })
        distinct = len({item["catalog_index"] for item in matches})
        categories = collections.Counter(item["category"] for item in matches)
        complete = (
            len(candidates) == len(references)
            and len(matches) == len(references)
            and distinct >= minimum_matches
            and categories["collision_prop"] > 0
            and not unmatched
            and not ambiguous
        )
        report = {
            "local_source": local_source,
            "word_offset": word_offset,
            "reference_source": reference_source,
            "multiplication_order": order,
            "convention": convention,
            "observed_snapshots": len(candidates),
            "matched": len(matches),
            "distinct_catalog_matches": distinct,
            "unmatched": unmatched,
            "ambiguous": ambiguous,
            "category_counts": dict(sorted(categories.items())),
            "complete": complete,
            "matches": matches,
        }
        reports.append(report)
        if complete:
            qualified.append(report)

    failures = []
    if not references:
        failures.append("no exact track reference snapshots were observed")
    if len(qualified) != 1:
        failures.append("track reference composition is not uniquely proved")
    selected_mapping = qualified[0] if len(qualified) == 1 else None
    mapping_keys = (
        "local_source", "word_offset", "reference_source",
        "multiplication_order", "convention",
    )
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "catalog_instance_count": len(instances),
        "scope_count": len(scopes),
        "reference_snapshot_count": len(references),
        "candidate_group_count": len(reports),
        "minimum_distinct_matches": minimum_matches,
        "position_tolerance": tolerance,
        "selected_mapping": None if selected_mapping is None else {
            key: selected_mapping[key] for key in mapping_keys
        },
        "candidate_groups": reports,
        "qualification": {
            "exact_track_reference_join_proved": True,
            "world_transform_composition_proved": not failures,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "guest_state_changed": False,
            "source_files_changed": False,
            "plaintext_identity_exported": False,
            "xenos_authority": True,
            "native_admission": False,
            "native_draw": False,
            "suppression_allowed": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--catalog", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--tolerance", type=float, default=SCOPE.DEFAULT_TOLERANCE)
    parser.add_argument("--minimum-matches", type=int, default=SCOPE.DEFAULT_MINIMUM_MATCHES)
    arguments = parser.parse_args()
    try:
        document = build(
            SCOPE.read_events(arguments.logs),
            json.loads(arguments.catalog.read_text(encoding="utf-8")),
            requested_session=arguments.session,
            tolerance=arguments.tolerance,
            minimum_matches=arguments.minimum_matches,
        )
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if document["status"] != "complete":
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (json.JSONDecodeError, OSError, ValueError) as error:
        print(f"track reference-composition classification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
