import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/summarize-native-renderer-track-prepared-layout.py"
SPEC = importlib.util.spec_from_file_location("track_prepared_layout", TOOL)
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
    constants = ";".join(
        f"{register}:3F800000:00000000:00000000:3F800000"
        for register in range(4, 8)
    )
    entry = event(
        MODULE.ENTRY,
        layout_key="0123456789ABCDEF",
        vertex_shader="1111222233334444",
        track_render_root="10000000",
        track_render_child="10000010",
        track_render_descriptor="10000020",
        track_render_descriptor_payload="10000030",
        calls="12",
        first_frame="100",
        last_frame="110",
        vertex_float_constant_count="4",
        vertex_float_constants=constants,
        pixel_float_constant_count="0",
        pixel_float_constants="",
        **safety(),
    )
    summary = event(
        MODULE.SUMMARY,
        checkpoint_kind="final",
        command_prepared_draw_joins="12",
        prepared_layout_observations="12",
        prepared_layout_exact="12",
        prepared_layout_entries="1",
        prepared_layout_unbounded_geometry="0",
        prepared_layout_parameter_overflows="0",
        prepared_layout_table_overflow="0",
        prepared_layout_accounting_complete="true",
        native_draw="false",
        **safety(),
    )
    return [
        event("process.start"),
        entry,
        summary,
        event("process.shutdown"),
    ]


class TrackPreparedLayoutTests(unittest.TestCase):
    def test_summarizes_exact_layout_and_candidate_run(self):
        document = MODULE.build(fixture())
        self.assertEqual("complete", document["status"])
        self.assertEqual(12, document["totals"]["prepared_layout_exact"])
        run = document["vertex_consecutive_register_runs"][0]
        self.assertEqual((4, 7, 4), (
            run["start_register"], run["end_register"], run["register_count"]
        ))
        self.assertFalse(
            document["qualification"]["world_transform_constant_layout_proved"]
        )

    def test_rejects_nonfinite_constant(self):
        events = fixture()
        events[1]["vertex_float_constants"] = events[1][
            "vertex_float_constants"
        ].replace("3F800000", "7F800000", 1)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            MODULE.build(events)

    def test_reports_accounting_drift(self):
        events = copy.deepcopy(fixture())
        events[2]["prepared_layout_exact"] = "11"
        document = MODULE.build(events)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "prepared layout call accounting drifted", document["failures"]
        )

    def test_runtime_census_is_shutdown_only_and_observation_only(self):
        source = (ROOT / "src/native_renderer/graphics_hooks.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("kTrackWorldPreparedLayoutCapacity = 1024", source)
        self.assertIn("RecordTrackWorldPreparedLayout", source)
        self.assertIn("track_world_prepared_layout_entry", source)
        summary = source.split(
            "void EmitTrackRenderModelRuntimeJoinSummary()", 1
        )[1].split("void EmitTrackRenderModelRuntimeJoinCheckpoint", 1)[0]
        self.assertIn("EmitTrackWorldPreparedLayoutEntries", summary)
        checkpoint = source.split(
            "void EmitTrackRenderModelRuntimeJoinCheckpoint", 1
        )[1].split("void EmitStaticWorldRuntimeJoinEvent", 1)[0]
        self.assertNotIn("EmitTrackWorldPreparedLayoutEntries", checkpoint)


if __name__ == "__main__":
    unittest.main()
