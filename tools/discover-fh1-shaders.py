#!/usr/bin/env python3
"""List a local Vulkan shader discovery capture without disassembling game code."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


IDENTITY = re.compile(r"shader_([0-9A-F]{16})_([0-9A-F]{16})_([0-9A-F]{16})\.spv")


def discover(directory: Path) -> list[dict]:
    entries: dict[str, dict] = {}
    frames = set()
    with (directory / "draws.jsonl").open(encoding="utf-8") as stream:
        for index, line in enumerate(stream, 1):
            draw = json.loads(line)
            frames.add(draw["frame"])
            if len(frames) > 1:
                raise ValueError("discovery must contain exactly one frame")
            for stage in ("vertex", "pixel"):
                name = draw[stage]
                if not name:
                    continue
                match = IDENTITY.fullmatch(name)
                if not match or not (directory / name).is_file():
                    raise ValueError(f"draw {index}: missing or invalid shader identity: {name}")
                entry = entries.setdefault(name, {
                    "file": name, "guest_hash": match[1], "modification": match[2],
                    "translated_hash": match[3], "stages": [], "draws": [],
                    "hud_draws": [], "surfaces": [],
                })
                if stage not in entry["stages"]:
                    entry["stages"].append(stage)
                entry["draws"].append(index)
                if draw["hud"]:
                    entry["hud_draws"].append(index)
                for surface in draw["surfaces"]:
                    if surface not in entry["surfaces"]:
                        entry["surfaces"].append(surface)
    if not entries:
        raise ValueError("no shaders captured; choose a frame that issues native draws")
    return sorted(entries.values(), key=lambda entry: entry["file"])


def check_mod(entries: list[dict], shaders: Path) -> list[dict]:
    current = {entry["file"] for entry in entries}
    pairs = {(entry["guest_hash"], entry["modification"]) for entry in entries}
    result = []
    for path in sorted(shaders.glob("*.spv")):
        match = IDENTITY.fullmatch(path.name)
        status = ("invalid filename" if not match else "matches capture" if path.name in current
                  else "stale translation" if (match[1], match[2]) in pairs
                  else "not seen in this frame")
        result.append({"file": path.name, "status": status})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory containing draws.jsonl and .spv files")
    parser.add_argument("--shader", default="", help="guest hash or full filename substring")
    parser.add_argument("--surface", default="", help="packed surface key")
    parser.add_argument("--check-mod", type=Path, help="a mod's shaders/ directory to compare")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        entries = discover(args.directory)
        checks = check_mod(entries, args.check_mod) if args.check_mod else []
        entries = [entry for entry in entries if args.shader.upper() in entry["file"].upper()
                   and (not args.surface or any(surface["key"] == args.surface.upper()
                                               for surface in entry["surfaces"]))]
        if args.json:
            print(json.dumps({"shaders": entries, "mod_files": checks}, indent=2))
        else:
            for entry in entries:
                print(f'{entry["file"]}  {"/".join(entry["stages"])}  '
                      f'{len(entry["draws"])} draws ({len(entry["hud_draws"])} HUD)')
                for surface in entry["surfaces"]:
                    kind = "depth" if surface["depth"] else "color"
                    print(f'  {surface["key"]} slot {surface["slot"]} {kind} '
                          f'{surface["width"]}x{surface["height"]} '
                          f'format {surface["format"]} samples {surface["samples"]}')
            for check in checks:
                print(f'{check["file"]}: {check["status"]}')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"shader discovery: {error}\n")


if __name__ == "__main__":
    main()
