#!/usr/bin/env python3
"""Validate retained-pass publication diagnostics without enabling suppression."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "pinyon-shift.native-renderer-pass-publication.v1"
CONFIG_EVENT = "native_renderer.retained_pass.publication_config"
PUBLICATION_EVENT = "native_renderer.retained_pass.publication"
SUMMARY_EVENT = "native_renderer.retained_pass.publication_summary"
SAFETY_FIELDS = {
    "xenos_draw": "preserved",
    "draw_suppression": "false",
    "resolve_suppression": "false",
    "side_effects": "preserved",
    "suppression_eligible": "false",
}


def _read_events(paths: Iterable[Path]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"{path}:{line_number}: invalid JSON: {error}"
                    ) from error
                if event.get("event") in {
                    CONFIG_EVENT,
                    PUBLICATION_EVENT,
                    SUMMARY_EVENT,
                }:
                    event["_source"] = str(path)
                    event["_line"] = line_number
                    events.append(event)
    return events


def _one(events: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [event for event in events if event.get("event") == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} event, found {len(matches)}")
    return matches[0]


def _positive_int(event: dict[str, Any], name: str) -> int:
    try:
        value = int(event[name])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{event.get('event')}: invalid {name}") from error
    if value <= 0:
        raise ValueError(f"{event.get('event')}: {name} must be positive")
    return value


def _nonnegative_int(event: dict[str, Any], name: str) -> int:
    try:
        value = int(event[name])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{event.get('event')}: invalid {name}") from error
    if value < 0:
        raise ValueError(f"{event.get('event')}: {name} must be nonnegative")
    return value


def _require_safety(event: dict[str, Any]) -> None:
    for field, expected in SAFETY_FIELDS.items():
        if str(event.get(field, "")) != expected:
            raise ValueError(
                f"{event.get('event')}: unsafe {field}={event.get(field)!r}"
            )


def summarize(paths: Iterable[Path]) -> dict[str, Any]:
    path_list = list(paths)
    events = _read_events(path_list)
    config = _one(events, CONFIG_EVENT)
    summary = _one(events, SUMMARY_EVENT)
    publications = [
        event for event in events if event.get("event") == PUBLICATION_EVENT
    ]
    _require_safety(config)
    _require_safety(summary)
    for publication in publications:
        _require_safety(publication)

    config_status = str(config.get("status", ""))
    if config_status not in {"disabled", "armed", "invalid_configuration"}:
        raise ValueError("publication config has invalid status")
    anchor = str(config.get("anchor_signature", ""))
    follower = str(config.get("follower_signature", ""))
    if config_status == "armed":
        for name, value in (("anchor", anchor), ("follower", follower)):
            if len(value) != 16 or any(
                character not in "0123456789ABCDEF" for character in value
            ):
                raise ValueError(f"armed publication has invalid {name} signature")
    detail_limit = _positive_int(config, "detail_limit")
    if config.get("guest_target_content") != "xenos_until_successful_publication":
        raise ValueError("publication config has invalid guest target authority")
    if summary.get("guest_target_content") != "per_attempt":
        raise ValueError("publication summary has invalid guest target authority")

    samples: list[dict[str, Any]] = []
    successful = 0
    for publication in publications:
        if str(publication.get("anchor_signature", "")) != anchor or str(
            publication.get("follower_signature", "")
        ) != follower:
            raise ValueError("publication event signature drift")
        status = str(publication.get("status", ""))
        if status not in {
            "published",
            "incomplete",
            "unsupported_path",
            "target_mismatch",
            "unavailable",
        }:
            raise ValueError(f"publication event has invalid status {status!r}")
        color = str(publication.get("color", ""))
        depth = str(publication.get("depth_stencil", ""))
        published = status == "published" and color == depth == "published"
        expected_content = "native_retained_pass" if published else "xenos"
        if publication.get("guest_target_content") != expected_content:
            raise ValueError("publication event has invalid guest target authority")
        successful += int(published)
        dimension = _positive_int if published else _nonnegative_int
        sample = {
            "frame": _positive_int(publication, "frame"),
            "draw": _positive_int(publication, "follower_draw"),
            "target_width": dimension(publication, "target_width"),
            "target_height": dimension(publication, "target_height"),
            "sample_count": dimension(publication, "sample_count"),
            "status": status,
            "guest_target_content": expected_content,
            "complete_attachment_pair": published,
        }
        samples.append(sample)

    attempts = _nonnegative_int(summary, "attempts")
    published_count = _nonnegative_int(summary, "published")
    failures = _nonnegative_int(summary, "failures")
    detail_events = _nonnegative_int(summary, "detail_events")
    detail_overflow = _nonnegative_int(summary, "detail_overflow")
    if detail_events != len(publications):
        raise ValueError("publication summary detail count mismatch")
    if attempts != detail_events + detail_overflow:
        raise ValueError("publication summary attempt count mismatch")
    if detail_events > detail_limit or (
        detail_overflow and detail_events != detail_limit
    ):
        raise ValueError("publication summary violates detail limit")
    if published_count + failures != attempts:
        raise ValueError("publication summary failure count mismatch")
    if successful != detail_events and failures == 0:
        raise ValueError("publication detail contradicts complete summary")
    complete = (
        config_status == "armed"
        and bool(samples)
        and published_count == attempts
        and failures == 0
        and str(summary.get("status", "")) == "complete"
    )

    return {
        "schema": SCHEMA,
        "source": [str(path) for path in path_list],
        "producer_family": {
            "anchor_signature": anchor,
            "follower_signature": follower,
        },
        "configuration": {
            "status": config_status,
            "activation": config.get("activation"),
            "default_enabled": config.get("default_enabled"),
            "fallback": config.get("fallback"),
            "detail_limit": detail_limit,
        },
        "publication": {
            "status": "pass" if complete else "incomplete",
            "attempts": attempts,
            "published": published_count,
            "failures": failures,
            "detail_events": detail_events,
            "detail_overflow": detail_overflow,
            "samples": samples,
        },
        "safety": {
            "xenos_draws_preserved": True,
            "draw_suppression": False,
            "resolve_suppression": False,
            "side_effects_preserved": True,
            "suppression_allowed": False,
            "later_gpu_consumers_gate": "qualification_required",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        report = summarize(args.logs)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    if args.require_complete and report["publication"]["status"] != "pass":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
