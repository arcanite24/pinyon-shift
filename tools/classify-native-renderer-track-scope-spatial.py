#!/usr/bin/env python3
"""Match exact track-scope numeric windows to the static-world catalog."""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import math
import pathlib
import struct
import sys


SCHEMA = "pinyon-shift.native-renderer-track-scope-spatial-classification.v1"
CATALOG_SCHEMA = "pinyon-shift.native-renderer-static-world-instance-catalog.v1"
ENTRY = "native_renderer.discovery.track_world_scope_spatial_entry"
SUMMARY = "native_renderer.discovery.track_render_model_runtime_join_summary"
DEFAULT_TOLERANCE = 0.05
DEFAULT_MINIMUM_MATCHES = 8
CONVENTIONS = {
    "translation_words_12_13_14": (12, 13, 14),
    "translation_words_3_7_11": (3, 7, 11),
}


def hexadecimal(value, width, label):
    value = str(value).upper()
    if len(value) != width or any(c not in "0123456789ABCDEF" for c in value):
        raise ValueError(f"invalid {label}")
    return value


def integer(event, key):
    try:
        value = int(event[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if value < 0:
        raise ValueError(f"negative {key}")
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
        raise ValueError("track-scope spatial evidence violates safety")


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
                    raise ValueError(f"invalid JSON at {path}:{line_number}") from error
                if isinstance(event, dict):
                    events.append(event)
    return events


def parse_words(event, prefix, expected_count):
    if integer(event, f"{prefix}_word_count") != expected_count:
        raise ValueError(f"{prefix} word count drifted")
    raw = event.get(f"{prefix}_words")
    if not isinstance(raw, str):
        raise ValueError(f"invalid {prefix} words")
    words = tuple(
        int(hexadecimal(word, 8, f"{prefix} word"), 16)
        for word in raw.split(":")
    )
    if len(words) != expected_count:
        raise ValueError(f"{prefix} payload count drifted")
    return words


def validate_catalog(document):
    if document.get("schema") != CATALOG_SCHEMA or document.get("status") != "complete":
        raise ValueError("static-world instance catalog is unsupported")
    safety = document.get("safety", {})
    if (
        safety.get("source_files_changed") is not False
        or safety.get("plaintext_identity_exported") is not False
        or safety.get("numeric_spatial_metadata_only") is not True
        or safety.get("native_admission") is not False
        or safety.get("suppression_allowed") is not False
    ):
        raise ValueError("static-world instance catalog safety drifted")
    instances = document.get("instances")
    if not isinstance(instances, list) or len(instances) != document.get("instance_count"):
        raise ValueError("static-world instance catalog count drifted")
    result = []
    for index, instance in enumerate(instances):
        position = instance.get("position")
        if (
            instance.get("category") not in ("collision_prop", "gameplay_object")
            or not isinstance(position, list)
            or len(position) != 3
            or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in position)
        ):
            raise ValueError("invalid static-world catalog instance")
        result.append({
            "catalog_index": index,
            "category": instance["category"],
            "identity_hash": hexadecimal(instance.get("identity_hash", ""), 16, "catalog identity hash"),
            "position": tuple(float(value) for value in position),
        })
    return result


def spatial_index(instances, tolerance):
    result = collections.defaultdict(list)
    for instance in instances:
        key = tuple(math.floor(value / tolerance) for value in instance["position"])
        result[key].append(instance)
    return result


def match_position(index, position, tolerance):
    key = tuple(math.floor(value / tolerance) for value in position)
    matches = []
    for offset in itertools.product((-1, 0, 1), repeat=3):
        adjacent = tuple(key[axis] + offset[axis] for axis in range(3))
        for instance in index.get(adjacent, ()):
            distance = math.dist(position, instance["position"])
            if distance <= tolerance:
                matches.append((distance, instance))
    matches.sort(key=lambda item: (item[0], item[1]["catalog_index"]))
    if not matches:
        return "unmatched", None
    if len(matches) != 1:
        return "ambiguous", None
    return "matched", matches[0]


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


def build(events, catalog, requested_session=None, tolerance=DEFAULT_TOLERANCE,
          minimum_matches=DEFAULT_MINIMUM_MATCHES):
    if not math.isfinite(tolerance) or tolerance <= 0 or tolerance > 1:
        raise ValueError("match tolerance is outside the safe range")
    if minimum_matches < 1:
        raise ValueError("minimum matches must be positive")
    instances = validate_catalog(catalog)
    session, selected = select_session(events, requested_session)
    starts = [event for event in selected if event.get("event") == "process.start"]
    shutdowns = [event for event in selected if event.get("event") == "process.shutdown"]
    summaries = [event for event in selected if event.get("event") == SUMMARY]
    if len(starts) != 1 or len(shutdowns) != 1 or len(summaries) != 1:
        raise ValueError("track-scope spatial lifecycle is incomplete")
    summary = summaries[0]
    require_safety(summary)
    if summary.get("checkpoint_kind") != "final":
        raise ValueError("track-scope spatial summary is not final")
    entries = [event for event in selected if event.get("event") == ENTRY]
    expected_entries = integer(summary, "scope_spatial_entries")
    observations = integer(summary, "scope_spatial_observations")
    if (
        len(entries) != expected_entries
        or integer(summary, "scope_spatial_table_overflow") != 0
        or summary.get("scope_spatial_accounting_complete") != "true"
    ):
        raise ValueError("track-scope spatial accounting is incomplete")

    parsed = []
    seen = set()
    calls = 0
    for event in entries:
        require_safety(event)
        key = hexadecimal(event.get("snapshot_key", ""), 16, "snapshot key")
        if key in seen:
            raise ValueError("duplicate track-scope spatial key")
        seen.add(key)
        hexadecimal(event.get("child_address", ""), 8, "child address")
        hexadecimal(event.get("descriptor_address", ""), 8, "descriptor address")
        entry_calls = integer(event, "calls")
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if not entry_calls or first_frame > last_frame or integer(event, "snapshot_variations"):
            raise ValueError("track-scope spatial snapshot is unstable")
        calls += entry_calls
        parsed.append({
            "snapshot_key": key,
            "child": parse_words(event, "child", 16),
            "descriptor": parse_words(event, "descriptor", 62),
        })
    if calls != observations:
        raise ValueError("track-scope spatial call accounting drifted")

    index = spatial_index(instances, tolerance)
    groups = collections.defaultdict(list)
    for entry in parsed:
        for source in ("child", "descriptor"):
            words = entry[source]
            for word_offset in range(len(words) - 15):
                window = words[word_offset : word_offset + 16]
                values = tuple(struct.unpack(">f", word.to_bytes(4, "big"))[0] for word in window)
                if not all(math.isfinite(value) for value in values):
                    continue
                for convention, indices in CONVENTIONS.items():
                    groups[(source, word_offset, convention)].append(
                        (entry["snapshot_key"], tuple(values[i] for i in indices))
                    )

    reports = []
    qualified = []
    for (source, word_offset, convention), candidates in sorted(groups.items()):
        matches = []
        unmatched = 0
        ambiguous = 0
        for snapshot_key, position in candidates:
            outcome, match = match_position(index, position, tolerance)
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
        distinct = len({match["catalog_index"] for match in matches})
        categories = collections.Counter(match["category"] for match in matches)
        complete = (
            len(candidates) == len(parsed)
            and len(matches) == len(parsed)
            and distinct >= minimum_matches
            and categories["collision_prop"] > 0
            and not unmatched
            and not ambiguous
        )
        report = {
            "source": source,
            "word_offset": word_offset,
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
    if not parsed:
        failures.append("no exact track-scope snapshots were observed")
    if len(qualified) != 1:
        failures.append("track-scope world transform mapping is not uniquely proved")
    selected_mapping = qualified[0] if len(qualified) == 1 else None
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "catalog_instance_count": len(instances),
        "snapshot_count": len(parsed),
        "observation_count": observations,
        "candidate_group_count": len(reports),
        "minimum_distinct_matches": minimum_matches,
        "position_tolerance": tolerance,
        "selected_mapping": None if selected_mapping is None else {
            key: selected_mapping[key] for key in ("source", "word_offset", "convention")
        },
        "candidate_groups": reports,
        "qualification": {
            "exact_track_scope_snapshots_proved": True,
            "world_transform_layout_proved": not failures,
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
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--minimum-matches", type=int, default=DEFAULT_MINIMUM_MATCHES)
    arguments = parser.parse_args()
    try:
        document = build(
            read_events(arguments.logs),
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
        print(f"track-scope spatial classification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
