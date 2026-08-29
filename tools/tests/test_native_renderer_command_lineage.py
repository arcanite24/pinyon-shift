import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-command-lineage.py"
SPEC = importlib.util.spec_from_file_location("native_command_lineage", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def static_inventory():
    return {
        "schema": "pinyon-shift.native-renderer-dispatch-static.v3",
        "packet_constructors": [
            {
                "function": "sub_82409398",
                "function_address": "82409398",
                "constructor_address": "824095AC",
                "constructor_instruction": "ori r10,r10,16128",
                "store_address": "824095B4",
                "store_instruction": "stwx r10,r11,r28",
                "packet_register": "r10",
                "opcode": "PM4_INDIRECT_BUFFER",
                "opcode_value": "3F",
                "header_source": "fixed_type3_count_2",
                "role": "unreviewed",
            }
        ],
    }


def events():
    common = {"session": "lineage-session"}
    return [
        {
            **common,
            "event": "native_renderer.discovery.command_buffer_lineage_config",
            "status": "armed",
            "scene": "open_world",
        },
        {
            **common,
            "event": "native_renderer.discovery.command_buffer_lineage_entry",
            "sample_prepared_signature": "747837906D0BF484",
            "prepared_signature_varied": "true",
            "calls": "12",
            "first_frame": "10",
            "last_frame": "20",
            "first_draw": "3",
            "last_draw": "7",
            "sample_packet_physical_address": "00102040",
            "sample_command_buffer_physical_address": "00102000",
            "sample_command_buffer_length_dwords": "64",
            "min_command_buffer_length_dwords": "48",
            "max_command_buffer_length_dwords": "96",
            "min_packet_offset_bytes": "32",
            "max_packet_offset_bytes": "96",
            "sample_parent_packet_physical_address": "00004020",
            "sample_root_physical_address": "00102000",
            "min_parent_root_offset_bytes": "none",
            "max_parent_root_offset_bytes": "none",
            "constructor_store_address": "824095B4",
            "depth": "1",
        },
        {
            **common,
            "event": "native_renderer.discovery.command_buffer_lineage_summary",
            "draws": "14",
            "primary_draws": "2",
            "indirect_draws": "12",
            "invalid_lineages": "0",
            "prepared_draws": "12",
            "entries": "1",
            "overflow": "0",
            "capacity": "4096",
            "title_indirect_packets_recorded": "37",
            "title_indirect_packet_address_failures": "0",
            "title_indirect_packet_table_overflow": "0",
            "title_indirect_packet_evictions": "7",
            "indirect_buffer_enters": "30",
            "indirect_buffer_exits": "28",
            "indirect_buffers_open_at_shutdown": "2",
            "indirect_buffer_constructor_matches": "20",
            "indirect_buffer_constructor_unmatched": "10",
            "indirect_buffer_stack_faults": "0",
            "indirect_draw_stack_faults": "0",
            "correlation": "exact_title_store_to_backend_nested_command_buffer_shape",
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false",
        },
    ]


def nested_events():
    result = events()
    result[1].update(
        {
            "sample_packet_physical_address": "00103040",
            "sample_command_buffer_physical_address": "00103000",
            "sample_parent_packet_physical_address": "00102020",
            "sample_root_physical_address": "00102000",
            "min_parent_root_offset_bytes": "16",
            "max_parent_root_offset_bytes": "48",
            "depth": "2",
        }
    )
    return result


def context_root_inventory():
    static = static_inventory()
    static["indirect_constructor_calls"] = [
        {
            "constructor_function_address": "82409398",
            "caller_function": "sub_82409668",
            "caller_function_address": "82409668",
            "callsite": "82409834",
            "return_address": "82409838",
        }
    ]
    static["indirect_owner_calls"] = [
        {
            "owner_function_address": "82409668",
            "caller_function": "sub_8240D070",
            "caller_function_address": "8240D070",
            "callsite": "8240D1AC",
            "return_address": "8240D1B0",
        }
    ]
    static["indirect_producer_calls"] = [
        {
            "producer_function_address": "8240D070",
            "caller_function": "sub_8240CF68",
            "caller_function_address": "8240CF68",
            "callsite": "8240CFFC",
            "return_address": "8240D000",
        }
    ]
    static["indirect_context_roots"] = [
        {
            "context_function": "sub_8240CF68",
            "context_function_address": "8240CF68",
            "producer_function": "sub_8240D070",
            "producer_function_address": "8240D070",
            "producer_return_address": "8240D000",
            "root_entry_register": "r3",
            "root_offset": 0,
            "derivation": "r3",
        }
    ]
    return static


def context_root_events():
    traced = events()
    traced[1].update(
        {
            "constructor_function_address": "82409398",
            "constructor_return_address": "82409838",
            "sample_constructor_arguments": "00000000," * 7 + "00000000",
            "constructor_argument_varying_mask": "00",
            "owner_function_address": "82409668",
            "owner_return_address": "8240D1B0",
            "sample_owner_arguments": "00000000," * 7 + "00000000",
            "owner_argument_varying_mask": "00",
            "producer_function_address": "8240D070",
            "producer_return_address": "8240D000",
            "sample_producer_arguments": (
                "10000000,20000000,00000001,00000000,00000000,"
                "00000000,00000000,00000000"
            ),
            "producer_argument_varying_mask": "03",
            "context_function_address": "8240CF68",
            "context_return_address": "83000000",
            "sample_context_arguments": (
                "10000000,30000000,00000002,00000000,00000000,"
                "00000000,00000000,00000000"
            ),
            "context_argument_varying_mask": "05",
            "sample_context_root_address": "10000000",
            "context_root_address_varied": "false",
        }
    )
    traced[-1].update(
        {
            "indirect_constructor_entries": "1",
            "indirect_constructor_exits": "1",
            "indirect_owner_entries": "1",
            "indirect_owner_exits": "1",
            "indirect_producer_entries": "1",
            "indirect_producer_exits": "1",
            "indirect_owner_producer_mismatches": "0",
            "indirect_context_entries": "1",
            "indirect_context_exits": "1",
            "indirect_context_invocations_open_at_shutdown": "0",
            "indirect_context_stack_faults": "0",
            "indirect_producers_without_context_origin": "0",
            "indirect_producer_context_mismatches": "0",
        }
    )
    return traced


def procedural_model_inventory():
    static = context_root_inventory()
    static["indirect_constructor_calls"][0].update(
        {
            "caller_function": "sub_824167F8",
            "caller_function_address": "824167F8",
            "callsite": "82416894",
            "return_address": "82416898",
        }
    )
    static["indirect_owner_calls"][0].update(
        {
            "owner_function_address": "824167F8",
            "caller_function": "sub_82417060",
            "caller_function_address": "82417060",
            "callsite": "824170B8",
            "return_address": "824170BC",
        }
    )
    static["indirect_producer_calls"][0].update(
        {
            "producer_function_address": "82417060",
            "caller_function": "sub_82417BC0",
            "caller_function_address": "82417BC0",
            "callsite": "82418A24",
            "return_address": "82418A28",
        }
    )
    static["indirect_context_roots"][0].update(
        {
            "context_function": "sub_82417BC0",
            "context_function_address": "82417BC0",
            "producer_function": "sub_82417060",
            "producer_function_address": "82417060",
            "producer_return_address": "82418A28",
            "root_entry_register": "r6",
            "root_offset": 59712,
            "derivation": "r6+59712",
        }
    )
    static["procedural_model_receiver_lifecycle"] = {
        "class_name": "proceduralGeometry::CProceduralModels",
        "dispatch_function_address": "82417BC0",
        "rtti_vtable_identity_proved": True,
        "object_extent_proved": True,
        "visibility_preparation_boundary_proved": True,
        "render_state_boundary_proved": True,
        "transform_matrix_ranges_proved": True,
    }
    return static


def procedural_model_events():
    traced = context_root_events()
    traced[1].update(
        {
            "constructor_return_address": "82416898",
            "owner_function_address": "824167F8",
            "owner_return_address": "824170BC",
            "producer_function_address": "82417060",
            "producer_return_address": "82418A28",
            "sample_producer_arguments": (
                "1000E940,20000000,00000001,00000000,00000000,"
                "00000000,00000000,00000000"
            ),
            "context_function_address": "82417BC0",
            "sample_context_arguments": (
                "20000000,30000000,00000002,10000000,00000000,"
                "00000000,00000000,00000000"
            ),
            "sample_context_root_address": "1000E940",
            "semantic_receiver_class": (
                "proceduralGeometry::CProceduralModels"
            ),
            "semantic_receiver_address": "20000000",
            "semantic_receiver_generation": "1",
            "semantic_visibility_epoch": "2",
            "semantic_render_state_epoch": "1",
            "semantic_render_state_visibility_epoch": "2",
            "semantic_preparation_epoch_varied": "true",
        }
    )
    summary = traced.pop()
    summary.update(
        {
            "semantic_receiver_constructor_entries": "1",
            "semantic_receiver_constructor_exits": "1",
            "semantic_receiver_constructor_open_at_shutdown": "0",
            "semantic_receiver_destructor_entries": "0",
            "semantic_receiver_destructor_exits": "0",
            "semantic_receiver_destructor_open_at_shutdown": "0",
            "semantic_receiver_stack_faults": "0",
            "semantic_receiver_instances_published": "1",
            "semantic_receiver_instances_destroyed": "0",
            "semantic_receiver_address_reuses": "0",
            "semantic_receiver_table_overflow": "0",
            "semantic_receiver_dispatches": "1",
            "semantic_receiver_live_dispatches": "1",
            "semantic_receiver_unregistered_dispatches": "0",
            "semantic_receiver_destroying_dispatches": "0",
            "semantic_receiver_destroyed_dispatches": "0",
            "semantic_receiver_destructors_without_instance": "0",
            "semantic_receivers_tracked": "1",
            "semantic_receivers_live_at_shutdown": "1",
            "semantic_receivers_destroying_at_shutdown": "0",
            "semantic_receivers_destroyed": "0",
            "semantic_visibility_entries": "2",
            "semantic_visibility_exits": "2",
            "semantic_visibility_open_at_shutdown": "0",
            "semantic_render_state_entries": "1",
            "semantic_render_state_exits": "1",
            "semantic_render_state_open_at_shutdown": "0",
            "semantic_stage_stack_faults": "0",
            "semantic_stage_unknown_receivers": "0",
        }
    )
    traced.extend(
        [
            {
                "session": "lineage-session",
                "event": "native_renderer.discovery.semantic_receiver_config",
                "status": "armed",
            },
            {
                "session": "lineage-session",
                "event": (
                    "native_renderer.discovery."
                    "semantic_receiver_lifecycle_entry"
                ),
                "class": "proceduralGeometry::CProceduralModels",
                "address": "20000000",
                "generation": "1",
                "state": "live",
                "dispatches": "1",
                "visibility_preparations": "2",
                "render_state_preparations": "1",
                "visibility_epoch": "2",
                "render_state_epoch": "1",
                "render_state_visibility_epoch": "2",
                "dispatches_with_preparation": "1",
                "dispatches_without_preparation": "0",
                "dispatches_without_visibility": "0",
                "dispatches_without_render_state": "0",
                "identity_join": "exact_constructor_receiver_address",
                "guest_payload_read": "false",
                "xenos_authority": "true",
                "suppression_allowed": "false",
            },
            summary,
        ]
    )
    return traced


class NativeRendererCommandLineageTests(unittest.TestCase):
    def test_builds_complete_exact_lineage_report(self):
        document = MODULE.build(events(), static_inventory())
        self.assertEqual("complete", document["status"])
        self.assertEqual(12, document["totals"]["indirect_draws"])
        self.assertEqual(1, document["totals"]["static_constructors"])
        self.assertEqual(
            "retained_sky_horizon_anchor",
            document["shapes"][0]["sample_prepared_family"],
        )
        self.assertEqual(1, document["shapes"][0]["depth"])
        self.assertEqual(
            48, document["shapes"][0]["min_command_buffer_length_dwords"]
        )
        self.assertEqual(
            96, document["shapes"][0]["max_command_buffer_length_dwords"]
        )
        self.assertEqual(2, document["totals"]["indirect_buffers_open_at_shutdown"])
        self.assertEqual(7, document["totals"]["title_indirect_packet_evictions"])
        self.assertEqual(
            10,
            document["totals"][
                "title_indirect_packets_retained_at_shutdown"
            ],
        )
        self.assertTrue(document["shapes"][0]["prepared_signature_varied"])
        self.assertEqual(
            "824095B4", document["shapes"][0]["constructor_store_address"]
        )
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_proves_procedural_model_receiver_generation(self):
        document = MODULE.build(
            procedural_model_events(), procedural_model_inventory()
        )
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            "procedural_model_receiver_stage_history",
            document["semantic_identity"],
        )
        self.assertEqual(
            "20000000", document["entries"][0]["semantic_receiver_address"]
        )
        self.assertEqual(
            1, document["entries"][0]["semantic_receiver_generation"]
        )
        self.assertEqual(
            12,
            document["totals"]["procedural_model_receiver_origin_draws"],
        )

    def test_accepts_observed_alternate_procedural_model_stage_routes(self):
        traced = procedural_model_events()
        traced[-2]["dispatches_with_preparation"] = "0"
        traced[-2]["dispatches_without_preparation"] = "1"
        document = MODULE.build(traced, procedural_model_inventory())
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            1,
            document["totals"][
                "semantic_dispatches_before_both_observed_stages"
            ],
        )

    def test_fails_closed_on_unregistered_procedural_model_dispatch(self):
        traced = procedural_model_events()
        traced[-1]["semantic_receiver_unregistered_dispatches"] = "1"
        traced[-1]["semantic_receiver_live_dispatches"] = "0"
        traced[-2]["dispatches"] = "0"
        traced[-2]["dispatches_with_preparation"] = "0"
        document = MODULE.build(traced, procedural_model_inventory())
        self.assertEqual("incomplete_fail_closed", document["status"])

    def test_fails_closed_on_invalid_or_overflowed_lineage(self):
        broken = events()
        broken[-1]["invalid_lineages"] = "1"
        broken[-1]["overflow"] = "2"
        document = MODULE.build(broken, static_inventory())
        self.assertEqual("incomplete_fail_closed", document["status"])

    def test_accepts_stable_nested_parent_root_shape(self):
        document = MODULE.build(nested_events(), static_inventory())
        entry = document["entries"][0]
        self.assertEqual(2, entry["depth"])
        self.assertEqual(16, entry["min_parent_root_offset_bytes"])
        self.assertEqual(48, entry["max_parent_root_offset_bytes"])
        self.assertEqual(
            16, document["shapes"][0]["min_parent_root_offset_bytes"]
        )

    def test_rejects_nested_parent_root_offset_mismatch(self):
        broken = nested_events()
        broken[1]["min_parent_root_offset_bytes"] = "36"
        with self.assertRaisesRegex(ValueError, "exclude their sample"):
            MODULE.build(broken, static_inventory())

    def test_fails_closed_without_an_exact_constructor_match(self):
        broken = events()
        broken[-1]["indirect_buffer_constructor_matches"] = "0"
        broken[-1]["indirect_buffer_constructor_unmatched"] = "30"
        document = MODULE.build(broken, static_inventory())
        self.assertEqual("incomplete_fail_closed", document["status"])

    def test_fails_closed_when_shutdown_open_buffers_do_not_balance(self):
        broken = events()
        broken[-1]["indirect_buffers_open_at_shutdown"] = "1"
        document = MODULE.build(broken, static_inventory())
        self.assertEqual("incomplete_fail_closed", document["status"])

    def test_rejects_unproved_constructor_store(self):
        broken = events()
        broken[1]["constructor_store_address"] = "82400000"
        with self.assertRaisesRegex(ValueError, "unproved constructor"):
            MODULE.build(broken, static_inventory())

    def test_rejects_indirect_entry_without_parent_packet(self):
        broken = events()
        broken[1]["sample_parent_packet_physical_address"] = "FFFFFFFF"
        with self.assertRaisesRegex(ValueError, "no valid parent packet"):
            MODULE.build(broken, static_inventory())

    def test_rejects_invalid_first_indirect_root(self):
        broken = events()
        broken[1]["sample_root_physical_address"] = "00103000"
        with self.assertRaisesRegex(ValueError, "root differs"):
            MODULE.build(broken, static_inventory())

    def test_requires_statically_proved_indirect_constructor(self):
        static = static_inventory()
        static["packet_constructors"] = []
        with self.assertRaisesRegex(ValueError, "no stored indirect-buffer"):
            MODULE.build(events(), static)

    def test_maps_runtime_constructor_origin_to_static_caller(self):
        static = static_inventory()
        static["indirect_constructor_calls"] = [
            {
                "constructor_function_address": "82409398",
                "caller_function": "sub_829E9790",
                "caller_function_address": "829E9790",
                "callsite": "829E982C",
                "return_address": "829E9830",
            }
        ]
        traced = events()
        traced[1].update(
            {
                "constructor_function_address": "82409398",
                "constructor_return_address": "829E9830",
                "sample_constructor_arguments": (
                    "10000000,20000000,00000001,00000000,00000000,"
                    "00000000,00000000,00000000"
                ),
                "constructor_argument_varying_mask": "03",
            }
        )
        traced[-1].update(
            {
                "indirect_constructor_entries": "4",
                "indirect_constructor_exits": "3",
                "indirect_constructor_invocations_open_at_shutdown": "1",
                "indirect_constructor_stack_faults": "0",
                "indirect_packets_without_constructor_origin": "2",
            }
        )
        document = MODULE.build(traced, static)
        self.assertEqual("complete", document["status"])
        shape = document["shapes"][0]
        self.assertEqual("829E982C", shape["constructor_callsite"])
        self.assertEqual("sub_829E9790", shape["constructor_caller_function"])
        self.assertEqual(3, shape["constructor_argument_varying_mask"])
        self.assertEqual(
            2,
            document["totals"]["indirect_packets_without_constructor_origin"],
        )

    def test_retains_exact_runtime_origin_when_static_caller_is_unresolved(self):
        static = static_inventory()
        static["indirect_constructor_calls"] = [
            {
                "constructor_function_address": "82409398",
                "caller_function": "sub_829E9790",
                "caller_function_address": "829E9790",
                "callsite": "829E982C",
                "return_address": "829E9830",
            }
        ]
        traced = events()
        traced[1].update(
            {
                "constructor_function_address": "82409398",
                "constructor_return_address": "83000004",
                "sample_constructor_arguments": (
                    "00000000,00000000,00000000,00000000,00000000,"
                    "00000000,00000000,00000000"
                ),
                "constructor_argument_varying_mask": "00",
            }
        )
        traced[-1].update(
            {
                "indirect_constructor_entries": "1",
                "indirect_constructor_exits": "1",
                "indirect_constructor_invocations_open_at_shutdown": "0",
                "indirect_constructor_stack_faults": "0",
            }
        )
        document = MODULE.build(traced, static)
        self.assertEqual("complete", document["status"])
        self.assertFalse(document["shapes"][0]["constructor_callsite_proved"])
        self.assertEqual(
            12, document["totals"]["unresolved_constructor_origin_draws"]
        )

    def test_maps_balanced_owner_origin_to_static_caller(self):
        static = static_inventory()
        static["indirect_constructor_calls"] = [
            {
                "constructor_function_address": "82409398",
                "caller_function": "sub_82409668",
                "caller_function_address": "82409668",
                "callsite": "82409834",
                "return_address": "82409838",
            }
        ]
        static["indirect_owner_calls"] = [
            {
                "owner_function_address": "82409668",
                "caller_function": "sub_82469290",
                "caller_function_address": "82469290",
                "callsite": "824693E0",
                "return_address": "824693E4",
            }
        ]
        traced = events()
        traced[1].update(
            {
                "constructor_function_address": "82409398",
                "constructor_return_address": "82409838",
                "sample_constructor_arguments": (
                    "10000000,20000000,00000001,00000000,00000000,"
                    "00000000,00000000,00000000"
                ),
                "constructor_argument_varying_mask": "03",
                "owner_function_address": "82409668",
                "owner_return_address": "824693E4",
                "sample_owner_arguments": (
                    "30000000,40000000,00000002,00000000,00000000,"
                    "00000000,00000000,00000000"
                ),
                "owner_argument_varying_mask": "05",
            }
        )
        traced[-1].update(
            {
                "indirect_constructor_entries": "4",
                "indirect_constructor_exits": "4",
                "indirect_constructor_invocations_open_at_shutdown": "0",
                "indirect_constructor_stack_faults": "0",
                "indirect_owner_entries": "4",
                "indirect_owner_exits": "4",
                "indirect_owner_invocations_open_at_shutdown": "0",
                "indirect_owner_stack_faults": "0",
                "indirect_constructors_without_owner_origin": "0",
                "indirect_constructor_owner_mismatches": "0",
            }
        )
        document = MODULE.build(traced, static)
        self.assertEqual("complete", document["status"])
        shape = document["shapes"][0]
        self.assertEqual("824693E0", shape["owner_callsite"])
        self.assertEqual("sub_82469290", shape["owner_caller_function"])
        self.assertEqual(5, shape["owner_argument_varying_mask"])
        self.assertEqual(12, document["totals"]["owner_origin_draws"])
        self.assertEqual(
            12, document["totals"]["statically_resolved_owner_origin_draws"]
        )

    def test_maps_balanced_producer_origin_to_static_caller(self):
        static = static_inventory()
        static["indirect_constructor_calls"] = [
            {
                "constructor_function_address": "82409398",
                "caller_function": "sub_82409668",
                "caller_function_address": "82409668",
                "callsite": "82409834",
                "return_address": "82409838",
            }
        ]
        static["indirect_owner_calls"] = [
            {
                "owner_function_address": "82409668",
                "caller_function": "sub_8240D070",
                "caller_function_address": "8240D070",
                "callsite": "8240D1AC",
                "return_address": "8240D1B0",
            }
        ]
        static["indirect_producer_calls"] = [
            {
                "producer_function_address": "8240D070",
                "caller_function": "sub_8240CF68",
                "caller_function_address": "8240CF68",
                "callsite": "8240CFFC",
                "return_address": "8240D000",
            }
        ]
        traced = events()
        traced[1].update(
            {
                "constructor_function_address": "82409398",
                "constructor_return_address": "82409838",
                "sample_constructor_arguments": "00000000," * 7 + "00000000",
                "constructor_argument_varying_mask": "00",
                "owner_function_address": "82409668",
                "owner_return_address": "8240D1B0",
                "sample_owner_arguments": "00000000," * 7 + "00000000",
                "owner_argument_varying_mask": "00",
                "producer_function_address": "8240D070",
                "producer_return_address": "8240D000",
                "sample_producer_arguments": (
                    "10000000,20000000,00000001,00000000,00000000,"
                    "00000000,00000000,00000000"
                ),
                "producer_argument_varying_mask": "03",
            }
        )
        traced[-1].update(
            {
                "indirect_constructor_entries": "1",
                "indirect_constructor_exits": "1",
                "indirect_owner_entries": "1",
                "indirect_owner_exits": "1",
                "indirect_producer_entries": "1",
                "indirect_producer_exits": "1",
                "indirect_owner_producer_mismatches": "0",
            }
        )
        document = MODULE.build(traced, static)
        self.assertEqual("complete", document["status"])
        shape = document["shapes"][0]
        self.assertEqual("8240CFFC", shape["producer_callsite"])
        self.assertEqual("sub_8240CF68", shape["producer_caller_function"])
        self.assertEqual(3, shape["producer_argument_varying_mask"])
        self.assertEqual(12, document["totals"]["producer_origin_draws"])
        self.assertEqual(
            12,
            document["totals"]["statically_resolved_producer_origin_draws"],
        )

    def test_proves_balanced_runtime_context_root(self):
        document = MODULE.build(context_root_events(), context_root_inventory())
        self.assertEqual("complete", document["status"])
        shape = document["shapes"][0]
        self.assertEqual("8240CF68", shape["context_function_address"])
        self.assertEqual("r3", shape["context_root_derivation"])
        self.assertTrue(shape["context_root_proved"])
        self.assertEqual("10000000", shape["sample_context_root_address"])
        self.assertEqual(5, shape["context_argument_varying_mask"])
        self.assertEqual(12, document["totals"]["context_origin_draws"])
        self.assertEqual(
            12,
            document["totals"]["statically_resolved_context_origin_draws"],
        )

    def test_rejects_runtime_context_root_derivation_mismatch(self):
        traced = context_root_events()
        traced[1]["sample_context_root_address"] = "10000004"
        with self.assertRaisesRegex(ValueError, "static derivation"):
            MODULE.build(traced, context_root_inventory())

    def test_fails_closed_on_context_producer_mismatch(self):
        traced = context_root_events()
        traced[-1]["indirect_producer_context_mismatches"] = "1"
        document = MODULE.build(traced, context_root_inventory())
        self.assertEqual("incomplete_fail_closed", document["status"])

    def test_rejects_producer_that_does_not_contain_owner_callsite(self):
        static = static_inventory()
        static["indirect_constructor_calls"] = [
            {
                "constructor_function_address": "82409398",
                "caller_function_address": "82409668",
                "return_address": "82409838",
            }
        ]
        static["indirect_owner_calls"] = [
            {
                "owner_function_address": "82409668",
                "caller_function_address": "8240D070",
                "return_address": "8240D1B0",
            }
        ]
        traced = events()
        traced[1].update(
            {
                "constructor_function_address": "82409398",
                "constructor_return_address": "82409838",
                "sample_constructor_arguments": "00000000," * 7 + "00000000",
                "constructor_argument_varying_mask": "00",
                "owner_function_address": "82409668",
                "owner_return_address": "8240D1B0",
                "sample_owner_arguments": "00000000," * 7 + "00000000",
                "owner_argument_varying_mask": "00",
                "producer_function_address": "829F6360",
                "producer_return_address": "829F67B0",
                "sample_producer_arguments": "00000000," * 7 + "00000000",
                "producer_argument_varying_mask": "00",
            }
        )
        with self.assertRaisesRegex(ValueError, "does not contain"):
            MODULE.build(traced, static)

    def test_rejects_owner_that_does_not_contain_constructor_callsite(self):
        static = static_inventory()
        static["indirect_constructor_calls"] = [
            {
                "constructor_function_address": "82409398",
                "caller_function": "sub_82409668",
                "caller_function_address": "82409668",
                "callsite": "82409834",
                "return_address": "82409838",
            }
        ]
        traced = events()
        traced[1].update(
            {
                "constructor_function_address": "82409398",
                "constructor_return_address": "82409838",
                "sample_constructor_arguments": "00000000," * 7 + "00000000",
                "constructor_argument_varying_mask": "00",
                "owner_function_address": "824167F8",
                "owner_return_address": "824170BC",
                "sample_owner_arguments": "00000000," * 7 + "00000000",
                "owner_argument_varying_mask": "00",
            }
        )
        with self.assertRaisesRegex(ValueError, "does not contain"):
            MODULE.build(traced, static)


if __name__ == "__main__":
    unittest.main()
