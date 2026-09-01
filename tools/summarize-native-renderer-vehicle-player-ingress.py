"""Summarize the exact player/traffic map-entity to pose census."""

import argparse
import json
from pathlib import Path


SCHEMA = "pinyon-shift.native-renderer-vehicle-player-ingress-runtime.v1"
SUMMARY_EVENT = "native_renderer.discovery.vehicle_map_entity_summary"
ENTITY_EVENT = "native_renderer.discovery.vehicle_map_entity"
CORRELATION_EVENT = (
    "native_renderer.discovery.vehicle_map_pose_correlation"
)
POSE_SUMMARY_EVENT = "native_renderer.discovery.vehicle_pose_summary"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(record, key):
    try:
        return int(record[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing or invalid integer field: {key}") from error


def optional_integer(record, key, default=0):
    if key not in record:
        return default
    return integer(record, key)


def load_events(path):
    events = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSONL at line {line_number}: {error}"
                ) from error
    return events


def summarize(log_path):
    events = load_events(log_path)
    summaries = [event for event in events if event.get("event") == SUMMARY_EVENT]
    pose_summaries = [
        event for event in events if event.get("event") == POSE_SUMMARY_EVENT
    ]
    entities = [event for event in events if event.get("event") == ENTITY_EVENT]
    correlations = [
        event for event in events if event.get("event") == CORRELATION_EVENT
    ]
    require(len(summaries) == 1, "expected one map-entity summary")
    require(len(pose_summaries) == 1, "expected one vehicle-pose summary")
    summary = summaries[0]
    pose_summary = pose_summaries[0]
    require(summary.get("status") == "complete", "map-entity census incomplete")
    require(summary.get("accounting_complete") == "true", "map-entity accounting drift")
    require(integer(summary, "observations") > 0, "map entities were not observed")
    require(integer(summary, "valid_observations") > 0, "no known vehicle entity observed")
    require(integer(summary, "overflow") == 0, "map-entity table overflowed")
    require(
        integer(summary, "pose_correlation_overflow") == 0,
        "map-to-pose correlation table overflowed",
    )
    require(
        integer(summary, "entities") == len(entities),
        "map-entity detail accounting drift",
    )
    require(
        integer(summary, "pose_correlations") == len(correlations),
        "map-to-pose detail accounting drift",
    )
    if optional_integer(summary, "assignment_observations"):
        require(
            summary.get("assignment_accounting_complete") == "true",
            "map-entity assignment accounting drift",
        )
    if optional_integer(summary, "pool_observations"):
        require(
            summary.get("pool_accounting_complete") == "true",
            "map-entity pool accounting drift",
        )
    require(pose_summary.get("status") == "complete", "vehicle-pose census incomplete")

    for event in [summary, *entities, *correlations]:
        require(event.get("xenos_authority") == "true", "Xenos authority changed")
        require(event.get("suppression_allowed") == "false", "suppression was allowed")
        require(event.get("native_draw") == "false", "native drawing was enabled")

    player_entities = [event for event in entities if event.get("class") == "player_local"]
    require(len(player_entities) == 1, "expected exactly one local-player entity")
    player = player_entities[0]
    require(player.get("vtable") == "8201D380", "player vtable drifted")
    require(
        player.get("type_name_address") == "8201D3B4"
        and player.get("expected_type_name_address") == "8201D3B4",
        "player type-name identity drifted",
    )
    require(integer(player, "observations") > 0, "player entity was not exercised")
    require(integer(player, "vtable_mismatches") == 0, "player vtable changed")
    require(integer(player, "type_name_mismatches") == 0, "player type-name changed")

    player_correlations = [
        event
        for event in correlations
        if event.get("entity") == player.get("entity")
        and event.get("entity_class") == "player_local"
    ]
    direct_relations = {}
    for relation in (
        "entity_is_pose_source",
        "entity_is_pose_owner",
        "pool_manager_is_pose_source",
        "pool_manager_is_pose_owner",
        "pool_root_is_pose_source",
        "pool_root_is_pose_owner",
        "pool_context_is_pose_source",
        "pool_context_is_pose_owner",
    ):
        rows = [event for event in player_correlations if event.get("relation") == relation]
        identities = {
            (
                row.get("identity_generation"),
                row.get("identity_source"),
                row.get("identity_owner"),
                row.get("identity_slot"),
            )
            for row in rows
        }
        if rows and len(identities) == 1:
            direct_relations[relation] = rows[0]

    direct_identities = {
        (
            row.get("identity_generation"),
            row.get("identity_source"),
            row.get("identity_owner"),
            row.get("identity_slot"),
        )
        for row in direct_relations.values()
    }
    relation_proved = len(direct_identities) == 1
    relation_priority = (
        "entity_is_pose_owner",
        "entity_is_pose_source",
        "pool_manager_is_pose_owner",
        "pool_manager_is_pose_source",
        "pool_root_is_pose_owner",
        "pool_root_is_pose_source",
        "pool_context_is_pose_owner",
        "pool_context_is_pose_source",
    )
    selected_relation = next(
        (
            relation
            for relation in relation_priority
            if relation_proved and relation in direct_relations
        ),
        "none",
    )
    selected = direct_relations.get(selected_relation)
    slot_candidates = [
        event
        for event in player_correlations
        if event.get("relation") == "vehicle_id_is_pose_slot"
    ]
    failures = []
    if not relation_proved:
        failures.append("no_unique_direct_player_pose_relation")
    return {
        "schema": SCHEMA,
        "status": "qualified" if not failures else "bounded_negative_result",
        "source_log": str(log_path),
        "summary": {
            "map_entity_observations": integer(summary, "observations"),
            "known_vehicle_entity_observations": integer(summary, "valid_observations"),
            "unrecognized_receiver_observations": integer(
                summary, "unrecognized_observations"
            ),
            "entity_count": len(entities),
            "player_entity": player.get("entity"),
            "player_vehicle_id": player.get("vehicle_id"),
            "player_vehicle_id_unassigned": player.get("vehicle_id")
            == "FFFFFFFF",
            "map_entity_assignment_observations": optional_integer(
                summary, "assignment_observations"
            ),
            "map_entity_pool_observations": optional_integer(
                summary, "pool_observations"
            ),
            "player_assignment_observations": optional_integer(
                player, "assignment_observations"
            ),
            "player_pool_observations": optional_integer(
                player, "pool_observations"
            ),
            "player_pose_comparisons": integer(player, "pose_comparisons"),
            "direct_player_pose_relation": selected_relation,
            "direct_player_pose_relations": sorted(direct_relations),
            "slot_relation_candidate_count": len(slot_candidates),
        },
        "qualification": {
            "exact_player_discriminator_proved": True,
            "player_pose_relation_proved": relation_proved,
            "selected_identity": (
                {
                    "generation": selected.get("identity_generation"),
                    "source": selected.get("identity_source"),
                    "owner": selected.get("identity_owner"),
                    "slot": integer(selected, "identity_slot"),
                }
                if selected
                else None
            ),
            "mesh_material_role_identity_proved": False,
            "native_admission_allowed": False,
            "suppression_allowed": False,
        },
        "failures": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        document = summarize(args.log)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError) as error:
        print(f"vehicle player ingress summary failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
