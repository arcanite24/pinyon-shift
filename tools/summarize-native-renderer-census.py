#!/usr/bin/env python3
"""Build a bounded machine-readable inventory from renderer census JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "pinyon-shift.native-renderer-census.v1"
PREFIX = "native_renderer.census."


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


def summarize(paths: Iterable[Path], session: str | None = None) -> dict[str, Any]:
    paths = list(paths)
    events = read_events(paths)
    selected_session = select_session(events, session)
    events = [event for event in events if event.get("session") == selected_session]

    draw_signatures: dict[str, dict[str, Any]] = {}
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
        "target_overflow": 0,
        "page_overflow": 0,
    }

    for event in events:
        kind = event.get("event")
        if kind == f"{PREFIX}draw_window":
            totals["draws"] += integer(event, "draws")
            totals["draw_overflow"] += integer(event, "overflow_draws")
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
    return {
        "schema": SCHEMA,
        "session": selected_session,
        "sources": [str(path) for path in paths],
        "totals": totals,
        "draw_signatures": [
            clean(record)
            for _, record in sorted(
                draw_signatures.items(), key=lambda item: (-integer(item[1], "draws"), item[0])
            )
        ],
        "resolve_dependencies": [
            clean(record) for _, record in sorted(dependencies.items())
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
    parser.add_argument("--output", "-o", type=Path, help="write inventory JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = summarize(args.logs, args.session)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
