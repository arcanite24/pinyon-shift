"""Owned Rally preparation, atomic publication and immutable source/save boundaries."""
import contextlib
import hashlib
from contextlib import closing, ExitStack
import importlib.util
import io
import json
import shutil
import sqlite3
import subprocess
import struct
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("rally_prepare", Path(__file__).parents[1] / "prepare-fh1-rally.py")
rally = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rally)


class RallyPreparationTests(unittest.TestCase):
    def fixture(self, root):
        state, game = root / "state", root / "game"
        content, inactive, header = rally.dlc.package_paths(state, rally.RALLY)
        media = content / "Media/DLCZips/1600_pri_65/Media"
        tickets = media / "UI/Textures/Horizon/EventTickets/RallyTickets"
        tickets.mkdir(parents=True)
        for series in range(1, 8):
            (tickets / f"{series:03}.xds").write_bytes(f"owned ticket {series}".encode())
        (media / "audio/VO").mkdir(parents=True)
        (media / "audio/VO/CoDriverAudio.xml").write_bytes(
            b'<CoDriverAudio><event play="50" group="CoDriver/Distance" cue="50Distance" icon="None"/></CoDriverAudio>')
        cameras = media / "gamemodes/ColoradoDirt/Cutscenes/Tracks/cutscenes_RALLY_002.xml"
        cameras.parent.mkdir(parents=True)
        cameras.write_text('''<Cutscenes>
            <Cutscene name="postrace_finishline_RALLY_002">
                <Cam TargetName="CameraTargetNode_0"><Key y="1.18"/></Cam>
                <EventTrigger id="CCutsceneCameraNodeTrigger" name="CameraTargetNode_0"
                    snapToGround="0" x="1" y="315.62" z="3" rotation="28.49" parent=""/>
                <EventTrigger id="CCutsceneCameraNodeTrigger" name="Unused" snapToGround="0"/>
            </Cutscene>
            <Cutscene name="prerace_RALLY_002"><Cam TargetName="CameraTargetNode_0"/>
                <EventTrigger id="CCutsceneCameraNodeTrigger" name="CameraTargetNode_0" snapToGround="0"/>
            </Cutscene>
            <Cutscene name="postrace_finishline_BASE"><Cam TargetName="CameraTargetNode_0"/>
                <EventTrigger id="CCutsceneCameraNodeTrigger" name="CameraTargetNode_0" snapToGround="0"/>
            </Cutscene></Cutscenes>''')
        (content / "Media/DLCZips/1600_pri_65.zip").write_bytes(b"archive")
        database = game / "media/db/gamedb.slt"
        database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database)) as db, db:
            db.executescript('''
                CREATE TABLE Environments (id INTEGER PRIMARY KEY, Name TEXT);
                INSERT INTO Environments VALUES (1,'Colorado');
                CREATE TABLE Tracks (id INTEGER PRIMARY KEY, MediaName TEXT,
                    RouteId INTEGER, RibbonConfiguration INTEGER, NumSplitPoints INTEGER);
                INSERT INTO Tracks VALUES (134,'Colorado',1,2,2);
                CREATE TABLE Events (Id INTEGER PRIMARY KEY, HorizonEventID TEXT,
                    NumberOfDrivers INTEGER, PlayerGridPosition INTEGER,
                    NemesisGridPosition INTEGER, CashPrize INTEGER,
                    UnlockPointsReq INTEGER, Level INTEGER, Name TEXT, ShortName TEXT, TargetClass INTEGER,
                    EventTicket TEXT, HubId INTEGER, CareerEventStyle INTEGER);
                INSERT INTO Events VALUES (43,'FR06',7,7,3,6000,430,1,'base-name','base-name',5,'043',1,1);
                CREATE TABLE EventHubs (Id INTEGER PRIMARY KEY, Name TEXT, UnlockPointsReq INTEGER, Icon TEXT);
                INSERT INTO EventHubs VALUES (1,'base hub',310,'base-icon');
                CREATE TABLE EventRestrictions (ID INTEGER PRIMARY KEY, EventID INTEGER,
                    BucketId INTEGER, Value TEXT);
                INSERT INTO EventRestrictions VALUES (11,43,0,'0000000004');
                CREATE TABLE Races (Id INTEGER PRIMARY KEY, EventId INTEGER,
                    HorizonEventID TEXT, TrackId INTEGER, NumLaps INTEGER);
                INSERT INTO Races VALUES (42,43,'FR06',134,1);
                CREATE TABLE EventUIColors (EventId INTEGER, Color1 INTEGER);
                INSERT INTO EventUIColors VALUES (43,123);
                CREATE TABLE Event_Music (EventId INTEGER, TrackName TEXT);
                CREATE TABLE EventRecommendedCars (EventId INTEGER, CarId INTEGER);
                CREATE TABLE List_UpgradeTireCompound (Id INTEGER PRIMARY KEY, Ordinal INTEGER,
                    Level INTEGER, IsStock INTEGER, TireCompoundID INTEGER, ManufacturerID INTEGER,
                    Price INTEGER, MassDiff REAL, DragScale REAL, WindInstabilityScale REAL);
                INSERT INTO List_UpgradeTireCompound VALUES (1000,1,0,1,5,0,0,0,1,1);
                INSERT INTO List_UpgradeTireCompound VALUES (1500003,1500,3,0,8,2,10000,0.5,1.02,1.03);
                INSERT INTO List_UpgradeTireCompound VALUES (1020000,1020,3,1,8,0,0,0,1,1);
                INSERT INTO List_UpgradeTireCompound VALUES (1171000,1171,3,1,8,0,0,0,1,1);
                CREATE TABLE List_TireCompound (TireCompoundID INTEGER PRIMARY KEY, DisplayName TEXT,
                    TorqueFreeLatFrictionScale REAL, TorqueFreeLongFrictionScaleBrake REAL,
                    TorqueFreeLongFrictionScaleAccel0 REAL, TorqueFreeLongFrictionScaleAccel1 REAL,
                    FrictionMultiCurveLateralID INTEGER, FrictionMultiCurveLongitudinalID INTEGER,
                    FrictionWear REAL);
                INSERT INTO List_TireCompound VALUES (4,'high',1,1,1,1,7,8,0.00021);
                INSERT INTO List_TireCompound VALUES (9,'reserved',2,2,2,2,17,18,0.00025);
                CREATE TABLE Upgrades (id INTEGER PRIMARY KEY, TypeId TEXT, IsException INTEGER,
                    Name TEXT, Level INTEGER, Description TEXT, IconPath TEXT, ImagePath TEXT);
                INSERT INTO Upgrades VALUES (80,'21',0,'sport',2,'sport','tyre','tyre-lg');
                INSERT INTO Upgrades VALUES (50,'13',0,'race',3,'race','spring','spring-lg');
                INSERT INTO Upgrades VALUES (58,'15',0,'race',3,'race','gear','gear-lg');
                INSERT INTO Upgrades VALUES (268,'21',0,'drag',4,'drag','drag','drag-lg');
            ''')
        merge = root / "rally.slt"
        with closing(sqlite3.connect(merge)) as db, db:
            db.executescript('''CREATE TABLE Environments (id INTEGER PRIMARY KEY, Name TEXT);
                INSERT INTO Environments VALUES (2,'ColoradoDirt');
                CREATE TABLE Tracks (id INTEGER PRIMARY KEY, MediaName TEXT,
                    RouteId INTEGER, RibbonConfiguration INTEGER, NumSplitPoints INTEGER);''')
            db.executemany("INSERT INTO Tracks VALUES (?,?,?,?,?)",
                           [(1000+r,"ColoradoDirt",r,8,-1) for r in rally.STAGE_ROUTES])
        (game / "default.xex").write_bytes(b"base executable")
        activities = b'<ActivityManager><Activity name="festival_01"/></ActivityManager>'
        flow = b'''<StateGroup><State id="postrace_internal">
            <Node id="postrace_rivals"><Exit id="quit" target="black_out.enter"/></Node>
            <Node id="black_out"><Exit id="exit" target="postrace_cleanup.enter"/></Node>
            <Node id="postrace_cleanup"><Exit id="exit" target="load_back_to_free_roam.enter"/></Node>
            </State><State id="load_back_to_free_roam">
            <Node id="load_into_free_roam" state="global.load_into_free_roam"/></State></StateGroup>'''
        with zipfile.ZipFile(game / "media/gamemodes.zip", "w") as archive:
            archive.writestr("Colorado/activities.xml", activities)
            archive.writestr("game_festival_race_flow.xml", flow)
        owned_activities = media / "gamemodes/ColoradoDirt/rally_event_activations.xml"
        owned_activities.parent.mkdir(parents=True, exist_ok=True)
        owned_activities.write_text('<ActivityManager>' + ''.join(
            f'<Activity name="MS_RALLY_{id:02}"><TriggerZone position.x="{id}" position.z="{id * 2}" radius="25"/></Activity>'
            for id in range(1,8)) + '</ActivityManager>')
        def table(entries):
            pool, offsets = b"", b""
            for key, text in sorted(entries.items()):
                offsets += struct.pack(">HI", key, len(pool) // 2)
                pool += text.encode("utf-16-be") + b"\0\0"
            offsets += struct.pack(">HI", 0xffff, len(pool) // 2 - 1)
            chunk = struct.pack(">II", 8 + len(offsets) + len(pool), len(entries)) + offsets + pool
            return b"LSB2" + bytes(8) + struct.pack(">I", 24) + bytes(8) + chunk
        stock_strings = table({60001: "base event"})
        owned_strings = table({60001: "base event"} | {key: f"Rally {key}"
            for key in (*rally.SERIES_NAME_KEYS, *(key for keys in rally.STAGE_NAME_KEYS for key in keys))} |
            {53679: "The Rockies - Stage 1", 20655: "Red Rock - Stage 1"})
        string_root = game / "media/StringTables"
        string_root.mkdir()
        with zipfile.ZipFile(string_root / "EN.zip", "w") as archive:
            archive.writestr("Events.str", stock_strings)
            archive.writestr("Upgrades.str", stock_strings)
            archive.writestr("Tracks.str", stock_strings)
            archive.writestr("Environments.str", stock_strings)
        with zipfile.ZipFile(content / "Media/DLCZips/StringTables_pri_1750.zip", "w") as archive:
            archive.writestr("EN/Events.str", owned_strings)
            archive.writestr("EN/Tracks.str", table({60001: "changed base", 42: "Rally route"}))
            archive.writestr("EN/Environments.str", table({60001: "changed base", 43: "Rally region"}))
        entries = [dict(guest_path=p.relative_to(game).as_posix(), size_bytes=p.stat().st_size,
                        sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())
                   for p in (game / "default.xex", database, game / "media/gamemodes.zip")]
        dump = dict(id="forza-horizon-usa-ms-2505-retail-base", executables=entries[:1], rally_adapter_inputs=entries[1:])
        header.parent.mkdir(parents=True)
        header.write_bytes(bytes(328) + b"\1\0\0\0")
        _, digest = rally.dlc.payload_catalog(content)
        package = dict(package_id=rally.RALLY, payload_sha256=digest,
                       accepted=[dict(sha256="A"*64, license_mask="00000001")])
        (state / "dlc").mkdir()
        record = dict(package_id=rally.RALLY, sha256="A"*64, payload_sha256=digest,
                      header_sha256=hashlib.sha256(header.read_bytes()).hexdigest().upper(), license_mask="00000001")
        (state / "dlc" / (rally.RALLY + ".json")).write_text(json.dumps(record))
        save = state / "user/save-sentinel"
        save.write_bytes(b"never change this save")
        def extract(args, **kwargs):
            target = Path(args[-1])
            if args[-2].endswith(".slt"):
                shutil.copy2(merge, target)
            elif args[-2] == "Colorado/activities.xml":
                target.write_bytes(activities)
            elif args[-2] == "game_festival_race_flow.xml":
                target.write_bytes(flow)
            elif args[-2].endswith("Events.str"):
                target.write_bytes(owned_strings if "1750" in str(args[-3]) else stock_strings)
            elif args[-2] == "Upgrades.str":
                target.write_bytes(stock_strings)
            elif args[-2].endswith(("Tracks.str", "Environments.str")):
                with zipfile.ZipFile(args[-3]) as archive:
                    target.write_bytes(archive.read(args[-2]))
            else:
                target.write_bytes(b'<TrackRoute><RallyCalls><RallyCall name="gate" width="20" numSamples="1">'
                    b'<Samples><Sample id="50"/></Samples><Transform pos.x="1" pos.y="2" pos.z="3" '
                    b'facing.x="1" facing.y="0" facing.z="0"/></RallyCall></RallyCalls></TrackRoute>')
            return subprocess.CompletedProcess(args, 0, "", "")
        return state, game, content, save, dump, package, extract

    def mocks(self, dump, package, extract):
        # Pin a synthetic base catalog; the real verifier still hashes every input.
        original = Path.read_text
        def read(path, *args, **kwargs):
            if path == rally.ROOT / "config/supported-dumps.json":
                return json.dumps(dict(dumps=[dump]))
            return original(path, *args, **kwargs)
        return (patch.object(Path, "read_text", read),
                patch.object(rally.dlc, "catalog", return_value=dict(packages=[package])),
                patch.object(rally.dlc.subprocess, "check_output", return_value=b""),
                patch.object(rally.subprocess, "run", side_effect=extract))

    def test_all_routes_prepare_without_changing_base_events_flow_or_save(self):
        with tempfile.TemporaryDirectory() as directory:
            state, game, content, save, dump, package, extract = self.fixture(Path(directory))
            before = (game / "media/db/gamedb.slt").read_bytes()
            camera_path = Path("gamemodes/ColoradoDirt/Cutscenes/Tracks/cutscenes_RALLY_002.xml")
            owned_camera = content / "Media/DLCZips/1600_pri_65/Media" / camera_path
            camera_before = owned_camera.read_bytes()
            with ExitStack() as stack:
                for mock in self.mocks(dump, package, extract): stack.enter_context(mock)
                result = rally.prepare(state, game, Path("extractor"))
                self.assertTrue(result["entry_ready"])
                self.assertEqual([s["route"] for s in result["stages"]], list(rally.STAGE_ROUTES))
                output = state / "cache/rally_adapter"
                expected_camera = rally.ET.fromstring(camera_before)
                expected_camera.find(".//EventTrigger").set("snapToGround", "1")
                actual_camera = rally.ET.parse(output / "game/media" / camera_path).getroot()
                self.assertEqual(rally.ET.tostring(actual_camera), rally.ET.tostring(expected_camera))
                mapping = tomllib.loads((output / "rally-stage.toml").read_text())
                self.assertEqual(mapping["version"], 4)
                self.assertEqual(len(mapping["stages"]), 28)
                with closing(sqlite3.connect(output / "game/media/db/gamedb.slt")) as db:
                    self.assertEqual(db.execute("SELECT TorqueFreeLatFrictionScale,"
                        "TorqueFreeLongFrictionScaleBrake,FrictionMultiCurveLateralID,"
                        "FrictionMultiCurveLongitudinalID,FrictionWear FROM List_TireCompound "
                        "WHERE TireCompoundID=9").fetchone(), (1.87,1.9,9,10,0.00021))
                    self.assertEqual(db.execute("SELECT Name,Level FROM Upgrades WHERE id=268").fetchone(),
                        ("_&1888572975",5))
                    self.assertEqual(db.execute("SELECT Name,Level FROM Upgrades WHERE id=271").fetchone(),
                        ("_&1888555695",4))
                    self.assertEqual(db.execute("SELECT Name,Level FROM Upgrades WHERE id=272").fetchone(),
                        ("_&1888555823",4))
                    self.assertEqual(db.execute("SELECT Level FROM Upgrades WHERE id=80").fetchone(),(2,))
                    self.assertEqual(db.execute("SELECT * FROM List_UpgradeTireCompound WHERE Id=1500005").fetchone(),
                        (1500005,1500,5,0,9,2,10000,0.5,1.02,1.03))
                    self.assertEqual(db.execute("SELECT IsStock,Price FROM List_UpgradeTireCompound WHERE Id=1020005").fetchone(),
                        (0,10000))
                    self.assertEqual(db.execute("SELECT IsStock,Price FROM List_UpgradeTireCompound WHERE Id=1020000").fetchone(),
                        (1,0))
                    self.assertIsNone(db.execute("SELECT Id FROM List_UpgradeTireCompound WHERE Id=1171005").fetchone())
                    self.assertEqual(db.execute("SELECT TireCompoundID FROM List_UpgradeTireCompound WHERE Id=1000").fetchone(),(5,))
                    for stage in mapping["stages"]:
                        self.assertEqual(db.execute("SELECT HorizonEventID FROM Events WHERE Id=?",
                            (stage["event_id"],)).fetchone()[0], stage["event_name"])
                        id, index = next((id, routes.index(stage["route"])) for id, routes in enumerate(rally.SERIES_ROUTES)
                            if stage["route"] in routes)
                        self.assertEqual(db.execute("SELECT Name,ShortName FROM Events WHERE Id=?",
                            (stage["event_id"],)).fetchone(), (rally.event_string(rally.STAGE_NAME_KEYS[id][index]),) * 2)
                    self.assertEqual(db.execute("SELECT Name,ShortName FROM Events WHERE Id=43").fetchone(),
                        ("base-name", "base-name"))
                with zipfile.ZipFile(output / "game/media/gamemodes.zip") as archive:
                    entries = rally.ET.fromstring(archive.read("Colorado/activities.xml"))
                    self.assertEqual(len(entries.findall("Activity[@type='ActivityGeneric']")), 7)
                    self.assertIsNotNone(entries.find("Activity[@name='festival_01']"))
                    for id, routes in enumerate(rally.SERIES_ROUTES, 1):
                        activity = entries.find(f"Activity[@name='horizon_rally_{id:02}']")
                        self.assertEqual(activity.find(".//Behaviour").get("event_id"), f"RALLY_STAGE_{routes[0]:02}")
                        self.assertEqual(activity.find("TriggerZone").get("position.x"), str(id))
                self.assertFalse((state / "user-modded").exists())
                strings = rally.tool("fh1-strings")
                with zipfile.ZipFile(output / "game/media/StringTables/EN.zip") as archive:
                    event_labels = dict(strings.parse(archive.read("Events.str")))
                    for table, key, label in (("Tracks", 42, "Rally route"),
                                               ("Environments", 43, "Rally region")):
                        labels = dict(strings.parse(archive.read(f"{table}.str")))
                        self.assertEqual(labels[60001], "base event")
                        self.assertEqual(labels[key], label)
                with closing(sqlite3.connect(output / "game/media/db/gamedb.slt")) as db:
                    # Independent authored route labels catch swapping string
                    # groups while leaving the stage routes themselves correct.
                    for route, expected in ((11, "The Rockies - Stage 1"),
                                            (1, "Red Rock - Stage 1")):
                        stage = next(s for s in result["stages"] if s["route"] == route)
                        reference = db.execute("SELECT Name FROM Events WHERE Id=?",
                                               (stage["event_id"],)).fetchone()[0]
                        self.assertEqual(event_labels[int(reference[2:]) & 0xffff], expected)
                    targets = {route: (target, f"RALLY_{series:02}") for series, (routes, target) in enumerate((
                        ((11, 10, 12, 44), 5), ((13, 14, 15, 45), 6),
                        ((4, 5, 6, 42), 4), ((19, 20, 21, 47), 5),
                        ((7, 8, 9, 43), 4), ((16, 17, 18, 46), 6),
                        ((1, 2, 3, 41), 7)), 1) for route in routes}
                    for route, (target, ticket) in targets.items():
                        stage = next(s for s in result["stages"] if s["route"] == route)
                        self.assertEqual(db.execute("SELECT TargetClass FROM Events WHERE Id=?",
                            (stage["event_id"],)).fetchone(), (target,))
                        self.assertEqual(db.execute("SELECT BucketId,Value FROM EventRestrictions WHERE EventID=?",
                            (stage["event_id"],)).fetchall(), [(0, '0000000004')])
                        self.assertEqual(db.execute("SELECT EventTicket FROM Events WHERE Id=?",
                            (stage["event_id"],)).fetchone(), (ticket,))
                    self.assertEqual(db.execute("SELECT * FROM EventRestrictions WHERE EventID=43").fetchall(),
                                     [(11, 43, 0, '0000000004')])
                    self.assertEqual(db.execute("SELECT NumberOfDrivers,UnlockPointsReq FROM Events WHERE Id=43").fetchone(), (7,430))
                    self.assertEqual(db.execute("SELECT TrackId FROM Races WHERE Id=42").fetchone()[0],134)
                    self.assertEqual(db.execute("SELECT EventTicket FROM Events WHERE Id=43").fetchone(), ('043',))
                tickets = Path("UI/Textures/Horizon/EventTickets")
                for series in range(1, 8):
                    original = content / "Media/DLCZips/1600_pri_65/Media" / tickets / "RallyTickets" / f"{series:03}.xds"
                    self.assertEqual(original.read_bytes(), f"owned ticket {series}".encode())
                    for folder in ("FestivalRaces", "StreetRaces"):
                        self.assertEqual((output / "game/media" / tickets / folder / f"RALLY_{series:02}.xds").read_bytes(), original.read_bytes())
                calls = tomllib.loads((output / "rally-pace.toml").read_text())["calls"]
                self.assertEqual({c["route"] for c in calls}, set(rally.STAGE_ROUTES))
                with patch.object(rally, "build_assets", side_effect=AssertionError("rebuild on unchanged input")):
                    self.assertTrue(rally.prepare(state, game, Path("extractor"))["reused"])
            self.assertEqual((game / "media/db/gamedb.slt").read_bytes(), before)
            self.assertEqual(owned_camera.read_bytes(), camera_before)
            self.assertEqual(save.read_bytes(), b"never change this save")

    def test_bad_base_disabled_content_and_widened_licence_never_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            state, game, content, save, dump, package, extract = self.fixture(Path(directory))
            with ExitStack() as stack:
                for mock in self.mocks(dump, package, extract): stack.enter_context(mock)
                (game / "default.xex").write_bytes(b"wrong update")
                with self.assertRaisesRegex(ValueError, "base-disc input"):
                    rally.prepare(state, game, Path("extractor"))
                self.assertFalse((state / "cache").exists())
                (game / "default.xex").write_bytes(b"base executable")
                _, inactive, header = rally.dlc.package_paths(state, rally.RALLY)
                inactive.parent.mkdir(parents=True)
                content.rename(inactive)
                with self.assertRaisesRegex(ValueError, "enable"):
                    rally.prepare(state, game, Path("extractor"))
                inactive.rename(content)
                header.write_bytes(bytes(328) + b"\4\0\0\0")
                with self.assertRaisesRegex(ValueError, "licence changed"):
                    rally.prepare(state, game, Path("extractor"))
                self.assertFalse((state / "cache").exists())
                self.assertEqual(save.read_bytes(), b"never change this save")

    def test_invalid_owned_location_never_publishes_or_removes_base_activities(self):
        base = b'<ActivityManager><Activity name="base"/></ActivityManager>'
        for owned in (b'<ActivityManager/>', b'<ActivityManager><Activity name="MS_RALLY_01">'
                b'<TriggerZone position.x="nan" position.z="0"/></Activity></ActivityManager>'):
            with self.assertRaisesRegex(ValueError, "activation location"):
                rally.championship_entries(base, owned)
        self.assertEqual(base, b'<ActivityManager><Activity name="base"/></ActivityManager>')

    def test_native_menu_preparation_preserves_sources_and_survives_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            state, game, content, save, dump, package, extract = self.fixture(Path(directory))
            original = (game / 'media/db/gamedb.slt').read_bytes()
            with ExitStack() as stack:
                for mock in self.mocks(dump, package, extract): stack.enter_context(mock)
                result = rally.prepare(state, game, Path('extractor'), native_menu=True)
                self.assertTrue(result['recipe']['native_menu'])
                output = state / 'cache/rally_adapter'
                with closing(sqlite3.connect(output / 'game/media/db/gamedb.slt')) as db:
                    rows = db.execute('SELECT HorizonEventID, CareerEventStyle FROM Events WHERE HubId=4').fetchall()
                    self.assertEqual(set(rows), {(f'RALLY_STAGE_{routes[0]:02}', 2) for routes in rally.SERIES_ROUTES})
                    self.assertEqual(db.execute('SELECT Name,UnlockPointsReq FROM EventHubs WHERE Id=1').fetchone(), ('base hub',310))
                    self.assertEqual(db.execute('SELECT Name,UnlockPointsReq FROM EventHubs WHERE Id=4').fetchone(), (rally.event_string(5807),0))
                with zipfile.ZipFile(output / 'game/media/gamemodes.zip') as archive:
                    entries = rally.ET.fromstring(archive.read('Colorado/activities.xml'))
                    for series in range(1,8):
                        activity = entries.find(f"Activity[@name='horizon_rally_{series:02}']")
                        flow = activity.find("StateGroup/State[@id='Root']")
                        self.assertEqual(flow.find("Node[@id='hub']/Exit[@id='okCareer']").get('target'), 'car_select.enter')
                        self.assertEqual(flow.find("Node[@id='car_select']/Exit[@id='back']").get('target'), 'hub.enter')
                        self.assertEqual(flow.find("Node[@id='close']/Exit").get('target'), '.exit')
                        self.assertEqual(flow.find("Node[@id='close_for_loading']/Exit").get('target'), 'load_selected.enter')
                        load = activity.find("StateGroup/State[@id='load_selected']/Behaviour")
                        self.assertEqual(load.get('id'), 'CLoadIntoCareerRace')
                        self.assertIsNone(load.get('event_id'))
                        self.assertEqual(activity.find('TriggerZone').get('position.x'), str(series))
                self.assertTrue(rally.prepare(state, game, Path('extractor'))['reused'])
                reverted = rally.prepare(state, game, Path('extractor'), native_menu=False)
                self.assertFalse(reverted['recipe']['native_menu'])
                self.assertFalse(reverted['reused'])
                self.assertEqual((game / 'media/db/gamedb.slt').read_bytes(), original)
                self.assertEqual(save.read_bytes(), b'never change this save')

    def test_launcher_enable_prepares_rally_and_failure_leaves_recoverable_content(self):
        with tempfile.TemporaryDirectory() as directory:
            state, game, content, save, dump, package, extract = self.fixture(Path(directory))
            with ExitStack() as stack:
                for mock in self.mocks(dump, package, extract): stack.enter_context(mock)
                rally.dlc.set_enabled(state, rally.RALLY, False)
                argv = ["manage-fh1-dlc.py", "enable", "--state-root", str(state),
                        "--package-id", rally.RALLY, "--game-root", str(game)]
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(rally.dlc.sys, "argv", argv), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                        patch.object(rally.dlc.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "interrupted preparation")):
                    self.assertEqual(rally.dlc.main(), 1)
                self.assertIn("Rally is enabled, but asset preparation failed", stderr.getvalue())
                self.assertTrue(content.is_dir())
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(save.read_bytes(), b"never change this save")
                # A repeated enable can prepare/repair the cache. The list reports
                # assets on disk without making a gameplay-ready claim.
                rally.prepare(state, game, Path("extractor"))
                stdout = io.StringIO()
                with patch.object(rally.dlc.sys, "argv", argv), contextlib.redirect_stdout(stdout), \
                        patch.object(rally.dlc.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "{}", "")) as child:
                    self.assertEqual(rally.dlc.main(), 0)
                command = child.call_args.args[0]
                self.assertIn("--game-root", command)
                result = json.loads(stdout.getvalue())["packages"][0]
                self.assertTrue(result["enabled"] and result["rally_assets_cached"])
                self.assertEqual(result["status"], "gameplay_unverified")
                rally.dlc.set_enabled(state, rally.RALLY, False)
                self.assertFalse(rally.dlc.list_content(state)[0]["enabled"])
                self.assertEqual(save.read_bytes(), b"never change this save")

    def test_prior_recipe_rebuild_retains_previous_managed_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            state, game, content, save, dump, package, extract = self.fixture(Path(directory))
            with ExitStack() as stack:
                for mock in self.mocks(dump, package, extract): stack.enter_context(mock)
                rally.prepare(state, game, Path("extractor"))
                output = state / "cache/rally_adapter"
                metadata = json.loads((output / "preparation.json").read_text())
                metadata["recipe"]["recipe_version"] = 1
                rally.dlc.write_json(output / "preparation.json", metadata)
                old_bytes = (output / "preparation.json").read_bytes()
                result = rally.prepare(state, game, Path("extractor"))
                self.assertFalse(result["reused"])
                self.assertEqual(result["recipe"]["recipe_version"], 12)
                retained = list((state / "cache").glob("rally_adapter.previous-*/preparation.json"))
                self.assertEqual(len(retained), 1)
                self.assertEqual(retained[0].read_bytes(), old_bytes)
                self.assertEqual(save.read_bytes(), b"never change this save")

    def test_failed_rebuild_keeps_existing_cache_then_repair_retains_old_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            state, game, content, save, dump, package, extract = self.fixture(Path(directory))
            with ExitStack() as stack:
                for mock in self.mocks(dump, package, extract): stack.enter_context(mock)
                rally.prepare(state, game, Path("extractor"))
                output = state / "cache/rally_adapter"
                metadata = (output / "preparation.json").read_bytes()
                (output / "rally-pace.toml").write_bytes(b"damaged")
                with patch.object(rally, "build_assets", side_effect=OSError("interrupted extraction")):
                    with self.assertRaisesRegex(OSError, "interrupted"):
                        rally.prepare(state, game, Path("extractor"))
                self.assertEqual((output / "preparation.json").read_bytes(), metadata)
                self.assertEqual((output / "rally-pace.toml").read_bytes(), b"damaged")
                self.assertFalse(list((state / "cache").glob("rally-build-*")))
                self.assertFalse(rally.prepare(state, game, Path("extractor"))["reused"])
                retained = list((state / "cache").glob("rally_adapter.previous-*/rally-pace.toml"))
                self.assertEqual(len(retained), 1)
                self.assertEqual(retained[0].read_bytes(), b"damaged")
                self.assertEqual(save.read_bytes(), b"never change this save")


if __name__ == "__main__":
    unittest.main()
