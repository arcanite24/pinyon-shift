#!/usr/bin/env python3
"""Match track prepared constant windows to the title-authored world catalog."""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import math
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-track-prepared-transform-classification.v1"
PREPARED_SCHEMA = "pinyon-shift.native-renderer-track-prepared-layout.v2"
CATALOG_SCHEMA = "pinyon-shift.native-renderer-static-world-instance-catalog.v1"
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


def validate_prepared(document):
    if document.get("schema") != PREPARED_SCHEMA or document.get("status") != "complete":
        raise ValueError("track prepared-layout report is incomplete")
    qualification = document.get("qualification", {})
    safety = document.get("safety", {})
    if (
        qualification.get("exact_track_prepared_layouts_proved") is not True
        or qualification.get("world_transform_constant_layout_proved") is not False
        or safety.get("guest_state_changed") is not False
        or safety.get("control_flow_changed") is not False
        or safety.get("xenos_authority") is not True
        or safety.get("native_admission") is not False
        or safety.get("suppression_allowed") is not False
    ):
        raise ValueError("track prepared-layout report safety drifted")
    runs = document.get("vertex_consecutive_register_runs")
    if not isinstance(runs, list):
        raise ValueError("track prepared-layout candidate runs are invalid")
    shader_frequency = document.get("vertex_shader_layout_frequency")
    if not isinstance(shader_frequency, list):
        raise ValueError("track prepared-layout shader frequency is invalid")
    shader_layouts = {}
    for item in shader_frequency:
        shader = hexadecimal(item.get("vertex_shader", ""), 16, "vertex shader")
        layouts = item.get("layouts")
        if not isinstance(layouts, int) or layouts < 1 or shader in shader_layouts:
            raise ValueError("track prepared-layout shader frequency is invalid")
        shader_layouts[shader] = layouts
    validated = []
    for run in runs:
        layout_key = hexadecimal(run.get("layout_key", ""), 16, "layout key")
        vertex_shader = hexadecimal(
            run.get("vertex_shader", ""), 16, "vertex shader"
        )
        if vertex_shader not in shader_layouts:
            raise ValueError("track prepared run has no shader frequency")
        registers = run.get("registers")
        if not isinstance(registers, list) or len(registers) < 4:
            raise ValueError("track prepared register run is too short")
        parsed = []
        for register in registers:
            index = register.get("index")
            values = register.get("values")
            if (
                not isinstance(index, int)
                or not isinstance(values, list)
                or len(values) != 4
                or not all(
                    isinstance(value, (int, float)) and math.isfinite(value)
                    for value in values
                )
            ):
                raise ValueError("track prepared register is invalid")
            if parsed and index != parsed[-1][0] + 1:
                raise ValueError("track prepared register run is not consecutive")
            parsed.append((index, tuple(float(value) for value in values)))
        if (
            run.get("start_register") != parsed[0][0]
            or run.get("end_register") != parsed[-1][0]
            or run.get("register_count") != len(parsed)
        ):
            raise ValueError("track prepared register run bounds drifted")
        validated.append(
            {
                "layout_key": layout_key,
                "vertex_shader": vertex_shader,
                "registers": parsed,
            }
        )
    return validated, shader_layouts


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


def build(
    catalog,
    prepared,
    tolerance=DEFAULT_TOLERANCE,
    minimum_matches=DEFAULT_MINIMUM_MATCHES,
):
    if not math.isfinite(tolerance) or tolerance <= 0 or tolerance > 1:
        raise ValueError("match tolerance is outside the safe range")
    if minimum_matches < 1:
        raise ValueError("minimum matches must be positive")
    instances = validate_catalog(catalog)
    runs, shader_layouts = validate_prepared(prepared)
    index = spatial_index(instances, tolerance)
    groups = collections.defaultdict(list)
    for run in runs:
        registers = run["registers"]
        for offset in range(len(registers) - 3):
            window = registers[offset : offset + 4]
            words = tuple(value for _, values in window for value in values)
            for convention, indices in CONVENTIONS.items():
                position = tuple(words[word] for word in indices)
                groups[(run["vertex_shader"], window[0][0], convention)].append(
                    (run["layout_key"], position)
                )

    reports = []
    qualified = []
    for (vertex_shader, start_register, convention), observations in sorted(groups.items()):
        matches = []
        unmatched = 0
        ambiguous = 0
        for layout_key, position in observations:
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
                    "layout_key": layout_key,
                    "category": instance["category"],
                    "catalog_identity_hash": instance["identity_hash"],
                    "catalog_index": instance["catalog_index"],
                    "distance": round(distance, 9),
                }
            )
        distinct_catalog_matches = len(
            {match["catalog_index"] for match in matches}
        )
        category_counts = collections.Counter(
            match["category"] for match in matches
        )
        complete = (
            len(observations) >= minimum_matches
            and len(observations) == shader_layouts[vertex_shader]
            and len(matches) == len(observations)
            and distinct_catalog_matches >= minimum_matches
            and not unmatched
            and not ambiguous
            and category_counts["collision_prop"] > 0
        )
        report = {
            "vertex_shader": vertex_shader,
            "start_register": start_register,
            "convention": convention,
            "observed_layouts": len(observations),
            "shader_layouts": shader_layouts[vertex_shader],
            "matched": len(matches),
            "distinct_catalog_matches": distinct_catalog_matches,
            "unmatched": unmatched,
            "ambiguous": ambiguous,
            "category_counts": dict(sorted(category_counts.items())),
            "complete": complete,
            "matches": matches,
        }
        reports.append(report)
        if complete:
            qualified.append(report)

    failures = []
    if not runs:
        failures.append("no consecutive vertex constant runs were observed")
    if len(qualified) != 1:
        failures.append("track world transform constant mapping is not uniquely proved")
    selected = qualified[0] if len(qualified) == 1 else None
    status = "complete" if not failures else "incomplete"
    return {
        "schema": SCHEMA,
        "session": prepared.get("session"),
        "status": status,
        "failures": failures,
        "catalog_instance_count": len(instances),
        "candidate_group_count": len(reports),
        "minimum_distinct_matches": minimum_matches,
        "position_tolerance": tolerance,
        "selected_mapping": (
            None
            if selected is None
            else {
                key: selected[key]
                for key in ("vertex_shader", "start_register", "convention")
            }
        ),
        "candidate_groups": reports,
        "qualification": {
            "exact_track_prepared_layouts_proved": True,
            "world_transform_constant_layout_proved": not failures,
            "terrain_or_road_instance_identity_proved": not failures,
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
    parser.add_argument("--catalog", required=True, type=pathlib.Path)
    parser.add_argument("--prepared", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument(
        "--minimum-matches", type=int, default=DEFAULT_MINIMUM_MATCHES
    )
    arguments = parser.parse_args()
    try:
        catalog = json.loads(arguments.catalog.read_text(encoding="utf-8"))
        prepared = json.loads(arguments.prepared.read_text(encoding="utf-8"))
        document = build(
            catalog,
            prepared,
            tolerance=arguments.tolerance,
            minimum_matches=arguments.minimum_matches,
        )
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if document["status"] != "complete":
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (json.JSONDecodeError, OSError, ValueError) as error:
        print(f"track prepared-transform classification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
