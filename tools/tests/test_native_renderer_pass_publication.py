import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/summarize-native-renderer-pass-publication.py"
SPEC = importlib.util.spec_from_file_location("pass_publication", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)

ANCHOR = "747837906D0BF484"
FOLLOWER = "1D253A52B55C9FB3"
SAFETY = {
    "xenos_draw": "preserved",
    "draw_suppression": "false",
    "resolve_suppression": "false",
    "side_effects": "preserved",
    "suppression_eligible": "false",
}


def event(name, **fields):
    return {"event": name, **SAFETY, **fields}


def records(status="published"):
    published = status == "published"
    return [
        event(
            MODULE.CONFIG_EVENT,
            status="armed",
            anchor_signature=ANCHOR,
            follower_signature=FOLLOWER,
            activation="startup_only",
            default_enabled="false",
            guest_target_content="xenos_until_successful_publication",
            fallback="preserve_xenos_targets",
            detail_limit="64",
        ),
        event(
            MODULE.PUBLICATION_EVENT,
            status=status,
            anchor_signature=ANCHOR,
            follower_signature=FOLLOWER,
            frame="100",
            follower_draw="20",
            target_width="2560",
            target_height="1024",
            sample_count="4",
            color="published" if published else "preserved_xenos",
            depth_stencil="published" if published else "preserved_xenos",
            guest_target_content=(
                "native_retained_pass" if published else "xenos"
            ),
        ),
        event(
            MODULE.SUMMARY_EVENT,
            status="complete" if published else "fallback_observed",
            attempts="1",
            published="1" if published else "0",
            failures="0" if published else "1",
            detail_events="1",
            detail_overflow="0",
            guest_target_content="per_attempt",
        ),
    ]


class PassPublicationTests(unittest.TestCase):
    def write(self, directory, values):
        path = Path(directory) / "capture.jsonl"
        path.write_text(
            "".join(json.dumps(value) + "\n" for value in values),
            encoding="utf-8",
        )
        return path

    def test_accepts_complete_paired_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            report = MODULE.summarize([self.write(temp, records())])
        self.assertEqual("pass", report["publication"]["status"])
        self.assertEqual(1, report["publication"]["published"])
        self.assertTrue(
            report["publication"]["samples"][0]["complete_attachment_pair"]
        )
        self.assertFalse(report["safety"]["suppression_allowed"])

    def test_reports_fallback_as_incomplete(self):
        values = records("target_mismatch")
        values[1]["target_width"] = "0"
        values[1]["target_height"] = "0"
        values[1]["sample_count"] = "0"
        with tempfile.TemporaryDirectory() as temp:
            report = MODULE.summarize([self.write(temp, values)])
        self.assertEqual("incomplete", report["publication"]["status"])
        self.assertEqual(1, report["publication"]["failures"])
        self.assertTrue(report["safety"]["xenos_draws_preserved"])

    def test_rejects_summary_count_mismatch(self):
        values = records()
        values[-1]["attempts"] = "2"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "attempt count mismatch"):
                MODULE.summarize([self.write(temp, values)])

    def test_accepts_bounded_detail_overflow(self):
        values = records()
        values[-1]["attempts"] = "3"
        values[-1]["published"] = "3"
        values[-1]["detail_events"] = "1"
        values[-1]["detail_overflow"] = "2"
        values[0]["detail_limit"] = "1"
        with tempfile.TemporaryDirectory() as temp:
            report = MODULE.summarize([self.write(temp, values)])
        self.assertEqual("pass", report["publication"]["status"])
        self.assertEqual(2, report["publication"]["detail_overflow"])

    def test_rejects_signature_drift(self):
        values = records()
        values[1]["follower_signature"] = "AAAAAAAAAAAAAAAA"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "signature drift"):
                MODULE.summarize([self.write(temp, values)])

    def test_rejects_any_suppression_claim(self):
        values = records()
        values[1]["draw_suppression"] = "true"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "unsafe draw_suppression"):
                MODULE.summarize([self.write(temp, values)])

    def test_rejects_native_authority_on_fallback(self):
        values = records("target_mismatch")
        values[1]["guest_target_content"] = "native_retained_pass"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "guest target authority"):
                MODULE.summarize([self.write(temp, values)])


if __name__ == "__main__":
    unittest.main()
