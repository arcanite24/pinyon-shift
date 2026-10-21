#!/usr/bin/env python3
"""Build a private, base-disc Rally free-roam qualification seed from owned inputs.

This is an initial-placement probe, not the player-facing travel feature. It
always places the car at an owned stage start; it cannot qualify save/resume
or return to Colorado. The pinned input seed, DLC and disc are only read.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import importlib.util

ROOT = Path(__file__).resolve().parents[1]


def tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assets = tool("prepare-fh1-rally")
MOD = "rally_freeroam_probe"


def free_roam_database(database: Path, merge: Path) -> int:
    """Use the owned route-zero descriptor, retaining every other base track."""
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("ATTACH DATABASE ? AS rally", (str(merge),))
        for table in ("Environments", "Tracks"):
            base_columns = [row[1:3] for row in db.execute(f"PRAGMA main.table_info({table})")]
            owned_columns = [row[1:3] for row in db.execute(f"PRAGMA rally.table_info({table})")]
            if base_columns != owned_columns:
                raise ValueError("Rally and base database schemas differ")
        rows = db.execute("SELECT * FROM rally.Tracks WHERE MediaName='ColoradoDirt' "
                          "AND DevName='DirtFreeRoam' AND RouteId=0").fetchall()
        if len(rows) != 1 or db.execute("SELECT COUNT(*) FROM main.Tracks WHERE id=317").fetchone()[0] != 1:
            raise ValueError("expected one owned Rally free-roam track and base track 317")
        columns = [row[1] for row in db.execute("PRAGMA main.table_info(Tracks)")]
        row = dict(zip(columns, rows[0]))
        source_id = row["id"]
        for table in ("Environments", "Tracks"):
            db.execute(f"INSERT OR REPLACE INTO main.{table} SELECT * FROM rally.{table}")
        row["id"] = 317
        db.execute("INSERT OR REPLACE INTO main.Tracks VALUES (" + ",".join("?" for _ in row) + ")", tuple(row.values()))
        return source_id


def start_transform(route: bytes) -> dict[str, str]:
    transform = ET.fromstring(route).find("./NamedTransforms/NamedTransform[@name='start_location_00']/Transform")
    if transform is None:
        raise ValueError("owned stage has no start transform")
    values = [float(transform.attrib[key]) for key in ("pos.x", "pos.y", "pos.z", "facing.x", "facing.z")]
    if not all(math.isfinite(value) for value in values) or math.hypot(*values[3:]) < 0.5:
        raise ValueError("invalid owned start transform")
    return dict(zip(("x", "y", "z", "rotation"), map(str, (*values[:3], math.degrees(math.atan2(*values[3:])) % 360))))


def place_initial_car(flow: bytes, transform: dict[str, str]) -> bytes:
    root = ET.fromstring(flow)
    node = root.find("State[@id='setup_free_roam']/Node[@id='place_car']")
    if node is None or node.get("state") != "global.restore_car_position" or root.find("State[@id='pinyon_rally_spawn']") is not None:
        raise ValueError("unsupported base free-roam placement flow")
    node.set("state", "pinyon_rally_spawn")
    state = ET.SubElement(root, "State", id="pinyon_rally_spawn")
    ET.SubElement(state, "Entry", id="enter", target=".exit")
    ET.SubElement(state, "Exit", id="exit")
    ET.SubElement(state, "Behaviour", id="CPlaceCar", **transform)
    return ET.tostring(root, encoding="utf-8")


def verify_seed(source: Path) -> None:
    manifest = json.loads((source / "seed.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "pinyon-shift.render-seed.v1" or not manifest.get("profiles"):
        raise ValueError("a pinned render seed with profile hashes is required")
    for relative, digest in manifest["profiles"].items():
        path = (source / relative).resolve()
        if not path.is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest().upper() != digest.upper():
            raise ValueError("pinned profile has changed or escapes the seed")


def create(args) -> Path:
    source, output, game, owned = (path.resolve() for path in (args.seed, args.output, args.game_root, args.dlc_state))
    protected = [source, game, owned]
    if os.environ.get("LOCALAPPDATA"):
        protected.append((Path(os.environ["LOCALAPPDATA"]) / "PinyonShift").resolve())
    if output.exists() or any(output.is_relative_to(path) for path in protected):
        raise ValueError("choose a new private output outside the seed, disc, DLC state and AppData")
    verify_seed(source)
    versions = tool("title-update-profile")
    if (source / "title-update-v4").exists() or any(
            versions.profile_version(profile) == "v4" for profile in versions.profiles(source)):
        raise ValueError("this initial-placement probe supports base-disc seeds only")
    assets.verify_base(game)
    content, package, record = assets.dlc.verified_content(owned, assets.RALLY, require_enabled=True)
    runner, archive = tool("run-fh1-render-test"), tool("patch-fh1-archive")
    # Publish only a complete seed; failed extraction leaves no launchable output.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rally-freeroam-", dir=assets.dlc.long_path(output.parent)) as temporary:
        staged = Path(temporary) / "seed"
        runner.prepare_isolated_state(source, staged)
        staged = assets.dlc.long_path(staged)
        enabled, disabled, header = assets.dlc.package_paths(staged, assets.RALLY)
        if enabled.exists() or disabled.exists():
            _, pinned_package, _ = assets.dlc.verified_content(staged, assets.RALLY, require_enabled=True)
            if pinned_package["payload_sha256"] != package["payload_sha256"]:
                raise ValueError("seed and owned Rally payloads differ")
        else:
            enabled.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(content, enabled, copy_function=runner.link_or_copy)
            _, _, original_header = assets.dlc.package_paths(assets.dlc.long_path(owned), assets.RALLY)
            header.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original_header, header)
            (staged / "dlc").mkdir(exist_ok=True)
            assets.dlc.write_json(staged / "dlc" / (assets.RALLY + ".json"), record)
        mod = staged / "mods" / MOD
        if mod.exists():
            raise ValueError("the seed already contains the Rally free-roam probe")
        media = mod / "game/media"
        shutil.copytree(content / "Media/DLCZips/1600_pri_65/Media", media)
        reference = Path(temporary) / "reference"
        reference.mkdir()

        def extract(container, member, name):
            target = reference / name
            subprocess.run([str(args.extractor.resolve()), "--archive-member", str(container), member, str(target)],
                           check=True, capture_output=True, text=True)
            return target

        rally_archive = content / "Media/DLCZips/1600_pri_65.zip"
        merge = extract(rally_archive, "media/db/patch/1600000_merge.slt", "rally.slt")
        database = media / "db/gamedb.slt"
        database.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(assets.disc_path(game, "media/db/gamedb.slt"), database)
        track_id = free_roam_database(database, merge)
        route = extract(rally_archive, "media/Tracks/ColoradoDirt/Ribbon_00/TrackRoute001.xml", "start.xml")
        spawn = start_transform(route.read_bytes())
        modes = assets.disc_path(game, "media/gamemodes.zip")
        flow = extract(modes, "game_free_roam_flow.xml", "free-roam.xml").read_bytes()
        archive.patch_archive(modes, media / "gamemodes.zip", {"game_free_roam_flow.xml": place_initial_car(flow, spawn)})
        (mod / "mod.toml").write_text(f'name = "{MOD}"\nversion = "0.1.0"\nabi = 1\nprofile = "rally-probe"\n', encoding="utf-8")
        # Explicitly seed this dedicated profile; a named mod profile otherwise starts new.
        profile = staged / "user-rally-probe"
        if profile.exists():
            raise ValueError("use an unmodified source seed without a previous Rally probe profile")
        shutil.copytree(staged / "user", profile, ignore=runner.skip_private_content)
        patches = tool("build-mod-patches")
        patches.set_enabled_mods(staged / "config/pinyon_shift.toml", [MOD])
        runner.seed_fh1_shader_storage(source, staged)
        runner.seed_fh1_pipeline_prewarm(source, staged)
        receipt = dict(diagnostic_only=True, initial_placement_only=True, source_seed=str(source),
                       package_id=assets.RALLY, payload_sha256=package["payload_sha256"],
                       owned_track_id=track_id, load_track_id=317, spawn=spawn,
                       unqualified=["fast travel entry/return", "save/reload", "traffic", "minimap", "collectibles", "20-minute drive", "v4"])
        (staged / "rally-freeroam-probe.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        assets.dlc.verified_content(staged, assets.RALLY, require_enabled=True)
        verify_seed(source)
        shutil.copy2(source / "seed.json", staged / "seed.json")
        staged.rename(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--dlc-state", type=Path, required=True, help="state with enabled, verified owned Rally")
    parser.add_argument("--output", type=Path, required=True, help="new private qualification seed")
    parser.add_argument("--game-root", type=Path, default=ROOT / ".local/game/base")
    parser.add_argument("--extractor", type=Path, default=ROOT / "out/build/win-amd64-release/pinyon_shift_fh1_archive_extract.exe")
    try:
        print(create(parser.parse_args()))
        return 0
    except (OSError, ValueError, KeyError, ET.ParseError, sqlite3.Error, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
