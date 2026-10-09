#!/usr/bin/env python3
"""Prepare owned Rally assets and entry activities without changing source files or saves."""
from __future__ import annotations

import argparse
import copy
from contextlib import closing
import hashlib
import json
import math
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
import xml.etree.ElementTree as ET

import importlib.util
ROOT = Path(__file__).resolve().parents[1]
def tool(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

dlc = tool("manage-fh1-dlc")
RALLY = dlc.RALLY
STAGE_ROUTES = (*range(1, 22), *range(41, 48))
SERIES_ROUTES = ((11, 10, 12, 44), (13, 14, 15, 45), (4, 5, 6, 42),
                 (19, 20, 21, 47), (7, 8, 9, 43), (16, 17, 18, 46), (1, 2, 3, 41))
# Native CarClasses IDs: A, S, B, A, B, S, R3, in championship order.
SERIES_TARGET_CLASSES = (5, 6, 4, 5, 4, 6, 7)


def pace_notes(routes: dict[int, bytes], audio_xml: bytes) -> str:
    """Convert owned XML into private runtime metadata; never ship its contents."""
    audio = {}
    for event in ET.fromstring(audio_xml).findall("event"):
        name = event.attrib["play"]
        if name in audio:
            raise ValueError("duplicate co-driver sample")
        audio[name] = {key: event.attrib[key] for key in ("group", "cue", "icon")}
    text = "version = 1\n"
    for route, xml in routes.items():
        if route not in STAGE_ROUTES:
            raise ValueError("invalid pace-note route")
        calls = ET.fromstring(xml).findall("./RallyCalls/RallyCall")
        if not calls:
            raise ValueError("route contains no pace notes")
        for call in calls:
            name = call.attrib["name"]
            width = float(call.attrib["width"])
            transform = call.find("Transform")
            position = [float(transform.attrib[f"pos.{axis}"]) for axis in "xyz"]
            facing = [float(transform.attrib[f"facing.{axis}"]) for axis in "xyz"]
            samples = [sample.attrib["id"] for sample in call.findall("./Samples/Sample")]
            if (not name or not math.isfinite(width) or width <= 0 or
                    not all(math.isfinite(value) for value in (*position, *facing)) or
                    abs(sum(value * value for value in facing) - 1) > 0.001 or
                    not samples or len(samples) != int(call.attrib["numSamples"]) or
                    any(sample not in audio for sample in samples)):
                raise ValueError("invalid authored pace note")
            text += (f"\n[[calls]]\nroute = {route}\nname = {json.dumps(name)}\n"
                     f"width = {width!r}\nposition = {position!r}\nfacing = {facing!r}\n")
            for sample in samples:
                text += "[[calls.samples]]\n" + "".join(
                    f"{key} = {json.dumps(value)}\n" for key, value in audio[sample].items())
    return text


def add_stage(db: sqlite3.Connection, route: int, event_name: str = "RALLY_PROBE") -> dict:
    """Use new IDs so the normal DLC merge cannot restore Rally-only flags."""
    if route not in STAGE_ROUTES:
        raise ValueError("choose a Rally stage route (1–21 or 41–47)")
    db.row_factory = sqlite3.Row
    track = dict(db.execute('SELECT * FROM Tracks WHERE MediaName=? AND RouteId=?',
                            ("ColoradoDirt", route)).fetchone())
    track["id"] = db.execute("SELECT MAX(id)+1 FROM Tracks").fetchone()[0]
    track.update(RibbonConfiguration=2, NumSplitPoints=2)
    event = dict(db.execute('SELECT * FROM Events WHERE HorizonEventID="FR06"').fetchone())
    event["Id"] = db.execute("SELECT MAX(Id)+1 FROM Events").fetchone()[0]
    # Keep existing localized UI references until the real Rally UI is ported.
    event.update(HorizonEventID=event_name, NumberOfDrivers=0,
                 PlayerGridPosition=0, NemesisGridPosition=0, CashPrize=0,
                 UnlockPointsReq=0, Level=0,
                 TargetClass=next(target for routes, target in zip(SERIES_ROUTES, SERIES_TARGET_CLASSES)
                                  if route in routes))
    race = dict(db.execute('SELECT * FROM Races WHERE HorizonEventID="FR06"').fetchone())
    race.update(Id=db.execute("SELECT MAX(Id)+1 FROM Races").fetchone()[0],
                EventId=event["Id"], HorizonEventID=event["HorizonEventID"],
                TrackId=track["id"], NumLaps=1)
    for table, row in (("Tracks", track), ("Events", event), ("Races", race)):
        db.execute(f'INSERT INTO {table} (' + ",".join(row) + ') VALUES (' +
                   ",".join("?" for _ in row) + ')', tuple(row.values()))
    for table in ("EventUIColors", "Event_Music", "EventRecommendedCars"):
        for original in db.execute(f"SELECT * FROM {table} WHERE EventId=43").fetchall():
            row = dict(original)
            row[next(key for key in row if key.lower() == "eventid")] = event["Id"]
            db.execute(f'INSERT INTO {table} (' + ",".join(row) + ') VALUES (' +
                       ",".join("?" for _ in row) + ')', tuple(row.values()))
    # The base selector compiles this supported record into a class ceiling.
    # Rally-upgrade eligibility requires a separate port; do not insert the
    # update-only restriction flag here and silently treat it as supported.
    restriction = db.execute("SELECT * FROM EventRestrictions WHERE EventID=43 AND BucketId=0").fetchone()
    if restriction is None or restriction["Value"] != "0000000004":
        raise ValueError("base class restriction contract changed")
    restriction = dict(restriction)
    restriction.update(ID=db.execute("SELECT MAX(ID)+1 FROM EventRestrictions").fetchone()[0], EventID=event["Id"])
    db.execute('INSERT INTO EventRestrictions (' + ",".join(restriction) + ') VALUES (' +
               ",".join("?" for _ in restriction) + ')', tuple(restriction.values()))
    return dict(event_id=event["Id"], horizon_event_id=event["HorizonEventID"],
                race_id=race["Id"], track_id=track["id"], route=route)

SCHEMA = "pinyon-shift.rally-preparation.v1"

# Keys in the owned Events.str tables, in authored championship order.
SERIES_NAME_KEYS = (4783, 4911, 5039, 4143, 4271, 4399, 4527)
STAGE_NAME_KEYS = ((53679, 54831, 54959, 53804), (37423, 37551, 37679, 53932),
                   (37807, 36911, 37039, 54060), (37167, 37295, 38447, 54188),
                   (38575, 21039, 21167, 53292), (21295, 21423, 20527, 53420),
                   (20655, 20783, 20911, 53548))

def event_string(key: int) -> str:
    return f"_&{0x0C150000 | key}"

def championship_entries(activities: bytes, owned: bytes, native_menu: bool = False) -> bytes:
    """Add the seven owned activation locations without changing base activities."""
    root, locations = ET.fromstring(activities), ET.fromstring(owned)
    for id, routes in enumerate(SERIES_ROUTES, 1):
        location = locations.find(f"Activity[@name='MS_RALLY_{id:02}']/TriggerZone")
        if location is None or any(not math.isfinite(float(location.attrib[f'position.{axis}'])) for axis in ('x', 'z')):
            raise ValueError("missing or invalid owned Rally activation location")
        name = f"horizon_rally_{id:02}"
        if root.find(f"Activity[@name='{name}']") is not None:
            raise ValueError("Rally activity already exists")
        activity = ET.SubElement(root, "Activity", type="ActivityGeneric", name=name)
        group = ET.SubElement(activity, "StateGroup", id=name)
        state = ET.SubElement(group, "State", id="Root")
        if native_menu:
            ET.SubElement(state, "Entry", id="enter", target="remove_hud.enter")
            ET.SubElement(state, "Exit", id="exit")
            ET.SubElement(state, "Behaviour", id="CGameControlWrapper")
            ET.SubElement(state, "Behaviour", id="CDisablePlayerCarControlsWrapper")
            nodes = (
                ("remove_hud", "global.show_empty_screen", "enter", {"exit": "prepare.enter"}),
                ("prepare", "InGameUI.enter", "enter", {"exit": "hub.enter"}),
                ("hub", "UIShowScreens.ShowCareerStreetRaceSelect", "enter",
                 {"okCareer": "car_select.enter", "selectCar": "car_select.enter",
                  "okRivals": "close.enter", "return": "close.enter"}),
                ("car_select", "UIShowScreens.ShowRegisterEventCarScreen", "enter",
                 {"next": "close_for_loading.enterForLoading", "back": "hub.enter", "buyCar": "hub.enter"}),
                ("close", "InGameUI.exit", "enter", {"exit": ".exit"}),
                ("close_for_loading", "InGameUI.exit", "enterForLoading", {"exit": "load_selected.enter"}),
                ("load_selected", "load_selected", "enter", {}),
            )
            for node_id, node_state, entry, exits in nodes:
                node = ET.SubElement(state, "Node", id=node_id, state=node_state)
                ET.SubElement(node, "Entry", id=entry)
                for exit_id, target in exits.items():
                    ET.SubElement(node, "Exit", id=exit_id, target=target)
            load = ET.SubElement(group, "State", id="load_selected")
            ET.SubElement(load, "Entry", id="enter")
            behavior = ET.SubElement(load, "Behaviour", id="CLoadIntoCareerRace")
        else:
            ET.SubElement(state, "Entry", id="enter")
            behavior = ET.SubElement(state, "Behaviour", id="CLoadIntoCareerRace", event_id=f"RALLY_STAGE_{routes[0]:02}")
        ET.SubElement(behavior, "Attribute", id="resource_package", value="CareerLoading")
        trigger = copy.deepcopy(location)
        trigger.set("name", name)
        trigger.set("prompt", event_string(SERIES_NAME_KEYS[id - 1]))
        trigger.set("mapDescription", event_string(SERIES_NAME_KEYS[id - 1]))
        # The base map has no Rally icon; retain its known activity marker.
        trigger.set("mapTag", "mediacentertodo")
        activity.append(trigger)
    return ET.tostring(root, encoding="utf-8")

def next_stage(flow: bytes, event_name: str) -> bytes:
    """Keep native retirement/restore paths; the loader guards base events."""
    root = ET.fromstring(flow)
    postrace = root.find("State[@id='postrace_internal']")
    postrace.find("Node[@id='postrace_rivals']/Exit[@id='quit']").set("target", "rally_black_out.enter")
    for original, name, target in (("black_out", "rally_black_out", "rally_postrace_cleanup.enter"),
                                  ("postrace_cleanup", "rally_postrace_cleanup", "rally_load_next_stage.enter")):
        node = copy.deepcopy(postrace.find(f"Node[@id='{original}']"))
        node.set("id", name)
        node.find("Exit").set("target", target)
        postrace.append(node)
    node = ET.SubElement(postrace, "Node", id="rally_load_next_stage", state="rally_load_next_stage")
    ET.SubElement(node, "Entry", id="enter")
    load = copy.deepcopy(root.find("State[@id='load_back_to_free_roam']"))
    load.set("id", "rally_load_next_stage")
    load.find("Node[@id='load_into_free_roam']").set("state", "rally_next_stage")
    root.append(load)
    state = ET.SubElement(root, "State", id="rally_next_stage")
    ET.SubElement(state, "Entry", id="enter")
    behavior = ET.SubElement(state, "Behaviour", id="CLoadIntoCareerRace", event_id=event_name)
    ET.SubElement(behavior, "Attribute", id="resource_package", value="CareerLoading")
    return ET.tostring(root, encoding="utf-8")

def prepare_upgrade_data(db: sqlite3.Connection) -> None:
    """Port the missing Rally levels using the pinned base's native tyre curves."""
    if db.execute("SELECT COUNT(*) FROM List_UpgradeTireCompound WHERE TireCompoundID=9").fetchone()[0]:
        raise ValueError("base cars already reference the reserved Rally compound")
    cursor = db.execute("SELECT * FROM List_TireCompound WHERE TireCompoundID=4")
    compound = dict(zip((c[0] for c in cursor.description), cursor.fetchone()))
    compound.update(TireCompoundID=9,
        DisplayName=db.execute("SELECT DisplayName FROM List_TireCompound WHERE TireCompoundID=9").fetchone()[0],
        TorqueFreeLatFrictionScale=1.87, TorqueFreeLongFrictionScaleBrake=1.9,
        TorqueFreeLongFrictionScaleAccel0=1.15, TorqueFreeLongFrictionScaleAccel1=1.25,
        FrictionMultiCurveLateralID=9, FrictionMultiCurveLongitudinalID=10)
    db.execute(f'INSERT OR REPLACE INTO List_TireCompound ({",".join(compound)}) '
               f'VALUES ({",".join("?" for _ in compound)})', tuple(compound.values()))
    # Rally tyres retain the car's race-tyre mass/aero data and cost 10,000.
    # The factory-race Ferrari 599XX has no Rally conversion on this base.
    db.execute("INSERT INTO List_UpgradeTireCompound "
        "SELECT Ordinal*1000+5,Ordinal,5,0,9,ManufacturerID,10000,"
        "MassDiff,DragScale,WindInstabilityScale FROM List_UpgradeTireCompound "
        "WHERE Level=3 AND Ordinal!=1171")
    # Reuse base icons. The authored parts/geometry still come from owned DLC.
    for id, level, stock_id, name, description in (
        (268, 5, 80, 0x562F, 0x6723), (271, 4, 50, 0x12AF, 0x23A3),
        (272, 4, 58, 0x132F, 0x2223)):
        db.execute("INSERT OR REPLACE INTO Upgrades "
            "SELECT ?,TypeId,IsException,?, ?, ?,IconPath,ImagePath FROM Upgrades WHERE id=?",
            (id, f"_&{0x70910000 | name}", level, f"_&{0x70910000 | description}", stock_id))


def upgrade_strings(language: str) -> dict[int, str]:
    if language in ("ES", "MX"):
        text = ("Neumáticos de rally", "Neumáticos para mejorar el agarre en superficies sueltas.",
                "Muelles y amortiguadores de rally", "Suspensión para absorber los baches en superficies irregulares.",
                "Transmisión de rally", "Caja de cambios con relaciones cortas para rally.")
    else:
        text = ("Rally Tire Compound", "Tyres for improved grip on loose surfaces.",
                "Rally Springs and Dampers", "Suspension for absorbing bumps on rough surfaces.",
                "Rally Transmission", "A gearbox with short ratios for rally driving.")
    return dict(zip((0x562F, 0x6723, 0x12AF, 0x23A3, 0x132F, 0x2223), text))


def prepare_entry(content: Path, game: Path, extractor: Path, output: Path, stages: list[dict],
                  native_menu: bool = False) -> None:
    archive, strings = tool("patch-fh1-archive"), tool("fh1-strings")
    reference = output / "reference"
    def extract(source, member, name):
        target = reference / name
        subprocess.run([str(extractor), "--archive-member", str(source), member, str(target)],
                       check=True, capture_output=True, text=True)
        return target.read_bytes()
    modes = game / "media/gamemodes.zip"
    activities = extract(modes, "Colorado/activities.xml", "base-activities.xml")
    flow = extract(modes, "game_festival_race_flow.xml", "base-race-flow.xml")
    owned = content / "Media/DLCZips/1600_pri_65/Media/gamemodes/ColoradoDirt/rally_event_activations.xml"
    archive.patch_archive(modes, output / "game/media/gamemodes.zip", {
        "Colorado/activities.xml": championship_entries(activities, owned.read_bytes(), native_menu),
        "game_festival_race_flow.xml": next_stage(flow, "RALLY_NEXT")})
    # Base ticket binding chooses a folder from the supported event style.
    # Keep the owned artwork intact and use reserved names for both base UIs.
    tickets = output / "game/media/UI/Textures/Horizon/EventTickets"
    for series in range(1, 8):
        source = tickets / "RallyTickets" / f"{series:03}.xds"
        for folder in ("FestivalRaces", "StreetRaces"):
            destination = tickets / folder / f"RALLY_{series:02}.xds"
            if destination.exists():
                raise ValueError("reserved Rally ticket artwork already exists")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    localized = content / "Media/DLCZips/StringTables_pri_1750.zip"
    languages = [p for p in (game / "media/StringTables").glob("*.zip") if p.stem not in ("DEV", "LOC")]
    if not languages or not any(p.stem == "EN" for p in languages):
        raise ValueError("base-disc localized string tables are missing")
    for source in languages:
        language = source.stem
        data = extract(localized, f"{language}/Events.str", f"rally-events-{language}.str")
        stock = extract(source, "Events.str", f"base-events-{language}.str")
        data = strings.merge_preserving_base(stock, data)
        replacement = dict(strings.parse(data))
        if any(not replacement.get(key) for keys in STAGE_NAME_KEYS for key in keys):
            raise ValueError(f"owned Rally stage names are incomplete: {language}")
        destination = output / "game/media/StringTables" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        upgrades = extract(source, "Upgrades.str", f"base-upgrades-{language}.str")
        upgrades = strings.replace_strings(upgrades, upgrade_strings(language))
        replacements = {"Events.str": data, "Upgrades.str": upgrades}
        # Native event tickets also resolve the owned route and region labels.
        # Preserve every base label when using the DLC's lookup dictionaries.
        for table in ("Tracks", "Environments"):
            stock = extract(source, f"{table}.str", f"base-{table}-{language}.str")
            owned_table = extract(localized, f"{language}/{table}.str", f"rally-{table}-{language}.str")
            replacements[f"{table}.str"] = strings.merge_preserving_base(stock, owned_table)
        archive.patch_archive(source, destination, replacements)
    with closing(sqlite3.connect(output / "game/media/db/gamedb.slt")) as db, db:
        for stage in stages:
            id, index = next((id, routes.index(stage["route"])) for id, routes in enumerate(SERIES_ROUTES)
                             if stage["route"] in routes)
            name = event_string(STAGE_NAME_KEYS[id][index])
            db.execute("UPDATE Events SET Name=?, ShortName=?, EventTicket=? WHERE Id=?",
                       (name, name, f"RALLY_{id + 1:02}", stage["event_id"]))
        if native_menu:
            db.row_factory = sqlite3.Row
            if db.execute("SELECT 1 FROM EventHubs WHERE Id=4").fetchone():
                raise ValueError("reserved Rally hub already exists")
            hub = dict(db.execute("SELECT * FROM EventHubs WHERE Id=1").fetchone())
            hub.update(Id=4, Name=event_string(5807), UnlockPointsReq=0)
            db.execute(f'INSERT INTO EventHubs ({",".join(hub)}) VALUES ({",".join("?" for _ in hub)})',
                       tuple(hub.values()))
            for series, routes in enumerate(SERIES_ROUTES, 1):
                stage = next(stage for stage in stages if stage["route"] == routes[0])
                label = event_string(SERIES_NAME_KEYS[series - 1])
                db.execute("UPDATE Events SET HubId=4, CareerEventStyle=2, Name=?, ShortName=? WHERE Id=?",
                           (label, label, stage["event_id"]))


def verify_base(game: Path) -> dict:
    manifest = json.loads((ROOT / "config/supported-dumps.json").read_text(encoding="utf-8"))
    base = next(d for d in manifest["dumps"] if d["id"] == "forza-horizon-usa-ms-2505-retail-base")
    for entry in (*base["executables"], *base["rally_adapter_inputs"]):
        path = game / entry["guest_path"]
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest().upper()
        if path.stat().st_size != entry["size_bytes"] or digest != entry["sha256"]:
            raise ValueError(f'Rally requires the verified base-disc input: {entry["guest_path"]}')
    return dict(dump_id=base["id"], inputs=base["executables"] + base["rally_adapter_inputs"])


def ground_finish_cameras(media: Path) -> None:
    """Resolve Rally finish targets against the base engine's loaded terrain."""
    for path in (media / "gamemodes/ColoradoDirt/Cutscenes/Tracks").glob("cutscenes_RALLY_*.xml"):
        tree = ET.parse(path)
        changed = False
        for cutscene in tree.getroot().findall("Cutscene"):
            if not (cutscene.get("name") or "").startswith("postrace_finishline_RALLY_"):
                continue
            targets = {camera.get("TargetName") for camera in cutscene.iter("Cam")}
            for node in cutscene.iter("EventTrigger"):
                if (node.get("id") == "CCutsceneCameraNodeTrigger" and
                        node.get("name") in targets and node.get("snapToGround") == "0"):
                    # Route 002's authored height is 12.51 m below native ground.
                    # Use the existing native ray query, preserving X/Z and animation.
                    node.set("snapToGround", "1")
                    changed = True
        if changed:
            tree.write(path, encoding="utf-8", xml_declaration=True)


def build_assets(content: Path, game: Path, extractor: Path, output: Path,
                 entries: list[tuple[int, str]], *, pace: bool = True) -> list[dict]:
    """Create a fresh derivative; entry and AI changes belong to the test builder."""
    routes = [route for route, _ in entries]
    names = [name for _, name in entries]
    if (not routes or len(set(routes)) != len(routes) or any(r not in STAGE_ROUTES for r in routes) or
            len(set(names)) != len(names) or any(not name or len(name) > 15 or
            any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name) for name in names)):
        raise ValueError("invalid Rally asset event mapping")
    if output.exists():
        raise ValueError("Rally assets require a fresh output")
    output.mkdir(parents=True)
    media = output / "game/media"
    shutil.copytree(content / "Media/DLCZips/1600_pri_65/Media", media)
    ground_finish_cameras(media)
    reference = output / "reference"
    reference.mkdir()
    archive = content / "Media/DLCZips/1600_pri_65.zip"
    def extract(member, filename):
        target = reference / filename
        subprocess.run([str(extractor), "--archive-member", str(archive), member, str(target)],
                       check=True, capture_output=True, text=True)
        return target
    merge = extract("media/db/patch/1600000_merge.slt", "rally.slt")
    database = media / "db/gamedb.slt"
    database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(game / "media/db/gamedb.slt", database)
    with closing(sqlite3.connect(database)) as db, db:
        prepare_upgrade_data(db)
        db.execute("ATTACH DATABASE ? AS rally", (str(merge),))
        for table in ("Environments", "Tracks"):
            db.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM rally.{table}")
        stages = [add_stage(db, route, name) for route, name in entries]
    if pace:
        xml = {route: extract(f"media/Tracks/ColoradoDirt/Ribbon_00/TrackRoute{route:03}.xml",
                              f"route-{route:03}.xml").read_bytes() for route in routes}
        audio = content / "Media/DLCZips/1600_pri_65/Media/audio/VO/CoDriverAudio.xml"
        (output / "rally-pace.toml").write_text(pace_notes(xml, audio.read_bytes()), encoding="utf-8")
    return stages


