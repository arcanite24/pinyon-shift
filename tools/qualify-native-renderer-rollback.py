#!/usr/bin/env python3
"""Qualify enabled/disabled rollback for the exact retained-pass family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


OUTPUT_SCHEMA = "pinyon-shift.native-renderer-rollback-qualification.v1"


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


def qualify(enabled_path: Path, disabled_path: Path) -> dict[str, Any]:
    enabled = _load(enabled_path)
    disabled = _load(disabled_path)
    enabled_start = _one(enabled, "process.start")
    disabled_start = _one(disabled, "process.start")
    executable_sha256 = str(enabled_start.get("executable_sha256", ""))
    _require(len(executable_sha256) == 64, "enabled executable SHA-256 is missing")
    _require(
        executable_sha256 == str(disabled_start.get("executable_sha256", "")),
        "enabled and disabled runs must use the same executable",
    )
    _one(enabled, "process.shutdown")
    _one(disabled, "process.shutdown")

    enabled_control = _one(enabled, "native_renderer.suppression_control")
    _require(enabled_control.get("requested") == "true", "enabled run was not requested")
    _require(
        enabled_control.get("status") == "armed_experimental",
        "enabled run was not armed",
    )
    _require(
        enabled_control.get("implementation") == "fail_closed_follower_draw",
        "enabled run used an unexpected implementation",
    )
    _require(enabled_control.get("resolve_suppression") == "false", "resolve suppression observed")
    enabled_summary = _one(enabled, "native_renderer.suppression_summary")
    attempts = _integer(enabled_summary, "attempts")
    suppressed = _integer(enabled_summary, "suppressed")
    fallbacks = _integer(enabled_summary, "fallbacks")
    _require(enabled_summary.get("status") == "active", "enabled suppression was not active")
    _require(attempts > 0 and suppressed == attempts, "not every enabled attempt suppressed the follower")
    _require(fallbacks == 0, "enabled qualification observed a fallback")
    _require(enabled_summary.get("anchor_draw") == "preserved", "anchor draw was not preserved")
    _require(enabled_summary.get("resolve_suppression") == "false", "enabled run suppressed resolves")
    publication = _one(enabled, "native_renderer.retained_pass.publication_summary")
    _require(_integer(publication, "attempts") == attempts, "publication attempt count drift")
    _require(_integer(publication, "published") == attempts, "publication was incomplete")
    _require(_integer(publication, "failures") == 0, "publication failure observed")

    disabled_control = _one(disabled, "native_renderer.suppression_control")
    _require(disabled_control.get("requested") == "false", "disabled run requested suppression")
    _require(disabled_control.get("status") == "disabled", "disabled run did not roll back")
    suppressed_details = [
        event
        for event in disabled
        if event.get("event") == "native_renderer.retained_pass.publication"
        and event.get("draw_suppression") == "follower"
    ]
    _require(not suppressed_details, "disabled run still suppressed a follower draw")

    return {
        "schema": OUTPUT_SCHEMA,
        "family": "sky_horizon",
        "scope": "exact_follower_draw_after_full_pair_publication",
        "executable_sha256": executable_sha256,
        "enabled": {
            "session": enabled_start.get("session"),
            "attempts": attempts,
            "suppressed": suppressed,
            "fallbacks": fallbacks,
            "normal_shutdown": True,
        },
        "disabled": {
            "session": disabled_start.get("session"),
            "status": "disabled",
            "suppressed": 0,
            "normal_shutdown": True,
        },
        "gate": {"rollback_switch": "pass"},
        "safety": {
            "default_enabled": False,
            "activation": "startup_only",
            "anchor_xenos_draw_preserved": True,
            "follower_xenos_fallback": "mandatory_on_failure",
            "resolve_suppression_implemented": False,
            "suppression_scope": "scene_bounded_operator_requested_only",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enabled-log", type=Path, required=True)
    parser.add_argument("--disabled-log", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = qualify(args.enabled_log, args.disabled_log)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
