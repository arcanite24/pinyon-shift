"""Build a fail-closed post-chain topology from payload-free capture metadata."""

import argparse
import hashlib
import json
import pathlib
import sys


USAGE_SCHEMA = "pinyon-shift.native-renderer-renderdoc-target-usage.v1"
PASS_SCHEMA = "pinyon-shift.native-renderer-renderdoc-pass-trace.v1"
SCHEMA = "pinyon-shift.native-renderer-post-chain-census.v1"
WRITE_USAGES = {"ColorTarget", "CopyDst", "ResolveDst", "Clear"}
READ_USAGES = {"PS_Resource", "CS_Resource", "CopySrc", "ResolveSrc"}


def canonical_sha256(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()


def draw_signature(draw):
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
            "color_targets",
            "depth_target",
        )
    }


def is_fullscreen_candidate(draw):
    viewport = draw.get("viewport") or {}
    depth_state = draw.get("depth_state") or {}
    return (
        0 < int(draw.get("index_count", 0)) <= 6
        and int(draw.get("instance_count", 0)) == 1
        and bool(draw.get("color_targets"))
        and draw.get("pixel_shader") is not None
        and viewport.get("enabled") is True
        and float(viewport.get("width", 0)) > 0
        and float(viewport.get("height", 0)) > 0
        and depth_state.get("writes") is not True
    )


