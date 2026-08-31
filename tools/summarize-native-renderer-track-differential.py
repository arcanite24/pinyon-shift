"""Compare exact prepared title families across isolated track modes."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-track-differential.v3"
MINIMUM_MATERIAL_DELTA_PER_1000_FRAMES = 5.0
MINIMUM_MATERIAL_RELATIVE_DELTA = 0.05
MAXIMUM_CHANGED_FAMILY_DETAILS = 128
CONFIG = "native_renderer.discovery.track_render_config"
DRAW_WINDOW = "native_renderer.census.draw_window"
PROVENANCE = "native_renderer.discovery.title_provenance_entry"
PREPARED_CANDIDATE = (
    "native_renderer.discovery.semantic_visibility_prepared_candidate_entry"
)
INSTALLED = "native_renderer.census.installed"
MODE_VALUES = {
    "baseline": (False, True, True, 55.0),
    "trackfardistance": (False, True, True, 5.0),
    "fasttrackrender": (True, True, True, 55.0),
    "noroaddetailblur": (False, False, True, 55.0),
    "notrackcommandbuffers": (False, True, False, 55.0),
}


def read_events(paths):
    events = []
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"invalid JSON at {path}:{line_number}: {error}")
                if isinstance(event, dict):
                    events.append(event)
    return events


def integer(event, key):
    try:
        return int(event[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key} in {event.get('event', 'event')}") from error


def boolean(event, key):
    value = event.get(key)
    if value not in ("true", "false"):
        raise ValueError(f"invalid {key} in {event.get('event', 'event')}")
    return value == "true"


def hexadecimal(event, key, width):
    value = str(event.get(key, "")).upper()
    if len(value) != width or any(
        character not in "0123456789ABCDEF" for character in value
    ):
        raise ValueError(f"invalid {key} in {event.get('event', 'event')}")
    return value


def session_events(events, requested_session=None):
    sessions = {
        str(event.get("session"))
        for event in events
        if event.get("event") == CONFIG and event.get("session")
    }
    if requested_session:
        if requested_session not in sessions:
            raise ValueError(f"track configuration missing for {requested_session}")
        session = requested_session
    elif len(sessions) == 1:
        session = next(iter(sessions))
    else:
        raise ValueError("input must contain exactly one track-config session")
    return session, [event for event in events if event.get("session") == session]


def summarize_side(events, expected_mode, requested_session=None):
    if expected_mode not in MODE_VALUES:
        raise ValueError(f"unsupported track mode: {expected_mode}")
    session, selected = session_events(events, requested_session)
    configs = [event for event in selected if event.get("event") == CONFIG]
    starts = [event for event in selected if event.get("event") == "process.start"]
    shutdowns = [event for event in selected if event.get("event") == "process.shutdown"]
    installed = [event for event in selected if event.get("event") == INSTALLED]
    windows = [event for event in selected if event.get("event") == DRAW_WINDOW]
    if len(configs) != 1 or len(starts) != 1 or len(shutdowns) != 1:
        raise ValueError("session lifecycle or track configuration is incomplete")
    if len(installed) != 1 or not windows:
        raise ValueError("census installation or draw windows are missing")

    config = configs[0]
    failures = []
    if config.get("status") != "complete" or config.get("mode") != expected_mode:
        failures.append("title did not confirm the requested track mode")
    expected_fast, expected_road_blur, expected_command_buffers, expected_far = MODE_VALUES[
        expected_mode
    ]
    for field, expected, label in (
        ("fast_track_render", expected_fast, "fast-track"),
        ("road_detail_blur", expected_road_blur, "road-detail blur"),
        ("track_command_buffers", expected_command_buffers, "track command-buffer"),
    ):
        if boolean(config, field) != expected:
            failures.append(
                f"{label} runtime value does not match the requested mode"
            )
    try:
        track_far_distance = float(config.get("track_far_distance", "nan"))
    except (TypeError, ValueError):
        track_far_distance = float("nan")
    if track_far_distance != expected_far:
        failures.append("track far distance does not match the requested mode")
    if not boolean(config, "address_consistent"):
        failures.append("command-line/runtime render-state identity drifted")
    if (
        not boolean(config, "xenos_authority")
        or boolean(config, "native_draw")
        or boolean(config, "suppression_allowed")
    ):
        failures.append("track differential violated the observation-only boundary")

    frame_count = 0
    draw_count = 0
    for window in windows:
        first = integer(window, "first_frame")
        last = integer(window, "last_frame")
        if last < first:
            failures.append("draw-window frame bounds are invalid")
            continue
        frame_count += last - first + 1
        draw_count += integer(window, "draws")
        if integer(window, "overflow_draws"):
            failures.append("draw-signature table overflowed")
    if frame_count < 600:
        failures.append("fewer than 600 census frames were observed")

    signatures = collections.defaultdict(
        lambda: {
            "calls": 0,
            "vertex_shaders": set(),
            "pixel_shaders": set(),
            "template_keys": set(),
            "receiver_generations": set(),
        }
    )
    for event in selected:
        if (
            event.get("event") != PROVENANCE
            or event.get("outcome") != "prepared"
            or event.get("semantic_identity") != "procedural_model_submission"
        ):
            continue
        signature = str(event.get("prepared_signature", "")).upper()
        if len(signature) != 16:
            failures.append("prepared semantic signature is invalid")
            continue
        entry = signatures[signature]
        entry["calls"] += integer(event, "calls")
        for source, destination in (
            ("semantic_vertex_shader", "vertex_shaders"),
            ("semantic_pixel_shader", "pixel_shaders"),
            ("semantic_template_key", "template_keys"),
        ):
            value = str(event.get(source, "")).upper()
            if value:
                entry[destination].add(value)
        receiver = (
            str(event.get("semantic_receiver_address", "")).upper(),
            str(event.get("semantic_receiver_generation", "")),
            str(event.get("semantic_record_index", "")),
        )
        entry["receiver_generations"].add(receiver)
        if (
            event.get("xenos_draw") != "preserved"
            or event.get("suppression_eligible") != "false"
        ):
            failures.append("semantic provenance violated Xenos safety")
    if not signatures:
        failures.append("no exact semantic prepared families were observed")

    prepared_candidates = collections.defaultdict(list)
    for event in selected:
        if event.get("event") != PREPARED_CANDIDATE:
            continue
        signature = hexadecimal(event, "prepared_signature", 16)
        rejection_mask = hexadecimal(event, "mechanical_rejection_mask", 8)
        mechanically_eligible = boolean(event, "mechanically_eligible")
        if mechanically_eligible != (rejection_mask == "00000000"):
            failures.append("prepared candidate eligibility disagrees with its mask")
        if (
            boolean(event, "guest_state_changed")
            or boolean(event, "control_flow_changed")
            or boolean(event, "native_upload")
            or boolean(event, "native_draw")
            or event.get("xenos_draw") != "preserved"
            or boolean(event, "suppression_allowed")
        ):
            failures.append("prepared candidate violated Xenos safety")
        first_frame = integer(event, "first_frame")
        last_frame = integer(event, "last_frame")
        if last_frame < first_frame:
            failures.append("prepared candidate frame bounds are invalid")
        prepared_candidates[signature].append(
            {
                "candidate_key": hexadecimal(event, "candidate_key", 16),
                "draws": integer(event, "draws"),
                "first_frame": first_frame,
                "last_frame": last_frame,
                "mechanically_eligible": mechanically_eligible,
                "mechanical_rejection_mask": rejection_mask,
                "visibility_category": str(event.get("visibility_category", "")),
                "visibility_result_mask": str(event.get("visibility_result_mask", "")),
            }
        )

    return {
        "session": session,
        "mode": expected_mode,
        "status": "complete" if not failures else "incomplete",
        "failures": sorted(set(failures)),
        "scene": installed[0].get("scene"),
        "identity": {
            "executable_sha256": starts[0].get("executable_sha256"),
            "patch_set_sha256": starts[0].get("rexglue_patch_set_sha256"),
            "patch_count": starts[0].get("rexglue_patch_count"),
        },
        "frames": frame_count,
        "draws": draw_count,
        "signatures": signatures,
        "prepared_candidates": prepared_candidates,
    }


def build(
    baseline_events,
    track_events,
    baseline_session=None,
    track_session=None,
    track_mode="fasttrackrender",
):
    baseline = summarize_side(baseline_events, "baseline", baseline_session)
    track = summarize_side(track_events, track_mode, track_session)
    failures = [
        *(f"baseline: {failure}" for failure in baseline["failures"]),
        *(f"{track_mode}: {failure}" for failure in track["failures"]),
    ]
    if baseline["session"] == track["session"]:
        failures.append("baseline and fast-track sessions are identical")
    if baseline["scene"] != track["scene"] or baseline["scene"] in (None, "unmarked"):
        failures.append("paired sessions do not share one marked scene")
    if baseline["identity"] != track["identity"]:
        failures.append("paired sessions do not use one build identity")

    rows = []
    signatures = set(baseline["signatures"]) | set(track["signatures"])
    for signature in signatures:
        left = baseline["signatures"].get(signature)
        right = track["signatures"].get(signature)
        left_calls = left["calls"] if left else 0
        right_calls = right["calls"] if right else 0
        left_rate = left_calls * 1000.0 / max(1, baseline["frames"])
        right_rate = right_calls * 1000.0 / max(1, track["frames"])
        metadata = right or left
        rows.append(
            {
                "prepared_signature": signature,
                "baseline_calls": left_calls,
                f"{track_mode}_calls": right_calls,
                "baseline_calls_per_1000_frames": round(left_rate, 3),
                f"{track_mode}_calls_per_1000_frames": round(right_rate, 3),
                "delta_calls_per_1000_frames": round(right_rate - left_rate, 3),
                "vertex_shaders": sorted(metadata["vertex_shaders"]),
                "pixel_shaders": sorted(metadata["pixel_shaders"]),
                "template_keys": sorted(metadata["template_keys"]),
                "receiver_generations": [
                    {
                        "address": address,
                        "generation": generation,
                        "record_index": record_index,
                    }
                    for address, generation, record_index in sorted(
                        metadata["receiver_generations"]
                    )
                ],
            }
        )
    rows.sort(
        key=lambda row: (
            -abs(row["delta_calls_per_1000_frames"]),
            row["prepared_signature"],
        )
    )
    observed_changed = [
        row for row in rows if row["delta_calls_per_1000_frames"] != 0
    ]
    changed = []
    for row in observed_changed:
        delta = abs(row["delta_calls_per_1000_frames"])
        peak = max(
            row["baseline_calls_per_1000_frames"],
            row[f"{track_mode}_calls_per_1000_frames"],
        )
        relative_delta = delta / peak if peak else 0.0
        appeared_or_disappeared = (
            row["baseline_calls"] == 0 or row[f"{track_mode}_calls"] == 0
        )
        if delta >= MINIMUM_MATERIAL_DELTA_PER_1000_FRAMES and (
            appeared_or_disappeared
            or relative_delta >= MINIMUM_MATERIAL_RELATIVE_DELTA
        ):
            changed.append(row)
    if not changed:
        failures.append("no prepared semantic family materially changed between modes")

    detailed_changed = changed[:MAXIMUM_CHANGED_FAMILY_DETAILS]
    changed_signatures = {row["prepared_signature"] for row in changed}
    candidate_rows = []
    for side_name, side in (("baseline", baseline), (track_mode, track)):
        for signature, entries in side["prepared_candidates"].items():
            if signature not in changed_signatures:
                continue
            for entry in entries:
                candidate_rows.append(
                    {
                        "session_mode": side_name,
                        "prepared_signature": signature,
                        **entry,
                    }
                )
    candidate_rows.sort(
        key=lambda row: (
            row["prepared_signature"],
            row["session_mode"],
            row["first_frame"],
            row["candidate_key"],
        )
    )
    joined_signatures = {row["prepared_signature"] for row in candidate_rows}
    eligible_signatures = {
        row["prepared_signature"]
        for row in candidate_rows
        if row["mechanically_eligible"]
    }
    rejection_mask_counts = collections.Counter(
        row["mechanical_rejection_mask"] for row in candidate_rows
    )

    return {
        "schema": SCHEMA,
        "status": "complete" if not failures else "incomplete",
        "failures": failures,
        "scene": baseline["scene"],
        "build_identity": baseline["identity"],
        "sessions": {
            "baseline": {
                "session": baseline["session"],
                "frames": baseline["frames"],
                "draws": baseline["draws"],
            },
            track_mode: {
                "session": track["session"],
                "frames": track["frames"],
                "draws": track["draws"],
            },
        },
        "changed_family_count": len(changed),
        "changed_family_detail_count": len(detailed_changed),
        "changed_family_details_truncated": len(changed) > len(detailed_changed),
        "changed_families": detailed_changed,
        "rate_noise_family_count": len(observed_changed) - len(changed),
        "material_delta_threshold": {
            "minimum_absolute_calls_per_1000_frames": MINIMUM_MATERIAL_DELTA_PER_1000_FRAMES,
            "minimum_relative_delta": MINIMUM_MATERIAL_RELATIVE_DELTA,
            "appearance_or_disappearance_bypasses_relative_threshold": True,
        },
        "semantic_visibility_join": {
            "changed_signature_count_with_candidate_lineage": len(joined_signatures),
            "candidate_entry_count": len(candidate_rows),
            "mechanically_eligible_changed_signature_count": len(
                eligible_signatures
            ),
            "mechanically_eligible_changed_signatures": sorted(
                eligible_signatures
            ),
            "rejection_mask_entry_counts": dict(
                sorted(rejection_mask_counts.items())
            ),
            "candidate_entries": candidate_rows,
            "representative_gameplay_identity_proved": False,
            "native_admission_allowed": False,
        },
        "qualification": {
            "title_track_render_delta_proved": not failures,
            "isolated_mode": track_mode,
            "terrain_road_semantic_identity_proved": False,
            "native_admission_allowed": False,
            "suppression_allowed": False,
        },
        "safety": {
            "xenos_authority": True,
            "native_draw": False,
            "save_mutation_required": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=pathlib.Path, nargs="+")
    variant = parser.add_mutually_exclusive_group(required=True)
    variant.add_argument("--fasttrackrender", type=pathlib.Path, nargs="+")
    variant.add_argument("--variant", type=pathlib.Path, nargs="+")
    parser.add_argument(
        "--variant-mode",
        choices=tuple(mode for mode in MODE_VALUES if mode != "baseline"),
    )
    parser.add_argument("--baseline-session")
    parser.add_argument("--fasttrackrender-session")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        if args.fasttrackrender:
            variant_paths = args.fasttrackrender
            variant_mode = "fasttrackrender"
        else:
            variant_paths = args.variant
            if not args.variant_mode:
                raise ValueError("--variant-mode is required with --variant")
            variant_mode = args.variant_mode
        document = build(
            read_events(args.baseline),
            read_events(variant_paths),
            args.baseline_session,
            args.fasttrackrender_session,
            variant_mode,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0 if document["status"] == "complete" else 1
    except (OSError, ValueError) as error:
        print(f"native renderer track differential failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
