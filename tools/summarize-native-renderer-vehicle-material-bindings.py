#!/usr/bin/env python3
"""Join title-owned vehicle material bindings to geometry contributions."""

import argparse
import json
from pathlib import Path


SCHEMA = "pinyon-shift.native-renderer-vehicle-material-bindings.v1"
CONTRIBUTION_SCHEMA = "pinyon-shift.native-renderer-vehicle-contributions.v1"
SUMMARY_EVENT = "native_renderer.discovery.vehicle_material_binding_summary"
DETAIL_EVENT = "native_renderer.discovery.vehicle_material_binding"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(record, key):
    try:
        return int(record[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing or invalid integer field: {key}") from error


def hexadecimal(value, width, label):
    value = str(value).upper()
    require(
        len(value) == width
        and all(character in "0123456789ABCDEF" for character in value),
        f"missing or invalid hexadecimal field: {label}",
    )
    return value


def load_json(path):
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def load_events(path):
    events = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSONL at line {line_number}: {error}"
                ) from error
    return events


def parse_signatures(record):
    values = [
        value
        for value in str(record.get("backend_signatures", "")).split(",")
        if value
    ]
    signatures = {
        hexadecimal(value, 16, "backend_signatures") for value in values
    }
    require(
        integer(record, "backend_signature_count") == len(signatures),
        "backend signature detail accounting drift",
    )
    return signatures


def summarize(log_path, contribution_path):
    events = load_events(log_path)
    summaries = [event for event in events if event.get("event") == SUMMARY_EVENT]
    details = [event for event in events if event.get("event") == DETAIL_EVENT]
    require(len(summaries) == 1, "expected one material-binding summary")
    summary = summaries[0]
    require(
        summary.get("status") == "complete",
        "material-binding census incomplete",
    )
    require(
        summary.get("accounting_complete") == "true",
        "binding accounting drift",
    )
    require(summary.get("hook") == "82549670", "material-binding hook drifted")
    require(
        summary.get("title_semantic") == "tire_wheel_shader_settings",
        "title material semantic drifted",
    )
    require(
        integer(summary, "observations") > 0,
        "material binding was not observed",
    )
    require(integer(summary, "valid_observations") > 0, "no valid binding observed")
    require(integer(summary, "invalid_relation") == 0, "binding relation drifted")
    require(integer(summary, "asset_read_faults") == 0, "asset-key read faulted")
    require(integer(summary, "overflow") == 0, "binding table overflowed")
    require(
        integer(summary, "bindings") == len(details),
        "binding detail accounting drift",
    )
    require(summary.get("xenos_authority") == "true", "Xenos authority changed")
    require(summary.get("suppression_allowed") == "false", "suppression was allowed")
    require(summary.get("native_draw") == "false", "native drawing was enabled")
    require(
        summary.get("guest_payload_exported") == "false",
        "guest payload was exported",
    )

    contributions = load_json(contribution_path)
    require(
        contributions.get("schema") == CONTRIBUTION_SCHEMA,
        "unsupported contribution schema",
    )
    require(
        contributions.get("status") == "qualified",
        "contribution partition incomplete",
    )
    require(
        contributions.get("qualification", {}).get(
            "exact_resource_contribution_partition_proved"
        )
        is True,
        "exact contribution partition was not proved",
    )
    require(
        contributions.get("safety", {}).get("source_xenos_authority") is True,
        "contribution source changed Xenos authority",
    )

    signature_to_contribution = {}
    for contribution in contributions.get("contributions", []):
        geometry_resource_hash = hexadecimal(
            contribution.get("geometry_resource_hash"),
            16,
            "geometry_resource_hash",
        )
        signatures = {
            hexadecimal(value, 16, "prepared_signatures")
            for value in contribution.get("prepared_signatures", [])
        }
        require(len(signatures) == 2, "contribution variant count drifted")
        for signature in signatures:
            require(
                signature not in signature_to_contribution,
                "prepared signature maps to multiple contributions",
            )
            signature_to_contribution[signature] = geometry_resource_hash

    all_binding_signatures = set()
    binding_rows = []
    detail_observations = 0
    for detail in details:
        require(
            detail.get("classification")
            == "exact_tire_wheel_material_binding_seed",
            "binding classification drifted",
        )
        require(detail.get("xenos_authority") == "true", "Xenos authority changed")
        require(
            detail.get("suppression_allowed") == "false",
            "suppression was allowed",
        )
        require(detail.get("native_draw") == "false", "native drawing was enabled")
        require(
            detail.get("guest_payload_exported") == "false",
            "guest payload was exported",
        )
        require(integer(detail, "asset_key_length") > 0, "asset key was empty")
        require(
            integer(detail, "backend_signature_overflow") == 0,
            "binding signature table overflowed",
        )
        detail_observations += integer(detail, "observations")
        signatures = parse_signatures(detail)
        all_binding_signatures.update(signatures)
        matches = sorted(
            {
                signature_to_contribution[signature]
                for signature in signatures
                if signature in signature_to_contribution
            }
        )
        binding_rows.append(
            {
                "asset_key_hash": hexadecimal(
                    detail.get("asset_key_hash"), 16, "asset_key_hash"
                ),
                "asset_key_length": integer(detail, "asset_key_length"),
                "load_ui": detail.get("load_ui") == "true",
                "slod": detail.get("slod") == "true",
                "observations": integer(detail, "observations"),
                "root_draw_probe_matches": integer(
                    detail, "root_draw_probe_matches"
                ),
                "binding_draw_probe_matches": integer(
                    detail, "binding_draw_probe_matches"
                ),
                "backend_signatures": sorted(signatures),
                "matched_geometry_resources": matches,
            }
        )

    require(
        detail_observations == integer(summary, "valid_observations"),
        "binding observation detail accounting drift",
    )

    matched_resources = sorted(
        {
            signature_to_contribution[signature]
            for signature in all_binding_signatures
            if signature in signature_to_contribution
        }
    )
    unmatched_signatures = sorted(
        signature
        for signature in all_binding_signatures
        if signature not in signature_to_contribution
    )
    unique_join = len(matched_resources) == 1 and not unmatched_signatures
    failures = []
    if not all_binding_signatures:
        failures.append("no_direct_binding_to_draw_join")
    elif not unique_join:
        failures.append("binding_to_geometry_join_not_unique")

    return {
        "schema": SCHEMA,
        "status": "qualified" if unique_join else "bounded_negative_result",
        "source_log": str(log_path),
        "source_contributions": str(contribution_path),
        "summary": {
            "binding_count": len(binding_rows),
            "backend_signature_count": len(all_binding_signatures),
            "matched_geometry_resource_count": len(matched_resources),
            "unmatched_backend_signature_count": len(unmatched_signatures),
        },
        "bindings": binding_rows,
        "matched_geometry_resources": matched_resources,
        "unmatched_backend_signatures": unmatched_signatures,
        "qualification": {
            "title_owned_tire_wheel_discriminator_proved": True,
            "unique_geometry_resource_join_proved": unique_join,
            "tire_wheel_visual_role_proved": False,
            "native_admission_allowed": False,
            "suppression_allowed": False,
        },
        "safety": {
            "xenos_authority": True,
            "guest_payload_exported": False,
            "native_draw": False,
            "suppression_allowed": False,
        },
        "failures": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--contributions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = summarize(args.log, args.contributions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError) as error:
        print(f"vehicle material-binding summary failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
