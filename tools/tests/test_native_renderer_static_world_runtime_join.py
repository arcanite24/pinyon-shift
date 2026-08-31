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
            "draw_emitter": "82416380",
            "packet_hooks": "82416260,824162F4",
            "join": "synchronous_scope_to_physical_pm4_prepared_draw",
            "guest_payload_read": "two_host_mapped_u32_fields_per_scope",
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
        accounting_complete="true",
        qualification_complete="true",
        classification="live_simple_model_resource_to_pm4_prepared_draw",
        **safety(),
    )
    return [config, summary]


class StaticWorldRuntimeJoinTests(unittest.TestCase):
    def test_qualifies_exact_scope_to_prepared_draw(self):
        document = MODULE.build(
            static_ingress(), static_lifetime(), static_resource(), fixture()
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
            static_ingress(), static_lifetime(), static_resource(), events
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn("unprepared_matches is nonzero", document["failures"])

    def test_rejects_scope_accounting_fault(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            scope_exits="9",
            accounting_complete="false",
            qualification_complete="false",
        )
        document = MODULE.build(
            static_ingress(), static_lifetime(), static_resource(), events
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
            MODULE.build(ingress, static_lifetime(), static_resource(), fixture())

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
            static_ingress(), static_lifetime(), static_resource(), events
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
            static_ingress(), static_lifetime(), static_resource(), events
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
            static_ingress(), static_lifetime(), static_resource(), events
        )
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "resource_registration_unregistered is nonzero",
            document["failures"],
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


if __name__ == "__main__":
    unittest.main()
