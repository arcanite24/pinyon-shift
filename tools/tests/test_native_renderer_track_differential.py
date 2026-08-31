import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "summarize-native-renderer-track-differential.py"
SPEC = importlib.util.spec_from_file_location("native_track_differential", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def events(session, mode, calls):
    common = {"schema": 1, "session": session}
    expected = MODULE.MODE_VALUES[mode]
    return [
        {"event": "process.start", **common, "executable_sha256": "EXE", "rexglue_patch_set_sha256": "PATCH", "rexglue_patch_count": "102"},
        {"event": MODULE.CONFIG, **common, "status": "complete", "mode": mode, "fast_track_render": "true" if expected[0] else "false", "road_detail_blur": "true" if expected[1] else "false", "track_command_buffers": "true" if expected[2] else "false", "track_far_distance": str(expected[3]), "address_consistent": "true", "xenos_authority": "true", "native_draw": "false", "suppression_allowed": "false"},
        {"event": MODULE.INSTALLED, **common, "scene": "open_world_day"},
        {"event": MODULE.DRAW_WINDOW, **common, "first_frame": "1", "last_frame": "600", "draws": "1200", "overflow_draws": "0"},
        {"event": MODULE.PROVENANCE, **common, "outcome": "prepared", "semantic_identity": "procedural_model_submission", "prepared_signature": "AABBCCDDEEFF0011", "calls": str(calls), "semantic_vertex_shader": "1111111111111111", "semantic_pixel_shader": "2222222222222222", "semantic_template_key": "3333333333333333", "semantic_receiver_address": "AAAABBBB", "semantic_receiver_generation": "1", "semantic_record_index": "7", "xenos_draw": "preserved", "suppression_eligible": "false"},
        {"event": "process.shutdown", **common},
    ]


class NativeRendererTrackDifferentialTests(unittest.TestCase):
    def test_qualifies_exact_title_track_delta_without_semantic_promotion(self):
        document = MODULE.build(
            events("baseline-session", "baseline", 60),
            events("track-session", "fasttrackrender", 120),
        )
        self.assertEqual("complete", document["status"])
        self.assertEqual(1, document["changed_family_count"])
        self.assertEqual(100.0, document["changed_families"][0]["delta_calls_per_1000_frames"])
        self.assertTrue(document["qualification"]["title_track_render_delta_proved"])
        self.assertFalse(document["qualification"]["terrain_road_semantic_identity_proved"])
        self.assertFalse(document["qualification"]["native_admission_allowed"])

    def test_rejects_unconfirmed_title_argument(self):
        track = events("track-session", "fasttrackrender", 120)
        track[1]["fast_track_render"] = "false"
        document = MODULE.build(events("baseline-session", "baseline", 60), track)
        self.assertEqual("incomplete", document["status"])
        self.assertIn(
            "fasttrackrender: fast-track runtime value does not match the requested mode",
            document["failures"],
        )

    def test_rejects_build_identity_drift(self):
        track = events("track-session", "fasttrackrender", 120)
        track[0]["executable_sha256"] = "OTHER"
        document = MODULE.build(events("baseline-session", "baseline", 60), track)
        self.assertIn("paired sessions do not use one build identity", document["failures"])

    def test_qualifies_road_detail_blur_as_an_isolated_variant(self):
        document = MODULE.build(
            events("baseline-session", "baseline", 60),
            events("road-session", "noroaddetailblur", 120),
            track_mode="noroaddetailblur",
        )
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            "noroaddetailblur", document["qualification"]["isolated_mode"]
        )
        self.assertEqual(
            120, document["changed_families"][0]["noroaddetailblur_calls"]
        )

    def test_qualifies_track_far_distance_as_an_isolated_variant(self):
        document = MODULE.build(
            events("baseline-session", "baseline", 60),
            events("far-session", "trackfardistance", 120),
            track_mode="trackfardistance",
        )
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            "trackfardistance", document["qualification"]["isolated_mode"]
        )

    def test_qualifies_disabled_track_command_buffers_as_an_isolated_variant(self):
        document = MODULE.build(
            events("baseline-session", "baseline", 60),
            events("command-session", "notrackcommandbuffers", 120),
            track_mode="notrackcommandbuffers",
        )
        self.assertEqual("complete", document["status"])
        self.assertEqual(
            "notrackcommandbuffers",
            document["qualification"]["isolated_mode"],
        )

    def test_ignores_small_normalized_rate_jitter(self):
        document = MODULE.build(
            events("baseline-session", "baseline", 60),
            events("track-session", "fasttrackrender", 61),
        )
        self.assertEqual("incomplete", document["status"])
        self.assertEqual(0, document["changed_family_count"])
        self.assertEqual(1, document["rate_noise_family_count"])


if __name__ == "__main__":
    unittest.main()
