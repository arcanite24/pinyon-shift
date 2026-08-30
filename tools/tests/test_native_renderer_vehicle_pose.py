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
        owner_method_candidates="82BCC368:14,82BD2DE0:20,82BC8410:22",
        owner_method_exit_hooks="82BCCD30,82BD35B0,82BC86F0",
        owner_method_stack_capacity="8",
        owner_indirect_callsites=(
            "82BC8468,82BC84A4,82BC84DC,82BC8688,82BC86BC,82BC86E4"
        ),
        owner_indirect_target_capacity="64",
        guest_payload_read=(
            "existing_title_pose_hook_values_and_bounded_owner_vtable"
        ),
        guest_state_changed="false",
        native_upload="false",
        native_draw="false",
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
        owner_method_candidates="82BCC368:14,82BD2DE0:20,82BC8410:22",
        owner_method_exit_hooks="82BCCD30,82BD35B0,82BC86F0",
        owner_method_stack_faults="0",
        owner_indirect_observations="0",
        owner_indirect_valid_observations="0",
        owner_indirect_invalid_observations="0",
        owner_indirect_targets="0",
        owner_indirect_target_capacity="64",
        owner_indirect_target_overflow="0",
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
    return [config, summary, identity, *methods]


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


if __name__ == "__main__":
    unittest.main()
