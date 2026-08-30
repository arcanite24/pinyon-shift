"""Build a deterministic report for exact mixed-tile caster provenance."""

import argparse
import json
from pathlib import Path


SCHEMA = "pinyon-shift.native-renderer-shadow-caster-provenance.v1"
CONTROL_EVENT = "native_renderer.shadow_caster_provenance.control"
DRAW_EVENT = "native_renderer.shadow_caster_provenance.draw"
SUMMARY_EVENT = "native_renderer.shadow_caster_provenance.summary"


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
    controls = [event for event in events if event.get("event") == CONTROL_EVENT]
    summaries = [event for event in events if event.get("event") == SUMMARY_EVENT]
    draws = [event for event in events if event.get("event") == DRAW_EVENT]
    require(len(controls) == 1, "expected exactly one provenance control event")
    require(len(summaries) == 1, "expected exactly one provenance summary")
    control = controls[0]
    summary = summaries[0]
    require(control.get("status") == "armed", "provenance mode was not armed")
    require(control.get("requested") == "true", "provenance mode not requested")
    require(control.get("valid") == "true", "provenance configuration invalid")
    require(
        summary.get("status")
        in {"provenance_observed", "sample_capacity_exhausted"},
        "no bounded provenance result",
    )
    require(integer(summary, "contract_matches") > 0, "no exact draw matched")
    require(integer(summary, "samples") == len(draws), "sample total drift")
    require(
        integer(summary, "contract_matches")
        == len(draws) + integer(summary, "sample_overflow"),
        "draw sample accounting drift",
    )
    require(summary.get("classification_accounting_complete") == "true", "classification accounting drift")
    require(summary.get("sample_accounting_complete") == "true", "sample accounting drift")
    require(summary.get("static_world_proven") == "0", "static class was inferred")
    require(summary.get("static_dynamic_separation_complete") == "false", "incomplete separation was promoted")
    for event in [control, summary, *draws]:
        require(event.get("xenos_authority") == "true", "Xenos authority changed")
        require(event.get("suppression_allowed") == "false", "suppression was allowed")
        require(event.get("native_draw") == "false", "native drawing was enabled")
    dynamic = []
    unresolved = []
    for expected_sample, draw in enumerate(draws, 1):
        require(integer(draw, "sample") == expected_sample, "sample sequence drift")
        classification = draw.get("classification")
        require(
            classification in {"dynamic_vehicle_proven", "unresolved"},
            f"unexpected classification: {classification}",
        )
        require(draw.get("static_inference_from_absence") == "false", "absence inferred static ownership")
        if classification == "dynamic_vehicle_proven":
            require(draw.get("unresolved_reason") == "none", "dynamic draw has unresolved reason")
            require(
                draw.get("provenance_source")
                in {"vehicle_owner_method", "exact_title_argument"},
                "dynamic draw lacks exact provenance",
            )
            require(integer(draw, "identity_generation") > 0, "dynamic draw lacks generation")
            require(bool(draw.get("identity_owner")), "dynamic draw lacks owner")
            require(
                integer(draw, "identity_age_frames")
                <= integer(control, "maximum_vehicle_identity_age_frames"),
                "dynamic draw used stale identity",
            )
            dynamic.append(draw)
        else:
            require(draw.get("provenance_source") == "none", "unresolved draw has promoted source")
            require(
                draw.get("unresolved_reason")
                in {
                    "missing_title_origin",
                    "no_vehicle_identity",
                    "stale_vehicle_identity",
                    "ambiguous_vehicle_identity",
                },
                "unresolved draw lacks a fail-closed reason",
            )
            unresolved.append(draw)
    summary_dynamic = integer(summary, "dynamic_vehicle_proven")
    summary_unresolved = integer(summary, "unresolved")
    require(summary_dynamic >= len(dynamic), "dynamic sample exceeds aggregate")
    require(summary_unresolved >= len(unresolved), "unresolved sample exceeds aggregate")
    require(
        summary_dynamic + summary_unresolved == integer(summary, "contract_matches"),
        "aggregate classification drift",
    )
    sample_overflow = integer(summary, "sample_overflow")
    return {
        "schema": SCHEMA,
        "source_log": str(log_path),
        "capture_contract": {
            "family_sha256": summary["capture_family_sha256"],
            "vertex_shader": summary["vertex_shader"],
            "atlas_region": summary["atlas_region"],
            "viewport_raw": summary["viewport_raw"],
            "classification_scope": control["classification_scope"],
            "maximum_vehicle_identity_age_frames": integer(
                control, "maximum_vehicle_identity_age_frames"
            ),
        },
        "totals": {
            "shader_matches": integer(summary, "shader_matches"),
            "contract_matches": integer(summary, "contract_matches"),
            "contract_rejections": integer(summary, "contract_rejections"),
            "dynamic_vehicle_proven": summary_dynamic,
            "static_world_proven": 0,
            "unresolved": summary_unresolved,
            "samples": len(draws),
            "sample_overflow": sample_overflow,
        },
        "draws": draws,
        "qualification": {
            "per_draw_vehicle_promotion_allowed": bool(dynamic),
            "sample_coverage_complete": sample_overflow == 0,
            "static_dynamic_separation_complete": False,
            "whole_family_promotion_allowed": False,
            "static_inference_from_absence": False,
        },
        "safety": {
            "metadata_only": True,
            "native_coverage": False,
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
