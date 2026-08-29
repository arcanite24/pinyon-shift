#!/usr/bin/env python3
"""Qualify retained-pass publication as preservation of later Xenos consumers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "pinyon-shift.native-renderer-publication-qualification.v1"
COLOR_SCHEMA = "pinyon-shift.native-renderer-pass-readback-comparison.v1"
DEPTH_SCHEMA = "pinyon-shift.native-renderer-pass-depth-readback-comparison.v1"
PUBLICATION_SCHEMA = "pinyon-shift.native-renderer-pass-publication.v1"
CONSUMER_SCHEMA = "pinyon-shift.native-renderer-pass-consumer-inventory.v2"
CORPUS_SCHEMA = "pinyon-shift.consumer-family-contribution-corpus.v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load(path: Path, schema: str, label: str) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    _require(document.get("schema") == schema, f"unsupported {label} schema")
    return document


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _exact_comparison(document: dict[str, Any], label: str) -> int:
    _require(document.get("result") == "pass", f"{label} comparison did not pass")
    identity = document.get("identity", {})
    _require(identity.get("same_guest_frame") is True, f"{label} is not same-frame")
    metrics = document.get("metrics", {})
    _require(metrics.get("exact_active_bytes") is True, f"{label} is not exact")
    _require(metrics.get("different_bytes") == 0, f"{label} contains differences")
    compared = metrics.get("compared_bytes")
    _require(isinstance(compared, int) and compared > 0, f"{label} has no compared bytes")
    safety = document.get("safety", {})
    _require(safety.get("xenos_draw_preserved") is True, f"{label} lost Xenos draw")
    _require(safety.get("output_authority") == "xenos", f"{label} authority is unsafe")
    _require(safety.get("suppression_allowed") is False, f"{label} allows suppression")
    _require(safety.get("gpu_wait_added") is False, f"{label} added a GPU wait")
    return compared


def qualify(
    color_path: Path,
    depth_path: Path,
    publication_path: Path,
    consumers_path: Path,
    corpus_path: Path,
) -> dict[str, Any]:
    color = _load(color_path, COLOR_SCHEMA, "color comparison")
    depth = _load(depth_path, DEPTH_SCHEMA, "depth comparison")
    publication = _load(publication_path, PUBLICATION_SCHEMA, "publication")
    consumers = _load(consumers_path, CONSUMER_SCHEMA, "consumer inventory")
    corpus = _load(corpus_path, CORPUS_SCHEMA, "consumer corpus")

    color_bytes = _exact_comparison(color, "color")
    depth_bytes = _exact_comparison(depth, "depth/stencil")
    follower = color.get("identity", {}).get("signature")
    _require(follower == depth.get("identity", {}).get("signature"), "comparison signature mismatch")

    producer = publication.get("producer_family", {})
    anchor = producer.get("anchor_signature")
    _require(follower == producer.get("follower_signature"), "publication follower mismatch")
    _require(anchor == consumers.get("anchor_signature"), "consumer anchor mismatch")
    _require(follower == consumers.get("follower_signature"), "consumer follower mismatch")

    publication_result = publication.get("publication", {})
    attempts = publication_result.get("attempts")
    published = publication_result.get("published")
    _require(publication_result.get("status") == "pass", "publication did not pass")
    _require(isinstance(attempts, int) and attempts > 0, "publication has no attempts")
    _require(published == attempts, "not every publication attempt succeeded")
    _require(publication_result.get("failures") == 0, "publication contains failures")
    publication_safety = publication.get("safety", {})
    _require(publication_safety.get("xenos_draws_preserved") is True, "publication lost Xenos draws")
    _require(publication_safety.get("side_effects_preserved") is True, "publication lost side effects")
    _require(publication_safety.get("draw_suppression") is False, "publication suppressed draws")
    _require(publication_safety.get("resolve_suppression") is False, "publication suppressed resolves")
    _require(publication_safety.get("suppression_allowed") is False, "publication allows suppression")

    counts = consumers.get("counts", {})
    consumer_count = counts.get("consumer_signature_count")
    family_count = len(consumers.get("consumer_shader_families", []))
    _require(consumers.get("lineage_status") == "complete", "consumer lineage is incomplete")
    _require(consumers.get("classification_status") == "complete", "consumer classification is incomplete")
    _require(consumers.get("guest_gpu_consumers") == "observed", "later GPU consumers were not observed")
    _require(isinstance(consumer_count, int) and consumer_count > 0, "consumer inventory is empty")
    _require(family_count > 0, "consumer family inventory is empty")
    _require(counts.get("consumer_signature_overflow") == 0, "consumer inventory overflowed")
    _require(counts.get("prepared_metadata_missing") == 0, "consumer metadata is incomplete")
    consumer_safety = consumers.get("safety", {})
    _require(consumer_safety.get("xenos_authority") is True, "consumer inventory lost Xenos authority")
    _require(consumer_safety.get("suppression_allowed") is False, "consumer inventory allows suppression")

    corpus_family = corpus.get("consumer_family")
    known_families = {
        item.get("shader_family_id")
        for item in consumers.get("consumer_shader_families", [])
    }
    _require(corpus_family in known_families, "corpus family is absent from consumer inventory")
    aggregate = corpus.get("aggregate", {})
    sample_count = corpus.get("sample_count")
    _require(isinstance(sample_count, int) and sample_count > 0, "consumer corpus is empty")
    _require(aggregate.get("all_samples_complete") is True, "consumer corpus is incomplete")
    deltas = aggregate.get("samples_with_color_delta", 0) + aggregate.get(
        "samples_with_depth_stencil_delta", 0
    )
    _require(deltas > 0, "consumer corpus contains no observed attachment contribution")
    corpus_safety = corpus.get("safety", {})
    _require(corpus_safety.get("output_authority") == "xenos", "consumer corpus authority is unsafe")
    _require(corpus_safety.get("xenos_draw_preserved") is True, "consumer draw was not preserved")
    _require(corpus_safety.get("draw_suppression") is False, "consumer corpus suppressed draws")
    _require(corpus_safety.get("resolve_suppression") is False, "consumer corpus suppressed resolves")
    _require(corpus_safety.get("suppression_allowed") is False, "consumer corpus allows suppression")

    artifacts = {
        "color_comparison": color_path,
        "depth_stencil_comparison": depth_path,
        "publication": publication_path,
        "consumer_inventory": consumers_path,
        "consumer_corpus": corpus_path,
    }
    return {
        "schema": OUTPUT_SCHEMA,
        "result": "pass",
        "producer_family": {
            "anchor_signature": anchor,
            "follower_signature": follower,
        },
        "proof": {
            "native_output_exact_before_publication": True,
            "color_compared_bytes": color_bytes,
            "depth_stencil_compared_bytes": depth_bytes,
            "publication_attempts": attempts,
            "publication_failures": 0,
            "observed_consumer_signatures": consumer_count,
            "observed_consumer_families": family_count,
            "sampled_consumer_family": corpus_family,
            "consumer_samples": sample_count,
            "samples_with_attachment_contribution": deltas,
            "preservation_boundary": "publish_exact_native_targets_then_preserve_xenos_resolves_and_consumers",
        },
        "artifacts": {
            name: {"path": str(path), "sha256": _sha256(path)}
            for name, path in artifacts.items()
        },
        "admission": {
            "later_gpu_consumers": "pass",
            "scope": "exact_family_scene_bounded",
            "reason": (
                "exact native color and depth/stencil are published into the "
                "authoritative guest targets before unchanged resolves and observed "
                "Xenos consumers"
            ),
        },
        "safety": {
            "xenos_draws_preserved": True,
            "xenos_resolves_preserved": True,
            "xenos_consumers_preserved": True,
            "draw_suppression": False,
            "resolve_suppression": False,
            "suppression_allowed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--color", type=Path, required=True)
    parser.add_argument("--depth-stencil", type=Path, required=True)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--consumers", type=Path, required=True)
    parser.add_argument("--consumer-corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        report = qualify(
            arguments.color.resolve(),
            arguments.depth_stencil.resolve(),
            arguments.publication.resolve(),
            arguments.consumers.resolve(),
            arguments.consumer_corpus.resolve(),
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}")
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
