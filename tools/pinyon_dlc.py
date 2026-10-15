#!/usr/bin/env python3
"""Owned FH1 DLC on every OS (LX-3.4): import, enable and disable packages.

  pinyon.py dlc status [--state-root DIR] [--json]
  pinyon.py dlc import PATH [--state-root DIR] [--json]
  pinyon.py dlc enable PACKAGE_ID [--state-root DIR] [--game-root DIR] [--json]
  pinyon.py dlc disable PACKAGE_ID [--state-root DIR] [--json]

PATH is a raw package, a ZIP of packages or a folder of them, as the Windows
launcher's DLC panel takes. The work is tools/manage-fh1-dlc.py, the same
verifier the Windows panel runs (through manage-dlc.ps1), given this
platform's archive extractor (pinyon_shift_fh1_archive_extract, built beside
the game). Each package is checked against config/supported-dlc.json before
anything is published; imported packages start disabled. Enabling Rally
verifies it and prepares its generated assets (prepare-fh1-rally.py).

Prints one JSON object: {"result": "ok", "packages": [...]} with each
package's package_id, display_name, enabled, status (gameplay_unverified,
missing, metadata_invalid, conflict, unmanaged) and, for Rally,
rally_assets_cached; or {"result": "error", "error": ...}.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402

MANAGER = common.ROOT / "tools" / "manage-fh1-dlc.py"
RALLY = "6F6992766050D818245ADD408031E280FB5F4E634D"


def run(args: argparse.Namespace) -> dict:
    state = common.state_root(args.state_root)
    action = {"status": "list"}.get(args.dlc_command, args.dlc_command)
    command = [common.python_executable(), str(MANAGER), action, "--state-root", str(state)]
    if action != "list":
        # Status needs no extractor; changes do (enable re-verifies content
        # and prepares Rally with it).
        command += ["--extractor", str(common.require_extractor())]
    if action == "import":
        source = args.path.expanduser()
        if not source.exists():
            raise common.CommandError(f"{source} does not exist")
        command += ["--source", str(source.resolve())]
    if action in ("enable", "disable"):
        command += ["--package-id", args.package_id.upper()]
        if args.game_root:
            command += ["--game-root", str(common.game_root(args.game_root))]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
    if completed.returncode:
        raise common.CommandError(completed.stderr.strip() or "DLC management stopped")
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise common.CommandError("DLC management returned an invalid result") from None
    packages = result.get("packages", [])
    out = {"result": "ok", "packages": packages,
           "enabled": sum(1 for package in packages if package.get("enabled"))}
    rally = next((package for package in packages if package.get("package_id") == RALLY), None)
    if rally is not None:
        out["rally"] = {"enabled": bool(rally.get("enabled")),
                        "assets_cached": bool(rally.get("rally_assets_cached"))}
    return out


def add_parser(commands) -> None:
    parser = commands.add_parser("dlc", help="import and manage your FH1 DLC packages")
    sub = parser.add_subparsers(dest="dlc_command", required=True)
    sub.add_parser("status", help="list the imported packages")
    importing = sub.add_parser("import", help="verify and import a package, ZIP or folder")
    importing.add_argument("path", type=Path)
    for name, text in (("enable", "play with an imported package"),
                       ("disable", "play without an imported package")):
        action = sub.add_parser(name, help=text)
        action.add_argument("package_id")
        action.add_argument("--game-root", type=Path)
    for action in sub.choices.values():
        action.add_argument("--state-root", type=Path)
        action.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(run, args)
