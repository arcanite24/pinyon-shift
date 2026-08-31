#!/usr/bin/env python3
"""Qualify SimpleModel renderer scopes joined to prepared PM4 draws."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-runtime-join.v8"
STATIC_SCHEMA = "pinyon-shift.native-renderer-static-world-ingress.v2"
LIFETIME_SCHEMA = "pinyon-shift.native-renderer-static-world-lifetime.v1"
RESOURCE_SCHEMA = "pinyon-shift.native-renderer-static-world-resource.v1"
STREAMING_SCHEMA = "pinyon-shift.native-renderer-static-world-streaming.v1"
GRAPH_SCHEMA = "pinyon-shift.native-renderer-static-world-graph.v1"
OWNER_SCHEMA = "pinyon-shift.native-renderer-static-world-owner.v1"
ASSET_METADATA_SCHEMA = (
    "pinyon-shift.native-renderer-static-world-asset-metadata.v1"
)
MESH_SEMANTICS_SCHEMA = (
    "pinyon-shift.native-renderer-static-world-mesh-semantics.v1"
)
CONFIG = "native_renderer.discovery.static_world_runtime_join_config"
SUMMARY = "native_renderer.discovery.static_world_runtime_join_summary"
CHECKPOINT = "native_renderer.discovery.static_world_runtime_join_checkpoint"


def integer(mapping, key):
    try:
        value = int(mapping[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if value < 0:
        raise ValueError(f"negative {key}")
    return value


def exact_event(events, name):
    matches = [event for event in events if event.get("event") == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} event")
    return matches[0]


def read_events(paths):
    events = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def select_session(events, requested):
    sessions = {
        event.get("session") for event in events if event.get("event") == CONFIG
    }
    sessions.discard(None)
    if requested:
        if requested not in sessions:
            raise ValueError("requested session has no static-world join config")
        return requested
    if len(sessions) != 1:
        raise ValueError("static-world join input contains multiple sessions")
    return next(iter(sessions))


def select_runtime_evidence(events, allow_checkpoint):
    summaries = [event for event in events if event.get("event") == SUMMARY]
    if len(summaries) > 1:
        raise ValueError(f"expected at most one {SUMMARY} event")
    if summaries:
        return summaries[0], True
    if not allow_checkpoint:
        raise ValueError(f"expected exactly one {SUMMARY} event")
    checkpoints = [
        event for event in events if event.get("event") == CHECKPOINT
    ]
    if not checkpoints:
        raise ValueError("no static-world runtime summary or checkpoint")
    return max(
        checkpoints, key=lambda event: integer(event, "frame_sequence")
    ), False


def require_safety(event):
    expected = {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("static-world join violates its safety boundary")


def validate_static_ingress(document):
    if (
        document.get("schema") != STATIC_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "title_simple_model_static_world_ingress_proved"
    ):
        raise ValueError("static-world ingress proof drifted")
    try:
        model_renderer = document["classes"]["simple_model_renderer"]
        primary = next(
            surface
            for surface in model_renderer["surfaces"]
            if surface.get("label") == "primary"
        )
    except (KeyError, StopIteration, TypeError) as error:
        raise ValueError("static-world renderer surface is missing") from error
    slot_targets = primary.get("slot_targets")
    if (
        model_renderer.get("decorated_name") != ".?AVCSimpleModelRenderer@@"
        or primary.get("vtable_address") != "82001B64"
        or primary.get("vtable_slot_count") != 17
        or not isinstance(slot_targets, list)
        or len(slot_targets) != 17
        or slot_targets[12] != "82C4CCC8"
    ):
        raise ValueError("static-world renderer dispatch proof drifted")


def validate_static_lifetime(document):
    if (
        document.get("schema") != LIFETIME_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "exact_simple_model_renderer_lifetime_and_graph_owner"
    ):
        raise ValueError("static-world lifetime proof drifted")
    try:
        renderer = document["renderer"]
        graph = document["graph_ownership"]
        claims = document["claims"]
    except (KeyError, TypeError) as error:
        raise ValueError("static-world lifetime proof is incomplete") from error
    expected_renderer = {
        "class": "CSimpleModelRenderer",
        "vtable": "82001B64",
        "object_bytes": 368,
        "constructor": "82C4DF78",
        "constructor_publish_hook": "82C4E094",
        "deleting_destructor_slot": 16,
        "deleting_destructor": "82C4E420",
        "destructor_entry_hook": "82C4E1F8",
        "destructor_exit_hook": "82C4E264",
    }
    expected_graph = {
        "field_offset": 72,
        "bind_slot": 1,
        "bind_method": "82C4CC50",
        "bind_completion_hook": "82C4CCB0",
        "release_slot": 15,
        "release_method": "82C4C6A8",
        "destructor_cleanup": "82C4E0A0",
        "draw_slot": 12,
        "draw_dispatch": "82C4CCC8",
    }
    if any(
        renderer.get(key) != value
        for key, value in expected_renderer.items()
    ):
        raise ValueError("static-world renderer lifetime proof drifted")
    if any(graph.get(key) != value for key, value in expected_graph.items()):
        raise ValueError("static-world graph ownership proof drifted")
    if (
        claims.get("renderer_generation_boundary_proved") is not True
        or claims.get("renderer_to_owned_graph_field_proved") is not True
        or claims.get("concrete_building_or_prop_identity_proved") is not False
    ):
        raise ValueError("static-world lifetime claims drifted")


def validate_static_resource(document):
    if (
        document.get("schema") != RESOURCE_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "exact_simple_model_resource_factory_and_lifetime"
    ):
        raise ValueError("static-world resource proof drifted")
    try:
        resource = document["resource"]
        binding = document["binding"]
        claims = document["claims"]
    except (KeyError, TypeError) as error:
        raise ValueError("static-world resource proof is incomplete") from error
    expected_resource = {
        "class": "CSimpleModelResource",
        "vtable": "82229294",
        "object_bytes": 320,
        "factory": "82C47F10",
        "constructor": "82C47DA0",
        "publish_hook": "82C47FBC",
        "registration_hook": "82C4802C",
        "deleting_destructor_slot": 0,
        "deleting_destructor": "82C47EC0",
        "destructor": "82C47DF8",
        "destructor_entry_hook": "82C47DF8",
        "destructor_exit_hook": "82C47E44",
    }
    expected_binding = {
        "renderer_bind": "82C48038",
        "renderer_graph_field_offset": 72,
        "factory_output_argument": "r5",
        "reference_assignment": "824E81A8",
        "existing_resource_path_join": "82C4802C",
        "new_resource_path_join": "82C4802C",
    }
    if any(resource.get(key) != value for key, value in expected_resource.items()):
        raise ValueError("static-world resource lifetime proof drifted")
    if any(binding.get(key) != value for key, value in expected_binding.items()):
        raise ValueError("static-world resource binding proof drifted")
    if (
        claims.get("bound_graph_dynamic_type_proved") is not True
        or claims.get("resource_generation_boundary_proved") is not True
        or claims.get("factory_registration_boundary_proved") is not True
        or claims.get("concrete_building_or_prop_identity_proved") is not False
        or claims.get("streaming_invalidation_proved") is not False
    ):
        raise ValueError("static-world resource claims drifted")


def validate_static_streaming(document):
    if (
        document.get("schema") != STREAMING_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "exact_simple_model_resource_payload_reset_paths"
    ):
        raise ValueError("static-world streaming proof drifted")
    try:
        resource = document["resource"]
        refresh = document["refresh"]
        transitions = document["transitions"]
        claims = document["claims"]
    except (KeyError, TypeError) as error:
        raise ValueError("static-world streaming proof is incomplete") from error
    expected_resource = {
        "class": "CSimpleModelResource",
        "vtable": "82229294",
        "payload_reference_offset": 64,
        "graph_offset": 112,
        "binding_offset": 76,
    }
    expected_refresh = {
        "slot": 15,
        "method": "82C46410",
        "graph_argument": "resource_plus_112",
        "binding_argument": "resource_plus_76",
    }
    expected_transitions = [
        {
            "kind": "direct_payload_reset",
            "slot": 16,
            "entry_hook": "82C46440",
            "exit_hook": "82C46480",
            "exit_resource_register": "r31",
        },
        {
            "kind": "refresh_then_payload_reset",
            "slot": 22,
            "entry_hook": "82C222C8",
            "exit_hook": "82C2231C",
            "exit_resource_register": "r30",
        },
    ]
    if any(resource.get(key) != value for key, value in expected_resource.items()):
        raise ValueError("static-world streaming resource proof drifted")
    if any(refresh.get(key) != value for key, value in expected_refresh.items()):
        raise ValueError("static-world streaming refresh proof drifted")
    if transitions != expected_transitions:
        raise ValueError("static-world streaming transition proof drifted")
    if (
        claims.get("owned_payload_reference_field_proved") is not True
        or claims.get("balanced_payload_reset_boundaries_proved") is not True
        or claims.get("payload_generation_invalidation_boundary_proved")
        is not True
        or claims.get("complete_streaming_invalidation_coverage_proved")
        is not False
        or claims.get("concrete_building_or_prop_identity_proved") is not False
    ):
        raise ValueError("static-world streaming claims drifted")


def validate_static_graph(document):
    if (
        document.get("schema") != GRAPH_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "exact_simple_model_resource_to_mesh_draw_graph"
    ):
        raise ValueError("static-world graph proof drifted")
    try:
        objects = document["objects"]
        dispatch = document["dispatch"]
        claims = document["claims"]
    except (KeyError, TypeError) as error:
        raise ValueError("static-world graph proof is incomplete") from error
    expected_objects = {
        "resource": {
            "class": "CSimpleModelResource",
            "vtable": "82229294",
        },
        "model": {
            "class": "CSimpleModel",
            "resource_offset": 112,
            "primary_vtable": "82229208",
            "secondary_vtable": "822291E8",
        },
        "submodel": {
            "class": "CSimpleSubModel",
            "vtable": "822291BC",
        },
        "mesh": {"class": "CSimpleMesh", "vtable": "822291A0"},
    }
    expected_dispatch = {
        "renderer": "82C4CCC8",
        "model_count_slot": 2,
        "model_submodel_slot": 4,
        "submodel_count_slot": 3,
        "submodel_mesh_slot": 5,
        "draw_member_entry_hook": "82C4DC54",
        "draw_member_exit_hook": "82C4DC58",
        "draw_emitter": "82416380",
        "entry_model_register": "r26",
        "entry_submodel_register": "r29",
        "entry_mesh_register": "r28",
    }
    if objects != expected_objects:
        raise ValueError("static-world graph object proof drifted")
    if any(dispatch.get(key) != value for key, value in expected_dispatch.items()):
        raise ValueError("static-world graph dispatch proof drifted")
    if (
        claims.get("resource_to_embedded_model_proved") is not True
        or claims.get("model_to_submodel_dispatch_proved") is not True
        or claims.get("submodel_to_mesh_dispatch_proved") is not True
        or claims.get("mesh_to_indexed_draw_proved") is not True
        or claims.get("concrete_building_or_prop_identity_proved") is not False
        or claims.get("mesh_material_semantics_proved") is not False
    ):
        raise ValueError("static-world graph claims drifted")


def validate_static_owner(document):
    if (
        document.get("schema") != OWNER_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "exact_model_presentation_to_simple_model_renderer_owner"
    ):
        raise ValueError("static-world owner proof drifted")
    try:
        presentation = document["presentation"]
        renderer_join = document["renderer_join"]
        resource_join = document["resource_join"]
        claims = document["claims"]
    except (KeyError, TypeError) as error:
        raise ValueError("static-world owner proof is incomplete") from error
    expected_presentation = {
        "class": "Presentation_Unified::CModelPresentation",
        "vtable": "822432D4",
        "constructor": "82DE9840",
        "destructor": "82DEA218",
        "deleting_destructor_slot": 0,
        "deleting_destructor": "82DEA508",
        "draw_slot": 12,
        "draw_method": "823F8DB8",
        "draw_entry_hook": "823F8DB8",
        "draw_exit_hook": "823F8FA0",
        "state_field_offset": 144,
        "resource_reference_offset": 148,
        "renderer_field_offset": 1608,
    }
    expected_join = {
        "prepare_helper": "823F8980",
        "constructor_wrapper": "82C4E3A0",
        "renderer_vtable": "82001B64",
        "bind_slot": 0,
        "bind_target": "82C4C838",
        "draw_slot": 12,
        "draw_target": "82C4CCC8",
        "join_kind": "balanced_synchronous_presentation_draw_scope",
    }
    expected_resource_join = {
        "initialize_slot": 7,
        "initialize_method": "82DEA298",
        "resource_bind": "82C48038",
        "presentation_resource_field_offset": 148,
        "binding_constructor": "824AFB20",
        "renderer_bind": "82C4C838",
        "reference_assignment": "826E1B10",
        "renderer_resource_field_offset": 72,
        "address_equation": (
            "presentation_plus_148_equals_renderer_plus_72"
        ),
    }
    if any(
        presentation.get(key) != value
        for key, value in expected_presentation.items()
    ):
        raise ValueError("static-world presentation proof drifted")
    if any(
        renderer_join.get(key) != value
        for key, value in expected_join.items()
    ):
        raise ValueError("static-world presentation renderer join drifted")
    if any(
        resource_join.get(key) != value
        for key, value in expected_resource_join.items()
    ):
        raise ValueError("static-world presentation resource join drifted")
    if (
        claims.get("exact_model_presentation_owner_proved") is not True
        or claims.get("presentation_to_renderer_field_proved") is not True
        or claims.get("presentation_to_resource_reference_proved") is not True
        or claims.get("renderer_bind_and_draw_dispatch_proved") is not True
        or claims.get("presentation_to_renderer_resource_identity_proved")
        is not True
        or claims.get("concrete_building_or_prop_identity_proved") is not False
        or claims.get("mesh_or_material_semantics_proved") is not False
    ):
        raise ValueError("static-world owner claims drifted")


def validate_static_asset_metadata(document):
    if (
        document.get("schema") != ASSET_METADATA_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "bounded_simple_model_asset_reference_metadata"
    ):
        raise ValueError("static-world asset metadata proof drifted")
    try:
        resource_key = document["resource_key"]
        effects = document["effect_references"]
        textures = document["texture_references"]
        claims = document["claims"]
        boundary = document["next_boundary"]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "static-world asset metadata proof is incomplete"
        ) from error
    expected_resource_key = {
        "presentation_class": "Presentation_Unified::CModelPresentation",
        "initialize_method": "82DEA298",
        "stored_name_offset": 16,
        "string_layout": "msvc_string_28_bytes_inline_capacity_below_16",
        "resource_reference_offset": 148,
        "resource_bind": "82C48038",
        "resource_type_argument": "00060000",
        "address_equation": (
            "resource_bind_key_equals_presentation_plus_16_string_bytes"
        ),
    }
    expected_effects = {
        "resource_class": "CSimpleModelResource",
        "prepare_helper": "823F8980",
        "records_pointer_offset": 124,
        "record_count_offset": 128,
        "record_count_width_bits": 16,
        "record_stride": 28,
        "record_layout": "msvc_string_28_bytes_inline_capacity_below_16",
        "suffix": ".fx",
        "suffix_address": "8224332C",
        "lookup": "82C39B78",
        "lookup_type_argument": "00060000",
    }
    expected_textures = {
        "resource_class": "CSimpleModelResource",
        "records_vector_offset": 288,
        "vector_begin_offset": 0,
        "vector_end_offset": 4,
        "record_stride": 28,
        "record_layout": "msvc_string_28_bytes_inline_capacity_below_16",
        "id_marker": "Id=",
        "id_marker_address": "8201C108",
        "path_format": "%s%stextures\\%s",
        "path_format_address": "8224331C",
        "lookup": "82C39730",
    }
    if resource_key != expected_resource_key:
        raise ValueError("static-world resource key proof drifted")
    if effects != expected_effects:
        raise ValueError("static-world effect reference proof drifted")
    if textures != expected_textures:
        raise ValueError("static-world texture reference proof drifted")
    if (
        claims.get("presentation_name_to_resource_key_proved") is not True
        or claims.get("bounded_effect_reference_table_proved") is not True
        or claims.get("bounded_texture_reference_table_proved") is not True
        or claims.get("effect_and_texture_path_construction_proved")
        is not True
        or claims.get("concrete_building_or_prop_category_proved") is not False
        or boundary.get("runtime_export")
        != "hash_and_structural_category_only"
        or boundary.get("plaintext_asset_names_allowed") is not False
    ):
        raise ValueError("static-world asset metadata claims drifted")


def validate_static_mesh_semantics(document):
    if (
        document.get("schema") != MESH_SEMANTICS_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "bounded_simple_mesh_draw_and_material_binding"
    ):
        raise ValueError("static-world mesh semantics proof drifted")
    try:
        geometry = document["geometry"]
        material = document["material_binding"]
        claims = document["claims"]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "static-world mesh semantics proof is incomplete"
        ) from error
    expected_geometry = {
        "class": "CSimpleMesh",
        "vtable": "822291A0",
        "primitive_type_offset": 36,
        "index_buffer_binding_offset": 96,
        "source_element_count_offset": 100,
        "primitive_count_helper": "82C48558",
        "primitive_scale_bias_table": "820023F0",
        "index_buffer_bind": "8244D760",
        "index_buffer_context_offset": 12812,
        "draw_emitter": "82416380",
        "draw_arguments": {
            "r3": "graphics_context",
            "r4": "mesh_plus_36_primitive_type",
            "r5": "zero_base_index",
            "r6": "zero_index_offset",
            "r7": "scale_times_primitive_count_plus_bias",
        },
        "index_buffer_clear_after_draw": True,
    }
    for key, value in expected_geometry.items():
        if geometry.get(key) != value:
            raise ValueError("static-world mesh geometry proof drifted")
    expected_scale_bias = [
        {"primitive_type": index, "scale": scale, "bias": bias}
        for index, (scale, bias) in enumerate(
            (
                (0, 0), (1, 0), (2, 0), (1, 1), (3, 0), (1, 2),
                (1, 2), (0, 0), (3, 0), (0, 0), (0, 0), (0, 0),
                (0, 0), (4, 0),
            )
        )
    ]
    if geometry.get("primitive_scale_bias") != expected_scale_bias:
        raise ValueError("static-world primitive scale/bias proof drifted")
    expected_material = {
        "class": "CSimpleSubModel_and_CSimpleMesh",
        "submodel_state_enabled_offset": 112,
        "submodel_state_selector_offset": 39,
        "submodel_state_object_offset": 32,
        "state_bind": "82410A70",
        "mesh_optional_reference_offset": 128,
        "optional_reference_resource_offset": 168,
        "optional_reference_dispatch_slot": 5,
        "resource_bind": "8244E728",
        "fallback_source": "renderer_r22",
    }
    if material != expected_material:
        raise ValueError("static-world material binding proof drifted")
    if (
        claims.get("primitive_and_element_count_fields_proved") is not True
        or claims.get("index_buffer_bind_draw_clear_sequence_proved")
        is not True
        or claims.get("submodel_state_binding_fields_proved") is not True
        or claims.get("optional_material_resource_branch_proved") is not True
        or claims.get("complete_vertex_layout_decoding_proved") is not False
        or claims.get("complete_material_parameter_decoding_proved") is not False
        or claims.get("native_draw_admission_proved") is not False
    ):
        raise ValueError("static-world mesh semantics claims drifted")


def build(
    static_ingress,
    static_lifetime,
    static_resource,
    static_streaming,
    static_graph,
    static_owner,
    static_asset_metadata,
    static_mesh_semantics,
    events,
    requested_session=None,
    allow_checkpoint=False,
):
    validate_static_ingress(static_ingress)
    validate_static_lifetime(static_lifetime)
    validate_static_resource(static_resource)
    validate_static_streaming(static_streaming)
    validate_static_graph(static_graph)
    validate_static_owner(static_owner)
    validate_static_asset_metadata(static_asset_metadata)
    validate_static_mesh_semantics(static_mesh_semantics)
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary, final_summary = select_runtime_evidence(
        selected, allow_checkpoint
    )
    expected_config = {
        "status": "armed",
        "class": "CSimpleModelRenderer",
        "vtable": "82001B64",
        "object_bytes": "368",
        "constructor": "82C4DF78",
        "constructor_publish_hook": "82C4E094",
        "deleting_destructor_slot": "16",
        "deleting_destructor": "82C4E420",
        "destructor_entry_hook": "82C4E1F8",
        "destructor_exit_hook": "82C4E264",
        "vtable_slot": "12",
        "dispatch": "82C4CCC8",
        "entry_hook": "82C4CCC8",
        "exit_hook": "82C4DEA0",
        "model_graph_field": "renderer_plus_72",
        "model_graph_bind_slot": "1",
        "model_graph_bind_hook": "82C4CCB0",
        "model_graph_release_slot": "15",
        "model_graph_release_hook": "82C4C6A8,82C4E0A0",
        "model_resource_class": "CSimpleModelResource",
        "model_resource_vtable": "82229294",
        "model_resource_bytes": "320",
        "model_resource_factory": "82C47F10",
        "model_resource_publish_hook": "82C47FBC",
        "model_resource_registration_hook": "82C4802C",
        "model_resource_destructor_entry_hook": "82C47DF8",
        "model_resource_destructor_exit_hook": "82C47E44",
        "model_resource_payload_reference": "resource_plus_64",
        "model_resource_refresh_slot": "15",
        "model_resource_refresh": "82C46410",
        "model_resource_direct_reset_slot": "16",
        "model_resource_direct_reset_hooks": "82C46440,82C46480",
        "model_resource_refresh_reset_slot": "22",
        "model_resource_refresh_reset_hooks": "82C222C8,82C2231C",
        "simple_model_offset": "resource_plus_112",
        "simple_model_vtable": "82229208",
        "simple_submodel_vtable": "822291BC",
        "simple_mesh_vtable": "822291A0",
        "simple_member_draw_hooks": "82C4DC54,82C4DC58",
        "presentation_class": "Presentation_Unified::CModelPresentation",
        "presentation_vtable": "822432D4",
        "presentation_draw_slot": "12",
        "presentation_draw_hooks": "823F8DB8,823F8FA0",
        "presentation_resource_field": "presentation_plus_148",
        "presentation_renderer_field": "presentation_plus_1608",
        "presentation_resource_join": (
            "presentation_plus_148_equals_renderer_plus_72"
        ),
        "asset_key_field": "presentation_plus_16_msvc_string",
        "asset_key_export": "fnv1a64_hash_and_length_only",
        "effect_reference_fields": "resource_plus_124_pointer_plus_128_u16",
        "texture_reference_vector": "resource_plus_288_stride_28",
        "asset_metadata_limits": "key_bytes_512_reference_count_4096",
        "mesh_primitive_type_field": "mesh_plus_36_u32",
        "mesh_index_buffer_binding_field": "mesh_plus_96_u32",
        "mesh_source_element_count_field": "mesh_plus_100_u32",
        "submodel_state_fields": "submodel_plus_32_u32_39_u8_112_u8",
        "mesh_optional_material_reference_field": "mesh_plus_128_u32",
        "mesh_semantics_export": "bounded_numeric_identity_fields_only",
        "draw_emitter": "82416380",
        "packet_hooks": "82416260,824162F4",
        "join": "synchronous_scope_to_physical_pm4_prepared_draw",
        "guest_payload_read": (
            "bounded_host_mapped_identity_asset_metadata_and_"
            "mesh_semantic_fields"
        ),
        "plaintext_asset_names_exported": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("static-world runtime configuration drifted")
    require_safety(config)
    require_safety(summary)
    expected_kinds = (
        ("complete", "incomplete", "not_observed")
        if final_summary
        else (
            "checkpoint_complete",
            "checkpoint_incomplete",
            "checkpoint_not_observed",
        )
    )
    if (
        summary.get("status") not in expected_kinds
        or summary.get("checkpoint_kind")
        != ("final" if final_summary else "periodic")
        or summary.get("classification")
        != "live_model_presentation_simple_model_mesh_to_prepared_draw"
    ):
        raise ValueError("static-world runtime summary drifted")

    keys = (
        "scope_entries",
        "scope_exits",
        "exact_scopes",
        "invalid_root",
        "vtable_mismatches",
        "invalid_graph_field",
        "unregistered_renderers",
        "nonlive_renderers",
        "unbound_graphs",
        "graph_mismatches",
        "scopes_with_packets",
        "scopes_without_packets",
        "packets_recorded",
        "packet_matches",
        "pending_packets",
        "prepared_matches",
        "unprepared_matches",
        "scope_overlaps",
        "exit_without_entry",
        "instances_published",
        "instances_destroyed",
        "instance_address_reuses",
        "lifecycle_table_overflow",
        "lifecycle_faults",
        "destructor_entries",
        "destructor_exits",
        "destructors_open",
        "destructors_without_instance",
        "graph_bind_observations",
        "graph_bind_successes",
        "graph_bind_null",
        "graph_bind_unregistered",
        "graph_bind_faults",
        "graph_replacements",
        "graph_release_observations",
        "graph_release_successes",
        "graph_release_empty",
        "graph_release_unregistered",
        "graph_release_faults",
        "resource_instances_published",
        "resource_instances_destroyed",
        "resource_address_reuses",
        "resource_table_overflow",
        "resource_lifecycle_faults",
        "resource_destructor_entries",
        "resource_destructor_exits",
        "resource_destructors_open",
        "resource_destructors_without_instance",
        "resource_registration_observations",
        "resource_registration_successes",
        "resource_registration_null",
        "resource_registration_unregistered",
        "resource_registration_type_mismatches",
        "resource_registration_faults",
        "resource_graph_bind_joins",
        "resource_scope_joins",
        "resource_scope_mismatches",
        "resource_transition_entries",
        "resource_transition_exits",
        "resource_transitions_open",
        "resource_transition_overflow",
        "resource_transition_exit_without_entry",
        "resource_transition_exact",
        "resource_direct_resets",
        "resource_refresh_resets",
        "resource_transition_invalid_root",
        "resource_transition_vtable_mismatches",
        "resource_transition_unregistered",
        "resource_transition_nonlive",
        "resource_transition_begin_read_faults",
        "resource_transition_completions",
        "resource_transition_completion_faults",
        "resource_payload_resets_with_reference",
        "resource_payload_resets_empty",
        "resource_payload_generation_invalidations",
        "member_entries",
        "member_exits",
        "member_exact",
        "member_scope_missing",
        "member_relation_mismatches",
        "member_vtable_read_faults",
        "member_vtable_mismatches",
        "member_overlaps",
        "member_exit_without_entry",
        "member_draws_with_packets",
        "member_draws_without_packets",
        "member_packets_recorded",
        "member_packet_mismatches",
        "mesh_semantic_observations",
        "mesh_semantic_exact",
        "mesh_semantic_read_faults",
        "mesh_semantic_packet_origins",
        "mesh_semantic_missing_packet_origins",
        "presentation_entries",
        "presentation_exits",
        "presentation_exact",
        "presentation_invalid_root",
        "presentation_vtable_mismatches",
        "presentation_resource_read_faults",
        "presentation_overlaps",
        "presentation_exit_without_entry",
        "presentation_scopes_with_renderer",
        "presentation_scopes_without_renderer",
        "presentation_renderer_joins",
        "presentation_renderer_mismatches",
        "presentation_resource_mismatches",
        "asset_metadata_observations",
        "asset_metadata_exact",
        "asset_metadata_empty_keys",
        "asset_metadata_read_faults",
        "asset_metadata_joins",
        "asset_metadata_missing_joins",
    )
    totals = {key: integer(summary, key) for key in keys}
    frame_sequence = integer(summary, "frame_sequence")
    failures = []
    classified = (
        totals["exact_scopes"]
        + totals["invalid_root"]
        + totals["vtable_mismatches"]
        + totals["invalid_graph_field"]
        + totals["unregistered_renderers"]
        + totals["nonlive_renderers"]
        + totals["unbound_graphs"]
        + totals["graph_mismatches"]
    )
    if summary.get("accounting_complete") != "true":
        failures.append("runtime accounting is incomplete")
    if totals["scope_entries"] != totals["scope_exits"]:
        failures.append("static-world scope entry/exit accounting drifted")
    if totals["scope_entries"] != classified:
        failures.append("static-world scope classification drifted")
    if totals["exact_scopes"] != (
        totals["scopes_with_packets"] + totals["scopes_without_packets"]
    ):
        failures.append("static-world scope outcome accounting drifted")
    if not totals["exact_scopes"]:
        failures.append("no exact SimpleModel renderer scope was observed")
    if not totals["instances_published"]:
        failures.append(
            "no completed SimpleModel renderer lifetime was observed"
        )
    if not totals["graph_bind_successes"]:
        failures.append("no owned SimpleModel renderer graph was observed")
    if not totals["resource_instances_published"]:
        failures.append("no completed SimpleModel resource lifetime was observed")
    if not totals["resource_registration_successes"]:
        failures.append("no registered SimpleModel resource was observed")
    if not totals["resource_graph_bind_joins"]:
        failures.append("no renderer bind joined a registered resource")
    if not totals["resource_scope_joins"]:
        failures.append("no exact scope joined a live resource generation")
    if not totals["resource_transition_exact"]:
        failures.append("no exact SimpleModel payload reset was observed")
    if not totals["resource_transition_completions"]:
        failures.append("no SimpleModel payload reset completed")
    if not totals["member_exact"]:
        failures.append("no exact SimpleModel model/submodel/mesh draw was observed")
    if not totals["member_packets_recorded"]:
        failures.append("no exact SimpleModel mesh draw emitted a PM4 packet")
    if not totals["scopes_with_packets"] or not totals["packets_recorded"]:
        failures.append("no exact scope emitted a PM4 draw packet")
    if totals["packet_matches"] + totals["pending_packets"] != totals[
        "packets_recorded"
    ]:
        failures.append("static-world packet outcome accounting drifted")
    if totals["packet_matches"] != (
        totals["prepared_matches"] + totals["unprepared_matches"]
    ):
        failures.append("static-world prepared accounting drifted")
    if totals["destructor_entries"] != (
        totals["destructor_exits"] + totals["destructors_open"]
    ):
        failures.append("static-world destructor accounting drifted")
    if totals["instances_destroyed"] > totals["instances_published"]:
        failures.append("static-world instance lifetime accounting drifted")
    if (
        totals["graph_bind_successes"]
        + totals["graph_bind_null"]
        + totals["graph_bind_unregistered"]
        + totals["graph_bind_faults"]
        != totals["graph_bind_observations"]
    ):
        failures.append("static-world graph bind accounting drifted")
    if (
        totals["graph_release_successes"]
        + totals["graph_release_empty"]
        + totals["graph_release_unregistered"]
        + totals["graph_release_faults"]
        != totals["graph_release_observations"]
    ):
        failures.append("static-world graph release accounting drifted")
    if totals["resource_destructor_entries"] != (
        totals["resource_destructor_exits"]
        + totals["resource_destructors_open"]
    ):
        failures.append("static-world resource destructor accounting drifted")
    if totals["resource_instances_destroyed"] > totals[
        "resource_instances_published"
    ]:
        failures.append("static-world resource lifetime accounting drifted")
    if (
        totals["resource_registration_successes"]
        + totals["resource_registration_null"]
        + totals["resource_registration_unregistered"]
        + totals["resource_registration_type_mismatches"]
        + totals["resource_registration_faults"]
        != totals["resource_registration_observations"]
    ):
        failures.append("static-world resource registration accounting drifted")
    if totals["resource_graph_bind_joins"] != totals["graph_bind_successes"]:
        failures.append("static-world resource graph-bind accounting drifted")
    if totals["resource_scope_joins"] != totals["exact_scopes"]:
        failures.append("static-world resource scope accounting drifted")
    resource_transition_classified = (
        totals["resource_transition_exact"]
        + totals["resource_transition_invalid_root"]
        + totals["resource_transition_vtable_mismatches"]
        + totals["resource_transition_unregistered"]
        + totals["resource_transition_nonlive"]
        + totals["resource_transition_begin_read_faults"]
        + totals["resource_transition_overflow"]
    )
    if totals["resource_transition_entries"] != resource_transition_classified:
        failures.append("static-world resource transition classification drifted")
    if totals["resource_transition_entries"] != totals["resource_transition_exits"]:
        failures.append("static-world resource transition entry/exit drifted")
    if totals["resource_transition_exact"] != (
        totals["resource_direct_resets"] + totals["resource_refresh_resets"]
    ):
        failures.append("static-world resource transition kind accounting drifted")
    if totals["resource_transition_exact"] != (
        totals["resource_transition_completions"]
        + totals["resource_transition_completion_faults"]
    ):
        failures.append("static-world resource transition outcome drifted")
    if totals["resource_transition_completions"] != (
        totals["resource_payload_resets_with_reference"]
        + totals["resource_payload_resets_empty"]
    ):
        failures.append("static-world resource payload-reset accounting drifted")
    if totals["resource_payload_generation_invalidations"] != totals[
        "resource_transition_completions"
    ]:
        failures.append("static-world resource payload generation drifted")
    member_classified = (
        totals["member_exact"]
        + totals["member_scope_missing"]
        + totals["member_relation_mismatches"]
        + totals["member_vtable_read_faults"]
        + totals["member_vtable_mismatches"]
    )
    if totals["member_entries"] != member_classified:
        failures.append("static-world member classification drifted")
    if totals["member_entries"] != totals["member_exits"]:
        failures.append("static-world member entry/exit accounting drifted")
    if totals["member_exact"] != (
        totals["member_draws_with_packets"]
        + totals["member_draws_without_packets"]
    ):
        failures.append("static-world member draw outcome accounting drifted")
    if totals["member_packets_recorded"] != totals["packets_recorded"]:
        failures.append("static-world member packet join accounting drifted")
    if totals["mesh_semantic_observations"] != totals["member_exact"]:
        failures.append("static-world mesh semantic observation drifted")
    if totals["mesh_semantic_observations"] != (
        totals["mesh_semantic_exact"]
        + totals["mesh_semantic_read_faults"]
    ):
        failures.append("static-world mesh semantic classification drifted")
    if totals["member_packets_recorded"] != (
        totals["mesh_semantic_packet_origins"]
        + totals["mesh_semantic_missing_packet_origins"]
    ):
        failures.append("static-world mesh semantic packet join drifted")
    presentation_classified = (
        totals["presentation_exact"]
        + totals["presentation_invalid_root"]
        + totals["presentation_vtable_mismatches"]
        + totals["presentation_resource_read_faults"]
    )
    if totals["presentation_entries"] != presentation_classified:
        failures.append("static-world presentation classification drifted")
    if totals["presentation_entries"] != totals["presentation_exits"]:
        failures.append("static-world presentation entry/exit accounting drifted")
    if totals["presentation_exact"] != (
        totals["presentation_scopes_with_renderer"]
        + totals["presentation_scopes_without_renderer"]
    ):
        failures.append("static-world presentation outcome accounting drifted")
    if totals["presentation_scopes_with_renderer"] > totals[
        "presentation_renderer_joins"
    ]:
        failures.append("static-world presentation renderer join drifted")
    if totals["asset_metadata_observations"] != totals["presentation_exact"]:
        failures.append("static-world asset metadata observation drifted")
    if totals["asset_metadata_observations"] != (
        totals["asset_metadata_exact"]
        + totals["asset_metadata_empty_keys"]
        + totals["asset_metadata_read_faults"]
    ):
        failures.append("static-world asset metadata classification drifted")
    if totals["presentation_renderer_joins"] != (
        totals["asset_metadata_joins"]
        + totals["asset_metadata_missing_joins"]
    ):
        failures.append("static-world asset metadata join drifted")
    if not totals["presentation_exact"]:
        failures.append("no exact CModelPresentation scope was observed")
    if not totals["presentation_renderer_joins"]:
        failures.append("no CModelPresentation joined its SimpleModel renderer")
    if not totals["asset_metadata_exact"]:
        failures.append("no bounded static-world asset metadata was observed")
    if not totals["asset_metadata_joins"]:
        failures.append("no asset-key hash joined a SimpleModel renderer")
    if not totals["mesh_semantic_exact"]:
        failures.append("no bounded static-world mesh semantics were observed")
    if not totals["mesh_semantic_packet_origins"]:
        failures.append("no mesh semantics joined a prepared-draw origin")
    if not totals["prepared_matches"]:
        failures.append("no static-world PM4 packet joined a prepared draw")
    for key in (
        "invalid_root",
        "vtable_mismatches",
        "invalid_graph_field",
        "unregistered_renderers",
        "nonlive_renderers",
        "graph_mismatches",
        "unprepared_matches",
        "scope_overlaps",
        "exit_without_entry",
        "lifecycle_table_overflow",
        "lifecycle_faults",
        "destructors_without_instance",
        "destructors_open",
        "graph_bind_unregistered",
        "graph_bind_faults",
        "graph_release_unregistered",
        "graph_release_faults",
        "resource_table_overflow",
        "resource_lifecycle_faults",
        "resource_destructors_without_instance",
        "resource_destructors_open",
        "resource_registration_unregistered",
        "resource_registration_type_mismatches",
        "resource_registration_faults",
        "resource_scope_mismatches",
        "resource_transitions_open",
        "resource_transition_overflow",
        "resource_transition_exit_without_entry",
        "resource_transition_invalid_root",
        "resource_transition_unregistered",
        "resource_transition_nonlive",
        "resource_transition_begin_read_faults",
        "resource_transition_completion_faults",
        "member_scope_missing",
        "member_relation_mismatches",
        "member_vtable_read_faults",
        "member_vtable_mismatches",
        "member_overlaps",
        "member_exit_without_entry",
        "member_draws_without_packets",
        "member_packet_mismatches",
        "mesh_semantic_read_faults",
        "mesh_semantic_missing_packet_origins",
        "presentation_invalid_root",
        "presentation_resource_read_faults",
        "presentation_overlaps",
        "presentation_exit_without_entry",
        "presentation_renderer_mismatches",
        "presentation_resource_mismatches",
        "asset_metadata_read_faults",
        "asset_metadata_missing_joins",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
    expected_status = (
        "complete" if not failures else "incomplete"
    ) if final_summary else (
        "checkpoint_complete" if not failures else "checkpoint_incomplete"
    )
    if summary.get("status") != expected_status:
        failures.append("runtime status does not match qualification outcome")
    if summary.get("qualification_complete") != (
        "true" if not failures else "false"
    ):
        failures.append("runtime qualification flag does not match outcome")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": expected_status,
        "evidence": {
            "kind": "final_summary" if final_summary else "periodic_checkpoint",
            "frame_sequence": frame_sequence,
            "session_exit_proved": final_summary,
            "native_admission_evidence": False,
        },
        "failures": failures,
        "totals": totals,
        "qualification": {
            "simple_model_renderer_scope_proved": not failures,
            "simple_model_renderer_lifetime_proved": not failures,
            "renderer_to_owned_graph_field_proved": not failures,
            "simple_model_resource_type_proved": not failures,
            "simple_model_resource_lifetime_proved": not failures,
            "renderer_to_registered_resource_proved": not failures,
            "simple_model_payload_reset_runtime_proved": not failures,
            "payload_generation_invalidation_proved": not failures,
            "resource_to_simple_model_proved": not failures,
            "simple_model_to_submodel_proved": not failures,
            "simple_submodel_to_mesh_proved": not failures,
            "simple_mesh_to_prepared_draw_proved": not failures,
            "model_presentation_owner_proved": not failures,
            "model_presentation_to_renderer_proved": not failures,
            "model_presentation_to_renderer_resource_proved": not failures,
            "bounded_asset_reference_metadata_proved": not failures,
            "hashed_asset_identity_to_prepared_draw_proved": not failures,
            "bounded_mesh_draw_semantics_proved": not failures,
            "bounded_material_binding_semantics_proved": not failures,
            "mesh_semantics_to_prepared_draw_proved": not failures,
            "static_world_scope_to_pm4_proved": not failures,
            "static_world_pm4_to_prepared_draw_proved": not failures,
            "building_or_prop_instance_identity_proved": False,
            "streaming_lifetime_proved": False,
            "complete_streaming_invalidation_coverage_proved": False,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "guest_state_changed": False,
            "control_flow_changed": False,
            "native_admission": False,
            "native_draw": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--lifetime", required=True, type=pathlib.Path)
    parser.add_argument("--resource", required=True, type=pathlib.Path)
    parser.add_argument("--streaming", required=True, type=pathlib.Path)
    parser.add_argument("--graph", required=True, type=pathlib.Path)
    parser.add_argument("--owner", required=True, type=pathlib.Path)
    parser.add_argument("--asset-metadata", required=True, type=pathlib.Path)
    parser.add_argument("--mesh-semantics", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--allow-checkpoint", action="store_true")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(
            json.loads(args.static.read_text(encoding="utf-8")),
            json.loads(args.lifetime.read_text(encoding="utf-8")),
            json.loads(args.resource.read_text(encoding="utf-8")),
            json.loads(args.streaming.read_text(encoding="utf-8")),
            json.loads(args.graph.read_text(encoding="utf-8")),
            json.loads(args.owner.read_text(encoding="utf-8")),
            json.loads(args.asset_metadata.read_text(encoding="utf-8")),
            json.loads(args.mesh_semantics.read_text(encoding="utf-8")),
            read_events(args.events),
            args.session,
            args.allow_checkpoint,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if document["status"] not in ("complete", "checkpoint_complete"):
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"static-world runtime join failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
