#!/usr/bin/env python3
"""Validate fail-closed native-renderer suppression-switch specifications."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


INPUT_SCHEMA = "pinyon-shift.native-renderer-suppression-switches.v1"
OUTPUT_SCHEMA = "pinyon-shift.native-renderer-suppression-switch-report.v1"
IMPLEMENTATION_STATUSES = {"absent", "diagnostic_only", "implemented"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def signature(value: Any, label: str) -> str:
    rendered = str(value)
    require(
        len(rendered) == 16
        and all(character in "0123456789ABCDEF" for character in rendered),
        f"{label} must be a 16-digit uppercase hexadecimal value",
    )
    return rendered


def validate(document: dict[str, Any]) -> dict[str, Any]:
    require(document.get("schema") == INPUT_SCHEMA, "unsupported switch schema")
    families = document.get("families")
    require(isinstance(families, list) and families, "families must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    family_names: set[str] = set()
    switch_names: set[str] = set()
    for index, entry in enumerate(families):
        require(isinstance(entry, dict), f"family {index} must be an object")
        family = str(entry.get("family", "")).strip()
        switch = str(entry.get("switch", "")).strip()
        cvar = str(entry.get("cvar", "")).strip()
        require(bool(family), f"family {index} requires a name")
        require(bool(switch), f"family {index} requires a switch")
        require(bool(cvar), f"family {index} requires a cvar")
        require(family not in family_names, f"duplicate family: {family}")
        require(switch not in switch_names, f"duplicate switch: {switch}")
        family_names.add(family)
        switch_names.add(switch)
        anchor = signature(entry.get("anchor_signature"), f"family {family} anchor")
        follower = signature(
            entry.get("follower_signature"), f"family {family} follower"
        )
        require(anchor != follower, f"family {family} signatures must be distinct")
        require(entry.get("scope") == "exact_pass_family", f"family {family} scope")
        require(entry.get("activation") == "startup_only", f"family {family} activation")
        require(entry.get("default_enabled") is False, f"family {family} must default off")
        require(entry.get("independent") is True, f"family {family} must be independent")
        status = str(entry.get("implementation_status", ""))
        require(
            status in IMPLEMENTATION_STATUSES,
            f"family {family} has invalid implementation status",
        )
        draw_implemented = entry.get("draw_suppression_implemented")
        resolve_implemented = entry.get("resolve_suppression_implemented")
        require(
            isinstance(draw_implemented, bool),
            f"family {family} draw implementation flag must be boolean",
        )
        require(
            isinstance(resolve_implemented, bool),
            f"family {family} resolve implementation flag must be boolean",
        )
        if status != "implemented":
            require(
                draw_implemented is False and resolve_implemented is False,
                f"family {family} cannot claim suppression before implementation",
            )
        rollback_qualified = entry.get("rollback_qualified", False)
        require(
            isinstance(rollback_qualified, bool),
            f"family {family} rollback qualification flag must be boolean",
        )
        require(
            status == "implemented" or rollback_qualified is False,
            f"family {family} cannot qualify rollback before implementation",
        )
        state_yield_implemented = entry.get("state_yield_implemented", False)
        state_yield_qualified = entry.get("state_yield_qualified", False)
        require(
            isinstance(state_yield_implemented, bool),
            f"family {family} state-yield implementation flag must be boolean",
        )
        require(
            isinstance(state_yield_qualified, bool),
            f"family {family} state-yield qualification flag must be boolean",
        )
        require(
            state_yield_implemented or state_yield_qualified is False,
            f"family {family} cannot qualify state yield before implementation",
        )
        if state_yield_implemented:
            require(
                entry.get("state_gate") == "consecutive_publication_warmup",
                f"family {family} must use the publication warmup gate",
            )
            require(
                isinstance(entry.get("warmup_frames"), int)
                and entry["warmup_frames"] > 0,
                f"family {family} warmup frames must be positive",
            )
            require(
                isinstance(entry.get("failure_cooldown_frames"), int)
                and entry["failure_cooldown_frames"] > 0,
                f"family {family} failure cooldown must be positive",
            )
            require(
                entry.get("gap_behavior") == "reset_warmup_and_execute_xenos",
                f"family {family} must yield after a frame gap",
            )
            require(
                entry.get("failure_behavior") == "cooldown_and_execute_xenos",
                f"family {family} must yield after publication failure",
            )
            require(
                entry.get("guest_side_effects_preserved") is True,
                f"family {family} must preserve guest side effects",
            )
        require(
            entry.get("xenos_fallback") == "mandatory",
            f"family {family} must retain mandatory Xenos fallback",
        )
        normalized.append(
            {
                "family": family,
                "anchor_signature": anchor,
                "follower_signature": follower,
                "switch": switch,
                "cvar": cvar,
                "scope": "exact_pass_family",
                "activation": "startup_only",
                "default_enabled": False,
                "independent": True,
                "implementation_status": status,
                "draw_suppression_implemented": draw_implemented,
                "resolve_suppression_implemented": resolve_implemented,
                "rollback_qualified": rollback_qualified,
                "state_yield_implemented": state_yield_implemented,
                "state_yield_qualified": state_yield_qualified,
                "xenos_fallback": "mandatory",
                "rollback_gate": (
                    "pass"
                    if rollback_qualified
                    else ("unknown" if status != "implemented" else "requires_runtime_test")
                ),
            }
        )
    return {
        "schema": OUTPUT_SCHEMA,
        "families": normalized,
        "summary": {
            "family_count": len(normalized),
            "implemented_count": sum(
                entry["implementation_status"] == "implemented"
                for entry in normalized
            ),
            "diagnostic_control_count": sum(
                entry["implementation_status"] == "diagnostic_only"
                for entry in normalized
            ),
            "rollback_switch_gate": (
                "pass" if all(entry["rollback_qualified"] for entry in normalized) else "unknown"
            ),
            "state_based_yield_gate": (
                "pass"
                if all(
                    not entry["state_yield_implemented"]
                    or entry["state_yield_qualified"]
                    for entry in normalized
                )
                else "requires_runtime_test"
            ),
            "reason": (
                "one or more state-yield gates still require runtime qualification"
                if any(
                    entry["state_yield_implemented"]
                    and not entry["state_yield_qualified"]
                    for entry in normalized
                )
                else (
                    "every implemented switch has runtime rollback and state-yield qualification"
                    if all(entry["rollback_qualified"] for entry in normalized)
                    else "one or more switches still require runtime rollback qualification"
                )
            ),
        },
        "safety": {
            "xenos_authority": True,
            "suppression_allowed": all(
                entry["rollback_qualified"]
                and entry["draw_suppression_implemented"]
                and (
                    not entry["state_yield_implemented"]
                    or entry["state_yield_qualified"]
                )
                for entry in normalized
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        document = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = validate(document)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"error: {error}")
        return 1
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
