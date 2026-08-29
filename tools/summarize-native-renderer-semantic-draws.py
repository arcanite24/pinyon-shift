"""Validate semantic submissions and probe their direct title-packet overlap."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-semantic-draw-catalog.v4"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
SEMANTIC_DRAW_PREFIX = "native_renderer.discovery.semantic_draw_"
SEMANTIC_SUBMISSION_PREFIX = "native_renderer.discovery.semantic_submission_"
SEMANTIC_INSTANCE_PREFIX = "native_renderer.discovery.semantic_instance_"
TITLE_PREFIX = "native_renderer.discovery.title_provenance_"
EXPECTED_CLASS = "proceduralGeometry::CProceduralModels"
EXPECTED_CORRELATION = "exact_render_item_scope_to_emitted_and_backend_pm4_header"
EXPECTED_DIRECT_ASSOCIATION = "exact_render_item_scope_and_physical_pm4_header"


def read_events(paths: list[pathlib.Path]) -> list[dict]:
    events = []
    prefixes = (
        SEMANTIC_DRAW_PREFIX,
        SEMANTIC_SUBMISSION_PREFIX,
        SEMANTIC_INSTANCE_PREFIX,
        TITLE_PREFIX,
    )
    for path in paths:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if str(event.get("event", "")).startswith(prefixes):
                events.append(event)
    return events


def _integer(mapping: dict, key: str) -> int:
    try:
        return int(mapping.get(key, ""))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid integer field: {key}") from error


def _hex(mapping: dict, key: str, width: int) -> str:
    value = str(mapping.get(key, "")).upper()
    if len(value) != width:
        raise ValueError(f"invalid hexadecimal field: {key}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid hexadecimal field: {key}") from error
    return value


def _boolean(mapping: dict, key: str) -> bool:
    value = str(mapping.get(key, "")).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"invalid boolean field: {key}")
    return value == "true"


def _select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"semantic-draw session not found: {requested}")
        return requested
    sessions = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == f"{SEMANTIC_DRAW_PREFIX}config"
        and event.get("status") == "armed"
    ]
    if not sessions or not sessions[-1]:
        raise ValueError("no armed semantic-draw session found")
    return sessions[-1]


def _validate_static(static: dict) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    lifecycle = static.get("procedural_model_receiver_lifecycle", {})
    contract = lifecycle.get("semantic_draw_association", {})
    expected = {
        "render_item_entry_hook_address": "8241741C",
        "render_item_exit_hook_address": "82417B80",
        "geometry_submission_hook_address": "82417B60",
        "title_draw_packet_hook_addresses": ["82410328", "829F7CB0"],
        "semantic_draw_packet_hook_addresses": ["82416260", "824162F4"],
        "title_indirect_packet_hook_addresses": [
            "824095B4",
            "82416EFC",
            "8246FC1C",
            "8263BD64",
            "829E8E88",
            "829EC49C",
        ],
        "graphics_submission_vtable_offset": 160,
        "graphics_submission_target_runtime_join_required": True,
        "graphics_submission_wrapper_address": "82415CE0",
        "graphics_submission_emitter_address": "82415F68",
        "semantic_draw_packet_opcode": "PM4_DRAW_INDX",
        "semantic_draw_packet_opcode_value": 0x22,
        "direct_title_packet_overlap_probe": True,
        "indirect_packet_constructor_overlap_probe": True,
        "semantic_pm4_packet_construction_proved": True,
        "semantic_pm4_backend_join_required": True,
        "semantic_prepared_contract_runtime_join_required": True,
        "semantic_catalog_classification": (
            "immutable_template_and_dynamic_resource_instance"
        ),
        "physical_pm4_packet_correlation_proved": False,
        "prepared_draw_lineage_proved": False,
        "classification": "procedural_submission_pm4_packet_boundary",
        "native_rendering_enabled": False,
        "suppression_eligible": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("unsupported semantic-draw static contract")
    if not all(
        contract.get(key)
        for key in (
            "render_item_invocation_scope_proved",
            "submission_before_draw_dispatch_proved",
        )
    ):
        raise ValueError("semantic-draw correlation is not statically proved")
    provenance = static.get("draw_packet_provenance", {})
    packet_hooks = {
        str(item.get("packet_hook_address", "")).upper()
        for item in provenance.get("packet_sites", [])
    }
    if packet_hooks != {"82410328", "829F7CB0"}:
        raise ValueError("title draw packet provenance contract drifted")
    return contract


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    contract = _validate_static(static)
    session = _select_session(events, requested)
    selected = [event for event in events if event.get("session") == session]

    configs = [
        event
        for event in selected
        if event.get("event") == f"{SEMANTIC_DRAW_PREFIX}config"
        and event.get("status") == "armed"
    ]
    title_summaries = [
        event for event in selected if event.get("event") == f"{TITLE_PREFIX}summary"
    ]
    submission_summaries = [
        event
        for event in selected
        if event.get("event") == f"{SEMANTIC_SUBMISSION_PREFIX}summary"
    ]
    instance_summaries = [
        event
        for event in selected
        if event.get("event") == f"{SEMANTIC_INSTANCE_PREFIX}summary"
    ]
    if (
        len(configs) != 1
        or len(title_summaries) != 1
        or len(submission_summaries) != 1
        or len(instance_summaries) != 1
    ):
        raise ValueError(
            "semantic-draw session needs one config and all three summaries"
        )
    config = configs[0]
    if (
        config.get("class") != EXPECTED_CLASS
        or config.get("render_item_entry_hook") != "8241741C"
        or config.get("render_item_exit_hook") != "82417B80"
        or config.get("geometry_submission_hook") != "82417B60"
        or config.get("title_packet_hooks") != "82410328,829F7CB0"
        or config.get("semantic_packet_hooks") != "82416260,824162F4"
        or config.get("graphics_submission_wrapper") != "82415CE0"
        or config.get("graphics_submission_emitter") != "82415F68"
        or config.get("semantic_packet_opcode") != "PM4_DRAW_INDX_0x22"
        or config.get("semantic_catalog")
        != "prepared_template_dynamic_resource_instance_and_batch_key"
        or _integer(config, "semantic_catalog_capacity") != 4096
        or config.get("title_indirect_packet_hooks")
        not in (
            None,
            "824095B4,82416EFC,8246FC1C,8263BD64,829E8E88,829EC49C",
        )
        or config.get("correlation") != EXPECTED_CORRELATION
        or config.get("classification")
        != "procedural_submission_pm4_packet_boundary"
    ):
        raise ValueError("semantic-draw runtime contract drifted")
    safety = {
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(str(config.get(key)).lower() != value for key, value in safety.items()):
        raise ValueError("semantic-draw config violates the safety boundary")

    instances_by_identity: dict[tuple[str, int, int], dict] = {}
    for event in selected:
        if event.get("event") != f"{SEMANTIC_INSTANCE_PREFIX}entry":
            continue
        identity = (
            _hex(event, "receiver_address", 8),
            _integer(event, "receiver_generation"),
            _integer(event, "record_index"),
        )
        instance = {
            "semantic_instance_key": _hex(event, "key", 16),
            "descriptor_address": _hex(event, "descriptor_address", 8),
            "runtime_address": _hex(event, "runtime_address", 8),
            "descriptor_hash": _hex(event, "descriptor_hash", 16),
            "runtime_hash": _hex(event, "runtime_hash", 16),
            "transform_hash": _hex(event, "transform_hash", 16),
            "descriptor_variations": _integer(event, "descriptor_variations"),
            "runtime_variations": _integer(event, "runtime_variations"),
            "transform_variations": _integer(event, "transform_variations"),
        }
        if (
            identity in instances_by_identity
            or identity[1] <= 0
            or min(
                instance["descriptor_variations"],
                instance["runtime_variations"],
                instance["transform_variations"],
            )
            < 0
            or str(event.get("fallback", "")).lower() != "xenos_replay"
            or str(event.get("native_draw", "")).lower() != "false"
            or str(event.get("suppression_allowed", "")).lower() != "false"
        ):
            raise ValueError("invalid or duplicate semantic instance entry")
        instances_by_identity[identity] = instance

    submissions: dict[str, dict] = {}
    submission_calls = 0
    for event in selected:
        if event.get("event") != f"{SEMANTIC_SUBMISSION_PREFIX}entry":
            continue
        key = _hex(event, "key", 16)
        calls = _integer(event, "calls")
        identity = {
            "receiver_address": _hex(event, "receiver_address", 8),
            "receiver_generation": _integer(event, "receiver_generation"),
            "record_index": _integer(event, "record_index"),
            "descriptor_kind": _integer(event, "descriptor_kind"),
            "helper_state": _integer(event, "helper_state"),
            "graphics_submission_method": _hex(
                event, "graphics_submission_method", 8
            ),
            "primary_resource_key": _hex(event, "primary_resource_key", 8),
            "secondary_resource_present": str(
                event.get("secondary_resource_present", "")
            ).lower()
            == "true",
            "secondary_resource_key": _hex(event, "secondary_resource_key", 8),
            "runtime_submission_object": _hex(
                event, "runtime_submission_object", 8
            ),
            "count_bytes": _integer(event, "count_bytes"),
            "source_address": _hex(event, "source_address", 8),
        }
        if key in submissions or calls <= 0 or identity["receiver_generation"] <= 0:
            raise ValueError("invalid or duplicate semantic submission entry")
        instance_identity = (
            identity["receiver_address"],
            identity["receiver_generation"],
            identity["record_index"],
        )
        instance = instances_by_identity.get(instance_identity)
        if instance is None:
            raise ValueError("semantic submission has no immutable instance")
        submissions[key] = {"calls": calls, **identity, "instance": instance}
        submission_calls += calls

    associations = []
    associated_calls_by_key: collections.Counter[str] = collections.Counter()
    prepared_signatures_by_key: dict[str, set[str]] = collections.defaultdict(set)
    templates: dict[str, dict] = {}
    batch_groups: dict[tuple[str, str, str, str, str], dict] = {}
    prepared_calls = 0
    unprepared_calls = 0
    for event in selected:
        if event.get("event") != f"{TITLE_PREFIX}entry":
            continue
        raw_key = str(event.get("semantic_submission_key", ""))
        if not raw_key:
            continue
        key = _hex(event, "semantic_submission_key", 16)
        submission = submissions.get(key)
        if submission is None:
            raise ValueError("semantic draw references an unknown submission key")
        calls = _integer(event, "calls")
        outcome = str(event.get("outcome", ""))
        signature = str(event.get("prepared_signature", "")).upper()
        backend_signature = _hex(event, "backend_signature", 16)
        receiver_address = _hex(event, "semantic_receiver_address", 8)
        receiver_generation = _integer(event, "semantic_receiver_generation")
        record_index = _integer(event, "semantic_record_index")
        descriptor_address = _hex(event, "semantic_descriptor_address", 8)
        runtime_address = _hex(event, "semantic_runtime_address", 8)
        origin_wrapper = str(event.get("origin_wrapper", ""))
        origin_wrapper_address = _hex(event, "origin_wrapper_address", 8)
        origin_caller = _hex(event, "origin_caller", 8)
        if (
            calls <= 0
            or event.get("semantic_draw_association") != EXPECTED_DIRECT_ASSOCIATION
            or event.get("semantic_identity") != "procedural_model_submission"
            or str(event.get("xenos_draw", "")).lower() != "preserved"
            or str(event.get("suppression_eligible", "")).lower() != "false"
            or receiver_address != submission["receiver_address"]
            or receiver_generation != submission["receiver_generation"]
            or record_index != submission["record_index"]
            or origin_wrapper != "procedural_model_draw_indexed"
            or origin_wrapper_address != "82415F68"
            or origin_caller not in {"82416260", "824162F4"}
        ):
            raise ValueError("semantic draw identity or safety evidence is inconsistent")
        catalog = None
        if outcome == "prepared":
            if len(signature) != 16 or signature != backend_signature:
                raise ValueError("semantic prepared draw signature is invalid")
            int(signature, 16)
            template_key = _hex(event, "semantic_template_key", 16)
            if int(template_key, 16) == 0:
                raise ValueError("semantic template key is zero")
            catalog = {
                "prepared_pipeline_hash": _hex(
                    event, "semantic_prepared_pipeline_hash", 16
                ),
                "geometry_layout_hash": _hex(
                    event, "semantic_geometry_layout_hash", 16
                ),
                "texture_layout_hash": _hex(
                    event, "semantic_texture_layout_hash", 16
                ),
                "render_state_hash": _hex(
                    event, "semantic_render_state_hash", 16
                ),
                "geometry_resource_hash": _hex(
                    event, "semantic_geometry_resource_hash", 16
                ),
                "texture_resource_hash": _hex(
                    event, "semantic_texture_resource_hash", 16
                ),
                "vertex_shader": _hex(event, "semantic_vertex_shader", 16),
                "pixel_shader": _hex(event, "semantic_pixel_shader", 16),
                "vertex_specialization": _hex(
                    event, "semantic_vertex_specialization", 16
                ),
                "pixel_specialization": _hex(
                    event, "semantic_pixel_specialization", 16
                ),
                "primitive_type": _integer(event, "semantic_primitive_type"),
                "source_select": _integer(event, "semantic_source_select"),
                "indexed": _boolean(event, "semantic_indexed"),
                "minimum_index_count": _integer(
                    event, "semantic_minimum_index_count"
                ),
                "maximum_index_count": _integer(
                    event, "semantic_maximum_index_count"
                ),
                "index_buffer_address": _hex(
                    event, "semantic_index_buffer_address", 8
                ),
                "index_buffer_length": _integer(
                    event, "semantic_index_buffer_length"
                ),
                "index_format": _integer(event, "semantic_index_format"),
                "index_endianness": _integer(
                    event, "semantic_index_endianness"
                ),
                "vertex_binding_count": _integer(
                    event, "semantic_vertex_binding_count"
                ),
                "vertex_attribute_count": _integer(
                    event, "semantic_vertex_attribute_count"
                ),
                "first_vertex_address": _hex(
                    event, "semantic_first_vertex_address", 8
                ),
                "first_vertex_size": _integer(
                    event, "semantic_first_vertex_size"
                ),
                "first_vertex_stride_words": _integer(
                    event, "semantic_first_vertex_stride_words"
                ),
                "first_vertex_endianness": _integer(
                    event, "semantic_first_vertex_endianness"
                ),
                "texture_fetch_mask": _hex(
                    event, "semantic_texture_fetch_mask", 8
                ),
                "texture_layout_valid_mask": _hex(
                    event, "semantic_texture_layout_valid_mask", 8
                ),
                "texture_state_count": _integer(
                    event, "semantic_texture_state_count"
                ),
                "geometry_bounded": _boolean(
                    event, "semantic_geometry_bounded"
                ),
                "texture_layout_bounded": _boolean(
                    event, "semantic_texture_layout_bounded"
                ),
                "template_variations": _integer(
                    event, "semantic_template_variations"
                ),
                "resource_variations": _integer(
                    event, "semantic_resource_variations"
                ),
            }
            if (
                event.get("semantic_catalog_classification")
                != "immutable_template_and_dynamic_resource_instance"
                or catalog["minimum_index_count"] <= 0
                or catalog["maximum_index_count"]
                < catalog["minimum_index_count"]
                or catalog["vertex_binding_count"] <= 0
                or catalog["template_variations"] < 0
                or catalog["resource_variations"] < 0
            ):
                raise ValueError("semantic prepared contract is invalid")
            template_identity = {
                key: catalog[key]
                for key in (
                    "prepared_pipeline_hash",
                    "geometry_layout_hash",
                    "texture_layout_hash",
                    "render_state_hash",
                    "vertex_shader",
                    "pixel_shader",
                    "vertex_specialization",
                    "pixel_specialization",
                    "primitive_type",
                    "source_select",
                    "indexed",
                    "index_format",
                    "index_endianness",
                    "vertex_binding_count",
                    "vertex_attribute_count",
                    "first_vertex_stride_words",
                    "first_vertex_endianness",
                    "texture_fetch_mask",
                    "texture_layout_valid_mask",
                    "texture_state_count",
                )
            }
            template = templates.get(template_key)
            if template is None:
                template = {
                    "template_key": template_key,
                    **template_identity,
                    "calls": 0,
                    "submission_keys": set(),
                    "geometry_resource_hashes": set(),
                    "texture_resource_hashes": set(),
                    "geometry_bounded": True,
                    "texture_layout_bounded": True,
                    "template_variations": 0,
                    "resource_variations": 0,
                }
                templates[template_key] = template
            elif any(
                template[name] != value
                for name, value in template_identity.items()
            ):
                raise ValueError("semantic template identity changed across entries")
            template["calls"] += calls
            template["submission_keys"].add(key)
            template["geometry_resource_hashes"].add(
                catalog["geometry_resource_hash"]
            )
            template["texture_resource_hashes"].add(
                catalog["texture_resource_hash"]
            )
            template["geometry_bounded"] &= catalog["geometry_bounded"]
            template["texture_layout_bounded"] &= catalog[
                "texture_layout_bounded"
            ]
            template["template_variations"] += catalog["template_variations"]
            template["resource_variations"] += catalog["resource_variations"]
            batch_key = (
                template_key,
                catalog["geometry_resource_hash"],
                catalog["texture_resource_hash"],
                submission["primary_resource_key"],
                submission["secondary_resource_key"],
            )
            batch = batch_groups.setdefault(
                batch_key,
                {
                    "template_key": template_key,
                    "geometry_resource_hash": catalog[
                        "geometry_resource_hash"
                    ],
                    "texture_resource_hash": catalog[
                        "texture_resource_hash"
                    ],
                    "primary_resource_key": submission[
                        "primary_resource_key"
                    ],
                    "secondary_resource_key": submission[
                        "secondary_resource_key"
                    ],
                    "calls": 0,
                    "submission_keys": set(),
                    "batchable": True,
                },
            )
            batch["calls"] += calls
            batch["submission_keys"].add(key)
            batch["batchable"] &= (
                catalog["geometry_bounded"]
                and catalog["texture_layout_bounded"]
                and catalog["template_variations"] == 0
                and catalog["resource_variations"] == 0
            )
            prepared_signatures_by_key[key].add(signature)
            prepared_calls += calls
        elif outcome == "not_prepared":
            if signature:
                raise ValueError("semantic unprepared draw has a prepared signature")
            unprepared_calls += calls
        else:
            raise ValueError("semantic draw has an invalid backend outcome")
        associated_calls_by_key[key] += calls
        associations.append(
            {
                "semantic_submission_key": key,
                "calls": calls,
                "receiver_address": receiver_address,
                "receiver_generation": receiver_generation,
                "record_index": record_index,
                "descriptor_address": descriptor_address,
                "runtime_address": runtime_address,
                "origin_wrapper": origin_wrapper,
                "origin_wrapper_address": origin_wrapper_address,
                "origin_caller": origin_caller,
                "outcome": outcome,
                "backend_outcome": str(event.get("backend_outcome", "")),
                "backend_signature": backend_signature,
                "prepared_signature": signature or None,
                "catalog": catalog if outcome == "prepared" else None,
                "xenos_draw": "preserved",
                "suppression_eligible": False,
            }
        )

    submission_summary = submission_summaries[0]
    instance_summary = instance_summaries[0]
    title_summary = title_summaries[0]
    live_submissions = _integer(submission_summary, "live_observations")
    instance_totals = {
        key: _integer(instance_summary, key)
        for key in (
            "live_observations",
            "unknown_receivers",
            "invalid_layouts",
            "invalid_indices",
            "replay_fallbacks",
            "native_admissions",
            "entries",
            "overflow",
        )
    }
    pending = _integer(title_summary, "semantic_draw_pending_packets")
    semantic_prepared = _integer(title_summary, "semantic_draw_prepared_matches")
    semantic_unprepared = _integer(title_summary, "semantic_draw_unprepared_matches")
    associated_calls = sum(associated_calls_by_key.values())
    prepared_associations = [
        item for item in associations if item["outcome"] == "prepared"
    ]
    catalog_counters = {
        key: _integer(title_summary, key)
        for key in (
            "semantic_contract_entries",
            "semantic_contract_calls",
            "semantic_bounded_geometry_calls",
            "semantic_bounded_texture_calls",
            "semantic_stable_template_calls",
            "semantic_stable_resource_calls",
            "semantic_template_variations",
            "semantic_resource_variations",
        )
    }
    expected_catalog_counters = {
        "semantic_contract_entries": len(prepared_associations),
        "semantic_contract_calls": prepared_calls,
        "semantic_bounded_geometry_calls": sum(
            item["calls"]
            for item in prepared_associations
            if item["catalog"]["geometry_bounded"]
        ),
        "semantic_bounded_texture_calls": sum(
            item["calls"]
            for item in prepared_associations
            if item["catalog"]["texture_layout_bounded"]
        ),
        "semantic_stable_template_calls": sum(
            item["calls"]
            for item in prepared_associations
            if item["catalog"]["template_variations"] == 0
        ),
        "semantic_stable_resource_calls": sum(
            item["calls"]
            for item in prepared_associations
            if item["catalog"]["resource_variations"] == 0
        ),
        "semantic_template_variations": sum(
            item["catalog"]["template_variations"]
            for item in prepared_associations
        ),
        "semantic_resource_variations": sum(
            item["catalog"]["resource_variations"]
            for item in prepared_associations
        ),
    }
    fault_fields = (
        "semantic_render_item_stack_faults",
        "semantic_draw_scope_mismatches",
    )
    faults = {key: _integer(title_summary, key) for key in fault_fields}
    counters = {
        key: _integer(title_summary, key)
        for key in (
            "semantic_submission_live_observations",
            "semantic_render_item_entries",
            "semantic_render_item_exits",
            "semantic_render_item_valid_scopes",
            "semantic_render_item_scopes_without_submission",
            "semantic_draw_scope_joins",
            "semantic_draw_origins_captured",
            "semantic_draw_dispatches_with_direct_title_origin",
            "semantic_draw_dispatches_without_direct_title_origin",
            "semantic_draw_indirect_packet_origins_captured",
            "semantic_draw_dispatches_with_indirect_packet_origin",
            "semantic_draw_dispatches_without_indirect_packet_origin",
            "semantic_draw_packets_recorded",
            "semantic_draw_packet_matches",
        )
    }
    if (
        not submissions
        or not instances_by_identity
        or instance_totals["entries"] != len(instances_by_identity)
        or instance_totals["live_observations"]
        != instance_totals["replay_fallbacks"]
        or any(
            instance_totals[key]
            for key in (
                "unknown_receivers",
                "invalid_layouts",
                "invalid_indices",
                "native_admissions",
                "overflow",
            )
        )
        or submission_calls != live_submissions
        or counters["semantic_submission_live_observations"] != live_submissions
        or counters["semantic_draw_scope_joins"] != live_submissions
        or counters["semantic_draw_dispatches_with_direct_title_origin"]
        + counters["semantic_draw_dispatches_without_direct_title_origin"]
        != live_submissions
        or counters["semantic_draw_dispatches_with_indirect_packet_origin"]
        + counters["semantic_draw_dispatches_without_indirect_packet_origin"]
        != live_submissions
        or counters["semantic_draw_indirect_packet_origins_captured"]
        < counters["semantic_draw_dispatches_with_indirect_packet_origin"]
        or counters["semantic_draw_origins_captured"]
        < counters["semantic_draw_dispatches_with_direct_title_origin"]
        or counters["semantic_draw_packets_recorded"]
        != counters["semantic_draw_origins_captured"]
        or counters["semantic_draw_packet_matches"] != associated_calls
        or associated_calls != prepared_calls + unprepared_calls
        or prepared_calls != semantic_prepared
        or unprepared_calls != semantic_unprepared
        or catalog_counters != expected_catalog_counters
        or str(title_summary.get("semantic_catalog_accounting_complete")).lower()
        != "true"
        or counters["semantic_draw_packets_recorded"]
        != associated_calls + pending
        or counters["semantic_render_item_entries"]
        != counters["semantic_render_item_exits"]
        + _integer(title_summary, "semantic_render_items_open_at_shutdown")
        or counters["semantic_render_item_valid_scopes"] < live_submissions
        or any(faults.values())
        or str(
            title_summary.get("semantic_draw_overlap_probe_accounting_complete")
        ).lower()
        != "true"
        or (
            str(title_summary.get("semantic_draw_accounting_complete")).lower()
            == "true"
        )
        != (counters["semantic_draw_dispatches_without_direct_title_origin"] == 0)
    ):
        raise ValueError("semantic draw accounting is incomplete or inconsistent")
    associations.sort(
        key=lambda item: (
            -item["calls"],
            item["semantic_submission_key"],
            item["backend_signature"],
        )
    )
    submission_lineage = [
        {
            "semantic_submission_key": key,
            **submission,
            "associated_draw_calls": associated_calls_by_key[key],
            "direct_title_packet_calls": associated_calls_by_key[key],
            "prepared_signatures": sorted(prepared_signatures_by_key[key]),
        }
        for key, submission in submissions.items()
    ]
    submission_lineage.sort(
        key=lambda item: (-item["calls"], item["semantic_submission_key"])
    )
    physical_pm4_packet_correlation_proved = (
        counters["semantic_draw_dispatches_without_direct_title_origin"] == 0
        and counters["semantic_draw_packets_recorded"] > 0
        and counters["semantic_draw_packets_recorded"] == associated_calls + pending
    )
    prepared_draw_lineage_proved = (
        physical_pm4_packet_correlation_proved
        and prepared_calls > 0
        and unprepared_calls == 0
    )
    template_entries = []
    for template in templates.values():
        template_entries.append(
            {
                **{
                    key: value
                    for key, value in template.items()
                    if key
                    not in {
                        "submission_keys",
                        "geometry_resource_hashes",
                        "texture_resource_hashes",
                    }
                },
                "submission_keys": sorted(template["submission_keys"]),
                "geometry_resource_hashes": sorted(
                    template["geometry_resource_hashes"]
                ),
                "texture_resource_hashes": sorted(
                    template["texture_resource_hashes"]
                ),
            }
        )
    template_entries.sort(key=lambda item: (-item["calls"], item["template_key"]))
    batch_entries = [
        {
            **{key: value for key, value in batch.items() if key != "submission_keys"},
            "submission_keys": sorted(batch["submission_keys"]),
        }
        for batch in batch_groups.values()
    ]
    batch_entries.sort(
        key=lambda item: (
            not item["batchable"],
            -item["calls"],
            item["template_key"],
            item["geometry_resource_hash"],
            item["texture_resource_hash"],
        )
    )
    batchable_calls = sum(item["calls"] for item in batch_entries if item["batchable"])
    compact_semantic_catalog_proved = (
        prepared_draw_lineage_proved
        and catalog_counters["semantic_contract_calls"] == prepared_calls
        and catalog_counters["semantic_template_variations"] == 0
        and catalog_counters["semantic_resource_variations"] == 0
        and catalog_counters["semantic_bounded_geometry_calls"] == prepared_calls
        and catalog_counters["semantic_bounded_texture_calls"] == prepared_calls
    )
    return {
        "schema": SCHEMA,
        "session": session,
        "scene": str(config.get("scene", "unmarked")),
        "status": "complete",
        "associations": associations,
        "submissions": submission_lineage,
        "templates": template_entries,
        "batch_groups": batch_entries,
        "totals": {
            "semantic_submissions": live_submissions,
            "semantic_submission_keys": len(submissions),
            "semantic_instance_keys": len(instances_by_identity),
            "associated_draw_calls": associated_calls,
            "prepared_draw_calls": prepared_calls,
            "unprepared_draw_calls": unprepared_calls,
            "pending_draw_packets": pending,
            "unique_prepared_signatures": len(
                {
                    signature
                    for signatures in prepared_signatures_by_key.values()
                    for signature in signatures
                }
            ),
            "association_entries": len(associations),
            "semantic_template_count": len(template_entries),
            "semantic_batch_group_count": len(batch_entries),
            "semantic_batchable_calls": batchable_calls,
            "semantic_render_items_open_at_shutdown": _integer(
                title_summary, "semantic_render_items_open_at_shutdown"
            ),
            **counters,
            **catalog_counters,
            **faults,
        },
        "correlation": contract,
        "qualification": (
            "compact_semantic_template_instance_and_conservative_batch_catalog"
        ),
        "physical_pm4_packet_correlation_proved": (
            physical_pm4_packet_correlation_proved
        ),
        "prepared_draw_lineage_proved": prepared_draw_lineage_proved,
        "compact_semantic_catalog_proved": compact_semantic_catalog_proved,
        "native_batching_enabled": False,
        "safety": {
            "bounded_guest_read": True,
            "guest_state_changed": False,
            "native_upload": False,
            "native_draw": False,
            "native_batching": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        static = json.loads(args.static.read_text(encoding="utf-8"))
        document = build(read_events(args.logs), static, args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"native renderer semantic draw summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
