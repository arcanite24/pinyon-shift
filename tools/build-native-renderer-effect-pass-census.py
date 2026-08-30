"""Build a fail-closed effect-pass census from an enriched RenderDoc trace."""

import argparse
import hashlib
import json
import pathlib
import sys


TRACE_SCHEMA = "pinyon-shift.native-renderer-renderdoc-pass-trace.v1"
SCHEMA = "pinyon-shift.native-renderer-effect-pass-census.v1"


def canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest().upper()


def target_shape(target):
    if target is None:
        return None
    return {
        key: target.get(key)
        for key in ("width", "height", "mip", "slice", "format")
    }


def output_class(draw):
    colors = draw.get("color_targets", [])
    depth = draw.get("depth_target")
    depth_state = draw.get("depth_state", {})
    if not colors and depth is not None:
        if depth_state.get("writes") is True:
            return "depth_only_write_candidate"
        return "depth_only_read_candidate"
    if colors and depth is not None:
        return "color_depth_candidate"
    if colors:
        return "color_only_candidate"
    return "no_output_candidate"


def signature(draw):
    return {
        "output_class": output_class(draw),
        "color_target_shapes": [
            target_shape(target) for target in draw.get("color_targets", [])
        ],
        "depth_target_shape": target_shape(draw.get("depth_target")),
        "pipeline": draw.get("pipeline"),
        "pipeline_name": draw.get("pipeline_name"),
        "vertex_shader": draw.get("vertex_shader"),
        "vertex_shader_name": draw.get("vertex_shader_name"),
        "pixel_shader": draw.get("pixel_shader"),
        "pixel_shader_name": draw.get("pixel_shader_name"),
        "primitive_topology": draw.get("primitive_topology"),
        "viewport": draw.get("viewport"),
        "scissor": draw.get("scissor"),
        "depth_state": draw.get("depth_state"),
        "raster_state": draw.get("raster_state"),
    }


def build_census(trace):
    if trace.get("schema") != TRACE_SCHEMA:
        raise ValueError("unsupported pass trace schema")
    safety = trace.get("safety", {})
    if safety.get("resource_payload_exported") is not False:
        raise ValueError("pass trace does not prove its payload-free boundary")
    if safety.get("pipeline_metadata_only") is not True:
        raise ValueError("pass trace has no enriched pipeline metadata")
    events = trace.get("events")
    if not isinstance(events, list):
        raise ValueError("pass trace events must be a list")

    families = {}
    ignored_native_draws = 0
    last_event = -1
    for event in events:
        event_id = event.get("event_id")
        if not isinstance(event_id, int) or event_id < last_event:
            raise ValueError("pass trace events are not monotonically ordered")
        last_event = event_id
        kind = event.get("kind")
        if kind == "boundary":
            continue
        if kind != "draw":
            raise ValueError("pass trace contains an unknown event kind")
        if event.get("isolated_native") is True:
            ignored_native_draws += 1
            continue
        required = (
            "pipeline",
            "vertex_shader",
            "pixel_shader",
            "primitive_topology",
            "viewport",
            "scissor",
            "depth_state",
            "raster_state",
        )
        if any(key not in event for key in required):
            raise ValueError("draw is missing enriched pipeline metadata")
        value = signature(event)
        key = canonical_sha256(value)
        family = families.setdefault(
            key,
            {
                "sha256": key,
                "signature": value,
                "draw_count": 0,
                "instance_count": 0,
                "index_count": 0,
                "first_event": event_id,
                "last_event": event_id,
                "semantic_role": "unknown_unclassified",
                "native_coverage": False,
                "suppression_eligible": False,
            },
        )
        family["draw_count"] += 1
        family["instance_count"] += int(event.get("instance_count", 0))
        family["index_count"] += int(event.get("index_count", 0))
        family["last_event"] = event_id

    ordered = sorted(
        families.values(),
        key=lambda item: (-item["draw_count"], item["sha256"]),
    )
    counts = {}
    for family in ordered:
        key = family["signature"]["output_class"]
        counts[key] = counts.get(key, 0) + family["draw_count"]
    return {
        "schema": SCHEMA,
        "capture": trace.get("capture"),
        "totals": {
            "draws": sum(item["draw_count"] for item in ordered),
            "families": len(ordered),
            "isolated_native_draws_ignored": ignored_native_draws,
            "draws_by_output_class": dict(sorted(counts.items())),
        },
        "families": ordered,
        "qualification": {
            "pipeline_metadata_census_complete": True,
            "shadow_pass_identified": False,
            "reflection_pass_identified": False,
            "semantic_promotion_requires_external_evidence": True,
        },
        "safety": {
            "metadata_only": True,
            "resource_payload_exported": False,
            "xenos_authority": True,
            "native_coverage": False,
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
        census = build_census(trace)
        census["trace_sha256"] = hashlib.sha256(trace_bytes).hexdigest().upper()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(census, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(
            "native renderer effect-pass census failed: {}".format(error),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
