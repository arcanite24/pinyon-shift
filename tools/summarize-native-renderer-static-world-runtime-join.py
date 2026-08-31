#!/usr/bin/env python3
"""Qualify SimpleModel renderer scopes joined to prepared PM4 draws."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys


SCHEMA = "pinyon-shift.native-renderer-static-world-runtime-join.v3"
STATIC_SCHEMA = "pinyon-shift.native-renderer-static-world-ingress.v2"
LIFETIME_SCHEMA = "pinyon-shift.native-renderer-static-world-lifetime.v1"
RESOURCE_SCHEMA = "pinyon-shift.native-renderer-static-world-resource.v1"
CONFIG = "native_renderer.discovery.static_world_runtime_join_config"
SUMMARY = "native_renderer.discovery.static_world_runtime_join_summary"
CHECKPOINT = "native_renderer.discovery.static_world_runtime_join_checkpoint"


def integer(mapping, key):
    try:
        value = int(mapping[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid {key}") from error
    if value < 0:
        raise ValueError(f"negative {key}")
    return value


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
            raise ValueError("requested session has no static-world join config")
        return requested
    if len(sessions) != 1:
        raise ValueError("static-world join input contains multiple sessions")
    return next(iter(sessions))


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
        raise ValueError("no static-world runtime summary or checkpoint")
    return max(
        checkpoints, key=lambda event: integer(event, "frame_sequence")
    ), False


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
        raise ValueError("static-world join violates its safety boundary")


def validate_static_ingress(document):
    if (
        document.get("schema") != STATIC_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "title_simple_model_static_world_ingress_proved"
    ):
        raise ValueError("static-world ingress proof drifted")
    try:
        model_renderer = document["classes"]["simple_model_renderer"]
        primary = next(
            surface
            for surface in model_renderer["surfaces"]
            if surface.get("label") == "primary"
        )
    except (KeyError, StopIteration, TypeError) as error:
        raise ValueError("static-world renderer surface is missing") from error
    slot_targets = primary.get("slot_targets")
    if (
        model_renderer.get("decorated_name") != ".?AVCSimpleModelRenderer@@"
        or primary.get("vtable_address") != "82001B64"
        or primary.get("vtable_slot_count") != 17
        or not isinstance(slot_targets, list)
        or len(slot_targets) != 17
        or slot_targets[12] != "82C4CCC8"
    ):
        raise ValueError("static-world renderer dispatch proof drifted")


def validate_static_lifetime(document):
    if (
        document.get("schema") != LIFETIME_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "exact_simple_model_renderer_lifetime_and_graph_owner"
    ):
        raise ValueError("static-world lifetime proof drifted")
    try:
        renderer = document["renderer"]
        graph = document["graph_ownership"]
        claims = document["claims"]
    except (KeyError, TypeError) as error:
        raise ValueError("static-world lifetime proof is incomplete") from error
    expected_renderer = {
        "class": "CSimpleModelRenderer",
        "vtable": "82001B64",
        "object_bytes": 368,
        "constructor": "82C4DF78",
        "constructor_publish_hook": "82C4E094",
        "deleting_destructor_slot": 16,
        "deleting_destructor": "82C4E420",
        "destructor_entry_hook": "82C4E1F8",
        "destructor_exit_hook": "82C4E264",
    }
    expected_graph = {
        "field_offset": 72,
        "bind_slot": 1,
        "bind_method": "82C4CC50",
        "bind_completion_hook": "82C4CCB0",
        "release_slot": 15,
        "release_method": "82C4C6A8",
        "destructor_cleanup": "82C4E0A0",
        "draw_slot": 12,
        "draw_dispatch": "82C4CCC8",
    }
    if any(
        renderer.get(key) != value
        for key, value in expected_renderer.items()
    ):
        raise ValueError("static-world renderer lifetime proof drifted")
    if any(graph.get(key) != value for key, value in expected_graph.items()):
        raise ValueError("static-world graph ownership proof drifted")
    if (
        claims.get("renderer_generation_boundary_proved") is not True
        or claims.get("renderer_to_owned_graph_field_proved") is not True
        or claims.get("concrete_building_or_prop_identity_proved") is not False
    ):
        raise ValueError("static-world lifetime claims drifted")


def validate_static_resource(document):
    if (
        document.get("schema") != RESOURCE_SCHEMA
        or document.get("status") != "complete"
        or document.get("classification")
        != "exact_simple_model_resource_factory_and_lifetime"
    ):
        raise ValueError("static-world resource proof drifted")
    try:
        resource = document["resource"]
        binding = document["binding"]
        claims = document["claims"]
    except (KeyError, TypeError) as error:
        raise ValueError("static-world resource proof is incomplete") from error
    expected_resource = {
        "class": "CSimpleModelResource",
        "vtable": "82229294",
        "object_bytes": 320,
        "factory": "82C47F10",
        "constructor": "82C47DA0",
        "publish_hook": "82C47FBC",
        "registration_hook": "82C4802C",
        "deleting_destructor_slot": 0,
        "deleting_destructor": "82C47EC0",
        "destructor": "82C47DF8",
        "destructor_entry_hook": "82C47DF8",
        "destructor_exit_hook": "82C47E44",
    }
    expected_binding = {
        "renderer_bind": "82C48038",
        "renderer_graph_field_offset": 72,
        "factory_output_argument": "r5",
        "reference_assignment": "824E81A8",
        "existing_resource_path_join": "82C4802C",
        "new_resource_path_join": "82C4802C",
    }
    if any(resource.get(key) != value for key, value in expected_resource.items()):
        raise ValueError("static-world resource lifetime proof drifted")
    if any(binding.get(key) != value for key, value in expected_binding.items()):
        raise ValueError("static-world resource binding proof drifted")
    if (
        claims.get("bound_graph_dynamic_type_proved") is not True
        or claims.get("resource_generation_boundary_proved") is not True
        or claims.get("factory_registration_boundary_proved") is not True
        or claims.get("concrete_building_or_prop_identity_proved") is not False
        or claims.get("streaming_invalidation_proved") is not False
    ):
        raise ValueError("static-world resource claims drifted")


def build(
    static_ingress,
    static_lifetime,
    static_resource,
    events,
    requested_session=None,
    allow_checkpoint=False,
):
    validate_static_ingress(static_ingress)
    validate_static_lifetime(static_lifetime)
    validate_static_resource(static_resource)
    session = select_session(events, requested_session)
    selected = [event for event in events if event.get("session") == session]
    config = exact_event(selected, CONFIG)
    summary, final_summary = select_runtime_evidence(
        selected, allow_checkpoint
    )
    expected_config = {
        "status": "armed",
        "class": "CSimpleModelRenderer",
        "vtable": "82001B64",
        "object_bytes": "368",
        "constructor": "82C4DF78",
        "constructor_publish_hook": "82C4E094",
        "deleting_destructor_slot": "16",
        "deleting_destructor": "82C4E420",
        "destructor_entry_hook": "82C4E1F8",
        "destructor_exit_hook": "82C4E264",
        "vtable_slot": "12",
        "dispatch": "82C4CCC8",
        "entry_hook": "82C4CCC8",
        "exit_hook": "82C4DEA0",
        "model_graph_field": "renderer_plus_72",
        "model_graph_bind_slot": "1",
        "model_graph_bind_hook": "82C4CCB0",
        "model_graph_release_slot": "15",
        "model_graph_release_hook": "82C4C6A8,82C4E0A0",
        "model_resource_class": "CSimpleModelResource",
        "model_resource_vtable": "82229294",
        "model_resource_bytes": "320",
        "model_resource_factory": "82C47F10",
        "model_resource_publish_hook": "82C47FBC",
        "model_resource_registration_hook": "82C4802C",
        "model_resource_destructor_entry_hook": "82C47DF8",
        "model_resource_destructor_exit_hook": "82C47E44",
        "draw_emitter": "82416380",
        "packet_hooks": "82416260,824162F4",
        "join": "synchronous_scope_to_physical_pm4_prepared_draw",
        "guest_payload_read": "two_host_mapped_u32_fields_per_scope",
    }
    if any(config.get(key) != value for key, value in expected_config.items()):
        raise ValueError("static-world runtime configuration drifted")
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
        or summary.get("checkpoint_kind")
        != ("final" if final_summary else "periodic")
        or summary.get("classification")
        != "live_simple_model_resource_to_pm4_prepared_draw"
    ):
        raise ValueError("static-world runtime summary drifted")

    keys = (
        "scope_entries",
        "scope_exits",
        "exact_scopes",
        "invalid_root",
        "vtable_mismatches",
        "invalid_graph_field",
        "unregistered_renderers",
        "nonlive_renderers",
        "unbound_graphs",
        "graph_mismatches",
        "scopes_with_packets",
        "scopes_without_packets",
        "packets_recorded",
        "packet_matches",
        "pending_packets",
        "prepared_matches",
        "unprepared_matches",
        "scope_overlaps",
        "exit_without_entry",
        "instances_published",
        "instances_destroyed",
        "instance_address_reuses",
        "lifecycle_table_overflow",
        "lifecycle_faults",
        "destructor_entries",
        "destructor_exits",
        "destructors_open",
        "destructors_without_instance",
        "graph_bind_observations",
        "graph_bind_successes",
        "graph_bind_null",
        "graph_bind_unregistered",
        "graph_bind_faults",
        "graph_replacements",
        "graph_release_observations",
        "graph_release_successes",
        "graph_release_empty",
        "graph_release_unregistered",
        "graph_release_faults",
        "resource_instances_published",
        "resource_instances_destroyed",
        "resource_address_reuses",
        "resource_table_overflow",
        "resource_lifecycle_faults",
        "resource_destructor_entries",
        "resource_destructor_exits",
        "resource_destructors_open",
        "resource_destructors_without_instance",
        "resource_registration_observations",
        "resource_registration_successes",
        "resource_registration_null",
        "resource_registration_unregistered",
        "resource_registration_type_mismatches",
        "resource_registration_faults",
        "resource_graph_bind_joins",
        "resource_scope_joins",
        "resource_scope_mismatches",
    )
    totals = {key: integer(summary, key) for key in keys}
    frame_sequence = integer(summary, "frame_sequence")
    failures = []
    classified = (
        totals["exact_scopes"]
        + totals["invalid_root"]
        + totals["vtable_mismatches"]
        + totals["invalid_graph_field"]
        + totals["unregistered_renderers"]
        + totals["nonlive_renderers"]
        + totals["unbound_graphs"]
        + totals["graph_mismatches"]
    )
    if summary.get("accounting_complete") != "true":
        failures.append("runtime accounting is incomplete")
    if totals["scope_entries"] != totals["scope_exits"]:
        failures.append("static-world scope entry/exit accounting drifted")
    if totals["scope_entries"] != classified:
        failures.append("static-world scope classification drifted")
    if totals["exact_scopes"] != (
        totals["scopes_with_packets"] + totals["scopes_without_packets"]
    ):
        failures.append("static-world scope outcome accounting drifted")
    if not totals["exact_scopes"]:
        failures.append("no exact SimpleModel renderer scope was observed")
    if not totals["instances_published"]:
        failures.append(
            "no completed SimpleModel renderer lifetime was observed"
        )
    if not totals["graph_bind_successes"]:
        failures.append("no owned SimpleModel renderer graph was observed")
    if not totals["resource_instances_published"]:
        failures.append("no completed SimpleModel resource lifetime was observed")
    if not totals["resource_registration_successes"]:
        failures.append("no registered SimpleModel resource was observed")
    if not totals["resource_graph_bind_joins"]:
        failures.append("no renderer bind joined a registered resource")
    if not totals["resource_scope_joins"]:
        failures.append("no exact scope joined a live resource generation")
    if not totals["scopes_with_packets"] or not totals["packets_recorded"]:
        failures.append("no exact scope emitted a PM4 draw packet")
    if totals["packet_matches"] + totals["pending_packets"] != totals[
        "packets_recorded"
    ]:
        failures.append("static-world packet outcome accounting drifted")
    if totals["packet_matches"] != (
        totals["prepared_matches"] + totals["unprepared_matches"]
    ):
        failures.append("static-world prepared accounting drifted")
    if totals["destructor_entries"] != (
        totals["destructor_exits"] + totals["destructors_open"]
    ):
        failures.append("static-world destructor accounting drifted")
    if totals["instances_destroyed"] > totals["instances_published"]:
        failures.append("static-world instance lifetime accounting drifted")
    if (
        totals["graph_bind_successes"]
        + totals["graph_bind_null"]
        + totals["graph_bind_unregistered"]
        + totals["graph_bind_faults"]
        != totals["graph_bind_observations"]
    ):
        failures.append("static-world graph bind accounting drifted")
    if (
        totals["graph_release_successes"]
        + totals["graph_release_empty"]
        + totals["graph_release_unregistered"]
        + totals["graph_release_faults"]
        != totals["graph_release_observations"]
    ):
        failures.append("static-world graph release accounting drifted")
    if totals["resource_destructor_entries"] != (
        totals["resource_destructor_exits"]
        + totals["resource_destructors_open"]
    ):
        failures.append("static-world resource destructor accounting drifted")
    if totals["resource_instances_destroyed"] > totals[
        "resource_instances_published"
    ]:
        failures.append("static-world resource lifetime accounting drifted")
    if (
        totals["resource_registration_successes"]
        + totals["resource_registration_null"]
        + totals["resource_registration_unregistered"]
        + totals["resource_registration_type_mismatches"]
        + totals["resource_registration_faults"]
        != totals["resource_registration_observations"]
    ):
        failures.append("static-world resource registration accounting drifted")
    if totals["resource_graph_bind_joins"] != totals["graph_bind_successes"]:
        failures.append("static-world resource graph-bind accounting drifted")
    if totals["resource_scope_joins"] != totals["exact_scopes"]:
        failures.append("static-world resource scope accounting drifted")
    if not totals["prepared_matches"]:
        failures.append("no static-world PM4 packet joined a prepared draw")
    for key in (
        "invalid_root",
        "vtable_mismatches",
        "invalid_graph_field",
        "unregistered_renderers",
        "nonlive_renderers",
        "graph_mismatches",
        "unprepared_matches",
        "scope_overlaps",
        "exit_without_entry",
        "lifecycle_table_overflow",
        "lifecycle_faults",
        "destructors_without_instance",
        "destructors_open",
        "graph_bind_unregistered",
        "graph_bind_faults",
        "graph_release_unregistered",
        "graph_release_faults",
        "resource_table_overflow",
        "resource_lifecycle_faults",
        "resource_destructors_without_instance",
        "resource_destructors_open",
        "resource_registration_unregistered",
        "resource_registration_type_mismatches",
        "resource_registration_faults",
        "resource_scope_mismatches",
    ):
        if totals[key]:
            failures.append(f"{key} is nonzero")
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
            "native_admission_evidence": False,
        },
        "failures": failures,
        "totals": totals,
        "qualification": {
            "simple_model_renderer_scope_proved": not failures,
            "simple_model_renderer_lifetime_proved": not failures,
            "renderer_to_owned_graph_field_proved": not failures,
            "simple_model_resource_type_proved": not failures,
            "simple_model_resource_lifetime_proved": not failures,
            "renderer_to_registered_resource_proved": not failures,
            "static_world_scope_to_pm4_proved": not failures,
            "static_world_pm4_to_prepared_draw_proved": not failures,
            "building_or_prop_instance_identity_proved": False,
            "streaming_lifetime_proved": False,
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
    parser.add_argument("--static", required=True, type=pathlib.Path)
    parser.add_argument("--lifetime", required=True, type=pathlib.Path)
    parser.add_argument("--resource", required=True, type=pathlib.Path)
    parser.add_argument("--session")
    parser.add_argument("--allow-checkpoint", action="store_true")
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        document = build(
            json.loads(args.static.read_text(encoding="utf-8")),
            json.loads(args.lifetime.read_text(encoding="utf-8")),
            json.loads(args.resource.read_text(encoding="utf-8")),
            read_events(args.events),
            args.session,
            args.allow_checkpoint,
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
        print(f"static-world runtime join failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
