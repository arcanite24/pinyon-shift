import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-static-world-runtime-join.py"
SPEC = importlib.util.spec_from_file_location("static_world_runtime_join", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def event(name, **values):
    return {"event": name, "session": "test", **values}


def safety():
    return {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }


def static_ingress():
    slots = [f"{0x82800000 + index * 4:08X}" for index in range(17)]
    slots[12] = "82C4CCC8"
    return {
        "schema": MODULE.STATIC_SCHEMA,
        "status": "complete",
        "classification": "title_simple_model_static_world_ingress_proved",
        "classes": {
            "simple_model_renderer": {
                "decorated_name": ".?AVCSimpleModelRenderer@@",
                "surfaces": [
                    {
                        "label": "primary",
                        "vtable_address": "82001B64",
                        "vtable_slot_count": 17,
                        "slot_targets": slots,
                    }
                ],
            }
        },
    }


def static_lifetime():
    return {
        "schema": MODULE.LIFETIME_SCHEMA,
        "status": "complete",
        "classification": (
            "exact_simple_model_renderer_lifetime_and_graph_owner"
        ),
        "renderer": {
            "class": "CSimpleModelRenderer",
            "vtable": "82001B64",
            "object_bytes": 368,
            "constructor": "82C4DF78",
            "constructor_publish_hook": "82C4E094",
            "deleting_destructor_slot": 16,
            "deleting_destructor": "82C4E420",
            "destructor_entry_hook": "82C4E1F8",
            "destructor_exit_hook": "82C4E264",
        },
        "graph_ownership": {
            "field_offset": 72,
            "bind_slot": 1,
            "bind_method": "82C4CC50",
            "bind_completion_hook": "82C4CCB0",
            "release_slot": 15,
            "release_method": "82C4C6A8",
            "destructor_cleanup": "82C4E0A0",
            "draw_slot": 12,
            "draw_dispatch": "82C4CCC8",
        },
        "claims": {
            "renderer_generation_boundary_proved": True,
            "renderer_to_owned_graph_field_proved": True,
            "concrete_building_or_prop_identity_proved": False,
        },
    }


def static_resource():
    return {
        "schema": MODULE.RESOURCE_SCHEMA,
        "status": "complete",
        "classification": "exact_simple_model_resource_factory_and_lifetime",
        "resource": {
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
        },
        "binding": {
            "renderer_bind": "82C48038",
            "renderer_graph_field_offset": 72,
            "factory_output_argument": "r5",
            "reference_assignment": "824E81A8",
            "existing_resource_path_join": "82C4802C",
            "new_resource_path_join": "82C4802C",
        },
        "claims": {
            "bound_graph_dynamic_type_proved": True,
            "resource_generation_boundary_proved": True,
            "factory_registration_boundary_proved": True,
            "concrete_building_or_prop_identity_proved": False,
            "streaming_invalidation_proved": False,
        },
    }


def static_streaming():
    return {
        "schema": MODULE.STREAMING_SCHEMA,
        "status": "complete",
        "classification": "exact_simple_model_resource_payload_reset_paths",
        "resource": {
            "class": "CSimpleModelResource",
            "vtable": "82229294",
            "payload_reference_offset": 64,
            "graph_offset": 112,
            "binding_offset": 76,
        },
        "refresh": {
            "slot": 15,
            "method": "82C46410",
            "graph_argument": "resource_plus_112",
            "binding_argument": "resource_plus_76",
        },
        "invalidation_surface": {
            "vtable_slot_count": 23,
            "vtable_targets": [
                "82C47EC0", "82A0E238", "824493C0", "82448FD8",
                "82B755A8", "82D68710", "830B2320", "82611B80",
                "82D68710", "82D68710", "82D68710", "82D68710",
                "82D68710", "82611B80", "824D7F98", "82C46410",
                "82C46440", "82D68710", "830B2320", "82C462C0",
                "824D7FA8", "82611B80", "82C222C8",
            ],
            "unique_target_count": 14,
            "destruction_slot": 0,
            "destructor": "82C47DF8",
            "base_destructor": "82E45B20",
            "destructor_payload_release": "resource_plus_64_reference_clear",
            "live_payload_reset_slots": [16, 22],
            "other_live_payload_reset_slots": [],
        },
        "transitions": [
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
        ],
        "claims": {
            "owned_payload_reference_field_proved": True,
            "balanced_payload_reset_boundaries_proved": True,
            "payload_generation_invalidation_boundary_proved": True,
            "complete_class_vtable_invalidation_coverage_proved": True,
            "complete_streaming_invalidation_coverage_proved": False,
            "concrete_building_or_prop_identity_proved": False,
        },
    }


def static_graph():
    return {
        "schema": MODULE.GRAPH_SCHEMA,
        "status": "complete",
        "classification": "exact_simple_model_resource_to_mesh_draw_graph",
        "objects": {
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
        },
        "dispatch": {
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
        },
        "claims": {
            "resource_to_embedded_model_proved": True,
            "model_to_submodel_dispatch_proved": True,
            "submodel_to_mesh_dispatch_proved": True,
            "mesh_to_indexed_draw_proved": True,
            "concrete_building_or_prop_identity_proved": False,
            "mesh_material_semantics_proved": False,
        },
    }


def static_owner():
    return {
        "schema": MODULE.OWNER_SCHEMA,
        "status": "complete",
        "classification": (
            "exact_model_presentation_to_simple_model_renderer_owner"
        ),
        "presentation": {
            "class": "Presentation_Unified::CModelPresentation",
            "vtable": "822432D4",
            "refcounted_primary_vtable": "82002464",
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
        },
        "renderer_join": {
            "prepare_helper": "823F8980",
            "constructor_wrapper": "82C4E3A0",
            "renderer_vtable": "82001B64",
            "bind_slot": 0,
            "bind_target": "82C4C838",
            "draw_slot": 12,
            "draw_target": "82C4CCC8",
            "join_kind": "balanced_synchronous_presentation_draw_scope",
        },
        "resource_join": {
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
        },
        "transform_join": {
            "presentation_transform_offset": 80,
            "transform_size_bytes": 64,
            "renderer_transform_slot": 6,
            "renderer_transform_target": "82C4C568",
            "renderer_transform_offset": 128,
            "address_equation": (
                "presentation_plus_80_64_bytes_copied_to_renderer_plus_128"
            ),
        },
        "claims": {
            "exact_model_presentation_owner_proved": True,
            "presentation_to_renderer_field_proved": True,
            "presentation_to_resource_reference_proved": True,
            "renderer_bind_and_draw_dispatch_proved": True,
            "presentation_to_renderer_resource_identity_proved": True,
            "presentation_transform_to_renderer_proved": True,
            "concrete_building_or_prop_identity_proved": False,
            "mesh_or_material_semantics_proved": False,
        },
    }


def static_asset_metadata():
    return {
        "schema": MODULE.ASSET_METADATA_SCHEMA,
        "status": "complete",
        "classification": "bounded_simple_model_asset_reference_metadata",
        "resource_key": {
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
        },
        "effect_references": {
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
        },
        "texture_references": {
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
        },
        "claims": {
            "presentation_name_to_resource_key_proved": True,
            "bounded_effect_reference_table_proved": True,
            "bounded_texture_reference_table_proved": True,
            "effect_and_texture_path_construction_proved": True,
            "concrete_building_or_prop_category_proved": False,
        },
        "next_boundary": {
            "runtime_export": "hash_and_structural_category_only",
            "plaintext_asset_names_allowed": False,
        },
    }


def static_mesh_semantics():
    scale_bias = (
        (0, 0), (1, 0), (2, 0), (1, 1), (3, 0), (1, 2), (1, 2),
        (0, 0), (3, 0), (0, 0), (0, 0), (0, 0), (0, 0), (4, 0),
    )
    return {
        "schema": MODULE.MESH_SEMANTICS_SCHEMA,
        "status": "complete",
        "classification": "bounded_simple_mesh_draw_and_material_binding",
        "geometry": {
            "class": "CSimpleMesh",
            "vtable": "822291A0",
            "primitive_type_offset": 36,
            "index_buffer_binding_offset": 96,
            "source_element_count_offset": 100,
            "primitive_count_helper": "82C48558",
            "primitive_scale_bias_table": "820023F0",
            "primitive_scale_bias": [
                {"primitive_type": index, "scale": scale, "bias": bias}
                for index, (scale, bias) in enumerate(scale_bias)
            ],
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
        },
        "material_binding": {
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
        },
        "prepared_layout_boundary": {
            "draw_state_flush": "8240BB40",
            "flush_after_index_buffer_bind": True,
            "flush_before_draw_emitter": True,
            "runtime_source": "xenos_decoded_draw_observation",
            "runtime_join": "exact_physical_pm4_header_origin",
            "vertex_binding_limit": 8,
            "vertex_attribute_limit": 32,
            "float_constant_limit_per_stage": 64,
            "texture_state_limit": 16,
            "payload_bytes_exported": False,
        },
        "claims": {
            "primitive_and_element_count_fields_proved": True,
            "index_buffer_bind_draw_clear_sequence_proved": True,
            "submodel_state_binding_fields_proved": True,
            "optional_material_resource_branch_proved": True,
            "complete_vertex_layout_runtime_boundary_proved": True,
            "bounded_material_parameter_runtime_boundary_proved": True,
            "complete_vertex_layout_decoding_proved": False,
            "complete_material_parameter_decoding_proved": False,
            "native_draw_admission_proved": False,
        },
    }


def fixture():
    config = event(
        MODULE.CONFIG,
        status="armed",
        **{
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
            "presentation_refcounted_vtable": "82002464",
            "presentation_draw_slot": "12",
            "presentation_draw_hooks": "823F8DB8,823F8FA0",
            "presentation_resource_field": "presentation_plus_148",
            "presentation_renderer_field": "presentation_plus_1608",
            "presentation_resource_join": (
                "presentation_plus_148_equals_renderer_plus_72"
            ),
            "presentation_transform_field": (
                "presentation_plus_80_16_be_u32"
            ),
            "presentation_transform_dispatch": (
                "renderer_slot_6_82C4C568_to_renderer_plus_128"
            ),
            "transform_export": "hash_and_16_numeric_words_only",
            "asset_key_field": "presentation_plus_16_msvc_string",
            "asset_key_export": "fnv1a64_hash_and_length_only",
            "effect_reference_fields": (
                "resource_plus_124_pointer_plus_128_u16"
            ),
            "texture_reference_vector": "resource_plus_288_stride_28",
            "asset_metadata_limits": "key_bytes_512_reference_count_4096",
            "mesh_primitive_type_field": "mesh_plus_36_u32",
            "mesh_index_buffer_binding_field": "mesh_plus_96_u32",
            "mesh_source_element_count_field": "mesh_plus_100_u32",
            "submodel_state_fields": "submodel_plus_32_u32_39_u8_112_u8",
            "mesh_optional_material_reference_field": "mesh_plus_128_u32",
            "mesh_semantics_export": "bounded_numeric_identity_fields_only",
            "prepared_layout_boundary": (
                "xenos_decoded_draw_observation_joined_by_physical_pm4_origin"
            ),
            "prepared_layout_capacity": "512",
            "prepared_layout_export": (
                "complete_bounded_vertex_fetch_attribute_constant_and_"
                "texture_metadata"
            ),
            "draw_emitter": "82416380",
            "packet_hooks": "82416260,824162F4",
            "join": "synchronous_scope_to_physical_pm4_prepared_draw",
            "guest_payload_read": (
                "bounded_host_mapped_identity_asset_metadata_and_"
                "mesh_semantic_fields"
            ),
            "plaintext_asset_names_exported": "false",
            **safety(),
        },
    )
    summary = event(
        MODULE.SUMMARY,
        status="complete",
        checkpoint_kind="final",
        frame_sequence="1200",
        scope_entries="12",
        scope_exits="12",
        exact_scopes="10",
        invalid_root="0",
        vtable_mismatches="0",
        invalid_graph_field="0",
        unregistered_renderers="0",
        nonlive_renderers="0",
        unbound_graphs="2",
        graph_mismatches="0",
        scopes_with_packets="8",
        scopes_without_packets="2",
        packets_recorded="100",
        packet_matches="98",
        pending_packets="2",
        prepared_matches="98",
        unprepared_matches="0",
        scope_overlaps="0",
        exit_without_entry="0",
        instances_published="3",
        instances_destroyed="1",
        instance_address_reuses="0",
        lifecycle_table_overflow="0",
        lifecycle_faults="0",
        destructor_entries="1",
        destructor_exits="1",
        destructors_open="0",
        destructors_without_instance="0",
        graph_bind_observations="4",
        graph_bind_successes="3",
        graph_bind_null="1",
        graph_bind_unregistered="0",
        graph_bind_faults="0",
        graph_replacements="0",
        graph_release_observations="1",
        graph_release_successes="1",
        graph_release_empty="0",
        graph_release_unregistered="0",
        graph_release_faults="0",
        resource_instances_published="3",
        resource_instances_destroyed="1",
        resource_address_reuses="0",
        resource_table_overflow="0",
        resource_lifecycle_faults="0",
        resource_destructor_entries="1",
        resource_destructor_exits="1",
        resource_destructors_open="0",
        resource_destructors_without_instance="0",
        resource_registration_observations="4",
        resource_registration_successes="3",
        resource_registration_null="1",
        resource_registration_unregistered="0",
        resource_registration_type_mismatches="0",
        resource_registration_faults="0",
        resource_graph_bind_joins="3",
        resource_scope_joins="10",
        resource_scope_mismatches="0",
        resource_transition_entries="6",
        resource_transition_exits="6",
        resource_transitions_open="0",
        resource_transition_overflow="0",
        resource_transition_exit_without_entry="0",
        resource_transition_exact="2",
        resource_direct_resets="1",
        resource_refresh_resets="1",
        resource_transition_invalid_root="0",
        resource_transition_vtable_mismatches="4",
        resource_transition_unregistered="0",
        resource_transition_nonlive="0",
        resource_transition_begin_read_faults="0",
        resource_transition_completions="2",
        resource_transition_completion_faults="0",
        resource_payload_resets_with_reference="1",
        resource_payload_resets_empty="1",
        resource_payload_generation_invalidations="2",
        member_entries="98",
        member_exits="98",
        member_exact="98",
        member_scope_missing="0",
        member_relation_mismatches="0",
        member_vtable_read_faults="0",
        member_vtable_mismatches="0",
        member_overlaps="0",
        member_exit_without_entry="0",
        member_draws_with_packets="98",
        member_draws_without_packets="0",
        member_packets_recorded="100",
        member_packet_mismatches="0",
        mesh_semantic_observations="98",
        mesh_semantic_exact="98",
        mesh_semantic_read_faults="0",
        mesh_semantic_packet_origins="100",
        mesh_semantic_missing_packet_origins="0",
        prepared_layout_observations="98",
        prepared_layout_exact="98",
        prepared_layout_unbounded_geometry="0",
        prepared_layout_parameter_overflows="0",
        prepared_layout_entries="12",
        prepared_layout_table_overflow="0",
        presentation_entries="12",
        presentation_exits="12",
        presentation_exact="12",
        presentation_invalid_root="0",
        presentation_vtable_mismatches="0",
        presentation_resource_read_faults="0",
        presentation_overlaps="0",
        presentation_exit_without_entry="0",
        presentation_scopes_with_renderer="8",
        presentation_scopes_without_renderer="4",
        presentation_renderer_joins="8",
        presentation_renderer_mismatches="0",
        presentation_resource_mismatches="0",
        asset_metadata_observations="12",
        asset_metadata_exact="10",
        asset_metadata_empty_keys="2",
        asset_metadata_read_faults="0",
        asset_metadata_joins="8",
        asset_metadata_missing_joins="0",
        transform_observations="12",
        transform_exact="12",
        transform_read_faults="0",
        transform_joins="8",
        transform_missing_joins="0",
        transform_packet_origins="100",
        transform_missing_packet_origins="0",
        accounting_complete="true",
        qualification_complete="true",
        classification=(
            "live_model_presentation_simple_model_mesh_to_prepared_draw"
        ),
        **safety(),
    )
    return [config, summary]


class StaticWorldRuntimeJoinTests(unittest.TestCase):
    def test_qualifies_exact_scope_to_prepared_draw(self):
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            fixture(),
        )
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["static_world_pm4_to_prepared_draw_proved"]
        )
        self.assertTrue(
            document["qualification"]["simple_model_renderer_lifetime_proved"]
        )
        self.assertTrue(
            document["qualification"]["simple_model_resource_type_proved"]
        )
        self.assertTrue(
            document["qualification"]["simple_mesh_to_prepared_draw_proved"]
        )
        self.assertTrue(
            document["qualification"][
                "mesh_semantics_to_prepared_draw_proved"
            ]
        )
        self.assertTrue(
            document["qualification"][
                "complete_vertex_layout_to_prepared_draw_proved"
            ]
        )
        self.assertTrue(
            document["qualification"][
                "bounded_material_parameter_boundary_proved"
            ]
        )
        self.assertTrue(
            document["qualification"]["model_presentation_owner_proved"]
        )
        self.assertTrue(
            document["qualification"][
                "model_presentation_to_renderer_resource_proved"
            ]
        )
        self.assertTrue(
            document["qualification"][
                "model_presentation_transform_to_prepared_draw_proved"
            ]
        )
        self.assertFalse(
            document["qualification"]["building_or_prop_instance_identity_proved"]
        )
        self.assertFalse(document["qualification"]["native_admission"])

    def test_checkpoint_is_diagnostic_not_admission_evidence(self):
        events = fixture()
        checkpoint = events.pop()
        checkpoint.update(
            event=MODULE.CHECKPOINT,
            status="checkpoint_complete",
            checkpoint_kind="periodic",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events + [checkpoint],
            allow_checkpoint=True,
        )
        self.assertEqual("checkpoint_complete", document["status"])
        self.assertFalse(document["evidence"]["session_exit_proved"])
        self.assertFalse(document["evidence"]["native_admission_evidence"])

    def test_rejects_unprepared_packet_match(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            prepared_matches="97",
            unprepared_matches="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn("unprepared_matches is nonzero", document["failures"])

    def test_rejects_transform_read_fault(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            transform_exact="11",
            transform_read_faults="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn("transform_read_faults is nonzero", document["failures"])

    def test_rejects_missing_transform_packet_origin(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            transform_packet_origins="99",
            transform_missing_packet_origins="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "transform_missing_packet_origins is nonzero",
            document["failures"],
        )

    def test_rejects_scope_accounting_fault(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            scope_exits="9",
            accounting_complete="false",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "static-world scope entry/exit accounting drifted",
            document["failures"],
        )

    def test_rejects_static_dispatch_drift(self):
        ingress = static_ingress()
        ingress["classes"]["simple_model_renderer"]["surfaces"][0][
            "slot_targets"
        ][12] = "82C4CCD0"
        with self.assertRaisesRegex(ValueError, "dispatch proof drifted"):
            MODULE.build(
                ingress,
                static_lifetime(),
                static_resource(),
                static_streaming(),
                static_graph(),
                static_owner(),
                static_asset_metadata(),
                static_mesh_semantics(),
                fixture(),
            )

    def test_rejects_unregistered_renderer_dispatch(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            exact_scopes="9",
            unregistered_renderers="1",
            scopes_with_packets="7",
            accounting_complete="true",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "unregistered_renderers is nonzero", document["failures"]
        )

    def test_rejects_resource_type_mismatch(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            resource_registration_successes="2",
            resource_registration_type_mismatches="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "resource_registration_type_mismatches is nonzero",
            document["failures"],
        )

    def test_rejects_unregistered_resource(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            resource_registration_successes="2",
            resource_registration_unregistered="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "resource_registration_unregistered is nonzero",
            document["failures"],
        )

    def test_rejects_payload_reset_completion_fault(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            resource_transition_completions="1",
            resource_transition_completion_faults="1",
            resource_payload_resets_empty="0",
            resource_payload_generation_invalidations="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "resource_transition_completion_faults is nonzero",
            document["failures"],
        )

    def test_rejects_presentation_renderer_mismatch(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            presentation_renderer_mismatches="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "presentation_renderer_mismatches is nonzero",
            document["failures"],
        )

    def test_rejects_presentation_resource_mismatch(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            presentation_resource_mismatches="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "presentation_resource_mismatches is nonzero",
            document["failures"],
        )

    def test_rejects_asset_metadata_missing_from_renderer_join(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            asset_metadata_joins="7",
            asset_metadata_missing_joins="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "asset_metadata_missing_joins is nonzero", document["failures"]
        )

    def test_rejects_mesh_semantic_read_fault(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            mesh_semantic_exact="97",
            mesh_semantic_read_faults="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "mesh_semantic_read_faults is nonzero", document["failures"]
        )

    def test_rejects_mesh_semantics_missing_from_packet_origin(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            mesh_semantic_packet_origins="99",
            mesh_semantic_missing_packet_origins="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "mesh_semantic_missing_packet_origins is nonzero",
            document["failures"],
        )

    def test_rejects_unbounded_prepared_vertex_layout(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            prepared_layout_exact="97",
            prepared_layout_unbounded_geometry="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "prepared_layout_unbounded_geometry is nonzero",
            document["failures"],
        )

    def test_rejects_prepared_layout_table_overflow(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            prepared_layout_table_overflow="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "prepared_layout_table_overflow is nonzero",
            document["failures"],
        )

    def test_rejects_prepared_material_parameter_overflow(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            prepared_layout_exact="97",
            prepared_layout_parameter_overflows="1",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(),
            static_lifetime(),
            static_resource(),
            static_streaming(),
            static_graph(),
            static_owner(),
            static_asset_metadata(),
            static_mesh_semantics(),
            events,
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "prepared_layout_parameter_overflows is nonzero",
            document["failures"],
        )

    def test_rejects_static_asset_key_offset_drift(self):
        metadata = static_asset_metadata()
        metadata["resource_key"]["stored_name_offset"] = 20
        with self.assertRaisesRegex(ValueError, "resource key proof drifted"):
            MODULE.build(
                static_ingress(),
                static_lifetime(),
                static_resource(),
                static_streaming(),
                static_graph(),
                static_owner(),
                metadata,
                static_mesh_semantics(),
                fixture(),
            )

    def test_rejects_static_mesh_primitive_offset_drift(self):
        semantics = static_mesh_semantics()
        semantics["geometry"]["primitive_type_offset"] = 40
        with self.assertRaisesRegex(ValueError, "mesh geometry proof drifted"):
            MODULE.build(
                static_ingress(),
                static_lifetime(),
                static_resource(),
                static_streaming(),
                static_graph(),
                static_owner(),
                static_asset_metadata(),
                semantics,
                fixture(),
            )

    def test_source_contract_has_balanced_static_world_hooks(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("kSimpleModelRendererVtable = 0x82001B64", hooks)
        self.assertIn("BeginStaticWorldRendererDispatch", hooks)
        self.assertIn("EndStaticWorldRendererDispatch", hooks)
        self.assertIn("BeginStaticWorldPresentationDispatch", hooks)
        self.assertIn("EndStaticWorldPresentationDispatch", hooks)
        self.assertIn("static_world_draw", hooks)
        self.assertIn("address = 0x82C4CCC8", analysis)
        self.assertIn("address = 0x82C4DEA0", analysis)
        self.assertIn("address = 0x82C4E094", analysis)
        self.assertIn("address = 0x82C4E1F8", analysis)
        self.assertIn("address = 0x82C4E264", analysis)
        self.assertIn("address = 0x82C4CCB0", analysis)
        self.assertIn("address = 0x82C4C6A8", analysis)
        self.assertIn("address = 0x82C4E0A0", analysis)
        self.assertIn("address = 0x82C47FBC", analysis)
        self.assertIn("address = 0x82C4802C", analysis)
        self.assertIn("address = 0x82C47DF8", analysis)
        self.assertIn("address = 0x82C47E44", analysis)
        self.assertIn("address = 0x82C46440", analysis)
        self.assertIn("address = 0x82C46480", analysis)
        self.assertIn("address = 0x82C222C8", analysis)
        self.assertIn("address = 0x82C2231C", analysis)
        self.assertIn("address = 0x82C4DC54", analysis)
        self.assertIn("address = 0x82C4DC58", analysis)
        self.assertIn("address = 0x823F8DB8", analysis)
        self.assertIn("address = 0x823F8DE0", analysis)
        self.assertIn("address = 0x823F8FA0", analysis)
        self.assertIn("ObserveStaticWorldPresentationPrepareOutcome", hooks)
        self.assertIn("kModelPresentationNameOffset = 16", hooks)
        self.assertIn("kRefCountedModelPresentationVtable = 0x82002464", hooks)
        self.assertIn("kModelPresentationTransformOffset = 80", hooks)
        self.assertIn("ReadStaticWorldPresentationTransform", hooks)
        self.assertIn("static_world_transform_words", hooks)
        self.assertIn("transform_missing_packet_origins", hooks)
        self.assertIn("ReadStaticWorldAssetMetadata", hooks)
        self.assertIn("static_world_asset_key_hash", hooks)
        self.assertIn("kSimpleMeshPrimitiveTypeOffset = 36", hooks)
        self.assertIn("mesh_semantic_packet_origins", hooks)
        self.assertIn("static_world_mesh_primitive_type", hooks)
        self.assertIn("RecordStaticWorldPreparedLayout", hooks)
        self.assertIn("static_world_prepared_layout_entry", hooks)


if __name__ == "__main__":
    unittest.main()
