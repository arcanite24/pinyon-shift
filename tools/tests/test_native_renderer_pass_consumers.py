import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "native_renderer_pass_consumers",
    ROOT / "tools/summarize-native-renderer-pass-consumers.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

ANCHOR = "747837906D0BF484"
FOLLOWER = "1D253A52B55C9FB3"


def event(kind, **fields):
    return {
        "event": f"native_renderer.census.pass_family_{kind}",
        "session": "session-1",
        "anchor_signature": ANCHOR,
        "follower_signature": FOLLOWER,
        "xenos_draw": "preserved",
        "suppression_eligible": "false",
        **{key: str(value) for key, value in fields.items()},
    }


def summary(**overrides):
    values = {
        "family_occurrences": 2,
        "family_resolves": 2,
        "family_resolve_bytes": 8192,
        "sampled_resolves": 1,
        "sampled_draws": 1,
        "sample_references": 2,
        "overwritten_unsampled": 1,
        "active_unsampled": 0,
        "superseded_without_resolve": 8,
        "consumer_signature_count": 1,
        "consumer_signature_overflow": 0,
        "unprepared_consumer_draws": 0,
        "unprepared_consumer_references": 0,
        "prepared_metadata_count": 1,
        "prepared_metadata_missing": 0,
        "detail_events": 3,
        "detail_overflow": 0,
        "classification": "bounded_exact_family_lineage",
        "guest_gpu_consumers": "observed",
    }
    values.update(overrides)
    return event("consumer_summary", **values)


def consumer_signature(signature="0123456789ABCDEF", sample_events=1, **fields):
    values = {
        "consumer_signature": signature,
        "sample_events": sample_events,
        "first_frame": 10,
        "last_frame": 10,
        "query_sample_events": 0,
        "memexport_sample_events": 0,
        "family_base_fetch_mask": "0000000000000001",
        "family_mip_fetch_mask": "0000000000000000",
        "vertex_shader": "1111111111111111",
        "pixel_shader": "2222222222222222",
        "vertex_specialization_mask": "0000000000000001",
        "pixel_specialization_mask": "0000000000000002",
        "prepared_pipeline_hash": "3333333333333333",
        "prepared_metadata": "observed",
    }
    values.update(fields)
    return event("consumer_signature", **values)


def guest_cpu_target(**overrides):
    values = {
        "address": "00100000",
        "latest_length": 4096,
        "resolve_count": 2,
        "read_page_events": 0,
        "write_page_events": 0,
        "read_generations": 0,
        "write_generations": 0,
        "guest_cpu_read": "unobserved",
    }
    values.update(overrides)
    return event("guest_cpu_target", **values)


def guest_cpu_summary(**overrides):
    values = {
        "armed_resolves": 2,
        "armed_bytes": 8192,
        "target_count": 1,
        "target_overflow": 0,
        "read_page_events": 0,
        "write_page_events": 0,
        "read_generations": 0,
        "write_generations": 0,
        "observation_complete": "true",
        "guest_cpu_visibility": "pass",
        "classification": "bounded_no_guest_cpu_read_observed",
    }
    values.update(overrides)
    return event("guest_cpu_summary", **values)


