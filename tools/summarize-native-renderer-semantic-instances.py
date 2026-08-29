"""Validate bounded procedural-model semantic-instance observations."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-semantic-instances.v1"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
PREFIX = "native_renderer.discovery.semantic_instance_"
EXPECTED_CLASS = "proceduralGeometry::CProceduralModels"
EXPECTED_WORDS = 88
EXPECTED_PAYLOAD_BYTES = 380


def read_events(paths: list[pathlib.Path]) -> list[dict]:
    events = []
    for path in paths:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if str(event.get("event", "")).startswith(PREFIX):
                events.append(event)
    return events


def _integer(mapping: dict, key: str) -> int:
    try:
        return int(mapping.get(key, ""))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid integer field: {key}") from error


def _hex(mapping: dict, key: str, width: int) -> str:
    value = str(mapping.get(key, "")).upper()
    if len(value) != width:
        raise ValueError(f"invalid hexadecimal field: {key}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid hexadecimal field: {key}") from error
    return value


def _hex_arguments(mapping: dict, key: str) -> list[str]:
    values = str(mapping.get(key, "")).upper().split(",")
    if len(values) != 7:
        raise ValueError(f"invalid argument vector: {key}")
    for value in values:
        _hex({key: value}, key, 8)
    return values


def _require_safety(mapping: dict) -> None:
    expected = {
        "guest_payload_read": "bounded_semantic_records_only",
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
        "fallback": "xenos_replay",
    }
    if any(str(mapping.get(key)).lower() != value for key, value in expected.items()):
        raise ValueError("semantic-instance evidence violates the safety boundary")


def _select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"semantic-instance session not found: {requested}")
        return requested
    armed = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == f"{PREFIX}config"
        and event.get("status") == "armed"
    ]
    if not armed or not armed[-1]:
        raise ValueError("no armed semantic-instance session found")
    return armed[-1]


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    lifecycle = static.get("procedural_model_receiver_lifecycle", {})
    extraction = lifecycle.get("semantic_instance_extraction", {})
    if not lifecycle.get("rtti_vtable_identity_proved"):
        raise ValueError("procedural-model receiver RTTI identity is unproved")
    if not all(
        extraction.get(key)
        for key in ("argument_mapping_proved", "record_address_derivation_proved")
    ):
        raise ValueError("procedural-model semantic record derivation is unproved")
    if (
        extraction.get("hook_address") != "8241741C"
        or extraction.get("bounded_payload_bytes_per_observation")
        != EXPECTED_PAYLOAD_BYTES
        or extraction.get("native_rendering_enabled") is not False
        or extraction.get("suppression_eligible") is not False
    ):
        raise ValueError("unsupported semantic extraction contract")

    session = _select_session(events, requested)
    selected = [event for event in events if event.get("session") == session]
    configs = [
        event
        for event in selected
        if event.get("event") == f"{PREFIX}config"
        and event.get("status") == "armed"
    ]
    summaries = [
        event for event in selected if event.get("event") == f"{PREFIX}summary"
    ]
    if len(configs) != 1 or len(summaries) != 1:
        raise ValueError("semantic-instance session needs one armed config and summary")

    entries = []
    entry_calls = 0
    for event in selected:
        if event.get("event") != f"{PREFIX}entry":
            continue
        _require_safety(event)
        if event.get("class") != EXPECTED_CLASS:
            raise ValueError("semantic-instance entry has an unexpected receiver class")
        key = _hex(event, "key", 16)
        receiver_address = _hex(event, "receiver_address", 8)
        descriptor_address = _hex(event, "descriptor_address", 8)
        runtime_address = _hex(event, "runtime_address", 8)
        descriptor_hash = _hex(event, "descriptor_hash", 16)
        runtime_hash = _hex(event, "runtime_hash", 16)
        transform_hash = _hex(event, "transform_hash", 16)
        helper_arguments = _hex_arguments(event, "helper_arguments")
        calls = _integer(event, "calls")
        first_frame = _integer(event, "first_frame")
        last_frame = _integer(event, "last_frame")
        generation = _integer(event, "receiver_generation")
        record_index = _integer(event, "record_index")
        descriptor_count = _integer(event, "descriptor_count")
        if (
            calls <= 0
            or generation <= 0
            or first_frame > last_frame
            or record_index < 0
            or descriptor_count <= record_index
            or int(descriptor_address, 16) & 3
            or int(runtime_address, 16) & 3
            or _integer(event, "immutable_sample_words") != EXPECTED_WORDS
            or event.get("classification") != "unclassified_material_or_state"
        ):
            raise ValueError("semantic-instance entry has invalid immutable evidence")
        entry_calls += calls
        entries.append(
            {
                "key": key,
                "calls": calls,
                "frames": [first_frame, last_frame],
                "receiver_address": receiver_address,
                "receiver_generation": generation,
                "record_index": record_index,
                "descriptor_count": descriptor_count,
                "descriptor_address": descriptor_address,
                "runtime_address": runtime_address,
                "descriptor_kind": _integer(event, "descriptor_kind"),
                "helper_arguments": helper_arguments,
                "hashes": {
                    "descriptor": descriptor_hash,
                    "runtime": runtime_hash,
                    "transform": transform_hash,
                },
                "variations": {
                    "descriptor": _integer(event, "descriptor_variations"),
                    "runtime": _integer(event, "runtime_variations"),
                    "transform": _integer(event, "transform_variations"),
                },
                "fallback": "xenos_replay",
            }
        )

    summary = summaries[0]
    _require_safety(summary)
    totals = {
        key: _integer(summary, key)
        for key in (
            "observations",
            "live_observations",
            "unknown_receivers",
            "invalid_layouts",
            "invalid_indices",
            "payload_bytes",
            "replay_fallbacks",
            "native_admissions",
            "entries",
            "capacity",
            "overflow",
            "payload_bytes_per_live_observation",
        )
    }
    failures = []
    if totals["observations"] != sum(
        totals[key]
        for key in (
            "live_observations",
            "unknown_receivers",
            "invalid_layouts",
            "invalid_indices",
        )
    ):
        failures.append("observation accounting is incomplete")
    if totals["live_observations"] != totals["replay_fallbacks"]:
        failures.append("not every live observation retained Xenos replay")
    if totals["payload_bytes_per_live_observation"] != EXPECTED_PAYLOAD_BYTES:
        failures.append("bounded payload contract changed")
    if totals["payload_bytes"] != totals["live_observations"] * EXPECTED_PAYLOAD_BYTES:
        failures.append("payload accounting is inconsistent")
    if entry_calls + totals["overflow"] != totals["live_observations"]:
        failures.append("entry accounting is inconsistent")
    if totals["entries"] != len(entries):
        failures.append("entry count is inconsistent")
    for key in (
        "unknown_receivers",
        "invalid_layouts",
        "invalid_indices",
        "overflow",
        "native_admissions",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
    if not entries:
        failures.append("no semantic instances were observed")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "entries": entries,
        "totals": totals,
        "safety": {
            "bounded_guest_read": True,
            "guest_state_changed": False,
            "native_upload": False,
            "native_draw": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        report = build(
            read_events(args.logs),
            json.loads(args.static.read_text(encoding="utf-8")),
            args.session,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
