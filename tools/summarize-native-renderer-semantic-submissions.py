"""Validate bounded procedural-model resource and geometry submissions."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-semantic-submissions.v2"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
PREFIX = "native_renderer.discovery.semantic_submission_"
EXPECTED_CLASS = "proceduralGeometry::CProceduralModels"
EXPECTED_CLASSIFICATION = "resolved_resource_and_state_variant_submission"
EXPECTED_HOOKS = (
    "82417A74",
    "82417A9C",
    "82415C50",
    "82415C6C",
    "82417B60",
)
EXPECTED_MAXIMUM_PAYLOAD_BYTES = 56


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


def _boolean(mapping: dict, key: str) -> bool:
    value = str(mapping.get(key, "")).lower()
    if value not in ("true", "false"):
        raise ValueError(f"invalid boolean field: {key}")
    return value == "true"


def _require_safety(mapping: dict) -> None:
    expected = {
        "guest_payload_read": "bounded_submission_fields_only",
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
        "fallback": "xenos_replay",
    }
    if any(str(mapping.get(key)).lower() != value for key, value in expected.items()):
        raise ValueError("semantic-submission evidence violates the safety boundary")


def _select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"semantic-submission session not found: {requested}")
        return requested
    armed = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == f"{PREFIX}config"
        and event.get("status") == "armed"
    ]
    if not armed or not armed[-1]:
        raise ValueError("no armed semantic-submission session found")
    return armed[-1]


def _validate_static(static: dict) -> None:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    lifecycle = static.get("procedural_model_receiver_lifecycle", {})
    extraction = lifecycle.get("semantic_submission_extraction", {})
    if not lifecycle.get("rtti_vtable_identity_proved"):
        raise ValueError("procedural-model receiver RTTI identity is unproved")
    if not all(
        extraction.get(key)
        for key in (
            "resource_binding_derivation_proved",
            "resolved_resource_object_derivation_proved",
            "record_join_proved",
            "geometry_submission_derivation_proved",
            "descriptor_kind_partition_proved",
            "helper_state_partition_proved",
        )
    ):
        raise ValueError("procedural-model submission derivation is unproved")
    hooks = tuple(
        extraction.get(key)
        for key in (
            "primary_resource_binding_hook_address",
            "secondary_resource_binding_hook_address",
            "resource_resolution_result_hook_address",
            "resource_bind_dispatch_hook_address",
            "geometry_submission_hook_address",
        )
    )
    if (
        hooks != EXPECTED_HOOKS
        or extraction.get("resource_binding_helper_function_address") != "82415BF8"
        or extraction.get("resource_binding_slots") != [0, 1]
        or extraction.get("graphics_submission_primitive") != 13
        or extraction.get("graphics_submission_count_scale") != 4
        or extraction.get("classification") != EXPECTED_CLASSIFICATION
        or extraction.get("native_rendering_enabled") is not False
        or extraction.get("suppression_eligible") is not False
    ):
        raise ValueError("unsupported semantic submission contract")


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    _validate_static(static)
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
        raise ValueError("semantic-submission session needs one armed config and summary")

    entries = []
    entry_calls = 0
    expected_payload_bytes = 0
    secondary_calls = 0
    descriptor_kinds: collections.Counter[int] = collections.Counter()
    helper_states: collections.Counter[int] = collections.Counter()
    descriptor_kind_groups: collections.Counter[str] = collections.Counter()
    helper_state_families: collections.Counter[str] = collections.Counter()
    source_contracts: collections.Counter[str] = collections.Counter()
    resource_pairs: set[tuple[str, str, str, str]] = set()
    for event in selected:
        if event.get("event") != f"{PREFIX}entry":
            continue
        _require_safety(event)
        if event.get("class") != EXPECTED_CLASS:
            raise ValueError("semantic-submission entry has an unexpected receiver class")
        if event.get("classification") != EXPECTED_CLASSIFICATION:
            raise ValueError("semantic-submission entry has an unexpected classification")

        key = _hex(event, "key", 16)
        receiver_address = _hex(event, "receiver_address", 8)
        graphics_context = _hex(event, "graphics_context", 8)
        resource_lookup_context = _hex(event, "resource_lookup_context", 8)
        primary_resource_key = _hex(event, "primary_resource_key", 8)
        primary_bound_resource_object = _hex(
            event, "primary_bound_resource_object", 8
        )
        secondary_resource_key = _hex(event, "secondary_resource_key", 8)
        secondary_bound_resource_object = _hex(
            event, "secondary_bound_resource_object", 8
        )
        runtime_submission_object = _hex(event, "runtime_submission_object", 8)
        source_address = _hex(event, "source_address", 8)
        calls = _integer(event, "calls")
        first_frame = _integer(event, "first_frame")
        last_frame = _integer(event, "last_frame")
        generation = _integer(event, "receiver_generation")
        record_index = _integer(event, "record_index")
        descriptor_kind = _integer(event, "descriptor_kind")
        helper_state = _integer(event, "helper_state")
        primary_index = _integer(event, "primary_resource_index")
        secondary_present = _boolean(event, "secondary_resource_present")
        secondary_index = _integer(event, "secondary_resource_index")
        primitive_type = _integer(event, "primitive_type")
        count_units = _integer(event, "count_units")
        count_bytes = _integer(event, "count_bytes")
        source_contract = str(event.get("source_contract", ""))
        descriptor_kind_group = str(event.get("descriptor_kind_group", ""))
        helper_state_family = str(event.get("helper_state_family", ""))

        expected_kind_group = (
            "kind_4_5"
            if descriptor_kind in (4, 5)
            else "kind_1_3"
            if descriptor_kind in (1, 3)
            else "other"
        )
        expected_state_family = (
            "state_9_table_4_28"
            if helper_state == 9
            else "state_11_table_196_220"
            if helper_state == 11
            else "state_24_27_table_148_172"
            if 24 <= helper_state <= 27
            else "state_6_8_table_100_124"
            if 6 <= helper_state <= 8
            else "default_table_52_76"
        )

        if (
            calls <= 0
            or generation <= 0
            or first_frame > last_frame
            or record_index < 0
            or primary_index < 0
            or primitive_type != 13
            or count_units < 0
            or count_bytes != ((count_units << 2) & 0xFFFFFFFF)
            or int(receiver_address, 16) == 0
            or int(graphics_context, 16) == 0
            or int(resource_lookup_context, 16) == 0
            or int(primary_bound_resource_object, 16) == 0
            or int(runtime_submission_object, 16) == 0
            or int(source_address, 16) == 0
            or descriptor_kind_group != expected_kind_group
            or helper_state_family != expected_state_family
        ):
            raise ValueError("semantic-submission entry has invalid structural evidence")
        if secondary_present != (secondary_index >= 0):
            raise ValueError("semantic-submission secondary resource presence is inconsistent")
        if secondary_present != (int(secondary_bound_resource_object, 16) != 0):
            raise ValueError("semantic-submission resolved secondary resource is inconsistent")
        if source_contract == "runtime_record_24_default":
            if count_units != 0:
                raise ValueError("default geometry source has a nonzero count")
        elif source_contract != "runtime_record_28_32":
            raise ValueError("semantic-submission source contract is invalid")

        entry_calls += calls
        expected_payload_bytes += calls * (56 if secondary_present else 52)
        secondary_calls += calls if secondary_present else 0
        descriptor_kinds[descriptor_kind] += calls
        helper_states[helper_state] += calls
        descriptor_kind_groups[descriptor_kind_group] += calls
        helper_state_families[helper_state_family] += calls
        source_contracts[source_contract] += calls
        resource_pairs.add(
            (
                primary_resource_key,
                primary_bound_resource_object,
                secondary_resource_key,
                secondary_bound_resource_object,
            )
        )
        entries.append(
            {
                "key": key,
                "calls": calls,
                "frames": [first_frame, last_frame],
                "receiver_address": receiver_address,
                "receiver_generation": generation,
                "record_index": record_index,
                "descriptor_kind": descriptor_kind,
                "helper_state": helper_state,
                "graphics_context": graphics_context,
                "resource_lookup_context": resource_lookup_context,
                "resources": {
                    "primary_index": primary_index,
                    "primary_key": primary_resource_key,
                    "primary_bound_object": primary_bound_resource_object,
                    "secondary_present": secondary_present,
                    "secondary_index": secondary_index,
                    "secondary_key": secondary_resource_key,
                    "secondary_bound_object": secondary_bound_resource_object,
                },
                "state_variant": {
                    "descriptor_kind_group": descriptor_kind_group,
                    "helper_state_family": helper_state_family,
                },
                "geometry": {
                    "runtime_submission_object": runtime_submission_object,
                    "primitive_type": primitive_type,
                    "count_units": count_units,
                    "count_bytes": count_bytes,
                    "source_address": source_address,
                    "source_contract": source_contract,
                },
                "fallback": "xenos_replay",
            }
        )

    summary = summaries[0]
    _require_safety(summary)
    if summary.get("classification") != EXPECTED_CLASSIFICATION:
        raise ValueError("semantic-submission summary has an unexpected classification")
    totals = {
        key: _integer(summary, key)
        for key in (
            "observations",
            "live_observations",
            "unknown_receivers",
            "binding_mismatches",
            "invalid_record_joins",
            "invalid_resource_joins",
            "unresolved_resource_joins",
            "invalid_geometry",
            "primary_binding_observations",
            "secondary_binding_observations",
            "resource_resolution_attempts",
            "resource_resolution_successes",
            "resource_resolution_misses",
            "resource_resolution_cache_hits",
            "resource_bind_dispatches",
            "resource_resolution_protocol_faults",
            "payload_bytes",
            "maximum_payload_bytes_per_live_observation",
            "replay_fallbacks",
            "native_admissions",
            "entries",
            "capacity",
            "overflow",
        )
    }
    failures = []
    if totals["observations"] != sum(
        totals[key]
        for key in (
            "live_observations",
            "unknown_receivers",
            "binding_mismatches",
            "invalid_record_joins",
            "invalid_resource_joins",
            "unresolved_resource_joins",
            "invalid_geometry",
        )
    ):
        failures.append("observation accounting is incomplete")
    if totals["live_observations"] != totals["replay_fallbacks"]:
        failures.append("not every live observation retained Xenos replay")
    if totals["maximum_payload_bytes_per_live_observation"] != EXPECTED_MAXIMUM_PAYLOAD_BYTES:
        failures.append("bounded payload contract changed")
    if entry_calls + totals["overflow"] != totals["live_observations"]:
        failures.append("entry accounting is inconsistent")
    if totals["entries"] != len(entries):
        failures.append("entry count is inconsistent")
    if not totals["overflow"] and totals["payload_bytes"] != expected_payload_bytes:
        failures.append("payload accounting is inconsistent")
    if totals["primary_binding_observations"] != totals["observations"]:
        failures.append("primary binding accounting is inconsistent")
    if not totals["overflow"] and totals["secondary_binding_observations"] != secondary_calls:
        failures.append("secondary binding accounting is inconsistent")
    total_binding_observations = (
        totals["primary_binding_observations"]
        + totals["secondary_binding_observations"]
    )
    if total_binding_observations != (
        totals["resource_resolution_attempts"]
        + totals["resource_resolution_cache_hits"]
    ):
        failures.append("resource resolution observation accounting is inconsistent")
    if totals["resource_resolution_attempts"] != (
        totals["resource_resolution_successes"]
        + totals["resource_resolution_misses"]
    ):
        failures.append("resource resolution result accounting is inconsistent")
    if totals["resource_bind_dispatches"] != totals["resource_resolution_successes"]:
        failures.append("resource bind dispatch accounting is inconsistent")
    for key in (
        "unknown_receivers",
        "binding_mismatches",
        "invalid_record_joins",
        "invalid_resource_joins",
        "unresolved_resource_joins",
        "invalid_geometry",
        "resource_resolution_misses",
        "resource_resolution_protocol_faults",
        "overflow",
        "native_admissions",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
    if not entries:
        failures.append("no semantic submissions were observed")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "entries": entries,
        "totals": totals,
        "coverage": {
            "descriptor_kinds": dict(sorted(descriptor_kinds.items())),
            "helper_states": dict(sorted(helper_states.items())),
            "descriptor_kind_groups": dict(sorted(descriptor_kind_groups.items())),
            "helper_state_families": dict(sorted(helper_state_families.items())),
            "source_contracts": dict(sorted(source_contracts.items())),
            "unique_resource_pairs": len(resource_pairs),
        },
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
