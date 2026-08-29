"""Validate the passive title-authoritative visibility and LOD census."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility.v1"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
CONFIG = "native_renderer.discovery.semantic_visibility_config"
SUMMARY = "native_renderer.discovery.semantic_visibility_summary"
CATEGORY = "native_renderer.discovery.semantic_visibility_category_summary"
LOD = "native_renderer.discovery.semantic_lod_summary"
RESULT_VALUE = (
    "native_renderer.discovery.semantic_visibility_result_value_summary"
)


def read_events(paths: list[pathlib.Path]) -> list[dict]:
    wanted = {CONFIG, SUMMARY, CATEGORY, LOD, RESULT_VALUE}
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
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error}"
                ) from error
            if event.get("event") in wanted:
                events.append(event)
    return events


def _integer(mapping: dict, key: str) -> int:
    try:
        return int(mapping.get(key, ""))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid integer field: {key}") from error


def _select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"semantic-visibility session not found: {requested}")
        return requested
    sessions = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == CONFIG and event.get("status") == "armed"
    ]
    if not sessions or not sessions[-1]:
        raise ValueError("no armed semantic-visibility session found")
    return sessions[-1]


def _validate_static(static: dict) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    contract = static.get("procedural_model_receiver_lifecycle", {}).get(
        "visibility_selection", {}
    )
    expected = {
        "record_entry_hook_address": "82E20094",
        "lod_write_hook_addresses": ["82E205E4", "82E206DC"],
        "result_hook_address": "82E206F8",
        "record_exit_hook_address": "82E2084C",
        "receiver_register": "r20",
        "record_index_register": "r16",
        "category_register": "r15",
        "descriptor_register": "r23",
        "runtime_register": "r21",
        "selection_byte_offset": 18,
        "lod_index_offset": 104,
        "title_visibility_authority": True,
        "passive_census_required": True,
        "native_culling_enabled": False,
        "native_lod_enabled": False,
        "guest_payload_read": False,
        "guest_state_changed": False,
        "control_flow_changed": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("unsupported static semantic-visibility contract")
    return contract


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    contract = _validate_static(static)
    session = _select_session(events, requested)
    selected_events = [
        event for event in events if event.get("session") == session
    ]
    configs = [event for event in selected_events if event.get("event") == CONFIG]
    summaries = [
        event for event in selected_events if event.get("event") == SUMMARY
    ]
    if len(configs) != 1 or len(summaries) != 1:
        raise ValueError(
            "semantic-visibility session needs one config and one summary"
        )
    config = configs[0]
    summary = summaries[0]
    expected_config = {
        "status": "armed",
        "class": "proceduralGeometry::CProceduralModels",
        "visibility_function": "82E1FD00",
        "record_entry_hook": "82E20094",
        "lod_write_hooks": "82E205E4,82E206DC",
        "result_hook": "82E206F8",
        "record_completion_hook": "82E2084C",
        "record_identity": (
            "receiver_generation,record_index,category,descriptor,runtime"
        ),
        "visibility_result": "runtime_selection_byte_18",
        "lod_selection": "runtime_record_plus_104",
        "classification": "title_authoritative_visibility_and_lod_observation",
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_culling": "false",
        "native_lod": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("semantic-visibility runtime configuration drifted")
    if _integer(config, "category_capacity") != 32 or _integer(
        config, "lod_capacity"
    ) != 32 or _integer(config, "result_value_capacity") != 256:
        raise ValueError("semantic-visibility runtime capacity drifted")

    expected_summary = {
        "classification": "title_authoritative_visibility_and_lod_observation",
        "guest_payload_read": "false",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_culling": "false",
        "native_lod": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        raise ValueError("semantic-visibility summary is incomplete or unsafe")
    legacy_lod_rewrites = _integer(summary, "duplicate_lod") if (
        "lod_rewrites" not in summary and "duplicate_lod" in summary
    ) else 0
    legacy_lod_rewrite_capture = (
        legacy_lod_rewrites > 0
        and summary.get("status") == "incomplete"
        and summary.get("accounting_complete") == "false"
        and _integer(summary, "record_stack_faults") == legacy_lod_rewrites
    )
    if not legacy_lod_rewrite_capture and (
        summary.get("status") != "complete"
        or summary.get("accounting_complete") != "true"
    ):
        raise ValueError("semantic-visibility summary is incomplete or unsafe")
    totals = {
        key: _integer(summary, key)
        for key in (
            "record_entries",
            "record_completions",
            "result_observations",
            "selected_records",
            "rejected_records",
            "early_rejected_records",
            "lod_writes",
            "lod_category_selected_with_lod",
            "lod_category_selected_without_lod",
            "category_overflow",
            "lod_overflow",
            "record_stack_faults",
            "entry_overlaps",
            "lod_without_record",
            "result_without_record",
            "duplicate_result",
            "completion_without_record",
            "visibility_exit_with_record",
            "record_identity_mismatches",
            "record_unknown_receivers",
            "record_open_at_shutdown",
        )
    }
    totals["lod_rewrites"] = (
        legacy_lod_rewrites
        if legacy_lod_rewrite_capture
        else _integer(summary, "lod_rewrites")
    )
    if legacy_lod_rewrite_capture:
        totals["record_stack_faults"] -= legacy_lod_rewrites
    if (
        totals["record_entries"] <= 0
        or totals["record_entries"] != totals["record_completions"]
        or totals["record_completions"]
        != totals["selected_records"]
        + totals["rejected_records"]
        + totals["early_rejected_records"]
        or totals["result_observations"]
        != totals["selected_records"] + totals["rejected_records"]
        or totals["selected_records"] <= 0
        or totals["lod_writes"] <= 0
        or totals["lod_category_selected_with_lod"] <= 0
        or totals["lod_category_selected_without_lod"] != 0
        or any(
            totals[key]
            for key in (
                "category_overflow",
                "lod_overflow",
                "record_stack_faults",
                "entry_overlaps",
                "lod_without_record",
                "result_without_record",
                "duplicate_result",
                "completion_without_record",
                "visibility_exit_with_record",
                "record_identity_mismatches",
                "record_unknown_receivers",
                "record_open_at_shutdown",
            )
        )
    ):
        raise ValueError("semantic-visibility aggregate accounting failed")

    categories = {}
    category_totals = {
        key: 0
        for key in (
            "entries",
            "completions",
            "selected",
            "rejected",
            "early_rejected",
            "lod_writes",
        )
    }
    for event in selected_events:
        if event.get("event") != CATEGORY:
            continue
        category = _integer(event, "category")
        if category in categories or not 0 <= category < 32:
            raise ValueError("duplicate or invalid semantic-visibility category")
        if (
            event.get("status") != "complete"
            or event.get("title_visibility_authority") != "true"
            or event.get("native_culling") != "false"
            or event.get("native_lod") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("semantic-visibility category is incomplete or unsafe")
        item = {key: _integer(event, key) for key in category_totals}
        if (
            item["entries"] <= 0
            or item["entries"] != item["completions"]
            or item["completions"]
            != item["selected"] + item["rejected"] + item["early_rejected"]
        ):
            raise ValueError("semantic-visibility category accounting failed")
        categories[category] = item
        for key, value in item.items():
            category_totals[key] += value
    if not categories or category_totals != {
        "entries": totals["record_entries"],
        "completions": totals["record_completions"],
        "selected": totals["selected_records"],
        "rejected": totals["rejected_records"],
        "early_rejected": totals["early_rejected_records"],
        "lod_writes": totals["lod_writes"],
    }:
        raise ValueError("semantic-visibility category totals drifted")

    lod_histogram = {}
    for event in selected_events:
        if event.get("event") != LOD:
            continue
        lod_index = _integer(event, "lod_index")
        if lod_index in lod_histogram or not 0 <= lod_index < 32:
            raise ValueError("duplicate or invalid semantic LOD index")
        if (
            event.get("status") != "complete"
            or event.get("source") != "title_selected_runtime_record_plus_104"
            or event.get("native_lod") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("semantic LOD summary is incomplete or unsafe")
        writes = _integer(event, "writes")
        if writes <= 0:
            raise ValueError("semantic LOD histogram contains an empty bin")
        lod_histogram[lod_index] = writes
    if not lod_histogram or sum(lod_histogram.values()) != totals["lod_writes"]:
        raise ValueError("semantic LOD histogram accounting failed")

    result_value_histogram = {}
    for event in selected_events:
        if event.get("event") != RESULT_VALUE:
            continue
        value = _integer(event, "selection_value")
        if value in result_value_histogram or not 0 <= value < 256:
            raise ValueError("duplicate or invalid visibility result value")
        expected_interpretation = (
            "selected_nonzero" if value else "rejected_zero"
        )
        if (
            event.get("status") != "complete"
            or event.get("interpretation") != expected_interpretation
            or event.get("native_culling") != "false"
            or event.get("xenos_authority") != "true"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("visibility result value is incomplete or unsafe")
        observations = _integer(event, "observations")
        if observations <= 0:
            raise ValueError("visibility result histogram contains an empty bin")
        result_value_histogram[value] = observations
    if (
        not result_value_histogram
        or sum(result_value_histogram.values())
        != totals["result_observations"]
        or result_value_histogram.get(0, 0) != totals["rejected_records"]
        or sum(
            count
            for value, count in result_value_histogram.items()
            if value
        )
        != totals["selected_records"]
    ):
        raise ValueError("visibility result histogram accounting failed")

    return {
        "schema": SCHEMA,
        "status": "complete",
        "session": session,
        "static_contract": contract,
        "totals": totals,
        "categories": {str(key): categories[key] for key in sorted(categories)},
        "lod_histogram": {
            str(key): lod_histogram[key] for key in sorted(lod_histogram)
        },
        "result_value_histogram": {
            str(key): result_value_histogram[key]
            for key in sorted(result_value_histogram)
        },
        "qualification": {
            "title_visibility_authority_proved": True,
            "title_lod_selection_observed": True,
            "ready_for_native_policy_modeling": True,
            "capture_model": (
                "legacy_duplicate_lod_normalized_as_rewrite"
                if legacy_lod_rewrite_capture
                else "lod_rewrite_aware"
            ),
        },
        "safety": {
            "guest_payload_read": False,
            "guest_state_changed": False,
            "control_flow_changed": False,
            "native_culling": False,
            "native_lod": False,
            "native_draw": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("events", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        static = json.loads(args.static.read_text(encoding="utf-8"))
        document = build(read_events(args.events), static, args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"native renderer visibility summary failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
