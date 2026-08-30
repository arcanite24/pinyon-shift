import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-vehicle-pose.py"
SPEC = importlib.util.spec_from_file_location(
    "summarize_native_renderer_vehicle_pose", TOOL
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
VTABLE_METHODS = ",".join(f"{0x823E0000 + index * 8:08X}" for index in range(32))


def event(name, **values):
    return {"event": name, "session": "session-1", **values}


def fixture():
    config = event(
        MODULE.CONFIG,
        status="armed",
        hook="82BC5A3C",
        identity="title_generation,source,owner,active_slot",
        transform="exact_active_slot_position_and_forward",
        capacity="64",
        summary_limit="64",
        classification="unclassified_vehicle_pose_stream",
        player_priority_admitted="false",
        owner_vtable_method_count="32",
        owner_method_candidates=(
            "82BD2BD0:0,82BD2B58:3,82BCFDD8:7,82BCFE18:8,"
            "82BCFE58:9,82BC1D90:12,82BBDD38:13,82BCC368:14,"
            "82BCD780:15,82BCD9B0:16,82BD0548:17,82BD05D8:18,"
            "82BD0648:19,82BD2DE0:20,82BBA9C0:21,82BC8410:22,"
            "82BB94D8:23,82BBC1B0:25,82BD0918:27"
        ),
        owner_method_exit_hooks=(
            "82BD2C20,82BD2BC0,82BCFE10,82BCFE50,82BCFE70,"
            "82BC1DC0,82BBDE40,82BCCD30,82BCD9A8,82BCDA90,"
            "82BD05D0,82BD0640,82BD06B0,82BD35B0,82BBAB28,"
            "82BC86F0,82BB9568,82BBC2C8,82BD0968"
        ),
        owner_method_stack_capacity="32",
        owner_indirect_callsites=(
            "82BC8468,82BC84A4,82BC84DC,82BC8688,82BC86BC,82BC86E4"
        ),
        owner_indirect_target_capacity="64",
        draw_correlation_capacity="1024",
        identity_address_capacity="512",
        draw_correlation=(
            "exact_backend_signature_and_provenance_argument_to_vehicle_address"
        ),
        title_provenance_requested="true",
        object_scan_enabled="false",
        object_scan_word_count="128",
        object_scan_cache_capacity="16384",
        object_correlation_capacity="2048",
        object_correlation="sampled_one_hop_pointer_to_vehicle_address",
        targeted_render_context_arguments="824365B0:r7,r8",
        targeted_render_context_static_contract=(
            "r7_vtable_slot_8_and_r8_vector_source"
        ),
        render_context_callee_contract=(
            "824365B0:r6_le_2,r7_vtable_slot_8,r8_32_byte_vector"
        ),
        render_context_dispatcher_hook="82436468:r8,r9,r10,r12",
        render_context_callee_profile_capacity="32",
        vehicle_matrix_caller_contract="8240E7B0:r6_4x4_matrix,r12",
        vehicle_matrix_layouts=(
            "row_major_translation_row3_forward_row2,"
            "column_major_translation_column3_forward_column2"
        ),
        vehicle_matrix_forward_signs="positive,negative",
        vehicle_matrix_match_thresholds=(
            "position_delta_squared<=0.25,forward_delta_squared<=0.04"
        ),
        vehicle_matrix_correlation_capacity="512",
        typed_render_item_hook="8240EC18:r11_descriptor,r31_root",
        typed_render_item_contract=(
            "eligible_root_child_and_descriptor_through_offset_244"
        ),
        typed_render_item_profile_capacity="32",
        typed_descriptor_word_count="62",
        typed_descriptor_correlation_capacity="512",
        composed_matrix_hook="8240EB5C:r22_object_matrix,r5_output_matrix",
        composed_matrix_contract=(
            "8240E7B0_live_r7_input_and_64_byte_payload_to_82435E78"
        ),
        composed_matrix_sources=(
            "object_input_matrix,composed_upload_matrix"
        ),
        composed_matrix_correlation_capacity="1024",
        guest_payload_read=(
            "existing_pose_values,bounded_owner_vtable,typed_context_entry,"
            "typed_4x4_caller_matrix,typed_render_item_descriptor,"
            "object_and_composed_4x4_matrices"
        ),
        guest_state_changed="false",
        native_upload="false",
        native_draw="false",
        xenos_authority="true",
        suppression_allowed="false",
    )
    title_provenance_config = event(
        MODULE.TITLE_PROVENANCE_CONFIG,
        status="armed",
        guest_state_changed="false",
        control_flow_changed="false",
        xenos_authority="true",
        suppression_allowed="false",
    )
    summary = event(
        MODULE.SUMMARY,
        status="complete",
        observations="10",
        valid_observations="10",
        invalid_observations="0",
        identities="1",
        capacity="64",
        summary_limit="64",
        overflow="0",
        accounting_complete="true",
        identity="title_generation,source,owner,active_slot",
        transform="exact_active_slot_position_and_forward",
        classification="vehicle_instance_semantic_seed",
        player_priority_admitted="false",
        owner_vtable_method_count="32",
        owner_method_candidates=(
            "82BD2BD0:0,82BD2B58:3,82BCFDD8:7,82BCFE18:8,"
            "82BCFE58:9,82BC1D90:12,82BBDD38:13,82BCC368:14,"
            "82BCD780:15,82BCD9B0:16,82BD0548:17,82BD05D8:18,"
            "82BD0648:19,82BD2DE0:20,82BBA9C0:21,82BC8410:22,"
            "82BB94D8:23,82BBC1B0:25,82BD0918:27"
        ),
        owner_method_exit_hooks=(
            "82BD2C20,82BD2BC0,82BCFE10,82BCFE50,82BCFE70,"
            "82BC1DC0,82BBDE40,82BCCD30,82BCD9A8,82BCDA90,"
            "82BD05D0,82BD0640,82BD06B0,82BD35B0,82BBAB28,"
            "82BC86F0,82BB9568,82BBC2C8,82BD0968"
        ),
        owner_method_stack_faults="0",
        owner_indirect_observations="0",
        owner_indirect_valid_observations="0",
        owner_indirect_invalid_observations="0",
        owner_indirect_targets="0",
        owner_indirect_target_capacity="64",
        owner_indirect_target_overflow="0",
        draws_examined="4",
        direct_draws_examined="2",
        indirect_draws_examined="4",
        draw_argument_probes="32",
        direct_argument_probes="8",
        semantic_argument_probes="0",
        indirect_argument_probes="24",
        draw_argument_matches="0",
        draw_correlations="0",
        draw_correlation_capacity="1024",
        draw_correlation_overflow="0",
        identity_addresses="3",
        identity_address_capacity="512",
        identity_address_overflow="0",
        object_scan_enabled="false",
        object_scan_requests="0",
        object_scans="0",
        object_scan_words="0",
        object_scan_word_count="128",
        object_scan_cache_entries="0",
        object_scan_cache_capacity="16384",
        object_scan_cache_overflow="0",
        object_argument_matches="0",
        object_correlations="0",
        object_correlation_capacity="2048",
        render_context_callee_profile_capacity="32",
        object_correlation_overflow="0",
        targeted_render_context_r7_scan_requests="0",
        targeted_render_context_r7_scans="0",
        targeted_render_context_r8_scan_requests="0",
        targeted_render_context_r8_scans="0",
        render_context_callee_observations="3",
        render_context_callee_eligible_observations="2",
        render_context_callee_ineligible_observations="1",
        render_context_callee_valid_observations="2",
        render_context_callee_invalid_root="0",
        render_context_callee_invalid_vtable="0",
        render_context_callee_invalid_vector="0",
        render_context_callee_profiles="1",
        render_context_callee_profile_overflow="0",
        render_context_dispatcher_observations="4",
        render_context_dispatcher_eligible_observations="3",
        render_context_dispatcher_matches="3",
        render_context_dispatcher_mismatches="0",
        vehicle_matrix_caller_observations="1",
        vehicle_matrix_caller_valid_observations="1",
        vehicle_matrix_caller_invalid_range="0",
        vehicle_matrix_caller_non_finite="0",
        vehicle_matrix_caller_accounting_complete="true",
        vehicle_matrix_identity_comparisons="4",
        vehicle_matrix_candidate_observations="4",
        vehicle_matrix_routes_without_identity="0",
        vehicle_matrix_route_accounting_complete="true",
        vehicle_matrix_tight_matches="1",
        vehicle_matrix_correlations="4",
        vehicle_matrix_correlation_capacity="512",
        vehicle_matrix_correlation_overflow="0",
        typed_render_item_observations="2",
        typed_render_item_valid_observations="2",
        typed_render_item_invalid_root="0",
        typed_render_item_invalid_child="0",
        typed_render_item_invalid_descriptor="0",
        typed_render_item_accounting_complete="true",
        typed_render_item_profiles="1",
        typed_render_item_profile_capacity="32",
        typed_render_item_profile_overflow="0",
        typed_descriptor_scan_words="124",
        typed_descriptor_word_count="62",
        typed_descriptor_matches="1",
        typed_descriptor_correlations="1",
        typed_descriptor_correlation_capacity="512",
        typed_descriptor_correlation_overflow="0",
        composed_matrix_observations="1",
        composed_matrix_valid_pairs="1",
        composed_matrix_invalid_object_range="0",
        composed_matrix_invalid_output_range="0",
        composed_matrix_object_non_finite="0",
        composed_matrix_output_non_finite="0",
        composed_matrix_accounting_complete="true",
        composed_matrix_identity_comparisons="8",
        composed_matrix_candidate_observations="8",
        composed_matrix_routes_without_identity="0",
        composed_matrix_route_accounting_complete="true",
        composed_matrix_tight_matches="1",
        composed_matrix_correlations="8",
        composed_matrix_correlation_capacity="1024",
        composed_matrix_correlation_overflow="0",
        title_provenance_requested="true",
        draw_provenance_coverage_complete="true",
        guest_state_changed="false",
        native_upload="false",
        native_draw="false",
        xenos_authority="true",
        suppression_allowed="false",
    )
    identity = event(
        MODULE.IDENTITY,
        generation="00000001",
        source="A0001000",
        owner="A0002000",
        owner_vtable="82001000",
        owner_vtable_hash="1234567890ABCDEF",
        owner_vtable_methods=VTABLE_METHODS,
        owner_vtable_mismatches="0",
        slot="2",
        position_address="A0003000",
        forward_address="A0003040",
        observations="10",
        first_frame="100",
        last_frame="109",
        position_changes="9",
        forward_changes="4",
        stabilized_observations="0",
        address_mismatches="0",
        maximum_position_delta_squared="2.5",
        classification="vehicle_instance_semantic_seed",
        player_priority_admitted="false",
        native_draw="false",
        xenos_authority="true",
        suppression_allowed="false",
    )
    methods = []
    for method, (slot, exit_address) in MODULE.OWNER_METHOD_CANDIDATES.items():
        methods.append(
            event(
                MODULE.OWNER_METHOD,
                status="complete",
                method_address=method,
                exit_address=exit_address,
                vtable_slot=str(slot),
                calls="0",
                matched_owner_calls="0",
                exits="0",
                direct_draw_origins="0",
                backend_draw_matches="0",
                vehicle_render_method_candidate_proved="false",
                player_vehicle_identity_proved="false",
                vehicle_draw_identity_proved="false",
                guest_state_changed="false",
                native_draw="false",
                xenos_authority="true",
                suppression_allowed="false",
            )
        )
    render_context_callee = event(
        MODULE.RENDER_CONTEXT_CALLEE,
        function_address="824365B0",
        mode_contract="r6_le_2",
        root_address="AB1A7BE4",
        root_vtable="82143000",
        slot_8_target="82439000",
        root_field_4="40400000",
        root_field_16="703FF2A0",
        vector_address="703FF2A0",
        dispatcher_return_address="82DEFA2C",
        vector_hash="1234567890ABCDEF",
        observations="2",
        root_address_changes="1",
        root_field_4_changes="0",
        root_field_16_changes="1",
        vector_address_changes="1",
        vector_hash_changes="1",
        classification="typed_vehicle_render_context_callee_seed",
        vehicle_draw_identity_proved="false",
        guest_state_changed="false",
        native_draw="false",
        xenos_authority="true",
        suppression_allowed="false",
    )
    matrix_correlations = []
    for layout in sorted(MODULE.VEHICLE_MATRIX_LAYOUTS):
        for forward_sign in sorted(MODULE.VEHICLE_MATRIX_FORWARD_SIGNS):
            tight_match = (
                layout == "row_major_translation_row3_forward_row2"
                and forward_sign == "positive"
            )
            matrix_correlations.append(
                event(
                    MODULE.VEHICLE_MATRIX_CORRELATION,
                    function_address="8240E7B0",
                    caller_return_address="8240F004",
                    matrix_layout=layout,
                    forward_sign=forward_sign,
                    identity_generation="00000001",
                    identity_owner="A0002000",
                    identity_slot="2",
                    observations="1",
                    tight_matches="1" if tight_match else "0",
                    first_frame="104",
                    last_frame="104",
                    matrix_address_changes="0",
                    matrix_hash_changes="0",
                    last_matrix_address="703FF000",
                    last_matrix_hash="1234567890ABCDEF",
                    best_matrix_address="703FF000",
                    best_matrix_hash="1234567890ABCDEF",
                    best_position_delta_squared=(
                        "0.01" if tight_match else "100.0"
                    ),
                    best_forward_delta_squared=(
                        "0.001" if tight_match else "1.0"
                    ),
                    best_normalized_score=(
                        "0.065" if tight_match else "425.0"
                    ),
                    classification=(
                        "vehicle_render_matrix_correlation_candidate"
                    ),
                    vehicle_render_transform_candidate_proved=(
                        "true" if tight_match else "false"
                    ),
                    vehicle_draw_identity_proved="false",
                    guest_state_changed="false",
                    native_draw="false",
                    xenos_authority="true",
                    suppression_allowed="false",
                )
            )
    composed_matrix_correlations = []
    for source in sorted(MODULE.VEHICLE_COMPOSED_MATRIX_SOURCES):
        for layout in sorted(MODULE.VEHICLE_MATRIX_LAYOUTS):
            for forward_sign in sorted(MODULE.VEHICLE_MATRIX_FORWARD_SIGNS):
                tight_match = (
                    source == "composed_upload_matrix"
                    and layout == "row_major_translation_row3_forward_row2"
                    and forward_sign == "positive"
                )
                composed_matrix_correlations.append(
                    event(
                        MODULE.VEHICLE_COMPOSED_MATRIX_CORRELATION,
                        function_address="8240E7B0",
                        hook_address="8240EB5C",
                        callee_address="82435E78",
                        matrix_source=source,
                        matrix_layout=layout,
                        forward_sign=forward_sign,
                        identity_generation="00000001",
                        identity_owner="A0002000",
                        identity_slot="2",
                        observations="1",
                        tight_matches="1" if tight_match else "0",
                        first_frame="104",
                        last_frame="104",
                        matrix_address_changes="0",
                        matrix_hash_changes="0",
                        last_matrix_address=(
                            "703FE000"
                            if source == "object_input_matrix"
                            else "703FF000"
                        ),
                        last_matrix_hash="1234567890ABCDEF",
                        best_matrix_address=(
                            "703FE000"
                            if source == "object_input_matrix"
                            else "703FF000"
                        ),
                        best_matrix_hash="1234567890ABCDEF",
                        best_position_delta_squared=(
                            "0.01" if tight_match else "100.0"
                        ),
                        best_forward_delta_squared=(
                            "0.001" if tight_match else "1.0"
                        ),
                        best_normalized_score=(
                            "0.065" if tight_match else "425.0"
                        ),
                        classification=(
                            "vehicle_composed_matrix_correlation_candidate"
                        ),
                        vehicle_render_transform_candidate_proved=(
                            "true" if tight_match else "false"
                        ),
                        vehicle_draw_identity_proved="false",
                        guest_state_changed="false",
                        native_upload="false",
                        native_draw="false",
                        xenos_authority="true",
                        suppression_allowed="false",
                    )
                )
    typed_render_item_profile = event(
        MODULE.TYPED_RENDER_ITEM_PROFILE,
        function_address="8240E7B0",
        hook_address="8240EC18",
        root_address="AB1A7BE4",
        root_vtable="82143000",
        child_address="AB1A8000",
        child_vtable="82144000",
        descriptor_address="AB1A8080",
        descriptor_type="19",
        descriptor_payload="AB1A9000",
        descriptor_flag="1",
        descriptor_hash="1234567890ABCDEF",
        observations="2",
        root_address_changes="0",
        child_address_changes="0",
        descriptor_address_changes="1",
        descriptor_hash_changes="1",
        classification="typed_render_item_descriptor_profile",
        vehicle_draw_identity_proved="false",
        guest_state_changed="false",
        native_draw="false",
        xenos_authority="true",
        suppression_allowed="false",
    )
    typed_descriptor_correlation = event(
        MODULE.TYPED_DESCRIPTOR_CORRELATION,
        function_address="8240E7B0",
        hook_address="8240EC18",
        root_vtable="82143000",
        child_vtable="82144000",
        descriptor_type="19",
        pointer_offset="40",
        identity_field="owner",
        matched_address="A0002000",
        identity_generation="00000001",
        identity_owner="A0002000",
        identity_slot="2",
        observations="1",
        first_frame="104",
        last_frame="104",
        classification="typed_vehicle_descriptor_correlation_candidate",
        vehicle_draw_identity_proved="false",
        guest_state_changed="false",
        native_draw="false",
        xenos_authority="true",
        suppression_allowed="false",
    )
    return [
        config,
        summary,
        identity,
        *methods,
        render_context_callee,
        *matrix_correlations,
        *composed_matrix_correlations,
        typed_render_item_profile,
        typed_descriptor_correlation,
        title_provenance_config,
    ]


class VehiclePoseSummaryTests(unittest.TestCase):
    def test_runtime_hook_feeds_read_only_renderer_discovery(self):
        runtime = (ROOT / "src/pinyon_shift_runtime_hooks.cpp").read_text(
            encoding="utf-8"
        )
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        header = (ROOT / "src/native_renderer/graphics_hooks.h").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        capture = (ROOT / "tools/capture-native-renderer-census.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("struct VehiclePoseObservation", header)
        self.assertIn("ObserveVehiclePose", runtime)
        self.assertIn(".presentation_stabilized = suppressed", runtime)
        self.assertIn("ConfigureVehicleDiscovery(census_requested, memory)", hooks)
        self.assertIn("EmitVehicleDiscoverySummary()", hooks)
        self.assertIn('"vehicle_instance_semantic_seed"', hooks)
        self.assertIn('{"native_draw", "false"}', hooks)
        self.assertIn('{"xenos_authority", "true"}', hooks)
        self.assertIn('{"suppression_allowed", "false"}', hooks)
        self.assertIn("BeginVehicleOwnerMethod", hooks)
        self.assertIn("EndVehicleOwnerMethod", hooks)
        self.assertIn(
            '"native_renderer.discovery.vehicle_owner_method"', hooks
        )
        self.assertIn("ObserveVehicleOwnerIndirectCall", hooks)
        self.assertIn(
            '"native_renderer.discovery.vehicle_owner_indirect_target"',
            hooks,
        )
        self.assertIn("ObserveVehicleDrawArgumentCorrelations", hooks)
        self.assertIn(
            '"native_renderer.discovery.vehicle_draw_argument_correlation"',
            hooks,
        )
        self.assertIn("ScanVehicleObjectProbeLocked", hooks)
        self.assertIn(
            '"native_renderer.discovery.vehicle_draw_object_correlation"',
            hooks,
        )
        self.assertNotIn("ScanVehicleDescriptorEdgeLocked", hooks)
        self.assertNotIn("VehicleDescriptorCorrelationEntry", hooks)
        self.assertIn(
            "probe.function_address == kVehicleRenderContextFunction",
            hooks,
        )
        self.assertIn(
            "if (IsTargetedVehicleRenderContextProbe(probe)) {\n"
            "    return true;",
            hooks,
        )
        self.assertIn("ObserveVehicleRenderContextCallee", hooks)
        self.assertIn(
            "PinyonShiftObserveVehicleRenderContextDispatcherEntry", hooks
        )
        self.assertIn(
            '"native_renderer.discovery.vehicle_render_context_callee"',
            hooks,
        )
        self.assertIn("ObserveVehicleMatrixCaller", hooks)
        self.assertIn(
            '"native_renderer.discovery.vehicle_matrix_correlation"', hooks
        )
        self.assertIn("ObserveVehicleTypedRenderItem", hooks)
        self.assertIn(
            '"native_renderer.discovery.vehicle_typed_render_item_profile"',
            hooks,
        )
        self.assertIn(
            '"native_renderer.discovery.vehicle_typed_descriptor_correlation"',
            hooks,
        )
        self.assertIn("ObserveVehicleComposedMatrix", hooks)
        self.assertIn(
            '"native_renderer.discovery.vehicle_composed_matrix_correlation"',
            hooks,
        )
        self.assertIn("[switch]$VehicleDrawCorrelation", capture)
        self.assertEqual(1, analysis.count("address = 0x8240E7B4"))
        self.assertEqual(1, analysis.count("address = 0x8240EC18"))
        self.assertEqual(1, analysis.count("address = 0x8240EB5C"))
        self.assertEqual(1, analysis.count("address = 0x8243646C"))
        for method, (_, exit_address) in MODULE.OWNER_METHOD_CANDIDATES.items():
            self.assertEqual(1, analysis.count(f"address = 0x{method}"))
            self.assertEqual(1, analysis.count(f"address = 0x{exit_address}"))
            self.assertEqual(
                1,
                hooks.count(
                    f"PINYON_SHIFT_VEHICLE_OWNER_METHOD_HOOKS({method})"
                ),
            )
        for address in (
            "82BC8468",
            "82BC84A4",
            "82BC84DC",
            "82BC8688",
            "82BC86BC",
            "82BC86E4",
        ):
            self.assertEqual(1, analysis.count(f"address = 0x{address}"))
            self.assertEqual(
                1,
                analysis.count(
                    f'name = "PinyonShiftObserveVehicleOwnerIndirect{address}"'
                ),
            )

    def test_qualifies_exact_vehicle_instance_seed(self):
        document = MODULE.build(fixture())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["vehicle_instance_semantic_seed_proved"]
        )
        self.assertFalse(
            document["qualification"]["player_vehicle_identity_proved"]
        )
        self.assertTrue(
            document["qualification"]["vehicle_owner_class_seed_proved"]
        )
        self.assertEqual(1, len(document["owner_classes"]))
        self.assertEqual(1, document["owner_classes"][0]["identity_count"])
        self.assertFalse(
            document["qualification"]["native_vehicle_rendering_admitted"]
        )
        self.assertTrue(
            document["coverage"]["draw_provenance_coverage_complete"]
        )
        self.assertTrue(
            document["qualification"][
                "render_context_callee_contract_proved"
            ]
        )
        self.assertEqual(1, len(document["render_context_callees"]))
        self.assertEqual(
            "82439000",
            document["render_context_callees"][0]["slot_8_target"],
        )
        self.assertTrue(
            document["qualification"][
                "vehicle_render_matrix_candidate_proved"
            ]
        )
        self.assertEqual(4, len(document["vehicle_matrix_correlations"]))
        self.assertTrue(
            document["qualification"]["typed_render_item_contract_proved"]
        )
        self.assertTrue(
            document["qualification"][
                "typed_vehicle_descriptor_candidate_proved"
            ]
        )
        self.assertEqual(1, len(document["typed_render_item_profiles"]))
        self.assertEqual(1, len(document["typed_descriptor_correlations"]))
        self.assertTrue(
            document["qualification"][
                "vehicle_composed_matrix_contract_proved"
            ]
        )
        self.assertTrue(
            document["qualification"][
                "vehicle_composed_matrix_candidate_proved"
            ]
        )
        self.assertEqual(8, len(document["composed_matrix_correlations"]))

    def test_rejects_composed_matrix_accounting_or_overflow(self):
        events = fixture()
        events[1]["composed_matrix_valid_pairs"] = "0"
        document = MODULE.build(events)
        self.assertIn(
            "vehicle composed matrix accounting drifted", document["failures"]
        )

        events = fixture()
        events[1]["composed_matrix_correlation_overflow"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "vehicle composed matrix correlation table overflowed",
            document["failures"],
        )

    def test_rejects_typed_render_item_accounting_or_overflow(self):
        events = fixture()
        events[1]["typed_render_item_valid_observations"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "typed render-item accounting drifted", document["failures"]
        )

        events = fixture()
        events[1]["typed_render_item_profile_overflow"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "typed render-item profile table overflowed",
            document["failures"],
        )

        events = fixture()
        events[1]["typed_descriptor_correlation_overflow"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "typed descriptor correlation table overflowed",
            document["failures"],
        )

    def test_rejects_vehicle_matrix_accounting_or_overflow(self):
        events = fixture()
        events[1]["vehicle_matrix_caller_valid_observations"] = "0"
        document = MODULE.build(events)
        self.assertIn(
            "vehicle matrix caller accounting drifted", document["failures"]
        )

        events = fixture()
        events[1]["vehicle_matrix_correlation_overflow"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "vehicle matrix correlation table overflowed",
            document["failures"],
        )

    def test_rejects_invalid_or_overflowed_observations(self):
        events = fixture()
        events[1]["invalid_observations"] = "1"
        events[1]["valid_observations"] = "9"
        events[2]["observations"] = "9"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "invalid vehicle-pose observations occurred", document["failures"]
        )

        events = fixture()
        events[1]["overflow"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "vehicle identity table overflowed", document["failures"]
        )

    def test_rejects_address_or_safety_drift(self):
        events = fixture()
        events[2]["address_mismatches"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "vehicle transform addresses changed", document["failures"]
        )

        events = fixture()
        events[2]["owner_vtable_mismatches"] = "1"
        document = MODULE.build(events)
        self.assertIn("vehicle owner vtable changed", document["failures"])

        unsafe = fixture()
        unsafe[2]["suppression_allowed"] = "true"
        with self.assertRaisesRegex(ValueError, "safety boundary"):
            MODULE.build(unsafe)

    def test_rejects_duplicate_identity(self):
        events = fixture()
        duplicate = copy.deepcopy(events[2])
        events[1]["identities"] = "2"
        events.append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE.build(events)

    def test_proves_only_a_bounded_render_method_candidate(self):
        events = fixture()
        candidate = events[3]
        candidate["calls"] = "5"
        candidate["matched_owner_calls"] = "4"
        candidate["exits"] = "5"
        candidate["direct_draw_origins"] = "3"
        candidate["backend_draw_matches"] = "3"
        candidate["vehicle_render_method_candidate_proved"] = "true"
        document = MODULE.build(events)
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"][
                "vehicle_render_method_candidate_proved"
            ]
        )
        self.assertFalse(
            document["qualification"]["vehicle_draw_identity_proved"]
        )
        self.assertFalse(
            document["qualification"]["native_vehicle_rendering_admitted"]
        )

    def test_qualifies_exact_downstream_component_dispatches(self):
        events = fixture()
        events[1]["owner_indirect_observations"] = "3"
        events[1]["owner_indirect_valid_observations"] = "3"
        events[1]["owner_indirect_targets"] = "1"
        events.append(
            event(
                MODULE.OWNER_INDIRECT_TARGET,
                method_address="82BC8410",
                callsite_address="82BC8468",
                target_address="823E1000",
                object_address="A0004000",
                object_vtable="82002000",
                observations="3",
                first_frame="102",
                last_frame="104",
                classification="vehicle_owner_component_dispatch_seed",
                vehicle_render_method_identity_proved="false",
                vehicle_draw_identity_proved="false",
                guest_state_changed="false",
                native_draw="false",
                xenos_authority="true",
                suppression_allowed="false",
            )
        )
        document = MODULE.build(events)
        self.assertEqual("complete", document["status"])
        self.assertEqual(1, len(document["indirect_targets"]))
        self.assertEqual(
            "823E1000", document["indirect_targets"][0]["target_address"]
        )
        self.assertFalse(
            document["qualification"]["vehicle_draw_identity_proved"]
        )

    def test_qualifies_draw_argument_match_as_candidate_only(self):
        events = fixture()
        events[1]["draw_argument_matches"] = "3"
        events[1]["draw_correlations"] = "1"
        events.append(
            event(
                MODULE.DRAW_ARGUMENT_CORRELATION,
                backend_signature="0123456789ABCDEF",
                provenance_layer="indirect_owner_arguments",
                function_address="82409668",
                return_address="8240D1B0",
                argument_index="3",
                identity_field="owner",
                matched_address="A0002000",
                identity_generation="00000001",
                identity_owner="A0002000",
                identity_slot="2",
                observations="3",
                first_frame="102",
                last_frame="104",
                classification="vehicle_draw_argument_correlation_candidate",
                vehicle_draw_identity_proved="false",
                guest_state_changed="false",
                native_draw="false",
                xenos_authority="true",
                suppression_allowed="false",
            )
        )
        document = MODULE.build(events)
        self.assertEqual("complete", document["status"])
        self.assertEqual(1, len(document["draw_argument_correlations"]))
        self.assertTrue(
            document["qualification"][
                "vehicle_draw_argument_candidate_proved"
            ]
        )
        self.assertFalse(
            document["qualification"]["vehicle_draw_identity_proved"]
        )
        self.assertFalse(
            document["qualification"]["native_vehicle_rendering_admitted"]
        )

    def test_rejects_draw_argument_correlation_overflow(self):
        events = fixture()
        events[1]["draw_correlation_overflow"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "vehicle draw correlation table overflowed", document["failures"]
        )

    def test_rejects_evidence_from_retired_one_hop_object_scan(self):
        events = fixture()
        events[1]["object_argument_matches"] = "2"
        events[1]["object_correlations"] = "1"
        events.append(
            event(
                MODULE.DRAW_OBJECT_CORRELATION,
                backend_signature="0123456789ABCDEF",
                provenance_layer="semantic_receiver",
                function_address="82417BC0",
                return_address="00000000",
                argument_index="8",
                container_address="A0005000",
                pointer_offset="64",
                identity_field="owner",
                matched_address="A0002000",
                identity_generation="00000001",
                identity_owner="A0002000",
                identity_slot="2",
                observations="2",
                first_frame="102",
                last_frame="104",
                relationship_depth="1",
                classification="vehicle_draw_object_correlation_candidate",
                vehicle_draw_identity_proved="false",
                guest_state_changed="false",
                native_draw="false",
                xenos_authority="true",
                suppression_allowed="false",
            )
        )
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertEqual(1, len(document["draw_object_correlations"]))
        self.assertIn(
            "retired vehicle object scan emitted evidence",
            document["failures"],
        )
        self.assertFalse(
            document["qualification"][
                "vehicle_draw_object_candidate_proved"
            ]
        )
        self.assertFalse(
            document["qualification"]["vehicle_draw_identity_proved"]
        )

    def test_rejects_object_scan_cache_overflow(self):
        events = fixture()
        events[1]["object_scan_cache_overflow"] = "1"
        document = MODULE.build(events)
        self.assertIn(
            "vehicle object scan cache overflowed", document["failures"]
        )

    def test_does_not_promote_candidate_without_direct_coverage(self):
        events = fixture()
        events[0]["title_provenance_requested"] = "false"
        events[1]["title_provenance_requested"] = "false"
        events[-1]["status"] = "disabled"
        events[1]["draw_provenance_coverage_complete"] = "false"
        events[1]["direct_draws_examined"] = "0"
        events[1]["direct_argument_probes"] = "0"
        events[1]["draw_argument_probes"] = "24"
        events[1]["draw_argument_matches"] = "1"
        events[1]["draw_correlations"] = "1"
        events.append(
            event(
                MODULE.DRAW_ARGUMENT_CORRELATION,
                backend_signature="0123456789ABCDEF",
                provenance_layer="indirect_owner_arguments",
                function_address="82409668",
                return_address="8240D1B0",
                argument_index="3",
                identity_field="owner",
                matched_address="A0002000",
                identity_generation="00000001",
                identity_owner="A0002000",
                identity_slot="2",
                observations="1",
                first_frame="102",
                last_frame="102",
                classification="vehicle_draw_argument_correlation_candidate",
                vehicle_draw_identity_proved="false",
                guest_state_changed="false",
                native_draw="false",
                xenos_authority="true",
                suppression_allowed="false",
            )
        )
        document = MODULE.build(events)
        self.assertEqual("complete", document["status"])
        self.assertFalse(
            document["coverage"]["draw_provenance_coverage_complete"]
        )
        self.assertFalse(
            document["qualification"][
                "vehicle_draw_argument_candidate_proved"
            ]
        )


if __name__ == "__main__":
    unittest.main()
