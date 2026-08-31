"""Join exact runtime static-world transforms to title-authored categories."""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import math
import pathlib
import struct
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-instance-classification.v1"
CATALOG_SCHEMA = "pinyon-shift.native-renderer-static-world-instance-catalog.v1"
CONFIG = "native_renderer.discovery.static_world_runtime_join_config"
SUMMARY = "native_renderer.discovery.static_world_runtime_join_summary"
PROVENANCE = "native_renderer.discovery.title_provenance_entry"
DEFAULT_TOLERANCE = 0.05
DEFAULT_MINIMUM_MATCHES = 8
CONVENTIONS = {
    "translation_words_12_13_14": (12, 13, 14),
    "translation_words_3_7_11": (3, 7, 11),
}


def read_events(paths):
    events = []
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"invalid JSON at {path}:{line_number}: {error}"
                    ) from error
                if isinstance(event, dict):
                    events.append(event)
    return events


def boolean(event, key):
    value = event.get(key)
    if value not in ("true", "false"):
        raise ValueError(f"invalid {key} in {event.get('event', 'event')}")
    return value == "true"


def integer(event, key):
    try:
        value = int(event[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key} in {event.get('event', 'event')}") from error
    if value < 0:
        raise ValueError(f"negative {key} in {event.get('event', 'event')}")
    return value


def hexadecimal(value, width, label):
    value = str(value).upper()
    if len(value) != width or any(
        character not in "0123456789ABCDEF" for character in value
    ):
        raise ValueError(f"invalid {label}")
    return value


def parse_transform(event):
    words = str(event.get("static_world_transform_words", "")).split(":")
    if len(words) != 16:
        raise ValueError("runtime transform does not contain 16 words")
    values = tuple(int(hexadecimal(word, 8, "transform word"), 16) for word in words)
    transform_hash = hexadecimal(
        event.get("static_world_transform_hash", ""), 16, "transform hash"
    )
    return transform_hash, values


def float_word(word):
    value = struct.unpack(">f", word.to_bytes(4, "big"))[0]
    return value if math.isfinite(value) else None


def translation(words, indices):
    values = tuple(float_word(words[index]) for index in indices)
    return None if any(value is None for value in values) else values


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
    if not isinstance(instances, list) or len(instances) != document.get(
        "instance_count"
    ):
        raise ValueError("static-world instance catalog count drifted")
    validated = []
    for index, instance in enumerate(instances):
        category = instance.get("category")
        if category not in ("collision_prop", "gameplay_object"):
            raise ValueError("static-world instance category is invalid")
        identity_hash = hexadecimal(
            instance.get("identity_hash", ""), 16, "catalog identity hash"
        )
        position = instance.get("position")
        if (
            not isinstance(position, list)
            or len(position) != 3
            or not all(
                isinstance(value, (int, float)) and math.isfinite(value)
                for value in position
            )
        ):
            raise ValueError("static-world catalog position is invalid")
        validated.append(
            {
                "catalog_index": index,
                "category": category,
                "identity_hash": identity_hash,
                "position": tuple(float(value) for value in position),
            }
        )
    return validated


def spatial_index(instances, tolerance):
    result = collections.defaultdict(list)
    for instance in instances:
        key = tuple(math.floor(value / tolerance) for value in instance["position"])
        result[key].append(instance)
    return result


def match_position(index, position, tolerance):
    key = tuple(math.floor(value / tolerance) for value in position)
    candidates = []
    for offset in itertools.product((-1, 0, 1), repeat=3):
        adjacent = tuple(key[axis] + offset[axis] for axis in range(3))
        for instance in index.get(adjacent, ()):
            distance = math.dist(position, instance["position"])
            if distance <= tolerance:
                candidates.append((distance, instance))
    candidates.sort(key=lambda item: (item[0], item[1]["catalog_index"]))
    if not candidates:
        return "unmatched", None
    if len(candidates) != 1:
        return "ambiguous", None
    return "matched", candidates[0]


def select_session(events, requested_session):
    sessions = {
        str(event.get("session"))
        for event in events
        if event.get("event") == CONFIG and event.get("session")
    }
    if requested_session:
        if requested_session not in sessions:
            raise ValueError("requested static-world session is missing")
        session = requested_session
    elif len(sessions) == 1:
        session = next(iter(sessions))
    else:
        raise ValueError("input must contain exactly one static-world session")
    return session, [event for event in events if str(event.get("session")) == session]


def build(
    catalog,
    events,
    requested_session=None,
    tolerance=DEFAULT_TOLERANCE,
    minimum_matches=DEFAULT_MINIMUM_MATCHES,
):
    if not math.isfinite(tolerance) or tolerance <= 0 or tolerance > 1:
        raise ValueError("match tolerance is outside the safe range")
    if minimum_matches < 1:
        raise ValueError("minimum matches must be positive")
    instances = validate_catalog(catalog)
    session, selected = select_session(events, requested_session)
    configs = [event for event in selected if event.get("event") == CONFIG]
    summaries = [event for event in selected if event.get("event") == SUMMARY]
    starts = [event for event in selected if event.get("event") == "process.start"]
    shutdowns = [
        event for event in selected if event.get("event") == "process.shutdown"
    ]
    if len(configs) != 1 or len(summaries) != 1:
        raise ValueError("static-world runtime lifecycle is incomplete")
    if len(starts) != 1 or len(shutdowns) != 1:
        raise ValueError("process lifecycle is incomplete")
    if (
        summaries[0].get("status") != "complete"
        or summaries[0].get("qualification_complete") != "true"
    ):
        raise ValueError("static-world runtime qualification is incomplete")

    transforms = {}
    failures = []
    for event in selected:
        if event.get("event") != PROVENANCE or event.get("outcome") != "prepared":
            continue
        if event.get("static_world_origin") != "true":
            continue
        if event.get("static_world_transform_valid") != "true":
            failures.append("prepared static-world origin lacks a valid transform")
            continue
        if (
            event.get("xenos_draw") != "preserved"
            or event.get("suppression_eligible") != "false"
        ):
            failures.append("runtime provenance violated Xenos authority")
        transform_hash, words = parse_transform(event)
        calls = integer(event, "calls")
        previous = transforms.get(transform_hash)
        if previous and previous["words"] != words:
            failures.append("runtime transform hash collision was observed")
            continue
        if previous:
            previous["calls"] += calls
        else:
            transforms[transform_hash] = {"words": words, "calls": calls}
    if not transforms:
        failures.append("no prepared static-world transforms were observed")

    index = spatial_index(instances, tolerance)
    convention_reports = {}
    qualified_conventions = []
    for name, indices in CONVENTIONS.items():
        matches = []
        unmatched = 0
        ambiguous = 0
        non_finite = 0
        for transform_hash, observed in sorted(transforms.items()):
            position = translation(observed["words"], indices)
            if position is None:
                non_finite += 1
                continue
            outcome, match = match_position(index, position, tolerance)
            if outcome == "unmatched":
                unmatched += 1
                continue
            if outcome == "ambiguous":
                ambiguous += 1
                continue
            distance, instance = match
            matches.append(
                {
                    "transform_hash": transform_hash,
                    "calls": observed["calls"],
                    "category": instance["category"],
                    "catalog_identity_hash": instance["identity_hash"],
                    "catalog_index": instance["catalog_index"],
                    "distance": round(distance, 9),
                }
            )
        complete = (
            len(matches) >= minimum_matches
            and len(matches) == len(transforms)
            and not unmatched
            and not ambiguous
            and not non_finite
        )
        if complete:
            qualified_conventions.append(name)
        convention_reports[name] = {
            "matched": len(matches),
            "unmatched": unmatched,
            "ambiguous": ambiguous,
            "non_finite": non_finite,
            "complete": complete,
            "matches": matches,
        }
    if len(qualified_conventions) != 1:
        failures.append("runtime matrix convention is not uniquely proved")
    selected_convention = (
        qualified_conventions[0] if len(qualified_conventions) == 1 else None
    )
    selected_report = (
        convention_reports[selected_convention]
        if selected_convention is not None
        else None
    )
    category_counts = collections.Counter(
        match["category"] for match in (selected_report or {}).get("matches", [])
    )
    if selected_report is not None and not category_counts["collision_prop"]:
        failures.append("no collision-prop runtime transform was classified")
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "catalog_instance_count": len(instances),
        "unique_runtime_transforms": len(transforms),
        "minimum_matches": minimum_matches,
        "position_tolerance": tolerance,
        "selected_matrix_convention": selected_convention,
        "category_counts": dict(sorted(category_counts.items())),
        "conventions": convention_reports,
        "qualification": {
            "runtime_transform_join_proved": not failures,
            "building_or_prop_instance_identity_proved": not failures,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "guest_state_changed": False,
            "source_files_changed": False,
            "plaintext_identity_exported": False,
            "xenos_draw": "preserved",
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
    parser.add_argument(
        "--minimum-matches", type=int, default=DEFAULT_MINIMUM_MATCHES
    )
    arguments = parser.parse_args()
    try:
        catalog = json.loads(arguments.catalog.read_text(encoding="utf-8"))
        document = build(
            catalog,
            read_events(arguments.logs),
            requested_session=arguments.session,
            tolerance=arguments.tolerance,
            minimum_matches=arguments.minimum_matches,
        )
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (json.JSONDecodeError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
