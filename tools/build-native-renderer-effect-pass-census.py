"""Build a fail-closed effect-pass census from an enriched RenderDoc trace."""

import argparse
import hashlib
import json
import pathlib
import sys


TRACE_SCHEMA = "pinyon-shift.native-renderer-renderdoc-pass-trace.v1"
SCHEMA = "pinyon-shift.native-renderer-effect-pass-census.v1"
CLASSIFIER_SCHEMA = "pinyon-shift.native-renderer-effect-pass-classifier.v2"
SEMANTIC_ROLES = {"shadow_depth", "reflection_capture", "retained_unknown"}
CONFIDENCE_LEVELS = {"medium", "high"}
CASTER_CLASSES = {"dynamic_vehicle", "static_world", "mixed_world"}
MATCH_FIELDS = {
    "output_class",
    "depth_target_name",
    "pipeline_name",
    "vertex_shader_name",
    "pixel_shader_name",
    "viewport_width",
    "viewport_height",
}


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
        "color_target_names": [
            target.get("resource_name")
            for target in draw.get("color_targets", [])
        ],
        "color_target_shapes": [
            target_shape(target) for target in draw.get("color_targets", [])
        ],
        "depth_target_name": (
            None
            if draw.get("depth_target") is None
            else draw["depth_target"].get("resource_name")
        ),
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


def match_projection(value):
    viewport = value.get("viewport") or {}
    return {
        "output_class": value.get("output_class"),
        "depth_target_name": value.get("depth_target_name"),
        "pipeline_name": value.get("pipeline_name"),
        "vertex_shader_name": value.get("vertex_shader_name"),
        "pixel_shader_name": value.get("pixel_shader_name"),
        "viewport_width": viewport.get("width"),
        "viewport_height": viewport.get("height"),
    }


def normalize_classifier(document, capture_sha256):
    if document.get("schema") != CLASSIFIER_SCHEMA:
        raise ValueError("unsupported effect-pass classifier schema")
    if document.get("evidence_capture_sha256") != capture_sha256:
        raise ValueError("effect-pass classifier capture evidence drifted")
    rules = document.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("effect-pass classifier rules must be a nonempty array")
    normalized = []
    seen = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"effect-pass classifier rule {index} must be an object")
        identifier = str(rule.get("id", "")).strip()
        if not identifier or identifier in seen:
            raise ValueError("effect-pass classifier rule ids must be unique")
        seen.add(identifier)
        match = rule.get("match")
        if not isinstance(match, dict) or set(match) != MATCH_FIELDS:
            raise ValueError(
                f"effect-pass classifier rule {identifier} match fields drifted"
            )
        role = rule.get("semantic_role")
        caster_class = rule.get("caster_class")
        atlas_region = rule.get("atlas_region")
        confidence = rule.get("confidence")
        evidence = str(rule.get("evidence", "")).strip()
        visual_sha256 = str(rule.get("visual_sha256", "")).upper()
        if role not in SEMANTIC_ROLES:
            raise ValueError(
                f"effect-pass classifier rule {identifier} has invalid role"
            )
        if role == "shadow_depth":
            if caster_class not in CASTER_CLASSES:
                raise ValueError(
                    f"effect-pass classifier rule {identifier} has invalid caster class"
                )
            if not isinstance(atlas_region, dict) or set(atlas_region) != {
                "x",
                "y",
                "width",
                "height",
            }:
                raise ValueError(
                    f"effect-pass classifier rule {identifier} has invalid atlas region"
                )
            if any(
                type(atlas_region[field]) is not int
                or atlas_region[field] < 0
                for field in ("x", "y", "width", "height")
            ) or atlas_region["width"] == 0 or atlas_region["height"] == 0:
                raise ValueError(
                    f"effect-pass classifier rule {identifier} has invalid atlas region"
                )
            if (
                atlas_region["width"] != match["viewport_width"]
                or atlas_region["height"] != match["viewport_height"]
            ):
                raise ValueError(
                    f"effect-pass classifier rule {identifier} atlas region and viewport differ"
                )
        elif caster_class is not None or atlas_region is not None:
            raise ValueError(
                "effect-pass classifier rule {} assigns shadow metadata "
                "to a non-shadow role".format(identifier)
            )
        if confidence not in CONFIDENCE_LEVELS:
            raise ValueError(
                f"effect-pass classifier rule {identifier} has invalid confidence"
            )
        if not evidence:
            raise ValueError(
                f"effect-pass classifier rule {identifier} requires evidence"
            )
        if len(visual_sha256) != 64 or any(
            character not in "0123456789ABCDEF"
            for character in visual_sha256
        ):
            raise ValueError(
                f"effect-pass classifier rule {identifier} has invalid visual hash"
            )
        if rule.get("native_coverage") is not False:
            raise ValueError(
                "effect-pass classifier rule {} must keep native coverage "
                "false".format(identifier)
            )
        if rule.get("suppression_eligible") is not False:
            raise ValueError(
                f"effect-pass classifier rule {identifier} must forbid suppression"
            )
        normalized.append(
            {
                "id": identifier,
                "match": match,
                "semantic_role": role,
                "caster_class": caster_class,
                "atlas_region": atlas_region,
                "semantic_confidence": confidence,
                "semantic_evidence": evidence,
                "visual_sha256": visual_sha256,
            }
        )
    return normalized


