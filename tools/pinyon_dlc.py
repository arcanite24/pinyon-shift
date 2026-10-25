#!/usr/bin/env python3
"""Owned FH1 DLC on every OS (LX-3.4): import, enable and disable packages.

  pinyon.py dlc status [--state-root DIR] [--json]
  pinyon.py dlc import PATH [--state-root DIR] [--json]
  pinyon.py dlc enable PACKAGE_ID [--state-root DIR] [--game-root DIR] [--json]
  pinyon.py dlc disable PACKAGE_ID [--state-root DIR] [--json]
  pinyon.py dlc udlc [--find] [--open-pages] [--wait SECONDS] [--traffic]
                    [PATH ...] [--state-root DIR] [--json]

PATH is a raw package, a ZIP of packages or a folder of them, as the Windows
launcher's DLC panel takes. The work is tools/manage-fh1-dlc.py, the same
verifier the Windows panel runs (through manage-dlc.ps1), given this
platform's archive extractor (pinyon_shift_fh1_archive_extract, built beside
the game). Each package is checked against config/supported-dlc.json before
anything is published; imported packages start disabled. Enabling Rally
verifies it and prepares its generated assets (prepare-fh1-rally.py).

Prints one JSON object: {"result": "ok", "packages": [...]} with each
package's package_id, display_name, enabled, source, status (gameplay_unverified,
missing, metadata_invalid, conflict, unmanaged) and, for Rally,
rally_assets_cached; or {"result": "error", "error": ...}.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import subprocess
import sys
import time
import webbrowser
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402
import pinyon_xe as xe  # noqa: E402

MANAGER = common.ROOT / "tools" / "manage-fh1-dlc.py"
RALLY = "6F6992766050D818245ADD408031E280FB5F4E634D"
UDLC = "4D5309C900000729"
TRAFFIC = "4D5309C900000732"
UDLC_ARCHIVES = {
    UDLC: {"file": "UDLCv1.2.zip", "size": 1053866142,
           "md5": "a96d5be3575702aacb8a4da9b20703cd",
           "page": "https://www.moddb.com/mods/forza-horizon-udlc-pack/downloads/udlcv12"},
    TRAFFIC: {"file": "Traffic_Unlocker.1.zip", "size": 1894387,
              "md5": "b4e91caf22003988f93b7f866a070172",
              "page": "https://www.moddb.com/mods/forza-horizon-udlc-pack/downloads/udlc-traffic-car-unlocker"},
}


def manager():
    spec = importlib.util.spec_from_file_location("fh1_dlc", MANAGER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def identify_udlc(path: Path) -> str:
    size = path.stat().st_size
    dlc = manager()
    if size == dlc.OLD_UDLC_SIZE and xe.digest(path, "md5") == dlc.OLD_UDLC_MD5:
        raise common.CommandError(f"This is UDLC v1.11. Download UDLC v1.2 from ModDB: {dlc.UDLC_PAGE}")
    candidates = {id: known for id, known in UDLC_ARCHIVES.items() if size == known["size"]}
    if candidates:
        md5 = xe.digest(path, "md5")
        for id, known in candidates.items():
            if md5 == known["md5"]:
                return id
        raise common.CommandError(f"{path.name} failed its MD5 check; download it again from ModDB")
    raise common.CommandError(f"{path.name} is not a supported UDLC ZIP; download UDLC v1.2 from ModDB: "
                              + UDLC_ARCHIVES[UDLC]["page"])


def find_udlc(folders: list[Path], wanted: list[str]) -> dict[str, Path]:
    found = {}
    for folder in folders:
        for id in wanted:
            if id in found:
                continue
            known = UDLC_ARCHIVES[id]
            pattern = re.compile(re.escape(Path(known["file"]).stem) + r"(?: \(\d+\))?\.zip", re.I)
            for path in sorted(folder.iterdir()) if folder.is_dir() else []:
                if path.is_file() and pattern.fullmatch(path.name) and path.stat().st_size == known["size"]:
                    identify_udlc(path)
                    found[id] = path
                    break
    return found


def run_udlc(args: argparse.Namespace) -> dict:
    if not math.isfinite(args.wait) or args.wait < 0:
        raise common.CommandError("the download wait must be zero or more seconds")
    wanted = [UDLC, TRAFFIC] if args.traffic else [UDLC]
    if args.open_pages:
        for id in wanted:
            webbrowser.open(UDLC_ARCHIVES[id]["page"])
    archives = {}
    for path in args.paths:
        path = path.expanduser().resolve()
        if not path.is_file():
            raise common.CommandError(f"{path} does not exist")
        id = identify_udlc(path)
        if id in archives:
            raise common.CommandError(f"two copies of {UDLC_ARCHIVES[id]['file']} were given")
        archives[id] = path
    if args.find or args.wait:
        folders = xe.download_folders()
        deadline = time.monotonic() + args.wait
        while True:
            missing = [id for id in wanted if id not in archives]
            archives.update(find_udlc(folders, missing))
            if all(id in archives for id in wanted):
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                missing = next(id for id in wanted if id not in archives)
                raise common.CommandError(f"{UDLC_ARCHIVES[missing]['file']} was not found in Downloads; "
                                          f"download it from {UDLC_ARCHIVES[missing]['page']}")
            time.sleep(min(5, remaining))
    if not archives:
        raise common.CommandError("choose the UDLC ZIPs, or pass --find to look in Downloads")
    state = common.state_root(args.state_root)
    extractor = common.require_extractor()
    dlc = manager()
    # Validate every wrapper before publishing; the importer also verifies
    # the inner package SHA-256 and the extracted payload against the catalog.
    for id in (UDLC, TRAFFIC):
        if id in archives:
            dlc.import_content(archives[id], state, extractor)
    dlc.set_enabled(state, UDLC, True)
    if TRAFFIC in archives:
        dlc.set_enabled(state, TRAFFIC, True)
    keys = ("package_id", "display_name", "enabled", "status", "source")
    return {"result": "ok", "packages": [{key: p[key] for key in keys}
            for p in dlc.list_content(state) if p["package_id"] in UDLC_ARCHIVES]}


def run(args: argparse.Namespace) -> dict:
    if args.dlc_command == "udlc":
        try:
            return run_udlc(args)
        except (zipfile.BadZipFile, subprocess.SubprocessError) as error:
            raise common.CommandError(f"UDLC could not be imported: {error}") from None
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
    udlc = sub.add_parser("udlc", help="install and enable the community UDLC pack from your downloads")
    udlc.add_argument("paths", type=Path, nargs="*")
    udlc.add_argument("--find", action="store_true", help="look in the browser's Downloads folders")
    udlc.add_argument("--open-pages", action="store_true", help="open the ModDB pages in your browser")
    udlc.add_argument("--wait", type=float, default=0, help="seconds to wait for the downloads to finish")
    udlc.add_argument("--traffic", action="store_true", help="also find the optional Traffic Car Unlocker")
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
