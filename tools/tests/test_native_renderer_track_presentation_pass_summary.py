import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-track-presentation-passes.py"
SPEC = importlib.util.spec_from_file_location("track_presentation_passes", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def event(name, **values):
    return {"event": name, "session": "test", **values}


def safety():
    return {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }


def fixture():
    summary = event(
        MODULE.SUMMARY,
        status="complete",
        presentation_vtable="82243774",
        overlaps="0",
        exit_without_entry="0",
        prepared_target_observations="12",
        prepared_target_entries="2",
        prepared_target_overflow="0",
        prepared_target_accounting_complete="true",
        receiver_observations="12",
        receiver_entries="2",
        receiver_read_faults="0",
        receiver_overflow="0",
        receiver_accounting_complete="true",
        accounting_complete="true",
        **{
            f"slot_{slot}_{field}": value
            for slot, function, entries in (
                (78, "82DEEEE0", 4),
                (79, "8240E7B0", 8),
                (80, "82DEF2B0", 0),
                (81, "82DEADE0", 0),
            )
            for field, value in (
                ("function", function),
                ("entries", str(entries)),
                ("exits", str(entries)),
                ("exact", str(entries)),
                ("invalid_root", "0"),
            )
        },
        **safety(),
    )
    for slot in MODULE.SLOTS:
        summary[f"slot_{slot}_dispatcher_direct"] = "3" if slot == 79 else "0"
        summary[f"slot_{slot}_dispatcher_context"] = "8" if slot == 79 else "0"
        adapter_dispatches = 4 if slot == 80 else 0
        summary[f"slot_{slot}_adapter_entries"] = (
            "6" if slot == 80 else "0"
        )
        summary[f"slot_{slot}_adapter_enabled"] = (
            "5" if slot == 80 else "0"
        )
        summary[f"slot_{slot}_adapter_eligible"] = str(adapter_dispatches)
        summary[f"slot_{slot}_adapter_dispatches"] = str(adapter_dispatches)
        summary[f"slot_{slot}_adapter_first_target"] = (
            "8240F000" if slot == 80 else "00000000"
        )
        summary[f"slot_{slot}_adapter_last_target"] = (
            "8240F000" if slot == 80 else "00000000"
        )
        summary[f"slot_{slot}_adapter_target_changes"] = "0"
    depth = event(
        MODULE.ENTRY,
        entry_key="1111222233334444",
        pass_mask="00000002",
        direct_scope_mask="00000000",
        packet_lineage_mask="00000002",
        calls="8",
        first_frame="10",
        last_frame="11",
        vertex_shader="AAAABBBBCCCCDDDD",
        pixel_shader="0000000000000000",
        bound_render_target_bits="00000001",
        bound_render_target_formats="0:0:0:0:0",
        prepared_pipeline_flags="00000003",
        viewport="43800000:44400000:C3800000:43800000",
        viewport_transform_control="00010F00",
        scissor="00000000:04000400",
        target_state="10000410:00000000:00000000:00000000:00000000:000002D0",
        **safety(),
    )
    color = event(
        MODULE.ENTRY,
        entry_key="5555666677778888",
        pass_mask="00000001",
        direct_scope_mask="00000001",
        packet_lineage_mask="00000000",
        calls="4",
        first_frame="10",
        last_frame="11",
        vertex_shader="1111222233334444",
        pixel_shader="9999AAAABBBBCCCC",
        bound_render_target_bits="00000002",
        bound_render_target_formats="0:6:0:0:0",
        prepared_pipeline_flags="00000003",
        viewport="44200000:44200000:C4200000:44200000",
        viewport_transform_control="00010F00",
        scissor="00000000:02800280",
        target_state="10000290:00000640:00000000:00000000:00000000:00000000",
        **safety(),
    )
    receiver_78 = event(
        MODULE.RECEIVER,
        pass_mask="00000001",
        receiver_vtable="82112233",
        calls="4",
        **safety(),
    )
    receiver_79 = event(
        MODULE.RECEIVER,
        pass_mask="00000002",
        receiver_vtable="82003CCC",
        calls="8",
        **safety(),
    )
    return [
        event("process.start"),
        depth,
        color,
        receiver_78,
        receiver_79,
        summary,
        event("process.shutdown"),
    ]


class TrackPresentationPassSummaryTests(unittest.TestCase):
    def test_correlates_live_slots_and_target_shapes(self):
        document = MODULE.build(fixture())
        self.assertEqual("complete", document["status"])
        self.assertEqual([78, 79], document["qualification"]["live_slots"])
        self.assertEqual(
            [78, 79], document["qualification"]["accepted_receiver_slots"]
        )
        self.assertEqual(
            {"direct": 3, "context": 8},
            document["slot_totals"]["79"]["dispatcher_routes"],
        )
        self.assertEqual(
            {
                "entries": 6,
                "enabled": 5,
                "eligible": 4,
                "dispatches": 4,
                "first_target": "8240F000",
                "last_target": "8240F000",
                "target_changes": 0,
            },
            document["slot_totals"]["80"]["adapter_route"],
        )
        self.assertEqual([78], document["qualification"]["color_target_slots"])
        self.assertEqual(
            {"82003CCC": 8}, document["runtime_receivers_by_slot"]["79"]
        )
        self.assertIn(
            "1024x1024:43800000:44400000:C3800000:43800000:00010F00",
            document["prepared_targets_by_slot"]["79"]["spatial_states"],
        )
        self.assertEqual(
            8,
            document["prepared_targets_by_slot"]["79"]["target_shapes"][
                "depth_only"
            ],
        )
        self.assertEqual(
            8,
            document["prepared_targets_by_slot"]["79"]["target_states"][
                "10000410:00000000:00000000:00000000:00000000:000002D0"
            ],
        )
        self.assertEqual(
            {"packet_lineage": 8},
            document["prepared_targets_by_slot"]["79"][
                "attribution_sources"
            ],
        )

    def test_reports_prepared_accounting_drift(self):
        events = copy.deepcopy(fixture())
        events[-2]["prepared_target_observations"] = "13"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "prepared target call accounting drifted", document["failures"]
        )

    def test_rejects_unsafe_entry(self):
        events = copy.deepcopy(fixture())
        events[1]["native_admission"] = "true"
        with self.assertRaisesRegex(ValueError, "violates safety"):
            MODULE.build(events)


if __name__ == "__main__":
    unittest.main()
