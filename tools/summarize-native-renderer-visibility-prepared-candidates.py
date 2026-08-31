#!/usr/bin/env python3
"""Qualify visibility-selected records at the exact prepared-draw boundary."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-visibility-prepared-candidates.v5"
STATIC_SCHEMA = "pinyon-shift.native-renderer-dispatch-static.v3"
CONFIG = (
    "native_renderer.discovery."
    "semantic_visibility_prepared_candidate_config"
)
ENTRY = (
    "native_renderer.discovery."
    "semantic_visibility_prepared_candidate_entry"
)
SUMMARY = (
    "native_renderer.discovery."
    "semantic_visibility_prepared_candidate_summary"
)
WORKSET = "native_renderer.discovery.semantic_visibility_workset_summary"

MECHANICAL_REJECTIONS = {
    0: "resolved_input",
    1: "unsupported_geometry",
    2: "empty_draw",
    3: "vertex_binding_count",
    4: "vertex_binding_overflow",
    5: "vertex_attribute_overflow",
    6: "vertex_constant_overflow",
    7: "pixel_constant_overflow",
    8: "texture_state_overflow",
    9: "memexport",
    10: "query",
    11: "texture_count",
    12: "texture_layout",
    13: "prepared_pipeline",
    14: "render_targets",
}
MECHANICAL_REJECTION_MASK = sum(1 << bit for bit in MECHANICAL_REJECTIONS)


def read_events(paths):
    events = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def integer(mapping, key):
    try:
        value = int(mapping[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if value < 0:
        raise ValueError(f"negative {key}")
    return value


def hexadecimal(mapping, key, width):
    value = str(mapping.get(key, "")).upper()
    if len(value) != width:
        raise ValueError(f"invalid {key}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"invalid {key}") from error
    return value


def exact_event(events, name):
    matches = [event for event in events if event.get("event") == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} event")
    return matches[0]


def select_session(events, requested):
    sessions = {
        event.get("session") for event in events if event.get("event") == CONFIG
    }
    sessions.discard(None)
    if requested:
        if requested not in sessions:
            raise ValueError("requested session has no prepared-candidate config")
        return requested
    if len(sessions) != 1:
        raise ValueError("prepared-candidate input contains multiple sessions")
    return next(iter(sessions))


def static_contract(document):
    if document.get("schema") != STATIC_SCHEMA:
        raise ValueError("unsupported static dispatch inventory schema")
    try:
        contract = document["procedural_model_receiver_lifecycle"][
            "visibility_prepared_candidates"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError("static prepared-candidate contract is missing") from error
    expected = {
        "semantic_instance_hook_address": "8241741C",
        "semantic_packet_hook_addresses": ["82416260", "824162F4"],
        "capacity": 4096,
        "maximum_policy_age_frames": 1,
        "identity": "receiver_generation_record_index",
        "selection": "independent_visibility_selected_and_fresh",
        "prepared_lineage": "exact_semantic_pm4_prepared_draw",
        "title_lod_lineage": "exact_visibility_identity_to_prepared_draw",
        "mechanical_admission_contract": "isolated_draw_v1",
        "guest_state_changed": False,
        "control_flow_changed": False,
        "native_upload_enabled": False,
        "native_draw_enabled": False,
        "xenos_draw_preserved": True,
        "suppression_allowed": False,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("static prepared-candidate contract drifted")
    return contract


def require_safety(event):
    expected = {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_draw": "preserved",
        "suppression_allowed": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("prepared-candidate evidence violates safety boundary")


def build(events, static, requested_session=None):
    contract = static_contract(static)
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary = exact_event(selected, SUMMARY)
    workset = exact_event(selected, WORKSET)
    expected_config = {
        "status": "armed",
        "class": "proceduralGeometry::CProceduralModels",
        "semantic_instance_hook": "8241741C",
        "semantic_packet_hooks": "82416260,824162F4",
        "prepared_draw_join": "physical_pm4_header_generation",
        "capacity": "4096",
        "policy_age_limit_frames": "1",
        "identity": "receiver_generation_record_index",
        "selection": "independent_visibility_selected_and_fresh",
        "prepared_lineage": "exact_semantic_pm4_prepared_draw",
        "title_lod_lineage": "exact_visibility_identity_to_prepared_draw",
        "mechanical_admission_contract": "isolated_draw_v1",
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_upload": "false",
        "native_draw": "false",
        "xenos_draw": "preserved",
        "suppression_allowed": "false",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("prepared-candidate runtime configuration drifted")
    require_safety(summary)
    if (
        summary.get("status") != "complete"
        or summary.get("accounting_complete") != "true"
        or summary.get("identity") != "receiver_generation_record_index"
        or summary.get("prepared_lineage")
        != "exact_semantic_pm4_prepared_draw"
        or summary.get("selection")
        != "independent_visibility_selected_and_fresh"
        or summary.get("title_lod_lineage")
        != "exact_visibility_identity_to_prepared_draw"
        or summary.get("track_texture_provider_lineage")
        != "exact_primary_provider_vtable_and_four_methods"
        or summary.get("mechanical_admission_contract") != "isolated_draw_v1"
    ):
        raise ValueError("prepared-candidate summary is incomplete")

    count_keys = (
        "observations",
        "selected_joins",
        "fresh_candidates",
        "stale_exclusions",
        "future_exclusions",
        "rejected_exclusions",
        "missing_exclusions",
        "candidate_entries",
        "entry_draws",
        "mechanically_eligible_entries",
        "mechanically_eligible_draws",
        "mechanically_ineligible_entries",
        "mechanically_ineligible_draws",
        "title_lod_entries",
        "title_lod_draws",
        "track_texture_provider_entries",
        "track_texture_provider_draws",
        "capacity",
        "overflow",
        "policy_age_limit_frames",
    )
    totals = {key: integer(summary, key) for key in count_keys}
    entries = []
    seen_keys = set()
    entry_draws = 0
    rejection_entry_counts = {name: 0 for name in MECHANICAL_REJECTIONS.values()}
    rejection_draw_counts = {name: 0 for name in MECHANICAL_REJECTIONS.values()}
    for event in selected:
        if event.get("event") != ENTRY:
            continue
        require_safety(event)
        key = hexadecimal(event, "candidate_key", 16)
        item = {
            "candidate_key": key,
            "prepared_signature": hexadecimal(event, "prepared_signature", 16),
            "template_key": hexadecimal(event, "template_key", 16),
            "geometry_resource_hash": hexadecimal(
                event, "geometry_resource_hash", 16
            ),
            "texture_resource_hash": hexadecimal(
                event, "texture_resource_hash", 16
            ),
            "vertex_shader": hexadecimal(event, "vertex_shader", 16),
            "pixel_shader": hexadecimal(event, "pixel_shader", 16),
            "vertex_specialization_mask": hexadecimal(
                event, "vertex_specialization_mask", 16
            ),
            "pixel_specialization_mask": hexadecimal(
                event, "pixel_specialization_mask", 16
            ),
            "receiver_address": hexadecimal(event, "receiver_address", 8),
            "receiver_generation": integer(event, "receiver_generation"),
            "record_index": integer(event, "record_index"),
            "visibility_category": integer(event, "visibility_category"),
            "visibility_result_mask": integer(event, "visibility_result_mask"),
            "title_lod_index": integer(event, "title_lod_index"),
            "title_lod_valid": event.get("title_lod_valid") == "true",
            "track_texture_provider": (
                event.get("track_texture_provider") == "true"
            ),
            "draws": integer(event, "draws"),
            "first_frame": integer(event, "first_frame"),
            "last_frame": integer(event, "last_frame"),
            "maximum_policy_age_frames": integer(
                event, "maximum_policy_age_frames"
            ),
            "mechanically_eligible": event.get("mechanically_eligible") == "true",
        }
        rejection_mask = int(hexadecimal(event, "mechanical_rejection_mask", 8), 16)
        item["mechanical_rejection_mask"] = rejection_mask
        item["mechanical_rejections"] = [
            name
            for bit, name in MECHANICAL_REJECTIONS.items()
            if rejection_mask & (1 << bit)
        ]
        if (
            event.get("status") != "complete"
            or event.get("classification")
            != "fresh_visibility_selected_prepared_candidate"
            or key in seen_keys
            or not item["draws"]
            or item["first_frame"] > item["last_frame"]
            or item["visibility_result_mask"] > 7
            or item["maximum_policy_age_frames"]
            > totals["policy_age_limit_frames"]
            or event.get("mechanically_eligible") not in ("true", "false")
            or event.get("mechanical_admission_contract") != "isolated_draw_v1"
            or rejection_mask & ~MECHANICAL_REJECTION_MASK
            or item["mechanically_eligible"] != (rejection_mask == 0)
            or event.get("title_lod_valid") not in ("true", "false")
            or event.get("title_lod_lineage")
            != "exact_visibility_identity_to_prepared_draw"
            or event.get("track_texture_provider") not in ("true", "false")
            or event.get("track_texture_provider_lineage")
            != "exact_primary_provider_vtable_and_four_methods"
            or (item["title_lod_valid"] and item["title_lod_index"] >= 32)
            or integer(event, "policy_age_limit_frames")
            != totals["policy_age_limit_frames"]
        ):
            raise ValueError("prepared-candidate entry evidence drifted")
        seen_keys.add(key)
        entry_draws += item["draws"]
        for reason in item["mechanical_rejections"]:
            rejection_entry_counts[reason] += 1
            rejection_draw_counts[reason] += item["draws"]
        entries.append(item)

    failures = []
    if totals["observations"] <= 0 or totals["fresh_candidates"] <= 0:
        failures.append("prepared visibility handoff was not exercised")
    if (
        totals["observations"]
        != totals["selected_joins"]
        + totals["rejected_exclusions"]
        + totals["missing_exclusions"]
    ):
        failures.append("prepared observation accounting drifted")
    if (
        totals["selected_joins"]
        != totals["fresh_candidates"]
        + totals["stale_exclusions"]
        + totals["future_exclusions"]
    ):
        failures.append("selected policy-age accounting drifted")
    if totals["fresh_candidates"] != totals["entry_draws"] + totals["overflow"]:
        failures.append("fresh candidate accounting drifted")
    if totals["candidate_entries"] != len(entries) or entry_draws != totals["entry_draws"]:
        failures.append("prepared-candidate entry totals drifted")
    eligible_entries = [entry for entry in entries if entry["mechanically_eligible"]]
    if (
        totals["mechanically_eligible_entries"] != len(eligible_entries)
        or totals["mechanically_eligible_draws"]
        != sum(entry["draws"] for entry in eligible_entries)
    ):
        failures.append("mechanically eligible candidate totals drifted")
    ineligible_entries = [
        entry for entry in entries if not entry["mechanically_eligible"]
    ]
    if (
        totals["mechanically_ineligible_entries"] != len(ineligible_entries)
        or totals["mechanically_ineligible_draws"]
        != sum(entry["draws"] for entry in ineligible_entries)
        or totals["mechanically_eligible_entries"]
        + totals["mechanically_ineligible_entries"]
        != totals["candidate_entries"]
        or totals["mechanically_eligible_draws"]
        + totals["mechanically_ineligible_draws"]
        != totals["entry_draws"]
    ):
        failures.append("mechanical admission partition drifted")
    lod_entries = [entry for entry in entries if entry["title_lod_valid"]]
    if (
        totals["title_lod_entries"] != len(lod_entries)
        or totals["title_lod_draws"]
        != sum(entry["draws"] for entry in lod_entries)
    ):
        failures.append("title LOD candidate totals drifted")
    track_provider_entries = [
        entry for entry in entries if entry["track_texture_provider"]
    ]
    if (
        totals["track_texture_provider_entries"] != len(track_provider_entries)
        or totals["track_texture_provider_draws"]
        != sum(entry["draws"] for entry in track_provider_entries)
    ):
        failures.append("track texture provider candidate totals drifted")
    if totals["capacity"] != 4096 or totals["policy_age_limit_frames"] != 1:
        failures.append("prepared-candidate bounds drifted")
    if totals["selected_joins"] > integer(workset, "selected_joins"):
        failures.append("prepared selected joins exceed workset joins")
    for key in ("future_exclusions", "overflow"):
        if totals[key]:
            failures.append(f"{key} is nonzero")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "static_contract": contract,
        "totals": totals,
        "entries": entries,
        "mechanical_rejection_entry_counts": rejection_entry_counts,
        "mechanical_rejection_draw_counts": rejection_draw_counts,
        "qualification": {
            "fresh_visibility_prepared_handoff_proved": not failures,
            "isolated_native_candidate_proved": not failures
            and bool(eligible_entries),
            "title_lod_lineage_proved": not failures and bool(lod_entries),
            "track_texture_provider_lineage_proved": (
                not failures and bool(track_provider_entries)
            ),
            "native_draw_enabled": False,
            "suppression_allowed": False,
        },
        "safety": {
            "guest_state_changed": False,
            "control_flow_changed": False,
            "native_upload": False,
            "native_draw": False,
            "xenos_draw_preserved": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("events", nargs="+", type=pathlib.Path)
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(
            read_events(args.events),
            json.loads(args.static.read_text(encoding="utf-8")),
            args.session,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if document["status"] != "complete":
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(
            f"native renderer prepared visibility summary failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
