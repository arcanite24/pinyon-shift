"""Summarize capture-proven vehicle shadow geometry/color correlations."""

import argparse
import json
from pathlib import Path


SCHEMA = "pinyon-shift.native-renderer-vehicle-shadow-geometry.v5"
CONFIG_EVENT = "native_renderer.discovery.vehicle_shadow_geometry_config"
EPOCH_EVENT = "native_renderer.discovery.vehicle_shadow_geometry_epoch"
CORRELATION_EVENT = (
    "native_renderer.discovery.vehicle_shadow_geometry_correlation"
)
CANDIDATE_EVENT = "native_renderer.discovery.vehicle_shadow_geometry_candidate"
SUMMARY_EVENT = "native_renderer.discovery.vehicle_shadow_geometry_summary"
CAPTURE_CONFIG_EVENT = (
    "native_renderer.discovery.vehicle_shadow_color_capture_config"
)
CAPTURE_RESULT_EVENT = (
    "native_renderer.discovery.vehicle_shadow_color_capture_result"
)
CAPTURE_SUMMARY_EVENT = (
    "native_renderer.discovery.vehicle_shadow_color_capture_summary"
)
REJECTION_REASON_FIELDS = (
    "reject_resolved_input",
    "reject_unsupported_geometry",
    "reject_empty_draw",
    "reject_vertex_binding_count",
    "reject_vertex_binding_overflow",
    "reject_vertex_attribute_overflow",
    "reject_vertex_constant_overflow",
    "reject_pixel_constant_overflow",
    "reject_texture_state_overflow",
    "reject_memexport",
    "reject_query",
    "reject_texture_count",
    "reject_texture_layout",
    "reject_prepared_pipeline",
    "reject_render_targets",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(record, key):
    try:
        return int(record[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing or invalid integer field: {key}") from error


def hexadecimal(record, key):
    try:
        return int(record[key], 16)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing or invalid hexadecimal field: {key}") from error


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


def summarize(log_path):
    events = load_events(log_path)
    configs = [event for event in events if event.get("event") == CONFIG_EVENT]
    epochs = [event for event in events if event.get("event") == EPOCH_EVENT]
    correlations = [
        event for event in events if event.get("event") == CORRELATION_EVENT
    ]
    candidates = [
        event for event in events if event.get("event") == CANDIDATE_EVENT
    ]
    summaries = [
        event for event in events if event.get("event") == SUMMARY_EVENT
    ]
    capture_configs = [
        event for event in events if event.get("event") == CAPTURE_CONFIG_EVENT
    ]
    capture_results = [
        event for event in events if event.get("event") == CAPTURE_RESULT_EVENT
    ]
    capture_summaries = [
        event for event in events if event.get("event") == CAPTURE_SUMMARY_EVENT
    ]
    require(len(configs) == 1, "expected exactly one correlation config event")
    require(configs[0].get("status") == "armed", "correlation was not armed")
    require(len(summaries) == 1, "expected exactly one correlation summary")
    summary = summaries[0]
    require(summary.get("status") == "qualified_epoch_observed", "no qualified epoch")
    require(integer(summary, "epochs_committed") == len(epochs), "epoch accounting drift")
    require(integer(summary, "epochs_committed") > 0, "no epoch was committed")
    require(summary.get("seed_accounting_complete") == "true", "seed accounting drift")
    require(integer(summary, "seed_overflow") == 0, "geometry seed table overflowed")
    require(
        integer(summary, "correlation_overflow") == 0,
        "geometry correlation table overflowed",
    )
    require(
        integer(summary, "correlations") == len(correlations),
        "correlation event accounting drift",
    )
    require(
        integer(summary, "correlations") == len(candidates),
        "candidate family accounting drift",
    )
    require(
        integer(summary, "color_draws_matched")
        == integer(summary, "full_geometry_matches")
        + integer(summary, "index_vertex_matches"),
        "match accounting drift",
    )
    require(
        summary.get("mechanical_rejection_accounting_complete") == "true",
        "mechanical rejection accounting drift",
    )
    mechanically_eligible_draws = integer(
        summary, "mechanically_eligible_draws"
    )
    mechanically_rejected_draws = integer(
        summary, "mechanically_rejected_draws"
    )
    require(
        mechanically_eligible_draws + mechanically_rejected_draws
        == integer(summary, "color_draws_matched"),
        "mechanical eligibility accounting drift",
    )
    require(
        summary.get("private_capture_rejection_accounting_complete") == "true",
        "private capture rejection accounting drift",
    )
    private_capture_eligible_draws = integer(
        summary, "private_capture_eligible_draws"
    )
    private_capture_rejected_draws = integer(
        summary, "private_capture_rejected_draws"
    )
    require(
        private_capture_eligible_draws + private_capture_rejected_draws
        == integer(summary, "color_draws_matched"),
        "private capture eligibility accounting drift",
    )
    require(
        summary.get("color_run_accounting_complete") == "true",
        "color run accounting drift",
    )
    color_runs = integer(summary, "color_runs")
    color_run_draws = integer(summary, "color_run_draws")
    require(
        color_run_draws == integer(summary, "color_draws_matched"),
        "color run draw accounting drift",
    )
    require(
        integer(summary, "multi_draw_color_runs") <= color_runs,
        "multi-draw color run accounting drift",
    )
    require(
        integer(summary, "full_family_color_runs") <= color_runs,
        "full-family color run accounting drift",
    )
    sequence_hash = summary.get("first_full_family_sequence_hash", "")
    require(len(sequence_hash) == 16, "invalid full-family sequence hash")
    safety_events = [*configs, *epochs, *correlations, *candidates, summary]
    for event in safety_events:
        require(event.get("native_draw") == "false", "native draw was enabled")
        require(event.get("xenos_authority") == "true", "Xenos authority changed")
        require(
            event.get("suppression_allowed") == "false",
            "suppression was allowed",
        )
    for event in epochs:
        require(integer(event, "draw_count") == 80, "epoch draw count drift")
        require(
            event.get("promotion_boundary")
            == "backend_recorded_full_80_draw_epoch",
            "partial epoch was promoted",
        )
    for event in correlations:
        require(
            event.get("classification")
            == "vehicle_color_geometry_correlation_candidate",
            "correlation classification drift",
        )
        require(
            event.get("match")
            in {
                "exact_geometry_resource_set",
                "exact_index_and_shared_vertex_resource",
            },
            "unbounded correlation match",
        )
    for event in candidates:
        require(
            event.get("classification")
            == "bounded_vehicle_color_geometry_candidate_family",
            "candidate family classification drift",
        )
        require(integer(event, "draws") > 0, "empty candidate family")
        require(
            integer(event, "last_frame") >= integer(event, "first_frame"),
            "candidate frame range drift",
        )
        require(
            event.get("pose_variation_observed")
            == ("true" if integer(event, "parameter_switches") else "false"),
            "pose variation accounting drift",
        )
        eligible_draws = integer(event, "mechanically_eligible_draws")
        rejected_draws = integer(event, "mechanically_rejected_draws")
        require(
            eligible_draws + rejected_draws == integer(event, "draws"),
            "candidate mechanical eligibility accounting drift",
        )
        first_mask = hexadecimal(event, "first_rejection_mask")
        last_mask = hexadecimal(event, "last_rejection_mask")
        mask_or = hexadecimal(event, "rejection_mask_or")
        mask_and = hexadecimal(event, "rejection_mask_and")
        require(first_mask & mask_or == first_mask, "candidate first mask drift")
        require(last_mask & mask_or == last_mask, "candidate last mask drift")
        require(mask_and & mask_or == mask_and, "candidate mask bounds drift")
        require(
            not eligible_draws or mask_and == 0,
            "candidate eligible draw retained a stable rejection",
        )
        private_eligible_draws = integer(
            event, "private_capture_eligible_draws"
        )
        private_rejected_draws = integer(
            event, "private_capture_rejected_draws"
        )
        require(
            private_eligible_draws + private_rejected_draws
            == integer(event, "draws"),
            "candidate private capture accounting drift",
        )
        private_first_mask = hexadecimal(
            event, "first_private_capture_rejection_mask"
        )
        private_last_mask = hexadecimal(
            event, "last_private_capture_rejection_mask"
        )
        private_mask_or = hexadecimal(
            event, "private_capture_rejection_mask_or"
        )
        private_mask_and = hexadecimal(
            event, "private_capture_rejection_mask_and"
        )
        require(
            private_first_mask & private_mask_or == private_first_mask,
            "candidate private first mask drift",
        )
        require(
            private_last_mask & private_mask_or == private_last_mask,
            "candidate private last mask drift",
        )
        require(
            private_mask_and & private_mask_or == private_mask_and,
            "candidate private mask bounds drift",
        )
        require(
            not private_eligible_draws or private_mask_and == 0,
            "candidate private eligible draw retained a stable rejection",
        )
        for key in (
            "prepared_signature",
            "template_key",
            "draw_argument_hash",
            "geometry_resource_hash",
            "texture_resource_hash",
            "prepared_pipeline_hash",
            "first_parameter_hash",
            "last_parameter_hash",
        ):
            require(len(event.get(key, "")) == 16, f"invalid candidate hash: {key}")
    capture = None
    if capture_configs or capture_results or capture_summaries:
        require(len(capture_configs) == 1, "expected one color capture config")
        require(capture_configs[0].get("status") == "armed", "color capture was not armed")
        require(len(capture_summaries) == 1, "expected one color capture summary")
        capture_summary = capture_summaries[0]
        require(
            capture_summary.get("request_accounting_complete") == "true",
            "color capture accounting drift",
        )
        requests = integer(capture_summary, "requests")
        recorded = integer(capture_summary, "recorded")
        require(requests in {0, 1}, "color capture request bound drift")
        require(recorded in {0, 1}, "color capture result bound drift")
        require(len(capture_results) == requests, "color capture result drift")
        require(recorded <= requests, "recorded capture exceeds requests")
        require(
            capture_summary.get("private_replay_accounting_complete") == "true",
            "private replay accounting drift",
        )
        private_replay_requests = integer(
            capture_summary, "private_replay_requests"
        )
        private_replay_recorded = integer(
            capture_summary, "private_replay_recorded"
        )
        private_replay_failures = integer(
            capture_summary, "private_replay_target_creation_failures"
        ) + integer(capture_summary, "private_replay_unsupported")
        private_replay_limit = integer(
            capture_summary, "private_replay_limit"
        )
        require(
            private_replay_requests
            == private_replay_recorded + private_replay_failures,
            "private replay outcome drift",
        )
        require(
            private_replay_requests <= private_replay_limit,
            "private replay request bound drift",
        )
        require(
            not private_replay_failures
            or capture_summary.get("private_replay_status") == "failed_closed",
            "private replay did not fail closed",
        )
        for event in [*capture_configs, *capture_results, capture_summary]:
            require(
                event.get("xenos_draw") == "preserved"
                and event.get("output_authority") == "xenos"
                and event.get("suppression_allowed") == "false",
                "color capture changed output authority",
            )
        if recorded:
            require(
                capture_results[0].get("status")
                == "recorded_private_color_candidate",
                "private color capture result drift",
            )
            require(
                capture_results[0].get("native_draw") == "private_capture_only",
                "color capture escaped private replay",
            )
        capture = {
            "config": capture_configs[0],
            "result": capture_results[0] if capture_results else None,
            "summary": capture_summary,
        }
    return {
        "schema": SCHEMA,
        "source_log": str(log_path),
        "totals": {
            "epochs_committed": integer(summary, "epochs_committed"),
            "unique_geometry_seeds": integer(summary, "unique_geometry_seeds"),
            "color_draws_examined": integer(summary, "color_draws_examined"),
            "color_draws_matched": integer(summary, "color_draws_matched"),
            "full_geometry_matches": integer(summary, "full_geometry_matches"),
            "index_vertex_matches": integer(summary, "index_vertex_matches"),
            "mechanically_eligible_draws": mechanically_eligible_draws,
            "mechanically_rejected_draws": mechanically_rejected_draws,
            "private_capture_eligible_draws": private_capture_eligible_draws,
            "private_capture_rejected_draws": private_capture_rejected_draws,
            "correlations": len(correlations),
        },
        "mechanical_rejections": {
            key.removeprefix("reject_"): integer(summary, key)
            for key in REJECTION_REASON_FIELDS
        },
        "color_run_topology": {
            "runs": color_runs,
            "draws": color_run_draws,
            "multi_draw_runs": integer(summary, "multi_draw_color_runs"),
            "maximum_run_length": integer(
                summary, "maximum_color_run_length"
            ),
            "full_family_runs": integer(summary, "full_family_color_runs"),
            "first_full_family_sequence_hash": sequence_hash,
            "full_family_sequence_variants": integer(
                summary, "full_family_sequence_variants"
            ),
        },
        "epochs": epochs,
        "correlations": correlations,
        "candidate_families": candidates,
        "private_color_capture": capture,
        "qualification": {
            "working_color_bridge_candidate": bool(correlations),
            "private_color_capture_recorded": bool(
                capture
                and integer(capture["summary"], "recorded") == 1
            ),
            "private_color_replay_stable": bool(
                capture
                and integer(capture["summary"], "private_replay_requests")
                and integer(capture["summary"], "private_replay_requests")
                == integer(capture["summary"], "private_replay_recorded")
            ),
            "object_identity_proven": False,
            "mesh_material_contract_proven": False,
            "native_admission_allowed": False,
        },
        "safety": {
            "guest_payload_capture": False,
            "native_draw": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = summarize(arguments.log)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
