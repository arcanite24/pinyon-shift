#!/usr/bin/env python3
"""Qualify NR-04E/04F state yield for an exact suppression family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "pinyon-shift.native-renderer-state-yield-qualification.v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        _require(isinstance(value, dict), f"{path}:{line_number} is not an object")
        events.append(value)
    _require(bool(events), f"{path} is empty")
    return events


def _one(events: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [event for event in events if event.get("event") == name]
    _require(len(matches) == 1, f"expected one {name} event, found {len(matches)}")
    return matches[0]


def _integer(event: dict[str, Any], name: str) -> int:
    try:
        value = int(str(event[name]))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{event.get('event')} has invalid {name}") from error
    _require(value >= 0, f"{event.get('event')}.{name} must be non-negative")
    return value


def qualify(log_path: Path) -> dict[str, Any]:
    events = _load(log_path)
    start = _one(events, "process.start")
    _one(events, "process.shutdown")
    executable_sha256 = str(start.get("executable_sha256", ""))
    _require(len(executable_sha256) == 64, "executable SHA-256 is missing")

    control = _one(events, "native_renderer.suppression_control")
    _require(control.get("requested") == "true", "suppression was not requested")
    _require(control.get("status") == "armed_experimental", "suppression was not armed")
    _require(
        control.get("state_gate") == "consecutive_publication_warmup",
        "state warmup gate was not armed",
    )
    warmup_required = _integer(control, "warmup_frames")
    cooldown_frames = _integer(control, "failure_cooldown_frames")
    _require(warmup_required > 0, "warmup frame count must be positive")
    _require(cooldown_frames > 0, "failure cooldown must be positive")

    transitions = [
        event
        for event in events
        if event.get("event") == "native_renderer.suppression_state"
    ]
    _require(
        any(
            event.get("previous") == "warming"
            and event.get("current") == "active"
            and event.get("reason") == "warmup_complete"
            for event in transitions
        ),
        "warmup-to-active transition was not observed",
    )

    summary = _one(events, "native_renderer.suppression_summary")
    attempts = _integer(summary, "attempts")
    suppressed = _integer(summary, "suppressed")
    fallbacks = _integer(summary, "fallbacks")
    unexpected_suppressions = _integer(summary, "unexpected_suppressions")
    yielded = _integer(summary, "yielded_attempts")
    warmup_publications = _integer(summary, "warmup_publications")
    cooldown_entries = _integer(summary, "cooldown_entries")
    _require(summary.get("status") == "active", "suppression never became active")
    _require(summary.get("runtime_state") == "active", "runtime did not finish active")
    _require(attempts > 0 and suppressed == attempts, "active attempts were not fail-closed")
    _require(fallbacks == 0, "an active suppression attempt fell back")
    _require(
        unexpected_suppressions == 0,
        "the backend suppressed a draw while the state gate yielded",
    )
    _require(yielded > 0, "state gate never yielded to Xenos")
    _require(warmup_publications >= warmup_required, "warmup evidence is incomplete")
    _require(cooldown_entries == 0, "qualification encountered a publication cooldown")
    for field in ("pm4_parsing", "query_event_fence", "memexport", "resolves_consumers"):
        _require(summary.get(field) == "preserved", f"{field} was not preserved")
    _require(summary.get("resolve_suppression") == "false", "resolve suppression observed")
    _require(summary.get("anchor_draw") == "preserved", "anchor draw was not preserved")

    publication = _one(events, "native_renderer.retained_pass.publication_summary")
    total_publications = attempts + yielded
    _require(_integer(publication, "attempts") == total_publications, "publication count drift")
    _require(_integer(publication, "published") == total_publications, "publication was incomplete")
    _require(_integer(publication, "failures") == 0, "publication failure observed")

    return {
        "schema": OUTPUT_SCHEMA,
        "family": "sky_horizon",
        "executable_sha256": executable_sha256,
        "session": start.get("session"),
        "state_gate": {
            "warmup_frames": warmup_required,
            "failure_cooldown_frames": cooldown_frames,
            "yielded_attempts": yielded,
            "warmup_publications": warmup_publications,
            "warmup_to_active": "pass",
        },
        "suppression": {
            "attempts": attempts,
            "suppressed": suppressed,
            "fallbacks": fallbacks,
            "unexpected_suppressions": unexpected_suppressions,
        },
        "gate": {"state_based_yield": "pass", "guest_side_effects": "pass"},
        "safety": {
            "xenos_on_warmup": True,
            "xenos_on_gap_or_failure": True,
            "anchor_draw_preserved": True,
            "resolve_suppression": False,
            "side_effects_preserved": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = qualify(args.log)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
