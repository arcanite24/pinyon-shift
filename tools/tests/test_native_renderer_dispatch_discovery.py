import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "discover-native-renderer-dispatch.py"
SPEC = importlib.util.spec_from_file_location("native_dispatch_discovery", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def fixture(address, body):
    return "\n".join(
        [
            "DEFINE_REX_FUNC(sub_{:08X}) {{".format(address),
            "\tREX_FUNC_PROLOGUE();",
            *[
                line if line.startswith("loc_") else "\t// {}".format(line)
                for line in body
            ],
            "}",
        ]
    )


def reviewed_fixtures(include_immediate=True):
    dirty_clears = []
    for offset in (16, 16, 16, 16, 24, 32):
        dirty_clears.extend(
            [
                f"ld r20,{offset}(r31)",
                "rldicr r20,r20,0,51",
                f"std r20,{offset}(r31)",
            ]
        )
    chunks = [
        fixture(
            0x824079B8,
            ["mflr r12", "loc_824079F8:", "bl 0x8240f4d8"],
        ),
        fixture(
            0x8240F4D8,
            [
                "mflr r12",
                "loc_82410318:",
                "oris r11,r11,49152",
                "rlwimi r10,r29,16,0,15",
                "ori r11,r11,13824",
                "cmpwi cr6,r22,0",
                "stwu r11,4(r3)",
                *dirty_clears,
            ],
        ),
        fixture(
            0x824587D8,
            [
                "mflr r12",
                "lis r20,-16384",
                "ori r20,r20,17920",
                "stwu r20,4(r3)",
                "lis r21,-16383",
                "ori r21,r21,15616",
                "stwu r21,4(r3)",
                "lis r22,-16383",
                "ori r22,r22,15616",
                "stwu r22,4(r3)",
                "lis r23,-16380",
                "ori r23,r23,15360",
                "stwu r23,4(r3)",
                "lis r24,-16380",
                "ori r24,r24,15360",
                "stwu r24,4(r3)",
                "lis r25,-16383",
                "ori r25,r25,23040",
                "stwu r25,4(r3)",
                "bl 0x82458a88",
                "bl 0x82458a88",
            ],
        ),
        fixture(
            0x82458A88,
            [
                "mflr r12",
                "li r11,8712",
                "li r10,6",
                "stwu r11,4(r3)",
                "lis r11,1",
                "stwu r10,4(r3)",
                "lis r20,-16384",
                "ori r20,r20,24576",
                "stwu r20,4(r3)",
                "lis r21,-16384",
                "ori r21,r21,24832",
                "stwu r21,4(r3)",
                "lis r22,-16384",
                "ori r22,r22,24576",
                "stwu r22,4(r3)",
                "lis r23,-16384",
                "ori r23,r23,24832",
                "stwu r23,4(r3)",
                "lis r24,-16384",
                "ori r24,r24,23296",
                "stwu r24,4(r3)",
            ],
        ),
        fixture(
            0x829F21A0,
            [
                "mflr r12",
                "lis r9,-16384",
                "ori r9,r9,8960",
                "stwu r9,4(r11)",
                "or r10,r9,r10",
                "std r10,12424(r31)",
            ],
        ),
        fixture(
            0x829F2280,
            [
                "mflr r12",
                "lis r11,-16384",
                "ori r11,r11,8960",
                "stwu r11,4(r3)",
                "andc r11,r10,r11",
                "std r11,12424(r31)",
            ],
        ),
        fixture(
            0x82D951E0,
            [
                "mflr r12",
                "bl 0x829f21a0",
                "bl 0x82415f68",
                "bl 0x829f2280",
            ],
        ),
        fixture(
            0x82413AB8,
            [
                "mflr r12",
                "lis r20,-16384",
                "ori r20,r20,24576",
                "stwu r20,4(r3)",
                "lis r21,-16384",
                "ori r21,r21,24832",
                "stwu r21,4(r3)",
            ],
        ),
        fixture(
            0x824736F0,
            [
                "mflr r12",
                "lis r20,-16384",
                "ori r20,r20,24576",
                "stwu r20,4(r3)",
                "lis r21,-16384",
                "ori r21,r21,24832",
                "stwu r21,4(r3)",
                "lis r22,-16384",
                "ori r22,r22,25088",
                "stwu r22,4(r3)",
                "lis r23,-16384",
                "ori r23,r23,25344",
                "stwu r23,4(r3)",
                "bl 0x82413ab8",
            ],
        ),
        fixture(0x82D95408, ["bl 0x82d951e0"]),
        fixture(0x82DA8CB0, ["bl 0x82d951e0"]),
        fixture(0x829ED510, ["b 0x82413ab8"]),
        fixture(0x8246FB90, ["bl 0x829ed510"]),
    ]
    if include_immediate:
        chunks.append(
            fixture(
                0x829F7C70,
                [
                    "mflr r12",
                    "loc_829F7CA0:",
                    "lis r11,-16384",
                    "rlwinm r10,r29,16,0,15",
                    "ori r11,r11,13824",
                    "or r10,r10,r30",
                    "stwu r11,4(r3)",
                ],
            )
        )
    return chunks


def owner_fixtures():
    return [
        fixture(
            0x82409668,
            [
                "mflr r12",
                "loc_82409834:",
                "bl 0x82409398",
                "mr r3,r29",
                "addi r1,r1,176",
                "b 0x82a7de40",
            ],
        ),
        fixture(
            0x824167F8,
            [
                "mflr r12",
                "loc_82416894:",
                "bl 0x82416a00",
                "addi r1,r1,112",
                "blr",
            ],
        ),
        fixture(
            0x8246E8F8,
            [
                "mflr r12",
                "loc_8246E92C:",
                "bl 0x82416a00",
                "mr r3,r30",
                "bl 0x82467468",
                "addi r1,r1,112",
                "blr",
            ],
        ),
        fixture(
            0x829F5FF0,
            [
                "mflr r12",
                "loc_829F6304:",
                "bl 0x82409398",
                "loc_829F6338:",
                "bl 0x82409398",
                "loc_829F6354:",
                "mr r3,r31",
                "addi r1,r1,176",
                "b 0x82a7de44",
            ],
        ),
    ]


def producer_fixtures():
    return [
        fixture(
            0x8240D070,
            [
                "mflr r12",
                "bl 0x82409668",
                "loc_8240D1F0:",
                "addi r1,r1,128",
                "b 0x82a7de58",
            ],
        ),
        fixture(
            0x82417060,
            [
                "mflr r12",
                "bl 0x824167f8",
                "loc_824170C0:",
                "addi r1,r1,96",
                "blr",
            ],
        ),
        fixture(
            0x829F6360,
            [
                "mflr r12",
                "bl 0x829f5ff0",
                "loc_829F63FC:",
                "addi r1,r1,128",
                "b 0x82a7de54",
            ],
        ),
    ]


class NativeRendererDispatchDiscoveryTests(unittest.TestCase):
    def build(self, chunks):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pinyon_shift_recomp.1.cpp"
            path.write_text("\n\n".join(chunks), encoding="utf-8")
            return MODULE.build([path])

    def test_finds_reviewed_wrappers_and_direct_calls(self):
        caller = fixture(
            0x82B00000,
            [
                "bl 0x824079b8",
                "bl 0x8240f4d8",
                "bl 0x829f21a0",
                "bl 0x829f2280",
                "bl 0x829f7c70",
                "bl 0x82413ab8",
                "bl 0x824736f0",
            ],
        )
        document = self.build([*reviewed_fixtures(), caller])
        self.assertEqual(document["totals"]["reviewed_wrappers"], 10)
        self.assertEqual(document["totals"]["direct_calls"], 15)
        self.assertEqual(document["totals"]["tail_forwarded_calls"], 1)
        self.assertEqual(document["totals"]["runtime_correlation_calls"], 16)
        self.assertEqual(document["totals"]["adapter_argument_leads"], 1)
        self.assertEqual(document["totals"]["dirty_state_clears"], 6)
        self.assertEqual(document["totals"]["query_state_transitions"], 2)
        indexed_packet = next(
            item
            for item in document["packet_constructors"]
            if item["function_address"] == "8240F4D8"
            and item["opcode"] == "PM4_DRAW_INDX_2"
        )
        self.assertEqual(indexed_packet["header_source"], "dynamic_type3_count")
        provenance = document["draw_packet_provenance"]
        self.assertEqual(
            provenance["correlation"], "exact_physical_pm4_header_address"
        )
        self.assertEqual(
            [item["packet_hook_address"] for item in provenance["packet_sites"]],
            ["82410328", "829F7CB0"],
        )
        self.assertEqual(
            provenance["adapter_forward_return_address"], "824079FC"
        )
        adapter_call = next(
            item
            for item in document["direct_calls"]
            if item["wrapper_kind"] == "draw_adapter"
        )
        self.assertEqual(adapter_call["return_address"], "82B00004")
        self.assertEqual(
            document["resolve_boundary"]["classification"],
            "title_resolve_setup_and_backend_copy_proved",
        )
        self.assertEqual(document["totals"]["resolve_mode_writes"], 1)
        self.assertEqual(document["totals"]["query_owner_callers"], 2)
        self.assertEqual(
            document["query_owner_lifecycle"]["classification"],
            "query_lifecycle_owner_proved_semantics_unknown",
        )
        self.assertEqual(
            len(document["side_effect_packets"]["resolve_controller"]), 6
        )
        forwarded = document["tail_forwarded_calls"][0]
        self.assertEqual(forwarded["wrapper"], "82413AB8")
        self.assertEqual(forwarded["return_address"], "8246FB94")
        self.assertEqual(forwarded["forwarder_function"], "sub_829ED510")
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_adapter_argument_leads_stop_at_calls_and_decode_loads(self):
        caller = fixture(
            0x82B00000,
            [
                "bl 0x82415f68",
                "lwz r3,40(r31)",
                "mr r4,r30",
                "bl 0x824079b8",
            ],
        )
        document = self.build([*reviewed_fixtures(), caller])
        lead = document["adapter_argument_leads"][0]
        by_register = {item["register"]: item for item in lead["arguments"]}
        self.assertEqual(
            by_register["r3"]["status"], "bounded_syntactic_definition"
        )
        self.assertEqual(
            by_register["r3"]["memory_load"],
            {"base_register": "r31", "offset": 40, "width": "lwz"},
        )
        self.assertEqual(by_register["r4"]["source_registers"], ["r30"])
        self.assertEqual(
            by_register["r5"]["status"], "unknown_across_call_boundary"
        )
        self.assertFalse(lead["object_identity_proved"])
        self.assertFalse(lead["lifetime_proved"])

    def test_rejects_missing_reviewed_packet_evidence(self):
        incomplete = reviewed_fixtures(include_immediate=False)
        with self.assertRaisesRegex(ValueError, "829F7C70"):
            self.build(incomplete)

    def test_ignores_matching_numeric_work_without_a_packet_store(self):
        false_positive = fixture(
            0x83051E48,
            ["ori r12,r12,13824", "add r11,r11,r12"],
        )
        document = self.build([false_positive, *reviewed_fixtures()])
        addresses = {
            item["function_address"] for item in document["packet_constructors"]
        }
        self.assertNotIn("83051E48", addresses)

    def test_inventories_stored_indirect_buffer_packets(self):
        indirect = fixture(
            0x83060000,
            [
                "lis r11,-16382",
                "ori r11,r11,16128",
                "stwu r11,4(r3)",
                "lis r10,-16382",
                "ori r10,r10,14080",
                "stw r10,16(r4)",
            ],
        )
        caller = fixture(0x83070000, ["bl 0x83060000"])
        document = self.build([indirect, caller, *reviewed_fixtures()])
        packets = [
            item
            for item in document["packet_constructors"]
            if item["function_address"] == "83060000"
        ]
        self.assertEqual(
            [item["opcode"] for item in packets],
            ["PM4_INDIRECT_BUFFER", "PM4_INDIRECT_BUFFER_PFD"],
        )
        self.assertEqual(
            [item["header_source"] for item in packets],
            ["fixed_type3_count_3", "fixed_type3_count_3"],
        )
        self.assertEqual(packets[0]["packet_register"], "r11")
        self.assertEqual(packets[0]["store_instruction"], "stwu r11,4(r3)")
        self.assertEqual(document["totals"]["indirect_constructor_calls"], 1)
        constructor_call = document["indirect_constructor_calls"][0]
        self.assertEqual(
            constructor_call["constructor_function_address"], "83060000"
        )
        self.assertEqual(constructor_call["callsite"], "83070000")
        self.assertEqual(constructor_call["return_address"], "83070004")
        self.assertEqual(
            constructor_call["constructor_store_addresses"],
            ["83060008", "83060014"],
        )
        self.assertFalse(constructor_call["suppression_eligible"])

    def test_inventories_balanced_constructor_owner_layer(self):
        callers = [
            fixture(0x83010000, ["lwz r3,40(r31)", "bl 0x82409668"]),
            fixture(0x83020000, ["bl 0x824167f8"]),
            fixture(0x83030000, ["bl 0x8246e8f8"]),
            fixture(0x83040000, ["bl 0x829f5ff0"]),
        ]
        document = self.build(
            [*reviewed_fixtures(), *owner_fixtures(), *callers]
        )
        self.assertEqual(4, document["totals"]["indirect_owner_runtime_hooks"])
        self.assertEqual(4, document["totals"]["indirect_owner_calls"])
        self.assertEqual(4, document["totals"]["indirect_owner_argument_leads"])
        hooks = {
            item["function_address"]: item
            for item in document["indirect_owner_runtime_hooks"]
        }
        self.assertEqual("8240983C", hooks["82409668"]["exit_hook_address"])
        call = next(
            item
            for item in document["indirect_owner_calls"]
            if item["owner_function_address"] == "82409668"
        )
        self.assertEqual("83010004", call["callsite"])
        lead = next(
            item
            for item in document["indirect_owner_argument_leads"]
            if item["owner_function_address"] == "82409668"
        )
        self.assertEqual(
            {"base_register": "r31", "offset": 40, "width": "lwz"},
            lead["arguments"][0]["memory_load"],
        )
        self.assertFalse(lead["suppression_eligible"])

    def test_inventories_balanced_dominant_producer_layer(self):
        callers = [
            fixture(0x83010000, ["lwz r3,40(r31)", "bl 0x8240d070"]),
            fixture(0x83020000, ["bl 0x82417060"]),
            fixture(0x83030000, ["bl 0x829f6360"]),
        ]
        document = self.build(
            [*reviewed_fixtures(), *producer_fixtures(), *callers]
        )
        self.assertEqual(3, document["totals"]["indirect_producer_runtime_hooks"])
        self.assertEqual(3, document["totals"]["indirect_producer_calls"])
        self.assertEqual(
            3, document["totals"]["indirect_producer_argument_leads"]
        )
        hooks = {
            item["function_address"]: item
            for item in document["indirect_producer_runtime_hooks"]
        }
        self.assertEqual("829F63FC", hooks["829F6360"]["exit_hook_address"])
        call = next(
            item
            for item in document["indirect_producer_calls"]
            if item["producer_function_address"] == "8240D070"
        )
        self.assertEqual("83010004", call["callsite"])
        lead = next(
            item
            for item in document["indirect_producer_argument_leads"]
            if item["producer_function_address"] == "8240D070"
        )
        self.assertEqual(
            {"base_register": "r31", "offset": 40, "width": "lwz"},
            lead["arguments"][0]["memory_load"],
        )
        self.assertFalse(call["object_identity_proved"])
        self.assertFalse(call["lifetime_proved"])

    def test_runtime_hooks_are_default_off_bounded_and_passive(self):
        hooks = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        analysis = (ROOT / "config/rexglue/analysis/main-xex.toml").read_text(
            encoding="utf-8"
        )
        capture = (
            ROOT / "tools/capture-native-renderer-dispatch.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "pinyon_shift_native_renderer_dispatch_discovery, false", hooks
        )
        self.assertIn("kDispatchCallerCapacity = 256", hooks)
        self.assertIn('"suppression_allowed", "false"', hooks)
        claim = hooks.index("entry.key.compare_exchange_strong")
        initial_count = hooks.index("entry.calls.store(1", claim)
        first_sample = hooks.index("entry.first_frame.store", claim)
        self.assertLess(initial_count, first_sample)
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveDrawIndexedDispatch"'), 1
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveDrawImmediateDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveDrawAdapterDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveDrawPacketSubmission"'),
            2,
        )
        for address in (
            "824095B4",
            "82416EFC",
            "8246FC1C",
            "8263BD64",
            "829E8E88",
            "829EC49C",
        ):
            self.assertIn(f"address = 0x{address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectPacket{address}"'
                ),
                1,
            )
        for function, entry, exit_address in (
            ("82409398", "8240939C", "82409660"),
            ("82416A00", "82416A04", "82417054"),
            ("8246FB98", "8246FB9C", "8246FC78"),
            ("8263BCB8", "8263BCBC", "8263BDF0"),
            ("829E8E00", "829E8E04", "829E8ED4"),
            ("829EC400", "829EC404", "829EC5AC"),
        ):
            self.assertIn(f"address = 0x{entry}", analysis)
            self.assertIn(f"address = 0x{exit_address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectConstructor{function}Entry"'
                ),
                1,
            )
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectConstructor{function}Exit"'
                ),
                1,
            )
        for function, entry, exit_address in (
            ("82409668", "8240966C", "8240983C"),
            ("824167F8", "824167FC", "82416898"),
            ("8246E8F8", "8246E8FC", "8246E938"),
            ("829F5FF0", "829F5FF4", "829F6358"),
        ):
            self.assertIn(f"address = 0x{entry}", analysis)
            self.assertIn(f"address = 0x{exit_address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectOwner{function}Entry"'
                ),
                1,
            )
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectOwner{function}Exit"'
                ),
                1,
            )
        for function, entry, exit_address in (
            ("8240D070", "8240D074", "8240D1F0"),
            ("82417060", "82417064", "824170C0"),
            ("829F6360", "829F6364", "829F63FC"),
        ):
            self.assertIn(f"address = 0x{entry}", analysis)
            self.assertIn(f"address = 0x{exit_address}", analysis)
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectProducer{function}Entry"'
                ),
                1,
            )
            self.assertEqual(
                analysis.count(
                    f'name = "PinyonShiftObserveIndirectProducer{function}Exit"'
                ),
                1,
            )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveVizQueryBeginDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveVizQueryEndDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveResolveControllerDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveResolveSetupDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveVizQueryOwnerDispatch"'),
            1,
        )
        self.assertEqual(
            analysis.count(
                'name = "PinyonShiftObserveBinningScissorStateDispatch"'
            ),
            1,
        )
        self.assertEqual(
            analysis.count('name = "PinyonShiftObserveBinningStateResetDispatch"'),
            1,
        )
        self.assertIn('address = 0x824079BC', analysis)
        self.assertIn('address = 0x8240F4DC', analysis)
        self.assertIn('address = 0x82410328', analysis)
        self.assertIn('address = 0x824587DC', analysis)
        self.assertIn('address = 0x82458A8C', analysis)
        self.assertIn('address = 0x829F21A4', analysis)
        self.assertIn('address = 0x829F2284', analysis)
        self.assertIn('address = 0x829F7C74', analysis)
        self.assertIn('address = 0x829F7CB0', analysis)
        self.assertIn('address = 0x82D951E4', analysis)
        self.assertIn('address = 0x82413ABC', analysis)
        self.assertIn('address = 0x824736F4', analysis)
        self.assertEqual(
            analysis.count(
                'registers = ["r3", "r4", "r5", "r6", "r7", "r8", '
                '"r9", "r10", "r12"]'
            ),
            23,
        )
        self.assertIn(
            "REX_PINYON_SHIFT_NATIVE_RENDERER_DISPATCH_DISCOVERY", capture
        )
        self.assertIn("REX_PINYON_SHIFT_NATIVE_RENDERER_CENSUS", capture)
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_SCENE", capture)
        self.assertIn("[string]$Scene = 'unmarked'", capture)
        self.assertIn("launch-preview.ps1", capture)
        for forbidden in ("SetDrawSuppression", "SetCopySuppression"):
            self.assertNotIn(forbidden, hooks + analysis + capture)


if __name__ == "__main__":
    unittest.main()
