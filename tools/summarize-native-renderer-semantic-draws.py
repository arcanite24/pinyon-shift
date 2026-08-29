"""Validate semantic submissions and probe their direct title-packet overlap."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-semantic-draw-boundary.v2"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
SEMANTIC_DRAW_PREFIX = "native_renderer.discovery.semantic_draw_"
SEMANTIC_SUBMISSION_PREFIX = "native_renderer.discovery.semantic_submission_"
TITLE_PREFIX = "native_renderer.discovery.title_provenance_"
EXPECTED_CLASS = "proceduralGeometry::CProceduralModels"
EXPECTED_CORRELATION = "exact_render_item_scope_with_packet_constructor_overlap_probe"
EXPECTED_DIRECT_ASSOCIATION = "exact_render_item_scope_and_physical_pm4_header"


def read_events(paths: list[pathlib.Path]) -> list[dict]:
    events = []
    prefixes = (SEMANTIC_DRAW_PREFIX, SEMANTIC_SUBMISSION_PREFIX, TITLE_PREFIX)
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
            if str(event.get("event", "")).startswith(prefixes):
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


def _select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"semantic-draw session not found: {requested}")
        return requested
    sessions = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == f"{SEMANTIC_DRAW_PREFIX}config"
        and event.get("status") == "armed"
    ]
    if not sessions or not sessions[-1]:
        raise ValueError("no armed semantic-draw session found")
    return sessions[-1]


def _validate_static(static: dict) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    lifecycle = static.get("procedural_model_receiver_lifecycle", {})
    contract = lifecycle.get("semantic_draw_association", {})
    expected = {
        "render_item_entry_hook_address": "8241741C",
        "render_item_exit_hook_address": "82417B80",
        "geometry_submission_hook_address": "82417B60",
        "title_draw_packet_hook_addresses": ["82410328", "829F7CB0"],
        "title_indirect_packet_hook_addresses": [
            "824095B4",
            "82416EFC",
            "8246FC1C",
            "8263BD64",
            "829E8E88",
            "829EC49C",
        ],
        "graphics_submission_vtable_offset": 160,
        "graphics_submission_target_runtime_join_required": True,
        "direct_title_packet_overlap_probe": True,
        "indirect_packet_constructor_overlap_probe": True,
        "physical_pm4_packet_correlation_proved": False,
        "prepared_draw_lineage_proved": False,
        "classification": "procedural_submission_dispatch_boundary",
        "native_rendering_enabled": False,
        "suppression_eligible": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("unsupported semantic-draw static contract")
    if not all(
        contract.get(key)
        for key in (
            "render_item_invocation_scope_proved",
            "submission_before_draw_dispatch_proved",
        )
    ):
        raise ValueError("semantic-draw correlation is not statically proved")
    provenance = static.get("draw_packet_provenance", {})
    packet_hooks = {
        str(item.get("packet_hook_address", "")).upper()
        for item in provenance.get("packet_sites", [])
    }
    if packet_hooks != {"82410328", "829F7CB0"}:
        raise ValueError("title draw packet provenance contract drifted")
    return contract


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    contract = _validate_static(static)
    session = _select_session(events, requested)
    selected = [event for event in events if event.get("session") == session]

    configs = [
        event
        for event in selected
        if event.get("event") == f"{SEMANTIC_DRAW_PREFIX}config"
        and event.get("status") == "armed"
    ]
    title_summaries = [
        event for event in selected if event.get("event") == f"{TITLE_PREFIX}summary"
    ]
    submission_summaries = [
        event
        for event in selected
        if event.get("event") == f"{SEMANTIC_SUBMISSION_PREFIX}summary"
    ]
    if len(configs) != 1 or len(title_summaries) != 1 or len(submission_summaries) != 1:
        raise ValueError(
            "semantic-draw session needs one config, title summary, and submission summary"
        )
    config = configs[0]
    if (
        config.get("class") != EXPECTED_CLASS
        or config.get("render_item_entry_hook") != "8241741C"
        or config.get("render_item_exit_hook") != "82417B80"
        or config.get("geometry_submission_hook") != "82417B60"
        or config.get("title_packet_hooks") != "82410328,829F7CB0"
        or config.get("title_indirect_packet_hooks")
        not in (
            None,
            "824095B4,82416EFC,8246FC1C,8263BD64,829E8E88,829EC49C",
        )
        or config.get("correlation") != EXPECTED_CORRELATION
        or config.get("classification")
        != "procedural_submission_dispatch_boundary"
    ):
        raise ValueError("semantic-draw runtime contract drifted")
    safety = {
        "guest_state_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(str(config.get(key)).lower() != value for key, value in safety.items()):
        raise ValueError("semantic-draw config violates the safety boundary")

    submissions: dict[str, dict] = {}
    submission_calls = 0
    for event in selected:
        if event.get("event") != f"{SEMANTIC_SUBMISSION_PREFIX}entry":
            continue
        key = _hex(event, "key", 16)
        calls = _integer(event, "calls")
        identity = {
            "receiver_address": _hex(event, "receiver_address", 8),
            "receiver_generation": _integer(event, "receiver_generation"),
            "record_index": _integer(event, "record_index"),
            "graphics_submission_method": _hex(
                event, "graphics_submission_method", 8
            ),
        }
        if key in submissions or calls <= 0 or identity["receiver_generation"] <= 0:
            raise ValueError("invalid or duplicate semantic submission entry")
        submissions[key] = {"calls": calls, **identity}
        submission_calls += calls

    associations = []
    associated_calls_by_key: collections.Counter[str] = collections.Counter()
    prepared_signatures_by_key: dict[str, set[str]] = collections.defaultdict(set)
    prepared_calls = 0
    unprepared_calls = 0
    for event in selected:
        if event.get("event") != f"{TITLE_PREFIX}entry":
            continue
        raw_key = str(event.get("semantic_submission_key", ""))
        if not raw_key:
            continue
        key = _hex(event, "semantic_submission_key", 16)
        submission = submissions.get(key)
        if submission is None:
            raise ValueError("semantic draw references an unknown submission key")
        calls = _integer(event, "calls")
        outcome = str(event.get("outcome", ""))
        signature = str(event.get("prepared_signature", "")).upper()
        backend_signature = _hex(event, "backend_signature", 16)
        receiver_address = _hex(event, "semantic_receiver_address", 8)
        receiver_generation = _integer(event, "semantic_receiver_generation")
        record_index = _integer(event, "semantic_record_index")
        descriptor_address = _hex(event, "semantic_descriptor_address", 8)
        runtime_address = _hex(event, "semantic_runtime_address", 8)
        if (
            calls <= 0
            or event.get("semantic_draw_association") != EXPECTED_DIRECT_ASSOCIATION
            or event.get("semantic_identity") != "procedural_model_submission"
            or str(event.get("xenos_draw", "")).lower() != "preserved"
            or str(event.get("suppression_eligible", "")).lower() != "false"
            or receiver_address != submission["receiver_address"]
            or receiver_generation != submission["receiver_generation"]
            or record_index != submission["record_index"]
        ):
            raise ValueError("semantic draw identity or safety evidence is inconsistent")
        if outcome == "prepared":
            if len(signature) != 16 or signature != backend_signature:
                raise ValueError("semantic prepared draw signature is invalid")
            int(signature, 16)
            prepared_signatures_by_key[key].add(signature)
            prepared_calls += calls
        elif outcome == "not_prepared":
            if signature:
                raise ValueError("semantic unprepared draw has a prepared signature")
            unprepared_calls += calls
        else:
            raise ValueError("semantic draw has an invalid backend outcome")
        associated_calls_by_key[key] += calls
        associations.append(
            {
                "semantic_submission_key": key,
                "calls": calls,
                "receiver_address": receiver_address,
                "receiver_generation": receiver_generation,
                "record_index": record_index,
                "descriptor_address": descriptor_address,
                "runtime_address": runtime_address,
                "origin_wrapper": str(event.get("origin_wrapper", "unknown")),
                "origin_wrapper_address": _hex(event, "origin_wrapper_address", 8),
                "origin_caller": _hex(event, "origin_caller", 8),
                "outcome": outcome,
                "backend_outcome": str(event.get("backend_outcome", "")),
                "backend_signature": backend_signature,
                "prepared_signature": signature or None,
                "xenos_draw": "preserved",
                "suppression_eligible": False,
            }
        )

    submission_summary = submission_summaries[0]
    title_summary = title_summaries[0]
    live_submissions = _integer(submission_summary, "live_observations")
    pending = _integer(title_summary, "semantic_draw_pending_packets")
    semantic_prepared = _integer(title_summary, "semantic_draw_prepared_matches")
    semantic_unprepared = _integer(title_summary, "semantic_draw_unprepared_matches")
    associated_calls = sum(associated_calls_by_key.values())
    fault_fields = (
        "semantic_render_item_stack_faults",
        "semantic_draw_scope_mismatches",
    )
    faults = {key: _integer(title_summary, key) for key in fault_fields}
    counters = {
        key: _integer(title_summary, key)
        for key in (
            "semantic_submission_live_observations",
            "semantic_render_item_entries",
            "semantic_render_item_exits",
            "semantic_render_item_valid_scopes",
            "semantic_render_item_scopes_without_submission",
            "semantic_draw_scope_joins",
            "semantic_draw_origins_captured",
            "semantic_draw_dispatches_with_direct_title_origin",
            "semantic_draw_dispatches_without_direct_title_origin",
            "semantic_draw_indirect_packet_origins_captured",
            "semantic_draw_dispatches_with_indirect_packet_origin",
            "semantic_draw_dispatches_without_indirect_packet_origin",
            "semantic_draw_packets_recorded",
            "semantic_draw_packet_matches",
        )
    }
    if (
        not submissions
        or submission_calls != live_submissions
        or counters["semantic_submission_live_observations"] != live_submissions
        or counters["semantic_draw_scope_joins"] != live_submissions
        or counters["semantic_draw_dispatches_with_direct_title_origin"]
        + counters["semantic_draw_dispatches_without_direct_title_origin"]
        != live_submissions
        or counters["semantic_draw_dispatches_with_indirect_packet_origin"]
        + counters["semantic_draw_dispatches_without_indirect_packet_origin"]
        != live_submissions
        or counters["semantic_draw_indirect_packet_origins_captured"]
        < counters["semantic_draw_dispatches_with_indirect_packet_origin"]
        or counters["semantic_draw_origins_captured"]
        < counters["semantic_draw_dispatches_with_direct_title_origin"]
        or counters["semantic_draw_packets_recorded"]
        != counters["semantic_draw_origins_captured"]
        or counters["semantic_draw_packet_matches"] != associated_calls
        or associated_calls != prepared_calls + unprepared_calls
        or prepared_calls != semantic_prepared
        or unprepared_calls != semantic_unprepared
        or counters["semantic_draw_packets_recorded"]
        != associated_calls + pending
        or counters["semantic_render_item_entries"]
        != counters["semantic_render_item_exits"]
        + _integer(title_summary, "semantic_render_items_open_at_shutdown")
        or counters["semantic_render_item_valid_scopes"] < live_submissions
        or any(faults.values())
        or str(
            title_summary.get("semantic_draw_overlap_probe_accounting_complete")
        ).lower()
        != "true"
        or (
            str(title_summary.get("semantic_draw_accounting_complete")).lower()
            == "true"
        )
        != (counters["semantic_draw_dispatches_without_direct_title_origin"] == 0)
    ):
        raise ValueError("semantic draw accounting is incomplete or inconsistent")
    associations.sort(
        key=lambda item: (
            -item["calls"],
            item["semantic_submission_key"],
            item["backend_signature"],
        )
    )
    submission_lineage = [
        {
            "semantic_submission_key": key,
            **submission,
            "associated_draw_calls": associated_calls_by_key[key],
            "direct_title_packet_calls": associated_calls_by_key[key],
            "prepared_signatures": sorted(prepared_signatures_by_key[key]),
        }
        for key, submission in submissions.items()
    ]
    submission_lineage.sort(
        key=lambda item: (-item["calls"], item["semantic_submission_key"])
    )
    return {
        "schema": SCHEMA,
        "session": session,
        "scene": str(config.get("scene", "unmarked")),
        "status": "complete",
        "associations": associations,
        "submissions": submission_lineage,
        "totals": {
            "semantic_submissions": live_submissions,
            "semantic_submission_keys": len(submissions),
            "associated_draw_calls": associated_calls,
            "prepared_draw_calls": prepared_calls,
            "unprepared_draw_calls": unprepared_calls,
            "pending_draw_packets": pending,
            "unique_prepared_signatures": len(
                {
                    signature
                    for signatures in prepared_signatures_by_key.values()
                    for signature in signatures
                }
            ),
            "association_entries": len(associations),
            "semantic_render_items_open_at_shutdown": _integer(
                title_summary, "semantic_render_items_open_at_shutdown"
            ),
            **counters,
            **faults,
        },
        "correlation": contract,
        "qualification": "exact_semantic_submission_dispatch_boundary_and_direct_packet_overlap_census",
        "prepared_draw_lineage_proved": (
            counters["semantic_draw_dispatches_without_direct_title_origin"] == 0
        ),
        "safety": {
            "bounded_guest_read": True,
            "guest_state_changed": False,
            "native_upload": False,
            "native_draw": False,
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
        print(f"native renderer semantic draw summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
