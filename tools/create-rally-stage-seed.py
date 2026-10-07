#!/usr/bin/env python3
"""Create a private base-disc Rally stage probe from a pinned save and owned DLC.

This is a diagnostic seed, not released Rally support. It adds a solo event
and a portal beside the pinned save's Gauntlet entry. Normal events remain in
the database; only that entry's trigger radius is suppressed in this copy.
No title-update inputs are used. Run it with fh1-rally-stage-start.fh1test.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assets = tool("prepare-fh1-rally")
RALLY, STAGE_ROUTES, SERIES_ROUTES = assets.RALLY, assets.STAGE_ROUTES, assets.SERIES_ROUTES
pace_notes, add_stage, next_stage = assets.pace_notes, assets.add_stage, assets.next_stage




def portal(activities: bytes, career: bytes) -> dict[str, bytes]:
    root = ET.fromstring(activities)
    activity = ET.SubElement(root, "Activity", type="ActivityGeneric", name="rally_stage_probe")
    group = ET.SubElement(activity, "StateGroup", id="rally_stage_probe")
    state = ET.SubElement(group, "State", id="Root")
    ET.SubElement(state, "Entry", id="enter")
    behavior = ET.SubElement(state, "Behaviour", id="CLoadIntoCareerRace", event_id="RALLY_PROBE")
    ET.SubElement(behavior, "Attribute", id="resource_package", value="CareerLoading")
    ET.SubElement(activity, "TriggerZone", object="FR06_NODE", name="rally_stage_probe",
                  radius="25", maxMPH="150", prompt="IDS_Description_MediaCenter",
                  mapTag="mediacentertodo", mapDescription="IDS_Description_MediaCenter")
    events = ET.fromstring(career)
    events.find("Activity[@name='FR06']/TriggerZone").set("radius", "0")
    # Use the generic activity file. The tested career-file variants could not
    # activate this new event; the generic file's direct loading flow works.
    return {"Colorado/activities.xml": ET.tostring(root, encoding="utf-8"),
            "Colorado/career_event_activations.xml": ET.tostring(events, encoding="utf-8")}


def autopilot(flow: bytes) -> bytes:
    root = ET.fromstring(flow)
    cleanup = root.find("State[@id='prerace_cleanup']")
    # Native retry resets the car's control mode but leaves the global AI
    # action's latch set. Clear it before enabling, or the repeated enable skips.
    cleanup.find("Node[@id='unblock_pause_entry']/Exit").set("target", "rally_probe_ai_reset.enter")
    reset = ET.SubElement(cleanup, "Node", id="rally_probe_ai_reset", state="global.disable_ai_player_car_control")
    ET.SubElement(reset, "Entry", id="enter")
    ET.SubElement(reset, "Exit", id="exit", target="rally_probe_ai.enter")
    node = ET.SubElement(cleanup, "Node", id="rally_probe_ai", state="global.enable_ai_player_car_control")
    ET.SubElement(node, "Entry", id="enter")
    ET.SubElement(node, "Exit", id="exit", target=".exit")
    return ET.tostring(root, encoding="utf-8")


def create(args) -> Path:
    dlc, runner, archive = (tool(name) for name in
        ("manage-fh1-dlc", "run-fh1-render-test", "patch-fh1-archive"))
    source, output = args.seed.resolve(), args.output.resolve()
    if os.environ.get("LOCALAPPDATA") and output.is_relative_to(
            (Path(os.environ["LOCALAPPDATA"]) / "PinyonShift").resolve()):
        raise ValueError("use a private output outside the AppData save")
    if output.exists() or any(output.is_relative_to(p.resolve()) for p in
                             (source, args.dlc_state, args.game_root)):
        raise ValueError("choose a new output outside all input directories")
    if getattr(args, "next_route", None) == getattr(args, "route", None) and getattr(args, "next_route", None) is not None:
        raise ValueError("the next Rally route must differ from the first stage")
    series_id = getattr(args, "series", None)
    if series_id and (series_id not in range(1, 8) or args.next_route):
        raise ValueError("choose one Rally series without --next-route")
    seed_manifest = json.loads((source / "seed.json").read_text(encoding="utf-8"))
    for relative, expected in seed_manifest["profiles"].items():
        with (source / relative).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest().upper() != expected:
                raise ValueError("pinned save seed has changed")
    content, package, _ = dlc.verified_content(args.dlc_state, RALLY)
    _, _, header = dlc.package_paths(dlc.long_path(args.dlc_state), RALLY)
    payload = package["payload_sha256"]
    assets.verify_base(args.game_root)
    runner.prepare_isolated_state(source, output)
    output = dlc.long_path(output)
    enabled, _, target_header = dlc.package_paths(output, RALLY)
    enabled.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(content, enabled)
    target_header.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(header, target_header)
    builtin = getattr(args, "builtin", False)
    adapter = output / ("cache/rally_adapter" if builtin else "mods/rally_stage_probe")
    if series_id:
        entries = [(route, "RALLY_PROBE" if i == 0 else f"RALLY_S{i+1}")
                   for i, route in enumerate(SERIES_ROUTES[series_id - 1])]
    else:
        entries = [(args.route, "RALLY_PROBE")]
        if args.next_route:
            entries.append((args.next_route, "RALLY_NEXT"))
    sequence = assets.build_assets(content, args.game_root, args.extractor.resolve(), adapter,
                                   entries, pace=getattr(args, "pace_notes", False))
    stage = sequence[0]
    following = sequence[1] if len(sequence) > 1 else None
    mod, media = adapter, adapter / "game/media"
    if not builtin:
        (mod / "mod.toml").write_text('name = "rally_stage_probe"\nversion = "0.1.0"\nabi = 1\n')
    settings = output / "config/pinyon_shift.toml"
    setting = 'enabled_mods = ""' if builtin else 'enabled_mods = "rally_stage_probe"'
    text = re.sub(r'(?m)^enabled_mods\s*=.*$', setting, settings.read_text())
    if not re.search(r'(?m)^enabled_mods\s*=', text):
        text += '\n' + setting + '\n'
    settings.write_text(text)
    reference = output / "rally-reference"
    reference.mkdir()
    def extract(zip_path, name, filename):
        target = reference / filename
        subprocess.run([str(args.extractor.resolve()), "--archive-member", str(zip_path),
                        name, str(target)], check=True, capture_output=True, text=True)
        return target
    game_modes = args.game_root / "media/gamemodes.zip"
    activities = extract(game_modes, "Colorado/activities.xml", "activities.xml").read_bytes()
    career = extract(game_modes, "Colorado/career_event_activations.xml", "career.xml").read_bytes()
    replacements = portal(activities, career)
    if args.autopilot or following:
        flow = extract(game_modes, "game_festival_race_flow.xml", "race-flow.xml").read_bytes()
        if args.autopilot:
            flow = autopilot(flow)
        if following:
            flow = next_stage(flow, "RALLY_NEXT" if series_id else following["horizon_event_id"])
        replacements["game_festival_race_flow.xml"] = flow
    archive.patch_archive(game_modes, media / "gamemodes.zip", replacements)
    for path in (source / "cache").glob("fh1-*"):
        if path.is_file():
            (output / "cache").mkdir(exist_ok=True)
            shutil.copy2(path, output / "cache" / path.name)
    (output / "rally-probe.json").write_text(json.dumps(dict(
        diagnostic_only=True, builtin=builtin, autopilot=args.autopilot, stage=stage, next_stage=following,
        series_id=series_id, sequence=sequence, package_id=RALLY,
        payload_sha256=payload, source_seed=str(source)), indent=2) + "\n")
    mapping = (f'version = 1\nevent_id = {stage["event_id"]}\nroute = {stage["route"]}\n' if not following else
        'version = 2\n' + ''.join(f'\n[[stages]]\nevent_id = {entry["event_id"]}\nroute = {entry["route"]}\n'
                                   for entry in (stage, following)))
    if series_id:
        mapping = f'version = 3\nseries_id = {series_id}\n' + ''.join(
            f'\n[[stages]]\nevent_id = {entry["event_id"]}\nroute = {entry["route"]}\n'
            f'event_name = "{entry["horizon_event_id"]}"\n' for entry in sequence)
    (mod / "rally-stage.toml").write_text(mapping, encoding="utf-8")
    return args.output.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True, help="pinned base-disc save seed")
    parser.add_argument("--dlc-state", type=Path, required=True, help="state with verified Rally import")
    parser.add_argument("--output", type=Path, required=True, help="new private state directory")
    parser.add_argument("--route", type=int, choices=STAGE_ROUTES, default=1)
    parser.add_argument("--next-route", type=int, choices=STAGE_ROUTES,
                        help="private completed-results transition probe to this route")
    parser.add_argument("--series", type=int, choices=range(1, 8),
                        help="private four-stage series director (overrides --route)")
    parser.add_argument("--autopilot", action="store_true", help="let the base AI drive the stage for diagnostics")
    parser.add_argument("--builtin", action="store_true", help="private built-in overlay experiment; use PINYON_SHIFT_RALLY_BUILTIN_PROBE=1")
    parser.add_argument("--pace-notes", action="store_true", help="extract owned pace notes for private scheduling tests")
    parser.add_argument("--game-root", type=Path, default=ROOT / ".local/game/base")
    parser.add_argument("--extractor", type=Path,
                        default=ROOT / "out/build/win-amd64-release/pinyon_shift_fh1_archive_extract.exe")
    args = parser.parse_args()
    try:
        print(create(args))
        return 0
    except (OSError, ValueError, StopIteration, TypeError, sqlite3.Error, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
