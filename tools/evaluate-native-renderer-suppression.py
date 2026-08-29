#!/usr/bin/env python3
"""Evaluate a local evidence bundle before implementing pass suppression."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


INPUT_SCHEMA = "pinyon-shift.native-renderer-suppression-evidence.v1"
OUTPUT_SCHEMA = "pinyon-shift.native-renderer-suppression-admission.v1"
STATUSES = {"pass", "fail", "unknown"}
REQUIRED_GATES = (
    "exact_family_identity",
    "complete_native_coverage",
    "color_parity",
    "depth_parity",
    "later_gpu_consumers",
    "guest_cpu_visibility",
    "query_side_effects",
    "memexport_side_effects",
    "output_freshness",
    "fallback_recovery",
    "gpu_timing",
    "rollback_switch",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _validate_sha256(value: Any, label: str) -> str:
    rendered = str(value)
    _require(
        len(rendered) == 64
        and all(character in "0123456789ABCDEF" for character in rendered),
        f"{label} must be an uppercase SHA-256",
    )
    return rendered


def evaluate(
    evidence: dict[str, Any], *, artifact_root: Path | None = None
) -> dict[str, Any]:
    _require(evidence.get("schema") == INPUT_SCHEMA, "unsupported evidence schema")
    family = str(evidence.get("family", ""))
    scene = str(evidence.get("scene", ""))
    _require(bool(family), "family is required")
    _require(bool(scene), "scene is required")
    build_sha256 = _validate_sha256(evidence.get("build_sha256"), "build_sha256")

    signatures = evidence.get("signatures")
    _require(isinstance(signatures, list) and signatures, "signatures are required")
    normalized_signatures: list[str] = []
    for index, signature in enumerate(signatures):
        rendered = str(signature)
        _require(
            len(rendered) == 16
            and all(character in "0123456789ABCDEF" for character in rendered),
            f"signatures[{index}] must be a 16-digit uppercase hexadecimal value",
        )
        _require(rendered not in normalized_signatures, "duplicate signature")
        normalized_signatures.append(rendered)

    gates = evidence.get("gates")
    _require(isinstance(gates, dict), "gates must be an object")
    missing = sorted(set(REQUIRED_GATES) - set(gates))
    extra = sorted(set(gates) - set(REQUIRED_GATES))
    _require(not missing, "missing gates: " + ", ".join(missing))
    _require(not extra, "unknown gates: " + ", ".join(extra))

    verified_root = artifact_root.resolve() if artifact_root else None
    normalized_gates: dict[str, dict[str, Any]] = {}
    blockers: list[dict[str, str]] = []
    for name in REQUIRED_GATES:
        gate = gates[name]
        _require(isinstance(gate, dict), f"gate {name} must be an object")
        status = str(gate.get("status", ""))
        evidence_text = str(gate.get("evidence", "")).strip()
        _require(status in STATUSES, f"gate {name} has invalid status")
        _require(bool(evidence_text), f"gate {name} requires evidence text")

        artifacts = gate.get("artifacts", [])
        _require(isinstance(artifacts, list), f"gate {name} artifacts must be a list")
        normalized_artifacts: list[dict[str, Any]] = []
        for index, artifact in enumerate(artifacts):
            _require(
                isinstance(artifact, dict),
                f"gate {name} artifact {index} must be an object",
            )
            path_text = str(artifact.get("path", ""))
            _require(bool(path_text), f"gate {name} artifact {index} needs a path")
            expected_hash = _validate_sha256(
                artifact.get("sha256"), f"gate {name} artifact {index} sha256"
            )
            normalized = {"path": path_text, "sha256": expected_hash}
            if verified_root:
                path = (verified_root / path_text).resolve()
                _require(
                    path == verified_root or verified_root in path.parents,
                    f"gate {name} artifact escapes artifact root: {path_text}",
                )
                _require(path.is_file(), f"gate {name} artifact is missing: {path_text}")
                _require(
                    _sha256(path) == expected_hash,
                    f"gate {name} artifact hash mismatch: {path_text}",
                )
                normalized["verified"] = True
            normalized_artifacts.append(normalized)

        normalized_gates[name] = {
            "status": status,
            "evidence": evidence_text,
            "artifacts": normalized_artifacts,
        }
        if status != "pass":
            blockers.append({"gate": name, "status": status, "reason": evidence_text})

    safety = evidence.get("safety")
    _require(isinstance(safety, dict), "safety must be an object")
    required_safety = {
        "xenos_draws_preserved": True,
        "draw_suppression_implemented": False,
        "resolve_suppression_implemented": False,
    }
    for name, expected in required_safety.items():
        _require(
            safety.get(name) is expected,
            f"safety.{name} must be {str(expected).lower()}",
        )

    ready = not blockers
    return {
        "schema": OUTPUT_SCHEMA,
        "family": family,
        "scene": scene,
        "build_sha256": build_sha256,
        "signatures": normalized_signatures,
        "gates": normalized_gates,
        "summary": {
            "passed": len(REQUIRED_GATES) - len(blockers),
            "required": len(REQUIRED_GATES),
            "blockers": blockers,
            "ready_for_suppression_implementation": ready,
        },
        "safety": {
            **required_safety,
            "suppression_allowed": False,
            "reason": (
                "admission evidence complete; implementation remains absent and disabled"
                if ready
                else "one or more admission gates are not proven"
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="local evidence bundle JSON")
    parser.add_argument("--output", "-o", type=Path, help="write admission report")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="verify artifact paths and hashes below this local directory",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="return exit code 2 while any admission gate is not proven",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    result = evaluate(evidence, artifact_root=args.artifact_root)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.require_ready and not result["summary"][
        "ready_for_suppression_implementation"
    ]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
