import copy
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-semantic-draws.py"
SPEC = importlib.util.spec_from_file_location("semantic_draws", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def static_inventory():
    return {
        "schema": MODULE.STATIC_SCHEMA,
        "procedural_model_receiver_lifecycle": {
            "semantic_draw_association": {
                "render_item_entry_hook_address": "8241741C",
                "render_item_exit_hook_address": "82417B80",
                "geometry_submission_hook_address": "82417B60",
                "title_draw_packet_hook_addresses": ["82410328", "829F7CB0"],
                "semantic_draw_packet_hook_addresses": [
                    "82416260", "824162F4",
                ],
                "title_indirect_packet_hook_addresses": [
                    "824095B4", "82416EFC", "8246FC1C",
                    "8263BD64", "829E8E88", "829EC49C",
                ],
                "graphics_submission_vtable_offset": 160,
                "graphics_submission_target_runtime_join_required": True,
                "graphics_submission_wrapper_address": "82415CE0",
                "graphics_submission_emitter_address": "82415F68",
                "semantic_draw_packet_opcode": "PM4_DRAW_INDX",
                "semantic_draw_packet_opcode_value": 0x22,
                "render_item_invocation_scope_proved": True,
                "submission_before_draw_dispatch_proved": True,
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
        },
        "draw_packet_provenance": {
            "packet_sites": [
                {"packet_hook_address": "82410328"},
                {"packet_hook_address": "829F7CB0"},
            ]
        },
    }


def events():
    common = {"session": "semantic-draw-run"}
    return [
        {
            **common,
            "event": "native_renderer.discovery.semantic_draw_config",
            "status": "armed",
            "scene": "open_world",
            "class": "proceduralGeometry::CProceduralModels",
            "render_item_entry_hook": "8241741C",
            "render_item_exit_hook": "82417B80",
            "geometry_submission_hook": "82417B60",
            "title_packet_hooks": "82410328,829F7CB0",
            "semantic_packet_hooks": "82416260,824162F4",
            "graphics_submission_wrapper": "82415CE0",
            "graphics_submission_emitter": "82415F68",
            "semantic_packet_opcode": "PM4_DRAW_INDX_0x22",
            "semantic_catalog": (
                "prepared_template_dynamic_resource_instance_and_batch_key"
            ),
            "semantic_catalog_capacity": "4096",
            "title_indirect_packet_hooks":
                "824095B4,82416EFC,8246FC1C,8263BD64,829E8E88,829EC49C",
            "correlation": "exact_render_item_scope_to_emitted_and_backend_pm4_header",
            "classification": "procedural_submission_pm4_packet_boundary",
            "guest_state_changed": "false",
            "native_upload": "false",
            "native_draw": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": "native_renderer.discovery.semantic_submission_entry",
            "key": "1122334455667788",
            "calls": "12",
            "receiver_address": "40102030",
            "receiver_generation": "7",
            "record_index": "4",
            "descriptor_kind": "0",
            "helper_state": "9",
            "graphics_submission_method": "82417BC0",
            "primary_resource_key": "00001000",
            "secondary_resource_present": "false",
            "secondary_resource_key": "00000000",
            "runtime_submission_object": "40103000",
            "count_bytes": "48",
            "source_address": "40104000",
        },
        {
            **common,
            "event": "native_renderer.discovery.semantic_submission_summary",
            "live_observations": "12",
        },
        {
            **common,
            "event": "native_renderer.discovery.title_provenance_entry",
            "semantic_submission_key": "1122334455667788",
            "semantic_receiver_address": "40102030",
            "semantic_receiver_generation": "7",
            "semantic_record_index": "4",
            "semantic_descriptor_address": "50001000",
            "semantic_runtime_address": "50002000",
            "semantic_draw_association":
                "exact_render_item_scope_and_physical_pm4_header",
            "semantic_identity": "procedural_model_submission",
            "origin_wrapper": "procedural_model_draw_indexed",
            "origin_wrapper_address": "82415F68",
            "origin_caller": "82416260",
            "outcome": "prepared",
            "backend_outcome": "prepared_callback",
            "backend_signature": "AABBCCDDEEFF0011",
            "prepared_signature": "AABBCCDDEEFF0011",
            "semantic_template_key": "1122334455667788",
            "semantic_prepared_pipeline_hash": "0000000000000001",
            "semantic_geometry_layout_hash": "0000000000000002",
            "semantic_texture_layout_hash": "0000000000000003",
            "semantic_render_state_hash": "0000000000000004",
            "semantic_geometry_resource_hash": "0000000000000005",
            "semantic_texture_resource_hash": "0000000000000006",
            "semantic_vertex_shader": "0000000000000007",
            "semantic_pixel_shader": "0000000000000008",
            "semantic_vertex_specialization": "0000000000000009",
            "semantic_pixel_specialization": "000000000000000A",
            "semantic_primitive_type": "13",
            "semantic_source_select": "0",
            "semantic_indexed": "true",
            "semantic_minimum_index_count": "12",
            "semantic_maximum_index_count": "12",
            "semantic_index_buffer_address": "40105000",
            "semantic_index_buffer_length": "24",
            "semantic_index_format": "0",
            "semantic_index_endianness": "2",
            "semantic_vertex_binding_count": "1",
            "semantic_vertex_attribute_count": "3",
            "semantic_first_vertex_address": "40106000",
            "semantic_first_vertex_size": "256",
            "semantic_first_vertex_stride_words": "8",
            "semantic_first_vertex_endianness": "2",
            "semantic_texture_fetch_mask": "00000001",
            "semantic_texture_layout_valid_mask": "00000001",
            "semantic_texture_state_count": "1",
            "semantic_geometry_bounded": "true",
            "semantic_texture_layout_bounded": "true",
            "semantic_template_variations": "0",
            "semantic_resource_variations": "0",
            "semantic_catalog_classification": (
                "immutable_template_and_dynamic_resource_instance"
            ),
            "calls": "12",
            "xenos_draw": "preserved",
            "suppression_eligible": "false",
        },
        {
            **common,
            "event": "native_renderer.discovery.semantic_instance_entry",
            "key": "0102030405060708",
            "receiver_address": "40102030",
            "receiver_generation": "7",
            "record_index": "4",
            "descriptor_address": "50001000",
            "runtime_address": "50002000",
            "descriptor_hash": "1000000000000001",
            "runtime_hash": "1000000000000002",
            "transform_hash": "1000000000000003",
            "descriptor_variations": "0",
            "runtime_variations": "11",
            "transform_variations": "11",
            "fallback": "xenos_replay",
            "native_draw": "false",
            "suppression_allowed": "false",
        },
        {
            **common,
            "event": "native_renderer.discovery.semantic_instance_summary",
            "live_observations": "12",
            "unknown_receivers": "0",
            "invalid_layouts": "0",
            "invalid_indices": "0",
            "replay_fallbacks": "12",
            "native_admissions": "0",
            "entries": "1",
            "overflow": "0",
        },
        {
            **common,
            "event": "native_renderer.discovery.title_provenance_summary",
            "semantic_submission_live_observations": "12",
            "semantic_render_item_entries": "20",
            "semantic_render_item_exits": "20",
            "semantic_render_items_open_at_shutdown": "0",
            "semantic_render_item_valid_scopes": "20",
            "semantic_render_item_scopes_without_submission": "8",
            "semantic_render_item_stack_faults": "0",
            "semantic_draw_scope_joins": "12",
            "semantic_draw_scope_mismatches": "0",
            "semantic_draw_origins_captured": "12",
            "semantic_draw_dispatches_with_direct_title_origin": "12",
            "semantic_draw_dispatches_without_direct_title_origin": "0",
            "semantic_draw_overlap_probe_accounting_complete": "true",
            "semantic_draw_indirect_packet_origins_captured": "0",
            "semantic_draw_dispatches_with_indirect_packet_origin": "0",
            "semantic_draw_dispatches_without_indirect_packet_origin": "12",
            "semantic_draw_packets_recorded": "12",
            "semantic_draw_packet_matches": "12",
            "semantic_draw_prepared_matches": "12",
            "semantic_draw_unprepared_matches": "0",
            "semantic_draw_pending_packets": "0",
            "semantic_draw_accounting_complete": "true",
            "semantic_contract_entries": "1",
            "semantic_contract_calls": "12",
            "semantic_bounded_geometry_calls": "12",
            "semantic_bounded_texture_calls": "12",
            "semantic_stable_template_calls": "12",
            "semantic_stable_resource_calls": "12",
            "semantic_template_variations": "0",
            "semantic_resource_variations": "0",
            "semantic_catalog_accounting_complete": "true",
        },
    ]


class SemanticDrawTests(unittest.TestCase):
    def test_builds_exact_submission_to_prepared_draw_lineage(self):
        document = MODULE.build(events(), static_inventory())
        self.assertEqual("complete", document["status"])
        self.assertEqual(12, document["totals"]["semantic_submissions"])
        self.assertEqual(12, document["totals"]["prepared_draw_calls"])
        self.assertEqual(1, document["totals"]["unique_prepared_signatures"])
        self.assertTrue(document["physical_pm4_packet_correlation_proved"])
        self.assertTrue(document["prepared_draw_lineage_proved"])
        self.assertTrue(document["compact_semantic_catalog_proved"])
        self.assertEqual(1, document["totals"]["semantic_template_count"])
        self.assertEqual(1, document["totals"]["semantic_batch_group_count"])
        self.assertEqual(12, document["totals"]["semantic_batchable_calls"])
        self.assertFalse(document["native_batching_enabled"])
        self.assertFalse(document["safety"]["native_draw"])
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_records_a_complete_negative_direct_packet_overlap(self):
        observed = copy.deepcopy(events())
        del observed[3]
        summary = observed[-1]
        summary["semantic_draw_origins_captured"] = "0"
        summary["semantic_draw_dispatches_with_direct_title_origin"] = "0"
        summary["semantic_draw_dispatches_without_direct_title_origin"] = "12"
        summary["semantic_draw_packets_recorded"] = "0"
        summary["semantic_draw_packet_matches"] = "0"
        summary["semantic_draw_prepared_matches"] = "0"
        summary["semantic_draw_accounting_complete"] = "false"
        summary["semantic_contract_entries"] = "0"
        summary["semantic_contract_calls"] = "0"
        summary["semantic_bounded_geometry_calls"] = "0"
        summary["semantic_bounded_texture_calls"] = "0"
        summary["semantic_stable_template_calls"] = "0"
        summary["semantic_stable_resource_calls"] = "0"
        document = MODULE.build(observed, static_inventory())
        self.assertEqual("complete", document["status"])
        self.assertFalse(document["prepared_draw_lineage_proved"])
        self.assertEqual(0, document["totals"]["associated_draw_calls"])
        self.assertEqual(
            12,
            document["totals"][
                "semantic_draw_dispatches_without_direct_title_origin"
            ],
        )

    def test_accepts_multiple_exact_draw_packets_for_one_submission_scope(self):
        observed = copy.deepcopy(events())
        observed[3]["calls"] = "15"
        summary = observed[-1]
        summary["semantic_draw_origins_captured"] = "15"
        summary["semantic_draw_packets_recorded"] = "15"
        summary["semantic_draw_packet_matches"] = "15"
        summary["semantic_draw_prepared_matches"] = "15"
        summary["semantic_contract_calls"] = "15"
        summary["semantic_bounded_geometry_calls"] = "15"
        summary["semantic_bounded_texture_calls"] = "15"
        summary["semantic_stable_template_calls"] = "15"
        summary["semantic_stable_resource_calls"] = "15"
        document = MODULE.build(observed, static_inventory())
        self.assertEqual(12, document["totals"]["semantic_submissions"])
        self.assertEqual(15, document["totals"]["prepared_draw_calls"])
        self.assertTrue(document["prepared_draw_lineage_proved"])

    def test_rejects_mismatched_submission_identity(self):
        observed = copy.deepcopy(events())
        observed[3]["semantic_record_index"] = "5"
        with self.assertRaisesRegex(ValueError, "identity or safety"):
            MODULE.build(observed, static_inventory())

    def test_keeps_varying_resources_out_of_conservative_batches(self):
        observed = copy.deepcopy(events())
        observed[3]["semantic_resource_variations"] = "1"
        summary = observed[-1]
        summary["semantic_stable_resource_calls"] = "0"
        summary["semantic_resource_variations"] = "1"
        document = MODULE.build(observed, static_inventory())
        self.assertFalse(document["compact_semantic_catalog_proved"])
        self.assertEqual(0, document["totals"]["semantic_batchable_calls"])
        self.assertFalse(document["batch_groups"][0]["batchable"])

    def test_rejects_submission_without_an_immutable_instance(self):
        observed = [
            event
            for event in copy.deepcopy(events())
            if event.get("event")
            != "native_renderer.discovery.semantic_instance_entry"
        ]
        with self.assertRaisesRegex(ValueError, "no immutable instance"):
            MODULE.build(observed, static_inventory())

    def test_rejects_incomplete_scope_accounting(self):
        observed = copy.deepcopy(events())
        observed[-1]["semantic_draw_scope_mismatches"] = "1"
        observed[-1]["semantic_draw_accounting_complete"] = "false"
        with self.assertRaisesRegex(ValueError, "accounting"):
            MODULE.build(observed, static_inventory())

    def test_rejects_static_suppression_eligibility(self):
        static = static_inventory()
        static["procedural_model_receiver_lifecycle"][
            "semantic_draw_association"
        ]["suppression_eligible"] = True
        with self.assertRaisesRegex(ValueError, "static contract"):
            MODULE.build(events(), static)


if __name__ == "__main__":
    unittest.main()
