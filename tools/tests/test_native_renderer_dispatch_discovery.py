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
            *["\t// {}".format(line) for line in body],
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
        fixture(0x824079B8, ["mflr r12", "bl 0x8240f4d8"]),
        fixture(
            0x8240F4D8,
            [
                "mflr r12",
                "oris r11,r11,49152",
                "ori r11,r11,13824",
                "stwu r11,4(r3)",
                *dirty_clears,
            ],
        ),
        fixture(
            0x824587D8,
            [
                "mflr r12",
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
    ]
    if include_immediate:
        chunks.append(
            fixture(
                0x829F7C70,
                [
                    "mflr r12",
                    "lis r11,-16384",
                    "ori r11,r11,13824",
                    "stwu r11,4(r3)",
                ],
            )
        )
    return chunks


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
            ],
        )
        document = self.build([*reviewed_fixtures(), caller])
        self.assertEqual(document["totals"]["reviewed_wrappers"], 7)
        self.assertEqual(document["totals"]["direct_calls"], 8)
        self.assertEqual(document["totals"]["dirty_state_clears"], 6)
        self.assertEqual(document["totals"]["query_state_transitions"], 2)
        self.assertEqual(
            document["packet_constructors"][0]["header_source"],
            "dynamic_type3_count",
        )
        self.assertEqual(
            document["packet_constructors"][1]["header_source"],
            "fixed_type3_count_1",
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
        self.assertFalse(document["safety"]["suppression_allowed"])

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
        self.assertIn('address = 0x824079BC', analysis)
        self.assertIn('address = 0x8240F4DC', analysis)
        self.assertIn('address = 0x824587DC', analysis)
        self.assertIn('address = 0x82458A8C', analysis)
        self.assertIn('address = 0x829F21A4', analysis)
        self.assertIn('address = 0x829F2284', analysis)
        self.assertIn('address = 0x829F7C74', analysis)
        self.assertEqual(
            analysis.count(
                'registers = ["r3", "r4", "r5", "r6", "r7", "r8", '
                '"r9", "r10", "r12"]'
            ),
            7,
        )
        self.assertIn(
            "REX_PINYON_SHIFT_NATIVE_RENDERER_DISPATCH_DISCOVERY", capture
        )
        self.assertIn("PINYON_SHIFT_NATIVE_RENDERER_SCENE", capture)
        self.assertIn("[string]$Scene = 'unmarked'", capture)
        self.assertIn("launch-preview.ps1", capture)
        for forbidden in ("SetDrawSuppression", "SetCopySuppression"):
            self.assertNotIn(forbidden, hooks + analysis + capture)


if __name__ == "__main__":
    unittest.main()
