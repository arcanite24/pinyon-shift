"""Validate the in-order semantic batch-admission census."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-semantic-batch-admission.v4"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
TITLE_CONFIG = "native_renderer.discovery.title_provenance_config"
TITLE_SUMMARY = "native_renderer.discovery.title_provenance_summary"
BATCH_ENTRY = "native_renderer.discovery.semantic_batch_entry"
BATCH_SUMMARY = "native_renderer.discovery.semantic_batch_summary"
EQUIVALENCE_ENTRY = (
    "native_renderer.discovery.semantic_batch_equivalence_entry"
)
EQUIVALENCE_SUMMARY = (
    "native_renderer.discovery.semantic_batch_equivalence_summary"
)
STATE_CACHE_SUMMARY = (
    "native_renderer.discovery.semantic_state_cache_summary"
)
EXPECTED_ORDERING = "exact_consecutive_prepared_draw_order"
EXPECTED_EQUIVALENCES = (
    "mesh_material_instance",
    "material_state_reuse",
    "pipeline_state_reuse",
)
EXPECTED_STATE_CACHE_LEVELS = ("material_state", "pipeline_state")
EXPECTED_STATE_CACHE_PROFILES = {
    "compact": 64,
    "balanced": 256,
    "headroom": 1024,
}
REJECTION_FIELDS = {
    "missing_title_resource": "reject_missing_title_resource",
    "non_opaque": "reject_non_opaque",
    "resolved_input": "reject_resolved_input",
    "query_or_conditional": "reject_query_or_conditional",
    "memexport": "reject_memexport",
    "unbounded_geometry": "reject_unbounded_geometry",
    "unsupported_geometry": "reject_unsupported_geometry",
    "constant_overflow": "reject_constant_overflow",
    "unbounded_texture_layout": "reject_unbounded_texture_layout",
    "texture_count": "reject_texture_count",
    "incomplete_prepared_pipeline": "reject_incomplete_prepared_pipeline",
    "render_target_coverage": "reject_render_target_coverage",
}


def read_events(paths: list[pathlib.Path]) -> list[dict]:
    events = []
    wanted = {
        TITLE_CONFIG,
        TITLE_SUMMARY,
        BATCH_ENTRY,
        BATCH_SUMMARY,
        EQUIVALENCE_ENTRY,
        EQUIVALENCE_SUMMARY,
        STATE_CACHE_SUMMARY,
    }
    for path in paths:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error}"
                ) from error
            if event.get("event") in wanted:
                events.append(event)
    return events


def _integer(mapping: dict, key: str) -> int:
    try:
        return int(mapping.get(key, ""))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid integer field: {key}") from error


def _number(mapping: dict, key: str) -> float:
    try:
        return float(mapping.get(key, ""))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid number field: {key}") from error


def _hex(mapping: dict, key: str, width: int) -> str:
    value = str(mapping.get(key, "")).upper()
    if len(value) != width:
        raise ValueError(f"invalid hexadecimal field: {key}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid hexadecimal field: {key}") from error
    return value


def _optional_hex(mapping: dict, key: str, width: int) -> str | None:
    if mapping.get(key, "") == "":
        return None
    return _hex(mapping, key, width)


def _boolean(mapping: dict, key: str) -> bool:
    value = str(mapping.get(key, "")).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"invalid boolean field: {key}")
    return value == "true"


def _select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"semantic-batch session not found: {requested}")
        return requested
    sessions = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == TITLE_CONFIG
        and event.get("status") == "armed"
    ]
    if not sessions or not sessions[-1]:
        raise ValueError("no armed semantic-batch session found")
    return sessions[-1]


def _validate_static(static: dict) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    lifecycle = static.get("procedural_model_receiver_lifecycle", {})
    contract = lifecycle.get("semantic_draw_association", {})
    expected = {
        "semantic_pm4_packet_construction_proved": True,
        "semantic_pm4_backend_join_required": True,
        "semantic_prepared_contract_runtime_join_required": True,
        "semantic_catalog_classification": (
            "immutable_template_and_dynamic_resource_instance"
        ),
        "semantic_batch_admission_census_required": True,
        "semantic_batch_ordering": EXPECTED_ORDERING,
        "semantic_batch_world_family_partition": (
            "none_or_exact_track_or_exact_static_or_both"
        ),
        "semantic_batch_equivalence_ladder_required": True,
        "semantic_batch_pipeline_identity": (
            "resource_free_layout_and_prepared_state"
        ),
        "semantic_batch_execution_enabled": False,
        "semantic_state_cache_required": True,
        "semantic_state_cache_policy": "set_associative_lru",
        "semantic_state_cache_profiles": (
            "compact:64,balanced:256,headroom:1024"
        ),
        "semantic_state_cache_execution_enabled": False,
        "native_rendering_enabled": False,
        "suppression_eligible": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("unsupported semantic-batch static contract")
    return contract


def _build_equivalence_levels(
    selected: list[dict], eligible_draws: int
) -> dict[str, dict]:
    result = {}
    for equivalence in EXPECTED_EQUIVALENCES:
        summaries = [
            event
            for event in selected
            if event.get("event") == EQUIVALENCE_SUMMARY
            and event.get("equivalence") == equivalence
        ]
        if len(summaries) != 1:
            raise ValueError(
                f"semantic-batch equivalence needs one summary: {equivalence}"
            )
        summary = summaries[0]
        if (
            summary.get("status") != "complete"
            or summary.get("accounting_complete") != "true"
            or summary.get("ordering") != EXPECTED_ORDERING
            or summary.get("reordering") != "false"
            or summary.get("parameterization") != "observed_not_executed"
            or summary.get("native_batch_execution") != "false"
            or summary.get("native_upload") != "false"
            or summary.get("native_draw") != "false"
            or summary.get("xenos_authority") != "true"
            or summary.get("suppression_allowed") != "false"
        ):
            raise ValueError(
                f"semantic-batch equivalence is incomplete or unsafe: {equivalence}"
            )
        expected_identity = {
            "mesh_material_instance": (
                "pipeline,draw_arguments,geometry,texture,render_target"
            ),
            "material_state_reuse": "pipeline,texture,render_target",
            "pipeline_state_reuse": "pipeline",
        }[equivalence]
        if summary.get("identity") != expected_identity:
            raise ValueError(
                f"semantic-batch equivalence identity drifted: {equivalence}"
            )

        entries = []
        seen_keys = set()
        aggregates = {
            "draws": 0,
            "consecutive_runs": 0,
            "multi_draw_runs": 0,
            "multi_draw_draws": 0,
            "maximum_run_length": 0,
            "instance_switches": 0,
            "same_instance_continuations": 0,
            "parameter_switches": 0,
            "same_parameter_continuations": 0,
        }
        for event in selected:
            if (
                event.get("event") != EQUIVALENCE_ENTRY
                or event.get("equivalence") != equivalence
            ):
                continue
            key = _hex(event, "opportunity_key", 16)
            if key in seen_keys or int(key, 16) == 0:
                raise ValueError(
                    f"duplicate or zero equivalence key: {equivalence}"
                )
            seen_keys.add(key)
            if (
                event.get("ordering") != EXPECTED_ORDERING
                or event.get("xenos_draw") != "preserved"
                or event.get("native_batch") != "false"
                or event.get("suppression_allowed") != "false"
            ):
                raise ValueError(
                    f"semantic-batch equivalence crossed safety: {equivalence}"
                )
            item = {
                "opportunity_key": key,
                "pipeline_key": _hex(event, "pipeline_key", 16),
                "draw_argument_hash": _optional_hex(
                    event, "draw_argument_hash", 16
                ),
                "geometry_resource_hash": _optional_hex(
                    event, "geometry_resource_hash", 16
                ),
                "texture_resource_hash": _optional_hex(
                    event, "texture_resource_hash", 16
                ),
                "render_target_resource_hash": _optional_hex(
                    event, "render_target_resource_hash", 16
                ),
                **{
                    name: _integer(event, name)
                    for name in (
                        "draws",
                        "frames",
                        "first_frame",
                        "last_frame",
                        "consecutive_runs",
                        "multi_draw_runs",
                        "multi_draw_draws",
                        "maximum_run_length",
                        "instance_switches",
                        "same_instance_continuations",
                        "parameter_switches",
                        "same_parameter_continuations",
                    )
                },
            }
            if (
                item["draws"] <= 0
                or item["frames"] <= 0
                or item["last_frame"] < item["first_frame"]
                or item["consecutive_runs"] <= 0
                or item["maximum_run_length"] <= 0
                or item["multi_draw_draws"] > item["draws"]
            ):
                raise ValueError(
                    f"invalid semantic-batch equivalence entry: {equivalence}"
                )
            if equivalence == "mesh_material_instance":
                if not all(
                    item[name]
                    for name in (
                        "draw_argument_hash",
                        "geometry_resource_hash",
                        "texture_resource_hash",
                        "render_target_resource_hash",
                    )
                ):
                    raise ValueError("mesh-material identity is incomplete")
            elif equivalence == "material_state_reuse":
                if (
                    item["draw_argument_hash"]
                    or item["geometry_resource_hash"]
                    or not item["texture_resource_hash"]
                    or not item["render_target_resource_hash"]
                ):
                    raise ValueError("material identity is inconsistent")
            elif any(
                item[name]
                for name in (
                    "draw_argument_hash",
                    "geometry_resource_hash",
                    "texture_resource_hash",
                    "render_target_resource_hash",
                )
            ):
                raise ValueError("pipeline identity is inconsistent")
            for name in aggregates:
                if name == "maximum_run_length":
                    aggregates[name] = max(aggregates[name], item[name])
                else:
                    aggregates[name] += item[name]
            entries.append(item)

        totals = {
            name: _integer(summary, name)
            for name in (
                "eligible_draws",
                "opportunity_entries",
                "opportunity_overflow",
                "consecutive_runs",
                "multi_draw_runs",
                "multi_draw_draws",
                "maximum_run_length",
                "instance_switches",
                "same_instance_continuations",
                "parameter_switches",
                "same_parameter_continuations",
                "potential_reduction",
            )
        }
        totals["potential_reduction_percent"] = _number(
            summary, "potential_reduction_percent"
        )
        continuation_count = (
            totals["multi_draw_draws"] - totals["multi_draw_runs"]
        )
        if (
            totals["eligible_draws"] != eligible_draws
            or totals["opportunity_overflow"] != 0
            or totals["opportunity_entries"] != len(entries)
            or aggregates["draws"] != eligible_draws
            or any(
                totals[name] != aggregates[name]
                for name in aggregates
                if name != "draws"
            )
            or totals["instance_switches"]
            + totals["same_instance_continuations"]
            != continuation_count
            or totals["parameter_switches"]
            + totals["same_parameter_continuations"]
            != continuation_count
            or totals["potential_reduction"]
            != eligible_draws - totals["consecutive_runs"]
        ):
            raise ValueError(
                f"semantic-batch equivalence accounting failed: {equivalence}"
            )
        expected_percent = (
            100.0 * totals["potential_reduction"] / eligible_draws
            if eligible_draws
            else 0.0
        )
        if (
            abs(
                totals["potential_reduction_percent"] - expected_percent
            )
            > 0.001
        ):
            raise ValueError(
                f"semantic-batch equivalence percentage drifted: {equivalence}"
            )
        entries.sort(
            key=lambda item: (
                -item["multi_draw_draws"],
                -item["draws"],
                item["opportunity_key"],
            )
        )
        result[equivalence] = {"groups": entries, "totals": totals}
    return result


def _build_state_caches(
    selected: list[dict], eligible_draws: int
) -> dict[str, dict]:
    result = {}
    for cache_level in EXPECTED_STATE_CACHE_LEVELS:
        profiles = {}
        for cache_profile, expected_capacity in (
            EXPECTED_STATE_CACHE_PROFILES.items()
        ):
            summaries = [
                event
                for event in selected
                if event.get("event") == STATE_CACHE_SUMMARY
                and event.get("cache_level") == cache_level
                and event.get("cache_profile") == cache_profile
            ]
            if len(summaries) != 1:
                raise ValueError(
                    "semantic state cache needs one summary: "
                    f"{cache_level}/{cache_profile}"
                )
            summary = summaries[0]
            if (
                summary.get("status") != "complete"
                or summary.get("accounting_complete") != "true"
                or summary.get("policy") != "set_associative_lru"
                or summary.get("lifetime") != "census_session"
                or summary.get("native_state_objects") != "false"
                or summary.get("native_bindings") != "false"
                or summary.get("native_draw") != "false"
                or summary.get("reordering") != "false"
                or summary.get("xenos_authority") != "true"
                or summary.get("suppression_allowed") != "false"
            ):
                raise ValueError(
                    "semantic state cache is incomplete or unsafe: "
                    f"{cache_level}/{cache_profile}"
                )
            totals = {
                name: _integer(summary, name)
                for name in (
                    "eligible_draws",
                    "lookups",
                    "hits",
                    "misses",
                    "evictions",
                    "full_bucket_misses",
                    "resident_entries",
                    "maximum_resident_entries",
                    "consecutive_hits",
                    "nonconsecutive_same_frame_hits",
                    "cross_frame_hits",
                    "object_constructions",
                    "object_constructions_avoided",
                    "required_bindings",
                    "binding_elisions",
                    "bucket_count",
                    "ways",
                    "capacity",
                )
            }
            totals["hit_percent"] = _number(summary, "hit_percent")
            totals["binding_elision_percent"] = _number(
                summary, "binding_elision_percent"
            )
            expected_hit_percent = (
                100.0 * totals["hits"] / totals["lookups"]
                if totals["lookups"]
                else 0.0
            )
            expected_elision_percent = (
                100.0 * totals["binding_elisions"] / totals["lookups"]
                if totals["lookups"]
                else 0.0
            )
            if (
                totals["eligible_draws"] != eligible_draws
                or totals["lookups"] != eligible_draws
                or totals["hits"] + totals["misses"]
                != totals["lookups"]
                or totals["consecutive_hits"]
                + totals["nonconsecutive_same_frame_hits"]
                + totals["cross_frame_hits"]
                != totals["hits"]
                or totals["object_constructions"] != totals["misses"]
                or totals["object_constructions_avoided"]
                != totals["hits"]
                or totals["required_bindings"]
                + totals["binding_elisions"]
                != totals["lookups"]
                or totals["binding_elisions"]
                != totals["consecutive_hits"]
                or totals["full_bucket_misses"] != totals["evictions"]
                or totals["evictions"] > totals["misses"]
                or totals["resident_entries"] > totals["capacity"]
                or totals["maximum_resident_entries"]
                > totals["capacity"]
                or totals["capacity"] != expected_capacity
                or totals["capacity"]
                != totals["bucket_count"] * totals["ways"]
                or totals["bucket_count"] <= 0
                or totals["ways"] <= 0
            ):
                raise ValueError(
                    "semantic state cache accounting failed: "
                    f"{cache_level}/{cache_profile}"
                )
            if (
                abs(totals["hit_percent"] - expected_hit_percent) > 0.001
                or abs(
                    totals["binding_elision_percent"]
                    - expected_elision_percent
                )
                > 0.001
            ):
                raise ValueError(
                    "semantic state cache percentage drifted: "
                    f"{cache_level}/{cache_profile}"
                )
            profiles[cache_profile] = totals
        zero_eviction_profile = next(
            (
                profile
                for profile in EXPECTED_STATE_CACHE_PROFILES
                if profiles[profile]["evictions"] == 0
            ),
            None,
        )
        result[cache_level] = {
            "profiles": profiles,
            "minimum_zero_eviction_profile": zero_eviction_profile,
        }
    return result


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    contract = _validate_static(static)
    session = _select_session(events, requested)
    selected = [event for event in events if event.get("session") == session]
    configs = [event for event in selected if event.get("event") == TITLE_CONFIG]
    title_summaries = [
        event for event in selected if event.get("event") == TITLE_SUMMARY
    ]
    summaries = [event for event in selected if event.get("event") == BATCH_SUMMARY]
    if len(configs) != 1 or len(title_summaries) != 1 or len(summaries) != 1:
        raise ValueError(
            "semantic-batch session needs one config, title summary, and batch summary"
        )
    config = configs[0]
    title_summary = title_summaries[0]
    summary = summaries[0]
    if (
        config.get("status") != "armed"
        or config.get("semantic_batch_planner")
        != "exact_consecutive_opaque_prepared_draw_order"
        or config.get("semantic_batch_execution")
        != "disabled_measurement_only"
        or config.get("semantic_batch_world_family_partition")
        != "none_or_exact_track_or_exact_static_or_both"
        or config.get("semantic_batch_equivalence_ladder")
        != "mesh_material,material,pipeline"
        or config.get("semantic_batch_pipeline_identity")
        != "resource_free_layout_and_prepared_state"
        or config.get("semantic_batch_instance_parameters")
        != "shader_constants_and_semantic_instance"
        or _integer(
            config, "semantic_batch_maximum_parameter_payload_bytes"
        )
        <= 0
        or config.get("semantic_state_cache_levels")
        != "material,pipeline"
        or config.get("semantic_state_cache_profiles")
        != "compact:64,balanced:256,headroom:1024"
        or _integer(config, "semantic_state_cache_ways") <= 0
        or _integer(config, "semantic_state_cache_maximum_capacity")
        != 1024
        or config.get("semantic_state_cache_policy")
        != "set_associative_lru"
        or config.get("semantic_state_cache_lifetime") != "census_session"
        or config.get("semantic_state_cache_execution")
        != "shadow_measurement_only"
        or config.get("xenos_authority") != "true"
        or config.get("suppression_allowed") != "false"
    ):
        raise ValueError("semantic-batch runtime configuration drifted")
    if (
        summary.get("status") != "complete"
        or summary.get("ordering") != EXPECTED_ORDERING
        or summary.get("reordering") != "false"
        or summary.get("native_batch_execution") != "false"
        or summary.get("native_upload") != "false"
        or summary.get("native_draw") != "false"
        or summary.get("xenos_authority") != "true"
        or summary.get("suppression_allowed") != "false"
        or summary.get("accounting_complete") != "true"
    ):
        raise ValueError("semantic-batch summary is incomplete or unsafe")

    entries = []
    seen_keys = set()
    entry_draws = 0
    eligible_draws = 0
    rejected_draws = 0
    consecutive_runs = 0
    multi_draw_runs = 0
    multi_draw_draws = 0
    instance_switches = 0
    same_instance_continuations = 0
    rejections = {name: 0 for name in REJECTION_FIELDS}
    for event in selected:
        if event.get("event") != BATCH_ENTRY:
            continue
        opportunity_key = _hex(event, "opportunity_key", 16)
        if opportunity_key in seen_keys or int(opportunity_key, 16) == 0:
            raise ValueError("duplicate or zero semantic-batch opportunity key")
        seen_keys.add(opportunity_key)
        eligible = _boolean(event, "eligible")
        rejection = str(event.get("rejection", ""))
        classification = str(event.get("classification", ""))
        if eligible:
            if (
                rejection != "none"
                or classification != "conservative_consecutive_batch_candidate"
            ):
                raise ValueError("eligible semantic-batch entry is inconsistent")
        elif (
            rejection not in REJECTION_FIELDS
            or classification != "xenos_replay_rejected"
        ):
            raise ValueError("rejected semantic-batch entry is inconsistent")
        if (
            event.get("native_batch") != "false"
            or event.get("xenos_draw") != "preserved"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("semantic-batch entry crossed the safety boundary")
        item = {
            "opportunity_key": opportunity_key,
            "template_key": _hex(event, "template_key", 16),
            "geometry_resource_hash": _hex(
                event, "geometry_resource_hash", 16
            ),
            "texture_resource_hash": _hex(event, "texture_resource_hash", 16),
            "primary_resource_key": _hex(event, "primary_resource_key", 8),
            "secondary_resource_present": _boolean(
                event, "secondary_resource_present"
            ),
            "secondary_resource_key": _hex(
                event, "secondary_resource_key", 8
            ),
            "world_family_mask": int(
                _hex(event, "world_family_mask", 8), 16
            ),
            "draws": _integer(event, "draws"),
            "frames": _integer(event, "frames"),
            "first_frame": _integer(event, "first_frame"),
            "last_frame": _integer(event, "last_frame"),
            "consecutive_runs": _integer(event, "consecutive_runs"),
            "multi_draw_runs": _integer(event, "multi_draw_runs"),
            "multi_draw_draws": _integer(event, "multi_draw_draws"),
            "maximum_run_length": _integer(event, "maximum_run_length"),
            "instance_switches": _integer(event, "instance_switches"),
            "same_instance_continuations": _integer(
                event, "same_instance_continuations"
            ),
            "eligible": eligible,
            "rejection": rejection,
            "classification": classification,
        }
        if (
            item["draws"] <= 0
            or item["frames"] <= 0
            or item["last_frame"] < item["first_frame"]
            or item["world_family_mask"] & ~0x3
            or event.get("world_family_partition")
            != "none_or_exact_track_or_exact_static_or_both"
            or any(
                item[key] < 0
                for key in (
                    "consecutive_runs",
                    "multi_draw_runs",
                    "multi_draw_draws",
                    "maximum_run_length",
                    "instance_switches",
                    "same_instance_continuations",
                )
            )
        ):
            raise ValueError("semantic-batch entry has invalid counters")
        if eligible:
            if (
                item["consecutive_runs"] <= 0
                or item["maximum_run_length"] <= 0
                or item["multi_draw_draws"] > item["draws"]
            ):
                raise ValueError("eligible semantic-batch run accounting failed")
            eligible_draws += item["draws"]
        else:
            if any(
                item[key]
                for key in (
                    "consecutive_runs",
                    "multi_draw_runs",
                    "multi_draw_draws",
                    "maximum_run_length",
                    "instance_switches",
                    "same_instance_continuations",
                )
            ):
                raise ValueError("rejected semantic-batch entry owns a run")
            rejected_draws += item["draws"]
            rejections[rejection] += item["draws"]
        entry_draws += item["draws"]
        consecutive_runs += item["consecutive_runs"]
        multi_draw_runs += item["multi_draw_runs"]
        multi_draw_draws += item["multi_draw_draws"]
        instance_switches += item["instance_switches"]
        same_instance_continuations += item["same_instance_continuations"]
        entries.append(item)

    totals = {
        key: _integer(summary, key)
        for key in (
            "observations",
            "eligible_draws",
            "rejected_draws",
            "opportunity_entries",
            "opportunity_overflow",
            "consecutive_runs",
            "multi_draw_runs",
            "multi_draw_draws",
            "maximum_run_length",
            "instance_switches",
            "same_instance_continuations",
            "frames",
            "maximum_draws_per_frame",
            "template_transitions",
            "geometry_transitions",
            "texture_transitions",
            "title_resource_transitions",
            "parameter_payload_bytes",
            "maximum_parameter_payload_bytes",
            "parameter_payload_limit_bytes",
            "projected_commands",
            "potential_command_reduction",
            "track_world_entries",
            "track_world_draws",
            "track_world_multi_draw_runs",
            "static_world_entries",
            "static_world_draws",
            "static_world_multi_draw_runs",
        )
    }
    totals["potential_command_reduction_percent"] = _number(
        summary, "potential_command_reduction_percent"
    )
    reported_rejections = {
        name: _integer(summary, field)
        for name, field in REJECTION_FIELDS.items()
    }
    if (
        totals["observations"] <= 0
        or totals["opportunity_overflow"] != 0
        or totals["opportunity_entries"] != len(entries)
        or totals["observations"] != entry_draws
        or totals["eligible_draws"] != eligible_draws
        or totals["rejected_draws"] != rejected_draws
        or totals["eligible_draws"] + totals["rejected_draws"]
        != totals["observations"]
        or totals["consecutive_runs"] != consecutive_runs
        or totals["multi_draw_runs"] != multi_draw_runs
        or totals["multi_draw_draws"] != multi_draw_draws
        or totals["instance_switches"] != instance_switches
        or totals["same_instance_continuations"]
        != same_instance_continuations
        or totals["projected_commands"]
        != totals["consecutive_runs"] + totals["rejected_draws"]
        or totals["potential_command_reduction"]
        != totals["eligible_draws"] - totals["consecutive_runs"]
        or reported_rejections != rejections
        or sum(reported_rejections.values()) != totals["rejected_draws"]
        or totals["observations"]
        != _integer(title_summary, "semantic_contract_calls")
        or totals["observations"]
        != _integer(title_summary, "semantic_draw_prepared_matches")
        or _integer(title_summary, "semantic_draw_unprepared_matches") != 0
        or totals["parameter_payload_bytes"] <= 0
        or totals["maximum_parameter_payload_bytes"] <= 0
        or totals["maximum_parameter_payload_bytes"]
        > totals["parameter_payload_limit_bytes"]
        or totals["parameter_payload_bytes"]
        > totals["eligible_draws"] * totals["parameter_payload_limit_bytes"]
        or totals["parameter_payload_limit_bytes"]
        != _integer(
            config, "semantic_batch_maximum_parameter_payload_bytes"
        )
        or summary.get("world_family_partition")
        != "none_or_exact_track_or_exact_static_or_both"
    ):
        raise ValueError("semantic-batch aggregate accounting failed")
    track_world_groups = [
        group for group in entries if group["world_family_mask"] & 0x1
    ]
    static_world_groups = [
        group for group in entries if group["world_family_mask"] & 0x2
    ]
    if (
        totals["track_world_entries"] != len(track_world_groups)
        or totals["track_world_draws"]
        != sum(group["draws"] for group in track_world_groups)
        or totals["track_world_multi_draw_runs"]
        != sum(group["multi_draw_runs"] for group in track_world_groups)
        or totals["static_world_entries"] != len(static_world_groups)
        or totals["static_world_draws"]
        != sum(group["draws"] for group in static_world_groups)
        or totals["static_world_multi_draw_runs"]
        != sum(group["multi_draw_runs"] for group in static_world_groups)
    ):
        raise ValueError("semantic world-family partition accounting failed")
    expected_percent = (
        100.0 * totals["potential_command_reduction"] / totals["observations"]
    )
    if abs(totals["potential_command_reduction_percent"] - expected_percent) > 0.001:
        raise ValueError("semantic-batch reduction percentage drifted")

    equivalence_levels = _build_equivalence_levels(
        selected, totals["eligible_draws"]
    )
    state_caches = _build_state_caches(
        selected, totals["eligible_draws"]
    )

    entries.sort(
        key=lambda item: (
            not item["eligible"],
            -item["multi_draw_draws"],
            -item["draws"],
            item["opportunity_key"],
        )
    )
    conservative_batch_plan_proved = (
        totals["eligible_draws"] > 0
        and totals["multi_draw_runs"] > 0
        and totals["potential_command_reduction"] > 0
    )
    mesh_material = equivalence_levels["mesh_material_instance"]["totals"]
    instancing_parameter_path_required = (
        mesh_material["multi_draw_runs"] > 0
        and mesh_material["instance_switches"] > 0
        and mesh_material["parameter_switches"] > 0
    )
    mesh_material_instancing_opportunity_proved = (
        mesh_material["multi_draw_runs"] > 0
        and mesh_material["potential_reduction"] > 0
        and mesh_material["instance_switches"] > 0
    )
    return {
        "schema": SCHEMA,
        "session": session,
        "scene": str(config.get("scene", "unmarked")),
        "status": "complete",
        "groups": entries,
        "totals": totals,
        "rejections": reported_rejections,
        "equivalence_levels": equivalence_levels,
        "state_caches": state_caches,
        "conservative_batch_plan_proved": conservative_batch_plan_proved,
        "track_world_batch_opportunity_proved": any(
            group["eligible"] and group["multi_draw_runs"] > 0
            for group in track_world_groups
        ),
        "static_world_batch_opportunity_proved": any(
            group["eligible"] and group["multi_draw_runs"] > 0
            for group in static_world_groups
        ),
        "mesh_material_instancing_opportunity_proved": (
            mesh_material_instancing_opportunity_proved
        ),
        "instancing_parameter_path_required": (
            instancing_parameter_path_required
        ),
        "state_object_cache_reuse_proved": all(
            cache["profiles"]["headroom"]["hits"] > 0
            for cache in state_caches.values()
        ),
        "state_binding_elision_proved": any(
            cache["profiles"]["headroom"]["binding_elisions"] > 0
            for cache in state_caches.values()
        ),
        "execution_admitted": False,
        "contract": contract,
        "safety": {
            "exact_consecutive_order": True,
            "reordering": False,
            "guest_state_changed": False,
            "native_upload": False,
            "native_draw": False,
            "native_batch_execution": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        events = read_events(args.logs)
        static = json.loads(args.static.read_text(encoding="utf-8"))
        document = build(events, static, args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"native renderer semantic batch summary failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
