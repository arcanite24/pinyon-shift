#!/usr/bin/env python3
"""Build a bounded machine-readable inventory from renderer census JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "pinyon-shift.native-renderer-census.v1"
PREFIX = "native_renderer.census."
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSIFIER = ROOT / "config/native-renderer/pass-classifier.json"


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
                    events.append(event)
    return events


def integer(event: dict[str, Any], key: str) -> int:
    return int(event.get(key, 0))


def select_session(events: list[dict[str, Any]], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"census session not found: {requested}")
        return requested
    installed = [
        event.get("session", "")
        for event in events
        if event.get("event") == f"{PREFIX}installed"
    ]
    candidates = installed or [event.get("session", "") for event in events]
    if not candidates or not candidates[-1]:
        raise ValueError("no native-renderer census session found")
    return str(candidates[-1])


def load_classifier(path: Path) -> dict[str, Any]:
    classifier = json.loads(path.read_text(encoding="utf-8"))
    if classifier.get("schema") != "pinyon-shift.pass-classifier.v1":
        raise ValueError(f"unsupported pass-classifier schema: {path}")
    return classifier


def classify_signatures(
    signatures: list[dict[str, Any]], scene: str, classifier: dict[str, Any]
) -> dict[str, Any]:
    matches: dict[str, dict[str, str]] = {}
    for rule in classifier.get("rules", []):
        if rule.get("scene") != scene:
            continue
        for signature in rule.get("signatures", []):
            if signature in matches:
                raise ValueError(f"duplicate classifier signature for {scene}: {signature}")
            matches[signature] = rule

    family_draws: dict[str, int] = {}
    classified_draws = 0
    drift: list[dict[str, Any]] = []
    for signature in signatures:
        draws = integer(signature, "draws")
        rule = matches.get(str(signature["signature"]))
        if rule:
            family = str(rule["family"])
            confidence = str(rule["confidence"])
            evidence = str(rule["evidence"])
            classified_draws += draws
        else:
            family = "retained_unknown"
            confidence = "unknown"
            evidence = "no exact scene-qualified rule; Xenos retained"
            drift.append(
                {
                    "signature": signature["signature"],
                    "draws": draws,
                    "reason": "unmatched_signature",
                }
            )
        signature.update(
            {"family": family, "confidence": confidence, "evidence": evidence}
        )
        family_draws[family] = family_draws.get(family, 0) + draws

    observed_draws = sum(integer(signature, "draws") for signature in signatures)
    limit = int(classifier.get("maximum_drift_records", 32))
    drift.sort(key=lambda record: (-record["draws"], record["signature"]))
    return {
        "scene": scene,
        "observed_draws": observed_draws,
        "classified_draws": classified_draws,
        "classified_percent": (
            round(classified_draws * 100.0 / observed_draws, 3)
            if observed_draws
            else 0.0
        ),
        "families": [
            {"family": family, "draws": draws}
            for family, draws in sorted(family_draws.items())
        ],
        "drift_count": len(drift),
        "drift_overflow": max(0, len(drift) - limit),
        "drift": drift[:limit],
        "unknown_policy": "retained_on_xenos",
    }


def summarize(
    paths: Iterable[Path], session: str | None = None,
    classifier_path: Path = DEFAULT_CLASSIFIER,
) -> dict[str, Any]:
    paths = list(paths)
    events = read_events(paths)
    selected_session = select_session(events, session)
    events = [event for event in events if event.get("session") == selected_session]
    marker_events = [
        event for event in events if event.get("event") == f"{PREFIX}scene_marker"
    ]
    scene = str(marker_events[-1].get("scene", "unmarked")) if marker_events else "unmarked"

    draw_signatures: dict[str, dict[str, Any]] = {}
    draw_candidates: dict[str, dict[str, Any]] = {}
    prepared_shader_pairs: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    dependencies: dict[str, dict[str, Any]] = {}
    resolve_targets: dict[str, dict[str, Any]] = {}
    totals = {
        "draws": 0,
        "resolves": 0,
        "resolve_bytes": 0,
        "sampled_draws": 0,
        "sample_references": 0,
        "query_draws": 0,
        "memexport_draws": 0,
        "draw_overflow": 0,
        "candidate_windows": 0,
        "candidate_eligible_signatures": 0,
        "candidate_eligible_draws": 0,
        "candidate_overflow": 0,
        "target_overflow": 0,
        "page_overflow": 0,
    }

    for event in events:
        kind = event.get("event")
        if kind == f"{PREFIX}draw_window":
            totals["draws"] += integer(event, "draws")
            totals["draw_overflow"] += integer(event, "overflow_draws")
        elif kind == f"{PREFIX}candidate_window":
            totals["candidate_windows"] += 1
            totals["candidate_eligible_signatures"] += integer(
                event, "eligible_signatures"
            )
            totals["candidate_eligible_draws"] += integer(event, "eligible_draws")
            totals["candidate_overflow"] += integer(event, "overflow_draws")
        elif kind == f"{PREFIX}draw_signature":
            key = str(event["signature"])
            record = draw_signatures.get(key)
            if record is None:
                draw_signatures[key] = dict(event)
            else:
                record["draws"] = str(integer(record, "draws") + integer(event, "draws"))
                record["first_frame"] = str(
                    min(integer(record, "first_frame"), integer(event, "first_frame"))
                )
                record["last_frame"] = str(
                    max(integer(record, "last_frame"), integer(event, "last_frame"))
                )
        elif kind == f"{PREFIX}draw_candidate":
            key = str(event["signature"])
            record = draw_candidates.get(key)
            if record is None:
                draw_candidates[key] = dict(event)
            else:
                record["draws"] = str(integer(record, "draws") + integer(event, "draws"))
                record["first_frame"] = str(
                    min(integer(record, "first_frame"), integer(event, "first_frame"))
                )
                record["last_frame"] = str(
                    max(integer(record, "last_frame"), integer(event, "last_frame"))
                )
                for field in ("index_count_min", "index_buffer_length_min"):
                    if field in record and field in event:
                        record[field] = str(
                            min(integer(record, field), integer(event, field))
                        )
                if "index_count_max" in record and "index_count_max" in event:
                    record["index_count_max"] = str(
                        max(
                            integer(record, "index_count_max"),
                            integer(event, "index_count_max"),
                        )
                    )
        elif kind == f"{PREFIX}prepared_shader_pair":
            key = (
                str(event["vertex_shader"]),
                str(event["pixel_shader"]),
                str(event["vertex_specialization_mask"]),
                str(event["pixel_specialization_mask"]),
            )
            prepared_shader_pairs.setdefault(key, dict(event))
        elif kind == f"{PREFIX}resolve_window":
            for key in (
                "resolves",
                "resolve_bytes",
                "sampled_draws",
                "sample_references",
                "query_draws",
                "memexport_draws",
            ):
                totals[key] += integer(event, key)
            for key in ("target_overflow", "page_overflow"):
                totals[key] = max(totals[key], integer(event, key))
        elif kind == f"{PREFIX}resolve_dependency":
            dependencies.setdefault(str(event["address"]), dict(event))
        elif kind == f"{PREFIX}resolve_target":
            address = str(event["address"])
            existing = resolve_targets.get(address)
            if existing is None or integer(event, "last_resolve_frame") >= integer(
                existing, "last_resolve_frame"
            ):
                resolve_targets[address] = dict(event)

    for address, target in resolve_targets.items():
        if address in dependencies:
            dependencies[address].update(
                {
                    key: target[key]
                    for key in (
                        "resolves",
                        "resolved_bytes",
                        "sampled_draws",
                        "sample_references",
                        "conditional_sample_draws",
                        "query_state_sample_draws",
                        "memexport_sample_draws",
                    )
                    if key in target
                }
            )

    private_fields = {"pid", "tid", "utc", "schema", "event", "session"}
    clean = lambda event: {key: value for key, value in event.items() if key not in private_fields}
    cleaned_signatures = [
        clean(record)
        for _, record in sorted(
            draw_signatures.items(), key=lambda item: (-integer(item[1], "draws"), item[0])
        )
    ]
    classification = classify_signatures(
        cleaned_signatures, scene, load_classifier(classifier_path)
    )
    return {
        "schema": SCHEMA,
        "session": selected_session,
        "sources": [str(path) for path in paths],
        "totals": totals,
        "classification": classification,
        "draw_signatures": cleaned_signatures,
        "draw_candidates": [
            clean(record)
            for _, record in sorted(
                draw_candidates.items(),
                key=lambda item: (-integer(item[1], "draws"), item[0]),
            )
        ],
        "prepared_shader_pairs": [
            clean(record) for _, record in sorted(prepared_shader_pairs.items())
        ],
        "resolve_dependencies": [
            clean(record) for _, record in sorted(dependencies.items())
        ],
        "resolve_targets": [
            clean(record) for _, record in sorted(resolve_targets.items())
        ],
        "safety": {
            "suppression_allowed": False,
            "guest_cpu_reads": "unknown_uninstrumented",
            "presentation_only": "unknown_uninstrumented",
            "semantic_roles": "unknown_unclassified",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path, help="diagnostic JSONL files")
    parser.add_argument("--session", help="specific diagnostic session id")
    parser.add_argument(
        "--classifier", type=Path, default=DEFAULT_CLASSIFIER,
        help="pass-classifier manifest",
    )
    parser.add_argument("--output", "-o", type=Path, help="write inventory JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = summarize(args.logs, args.session, args.classifier)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
