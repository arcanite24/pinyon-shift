import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-procedural-frame-accumulator.py"
SPEC = importlib.util.spec_from_file_location("procedural_frame_accumulator", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    common = {"session": "session"}
    events = [
        {
            **common,
            "event": MODULE.CONFIG,
            "procedural_color_frame_accumulator_backend": (
                "armed_private_d3d12_v1"
            ),
        }
    ]
    plans = (
        ("begin_and_append", 0, 256, 256),
        ("append", 256, 256, 512),
        ("append_and_commit", 512, 224, 736),
    )
    for operation, destination_row, storage_rows, padded_height in plans:
        events.append(
            {
                **common,
                "event": MODULE.PLAN,
                "frame": "100",
                "operation": operation,
                "destination_row": str(destination_row),
                "storage_row_count": str(storage_rows),
                "padded_height": str(padded_height),
                "logical_extent": "1280x720",
                "source_state": "14020500:00030000",
                "backend_resource_action": "private_only",
                "xenos_authority": "true",
                "suppression_allowed": "false",
            }
        )
    for appended_row_end, committed in ((256, "false"), (512, "false"), (736, "true")):
        events.append(
            {
                **common,
                "event": MODULE.RESULT,
                "frame": "100",
                "status": "recorded",
                "resource_extent": "1280x736",
                "logical_extent": "1280x720",
                "appended_row_end": str(appended_row_end),
                "committed": committed,
                "resource_scope": "private_d3d12",
                "guest_memory_publication": "false",
                "xenos_resolve": "preserved_and_completed_first",
                "draw_suppression": "false",
            }
        )
    events.extend(
        [
            {
                **common,
                "event": MODULE.PLAN_SUMMARY,
                "qualified_resolve_ingress_arms": "1",
                "qualified_resolve_source_mode_3": "1",
                "qualified_resolve_source_mode_12": "0",
            },
            {
                **common,
                "event": MODULE.RESULT_SUMMARY,
                "status": "armed",
                "recorded": "3",
                "cancelled": "0",
                "invalid_request": "0",
                "unavailable": "0",
                "unsupported_target": "0",
                "allocation_failed": "0",
                "detail_events": "3",
                "detail_overflow": "0",
                "resource_scope": "private_d3d12",
                "guest_memory_publication": "false",
                "xenos_resolve": "preserved_and_completed_first",
                "draw_suppression": "false",
            },
            {**common, "event": MODULE.SHUTDOWN},
        ]
    )
    return events


class ProceduralFrameAccumulatorTests(unittest.TestCase):
    def test_qualifies_exact_private_padded_frame(self):
        result = MODULE.build(fixture(), "session")
        self.assertEqual("complete", result["status"])
        self.assertEqual([100], result["evidence"]["qualified_frames"])
        self.assertTrue(
            result["qualification"]["exact_private_padded_frame_accumulator"]
        )
        self.assertEqual("1280x720", result["qualification"]["logical_extent"])
        self.assertEqual("1280x736", result["qualification"]["storage_extent"])
        self.assertFalse(result["qualification"]["guest_memory_publication"])
        self.assertFalse(result["qualification"]["draw_suppression"])

    def test_rejects_incomplete_row_plan(self):
        events = fixture()
        for event in events:
            if event.get("event") == MODULE.PLAN and event.get("operation") == "append":
                event["destination_row"] = "257"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn(
            "no exact planned and committed 1280x720 frame was observed",
            result["failures"],
        )

    def test_rejects_backend_hard_failure(self):
        events = fixture()
        summary = next(
            event for event in events if event.get("event") == MODULE.RESULT_SUMMARY
        )
        summary["unavailable"] = "1"
        summary["detail_events"] = "4"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn("backend reported a hard failure", result["failures"])

    def test_qualifies_float_as_16_source_alias(self):
        events = fixture()
        for event in events:
            if event.get("event") == MODULE.PLAN:
                event["source_state"] = "14020500:000C0000"
        summary = next(
            event for event in events if event.get("event") == MODULE.PLAN_SUMMARY
        )
        summary["qualified_resolve_source_mode_3"] = "0"
        summary["qualified_resolve_source_mode_12"] = "1"
        result = MODULE.build(events, "session")
        self.assertEqual("complete", result["status"])

    def test_rejects_unproved_source_mode(self):
        events = fixture()
        for event in events:
            if event.get("event") == MODULE.PLAN:
                event["source_state"] = "14020500:00020000"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn(
            "no exact planned and committed 1280x720 frame was observed",
            result["failures"],
        )

    def test_rejects_ingress_accounting_drift(self):
        events = fixture()
        summary = next(
            event for event in events if event.get("event") == MODULE.PLAN_SUMMARY
        )
        summary["qualified_resolve_ingress_arms"] = "2"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn(
            "qualified resolve ingress accounting is incomplete",
            result["failures"],
        )

    def test_rejects_incomplete_result_accounting(self):
        events = fixture()
        summary = next(
            event for event in events if event.get("event") == MODULE.RESULT_SUMMARY
        )
        summary["detail_events"] = "2"
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn("backend result accounting is incomplete", result["failures"])

    def test_rejects_missing_clean_shutdown(self):
        events = [event for event in fixture() if event.get("event") != MODULE.SHUTDOWN]
        result = MODULE.build(events, "session")
        self.assertEqual("incomplete", result["status"])
        self.assertIn("clean process shutdown was not observed", result["failures"])


if __name__ == "__main__":
    unittest.main()