def artifact_digest(output: Path) -> str:
    files, _ = dlc.payload_catalog(output)
    files = [entry for entry in files if entry["path"] != "preparation.json"]
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest().upper()


def prepare(state: Path, game: Path, extractor: Path, *, native_menu: bool | None = None) -> dict:
    state, game = dlc.long_path(state), dlc.long_path(game)
    with dlc.mutation_lock(state):
        content, package, record = dlc.verified_content(state, RALLY, require_enabled=True)
        recipe = dict(schema=SCHEMA, package_id=RALLY, package_sha256=record["sha256"],
                      payload_sha256=package["payload_sha256"], header_sha256=record["header_sha256"],
                      base=verify_base(game), recipe_version=12)
        cache = state / "cache"
        output = cache / "rally_adapter"
        if cache.is_symlink() or output.is_symlink() or output.is_relative_to(game):
            raise ValueError("Rally cache must be separate from game inputs and symbolic links")
        previous = None
        if output.exists():
            try:
                previous = json.loads((output / "preparation.json").read_text())
            except (OSError, ValueError) as error:
                raise ValueError("existing Rally cache is unmanaged; keep it in place") from error
            if previous.get("schema") != SCHEMA:
                raise ValueError("existing Rally cache is unmanaged; keep it in place")
        # Preserve an explicitly selected experimental flow across normal
        # launch preflight; a caller can explicitly turn it off again.
        if native_menu is None:
            native_menu = bool(previous and previous.get("recipe", {}).get("native_menu", False))
        recipe["native_menu"] = native_menu
        if previous and previous.get("recipe") == recipe and previous.get("artifact_sha256") == artifact_digest(output):
            return previous | dict(reused=True)
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rally-build-", dir=cache) as temporary:
            staged = Path(temporary) / "adapter"
            stages = build_assets(content, game, extractor.resolve(), staged,
                                  [(r, f"RALLY_STAGE_{r:02}") for r in STAGE_ROUTES])
            mapping = "version = 4\n" + "".join(
                f'\n[[stages]]\nevent_id = {s["event_id"]}\nroute = {s["route"]}\n'
                f'event_name = "{s["horizon_event_id"]}"\n' for s in stages)
            (staged / "rally-stage.toml").write_text(mapping, encoding="utf-8")
            prepare_entry(content, game, extractor.resolve(), staged, stages, native_menu)
            prepared = dict(schema=SCHEMA, recipe=recipe, stages=stages,
                            artifact_sha256=artifact_digest(staged), entry_ready=True)
            dlc.write_json(staged / "preparation.json", prepared)
            retained = cache / ("rally_adapter.previous-" + uuid.uuid4().hex)
            if previous is not None:
                output.rename(retained)
            try:
                staged.rename(output)
            except OSError:
                if previous is not None:
                    retained.rename(output)
                raise
            # Keep only the copy just retained for recovery; each holds about
            # 1 GB of DLC media, and older ones are never used again.
            for stale in cache.glob("rally_adapter.previous-*"):
                if stale != retained and stale.is_dir():
                    shutil.rmtree(stale, ignore_errors=True)
        return prepared | dict(reused=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--extractor", type=Path, default=ROOT / "out/build/win-amd64-release/pinyon_shift_fh1_archive_extract.exe")
    parser.add_argument("--native-menu", action=argparse.BooleanOptionalAction, default=None,
                        help="prepare the experimental native Rally hub/car-selection flow")
    args = parser.parse_args()
    # An enabled mod that cannot run with Rally (the XE mod) hides it from
    # the title; leave the owned package and its cache untouched.
    patches = importlib.util.spec_from_file_location(
        "build_mod_patches", Path(__file__).with_name("build-mod-patches.py"))
    module = importlib.util.module_from_spec(patches)
    patches.loader.exec_module(module)
    hidden_by = module.hidden_dlc(args.state_root).get(RALLY)
    if hidden_by:
        print(json.dumps({"entry_ready": False, "hidden_by_mod": hidden_by}))
        return 0
    try:
        print(json.dumps(prepare(args.state_root, args.game_root, args.extractor, native_menu=args.native_menu)))
        return 0
    except (OSError, ValueError, KeyError, AttributeError, ET.ParseError, StopIteration, sqlite3.Error, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
