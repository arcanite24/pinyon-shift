#!/usr/bin/env python3
"""Summarize exact pass-family resolve and later-GPU-consumer diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "pinyon-shift.native-renderer-pass-consumer-inventory.v2"
PREFIX = "native_renderer.census.pass_family_"
SUMMARY_EVENT = f"{PREFIX}consumer_summary"
RESOLVE_EVENT = f"{PREFIX}resolve"
CONSUMER_EVENT = f"{PREFIX}consumer"
CONSUMER_SIGNATURE_EVENT = f"{PREFIX}consumer_signature"
SAFETY_FIELDS = {
    "xenos_draw": "preserved",
    "suppression_eligible": "false",
}
COUNT_FIELDS = (
    "family_occurrences",
    "family_resolves",
    "family_resolve_bytes",
    "sampled_resolves",
    "sampled_draws",
    "sample_references",
    "overwritten_unsampled",
    "active_unsampled",
    "superseded_without_resolve",
    "consumer_signature_count",
    "consumer_signature_overflow",
    "unprepared_consumer_draws",
    "unprepared_consumer_references",
    "prepared_metadata_count",
    "prepared_metadata_missing",
    "detail_events",
    "detail_overflow",
)
HEX_METADATA_FIELDS = (
    "consumer_signature",
    "vertex_shader",
    "pixel_shader",
    "vertex_specialization_mask",
    "pixel_specialization_mask",
    "prepared_pipeline_hash",
    "family_base_fetch_mask",
    "family_mip_fetch_mask",
)


def read_events(paths: Iterable[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
                if str(event.get("event", "")).startswith(PREFIX):
                    event["_source"] = str(path)
                    event["_line"] = line_number
                    events.append(event)
    return events


def normalize_signature(value: str) -> str:
    signature = value.upper()
    if len(signature) != 16 or any(
        character not in "0123456789ABCDEF" for character in signature
    ):
        raise ValueError(f"invalid 64-bit signature: {value!r}")
    return signature


def require_safety(event: dict[str, Any]) -> None:
    location = f"{event.get('_source')}:{event.get('_line')}"
    for key, expected in SAFETY_FIELDS.items():
        if event.get(key) != expected:
            raise ValueError(
                f"{location}: unsafe {key}={event.get(key)!r}; expected {expected!r}"
            )


def clean(event: dict[str, Any]) -> dict[str, Any]:
    private = {"pid", "tid", "utc", "schema", "event", "session", "_source", "_line"}
    return {key: value for key, value in event.items() if key not in private}


def build_shader_families(
    consumer_signatures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    families: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for event in consumer_signatures:
        if event.get("prepared_metadata") != "observed":
            continue
        normalized = {
            field: normalize_signature(str(event.get(field, "")))
            for field in HEX_METADATA_FIELDS
        }
        key = (
            normalized["vertex_shader"],
            normalized["pixel_shader"],
            normalized["vertex_specialization_mask"],
            normalized["pixel_specialization_mask"],
        )
        family = families.setdefault(
            key,
            {
                "shader_family_id": "/".join(key),
                "vertex_shader": key[0],
                "pixel_shader": key[1],
                "vertex_specialization_mask": key[2],
                "pixel_specialization_mask": key[3],
                "sample_events": 0,
                "query_sample_events": 0,
                "memexport_sample_events": 0,
                "first_frame": None,
                "last_frame": 0,
                "consumer_signatures": set(),
                "prepared_pipeline_hashes": set(),
                "family_base_fetch_mask": 0,
                "family_mip_fetch_mask": 0,
            },
        )
        try:
            sample_events = int(event["sample_events"])
            query_events = int(event["query_sample_events"])
            memexport_events = int(event["memexport_sample_events"])
            first_frame = int(event["first_frame"])
            last_frame = int(event["last_frame"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("consumer signature metadata has invalid counts") from error
        family["sample_events"] += sample_events
        family["query_sample_events"] += query_events
        family["memexport_sample_events"] += memexport_events
        family["first_frame"] = (
            first_frame
            if family["first_frame"] is None
            else min(family["first_frame"], first_frame)
        )
        family["last_frame"] = max(family["last_frame"], last_frame)
        family["consumer_signatures"].add(normalized["consumer_signature"])
        family["prepared_pipeline_hashes"].add(
            normalized["prepared_pipeline_hash"]
        )
        family["family_base_fetch_mask"] |= int(
            normalized["family_base_fetch_mask"], 16
        )
        family["family_mip_fetch_mask"] |= int(
            normalized["family_mip_fetch_mask"], 16
        )

    rendered: list[dict[str, Any]] = []
    for family in families.values():
        signatures = sorted(family.pop("consumer_signatures"))
        pipeline_hashes = sorted(family.pop("prepared_pipeline_hashes"))
        family.update(
            {
                "signature_count": len(signatures),
                "consumer_signatures": signatures,
                "pipeline_hash_count": len(pipeline_hashes),
                "prepared_pipeline_hashes": pipeline_hashes,
                "family_base_fetch_mask": f"{family['family_base_fetch_mask']:016X}",
                "family_mip_fetch_mask": f"{family['family_mip_fetch_mask']:016X}",
                "semantic_role": "unknown_unclassified",
                "native_coverage": False,
                "suppression_eligible": False,
            }
        )
        rendered.append(family)
    ranked = sorted(
        rendered,
        key=lambda family: (
            -int(family["sample_events"]),
            family["vertex_shader"],
            family["pixel_shader"],
        ),
    )
    total_samples = sum(int(family["sample_events"]) for family in ranked)
    for rank, family in enumerate(ranked, 1):
        family["rank"] = rank
        family["sample_share_ppm"] = (
            int(family["sample_events"]) * 1_000_000 // total_samples
            if total_samples
            else 0
        )
    return ranked


def summarize(
    paths: Iterable[Path],
    anchor: str | None = None,
    follower: str | None = None,
    session: str | None = None,
) -> dict[str, Any]:
    paths = list(paths)
    events = read_events(paths)
    if anchor is not None:
        anchor = normalize_signature(anchor)
    if follower is not None:
        follower = normalize_signature(follower)

    summaries = [event for event in events if event.get("event") == SUMMARY_EVENT]
    if session is not None:
        summaries = [event for event in summaries if event.get("session") == session]
    if anchor is not None:
        summaries = [event for event in summaries if event.get("anchor_signature") == anchor]
    if follower is not None:
        summaries = [event for event in summaries if event.get("follower_signature") == follower]
    if not summaries:
        raise ValueError("no matching completed pass-family consumer summary found")

    summary = summaries[-1]
    selected_session = str(summary.get("session", ""))
    if not selected_session:
        raise ValueError("summary has no diagnostic session")
    selected_anchor = normalize_signature(str(summary.get("anchor_signature", "")))
    selected_follower = normalize_signature(str(summary.get("follower_signature", "")))
    require_safety(summary)
    if summary.get("classification") != "bounded_exact_family_lineage":
        raise ValueError("summary does not use the exact-family lineage classification")

    related = [
        event
        for event in events
        if event.get("session") == selected_session
        and event.get("anchor_signature") == selected_anchor
        and event.get("follower_signature") == selected_follower
    ]
    resolves = [event for event in related if event.get("event") == RESOLVE_EVENT]
    consumers = [event for event in related if event.get("event") == CONSUMER_EVENT]
    consumer_signatures = [
        event for event in related if event.get("event") == CONSUMER_SIGNATURE_EVENT
    ]
    for event in resolves + consumers + consumer_signatures:
        require_safety(event)

    counts: dict[str, int] = {}
    for field in COUNT_FIELDS:
        try:
            counts[field] = int(summary[field])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"summary has invalid {field}") from error
        if counts[field] < 0:
            raise ValueError(f"summary has negative {field}")

    if counts["family_resolves"] > counts["family_occurrences"]:
        raise ValueError("family resolves exceed observed family occurrences")
    if counts["sampled_resolves"] > counts["family_resolves"]:
        raise ValueError("sampled resolves exceed family resolves")
    if (
        counts["unprepared_consumer_draws"]
        > counts["unprepared_consumer_references"]
    ):
        raise ValueError("unprepared consumer draws exceed provisional references")
    expected_consumer_state = "observed" if counts["sampled_draws"] else "unobserved"
    if summary.get("guest_gpu_consumers") != expected_consumer_state:
        raise ValueError("guest GPU consumer classification contradicts summary counts")
    if counts["detail_events"] != len(resolves) + len(consumers):
        raise ValueError("detail event count does not match retained detail records")
    if counts["consumer_signature_count"] != len(consumer_signatures):
        raise ValueError("consumer signature count does not match aggregate records")
    if (
        counts["prepared_metadata_count"]
        + counts["prepared_metadata_missing"]
        != counts["consumer_signature_count"]
    ):
        raise ValueError("prepared metadata counts contradict signature count")
    if counts["sampled_draws"] and not consumer_signatures:
        raise ValueError("observed consumer events have no consumer signature aggregate")
    normalized_consumer_signatures = [
        normalize_signature(str(event.get("consumer_signature", "")))
        for event in consumer_signatures
    ]
    if len(set(normalized_consumer_signatures)) != len(normalized_consumer_signatures):
        raise ValueError("duplicate consumer signature aggregate")
    aggregate_sample_events = 0
    observed_prepared_metadata = 0
    for event in consumer_signatures:
        try:
            sample_events = int(event["sample_events"])
            first_frame = int(event["first_frame"])
            last_frame = int(event["last_frame"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("consumer signature aggregate has invalid counts") from error
        if sample_events <= 0 or first_frame <= 0 or last_frame < first_frame:
            raise ValueError("consumer signature aggregate has inconsistent counts")
        aggregate_sample_events += sample_events
        observed_prepared_metadata += event.get("prepared_metadata") == "observed"
    if observed_prepared_metadata != counts["prepared_metadata_count"]:
        raise ValueError("prepared metadata summary contradicts aggregate records")
    if (
        counts["consumer_signature_overflow"] == 0
        and aggregate_sample_events != counts["sampled_draws"]
    ):
        raise ValueError("consumer signature sample totals contradict summary counts")
    shader_families = build_shader_families(consumer_signatures)
    classified_sample_events = sum(
        int(family["sample_events"]) for family in shader_families
    )
    if counts["prepared_metadata_missing"] == 0 and (
        classified_sample_events != aggregate_sample_events
    ):
        raise ValueError("shader family sample totals contradict aggregate records")
    if counts["sampled_draws"]:
        classification_evidence = (
            f"{counts['prepared_metadata_count']} of "
            f"{len(consumer_signatures)} later consumer signatures are grouped "
            f"into {len(shader_families)} shader families"
        )
        if counts["prepared_metadata_missing"]:
            classification_evidence += (
                f"; {counts['prepared_metadata_missing']} signatures lack "
                "prepared metadata"
            )
        later_gpu_consumer_gate = {
            "status": "fail",
            "evidence": classification_evidence
            + "; none has a native replacement",
        }
    else:
        later_gpu_consumer_gate = {
            "status": "unknown",
            "evidence": (
                "no later consumer was observed; absence is not proof that the "
                "family has no later GPU dependency"
            ),
        }

    lineage_complete = (
        counts["family_occurrences"] > 0
        and counts["family_resolves"] > 0
        and counts["consumer_signature_overflow"] == 0
    )
    return {
        "schema": SCHEMA,
        "session": selected_session,
        "anchor_signature": selected_anchor,
        "follower_signature": selected_follower,
        "sources": [str(path) for path in paths],
        "lineage_status": "complete" if lineage_complete else "incomplete",
        "classification_status": (
            "complete"
            if lineage_complete and counts["prepared_metadata_missing"] == 0
            else "incomplete"
        ),
        "guest_gpu_consumers": expected_consumer_state,
        "counts": counts,
        "resolves": [clean(event) for event in resolves],
        "consumers": [clean(event) for event in consumers],
        "consumer_signatures": [
            clean(event)
            for event in sorted(
                consumer_signatures,
                key=lambda event: str(event["consumer_signature"]),
            )
        ],
        "consumer_shader_families": shader_families,
        "classification_counts": {
            "classified_signatures": counts["prepared_metadata_count"],
            "unclassified_signatures": counts["prepared_metadata_missing"],
            "classified_sample_events": classified_sample_events,
            "unclassified_sample_events": (
                aggregate_sample_events - classified_sample_events
            ),
        },
        "interpretation": (
            "observed consumers are proven dependencies"
            if counts["sampled_draws"]
            else "no consumer was observed; absence is not proof of independence"
        ),
        "admission": {"later_gpu_consumers": later_gpu_consumer_gate},
        "safety": {
            "xenos_authority": True,
            "suppression_allowed": False,
            "unobserved_means_independent": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--anchor")
    parser.add_argument("--follower")
    parser.add_argument("--session")
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = summarize(
            args.logs, anchor=args.anchor, follower=args.follower, session=args.session
        )
    except ValueError as error:
        print(f"error: {error}")
        return 1
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
