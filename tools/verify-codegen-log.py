#!/usr/bin/env python3
"""Verify that a ReXGlue codegen log contains only reviewed warnings."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


WARNING_PREFIX = re.compile(r"\[warning\]\s+\[codegen\](?:\s+\[t\d+\])?\s+(?P<message>.+)$", re.IGNORECASE)


def verify(log_path: pathlib.Path, allowlist_path: pathlib.Path) -> dict:
    config = json.loads(allowlist_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1 or not isinstance(config.get("warnings"), list):
        raise ValueError("unsupported warning allowlist schema")
    rules = []
    for item in config["warnings"]:
        if not item.get("id") or not item.get("pattern") or not item.get("reason"):
            raise ValueError("every accepted warning needs id, pattern, and reason")
        rules.append((item["id"], re.compile(item["pattern"])))

    matches = {identifier: 0 for identifier, _ in rules}
    unknown: list[str] = []
    warning_count = 0
    for line in log_path.read_text(encoding="utf-8", errors="strict").splitlines():
        marker = WARNING_PREFIX.search(line)
        if not marker:
            continue
        warning_count += 1
        message = marker.group("message").strip()
        matching = [identifier for identifier, pattern in rules if pattern.fullmatch(message)]
        if len(matching) == 1:
            matches[matching[0]] += 1
        elif not matching:
            unknown.append(message)
        else:
            unknown.append(f"ambiguous allowlist match: {message}")

    missing = sorted(identifier for identifier, count in matches.items() if count == 0)
    if unknown or missing:
        details = []
        if unknown:
            details.append("unrecognized warnings: " + " | ".join(sorted(set(unknown))))
        if missing:
            details.append("expected warnings not observed: " + ", ".join(missing))
        raise ValueError("; ".join(details))
    return {
        "schema": "pinyon-shift.codegen-warning-verification.v1",
        "log": log_path.name,
        "warning_count": warning_count,
        "accepted": matches,
    }


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument(
        "--allowlist",
        type=pathlib.Path,
        default=root / "config/rexglue/accepted-codegen-warnings.json",
    )
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.log, args.allowlist), indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
