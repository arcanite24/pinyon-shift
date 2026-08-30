import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/inventory-native-renderer-vehicle-vtables.py"
SPEC = importlib.util.spec_from_file_location(
    "inventory_native_renderer_vehicle_vtables", TOOL
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VehicleVtableInventoryTests(unittest.TestCase):
    def report(self):
        methods = ["00000000"] * 32
        methods[3] = "823E1000"
        methods[7] = "823E2000"
        return {
            "schema": "pinyon-shift.native-renderer-vehicle-pose.v1",
            "session": "session-1",
            "status": "complete",
            "qualification": {
                "vehicle_owner_class_seed_proved": True,
                "player_vehicle_identity_proved": False,
            },
            "owner_classes": [
                {
                    "owner_vtable": "82001000",
                    "owner_vtable_hash": "1234567890ABCDEF",
                    "owner_vtable_methods": methods,
                    "identity_count": 4,
                }
            ],
        }

    def test_resolves_exact_generated_methods_without_admitting_rendering(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated = pathlib.Path(temporary)
            (generated / "pinyon_shift_recomp.5.cpp").write_text(
                "DEFINE_REX_FUNC(sub_823E1000) {\n"
                "\t// bl 0x823e2000\n"
                "\tsub_823E2000(ctx, base);\n"
                "}\n\n"
                "DEFINE_REX_FUNC(sub_823E2000) {\n"
                "\t// bctrl\n"
                "\tPinyonShiftObserveDrawPacketSubmission(ctx.r3);\n"
                "\tREX_CALL_INDIRECT_FUNC(ctx.ctr.u32);\n"
                "}\n",
                encoding="utf-8",
            )
            document = MODULE.build(
                self.report(),
                {"assignments": {"823E1000": 5, "823E2000": 5}},
                generated,
            )
        self.assertEqual("complete", document["status"])
        self.assertEqual(2, document["totals"]["resolved_generated_methods"])
        self.assertTrue(
            document["qualification"]["generated_method_resolution_complete"]
        )
        self.assertFalse(
            document["qualification"]["vehicle_render_method_identity_proved"]
        )
        first = next(
            item for item in document["methods"] if item["address"] == "823E1000"
        )
        self.assertEqual(["823E2000"], first["direct_callees"])
        self.assertEqual([{"owner_vtable": "82001000", "slot": 3}], first["owners"])
        self.assertEqual(1, first["closest_native_hook_depth"])
        self.assertEqual(
            ["823E1000", "823E2000"],
            first["reachable_hook_paths"][0]["path"],
        )
        self.assertEqual(
            ["PinyonShiftObserveDrawPacketSubmission"],
            first["reachable_hook_paths"][0]["native_hook_mentions"],
        )
        self.assertTrue(first["static_callgraph_candidate_only"])
        self.assertEqual(2, document["totals"]["methods_reaching_native_hooks"])

    def test_preserves_runtime_candidate_without_promoting_draw_identity(self):
        report = self.report()
        report["method_correlations"] = [
            {
                "method_address": "823E1000",
                "vtable_slot": 3,
                "calls": 8,
                "matched_owner_calls": 7,
                "exits": 8,
                "direct_draw_origins": 4,
                "backend_draw_matches": 4,
                "vehicle_render_method_candidate_proved": True,
            }
        ]
        report["qualification"]["vehicle_render_method_candidate_proved"] = True
        with tempfile.TemporaryDirectory() as temporary:
            generated = pathlib.Path(temporary)
            (generated / "pinyon_shift_recomp.5.cpp").write_text(
                "DEFINE_REX_FUNC(sub_823E1000) {\n}\n\n"
                "DEFINE_REX_FUNC(sub_823E2000) {\n}\n",
                encoding="utf-8",
            )
            document = MODULE.build(
                report,
                {"assignments": {"823E1000": 5, "823E2000": 5}},
                generated,
            )
        candidate = next(
            item for item in document["methods"] if item["address"] == "823E1000"
        )
        self.assertEqual(4, candidate["runtime_correlation"]["backend_draw_matches"])
        self.assertTrue(
            document["qualification"]["vehicle_render_method_candidate_proved"]
        )
        self.assertFalse(
            document["qualification"]["vehicle_render_method_identity_proved"]
        )

    def test_resolves_component_dispatch_targets_without_promoting_them(self):
        report = self.report()
        report["indirect_targets"] = [
            {
                "method_address": "823E1000",
                "callsite_address": "823E1010",
                "target_address": "823E3000",
                "object_address": "A0004000",
                "object_vtable": "82002000",
                "observations": 6,
                "first_frame": 10,
                "last_frame": 12,
            }
        ]
        with tempfile.TemporaryDirectory() as temporary:
            generated = pathlib.Path(temporary)
            (generated / "pinyon_shift_recomp.5.cpp").write_text(
                "DEFINE_REX_FUNC(sub_823E1000) {\n}\n\n"
                "DEFINE_REX_FUNC(sub_823E2000) {\n}\n\n"
                "DEFINE_REX_FUNC(sub_823E3000) {\n"
                "\tPinyonShiftObserveDrawPacketSubmission(ctx.r3);\n"
                "}\n",
                encoding="utf-8",
            )
            document = MODULE.build(
                report,
                {
                    "assignments": {
                        "823E1000": 5,
                        "823E2000": 5,
                        "823E3000": 5,
                    }
                },
                generated,
            )
        dispatch = document["component_dispatches"][0]
        self.assertEqual("generated_function", dispatch["target_method"]["resolution"])
        self.assertTrue(
            document["qualification"]["vehicle_component_dispatch_seed_proved"]
        )
        self.assertTrue(dispatch["vehicle_component_dispatch_candidate_only"])
        self.assertFalse(
            document["qualification"]["vehicle_render_method_identity_proved"]
        )

    def test_preserves_unresolved_methods_as_candidates(self):
        document = MODULE.build(
            self.report(), {"assignments": {}}, pathlib.Path("missing")
        )
        self.assertEqual(2, document["totals"]["unresolved_methods"])
        self.assertFalse(
            document["qualification"]["generated_method_resolution_complete"]
        )

    def test_rejects_unqualified_or_player_claiming_input(self):
        report = self.report()
        report["qualification"]["vehicle_owner_class_seed_proved"] = False
        with self.assertRaisesRegex(ValueError, "not qualified"):
            MODULE.build(report, {"assignments": {}}, pathlib.Path("missing"))

        report = self.report()
        report["qualification"]["player_vehicle_identity_proved"] = True
        with self.assertRaisesRegex(ValueError, "player identity"):
            MODULE.build(report, {"assignments": {}}, pathlib.Path("missing"))

    def test_bounds_callgraph_without_promoting_a_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            generated = pathlib.Path(temporary)
            (generated / "pinyon_shift_recomp.5.cpp").write_text(
                "DEFINE_REX_FUNC(sub_823E1000) {\n"
                "\tsub_823E2000(ctx, base);\n"
                "}\n\n"
                "DEFINE_REX_FUNC(sub_823E2000) {\n"
                "\tREX_TAIL_CALL(sub_823E3000);\n"
                "}\n\n"
                "DEFINE_REX_FUNC(sub_823E3000) {\n"
                "\tPinyonShiftObserveDrawImmediateDispatch(ctx.r3);\n"
                "}\n",
                encoding="utf-8",
            )
            document = MODULE.build(
                self.report(),
                {
                    "assignments": {
                        "823E1000": 5,
                        "823E2000": 5,
                        "823E3000": 5,
                    }
                },
                generated,
                callgraph_depth=1,
            )
        first = next(
            item for item in document["methods"] if item["address"] == "823E1000"
        )
        self.assertTrue(first["callgraph_depth_limited"])
        self.assertEqual([], first["reachable_hook_paths"])
        self.assertFalse(
            document["qualification"]["vehicle_render_method_identity_proved"]
        )


if __name__ == "__main__":
    unittest.main()
