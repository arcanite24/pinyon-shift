#!/usr/bin/env python3
"""Join one clean C1/C2 AppData qualification batch."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-c1-c2-batch.v1"
INPUT_SCHEMAS = {
    "track": "pinyon-shift.native-renderer-track-model-runtime-join.v3",
    "static_world": "pinyon-shift.native-renderer-static-world-runtime-join.v10",
    "classification": (
        "pinyon-shift.native-renderer-static-world-instance-classification.v1"
    ),
    "workset": "pinyon-shift.native-renderer-continuous-world-workset.v6",
}


def read_document(path):
    with path.open(encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, dict):
        raise ValueError(f"{path} is not a JSON object")
    return document


def require_mapping(document, key, label):
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{label} {key} is missing")
    return value


def validate_safety(reports):
    track = require_mapping(reports["track"], "safety", "track report")
    static_world = require_mapping(
        reports["static_world"], "safety", "static-world report"
    )
    classification = require_mapping(
        reports["classification"], "safety", "classification report"
    )
    workset = require_mapping(reports["workset"], "safety", "workset report")
    passive = {
        "guest_state_changed": False,
        "native_admission": False,
        "native_draw": False,
        "suppression_allowed": False,
    }
    for label, safety in (
        ("track", track),
        ("static-world", static_world),
    ):
        if any(safety.get(key) != value for key, value in passive.items()):
            raise ValueError(f"{label} safety boundary drifted")
        if safety.get("xenos_authority") is not True:
            raise ValueError(f"{label} Xenos authority drifted")
    if (
        classification.get("guest_state_changed") is not False
        or classification.get("source_files_changed") is not False
        or classification.get("plaintext_identity_exported") is not False
        or classification.get("xenos_draw") != "preserved"
        or classification.get("native_admission") is not False
        or classification.get("native_draw") is not False
        or classification.get("suppression_allowed") is not False
    ):
        raise ValueError("classification safety boundary drifted")
    if (
        workset.get("readback") is not False
        or workset.get("xenos_draw_preserved") is not True
        or workset.get("output_authority") != "renderer_selector"
        or workset.get("suppression_allowed") is not False
    ):
        raise ValueError("workset safety boundary drifted")


def build(reports):
    for label, schema in INPUT_SCHEMAS.items():
        if reports[label].get("schema") != schema:
            raise ValueError(f"{label} report schema drifted")
    sessions = {reports[label].get("session") for label in INPUT_SCHEMAS}
    if None in sessions or len(sessions) != 1:
        raise ValueError("C1/C2 reports do not describe one exact session")
    session = next(iter(sessions))
    validate_safety(reports)

    failures = []
    for label, document in reports.items():
        if document.get("status") != "complete":
            failures.append(f"{label} report is not final and complete")
        if document.get("failures"):
            failures.append(f"{label} report contains failures")

    for label in ("track", "static_world", "workset"):
        evidence = require_mapping(reports[label], "evidence", f"{label} report")
        if evidence.get("session_exit_proved") is not True:
            failures.append(f"{label} report does not prove session exit")

    track = require_mapping(reports["track"], "qualification", "track report")
    static_world = require_mapping(
        reports["static_world"], "qualification", "static-world report"
    )
    classification = require_mapping(
        reports["classification"], "qualification", "classification report"
    )
    workset = require_mapping(
        reports["workset"], "qualification", "workset report"
    )

    required_track = (
        "track_command_lineage_to_prepared_draw_proved",
    )
    for key in required_track:
        if track.get(key) is not True:
            failures.append(f"track gate is unproved: {key}")

    required_static = (
        "simple_model_renderer_scope_proved",
        "simple_model_resource_lifetime_proved",
        "payload_generation_invalidation_proved",
        "simple_mesh_to_prepared_draw_proved",
        "model_presentation_transform_to_prepared_draw_proved",
        "hashed_asset_identity_to_prepared_draw_proved",
        "complete_vertex_layout_to_prepared_draw_proved",
        "static_world_pm4_to_prepared_draw_proved",
    )
    for key in required_static:
        if static_world.get(key) is not True:
            failures.append(f"static-world gate is unproved: {key}")

    if classification.get("runtime_transform_join_proved") is not True:
        failures.append("static-world runtime transform join is unproved")
    if classification.get("building_or_prop_instance_identity_proved") is not True:
        failures.append("static-world building/prop identity is unproved")

    required_workset = (
        "continuous_multi_draw_workset_proved",
        "swap_committed_freshness_proved",
        "clean_xenos_fallback_proved",
        "track_world_selection_proved",
        "static_world_selection_proved",
    )
    for key in required_workset:
        if workset.get(key) is not True:
            failures.append(f"continuous-output gate is unproved: {key}")

    track_ready = not any(
        failure.startswith("track gate")
        or failure.startswith("continuous-output gate")
        for failure in failures
    )
    static_ready = not any(
        failure.startswith("static-world")
        or failure.startswith("continuous-output gate")
        for failure in failures
    )
    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "qualification": {
            "c1_exact_track_world_output_proved": track_ready and not failures,
            "c2_exact_classified_static_world_output_proved": (
                static_ready and not failures
            ),
            "combined_swap_committed_output_proved": not failures,
            "session_exit_proved": not failures,
            "manual_visual_acceptance_proved": False,
            "representative_race_coverage_proved": False,
            "representative_streaming_coverage_proved": False,
            "family_promotion_allowed": False,
            "suppression_allowed": False,
        },
        "next_gate": (
            "manual_visual_and_representative_race_streaming_qualification"
            if not failures
            else "resolve_reported_batch_failures"
        ),
        "safety": {
            "xenos_authority_preserved": True,
            "guest_state_changed": False,
            "save_files_changed": False,
            "family_promotion_allowed": False,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--track", required=True, type=pathlib.Path)
    parser.add_argument("--static-world", required=True, type=pathlib.Path)
    parser.add_argument("--classification", required=True, type=pathlib.Path)
    parser.add_argument("--workset", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(
            {
                "track": read_document(args.track),
                "static_world": read_document(args.static_world),
                "classification": read_document(args.classification),
                "workset": read_document(args.workset),
            }
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if document["status"] != "complete":
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"native renderer C1/C2 batch failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
