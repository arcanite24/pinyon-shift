"""Build deterministic target phases from a payload-free RenderDoc trace."""

import argparse
import hashlib
import json
import pathlib
import sys


TRACE_SCHEMA = "pinyon-shift.native-renderer-renderdoc-pass-trace.v1"
SCHEMA = "pinyon-shift.native-renderer-pass-inventory.v1"


def target_key(draw):
    colors = tuple(
        (item["resource_id"], item["mip"], item["slice"])
        for item in draw.get("color_targets", [])
    )
    depth = draw.get("depth_target")
    depth_key = None if depth is None else (
        depth["resource_id"], depth["mip"], depth["slice"]
    )
    return colors, depth_key


def pipeline_signature(draw):
    return {
        key: draw.get(key)
        for key in (
            "pipeline",
            "pipeline_name",
            "vertex_shader",
            "vertex_shader_name",
            "pixel_shader",
            "pixel_shader_name",
            "primitive_topology",
            "viewport",
            "scissor",
            "depth_state",
            "raster_state",
        )
        if key in draw
    }


def build_inventory(trace):
    if trace.get("schema") != TRACE_SCHEMA:
        raise ValueError("unsupported pass trace schema")
    safety = trace.get("safety", {})
    if safety.get("resource_payload_exported") is not False:
        raise ValueError("pass trace does not prove its payload-free boundary")
    events = trace.get("events")
    if not isinstance(events, list):
        raise ValueError("pass trace events must be a list")

    phases = []
    current = None
    pending_boundaries = []
    last_event = -1
    ignored_native_draws = 0
    authoritative_candidates = 0
    for event in events:
        event_id = event.get("event_id")
        if not isinstance(event_id, int) or event_id < last_event:
            raise ValueError("pass trace events are not monotonically ordered")
        last_event = event_id
        kind = event.get("kind")
        if kind == "boundary":
            pending_boundaries.extend(event.get("boundary_kinds", []))
            continue
        if kind != "draw":
            raise ValueError("pass trace contains an unknown event kind")
        if event.get("isolated_native") is True:
            ignored_native_draws += 1
            continue

        key = target_key(event)
        must_split = current is None or key != current["_key"] or bool(pending_boundaries)
        if must_split:
            current = {
                "ordinal": len(phases) + 1,
                "first_draw_event": event_id,
                "last_draw_event": event_id,
                "draw_count": 0,
                "index_count_total": 0,
                "candidate_draw_count": 0,
                "boundary_before": sorted(set(pending_boundaries)),
                "color_targets": event.get("color_targets", []),
                "depth_target": event.get("depth_target"),
                "pipeline_signatures": {},
                "_key": key,
            }
            phases.append(current)
        current["last_draw_event"] = event_id
        current["draw_count"] += 1
        current["index_count_total"] += int(event.get("index_count", 0))
        if event.get("authoritative_candidate") is True:
            current["candidate_draw_count"] += 1
            authoritative_candidates += 1
        signature = pipeline_signature(event)
        if signature:
            signature_key = hashlib.sha256(
                json.dumps(
                    signature, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest().upper()
            entry = current["pipeline_signatures"].setdefault(
                signature_key,
                {"signature": signature, "draw_count": 0},
            )
            entry["draw_count"] += 1
        pending_boundaries = []

    for phase in phases:
        phase.pop("_key")
        phase["pipeline_signatures"] = [
            {"sha256": key, **value}
            for key, value in sorted(phase["pipeline_signatures"].items())
        ]
        phase["qualification"] = (
            "candidate_phase"
            if phase["candidate_draw_count"]
            else "metadata_inventory_only"
        )
        phase["suppression_eligible"] = False
    return {
        "schema": SCHEMA,
        "capture": trace.get("capture"),
        "totals": {
            "phases": len(phases),
            "draws": sum(phase["draw_count"] for phase in phases),
            "isolated_native_draws_ignored": ignored_native_draws,
            "authoritative_candidate_draws": authoritative_candidates,
        },
        "phases": phases,
        "safety": {
            "metadata_only": True,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        trace_bytes = args.trace.read_bytes()
        trace = json.loads(trace_bytes)
        inventory = build_inventory(trace)
        inventory["trace_sha256"] = hashlib.sha256(trace_bytes).hexdigest().upper()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print("native renderer pass inventory failed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
