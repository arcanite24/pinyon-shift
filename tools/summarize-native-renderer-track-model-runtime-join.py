#!/usr/bin/env python3
"""Qualify exact track scopes joined to prepared draws by command lineage."""

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-track-model-runtime-join.v6"
CONFIG = "native_renderer.discovery.track_render_model_runtime_join_config"
SUMMARY = "native_renderer.discovery.track_render_model_runtime_join_summary"
CHECKPOINT = (
    "native_renderer.discovery.track_render_model_runtime_join_checkpoint"
)

RELATIONS = (
    "shared_descriptor",
    "shared_descriptor_payload_bound_resource",
    "shared_descriptor_payload_provider",
    "shared_descriptor_payload_runtime_object",
    "shared_root_receiver",
    "shared_child_receiver",
    "shared_root_runtime_object",
    "shared_child_runtime_object",
    "shared_command_lineage",
)

WORLD_RELATIONS = (
    "world_track_model",
    "world_track_mesh",
    "world_track_submodel",
    "world_procedural_geometry_object",
    "world_procedural_geometry_resource",
    "world_pvs_zone_object",
    "world_pvs_zone_resource",
)

SHARED_WORLD_RELATIONS = tuple(
    f"shared_{relation}" for relation in WORLD_RELATIONS
)
NESTED_WORLD_RELATIONS = tuple(
    f"nested_{relation}" for relation in WORLD_RELATIONS
)
POINTEE_RELATIONS = (
    "track_model",
    "track_mesh",
    "track_submodel",
    "procedural_object",
    "procedural_resource",
    "pvs_object",
    "pvs_resource",
    "simple_renderer",
    "simple_resource",
    "simple_model",
    "simple_submodel",
    "simple_mesh",
    "deferred_renderer",
    "model_presentation",
)


