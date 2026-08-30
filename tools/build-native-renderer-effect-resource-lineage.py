"""Join a RenderDoc resource-usage trace to exact effect-pass metadata."""

import argparse
import hashlib
import json
import pathlib
import sys


USAGE_SCHEMA = "pinyon-shift.native-renderer-renderdoc-resource-usage.v1"
PASS_SCHEMA = "pinyon-shift.native-renderer-renderdoc-pass-trace.v1"
EFFECT_CENSUS_SCHEMA = "pinyon-shift.native-renderer-effect-pass-census.v1"
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


def build_lineage(usage_trace, pass_trace, effect_census=None):
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
    producer_by_event = {}
    if effect_census is not None:
        if effect_census.get("schema") != EFFECT_CENSUS_SCHEMA:
            raise ValueError("unsupported effect-pass census schema")
        if effect_census.get("capture", {}).get("sha256") != usage_capture.get(
            "sha256"
        ):
            raise ValueError("effect-pass census capture differs")
        census_safety = effect_census.get("safety", {})
        if census_safety.get("metadata_only") is not True or census_safety.get(
            "suppression_allowed"
        ) is not False:
            raise ValueError("effect-pass census does not preserve the safety boundary")
        census_families = effect_census.get("families")
        if not isinstance(census_families, list):
            raise ValueError("effect-pass census has no family inventory")
        for family in census_families:
            family_sha256 = family.get("sha256")
            if not isinstance(family_sha256, str) or not family_sha256:
                raise ValueError("effect-pass family has no stable identity")
            event_ids = family.get("event_ids")
            if not isinstance(event_ids, list):
                raise ValueError("effect-pass family has no exact event inventory")
            for event_id in event_ids:
                if not isinstance(event_id, int) or event_id in producer_by_event:
                    raise ValueError("effect-pass event inventory is invalid")
                producer_by_event[event_id] = {
                    "family_sha256": family_sha256,
                    "semantic_role": family.get(
                        "semantic_role", "unknown_unclassified"
                    ),
                    "caster_class": family.get("caster_class"),
                    "atlas_region": family.get("atlas_region"),
                }
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
        producer_families = {
            producer_by_event[event_id]["family_sha256"]: producer_by_event[
                event_id
            ]
            for event_id in epoch["depth_write_events"]
            if event_id in producer_by_event
        }
        classified_shadow_events = [
            event_id
            for event_id in epoch["depth_write_events"]
            if event_id in producer_by_event
            and producer_by_event[event_id]["semantic_role"] == "shadow_depth"
        ]
        epoch["producer_families"] = sorted(
            producer_families.values(),
            key=lambda family: str(family["family_sha256"]),
        )
        epoch["classified_shadow_write_count"] = len(classified_shadow_events)
        epoch["unclassified_write_count"] = (
            epoch["depth_write_count"] - len(classified_shadow_events)
        )
        epoch["caster_classes"] = sorted(
            {
                producer_by_event[event_id]["caster_class"]
                for event_id in classified_shadow_events
                if producer_by_event[event_id]["caster_class"] is not None
            }
        )
        epoch["caster_class_complete"] = bool(epoch["depth_write_count"]) and (
            epoch["unclassified_write_count"] == 0
        )
    ordered_families = sorted(
        consumer_families.values(),
        key=lambda family: (-len(family["read_events"]), family["sha256"]),
    )
    for family in ordered_families:
        family["read_count"] = len(family["read_events"])
    sampled_epochs = sum(epoch["sampled_after_write"] for epoch in epochs)
    classified_shadow_writes = sum(
        epoch["classified_shadow_write_count"] for epoch in epochs
    )
    classified_reflection_writes = sum(
        1
        for epoch in epochs
        for event_id in epoch["depth_write_events"]
        if event_id in producer_by_event
        and producer_by_event[event_id]["semantic_role"]
        == "reflection_capture"
    )
    caster_classes = sorted(
        {
            caster_class
            for epoch in epochs
            for caster_class in epoch["caster_classes"]
        }
    )
    caster_complete_epochs = sum(
        epoch["caster_class_complete"] for epoch in epochs
    )
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
            "classified_shadow_writes": classified_shadow_writes,
            "classified_reflection_writes": classified_reflection_writes,
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
            "producer_caster_inventory_joined": effect_census is not None,
            "caster_classes_identified": caster_classes,
            "caster_complete_epochs": caster_complete_epochs,
            "static_dynamic_caster_separation_ready": (
                bool(epochs)
                and caster_complete_epochs == len(epochs)
                and "dynamic_vehicle" in caster_classes
                and "static_world" in caster_classes
                and "mixed_world" not in caster_classes
            ),
            "shadow_semantic_proved": classified_shadow_writes > 0,
            "reflection_semantic_proved": classified_reflection_writes > 0,
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
    parser.add_argument("--effect-census", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        usage_bytes = args.usage_trace.read_bytes()
        pass_bytes = args.pass_trace.read_bytes()
        effect_bytes = (
            args.effect_census.read_bytes()
            if args.effect_census is not None
            else None
        )
        lineage = build_lineage(
            json.loads(usage_bytes),
            json.loads(pass_bytes),
            json.loads(effect_bytes) if effect_bytes is not None else None,
        )
        lineage["usage_trace_sha256"] = hashlib.sha256(usage_bytes).hexdigest().upper()
        lineage["pass_trace_sha256"] = hashlib.sha256(pass_bytes).hexdigest().upper()
        if effect_bytes is not None:
            lineage["effect_census_sha256"] = hashlib.sha256(
                effect_bytes
            ).hexdigest().upper()
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