class PassConsumerSummaryTests(unittest.TestCase):
    def write(self, root, records, add_cpu=True):
        records = list(records)
        has_consumer_summary = any(
            record.get("event")
            == "native_renderer.census.pass_family_consumer_summary"
            for record in records
        )
        has_cpu_summary = any(
            record.get("event")
            == "native_renderer.census.pass_family_guest_cpu_summary"
            for record in records
        )
        if add_cpu and has_consumer_summary and not has_cpu_summary:
            records.extend([guest_cpu_target(), guest_cpu_summary()])
        path = Path(root) / "diagnostics.jsonl"
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def write_classifier(self, root, rules, **overrides):
        document = {
            "schema": MODULE.CONSUMER_CLASSIFIER_SCHEMA,
            "producer_family": {
                "anchor_signature": ANCHOR,
                "follower_signature": FOLLOWER,
            },
            "maximum_drift_records": 32,
            "rules": rules,
        }
        document.update(overrides)
        path = Path(root) / "consumer-classifier.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_summarizes_complete_observed_lineage(self):
        records = [
            event("resolve", address="1000"),
            event("consumer", consumer_signature="0123456789ABCDEF"),
            event("resolve", address="2000"),
            consumer_signature(),
            summary(),
        ]
        with tempfile.TemporaryDirectory() as temp:
            result = MODULE.summarize([self.write(temp, records)])
        self.assertEqual("complete", result["lineage_status"])
        self.assertEqual("complete", result["classification_status"])
        self.assertEqual("observed", result["guest_gpu_consumers"])
        self.assertFalse(result["safety"]["suppression_allowed"])
        self.assertFalse(result["safety"]["unobserved_means_independent"])
        self.assertEqual(1, len(result["consumer_shader_families"]))
        self.assertEqual(
            "unknown_unclassified",
            result["consumer_shader_families"][0]["semantic_role"],
        )
        self.assertFalse(result["consumer_shader_families"][0]["native_coverage"])
        self.assertEqual(1, result["consumer_shader_families"][0]["rank"])
        self.assertEqual(
            1_000_000,
            result["consumer_shader_families"][0]["sample_share_ppm"],
        )
        self.assertEqual(
            "fail", result["admission"]["later_gpu_consumers"]["status"]
        )
        self.assertEqual(
            "pass", result["admission"]["guest_cpu_visibility"]["status"]
        )
        self.assertEqual(2, result["guest_cpu_visibility"]["counts"]["armed_resolves"])

    def test_unobserved_consumers_remain_fail_closed(self):
        record = summary(
            sampled_resolves=0,
            sampled_draws=0,
            sample_references=0,
            consumer_signature_count=0,
            prepared_metadata_count=0,
            detail_events=2,
            guest_gpu_consumers="unobserved",
        )
        with tempfile.TemporaryDirectory() as temp:
            result = MODULE.summarize(
                [self.write(temp, [event("resolve"), event("resolve"), record])]
            )
        self.assertEqual("unobserved", result["guest_gpu_consumers"])
        self.assertIn("not proof", result["interpretation"])
        self.assertFalse(result["safety"]["suppression_allowed"])
        self.assertEqual(
            "unknown", result["admission"]["later_gpu_consumers"]["status"]
        )

    def test_rejects_missing_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, [event("resolve")])
            with self.assertRaisesRegex(ValueError, "no matching completed"):
                MODULE.summarize([path])

    def test_rejects_missing_guest_cpu_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, [summary()], add_cpu=False)
            with self.assertRaisesRegex(ValueError, "guest CPU visibility summary"):
                MODULE.summarize([path])

    def test_guest_cpu_read_closes_gate_as_failure(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            guest_cpu_target(
                read_page_events=1,
                read_generations=1,
                guest_cpu_read="observed",
            ),
            guest_cpu_summary(
                read_page_events=1,
                read_generations=1,
                guest_cpu_visibility="fail",
                classification="guest_cpu_read_observed",
            ),
            summary(),
        ]
        with tempfile.TemporaryDirectory() as temp:
            result = MODULE.summarize([self.write(temp, records)])
        self.assertEqual(
            "fail", result["admission"]["guest_cpu_visibility"]["status"]
        )

    def test_rejects_unsafe_event(self):
        unsafe = summary(suppression_eligible="true")
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, [unsafe])
            with self.assertRaisesRegex(ValueError, "unsafe suppression_eligible"):
                MODULE.summarize([path])

    def test_rejects_inconsistent_detail_count(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, [event("resolve"), summary()])
            with self.assertRaisesRegex(ValueError, "detail event count"):
                MODULE.summarize([path])

    def test_marks_signature_overflow_incomplete(self):
        record = summary(consumer_signature_overflow=1)
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            record,
        ]
        with tempfile.TemporaryDirectory() as temp:
            result = MODULE.summarize([self.write(temp, records)])
        self.assertEqual("incomplete", result["lineage_status"])

    def test_reports_missing_prepared_metadata_as_incomplete(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(
                prepared_metadata="missing",
                vertex_specialization_mask="unknown",
                pixel_specialization_mask="unknown",
                prepared_pipeline_hash="unknown",
            ),
            summary(prepared_metadata_count=0, prepared_metadata_missing=1),
        ]
        with tempfile.TemporaryDirectory() as temp:
            result = MODULE.summarize([self.write(temp, records)])
        self.assertEqual("complete", result["lineage_status"])
        self.assertEqual("incomplete", result["classification_status"])
        self.assertEqual([], result["consumer_shader_families"])
        self.assertEqual(1, result["classification_counts"]["unclassified_signatures"])
        self.assertEqual(
            1, result["classification_counts"]["unclassified_sample_events"]
        )

    def test_rejects_prepared_metadata_count_mismatch(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            summary(prepared_metadata_count=0, prepared_metadata_missing=1),
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, records)
            with self.assertRaisesRegex(ValueError, "prepared metadata summary"):
                MODULE.summarize([path])

    def test_rejects_consumer_sample_total_mismatch(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(sample_events=2),
            summary(),
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, records)
            with self.assertRaisesRegex(ValueError, "sample totals"):
                MODULE.summarize([path])

    def test_rejects_impossible_unprepared_consumer_counts(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            summary(
                unprepared_consumer_draws=2,
                unprepared_consumer_references=1,
            ),
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = self.write(temp, records)
            with self.assertRaisesRegex(ValueError, "provisional references"):
                MODULE.summarize([path])

    def test_groups_pipeline_variants_by_shader_specialization(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            consumer_signature(
                signature="FEDCBA9876543210",
                prepared_pipeline_hash="4444444444444444",
            ),
            summary(
                sampled_draws=2,
                sample_references=2,
                consumer_signature_count=2,
                prepared_metadata_count=2,
            ),
        ]
        with tempfile.TemporaryDirectory() as temp:
            result = MODULE.summarize([self.write(temp, records)])
        families = result["consumer_shader_families"]
        self.assertEqual(1, len(families))
        self.assertEqual(2, families[0]["signature_count"])
        self.assertEqual(2, families[0]["pipeline_hash_count"])
        self.assertEqual(1_000_000, families[0]["sample_share_ppm"])
        self.assertFalse(families[0]["suppression_eligible"])

    def test_applies_exact_consumer_family_classifier(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            summary(),
        ]
        rule = {
            "shader_family_id": (
                "1111111111111111/2222222222222222/"
                "0000000000000001/0000000000000002"
            ),
            "semantic_role": "retained_unknown",
            "confidence": "identity_only",
            "evidence": "exact family observed in the qualified scene",
            "native_coverage": False,
        }
        with tempfile.TemporaryDirectory() as temp:
            classifier = self.write_classifier(temp, [rule])
            result = MODULE.summarize(
                [self.write(temp, records)], classifier_path=classifier
            )
        family = result["consumer_shader_families"][0]
        classification = result["consumer_family_classification"]
        self.assertTrue(family["classifier_match"])
        self.assertEqual("retained_unknown", family["semantic_role"])
        self.assertEqual("identity_only", family["semantic_confidence"])
        self.assertFalse(family["native_coverage"])
        self.assertEqual("complete", classification["identity_status"])
        self.assertEqual("incomplete", classification["semantic_status"])
        self.assertEqual(1, classification["retained_unknown_family_count"])
        self.assertEqual([], classification["drift_records"])

    def test_reports_bounded_consumer_classifier_drift(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            summary(),
        ]
        with tempfile.TemporaryDirectory() as temp:
            classifier = self.write_classifier(
                temp, [], maximum_drift_records=0
            )
            result = MODULE.summarize(
                [self.write(temp, records)], classifier_path=classifier
            )
        classification = result["consumer_family_classification"]
        self.assertEqual("drift_observed", classification["identity_status"])
        self.assertEqual([], classification["drift_records"])
        self.assertEqual(1, classification["drift_overflow"])
        self.assertFalse(result["safety"]["suppression_allowed"])

    def test_rejects_unsafe_consumer_classifier_native_coverage(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            summary(),
        ]
        rule = {
            "shader_family_id": (
                "1111111111111111/2222222222222222/"
                "0000000000000001/0000000000000002"
            ),
            "semantic_role": "post_process",
            "confidence": "high",
            "evidence": "fixture",
            "native_coverage": True,
        }
        with tempfile.TemporaryDirectory() as temp:
            classifier = self.write_classifier(temp, [rule])
            with self.assertRaisesRegex(ValueError, "native_coverage false"):
                MODULE.summarize(
                    [self.write(temp, records)], classifier_path=classifier
                )

    def test_rejects_consumer_classifier_for_different_producer(self):
        records = [
            event("resolve"),
            event("consumer"),
            event("resolve"),
            consumer_signature(),
            summary(),
        ]
        with tempfile.TemporaryDirectory() as temp:
            classifier = self.write_classifier(
                temp,
                [],
                producer_family={
                    "anchor_signature": "AAAAAAAAAAAAAAAA",
                    "follower_signature": FOLLOWER,
                },
            )
            with self.assertRaisesRegex(ValueError, "anchor does not match"):
                MODULE.summarize(
                    [self.write(temp, records)], classifier_path=classifier
                )


if __name__ == "__main__":
    unittest.main()
