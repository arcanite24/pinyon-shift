import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-visibility-shadow-replay.py"
SPEC = importlib.util.spec_from_file_location(
    "summarize_native_renderer_visibility_shadow_replay", TOOL
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def event(name, **values):
    return {"event": name, "session": "session-1", **values}


def fixture():
    config = event(
        MODULE.CONFIG,
        status="armed_private_replay",
        activation="startup_environment_only",
        default_enabled="false",
        selection="fresh_visibility_and_mechanical",
        title_lod="optional_exact_metadata_no_inference",
        maximum_draws_per_frame="1",
        signature_capacity="256",
        semantic_lineage="armed",
        readback="disabled",
        publication="disabled",
        native_draw="private_shadow_replay",
        xenos_draw="preserved",
        output_authority="xenos",
        draw_suppression="false",
        suppression_eligible="false",
    )
    summary = event(
        MODULE.SUMMARY,
        status="complete",
        prepared_observations="14",
        requests="3",
        recorded="3",
        target_creation_failures="0",
        unsupported="0",
        mechanical_rejections="4",
        stale_or_unselected_rejections="2",
        requests_with_title_lod="2",
        requests_without_title_lod="1",
        per_frame_quota_yields="5",
        unique_signatures="2",
        signature_capacity="256",
        signature_overflow="0",
        accounting_complete="true",
        selection_accounting_complete="true",
        title_lod_accounting_complete="true",
        maximum_draws_per_frame="1",
        selection="fresh_visibility_and_mechanical",
        title_lod="optional_exact_metadata_no_inference",
        readback="disabled",
        native_draw="private_shadow_replay",
        xenos_draw="preserved",
        output_authority="xenos",
        draw_suppression="false",
        suppression_eligible="false",
    )
    signatures = [
        event(
            MODULE.SIGNATURE,
            signature="0123456789ABCDEF",
            requests="2",
            first_frame="10",
            last_frame="12",
            minimum_title_lod="0",
            maximum_title_lod="1",
            title_lod_observations="1",
            missing_title_lod_requests="1",
            native_draw="private_shadow_replay",
            xenos_draw="preserved",
            output_authority="xenos",
            suppression_eligible="false",
        ),
        event(
            MODULE.SIGNATURE,
            signature="FEDCBA9876543210",
            requests="1",
            first_frame="11",
            last_frame="11",
            minimum_title_lod="2",
            maximum_title_lod="2",
            title_lod_observations="1",
            missing_title_lod_requests="0",
            native_draw="private_shadow_replay",
            xenos_draw="preserved",
            output_authority="xenos",
            suppression_eligible="false",
        ),
    ]
    return [config, summary, *signatures]


class VisibilityShadowReplayTests(unittest.TestCase):
    def test_qualifies_complete_bounded_private_replay(self):
        document = MODULE.build(fixture())
        self.assertEqual("complete", document["status"])
        self.assertTrue(
            document["qualification"]["broad_visibility_workset_replay_proved"]
        )
        self.assertFalse(document["qualification"]["suppression_allowed"])
        self.assertEqual(2, len(document["signatures"]))

    def test_fails_when_any_replay_is_unsupported(self):
        events = fixture()
        summary = events[1]
        summary["recorded"] = "2"
        summary["unsupported"] = "1"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn("one or more private replays failed", document["failures"])

    def test_rejects_safety_or_accounting_drift(self):
        unsafe = fixture()
        unsafe[1]["draw_suppression"] = "true"
        with self.assertRaisesRegex(ValueError, "safety boundary"):
            MODULE.build(unsafe)

        drifted = fixture()
        drifted[1]["prepared_observations"] = "15"
        document = MODULE.build(drifted)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "prepared selection accounting drifted", document["failures"]
        )

    def test_rejects_duplicate_signature_summary(self):
        events = fixture()
        duplicate = copy.deepcopy(events[-1])
        duplicate["signature"] = events[-2]["signature"]
        events[-1] = duplicate
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE.build(events)


if __name__ == "__main__":
    unittest.main()
