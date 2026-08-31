"""Join track RTTI identity to procedural-model semantic submissions."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-track-world-join.v1"
INGRESS_SCHEMA = "pinyon-shift.native-renderer-track-ingress.v1"
SUBMISSION_SCHEMA = "pinyon-shift.native-renderer-semantic-submissions.v4"
TRACK_TEXTURE_CLASS = "track_texture_unified"
PROVIDER_METHOD_SLOTS = (6, 9, 10, 11)


def _validate_input(ingress: dict, submissions: dict) -> tuple[str, tuple[str, ...]]:
    if ingress.get("schema") != INGRESS_SCHEMA or ingress.get("status") != "complete":
        raise ValueError("track-ingress static proof is incomplete or unsupported")
    if (
        ingress.get("classification")
        != "title_track_world_ingress_statically_proved"
    ):
        raise ValueError("track-ingress classification drifted")
    ingress_safety = ingress.get("safety", {})
    if (
        ingress_safety.get("runtime_hook_enabled") is not False
        or ingress_safety.get("native_admission") is not False
        or ingress_safety.get("suppression_allowed") is not False
        or ingress_safety.get("xenos_authority_required") is not True
    ):
        raise ValueError("track-ingress safety boundary drifted")

    if (
        submissions.get("schema") != SUBMISSION_SCHEMA
        or submissions.get("status") != "complete"
    ):
        raise ValueError("semantic-submission report is incomplete or unsupported")
    submission_safety = submissions.get("safety", {})
    if (
        submission_safety.get("native_draw") is not False
        or submission_safety.get("suppression_allowed") is not False
        or submission_safety.get("xenos_authority") is not True
    ):
        raise ValueError("semantic-submission safety boundary drifted")

    texture = ingress.get("classes", {}).get(TRACK_TEXTURE_CLASS, {})
    vtable = str(texture.get("vtable_address", ""))
    if (
        texture.get("decorated_name")
        != ".?AVCTrackTexture_Unified@Presentation_Unified@@"
        or vtable != "82001708"
        or texture.get("vtable_slot_count") != 14
    ):
        raise ValueError("unified track-texture RTTI identity drifted")
    candidates = ingress.get("passive_observation_candidates", {}).get(
        TRACK_TEXTURE_CLASS, []
    )
    by_slot = {int(row.get("slot", -1)): str(row.get("target", "")) for row in candidates}
    methods = tuple(by_slot.get(slot, "") for slot in PROVIDER_METHOD_SLOTS)
    if methods != ("824107C8", "824108D0", "82DF1300", "82DF0B40"):
        raise ValueError("unified track-texture provider methods drifted")
    return vtable, methods


def build(ingress: dict, submissions: dict) -> dict:
    track_vtable, expected_methods = _validate_input(ingress, submissions)
    matched = []
    matched_calls = 0
    unmatched_calls = 0
    method_mismatch_calls = 0
    resource_keys: collections.Counter[str] = collections.Counter()
    provider_selections: collections.Counter[str] = collections.Counter()
    object_sources: collections.Counter[str] = collections.Counter()
    first_frame = None
    last_frame = None

    for entry in submissions.get("entries", []):
        calls = int(entry.get("calls", 0))
        resources = entry.get("resources", {})
        provider = resources.get("primary_provider", {})
        if str(provider.get("vtable", "")) != track_vtable:
            unmatched_calls += calls
            continue
        methods = tuple(
            str(provider.get(key, ""))
            for key in (
                "predicate_24_method",
                "primary_36_method",
                "fallback_40_method",
                "predicate_44_method",
            )
        )
        if methods != expected_methods:
            method_mismatch_calls += calls
            continue
        frames = entry.get("frames", [])
        if len(frames) != 2:
            raise ValueError("semantic-submission frame range is malformed")
        matched.append(str(entry.get("key", "")))
        matched_calls += calls
        first_frame = frames[0] if first_frame is None else min(first_frame, frames[0])
        last_frame = frames[1] if last_frame is None else max(last_frame, frames[1])
        resource_keys[str(resources.get("primary_key", ""))] += calls
        provider_selections[str(provider.get("selection", ""))] += calls
        object_sources[str(provider.get("object_source", ""))] += calls

    failures = []
    if not matched:
        failures.append("no procedural-model submission joins the track texture provider")
    if method_mismatch_calls:
        failures.append("track texture provider method tuple drifted at runtime")

    return {
        "schema": SCHEMA,
        "session": submissions.get("session"),
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "classification": "exact_track_texture_provider_to_prepared_record_join",
        "track_provider": {
            "class": "Presentation_Unified::CTrackTexture_Unified",
            "decorated_name": ".?AVCTrackTexture_Unified@Presentation_Unified@@",
            "vtable": track_vtable,
            "provider_method_vtable_offsets": [24, 36, 40, 44],
            "provider_methods": list(expected_methods),
        },
        "coverage": {
            "matched_submission_entries": len(matched),
            "matched_submission_calls": matched_calls,
            "unmatched_submission_calls": unmatched_calls,
            "method_mismatch_calls": method_mismatch_calls,
            "first_frame": first_frame,
            "last_frame": last_frame,
            "resource_keys_by_calls": dict(sorted(resource_keys.items())),
            "provider_selections_by_calls": dict(sorted(provider_selections.items())),
            "object_sources_by_calls": dict(sorted(object_sources.items())),
        },
        "remaining_identity_gap": {
            "track_texture_ownership_proved": bool(matched),
            "track_model_or_mesh_ownership_proved": False,
            "terrain_or_road_visual_identity_proved": False,
            "next_join": "track_model_mesh_or_world_section_to_same_prepared_records",
        },
        "safety": {
            "payload_free_report": True,
            "runtime_hook_added": False,
            "guest_state_changed": False,
            "native_admission": False,
            "suppression_allowed": False,
            "xenos_authority": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingress", required=True, type=pathlib.Path)
    parser.add_argument("--submissions", required=True, type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        report = build(
            json.loads(args.ingress.read_text(encoding="utf-8")),
            json.loads(args.submissions.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
