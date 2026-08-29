"""Validate the in-order semantic batch-admission census."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-semantic-batch-admission.v1"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
TITLE_CONFIG = "native_renderer.discovery.title_provenance_config"
TITLE_SUMMARY = "native_renderer.discovery.title_provenance_summary"
BATCH_ENTRY = "native_renderer.discovery.semantic_batch_entry"
BATCH_SUMMARY = "native_renderer.discovery.semantic_batch_summary"
EXPECTED_ORDERING = "exact_consecutive_prepared_draw_order"
REJECTION_FIELDS = {
    "missing_title_resource": "reject_missing_title_resource",
    "non_opaque": "reject_non_opaque",
    "resolved_input": "reject_resolved_input",
    "query_or_conditional": "reject_query_or_conditional",
    "memexport": "reject_memexport",
    "unbounded_geometry": "reject_unbounded_geometry",
    "unsupported_geometry": "reject_unsupported_geometry",
    "constant_overflow": "reject_constant_overflow",
    "unbounded_texture_layout": "reject_unbounded_texture_layout",
    "texture_count": "reject_texture_count",
    "incomplete_prepared_pipeline": "reject_incomplete_prepared_pipeline",
    "render_target_coverage": "reject_render_target_coverage",
}


def read_events(paths: list[pathlib.Path]) -> list[dict]:
    events = []
    wanted = {TITLE_CONFIG, TITLE_SUMMARY, BATCH_ENTRY, BATCH_SUMMARY}
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


def _number(mapping: dict, key: str) -> float:
    try:
        return float(mapping.get(key, ""))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid number field: {key}") from error


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
    if value not in {"true", "false"}:
        raise ValueError(f"invalid boolean field: {key}")
    return value == "true"


def _select_session(events: list[dict], requested: str | None) -> str:
    if requested:
        if not any(event.get("session") == requested for event in events):
            raise ValueError(f"semantic-batch session not found: {requested}")
        return requested
    sessions = [
        str(event.get("session", ""))
        for event in events
        if event.get("event") == TITLE_CONFIG
        and event.get("status") == "armed"
    ]
    if not sessions or not sessions[-1]:
        raise ValueError("no armed semantic-batch session found")
    return sessions[-1]


def _validate_static(static: dict) -> dict:
    if static.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    lifecycle = static.get("procedural_model_receiver_lifecycle", {})
    contract = lifecycle.get("semantic_draw_association", {})
    expected = {
        "semantic_pm4_packet_construction_proved": True,
        "semantic_pm4_backend_join_required": True,
        "semantic_prepared_contract_runtime_join_required": True,
        "semantic_catalog_classification": (
            "immutable_template_and_dynamic_resource_instance"
        ),
        "semantic_batch_admission_census_required": True,
        "semantic_batch_ordering": EXPECTED_ORDERING,
        "semantic_batch_execution_enabled": False,
        "native_rendering_enabled": False,
        "suppression_eligible": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("unsupported semantic-batch static contract")
    return contract


def build(events: list[dict], static: dict, requested: str | None = None) -> dict:
    contract = _validate_static(static)
    session = _select_session(events, requested)
    selected = [event for event in events if event.get("session") == session]
    configs = [event for event in selected if event.get("event") == TITLE_CONFIG]
    title_summaries = [
        event for event in selected if event.get("event") == TITLE_SUMMARY
    ]
    summaries = [event for event in selected if event.get("event") == BATCH_SUMMARY]
    if len(configs) != 1 or len(title_summaries) != 1 or len(summaries) != 1:
        raise ValueError(
            "semantic-batch session needs one config, title summary, and batch summary"
        )
    config = configs[0]
    title_summary = title_summaries[0]
    summary = summaries[0]
    if (
        config.get("status") != "armed"
        or config.get("semantic_batch_planner")
        != "exact_consecutive_opaque_prepared_draw_order"
        or config.get("semantic_batch_execution")
        != "disabled_measurement_only"
        or config.get("xenos_authority") != "true"
        or config.get("suppression_allowed") != "false"
    ):
        raise ValueError("semantic-batch runtime configuration drifted")
    if (
        summary.get("status") != "complete"
        or summary.get("ordering") != EXPECTED_ORDERING
        or summary.get("reordering") != "false"
        or summary.get("native_batch_execution") != "false"
        or summary.get("native_upload") != "false"
        or summary.get("native_draw") != "false"
        or summary.get("xenos_authority") != "true"
        or summary.get("suppression_allowed") != "false"
        or summary.get("accounting_complete") != "true"
    ):
        raise ValueError("semantic-batch summary is incomplete or unsafe")

    entries = []
    seen_keys = set()
    entry_draws = 0
    eligible_draws = 0
    rejected_draws = 0
    consecutive_runs = 0
    multi_draw_runs = 0
    multi_draw_draws = 0
    instance_switches = 0
    same_instance_continuations = 0
    rejections = {name: 0 for name in REJECTION_FIELDS}
    for event in selected:
        if event.get("event") != BATCH_ENTRY:
            continue
        opportunity_key = _hex(event, "opportunity_key", 16)
        if opportunity_key in seen_keys or int(opportunity_key, 16) == 0:
            raise ValueError("duplicate or zero semantic-batch opportunity key")
        seen_keys.add(opportunity_key)
        eligible = _boolean(event, "eligible")
        rejection = str(event.get("rejection", ""))
        classification = str(event.get("classification", ""))
        if eligible:
            if (
                rejection != "none"
                or classification != "conservative_consecutive_batch_candidate"
            ):
                raise ValueError("eligible semantic-batch entry is inconsistent")
        elif (
            rejection not in REJECTION_FIELDS
            or classification != "xenos_replay_rejected"
        ):
            raise ValueError("rejected semantic-batch entry is inconsistent")
        if (
            event.get("native_batch") != "false"
            or event.get("xenos_draw") != "preserved"
            or event.get("suppression_allowed") != "false"
        ):
            raise ValueError("semantic-batch entry crossed the safety boundary")
        item = {
            "opportunity_key": opportunity_key,
            "template_key": _hex(event, "template_key", 16),
            "geometry_resource_hash": _hex(
                event, "geometry_resource_hash", 16
            ),
            "texture_resource_hash": _hex(event, "texture_resource_hash", 16),
            "primary_resource_key": _hex(event, "primary_resource_key", 8),
            "secondary_resource_present": _boolean(
                event, "secondary_resource_present"
            ),
            "secondary_resource_key": _hex(
                event, "secondary_resource_key", 8
            ),
            "draws": _integer(event, "draws"),
            "frames": _integer(event, "frames"),
            "first_frame": _integer(event, "first_frame"),
            "last_frame": _integer(event, "last_frame"),
            "consecutive_runs": _integer(event, "consecutive_runs"),
            "multi_draw_runs": _integer(event, "multi_draw_runs"),
            "multi_draw_draws": _integer(event, "multi_draw_draws"),
            "maximum_run_length": _integer(event, "maximum_run_length"),
            "instance_switches": _integer(event, "instance_switches"),
            "same_instance_continuations": _integer(
                event, "same_instance_continuations"
            ),
            "eligible": eligible,
            "rejection": rejection,
            "classification": classification,
        }
        if (
            item["draws"] <= 0
            or item["frames"] <= 0
            or item["last_frame"] < item["first_frame"]
            or any(
                item[key] < 0
                for key in (
                    "consecutive_runs",
                    "multi_draw_runs",
                    "multi_draw_draws",
                    "maximum_run_length",
                    "instance_switches",
                    "same_instance_continuations",
                )
            )
        ):
            raise ValueError("semantic-batch entry has invalid counters")
        if eligible:
            if (
                item["consecutive_runs"] <= 0
                or item["maximum_run_length"] <= 0
                or item["multi_draw_draws"] > item["draws"]
            ):
                raise ValueError("eligible semantic-batch run accounting failed")
            eligible_draws += item["draws"]
        else:
            if any(
                item[key]
                for key in (
                    "consecutive_runs",
                    "multi_draw_runs",
                    "multi_draw_draws",
                    "maximum_run_length",
                    "instance_switches",
                    "same_instance_continuations",
                )
            ):
                raise ValueError("rejected semantic-batch entry owns a run")
            rejected_draws += item["draws"]
            rejections[rejection] += item["draws"]
        entry_draws += item["draws"]
        consecutive_runs += item["consecutive_runs"]
        multi_draw_runs += item["multi_draw_runs"]
        multi_draw_draws += item["multi_draw_draws"]
        instance_switches += item["instance_switches"]
        same_instance_continuations += item["same_instance_continuations"]
        entries.append(item)

    totals = {
        key: _integer(summary, key)
        for key in (
            "observations",
            "eligible_draws",
            "rejected_draws",
            "opportunity_entries",
            "opportunity_overflow",
            "consecutive_runs",
            "multi_draw_runs",
            "multi_draw_draws",
            "maximum_run_length",
            "instance_switches",
            "same_instance_continuations",
            "frames",
            "maximum_draws_per_frame",
            "template_transitions",
            "geometry_transitions",
            "texture_transitions",
            "title_resource_transitions",
            "projected_commands",
            "potential_command_reduction",
        )
    }
    totals["potential_command_reduction_percent"] = _number(
        summary, "potential_command_reduction_percent"
    )
    reported_rejections = {
        name: _integer(summary, field)
        for name, field in REJECTION_FIELDS.items()
    }
    if (
        totals["observations"] <= 0
        or totals["opportunity_overflow"] != 0
        or totals["opportunity_entries"] != len(entries)
        or totals["observations"] != entry_draws
        or totals["eligible_draws"] != eligible_draws
        or totals["rejected_draws"] != rejected_draws
        or totals["eligible_draws"] + totals["rejected_draws"]
        != totals["observations"]
        or totals["consecutive_runs"] != consecutive_runs
        or totals["multi_draw_runs"] != multi_draw_runs
        or totals["multi_draw_draws"] != multi_draw_draws
        or totals["instance_switches"] != instance_switches
        or totals["same_instance_continuations"]
        != same_instance_continuations
        or totals["projected_commands"]
        != totals["consecutive_runs"] + totals["rejected_draws"]
        or totals["potential_command_reduction"]
        != totals["eligible_draws"] - totals["consecutive_runs"]
        or reported_rejections != rejections
        or sum(reported_rejections.values()) != totals["rejected_draws"]
        or totals["observations"]
        != _integer(title_summary, "semantic_contract_calls")
        or totals["observations"]
        != _integer(title_summary, "semantic_draw_prepared_matches")
        or _integer(title_summary, "semantic_draw_unprepared_matches") != 0
    ):
        raise ValueError("semantic-batch aggregate accounting failed")
    expected_percent = (
        100.0 * totals["potential_command_reduction"] / totals["observations"]
    )
    if abs(totals["potential_command_reduction_percent"] - expected_percent) > 0.001:
        raise ValueError("semantic-batch reduction percentage drifted")

    entries.sort(
        key=lambda item: (
            not item["eligible"],
            -item["multi_draw_draws"],
            -item["draws"],
            item["opportunity_key"],
        )
    )
    conservative_batch_plan_proved = (
        totals["eligible_draws"] > 0
        and totals["multi_draw_runs"] > 0
        and totals["potential_command_reduction"] > 0
    )
    return {
        "schema": SCHEMA,
        "session": session,
        "scene": str(config.get("scene", "unmarked")),
        "status": "complete",
        "groups": entries,
        "totals": totals,
        "rejections": reported_rejections,
        "conservative_batch_plan_proved": conservative_batch_plan_proved,
        "execution_admitted": False,
        "contract": contract,
        "safety": {
            "exact_consecutive_order": True,
            "reordering": False,
            "guest_state_changed": False,
            "native_upload": False,
            "native_draw": False,
            "native_batch_execution": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        events = read_events(args.logs)
        static = json.loads(args.static.read_text(encoding="utf-8"))
        document = build(events, static, args.session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"native renderer semantic batch summary failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
