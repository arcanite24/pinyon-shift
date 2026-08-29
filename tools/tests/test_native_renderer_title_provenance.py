import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-title-provenance.py"
SPEC = importlib.util.spec_from_file_location("native_title_provenance", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def static_inventory():
    return {
        "schema": MODULE.STATIC_SCHEMA,
        "runtime_correlation_calls": [
            {
                "wrapper": "824079B8",
                "return_address": "823E6F50",
                "caller_function": "sub_823E6EF0",
                "caller_function_address": "823E6EF0",
                "callsite": "823E6F4C",
                "wrapper_layer": "title_adapter",
            }
        ],
        "draw_packet_provenance": {
            "packet_sites": [
                {
                    "wrapper": "8240F4D8",
                    "packet_hook_address": "82410328",
                },
                {
                    "wrapper": "829F7C70",
                    "packet_hook_address": "829F7CB0",
                },
            ],
            "correlation": "exact_physical_pm4_header_address",
        },
        "adapter_argument_leads": [
            {
                "wrapper": "824079B8",
                "return_address": "823E6F50",
                "callsite": "823E6F4C",
                "arguments": [
                    {
                        "register": "r3",
                        "status": "bounded_syntactic_definition",
                        "instruction": "lwz r3,40(r31)",
                    }
                ],
                "classification": "bounded_syntactic_object_lead_only",
                "object_identity_proved": False,
                "lifetime_proved": False,
            }
        ],
    }


def events(safe=True, fault=False):
    return [
        {
            "event": "native_renderer.discovery.title_provenance_config",
            "session": "run",
            "status": "armed",
            "scene": "open_world",
        },
        {
            "event": "native_renderer.discovery.title_provenance_entry",
            "session": "run",
            "origin_wrapper": "draw_adapter",
            "origin_wrapper_address": "824079B8",
            "origin_caller": "823E6F50",
            "outcome": "prepared",
            "backend_outcome": "prepared_callback",
            "backend_signature": "747837906D0BF484",
            "prepared_signature": "747837906D0BF484",
            "calls": "12",
            "first_frame": "4",
            "last_frame": "20",
            "first_draw": "8",
            "first_packet_physical_address": "00102000",
            **{f"first_r{index}": f"{index:08X}" for index in range(3, 11)},
            "last_arguments": ":".join(
                f"{index + 1:08X}" for index in range(3, 11)
            ),
            "minimum_arguments": ":".join(
                f"{index:08X}" for index in range(3, 11)
            ),
            "maximum_arguments": ":".join(
                f"{index + 1:08X}" for index in range(3, 11)
            ),
            "varying_argument_mask": "05",
        },
        {
            "event": "native_renderer.discovery.title_provenance_outcome",
            "session": "run",
            "backend_outcome": "completed",
            "backend_draws": "12",
            "title_matches": "0",
        },
        {
            "event": "native_renderer.discovery.title_provenance_summary",
            "session": "run",
            "title_packets_recorded": "12",
            "backend_packet_matches": "12",
            "prepared_matches": "12",
            "matched_unprepared_draws": "0",
            "backend_draw_outcomes_observed": "12",
            "backend_draw_outcome_mismatches": "0",
            "backend_draw_outcome_missing": "0",
            "title_backend_outcomes": "0",
            "pending_packets": "0",
            "backend_draws_without_title_packet": "25",
            "packet_address_failures": "0",
            "reused_live_packet_addresses": "0",
            "packet_table_overflow": "0",
            "forwarding_mismatches": "0",
            "origins_pushed": "12",
            "origins_consumed": "12",
            "origin_stack_overflow": "0",
            "packets_without_origin": "0",
            "origin_accounting_complete": "true",
            "aggregate_count": "1",
            "prepared_aggregate_count": "1",
            "unprepared_aggregate_count": "0",
            "unprepared_aggregate_matches": "0",
            "aggregate_overflow": "1" if fault else "0",
            "packet_accounting_complete": "true",
            "correlation": "exact_physical_pm4_header_address",
            "guest_payload_read": "false",
            "guest_state_changed": "false",
            "control_flow_changed": "false",
            "xenos_authority": "true",
            "suppression_allowed": "false" if safe else "true",
        },
    ]


class NativeRendererTitleProvenanceTests(unittest.TestCase):
    def test_correlates_exact_known_family_with_title_caller(self):
        document = MODULE.build(events(), static_inventory())
        self.assertEqual(document["status"], "complete")
        self.assertEqual(document["totals"]["prepared_matches"], 12)
        self.assertEqual(document["totals"]["known_family_calls"], 12)
        self.assertEqual(
            document["entries"][0]["prepared_family"],
            "retained_sky_horizon_anchor",
        )
        self.assertEqual(
            document["entries"][0]["static_match"]["callsite"], "823E6F4C"
        )
        self.assertEqual(
            document["entries"][0]["static_argument_lead"]["classification"],
            "bounded_syntactic_object_lead_only",
        )
        self.assertFalse(document["entries"][0]["native_coverage"])
        self.assertEqual(document["entries"][0]["varying_registers"], ["r3", "r5"])
        self.assertIn("r4", document["entries"][0]["stable_registers"])
        self.assertEqual(
            document["entries"][0]["argument_ranges"]["r3"]["minimum"],
            "00000003",
        )
        self.assertEqual(
            document["callers"][0]["stable_argument_candidates"],
            ["r10", "r4", "r6", "r7", "r8", "r9"],
        )
        self.assertEqual(
            document["callers"][0]["prepared_families"],
            ["retained_sky_horizon_anchor"],
        )
        self.assertFalse(document["safety"]["suppression_allowed"])

    def test_faults_remain_incomplete_without_discarding_evidence(self):
        document = MODULE.build(events(fault=True), static_inventory())
        self.assertEqual(document["status"], "incomplete_fail_closed")
        self.assertEqual(document["totals"]["aggregate_overflow"], 1)
        self.assertEqual(len(document["entries"]), 1)

    def test_missing_backend_outcome_fails_closed(self):
        capture = events()
        capture[-1]["backend_draw_outcome_missing"] = "1"

        document = MODULE.build(capture, static_inventory())

        self.assertEqual(document["status"], "incomplete_fail_closed")
        self.assertEqual(document["totals"]["backend_draw_outcome_missing"], 1)

    def test_accounts_pending_and_reused_addresses_with_unprepared_evidence(self):
        capture = events()
        entry = capture[1]
        entry["outcome"] = "not_prepared"
        entry["backend_outcome"] = "edram_copy"
        entry["backend_signature"] = "0123456789ABCDEF"
        entry["prepared_signature"] = ""
        entry["calls"] = "10"
        summary = capture[-1]
        summary["title_packets_recorded"] = "12"
        summary["backend_packet_matches"] = "10"
        summary["prepared_matches"] = "0"
        summary["matched_unprepared_draws"] = "10"
        summary["backend_draw_outcomes_observed"] = "10"
        summary["title_backend_outcomes"] = "10"
        summary["pending_packets"] = "2"
        summary["reused_live_packet_addresses"] = "3"
        summary["prepared_aggregate_count"] = "0"
        summary["unprepared_aggregate_count"] = "1"
        summary["unprepared_aggregate_matches"] = "10"
        capture[2]["backend_outcome"] = "edram_copy"
        capture[2]["backend_draws"] = "10"
        capture[2]["title_matches"] = "10"

        document = MODULE.build(capture, static_inventory())

        self.assertEqual(document["status"], "complete")
        self.assertEqual(document["prepared_coverage"], "none_observed")
        self.assertEqual(document["totals"]["pending_packets"], 2)
        self.assertEqual(document["totals"]["reused_live_packet_addresses"], 3)
        self.assertEqual(document["entries"][0]["outcome"], "not_prepared")
        self.assertEqual(document["entries"][0]["backend_outcome"], "edram_copy")
        self.assertIsNone(document["entries"][0]["prepared_signature"])
        self.assertEqual(document["entries"][0]["semantic_identity"], "unknown")
        self.assertEqual(document["callers"][0]["unprepared_signatures"], 1)
        self.assertEqual(document["callers"][0]["backend_outcomes"], ["edram_copy"])

    def test_rejects_unsafe_or_drifted_contracts(self):
        with self.assertRaisesRegex(ValueError, "safety"):
            MODULE.build(events(safe=False), static_inventory())
        drifted = static_inventory()
        drifted["draw_packet_provenance"]["packet_sites"][0][
            "packet_hook_address"
        ] = "82410320"
        with self.assertRaisesRegex(ValueError, "drifted"):
            MODULE.build(events(), drifted)

        invalid_outcome = events()
        invalid_outcome[1]["backend_outcome"] = "guessed"
        with self.assertRaisesRegex(ValueError, "backend outcome"):
            MODULE.build(invalid_outcome, static_inventory())

    def test_rejects_count_mismatch(self):
        mismatched = events()
        mismatched[-1]["prepared_matches"] = "13"
        with self.assertRaisesRegex(ValueError, "counts"):
            MODULE.build(mismatched, static_inventory())


if __name__ == "__main__":
    unittest.main()
