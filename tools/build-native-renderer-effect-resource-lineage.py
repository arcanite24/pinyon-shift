"""Join a RenderDoc resource-usage trace to exact effect-pass metadata."""

import argparse
import hashlib
import json
import pathlib
import sys


USAGE_SCHEMA = "pinyon-shift.native-renderer-renderdoc-resource-usage.v1"
PASS_SCHEMA = "pinyon-shift.native-renderer-renderdoc-pass-trace.v1"
SCHEMA = "pinyon-shift.native-renderer-effect-resource-lineage.v1"
READ_USAGES = {"PS_Resource", "CS_Resource"}


def canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest().upper()


def consumer_signature(draw):
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
            "color_targets",
            "depth_target",
        )
        if key in draw
    }


def build_lineage(usage_trace, pass_trace):
    if usage_trace.get("schema") != USAGE_SCHEMA:
        raise ValueError("unsupported resource-usage schema")
    if pass_trace.get("schema") != PASS_SCHEMA:
        raise ValueError("unsupported pass-trace schema")
    usage_safety = usage_trace.get("safety", {})
    pass_safety = pass_trace.get("safety", {})
    if usage_safety.get("resource_payload_exported") is not False:
        raise ValueError("resource usage does not prove its payload-free boundary")
    if usage_safety.get("action_metadata_only") is not True:
        raise ValueError("resource usage is not action-metadata-only")
    if pass_safety.get("resource_payload_exported") is not False:
        raise ValueError("pass trace does not prove its payload-free boundary")
    usage_capture = usage_trace.get("capture", {})
    pass_capture = pass_trace.get("capture", {})
    if usage_capture.get("sha256") != pass_capture.get("sha256"):
        raise ValueError("resource usage and pass trace captures differ")
    usages = usage_trace.get("usages")
    events = pass_trace.get("events")
    if not isinstance(usages, list) or not isinstance(events, list):
        raise ValueError("lineage inputs must contain event arrays")

    draw_events = {
        event["event_id"]: event
        for event in events
        if event.get("kind") == "draw" and event.get("isolated_native") is not True
    }
    epochs = []
    current = None
    usage_counts = {}
    unique_events = {}
    consumer_families = {}
    pixel_consumer_events = set()
    pixel_consumers_depth_only = set()
    pixel_consumers_with_color = set()
    pixel_consumers_without_output = set()
    last_event = -1
    for item in usages:
        event_id = item.get("event_id")
        usage = item.get("usage")
        if not isinstance(event_id, int) or event_id < last_event:
            raise ValueError("resource usages are not monotonically ordered")
        if not isinstance(usage, str) or not usage:
            raise ValueError("resource usage kind is invalid")
        last_event = event_id
        usage_counts[usage] = usage_counts.get(usage, 0) + 1
        unique_events.setdefault(usage, set()).add(event_id)
        if usage == "Clear":
            current = {
                "ordinal": len(epochs) + 1,
                "clear_event": event_id,
                "last_event": event_id,
                "depth_write_events": [],
                "pixel_read_events": [],
                "compute_read_events": [],
            }
            epochs.append(current)
            continue
        if current is not None:
            current["last_event"] = event_id
            key = {
                "DepthStencilTarget": "depth_write_events",
                "PS_Resource": "pixel_read_events",
                "CS_Resource": "compute_read_events",
            }.get(usage)
            if key is not None and event_id not in current[key]:
                current[key].append(event_id)
        if usage != "PS_Resource":
            continue
        draw = draw_events.get(event_id)
        if draw is None:
            raise ValueError("pixel consumer has no authoritative draw metadata")
        pixel_consumer_events.add(event_id)
        if draw.get("color_targets"):
            pixel_consumers_with_color.add(event_id)
        elif draw.get("depth_target") is not None:
            pixel_consumers_depth_only.add(event_id)
        else:
            pixel_consumers_without_output.add(event_id)
        value = consumer_signature(draw)
        key = canonical_sha256(value)
        family = consumer_families.setdefault(
            key,
            {
                "sha256": key,
                "signature": value,
                "read_events": [],
                "semantic_role": "unknown_unclassified",
                "native_coverage": False,
                "suppression_eligible": False,
            },
        )
        if event_id not in family["read_events"]:
            family["read_events"].append(event_id)

    for epoch in epochs:
        epoch["depth_write_count"] = len(epoch["depth_write_events"])
        epoch["pixel_read_count"] = len(epoch["pixel_read_events"])
        epoch["compute_read_count"] = len(epoch["compute_read_events"])
        epoch["sampled_after_write"] = bool(
            epoch["depth_write_events"]
            and (epoch["pixel_read_events"] or epoch["compute_read_events"])
            and min(epoch["pixel_read_events"] + epoch["compute_read_events"])
            > min(epoch["depth_write_events"])
        )
    ordered_families = sorted(
        consumer_families.values(),
        key=lambda family: (-len(family["read_events"]), family["sha256"]),
    )
    for family in ordered_families:
        family["read_count"] = len(family["read_events"])
    sampled_epochs = sum(epoch["sampled_after_write"] for epoch in epochs)
    return {
        "schema": SCHEMA,
        "capture": usage_capture,
        "resource": usage_trace.get("resource"),
        "totals": {
            "usage_references": len(usages),
            "usage_references_by_kind": dict(sorted(usage_counts.items())),
            "unique_events_by_kind": {
                key: len(value) for key, value in sorted(unique_events.items())
            },
            "clear_epochs": len(epochs),
            "sampled_epochs": sampled_epochs,
            "consumer_families": len(ordered_families),
            "pixel_consumer_events": len(pixel_consumer_events),
            "pixel_consumers_depth_only": len(pixel_consumers_depth_only),
            "pixel_consumers_with_color": len(pixel_consumers_with_color),
            "pixel_consumers_without_output": len(
                pixel_consumers_without_output
            ),
        },
        "epochs": epochs,
        "consumer_families": ordered_families,
        "qualification": {
            "depth_producer_consumer_chain_proved": bool(epochs)
            and sampled_epochs == len(epochs),
            "depth_to_depth_propagation_chain_proved": bool(
                pixel_consumer_events
            )
            and len(pixel_consumers_depth_only) == len(pixel_consumer_events)
            and not pixel_consumers_with_color
            and not pixel_consumers_without_output,
            "direct_color_sampling_observed": bool(pixel_consumers_with_color),
            "shadow_semantic_proved": False,
            "reflection_semantic_proved": False,
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
    parser.add_argument("usage_trace", type=pathlib.Path)
    parser.add_argument("pass_trace", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        usage_bytes = args.usage_trace.read_bytes()
        pass_bytes = args.pass_trace.read_bytes()
        lineage = build_lineage(json.loads(usage_bytes), json.loads(pass_bytes))
        lineage["usage_trace_sha256"] = hashlib.sha256(usage_bytes).hexdigest().upper()
        lineage["pass_trace_sha256"] = hashlib.sha256(pass_bytes).hexdigest().upper()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(lineage, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(
            "native renderer effect resource lineage failed: {}".format(error),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
