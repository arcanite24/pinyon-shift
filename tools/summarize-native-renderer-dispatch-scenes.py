"""Build a conservative cross-scene matrix from dispatch runtime reports."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-dispatch-scenes.v1"
RUNTIME_SCHEMA = "pinyon-shift.native-renderer-dispatch-runtime.v3"
SCENE_RE = re.compile(r"^[a-z_]{1,32}$")


def _validate_report(report: dict) -> None:
    if report.get("schema") != RUNTIME_SCHEMA:
        raise ValueError("unsupported dispatch runtime report schema")
    scene = str(report.get("scene", ""))
    if not SCENE_RE.fullmatch(scene):
        raise ValueError(f"invalid dispatch scene marker: {scene}")
    required_safety = {
        "metadata_only": True,
        "guest_payload_read": False,
        "guest_state_changed": False,
        "control_flow_changed": False,
        "xenos_authority": True,
        "suppression_allowed": False,
    }
    safety = report.get("safety", {})
    if any(safety.get(key) is not value for key, value in required_safety.items()):
        raise ValueError("dispatch runtime report does not prove passive safety")


def build(reports: list[dict], minimum_scene_sessions: int = 2) -> dict:
    if minimum_scene_sessions < 2:
        raise ValueError("scene qualification requires at least two sessions")
    if not reports:
        raise ValueError("no dispatch runtime reports supplied")
    for report in reports:
        _validate_report(report)
    sessions = [str(report.get("session", "")) for report in reports]
    if any(not session for session in sessions) or len(set(sessions)) != len(sessions):
        raise ValueError("dispatch runtime report sessions must be unique and non-empty")

    scene_sessions = collections.Counter(str(report["scene"]) for report in reports)
    families: dict[tuple[str, str], dict] = {}
    observed_sessions: dict[tuple[str, str], dict[str, set[str]]] = {}
    for report in reports:
        scene = str(report["scene"])
        session = str(report["session"])
        for caller in report.get("callers", []):
            wrapper = str(caller.get("wrapper_address", "")).upper()
            address = str(caller.get("caller", "")).upper()
            key = (wrapper, address)
            family = families.setdefault(
                key,
                {
                    "wrapper": str(caller.get("wrapper", "unknown")),
                    "wrapper_address": wrapper,
                    "caller": address,
                    "calls_by_scene": collections.Counter(),
                    "semantic_identity": "unknown",
                    "suppression_eligible": False,
                },
            )
            family["calls_by_scene"][scene] += int(caller.get("calls", 0))
            observed_sessions.setdefault(key, {}).setdefault(scene, set()).add(session)

    rows = []
    for key, family in families.items():
        coverage = {}
        stable_scenes = []
        repeated_scene_available = False
        for scene in sorted(scene_sessions):
            total = scene_sessions[scene]
            observed = len(observed_sessions.get(key, {}).get(scene, set()))
            calls = int(family["calls_by_scene"].get(scene, 0))
            coverage[scene] = {
                "calls": calls,
                "observed_sessions": observed,
                "total_sessions": total,
            }
            if scene != "unmarked" and total >= minimum_scene_sessions:
                repeated_scene_available = True
                if observed == total:
                    stable_scenes.append(scene)
        if not repeated_scene_available:
            status = "insufficient_repeats"
        elif len(stable_scenes) == 1:
            status = "stable_scene_candidate"
        elif len(stable_scenes) > 1:
            status = "stable_multi_scene_candidate"
        else:
            status = "unstable_or_unobserved"
        rows.append(
            {
                "wrapper": family["wrapper"],
                "wrapper_address": family["wrapper_address"],
                "caller": family["caller"],
                "scene_coverage": coverage,
                "stable_scenes": stable_scenes,
                "candidate_status": status,
                "semantic_identity": "unknown",
                "promotion_eligible": False,
                "suppression_eligible": False,
            }
        )
    rows.sort(key=lambda item: (item["wrapper_address"], item["caller"]))
    status_counts = collections.Counter(item["candidate_status"] for item in rows)
    return {
        "schema": SCHEMA,
        "minimum_scene_sessions": minimum_scene_sessions,
        "scene_sessions": dict(sorted(scene_sessions.items())),
        "families": rows,
        "totals": {
            "reports": len(reports),
            "families": len(rows),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "qualification": "scene_frequency_only_semantics_unknown",
        "safety": {
            "metadata_only": True,
            "xenos_authority": True,
            "promotion_allowed": False,
            "suppression_allowed": False,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=pathlib.Path)
    parser.add_argument("--minimum-scene-sessions", type=int, default=2)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
        document = build(reports, args.minimum_scene_sessions)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print("native renderer dispatch scene summary failed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