def build_census(target_usage, pass_trace):
    if target_usage.get("schema") != USAGE_SCHEMA:
        raise ValueError("unsupported target-usage schema")
    if pass_trace.get("schema") != PASS_SCHEMA:
        raise ValueError("unsupported pass-trace schema")
    usage_safety = target_usage.get("safety", {})
    pass_safety = pass_trace.get("safety", {})
    if usage_safety.get("resource_payload_exported") is not False:
        raise ValueError("target usage does not prove its payload-free boundary")
    if usage_safety.get("action_metadata_only") is not True:
        raise ValueError("target usage is not action-metadata-only")
    if pass_safety.get("resource_payload_exported") is not False:
        raise ValueError("pass trace does not prove its payload-free boundary")
    if target_usage.get("capture", {}).get("sha256") != pass_trace.get(
        "capture", {}
    ).get("sha256"):
        raise ValueError("target usage and pass trace captures differ")
    resources = target_usage.get("resources")
    transfers = target_usage.get("transfers", [])
    events = pass_trace.get("events")
    if (
        not isinstance(resources, list)
        or not isinstance(transfers, list)
        or not isinstance(events, list)
    ):
        raise ValueError("census inputs must contain arrays")

    draws = {
        event["event_id"]: event
        for event in events
        if event.get("kind") == "draw" and event.get("isolated_native") is not True
    }
    present_boundaries = sorted(
        event["event_id"]
        for event in events
        if event.get("kind") == "boundary"
        and "present" in event.get("boundary_kinds", [])
    )
    edges = []
    unresolved_reads = []
    presentation_sinks = []
    produced_events = set()
    writes_by_resource = {}
    transfer_by_destination_event = {}
    for transfer in transfers:
        event_id = transfer.get("event_id")
        source = transfer.get("source_resource_id")
        destination = transfer.get("destination_resource_id")
        if (
            not isinstance(event_id, int)
            or not isinstance(source, str)
            or not isinstance(destination, str)
            or transfer.get("kind") not in {"copy", "resolve"}
        ):
            raise ValueError("target transfer inventory is invalid")
        key = (destination, event_id)
        if key in transfer_by_destination_event:
            raise ValueError("duplicate target transfer destination")
        transfer_by_destination_event[key] = transfer
    for resource in resources:
        identifier = resource.get("resource_id")
        usages = resource.get("usages")
        if not isinstance(identifier, str) or not isinstance(usages, list):
            raise ValueError("target resource inventory is invalid")
        writes_by_resource[identifier] = [
            (usage.get("event_id"), usage.get("usage"))
            for usage in usages
            if usage.get("usage") in WRITE_USAGES
        ]

    def resolve_producer(identifier, before_event, visited=None):
        visited = set() if visited is None else set(visited)
        key = (identifier, before_event)
        if key in visited:
            return None
        visited.add(key)
        prior = [
            item
            for item in writes_by_resource.get(identifier, [])
            if isinstance(item[0], int) and item[0] < before_event
        ]
        if not prior:
            return None
        event_id, kind = prior[-1]
        if kind == "ColorTarget" and event_id in draws:
            return event_id
        if kind in {"CopyDst", "ResolveDst"}:
            transfer = transfer_by_destination_event.get((identifier, event_id))
            if transfer is not None:
                return resolve_producer(
                    transfer["source_resource_id"], event_id, visited
                )
        return None

    for resource in resources:
        identifier = resource.get("resource_id")
        usages = resource.get("usages")
        if not isinstance(identifier, str) or not isinstance(usages, list):
            raise ValueError("target resource inventory is invalid")
        last_event = -1
        writes = []
        resource_sinks = []
        for usage in usages:
            event_id = usage.get("event_id")
            kind = usage.get("usage")
            if not isinstance(event_id, int) or event_id < last_event:
                raise ValueError("target usages are not monotonically ordered")
            if not isinstance(kind, str) or not kind:
                raise ValueError("target usage kind is invalid")
            last_event = event_id
            if kind in WRITE_USAGES:
                writes.append((event_id, kind))
                if kind == "ColorTarget" and event_id in draws:
                    produced_events.add(event_id)
            if kind in READ_USAGES:
                prior = [item for item in writes if item[0] < event_id]
                producer = prior[-1] if prior else None
                resolved_producer = resolve_producer(identifier, event_id)
                if resolved_producer is not None and event_id in draws:
                    edges.append(
                        {
                            "resource_id": identifier,
                            "resource_name": resource.get("resource_name", ""),
                            "producer_event": resolved_producer,
                            "consumer_event": event_id,
                            "read_usage": kind,
                        }
                    )
                else:
                    unresolved_reads.append(
                        {
                            "resource_id": identifier,
                            "consumer_event": event_id,
                            "read_usage": kind,
                            "last_write_event": None if producer is None else producer[0],
                            "last_write_usage": None if producer is None else producer[1],
                        }
                    )
            if kind == "Present":
                prior = [item for item in writes if item[0] < event_id]
                sink = prior[-1] if prior else None
                if sink is not None and sink[1] == "ColorTarget" and sink[0] in draws:
                    resource_sinks.append(
                        {
                            "resource_id": identifier,
                            "present_event": event_id,
                            "producer_event": sink[0],
                        }
                    )
        if (
            not resource_sinks
            and str(resource.get("resource_name", "")).startswith(
                "Swapchain Image "
            )
        ):
            color_writes = [
                item
                for item in writes
                if item[1] == "ColorTarget" and item[0] in draws
            ]
            if color_writes:
                sink = color_writes[-1]
                present_event = next(
                    (
                        event_id
                        for event_id in present_boundaries
                        if event_id > sink[0]
                    ),
                    None,
                )
                if present_event is not None:
                    resource_sinks.append(
                        {
                            "resource_id": identifier,
                            "present_event": present_event,
                            "producer_event": sink[0],
                            "present_source": "swapchain_name_and_boundary",
                        }
                    )
        presentation_sinks.extend(resource_sinks)

    incoming = {}
    for edge in edges:
        incoming.setdefault(edge["consumer_event"], []).append(edge)
    reachable = set()
    pending = [sink["producer_event"] for sink in presentation_sinks]
    while pending:
        event_id = pending.pop()
        if event_id in reachable:
            continue
        reachable.add(event_id)
        pending.extend(
            edge["producer_event"] for edge in incoming.get(event_id, [])
        )

    candidates = []
    for event_id in sorted(reachable):
        draw = draws[event_id]
        if not is_fullscreen_candidate(draw):
            continue
        signature = draw_signature(draw)
        candidates.append(
            {
                "event_id": event_id,
                "sha256": canonical_sha256(signature),
                "signature": signature,
                "index_count": int(draw.get("index_count", 0)),
                "semantic_role": "operator_review_required",
                "native_coverage": False,
                "suppression_eligible": False,
            }
        )
    presentation_source_boundaries = sorted(
        sink["producer_event"]
        for sink in presentation_sinks
        if not incoming.get(sink["producer_event"])
    )
    return {
        "schema": SCHEMA,
        "capture": pass_trace.get("capture"),
        "totals": {
            "target_resources": len(resources),
            "transfers": len(transfers),
            "produced_draw_events": len(produced_events),
            "resource_edges": len(edges),
            "unresolved_reads": len(unresolved_reads),
            "presentation_sinks": len(presentation_sinks),
            "presentation_reachable_draws": len(reachable),
            "fullscreen_candidates": len(candidates),
            "presentation_source_boundaries": len(
                presentation_source_boundaries
            ),
        },
        "presentation_sinks": presentation_sinks,
        "edges": sorted(
            edges,
            key=lambda edge: (
                edge["consumer_event"],
                edge["producer_event"],
                edge["resource_id"],
            ),
        ),
        "unresolved_reads": unresolved_reads,
        "presentation_reachable_events": sorted(reachable),
        "presentation_source_boundaries": presentation_source_boundaries,
        "fullscreen_candidates": candidates,
        "qualification": {
            "presentation_topology_observed": bool(presentation_sinks),
            "presentation_ingress_resolved": bool(presentation_sinks)
            and not presentation_source_boundaries,
            "effect_semantics_proven": False,
            "ui_composite_boundary_proven": False,
            "native_implementation_ready": False,
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
    parser.add_argument("target_usage", type=pathlib.Path)
    parser.add_argument("pass_trace", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        usage_bytes = args.target_usage.read_bytes()
        pass_bytes = args.pass_trace.read_bytes()
        result = build_census(json.loads(usage_bytes), json.loads(pass_bytes))
        result["target_usage_sha256"] = hashlib.sha256(usage_bytes).hexdigest().upper()
        result["pass_trace_sha256"] = hashlib.sha256(pass_bytes).hexdigest().upper()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(result["totals"], sort_keys=True),
            file=sys.stdout,
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print("native renderer post-chain census failed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
