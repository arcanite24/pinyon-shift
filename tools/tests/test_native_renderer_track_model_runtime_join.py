import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-track-model-runtime-join.py"
SPEC = importlib.util.spec_from_file_location("track_model_runtime_join", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
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


def fixture(shared=3):
    config = event(
        MODULE.CONFIG,
        status="armed",
        entry_hook="8240EC80",
        exit_hook="8240ECAC",
        nested_dispatch="82436468",
        instance_vtable="820019CC",
        model_vtable="82001D74",
        instance_to_model="root_plus_4",
        model_to_descriptor="child_plus_48_then_plus_128",
        descriptor_type="21",
        descriptor_flag="1",
        join="synchronous_scope_to_procedural_model_submission",
        shared_identity="descriptor_payload_or_object_address_exact_equality",
        world_resource_vtables=(
            "820016B4,8200143C,82001474,82144CF8,82144D7C,82144DE0,"
            "82144E64"
        ),
        world_resource_graph=(
            "direct_child_or_descriptor_pointer_with_exact_rtti_vtable"
        ),
        world_resource_shared_identity=(
            "exact_address_equality_to_submission_objects_or_resources"
        ),
        world_resource_graph_cache_capacity="1024",
        world_resource_reference_capacity="16",
        guest_payload_read=(
            "bounded_320_bytes_plus_direct_vtable_words_per_cache_miss"
        ),
        **safety(),
    )
    relations = {key: "0" for key in MODULE.RELATIONS}
    world_relations = {key: "0" for key in MODULE.WORLD_RELATIONS}
    shared_world_relations = {
        key: "0" for key in MODULE.SHARED_WORLD_RELATIONS
    }
    if shared:
        relations["shared_descriptor_payload_bound_resource"] = str(shared)
        world_relations["world_track_mesh"] = "6"
        shared_world_relations["shared_world_track_mesh"] = str(shared)
    summary = event(
        MODULE.SUMMARY,
        status="complete",
        scope_entries="10",
        scope_exits="10",
        exact_scopes="10",
        invalid_root="0",
        invalid_child="0",
        invalid_descriptor="0",
        contract_mismatches="0",
        joined_scopes="8",
        unjoined_scopes="2",
        submission_joins="12",
        shared_identity_joins=str(shared),
        world_resource_graph_scopes="6" if shared else "0",
        world_resource_graph_cache_hits="8",
        world_resource_graph_cache_misses="2",
        world_resource_graph_reference_overflow="0",
        world_resource_shared_identity_joins=str(shared),
        scope_overlaps="0",
        exit_without_entry="0",
        accounting_complete="true",
        qualification_complete="true",
        classification="exact_unified_track_render_model_nested_submission_join",
        **relations,
        **world_relations,
        **shared_world_relations,
        **safety(),
    )
    return [config, summary]


class TrackModelRuntimeJoinTests(unittest.TestCase):
    def test_qualifies_scope_and_shared_identity(self):
        document = MODULE.build(fixture())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"][
                "track_render_model_scope_to_submission_proved"
            ]
        )
        self.assertTrue(
            document["qualification"][
                "shared_object_or_resource_identity_proved"
            ]
        )
        self.assertTrue(
            document["qualification"][
                "track_world_resource_to_submission_identity_proved"
            ]
        )

    def test_qualifies_scope_without_claiming_shared_identity(self):
        document = MODULE.build(fixture(shared=0))
        self.assertEqual("complete", document["status"])
        self.assertFalse(
            document["qualification"][
                "shared_object_or_resource_identity_proved"
            ]
        )
        self.assertFalse(
            document["qualification"][
                "track_world_resource_graph_identity_proved"
            ]
        )

    def test_rejects_unjoined_scopes(self):
        events = copy.deepcopy(fixture())
        summary = events[-1]
        summary.update(
            status="incomplete",
            joined_scopes="0",
            unjoined_scopes="10",
            submission_joins="0",
            shared_identity_joins="0",
            shared_descriptor_payload_bound_resource="0",
            world_resource_graph_scopes="0",
            world_resource_shared_identity_joins="0",
            world_track_mesh="0",
            shared_world_track_mesh="0",
            qualification_complete="false",
        )
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "no exact scope joined a procedural-model submission",
            document["failures"],
        )

    def test_rejects_scope_fault(self):
        events = copy.deepcopy(fixture())
        events[-1].update(
            status="incomplete",
            accounting_complete="false",
            qualification_complete="false",
            scope_overlaps="1",
        )
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn("scope_overlaps is nonzero", document["failures"])

    def test_source_contract_has_exact_balanced_hooks(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        self.assertIn("kTrackRenderModelInstanceUnifiedVtable = 0x820019CC", hooks)
        self.assertIn("kTrackRenderModelUnifiedVtable = 0x82001D74", hooks)
        self.assertIn("BeginTrackRenderModelDispatch", hooks)
        self.assertIn("EndTrackRenderModelDispatch", hooks)
        self.assertIn("address = 0x8240EC80", analysis)
        self.assertIn("address = 0x8240ECAC", analysis)


if __name__ == "__main__":
    unittest.main()