def integer(mapping, key):
    try:
        value = int(mapping[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if value < 0:
        raise ValueError(f"negative {key}")
    return value


def relation_counts(mapping, key):
    raw = mapping.get(key)
    if not isinstance(raw, str):
        raise ValueError(f"invalid {key}")
    result = {}
    for part in raw.split(";"):
        name, separator, value = part.partition("=")
        if not separator or name in result:
            raise ValueError(f"invalid {key}")
        result[name] = integer({name: value}, name)
    if tuple(result) != POINTEE_RELATIONS:
        raise ValueError(f"invalid {key}")
    return result


def exact_event(events, name):
    matches = [event for event in events if event.get("event") == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {name} event")
    return matches[0]


def read_events(paths):
    events = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    return events


def select_session(events, requested):
    sessions = {
        event.get("session") for event in events if event.get("event") == CONFIG
    }
    sessions.discard(None)
    if requested:
        if requested not in sessions:
            raise ValueError("requested session has no track-model join config")
        return requested
    if len(sessions) != 1:
        raise ValueError("track-model join input contains multiple sessions")
    return next(iter(sessions))


def require_safety(event):
    expected = {
        "guest_state_changed": "false",
        "control_flow_changed": "false",
        "native_admission": "false",
        "native_draw": "false",
        "xenos_authority": "true",
        "suppression_allowed": "false",
    }
    if any(event.get(key) != value for key, value in expected.items()):
        raise ValueError("track-model join violates its safety boundary")


def select_runtime_evidence(events, allow_checkpoint):
    summaries = [event for event in events if event.get("event") == SUMMARY]
    if len(summaries) > 1:
        raise ValueError(f"expected at most one {SUMMARY} event")
    if summaries:
        return summaries[0], True
    if not allow_checkpoint:
        raise ValueError(f"expected exactly one {SUMMARY} event")
    checkpoints = [
        event for event in events if event.get("event") == CHECKPOINT
    ]
    if not checkpoints:
        raise ValueError("no track-model runtime summary or checkpoint")
    try:
        checkpoint = max(
            checkpoints, key=lambda event: integer(event, "frame_sequence")
        )
    except ValueError as error:
        raise ValueError("invalid track-model runtime checkpoint") from error
    return checkpoint, False


def build(events, requested_session=None, allow_checkpoint=False):
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary, final_summary = select_runtime_evidence(
        selected, allow_checkpoint
    )
    expected_config = {
        "status": "armed",
        "entry_hook": "8240EC80",
        "exit_hook": "8240ECAC",
        "nested_dispatch": "82436468",
        "command_context_entry": "824365B4",
        "instance_vtable": "820019CC",
        "model_vtable": "82001D74",
        "instance_to_model": "root_plus_4",
        "model_to_descriptor": "child_plus_48_then_plus_128",
        "descriptor_type": "21",
        "descriptor_flag": "1",
        "join": "exact_track_scope_to_indirect_command_packet_to_prepared_draw",
        "shared_identity": "descriptor_payload_or_object_address_exact_equality",
        "world_resource_vtables": (
            "820016B4,8200143C,82001474,82144CF8,82144D7C,82144DE0,"
            "82144E64"
        ),
        "world_resource_graph": (
            "host_mapped_direct_or_one_level_nested_child_or_descriptor_pointer_"
            "with_exact_track_rtti_vtable"
        ),
        "world_resource_shared_identity": (
            "exact_address_equality_to_submission_objects_or_resources"
        ),
        "world_resource_graph_cache_capacity": "1024",
        "world_resource_reference_capacity": "64",
        "world_pointee_root_capacity": "16",
        "guest_payload_read": (
            "bounded_320_bytes_plus_direct_and_16_word_nested_vtable_census_per_"
            "cache_miss"
        ),
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("track-model runtime configuration drifted")
    require_safety(config)
    require_safety(summary)
    expected_kinds = (
        ("complete", "incomplete", "not_observed")
        if final_summary
        else (
            "checkpoint_complete",
            "checkpoint_incomplete",
            "checkpoint_not_observed",
        )
    )
    if (
        summary.get("status") not in expected_kinds
        or (
            final_summary
            and summary.get("checkpoint_kind") not in (None, "final")
        )
        or (
            not final_summary
            and summary.get("checkpoint_kind") != "periodic"
        )
        or summary.get("classification")
        != "exact_track_scope_to_indirect_command_packet_to_prepared_draw"
    ):
        raise ValueError("track-model runtime summary drifted")
    frame_sequence = (
        integer(summary, "frame_sequence")
        if "frame_sequence" in summary
        else None
    )
    if not final_summary and not frame_sequence:
        raise ValueError("periodic checkpoint has no frame sequence")

    keys = (
        "scope_entries",
        "scope_exits",
        "exact_scopes",
        "invalid_root",
        "invalid_child",
        "invalid_descriptor",
        "contract_mismatches",
        "joined_scopes",
        "unjoined_scopes",
        "submission_joins",
        "command_context_observations",
        "command_context_bridges",
        "command_packet_joins",
        "command_prepared_draw_joins",
        "shared_identity_joins",
        "scope_overlaps",
        "exit_without_entry",
        "world_resource_graph_scopes",
        "world_resource_nested_graph_scopes",
        "world_resource_graph_cache_hits",
        "world_resource_graph_cache_misses",
        "world_resource_graph_reference_overflow",
        "world_resource_graph_reference_high_watermark",
        "world_resource_graph_host_unmapped_rejections",
        "world_resource_shared_identity_joins",
        *RELATIONS,
        *WORLD_RELATIONS,
        *NESTED_WORLD_RELATIONS,
        *SHARED_WORLD_RELATIONS,
    )
    totals = {key: integer(summary, key) for key in keys}
    prepared_partition_keys = (
        "command_prepared_draw_joins_with_semantic_origin",
        "command_prepared_draw_joins_without_semantic_origin",
    )
    prepared_partition_present = all(
        key in summary for key in prepared_partition_keys
    )
    for key in prepared_partition_keys:
        totals[key] = integer(summary, key) if key in summary else 0
    pointee_keys = (
        "world_pointee_graph_samples",
        "world_pointee_direct_hits",
        "world_pointee_nested_hits",
        "world_pointee_host_unmapped_rejections",
        "world_pointee_direct_relations",
        "world_pointee_nested_relations",
    )
    pointee_present = all(key in summary for key in pointee_keys)
    pointee_direct_relations = {}
    pointee_nested_relations = {}
    if pointee_present:
        for key in pointee_keys[:4]:
            totals[key] = integer(summary, key)
        pointee_direct_relations = relation_counts(
            summary, "world_pointee_direct_relations"
        )
        pointee_nested_relations = relation_counts(
            summary, "world_pointee_nested_relations"
        )
    failures = []
    if any(key in summary for key in prepared_partition_keys) and not (
        prepared_partition_present
    ):
        failures.append("prepared command semantic-origin partition is incomplete")
    if any(key in summary for key in pointee_keys) and not pointee_present:
        failures.append("world-pointee census is incomplete")
    if pointee_present:
        if totals["world_pointee_graph_samples"] != (
            2 * totals["world_resource_graph_cache_misses"]
        ):
            failures.append("world-pointee sample accounting drifted")
        if totals["world_pointee_direct_hits"] != sum(
            pointee_direct_relations.values()
        ):
            failures.append("direct world-pointee relation accounting drifted")
        if totals["world_pointee_nested_hits"] != sum(
            pointee_nested_relations.values()
        ):
            failures.append("nested world-pointee relation accounting drifted")
    classified = (
        totals["exact_scopes"]
        + totals["invalid_root"]
        + totals["invalid_child"]
        + totals["invalid_descriptor"]
        + totals["contract_mismatches"]
    )
    if summary.get("accounting_complete") != "true":
        failures.append("runtime accounting is incomplete")
    if totals["scope_entries"] != totals["scope_exits"]:
        failures.append("track-model scope entry/exit accounting drifted")
    if totals["scope_entries"] != classified:
        failures.append("track-model scope classification drifted")
    if totals["exact_scopes"] != (
        totals["joined_scopes"] + totals["unjoined_scopes"]
    ):
        failures.append("exact scope outcome accounting drifted")
    if not totals["exact_scopes"]:
        failures.append("no exact unified track render-model scope was observed")
    if not totals["joined_scopes"]:
        failures.append("no exact scope joined an indirect command context")
    if not totals["command_context_bridges"]:
        failures.append("no exact track command context bridge was observed")
    if not totals["command_packet_joins"]:
        failures.append("no exact track command packet was observed")
    if not totals["command_prepared_draw_joins"]:
        failures.append("no exact track command reached a prepared draw")
    if prepared_partition_present and totals["command_prepared_draw_joins"] != (
        totals["command_prepared_draw_joins_with_semantic_origin"]
        + totals["command_prepared_draw_joins_without_semantic_origin"]
    ):
        failures.append("prepared command semantic-origin accounting drifted")
    if totals["shared_command_lineage"] != totals["command_prepared_draw_joins"]:
        failures.append("prepared command-lineage relation accounting drifted")
    for key in (
        "invalid_child",
        "invalid_descriptor",
        "contract_mismatches",
        "scope_overlaps",
        "exit_without_entry",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
    if totals["shared_identity_joins"] > totals["submission_joins"]:
        failures.append("shared identity joins exceed submission joins")
    if totals["shared_identity_joins"] and not any(
        totals[key] for key in RELATIONS
    ):
        failures.append("shared identity relation accounting is empty")
    if (
        totals["world_resource_graph_cache_hits"]
        + totals["world_resource_graph_cache_misses"]
        != totals["exact_scopes"]
    ):
        failures.append("world-resource graph cache accounting drifted")
    if totals["world_resource_graph_scopes"] > totals["exact_scopes"]:
        failures.append("world-resource graph scopes exceed exact scopes")
    if (
        totals["world_resource_nested_graph_scopes"]
        > totals["world_resource_graph_scopes"]
    ):
        failures.append("nested world-resource scopes exceed graph scopes")
    if totals["world_resource_graph_reference_overflow"]:
        failures.append("world-resource graph reference overflow is nonzero")
    if totals["world_resource_graph_reference_high_watermark"] > 64:
        failures.append("world-resource graph reference capacity drifted")
    if (
        totals["world_resource_graph_scopes"]
        and not totals["world_resource_graph_reference_high_watermark"]
    ):
        failures.append("world-resource graph reference watermark is empty")
    if totals["world_resource_graph_scopes"] and not any(
        totals[key] for key in WORLD_RELATIONS
    ):
        failures.append("world-resource graph relation accounting is empty")
    if any(
        totals[key] > totals["world_resource_graph_scopes"]
        for key in WORLD_RELATIONS
    ):
        failures.append("world-resource graph relation exceeds graph scopes")
    if totals["world_resource_nested_graph_scopes"] and not any(
        totals[key] for key in NESTED_WORLD_RELATIONS
    ):
        failures.append("nested world-resource relation accounting is empty")
    if any(
        totals[key] > totals["world_resource_nested_graph_scopes"]
        for key in NESTED_WORLD_RELATIONS
    ):
        failures.append("nested world-resource relation exceeds nested scopes")
    if (
        totals["world_resource_shared_identity_joins"]
        > totals["submission_joins"]
    ):
        failures.append("world-resource shared joins exceed submission joins")
    if totals["world_resource_shared_identity_joins"] and not any(
        totals[key] for key in SHARED_WORLD_RELATIONS
    ):
        failures.append("shared world-resource relation accounting is empty")
    if any(
        totals[key] > totals["world_resource_shared_identity_joins"]
        for key in SHARED_WORLD_RELATIONS
    ):
        failures.append("shared world-resource relation exceeds shared joins")
    expected_status = (
        "complete" if not failures else "incomplete"
    ) if final_summary else (
        "checkpoint_complete" if not failures else "checkpoint_incomplete"
    )
    if summary.get("status") != expected_status:
        failures.append("runtime status does not match qualification outcome")
    if summary.get("qualification_complete") != (
        "true" if not failures else "false"
    ):
        failures.append("runtime qualification flag does not match outcome")

    return {
        "schema": SCHEMA,
        "session": session,
        "status": expected_status,
        "evidence": {
            "kind": "final_summary" if final_summary else "periodic_checkpoint",
            "frame_sequence": frame_sequence,
            "session_exit_proved": final_summary,
            "admission_evidence": final_summary and not failures,
        },
        "failures": failures,
        "totals": totals,
        "shared_identity_relations": {
            key: totals[key] for key in RELATIONS
        },
        "world_resource_relations": {
            key: totals[key] for key in WORLD_RELATIONS
        },
        "nested_world_resource_relations": {
            key: totals[key] for key in NESTED_WORLD_RELATIONS
        },
        "shared_world_resource_relations": {
            key: totals[key] for key in SHARED_WORLD_RELATIONS
        },
        "world_pointee_census": {
            "available": pointee_present,
            "direct_relations": pointee_direct_relations,
            "nested_relations": pointee_nested_relations,
        },
        "qualification": {
            "track_render_model_scope_to_submission_proved": False,
            "track_command_lineage_to_prepared_draw_proved": not failures,
            "shared_object_or_resource_identity_proved": (
                not failures and totals["shared_identity_joins"] > 0
            ),
            "track_world_resource_graph_identity_proved": (
                not failures and totals["world_resource_graph_scopes"] > 0
            ),
            "nested_track_world_resource_graph_identity_proved": (
                not failures
                and totals["world_resource_nested_graph_scopes"] > 0
            ),
            "track_world_resource_to_submission_identity_proved": (
                not failures
                and totals["world_resource_shared_identity_joins"] > 0
            ),
            "terrain_or_road_visual_identity_proved": False,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "guest_state_changed": False,
            "control_flow_changed": False,
            "native_admission": False,
            "native_draw": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", nargs="+", type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument(
        "--allow-checkpoint",
        action="store_true",
        help=(
            "use the latest periodic checkpoint only when the final shutdown "
            "summary is absent"
        ),
    )
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(
            read_events(args.events), args.session, args.allow_checkpoint
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if document["status"] not in ("complete", "checkpoint_complete"):
            raise ValueError("; ".join(document["failures"]))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"native renderer track-model join failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
