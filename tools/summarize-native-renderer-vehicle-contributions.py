#!/usr/bin/env python3
"""Partition the retained vehicle families into exact resource contributions."""

import argparse
import collections
import json
from pathlib import Path


SCHEMA = "pinyon-shift.native-renderer-vehicle-contributions.v1"
INPUT_SCHEMA = "pinyon-shift.native-renderer-vehicle-shadow-geometry.v15"
EXPECTED_FAMILY_COUNT = 30
EXPECTED_VARIANTS_PER_CONTRIBUTION = 2
STABLE_FIELDS = (
    "seed_index",
    "draw_argument_hash",
    "material_topology_key",
    "pixel_shader",
    "prepared_pipeline_hash",
    "render_state_hash",
    "template_key",
    "texture_layout_hash",
    "texture_resource_hash",
    "vertex_shader",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(record, key):
    try:
        return int(record[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing or invalid integer field: {key}") from error


def hexadecimal(record, key, width):
    value = str(record.get(key, "")).upper()
    require(
        len(value) == width and all(character in "0123456789ABCDEF" for character in value),
        f"missing or invalid hexadecimal field: {key}",
    )
    return value


def load(path):
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def stable_key(family):
    return tuple(str(family.get(field, "")) for field in STABLE_FIELDS)


def summarize(path):
    source = load(path)
    require(source.get("schema") == INPUT_SCHEMA, "unsupported source schema")
    safety = source.get("safety", {})
    require(safety.get("xenos_authority") is True, "Xenos authority changed")
    require(safety.get("native_draw") is False, "native drawing was enabled")
    require(
        safety.get("suppression_allowed") is False,
        "suppression was allowed",
    )
    require(
        safety.get("guest_payload_capture") is False,
        "guest payload capture was enabled",
    )
    qualification = source.get("qualification", {})
    require(
        qualification.get("working_color_bridge_candidate") is True,
        "semantic constant bridge is not complete",
    )
    require(
        qualification.get("native_admission_allowed") is False,
        "source report unexpectedly allows native admission",
    )

    families = source.get("candidate_families")
    require(isinstance(families, list), "candidate family table is missing")
    require(
        len(families) == EXPECTED_FAMILY_COUNT,
        f"expected {EXPECTED_FAMILY_COUNT} candidate families",
    )
    require(
        integer(source.get("totals", {}), "correlations") == len(families),
        "candidate family accounting drift",
    )

    groups = collections.defaultdict(list)
    for family in families:
        geometry = hexadecimal(family, "geometry_resource_hash", 16)
        hexadecimal(family, "prepared_signature", 16)
        require(integer(family, "draws") > 0, "candidate family was not exercised")
        require(
            integer(family, "semantic_constant_bridge_publications")
            == integer(family, "draws"),
            "semantic bridge publication accounting drift",
        )
        groups[geometry].append(family)

    contributions = []
    failures = []
    ordered_groups = sorted(
        groups.items(), key=lambda item: (integer(item[1][0], "seed_index"), item[0])
    )
    for geometry, variants in ordered_groups:
        signatures = sorted(
            hexadecimal(variant, "prepared_signature", 16) for variant in variants
        )
        keys = {stable_key(variant) for variant in variants}
        draw_counts = {integer(variant, "draws") for variant in variants}
        publication_counts = {
            integer(variant, "semantic_constant_bridge_publications")
            for variant in variants
        }
        local_failures = []
        if len(variants) != EXPECTED_VARIANTS_PER_CONTRIBUTION:
            local_failures.append("variant_count")
        if len(set(signatures)) != EXPECTED_VARIANTS_PER_CONTRIBUTION:
            local_failures.append("prepared_signature_count")
        if len(keys) != 1:
            local_failures.append("mechanical_contract_drift")
        if draw_counts and max(draw_counts) - min(draw_counts) > 1:
            local_failures.append("draw_count_drift")
        failures.extend(f"{geometry}:{failure}" for failure in local_failures)
        representative = variants[0]
        contributions.append(
            {
                "contribution_index": len(contributions),
                "geometry_resource_hash": geometry,
                "seed_index": integer(representative, "seed_index"),
                "variant_count": len(variants),
                "prepared_signatures": signatures,
                "draws_per_variant": sorted(draw_counts),
                "semantic_bridge_publications_per_variant": sorted(
                    publication_counts
                ),
                "draw_argument_hash": hexadecimal(
                    representative, "draw_argument_hash", 16
                ),
                "template_key": hexadecimal(representative, "template_key", 16),
                "mechanical_contract_stable": len(keys) == 1,
                "semantic_role": "unclassified",
                "semantic_label_proved": False,
            }
        )

    complete = not failures
    return {
        "schema": SCHEMA,
        "status": "qualified" if complete else "incomplete",
        "source_report": str(path),
        "summary": {
            "candidate_family_count": len(families),
            "resource_contribution_count": len(contributions),
            "variants_per_complete_contribution": EXPECTED_VARIANTS_PER_CONTRIBUTION,
            "complete_resource_contributions": sum(
                contribution["variant_count"] == EXPECTED_VARIANTS_PER_CONTRIBUTION
                and contribution["mechanical_contract_stable"]
                for contribution in contributions
            ),
            "family_to_contribution_reduction": len(families) - len(contributions),
        },
        "contributions": contributions,
        "qualification": {
            "exact_resource_contribution_partition_proved": complete,
            "semantic_mesh_material_roles_proved": False,
            "player_vehicle_identity_proved": False,
            "native_admission_allowed": False,
            "suppression_allowed": False,
        },
        "safety": {
            "source_xenos_authority": True,
            "guest_payload_exported": False,
            "native_draw": False,
            "suppression_allowed": False,
        },
        "failures": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = summarize(args.report)
        require(document["status"] == "qualified", "contribution partition incomplete")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError) as error:
        print(f"vehicle contribution summary failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
