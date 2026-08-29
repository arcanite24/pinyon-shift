import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "qualify-native-renderer-publication.py"
SPEC = importlib.util.spec_from_file_location("publication_qualification", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ANCHOR = "747837906D0BF484"
FOLLOWER = "1D253A52B55C9FB3"
FAMILY = "2E5E0A854BE00027/BDFFA72B7ED2FBA4/000000000000003F/000000000016003F"


def comparison(schema):
    return {
        "schema": schema,
        "result": "pass",
        "identity": {"signature": FOLLOWER, "same_guest_frame": True},
        "metrics": {
            "compared_bytes": 4096,
            "different_bytes": 0,
            "exact_active_bytes": True,
        },
        "safety": {
            "xenos_draw_preserved": True,
            "output_authority": "xenos",
            "suppression_allowed": False,
            "gpu_wait_added": False,
        },
    }


def fixtures():
    return {
        "color": comparison(MODULE.COLOR_SCHEMA),
        "depth": comparison(MODULE.DEPTH_SCHEMA),
        "publication": {
            "schema": MODULE.PUBLICATION_SCHEMA,
            "producer_family": {
                "anchor_signature": ANCHOR,
                "follower_signature": FOLLOWER,
            },
            "publication": {
                "status": "pass",
                "attempts": 8,
                "published": 8,
                "failures": 0,
            },
            "safety": {
                "xenos_draws_preserved": True,
                "side_effects_preserved": True,
                "draw_suppression": False,
                "resolve_suppression": False,
                "suppression_allowed": False,
            },
        },
        "consumers": {
            "schema": MODULE.CONSUMER_SCHEMA,
            "anchor_signature": ANCHOR,
            "follower_signature": FOLLOWER,
            "lineage_status": "complete",
            "classification_status": "complete",
            "guest_gpu_consumers": "observed",
            "counts": {
                "consumer_signature_count": 2,
                "consumer_signature_overflow": 0,
                "prepared_metadata_missing": 0,
            },
            "consumer_shader_families": [{"shader_family_id": FAMILY}],
            "safety": {"xenos_authority": True, "suppression_allowed": False},
        },
        "corpus": {
            "schema": MODULE.CORPUS_SCHEMA,
            "consumer_family": FAMILY,
            "sample_count": 4,
            "aggregate": {
                "all_samples_complete": True,
                "samples_with_color_delta": 0,
                "samples_with_depth_stencil_delta": 1,
            },
            "safety": {
                "output_authority": "xenos",
                "xenos_draw_preserved": True,
                "draw_suppression": False,
                "resolve_suppression": False,
                "suppression_allowed": False,
            },
        },
    }


def write_documents(root, documents):
    paths = {}
    for name, document in documents.items():
        path = root / f"{name}.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        paths[name] = path
    return paths


class PublicationQualificationTests(unittest.TestCase):
    def test_exact_publication_preserves_observed_consumers(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_documents(Path(temporary), fixtures())
            report = MODULE.qualify(
                paths["color"], paths["depth"], paths["publication"],
                paths["consumers"], paths["corpus"]
            )
            self.assertEqual("pass", report["result"])
            self.assertEqual("pass", report["admission"]["later_gpu_consumers"])
            self.assertEqual(2, report["proof"]["observed_consumer_signatures"])
            self.assertTrue(report["safety"]["xenos_consumers_preserved"])
            self.assertFalse(report["safety"]["suppression_allowed"])

    def test_rejects_inexact_producer_output(self):
        documents = fixtures()
        documents["depth"]["metrics"]["different_bytes"] = 1
        documents["depth"]["metrics"]["exact_active_bytes"] = False
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_documents(Path(temporary), documents)
            with self.assertRaisesRegex(ValueError, "depth/stencil is not exact"):
                MODULE.qualify(paths["color"], paths["depth"], paths["publication"], paths["consumers"], paths["corpus"])

    def test_rejects_partial_publication(self):
        documents = fixtures()
        documents["publication"]["publication"]["published"] = 7
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_documents(Path(temporary), documents)
            with self.assertRaisesRegex(ValueError, "not every publication"):
                MODULE.qualify(paths["color"], paths["depth"], paths["publication"], paths["consumers"], paths["corpus"])

    def test_rejects_incomplete_or_unobserved_consumers(self):
        for field, value, message in (
            ("classification_status", "partial", "classification"),
            ("guest_gpu_consumers", "unobserved", "not observed"),
        ):
            documents = fixtures()
            documents["consumers"][field] = value
            with tempfile.TemporaryDirectory() as temporary:
                paths = write_documents(Path(temporary), documents)
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.qualify(paths["color"], paths["depth"], paths["publication"], paths["consumers"], paths["corpus"])

    def test_rejects_corpus_without_a_real_consumer_contribution(self):
        documents = fixtures()
        documents["corpus"]["aggregate"]["samples_with_depth_stencil_delta"] = 0
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_documents(Path(temporary), documents)
            with self.assertRaisesRegex(ValueError, "no observed attachment"):
                MODULE.qualify(paths["color"], paths["depth"], paths["publication"], paths["consumers"], paths["corpus"])

    def test_rejects_any_unsafe_evidence(self):
        documents = fixtures()
        documents["publication"]["safety"]["draw_suppression"] = True
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_documents(Path(temporary), documents)
            with self.assertRaisesRegex(ValueError, "suppressed draws"):
                MODULE.qualify(paths["color"], paths["depth"], paths["publication"], paths["consumers"], paths["corpus"])


if __name__ == "__main__":
    unittest.main()