def apply_classifier(families, rules):
    matched = set()
    for rule in rules:
        candidates = [
            family
            for family in families
            if match_projection(family["signature"]) == rule["match"]
        ]
        if len(candidates) != 1:
            raise ValueError(
                "effect-pass classifier rule {} matched {} families".format(
                    rule["id"], len(candidates)
                )
            )
        family = candidates[0]
        if family["sha256"] in matched:
            raise ValueError("multiple effect-pass rules matched one family")
        matched.add(family["sha256"])
        family.update(
            {
                "classifier_rule": rule["id"],
                "semantic_role": rule["semantic_role"],
                "caster_class": rule["caster_class"],
                "atlas_region": rule["atlas_region"],
                "semantic_confidence": rule["semantic_confidence"],
                "semantic_evidence": rule["semantic_evidence"],
                "visual_sha256": rule["visual_sha256"],
            }
        )
    return matched


def build_census(trace, classifier=None):
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
                "event_ids": [],
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
        family["event_ids"].append(event_id)
        family["last_event"] = event_id

    ordered = sorted(
        families.values(),
        key=lambda item: (-item["draw_count"], item["sha256"]),
    )
    counts = {}
    classifier_rules = []
    matched = set()
    if classifier is not None:
        classifier_rules = normalize_classifier(
            classifier, str(trace.get("capture", {}).get("sha256", ""))
        )
        matched = apply_classifier(ordered, classifier_rules)
    semantic_counts = {}
    semantic_draws = {}
    caster_counts = {}
    caster_draws = {}
    for family in ordered:
        key = family["signature"]["output_class"]
        counts[key] = counts.get(key, 0) + family["draw_count"]
        role = family["semantic_role"]
        semantic_counts[role] = semantic_counts.get(role, 0) + 1
        semantic_draws[role] = semantic_draws.get(role, 0) + family["draw_count"]
        caster_class = family.get("caster_class")
        if caster_class is not None:
            caster_counts[caster_class] = caster_counts.get(caster_class, 0) + 1
            caster_draws[caster_class] = (
                caster_draws.get(caster_class, 0) + family["draw_count"]
            )
    shadow_identified = semantic_counts.get("shadow_depth", 0) > 0
    reflection_identified = semantic_counts.get("reflection_capture", 0) > 0
    return {
        "schema": SCHEMA,
        "capture": trace.get("capture"),
        "totals": {
            "draws": sum(item["draw_count"] for item in ordered),
            "families": len(ordered),
            "isolated_native_draws_ignored": ignored_native_draws,
            "draws_by_output_class": dict(sorted(counts.items())),
            "families_by_semantic_role": dict(sorted(semantic_counts.items())),
            "draws_by_semantic_role": dict(sorted(semantic_draws.items())),
            "families_by_caster_class": dict(sorted(caster_counts.items())),
            "draws_by_caster_class": dict(sorted(caster_draws.items())),
        },
        "families": ordered,
        "classification": {
            "configured": classifier is not None,
            "rules": len(classifier_rules),
            "matched_families": len(matched),
            "unclassified_families": len(ordered) - len(matched),
        },
        "qualification": {
            "pipeline_metadata_census_complete": True,
            "shadow_pass_identified": shadow_identified,
            "reflection_pass_identified": reflection_identified,
            "shadow_caster_classes_identified": sorted(caster_counts),
            "static_dynamic_caster_classes_observed": (
                "dynamic_vehicle" in caster_counts
                and "static_world" in caster_counts
            ),
            "static_dynamic_caster_separation_ready": False,
            "native_shadow_renderer_ready": False,
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
    parser.add_argument("--classifier", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        trace_bytes = args.trace.read_bytes()
        trace = json.loads(trace_bytes)
        classifier = None
        if args.classifier is not None:
            classifier = json.loads(args.classifier.read_text(encoding="utf-8"))
        census = build_census(trace, classifier)
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
