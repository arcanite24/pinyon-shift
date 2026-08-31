"""Summarize capture-proven vehicle shadow geometry/color correlations."""

import argparse
import json
from pathlib import Path


SCHEMA = "pinyon-shift.native-renderer-vehicle-shadow-geometry.v12"
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
RETAINED_CONFIG_EVENT = (
    "native_renderer.discovery.vehicle_shadow_color_retained_config"
)
RETAINED_RESULT_EVENT = (
    "native_renderer.discovery.vehicle_shadow_color_retained_result"
)
RETAINED_SUMMARY_EVENT = (
    "native_renderer.discovery.vehicle_shadow_color_retained_summary"
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


def decimal(record, key):
    try:
        return float(record[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing or invalid decimal field: {key}") from error


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
    retained_configs = [
        event for event in events if event.get("event") == RETAINED_CONFIG_EVENT
    ]
    retained_results = [
        event for event in events if event.get("event") == RETAINED_RESULT_EVENT
    ]
    retained_summaries = [
        event for event in events if event.get("event") == RETAINED_SUMMARY_EVENT
    ]
    require(len(configs) == 1, "expected exactly one correlation config event")
    require(configs[0].get("status") == "armed", "correlation was not armed")
    require(
        configs[0].get("typed_constant_upload_hook")
        == "82435E78:r3,r4,r5,r6,lr",
        "typed constant upload hook drift",
    )
    require(
        configs[0].get("typed_constant_upload_contract")
        == "exact_shader_used_vertex_register_hash",
        "typed constant upload contract drift",
    )
    require(
        integer(configs[0], "typed_constant_upload_capacity") == 8192,
        "typed constant upload capacity drift",
    )
    require(
        integer(configs[0], "typed_constant_upload_maximum_age_frames") == 1,
        "typed constant upload freshness drift",
    )
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
    constant_identity_scans = integer(summary, "constant_identity_scans")
    require(
        constant_identity_scans == integer(summary, "color_draws_matched"),
        "constant identity scan accounting drift",
    )
    require(
        summary.get("constant_position_accounting_complete") == "true",
        "constant position accounting drift",
    )
    require(
        integer(summary, "constant_position_unique_matches")
        + integer(summary, "constant_position_ambiguous_matches")
        + integer(summary, "constant_position_misses")
        == constant_identity_scans,
        "constant position outcome drift",
    )
    require(
        summary.get("constant_forward_accounting_complete") == "true",
        "constant forward accounting drift",
    )
    require(
        integer(summary, "constant_forward_unique_matches")
        + integer(summary, "constant_forward_ambiguous_matches")
        + integer(summary, "constant_forward_misses")
        == constant_identity_scans,
        "constant forward outcome drift",
    )
    require(
        integer(summary, "constant_identity_maximum_pose_age_frames") == 1,
        "constant identity freshness drift",
    )
    require(
        summary.get("material_topology_group_accounting_complete") == "true",
        "material topology group accounting drift",
    )
    material_topology_groups = integer(summary, "material_topology_groups")
    require(
        0 < material_topology_groups <= len(candidates),
        "material topology group bounds drift",
    )
    require(
        summary.get("material_topology_contract")
        == "shader_specialization_render_state_texture_layout",
        "material topology contract drift",
    )
    typed_upload_scans = integer(summary, "typed_upload_scans")
    typed_upload_exact_matches = integer(
        summary, "typed_upload_exact_matches"
    )
    typed_upload_misses = integer(summary, "typed_upload_misses")
    typed_upload_exact_used_vectors = integer(
        summary, "typed_upload_exact_used_vectors"
    )
    typed_upload_fresh_candidates = integer(
        summary, "typed_upload_fresh_candidates"
    )
    typed_upload_no_overlap_candidates = integer(
        summary, "typed_upload_no_overlap_candidates"
    )
    typed_upload_hash_mismatch_candidates = integer(
        summary, "typed_upload_hash_mismatch_candidates"
    )
    typed_upload_exact_candidates = integer(
        summary, "typed_upload_exact_candidates"
    )
    require(
        typed_upload_scans == integer(summary, "color_draws_matched"),
        "typed upload scan accounting drift",
    )
    require(
        summary.get("typed_upload_outcome_accounting_complete") == "true",
        "typed upload outcome accounting drift",
    )
    require(
        typed_upload_exact_matches + typed_upload_misses
        == typed_upload_scans,
        "typed upload outcome drift",
    )
    require(
        typed_upload_exact_used_vectors >= typed_upload_exact_matches,
        "typed upload used-vector accounting drift",
    )
    require(
        summary.get("typed_upload_candidate_accounting_complete") == "true",
        "typed upload candidate accounting drift",
    )
    require(
        typed_upload_no_overlap_candidates
        + typed_upload_hash_mismatch_candidates
        + typed_upload_exact_candidates
        == typed_upload_fresh_candidates,
        "typed upload candidate outcome drift",
    )
    require(
        integer(summary, "typed_upload_valid")
        + integer(summary, "typed_upload_invalid_register_range")
        + integer(summary, "typed_upload_invalid_source_range")
        == integer(summary, "typed_upload_observations"),
        "typed upload observation accounting drift",
    )
    require(
        integer(summary, "typed_upload_capacity") == 8192,
        "typed upload summary capacity drift",
    )
    require(
        integer(summary, "typed_upload_maximum_age_frames") == 1,
        "typed upload summary freshness drift",
    )
    require(
        summary.get("typed_upload_contract")
        == "82435E78_exact_shader_used_vertex_register_hash",
        "typed upload summary contract drift",
    )
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
        for key in (
            "material_topology_key",
            "vertex_shader",
            "pixel_shader",
            "render_state_hash",
            "texture_layout_hash",
        ):
            require(
                len(event.get(key, "")) == 16,
                f"invalid correlation material hash: {key}",
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
        constant_scans = integer(event, "constant_identity_scans")
        require(
            constant_scans == integer(event, "draws"),
            "candidate constant scan accounting drift",
        )
        require(
            integer(event, "constant_position_unique_matches")
            + integer(event, "constant_position_ambiguous_matches")
            + integer(event, "constant_position_misses")
            == constant_scans,
            "candidate constant position accounting drift",
        )
        require(
            integer(event, "constant_forward_unique_matches")
            + integer(event, "constant_forward_ambiguous_matches")
            + integer(event, "constant_forward_misses")
            == constant_scans,
            "candidate constant forward accounting drift",
        )
        stable_position_candidate = (
            integer(event, "constant_position_unique_matches")
            == integer(event, "draws")
            and integer(event, "constant_position_ambiguous_matches") == 0
            and integer(event, "constant_position_misses") == 0
            and integer(event, "constant_position_identity_variations") == 0
            and integer(event, "constant_position_register_variations") == 0
        )
        require(
            event.get("constant_identity_classification")
            == (
                "stable_tight_position_candidate"
                if stable_position_candidate
                else "unresolved"
            ),
            "candidate constant identity classification drift",
        )
        if integer(event, "constant_position_unique_matches"):
            hexadecimal(event, "constant_position_identity_generation")
            hexadecimal(event, "constant_position_identity_owner")
            integer(event, "constant_position_identity_slot")
            integer(event, "constant_position_register")
            require(
                decimal(event, "closest_position_delta_squared") <= 0.25,
                "candidate position threshold drift",
            )
        if integer(event, "constant_forward_unique_matches"):
            hexadecimal(event, "constant_forward_identity_generation")
            hexadecimal(event, "constant_forward_identity_owner")
            integer(event, "constant_forward_identity_slot")
            integer(event, "constant_forward_register")
            require(
                integer(event, "constant_forward_sign") in {-1, 1},
                "candidate forward sign drift",
            )
            require(
                decimal(event, "closest_forward_delta_squared") <= 0.04,
                "candidate forward threshold drift",
            )
        family_typed_upload_scans = integer(event, "typed_upload_scans")
        family_typed_upload_matches = integer(
            event, "typed_upload_exact_matches"
        )
        family_typed_upload_misses = integer(event, "typed_upload_misses")
        family_typed_upload_fresh_candidates = integer(
            event, "typed_upload_fresh_candidates"
        )
        family_typed_upload_no_overlap_candidates = integer(
            event, "typed_upload_no_overlap_candidates"
        )
        family_typed_upload_hash_mismatch_candidates = integer(
            event, "typed_upload_hash_mismatch_candidates"
        )
        family_typed_upload_exact_candidates = integer(
            event, "typed_upload_exact_candidates"
        )
        require(
            family_typed_upload_scans == integer(event, "draws"),
            "candidate typed upload scan accounting drift",
        )
        require(
            family_typed_upload_matches + family_typed_upload_misses
            == family_typed_upload_scans,
            "candidate typed upload outcome drift",
        )
        require(
            family_typed_upload_no_overlap_candidates
            + family_typed_upload_hash_mismatch_candidates
            + family_typed_upload_exact_candidates
            == family_typed_upload_fresh_candidates,
            "candidate typed upload candidate outcome drift",
        )
        observed_register_min = integer(
            event, "typed_upload_observed_register_min"
        )
        observed_register_max = integer(
            event, "typed_upload_observed_register_max"
        )
        require(
            0 <= observed_register_min <= observed_register_max < 256,
            "candidate typed upload observed register range drift",
        )
        stable_typed_upload_candidate = (
            family_typed_upload_matches == integer(event, "draws")
            and family_typed_upload_misses == 0
            and integer(event, "typed_upload_exact_used_vectors")
            >= family_typed_upload_matches
            and integer(event, "typed_upload_start_register_variations") == 0
            and integer(event, "typed_upload_vector_count_variations") == 0
            and integer(
                event, "typed_upload_used_vector_count_variations"
            ) == 0
            and integer(event, "typed_upload_caller_variations") == 0
        )
        require(
            event.get("typed_upload_classification")
            == (
                "stable_exact_vertex_register_candidate"
                if stable_typed_upload_candidate
                else "unresolved"
            ),
            "candidate typed upload classification drift",
        )
        if family_typed_upload_matches:
            require(
                0 <= integer(event, "typed_upload_start_register") < 256,
                "candidate typed upload register drift",
            )
            require(
                0 < integer(event, "typed_upload_vector_count") <= 64,
                "candidate typed upload vector count drift",
            )
            require(
                0 < integer(event, "typed_upload_used_vector_count")
                <= integer(event, "typed_upload_vector_count"),
                "candidate typed upload used vector count drift",
            )
            hexadecimal(event, "typed_upload_source_address")
            hexadecimal(event, "typed_upload_buffer_address")
            hexadecimal(event, "typed_upload_caller_return_address")
        for key in (
            "prepared_signature",
            "template_key",
            "material_topology_key",
            "vertex_shader",
            "pixel_shader",
            "render_state_hash",
            "texture_layout_hash",
            "first_material_parameter_hash",
            "last_material_parameter_hash",
            "draw_argument_hash",
            "geometry_resource_hash",
            "texture_resource_hash",
            "prepared_pipeline_hash",
            "first_parameter_hash",
            "last_parameter_hash",
        ):
            require(len(event.get(key, "")) == 16, f"invalid candidate hash: {key}")
        require(
            integer(event, "material_parameter_switches")
            <= integer(event, "draws") - 1,
            "candidate material parameter switch drift",
        )
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
    retained = None
    if retained_configs or retained_results or retained_summaries:
        require(len(retained_configs) == 1, "expected one retained pass config")
        require(
            retained_configs[0].get("status") == "armed",
            "retained pass was not armed",
        )
        require(len(retained_summaries) == 1, "expected one retained pass summary")
        retained_summary = retained_summaries[0]
        require(
            retained_summary.get("request_accounting_complete") == "true",
            "retained pass request accounting drift",
        )
        retained_requests = integer(retained_summary, "requests")
        retained_recorded = integer(retained_summary, "recorded")
        retained_failures = integer(
            retained_summary, "target_creation_failures"
        ) + integer(retained_summary, "unsupported")
        require(
            retained_requests == retained_recorded + retained_failures,
            "retained pass outcome drift",
        )
        frames_started = integer(retained_summary, "frames_started")
        frames_completed = integer(retained_summary, "frames_completed")
        frames_failed = integer(retained_summary, "frames_failed")
        draws_per_frame = integer(retained_summary, "draws_per_frame")
        pass_limit = integer(retained_summary, "pass_limit")
        require(draws_per_frame == 30, "retained family count drift")
        require(frames_started <= pass_limit, "retained pass limit drift")
        require(
            retained_summary.get("frame_accounting_complete") == "true",
            "retained frame accounting drift",
        )
        require(
            frames_started == frames_completed + frames_failed,
            "retained frame outcome drift",
        )
        require(
            retained_requests <= frames_started * draws_per_frame,
            "retained request frame bound drift",
        )
        reused_target_requests = integer(
            retained_summary, "reused_target_requests"
        )
        require(
            reused_target_requests <= retained_requests,
            "retained target reuse bound drift",
        )
        if not retained_failures and frames_completed == frames_started:
            require(
                retained_requests == frames_completed * draws_per_frame,
                "retained complete-frame request drift",
            )
            require(
                reused_target_requests
                == frames_completed * (draws_per_frame - 1),
                "retained target lifecycle drift",
            )
        require(
            not retained_failures
            or retained_summary.get("status") == "failed_closed",
            "retained pass did not fail closed",
        )
        capture_recorded = retained_summary.get("capture_recorded") == "true"
        require(
            len(retained_results) == (1 if capture_recorded else 0),
            "retained capture result drift",
        )
        for event in [*retained_configs, *retained_results, retained_summary]:
            require(
                event.get("xenos_draw") == "preserved"
                and event.get("output_authority") == "xenos"
                and event.get("suppression_allowed") == "false",
                "retained pass changed output authority",
            )
        if retained_results:
            require(
                retained_results[0].get("status")
                == "recorded_complete_private_vehicle_pass",
                "retained pass result drift",
            )
            require(
                integer(retained_results[0], "draw_count") == draws_per_frame,
                "retained result draw count drift",
            )
        retained = {
            "config": retained_configs[0],
            "result": retained_results[0] if retained_results else None,
            "summary": retained_summary,
        }
    stable_position_candidates = [
        event
        for event in candidates
        if event.get("constant_identity_classification")
        == "stable_tight_position_candidate"
    ]
    stable_position_identities = {
        (
            event.get("constant_position_identity_generation"),
            event.get("constant_position_identity_owner"),
            event.get("constant_position_identity_slot"),
        )
        for event in stable_position_candidates
    }
    complete_shared_vehicle_transform_candidate = (
        len(candidates) == 30
        and len(stable_position_candidates) == len(candidates)
        and len(stable_position_identities) == 1
    )
    stable_typed_upload_candidates = [
        event
        for event in candidates
        if event.get("typed_upload_classification")
        == "stable_exact_vertex_register_candidate"
    ]
    complete_typed_upload_bridge_candidate = (
        len(candidates) == 30
        and len(stable_typed_upload_candidates) == len(candidates)
    )
    typed_upload_callers = sorted(
        {
            event["typed_upload_caller_return_address"]
            for event in candidates
            if integer(event, "typed_upload_exact_matches")
        }
    )
    material_groups = {}
    for event in candidates:
        material_groups.setdefault(event["material_topology_key"], []).append(
            event["prepared_signature"]
        )
    require(
        len(material_groups) == material_topology_groups,
        "material topology candidate accounting drift",
    )
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
        "constant_identity": {
            "scans": constant_identity_scans,
            "missing_fresh_pose": integer(
                summary, "constant_identity_missing_fresh_pose"
            ),
            "vectors_scanned": integer(summary, "constant_vectors_scanned"),
            "non_finite_vectors": integer(
                summary, "constant_non_finite_vectors"
            ),
            "identity_comparisons": integer(
                summary, "constant_identity_comparisons"
            ),
            "stable_position_candidate_families": len(
                stable_position_candidates
            ),
            "stable_position_identities": [
                {
                    "generation": generation,
                    "owner": owner,
                    "slot": slot,
                }
                for generation, owner, slot in sorted(
                    stable_position_identities
                )
            ],
        },
        "typed_constant_upload": {
            "observations": integer(summary, "typed_upload_observations"),
            "valid": integer(summary, "typed_upload_valid"),
            "invalid_register_range": integer(
                summary, "typed_upload_invalid_register_range"
            ),
            "invalid_source_range": integer(
                summary, "typed_upload_invalid_source_range"
            ),
            "overwrites": integer(summary, "typed_upload_overwrites"),
            "capacity": integer(summary, "typed_upload_capacity"),
            "scans": typed_upload_scans,
            "exact_matches": typed_upload_exact_matches,
            "misses": typed_upload_misses,
            "exact_used_vectors": typed_upload_exact_used_vectors,
            "fresh_candidates": typed_upload_fresh_candidates,
            "no_overlap_candidates": typed_upload_no_overlap_candidates,
            "hash_mismatch_candidates": (
                typed_upload_hash_mismatch_candidates
            ),
            "exact_candidates": typed_upload_exact_candidates,
            "stable_candidate_families": len(
                stable_typed_upload_candidates
            ),
            "caller_return_addresses": typed_upload_callers,
        },
        "material_topology": {
            "group_count": material_topology_groups,
            "groups": [
                {
                    "material_topology_key": key,
                    "family_count": len(signatures),
                    "prepared_signatures": signatures,
                }
                for key, signatures in sorted(material_groups.items())
            ],
            "families_with_parameter_variation": sum(
                integer(event, "material_parameter_switches") > 0
                for event in candidates
            ),
        },
        "private_color_capture": capture,
        "private_retained_color_pass": retained,
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
            "private_retained_color_pass_stable": bool(
                retained
                and integer(retained["summary"], "frames_completed")
                == integer(retained["summary"], "pass_limit")
                and integer(retained["summary"], "frames_failed") == 0
                and integer(retained["summary"], "requests")
                == integer(retained["summary"], "recorded")
                and retained["summary"].get("capture_recorded") == "true"
            ),
            "complete_shared_vehicle_transform_candidate": (
                complete_shared_vehicle_transform_candidate
            ),
            "complete_typed_upload_bridge_candidate": (
                complete_typed_upload_bridge_candidate
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
