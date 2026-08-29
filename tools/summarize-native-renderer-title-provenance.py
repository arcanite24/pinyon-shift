"""Correlate exact title PM4 packet origins with prepared backend draws."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-title-provenance.v3"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
PREFIX = "native_renderer.discovery.title_provenance_"
KNOWN_PREPARED_FAMILIES = {
    "747837906D0BF484": "retained_sky_horizon_anchor",
    "1D253A52B55C9FB3": "retained_sky_horizon_follower",
}
BACKEND_OUTCOMES = {
    "completed",
    "edram_copy",
    "missing_vertex_shader",
    "zero_surface_pitch",
    "no_rasterization_or_memexport",
    "submission_failed",
    "primitive_processing_failed",
    "no_host_vertices",
    "render_target_update_failed",
    "pipeline_configuration_failed",
    "pipeline_pending",
    "binding_update_failed",
    "invalid_vertex_fetch",
    "vertex_residency_failed",
    "memexport_residency_failed",
    "unsupported_primitive",
    "scratch_index_buffer_failed",
    "unsupported_index_buffer",
}


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


def select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"title provenance session not found: {requested}")
        return requested
    armed = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == f"{PREFIX}config"
        and event.get("status") == "armed"
    ]
    if not armed or not armed[-1]:
        raise ValueError("no armed title provenance session found")
    return armed[-1]


def _integer(mapping: dict, key: str) -> int:
    try:
        return int(mapping.get(key, 0))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid integer field: {key}") from error


def _argument_vector(mapping: dict, key: str) -> dict[str, str]:
    values = str(mapping.get(key, "")).upper().split(":")
    if len(values) != 8 or any(len(value) != 8 for value in values):
        raise ValueError(f"invalid title provenance argument vector: {key}")
    return {f"r{index}": values[index - 3] for index in range(3, 11)}


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    provenance_contract = static.get("draw_packet_provenance")
    if not isinstance(provenance_contract, dict):
        raise ValueError("static inventory has no draw packet provenance contract")
    packet_sites = provenance_contract.get("packet_sites", [])
    if {
        (item.get("wrapper"), item.get("packet_hook_address"))
        for item in packet_sites
    } != {("8240F4D8", "82410328"), ("829F7C70", "829F7CB0")}:
        raise ValueError("static draw packet provenance sites drifted")

    session = select_session(events, requested)
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
        raise ValueError("title provenance session needs one armed config and summary")
    summary = summaries[0]
    required_safety = {
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(str(summary.get(key)).lower() != value for key, value in required_safety.items()):
        raise ValueError("title provenance summary does not prove the safety boundary")
    if str(summary.get("correlation")) != "exact_physical_pm4_header_address":
        raise ValueError("title provenance summary uses an unsupported correlation key")

    static_calls = {
        (item["wrapper"], item["return_address"]): item
        for item in static.get("runtime_correlation_calls", static.get("direct_calls", []))
    }
    static_argument_leads = {
        (item["wrapper"], item["return_address"]): item
        for item in static.get("adapter_argument_leads", [])
    }
    entries = []
    for event in selected:
        if event.get("event") != f"{PREFIX}entry":
            continue
        wrapper = str(event.get("origin_wrapper_address", "")).upper()
        caller = str(event.get("origin_caller", "")).upper()
        outcome = str(event.get("outcome", ""))
        if outcome not in {"prepared", "not_prepared"}:
            raise ValueError("invalid backend outcome in title provenance entry")
        backend_outcome = str(event.get("backend_outcome", ""))
        if outcome == "prepared":
            if backend_outcome != "prepared_callback":
                raise ValueError("prepared entry has an invalid backend outcome")
        elif backend_outcome not in BACKEND_OUTCOMES:
            raise ValueError("unprepared entry has an invalid backend outcome")
        backend_signature = str(event.get("backend_signature", "")).upper()
        if len(backend_signature) != 16:
            raise ValueError("invalid backend signature in title provenance entry")
        signature = str(event.get("prepared_signature", "")).upper()
        if outcome == "prepared" and len(signature) != 16:
            raise ValueError("invalid prepared signature in title provenance entry")
        if outcome == "not_prepared" and signature:
            raise ValueError("unprepared title provenance entry has a prepared signature")
        callsite = static_calls.get((wrapper, caller))
        argument_lead = static_argument_leads.get((wrapper, caller))
        family = (
            KNOWN_PREPARED_FAMILIES.get(signature, "unknown")
            if outcome == "prepared"
            else "not_prepared"
        )
        varying_mask = int(str(event.get("varying_argument_mask", "")), 16)
        if varying_mask & ~0xFF:
            raise ValueError("invalid varying argument mask")
        minimums = _argument_vector(event, "minimum_arguments")
        maximums = _argument_vector(event, "maximum_arguments")
        entries.append(
            {
                "origin_wrapper": str(event.get("origin_wrapper", "unknown")),
                "origin_wrapper_address": wrapper,
                "origin_caller": caller,
                "outcome": outcome,
                "backend_outcome": backend_outcome,
                "backend_signature": backend_signature,
                "prepared_signature": signature or None,
                "prepared_family": family,
                "calls": _integer(event, "calls"),
                "first_frame": _integer(event, "first_frame"),
                "last_frame": _integer(event, "last_frame"),
                "first_draw": _integer(event, "first_draw"),
                "first_packet_physical_address": str(
                    event.get("first_packet_physical_address", "")
                ).upper(),
                "first_arguments": {
                    f"r{index}": str(event.get(f"first_r{index}", "")).upper()
                    for index in range(3, 11)
                },
                "last_arguments": _argument_vector(event, "last_arguments"),
                "argument_ranges": {
                    register: {
                        "minimum": minimums[register],
                        "maximum": maximums[register],
                    }
                    for register in minimums
                },
                "varying_registers": [
                    f"r{index}"
                    for index in range(3, 11)
                    if varying_mask & (1 << (index - 3))
                ],
                "stable_registers": [
                    f"r{index}"
                    for index in range(3, 11)
                    if not (varying_mask & (1 << (index - 3)))
                ],
                "static_match": (
                    {
                        "caller_function": callsite["caller_function"],
                        "caller_function_address": callsite["caller_function_address"],
                        "callsite": callsite["callsite"],
                        "wrapper_layer": callsite.get("wrapper_layer", "unknown"),
                    }
                    if callsite
                    else None
                ),
                "static_argument_lead": argument_lead,
                "semantic_identity": (
                    family
                    if outcome == "prepared" and family != "unknown"
                    else "unknown"
                ),
                "semantic_evidence": (
                    "existing_exact_prepared_signature_family"
                    if family != "unknown"
                    and outcome == "prepared"
                    else (
                        "exact_backend_draw_observed_without_prepared_callback"
                        if outcome == "not_prepared"
                        else "none"
                    )
                ),
                "native_coverage": False,
                "suppression_eligible": False,
            }
        )
    entries.sort(
        key=lambda item: (
            -item["calls"],
            item["origin_wrapper_address"],
            item["origin_caller"],
            item["backend_outcome"],
            item["backend_signature"],
        )
    )
    prepared_entries = [item for item in entries if item["outcome"] == "prepared"]
    unprepared_entries = [
        item for item in entries if item["outcome"] == "not_prepared"
    ]
    prepared_matches = sum(item["calls"] for item in prepared_entries)
    unprepared_aggregate_matches = sum(item["calls"] for item in unprepared_entries)
    outcome_entries = []
    for event in selected:
        if event.get("event") != f"{PREFIX}outcome":
            continue
        backend_outcome = str(event.get("backend_outcome", ""))
        if backend_outcome not in BACKEND_OUTCOMES:
            raise ValueError("invalid draw outcome summary entry")
        outcome_entries.append(
            {
                "backend_outcome": backend_outcome,
                "backend_draws": _integer(event, "backend_draws"),
                "title_matches": _integer(event, "title_matches"),
            }
        )
    if len({item["backend_outcome"] for item in outcome_entries}) != len(
        outcome_entries
    ):
        raise ValueError("duplicate draw outcome summary entry")
    outcome_entries.sort(key=lambda item: (-item["backend_draws"], item["backend_outcome"]))
    if prepared_matches != _integer(summary, "prepared_matches"):
        raise ValueError("title provenance entry counts do not match the summary")
    if len(entries) != _integer(summary, "aggregate_count"):
        raise ValueError("title provenance aggregate count does not match the summary")
    if len(prepared_entries) != _integer(summary, "prepared_aggregate_count"):
        raise ValueError("prepared aggregate count does not match the summary")
    if len(unprepared_entries) != _integer(summary, "unprepared_aggregate_count"):
        raise ValueError("unprepared aggregate count does not match the summary")
    if unprepared_aggregate_matches != _integer(
        summary, "unprepared_aggregate_matches"
    ):
        raise ValueError("unprepared aggregate calls do not match the summary")

    recorded = _integer(summary, "title_packets_recorded")
    backend_matches = _integer(summary, "backend_packet_matches")
    unprepared = _integer(summary, "matched_unprepared_draws")
    pending = _integer(summary, "pending_packets")
    unattributed_backend = _integer(summary, "backend_draws_without_title_packet")
    origins_pushed = _integer(summary, "origins_pushed")
    origins_consumed = _integer(summary, "origins_consumed")
    backend_outcomes_observed = _integer(summary, "backend_draw_outcomes_observed")
    title_backend_outcomes = _integer(summary, "title_backend_outcomes")
    fault_fields = (
        "packet_address_failures",
        "packet_table_overflow",
        "forwarding_mismatches",
        "origin_stack_overflow",
        "packets_without_origin",
        "aggregate_overflow",
        "backend_draw_outcome_mismatches",
        "backend_draw_outcome_missing",
    )
    faults = {field: _integer(summary, field) for field in fault_fields}
    reused_live_addresses = _integer(summary, "reused_live_packet_addresses")
    complete = (
        recorded > 0
        and str(summary.get("packet_accounting_complete")).lower() == "true"
        and str(summary.get("origin_accounting_complete")).lower() == "true"
        and recorded == backend_matches + pending
        and backend_matches == prepared_matches + unprepared
        and unprepared == unprepared_aggregate_matches
        and title_backend_outcomes == unprepared
        and sum(item["title_matches"] for item in outcome_entries) == unprepared
        and sum(item["backend_draws"] for item in outcome_entries)
        == backend_outcomes_observed
        and origins_pushed == origins_consumed
        and not any(faults.values())
    )
    callers = {}
    for entry in entries:
        key = (entry["origin_wrapper_address"], entry["origin_caller"])
        aggregate = callers.setdefault(
            key,
            {
                "origin_wrapper": entry["origin_wrapper"],
                "origin_wrapper_address": key[0],
                "origin_caller": key[1],
                "calls": 0,
                "prepared_signatures": 0,
                "unprepared_signatures": 0,
                "known_family_calls": 0,
                "static_match": entry["static_match"],
                "static_argument_lead": entry["static_argument_lead"],
                "stable_argument_candidates": set(entry["stable_registers"]),
                "varying_registers": set(entry["varying_registers"]),
                "prepared_families": set(),
                "backend_outcomes": set(),
            },
        )
        aggregate["calls"] += entry["calls"]
        if entry["outcome"] == "prepared":
            aggregate["prepared_signatures"] += 1
            aggregate["prepared_families"].add(entry["prepared_family"])
        else:
            aggregate["unprepared_signatures"] += 1
            aggregate["backend_outcomes"].add(entry["backend_outcome"])
        aggregate["stable_argument_candidates"].intersection_update(
            entry["stable_registers"]
        )
        aggregate["varying_registers"].update(entry["varying_registers"])
        if entry["outcome"] == "prepared" and entry["prepared_family"] != "unknown":
            aggregate["known_family_calls"] += entry["calls"]

    caller_summaries = []
    for aggregate in callers.values():
        aggregate["stable_argument_candidates"] = sorted(
            aggregate["stable_argument_candidates"]
        )
        aggregate["varying_registers"] = sorted(aggregate["varying_registers"])
        aggregate["prepared_families"] = sorted(aggregate["prepared_families"])
        aggregate["backend_outcomes"] = sorted(aggregate["backend_outcomes"])
        caller_summaries.append(aggregate)

    return {
        "schema": SCHEMA,
        "session": session,
        "scene": str(configs[0].get("scene", "unmarked")),
        "status": "complete" if complete else "incomplete_fail_closed",
        "entries": entries,
        "backend_outcomes": outcome_entries,
        "callers": sorted(
            caller_summaries,
            key=lambda item: (-item["calls"], item["origin_caller"]),
        ),
        "totals": {
            "title_packets_recorded": recorded,
            "backend_packet_matches": backend_matches,
            "prepared_matches": prepared_matches,
            "matched_unprepared_draws": unprepared,
            "backend_draw_outcomes_observed": backend_outcomes_observed,
            "title_backend_outcomes": title_backend_outcomes,
            "pending_packets": pending,
            "backend_draws_without_title_packet": unattributed_backend,
            "aggregate_count": len(entries),
            "prepared_aggregate_count": len(prepared_entries),
            "unprepared_aggregate_count": len(unprepared_entries),
            "origins_pushed": origins_pushed,
            "origins_consumed": origins_consumed,
            "static_matches": sum(item["static_match"] is not None for item in entries),
            "unknown_callers": sum(item["static_match"] is None for item in entries),
            "known_family_calls": sum(
                item["calls"]
                for item in entries
                if item["outcome"] == "prepared"
                and item["prepared_family"] != "unknown"
            ),
            "reused_live_packet_addresses": reused_live_addresses,
            **faults,
        },
        "correlation": provenance_contract,
        "qualification": "exact_title_packet_to_backend_draw_provenance",
        "prepared_coverage": (
            "observed" if prepared_matches else "none_observed"
        ),
        "safety": {
            "guest_payload_read": False,
            "guest_state_changed": False,
            "control_flow_changed": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        static = json.loads(args.static.read_text(encoding="utf-8"))
        document = build(read_events(args.logs), static, args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"native renderer title provenance summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
