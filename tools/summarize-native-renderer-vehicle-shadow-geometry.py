"""Summarize capture-proven vehicle shadow geometry/color correlations."""

import argparse
import json
from pathlib import Path


SCHEMA = "pinyon-shift.native-renderer-vehicle-shadow-geometry.v1"
CONFIG_EVENT = "native_renderer.discovery.vehicle_shadow_geometry_config"
EPOCH_EVENT = "native_renderer.discovery.vehicle_shadow_geometry_epoch"
CORRELATION_EVENT = (
    "native_renderer.discovery.vehicle_shadow_geometry_correlation"
)
SUMMARY_EVENT = "native_renderer.discovery.vehicle_shadow_geometry_summary"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(record, key):
    try:
        return int(record[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"missing or invalid integer field: {key}") from error


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
    configs = [event for event in events if event.get("event") == CONFIG_EVENT]
    epochs = [event for event in events if event.get("event") == EPOCH_EVENT]
    correlations = [
        event for event in events if event.get("event") == CORRELATION_EVENT
    ]
    summaries = [
        event for event in events if event.get("event") == SUMMARY_EVENT
    ]
    require(len(configs) == 1, "expected exactly one correlation config event")
    require(configs[0].get("status") == "armed", "correlation was not armed")
    require(len(summaries) == 1, "expected exactly one correlation summary")
    summary = summaries[0]
    require(summary.get("status") == "qualified_epoch_observed", "no qualified epoch")
    require(integer(summary, "epochs_committed") == len(epochs), "epoch accounting drift")
    require(integer(summary, "epochs_committed") > 0, "no epoch was committed")
    require(summary.get("seed_accounting_complete") == "true", "seed accounting drift")
    require(integer(summary, "seed_overflow") == 0, "geometry seed table overflowed")
    require(
        integer(summary, "correlation_overflow") == 0,
        "geometry correlation table overflowed",
    )
    require(
        integer(summary, "correlations") == len(correlations),
        "correlation event accounting drift",
    )
    require(
        integer(summary, "color_draws_matched")
        == integer(summary, "full_geometry_matches")
        + integer(summary, "index_vertex_matches"),
        "match accounting drift",
    )
    safety_events = [*configs, *epochs, *correlations, summary]
    for event in safety_events:
        require(event.get("native_draw") == "false", "native draw was enabled")
        require(event.get("xenos_authority") == "true", "Xenos authority changed")
        require(
            event.get("suppression_allowed") == "false",
            "suppression was allowed",
        )
    for event in epochs:
        require(integer(event, "draw_count") == 80, "epoch draw count drift")
        require(
            event.get("promotion_boundary")
            == "backend_recorded_full_80_draw_epoch",
            "partial epoch was promoted",
        )
    for event in correlations:
        require(
            event.get("classification")
            == "vehicle_color_geometry_correlation_candidate",
            "correlation classification drift",
        )
        require(
            event.get("match")
            in {
                "exact_geometry_resource_set",
                "exact_index_and_shared_vertex_resource",
            },
            "unbounded correlation match",
        )
    return {
        "schema": SCHEMA,
        "source_log": str(log_path),
        "totals": {
            "epochs_committed": integer(summary, "epochs_committed"),
            "unique_geometry_seeds": integer(summary, "unique_geometry_seeds"),
            "color_draws_examined": integer(summary, "color_draws_examined"),
            "color_draws_matched": integer(summary, "color_draws_matched"),
            "full_geometry_matches": integer(summary, "full_geometry_matches"),
            "index_vertex_matches": integer(summary, "index_vertex_matches"),
            "correlations": len(correlations),
        },
        "epochs": epochs,
        "correlations": correlations,
        "qualification": {
            "working_color_bridge_candidate": bool(correlations),
            "object_identity_proven": False,
            "mesh_material_contract_proven": False,
            "native_admission_allowed": False,
        },
        "safety": {
            "guest_payload_capture": False,
            "native_draw": False,
            "xenos_authority": True,
            "suppression_allowed": False,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = summarize(arguments.log)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["totals"], sort_keys=True))


if __name__ == "__main__":
    main()
