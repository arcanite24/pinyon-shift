"""Rally adapter boundaries without game assets or real profiles."""
import importlib.util
import json
import sqlite3
import tomllib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

SPEC = importlib.util.spec_from_file_location("rally_seed", Path(__file__).parents[1] / "create-rally-stage-seed.py")
rally = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rally)


class RallySeedTests(unittest.TestCase):
    def test_pace_notes_preserve_authored_phrase_and_reject_bad_samples(self):
        audio = b'<CoDriverAudio><event play="50" group="CoDriver/Distance" cue="50Distance" icon="None"/><event play="Right" group="CoDriver/Turns/Right" cue="HardRight" icon="HardRight"/></CoDriverAudio>'
        route = b'<TrackRoute><RallyCalls><RallyCall name="gate" width="20" numSamples="2"><Samples><Sample id="50"/><Sample id="Right"/></Samples><Transform pos.x="1" pos.y="2" pos.z="3" facing.x="1" facing.y="0" facing.z="0"/></RallyCall></RallyCalls></TrackRoute>'
        call = tomllib.loads(rally.pace_notes({1: route}, audio))["calls"][0]
        self.assertEqual(call["position"], [1, 2, 3])
        self.assertEqual([sample["cue"] for sample in call["samples"]], ["50Distance", "HardRight"])
        # The owned fourth stage repeats exporter names for distinct trigger gates.
        node = ET.fromstring(route)
        duplicate = ET.fromstring(ET.tostring(node.find("./RallyCalls/RallyCall")))
        duplicate.find("Transform").set("pos.x", "4")
        node.find("RallyCalls").append(duplicate)
        calls = tomllib.loads(rally.pace_notes({47: ET.tostring(node)}, audio))["calls"]
        self.assertEqual([item["position"][0] for item in calls], [1, 4])
        for before, after in ((b'id="Right"', b'id="Unknown"'), (b'numSamples="2"', b'numSamples="1"'),
                              (b'width="20"', b'width="nan"'), (b'facing.x="1"', b'facing.x="0"')):
            with self.assertRaisesRegex(ValueError, "invalid authored"):
                rally.pace_notes({1: route.replace(before, after)}, audio)

    def test_separate_stage_survives_merge_without_changing_base_event(self):
        with sqlite3.connect(":memory:") as db:
            db.executescript('''
                CREATE TABLE Tracks (id INTEGER PRIMARY KEY, MediaName TEXT,
                    RouteId INTEGER, RibbonConfiguration INTEGER, NumSplitPoints INTEGER);
                INSERT INTO Tracks VALUES (1114,'ColoradoDirt',1,8,-1);
                INSERT INTO Tracks VALUES (1147,'ColoradoDirt',47,8,-1);
                CREATE TABLE Events (Id INTEGER PRIMARY KEY, HorizonEventID TEXT,
                    NumberOfDrivers INTEGER, PlayerGridPosition INTEGER,
                    NemesisGridPosition INTEGER, CashPrize INTEGER,
                    UnlockPointsReq INTEGER, Level INTEGER, TargetClass INTEGER);
                INSERT INTO Events VALUES (43,'FR06',7,7,3,6000,430,1,5);
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
            ''')
            stage = rally.add_stage(db, 1)
            db.execute("INSERT OR REPLACE INTO Tracks VALUES (1114,'ColoradoDirt',1,8,-1)")
            self.assertEqual(tuple(db.execute("SELECT NumberOfDrivers,UnlockPointsReq FROM Events WHERE Id=43").fetchone()), (7,430))
            self.assertEqual(tuple(db.execute("SELECT RibbonConfiguration,NumSplitPoints FROM Tracks WHERE id=?", (stage["track_id"],)).fetchone()), (2,2))
            self.assertEqual(db.execute("SELECT TrackId FROM Races WHERE Id=42").fetchone()[0],134)
            self.assertEqual(db.execute("SELECT NumberOfDrivers FROM Events WHERE Id=?", (stage["event_id"],)).fetchone()[0],0)
            self.assertEqual(db.execute("SELECT TargetClass FROM Events WHERE Id=?", (stage["event_id"],)).fetchone()[0],7)
            self.assertEqual(db.execute("SELECT Value FROM EventRestrictions WHERE EventID=?", (stage["event_id"],)).fetchone()[0],'0000000004')
            fourth = rally.add_stage(db, 47, "RALLY_NEXT")
            self.assertEqual(fourth["route"], 47)
            self.assertEqual(fourth["horizon_event_id"], "RALLY_NEXT")
            self.assertEqual(db.execute("SELECT TargetClass FROM Events WHERE Id=?", (fourth["event_id"],)).fetchone()[0],5)
            self.assertEqual(db.execute("SELECT RouteId,RibbonConfiguration FROM Tracks WHERE id=?", (fourth["track_id"],)).fetchone()[:], (47,2))
            with self.assertRaisesRegex(ValueError, "Rally stage route"):
                rally.add_stage(db, 24)

    def test_portal_uses_generic_activity_file(self):
        replacements = rally.portal(b'<ActivityManager><Activity name="festival_01"/></ActivityManager>',
            b'<ActivityManager><Activity name="FR06"><TriggerZone radius="25"/></Activity><Activity name="FR07"/></ActivityManager>')
        activities = ET.fromstring(replacements["Colorado/activities.xml"])
        self.assertIsNotNone(activities.find("Activity[@name='festival_01']"))
        entry = activities.find("Activity[@type='ActivityGeneric']")
        self.assertEqual(entry.find(".//Behaviour").get("event_id"), "RALLY_PROBE")
        career = ET.fromstring(replacements["Colorado/career_event_activations.xml"])
        self.assertEqual(career.find("Activity[@name='FR06']/TriggerZone").get("radius"), "0")
        self.assertIsNotNone(career.find("Activity[@name='FR07']"))

    def test_existing_output_and_changed_seed_are_never_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed, output = root / "seed", root / "output"
            seed.mkdir()
            output.mkdir()
            sentinel = output / "save"
            sentinel.write_bytes(b"keep")
            args = SimpleNamespace(seed=seed, output=output, dlc_state=root/"dlc", game_root=root/"game")
            with self.assertRaisesRegex(ValueError, "new output"):
                rally.create(args)
            self.assertEqual(sentinel.read_bytes(), b"keep")
            args.output = root / "new-output"
            (seed / "profile").write_bytes(b"changed")
            (seed / "seed.json").write_text(json.dumps(dict(profiles={"profile":"00"*32})))
            with self.assertRaisesRegex(ValueError, "pinned save seed has changed"):
                rally.create(args)
            self.assertFalse(args.output.exists())

    def test_autopilot_releases_controls_after_normal_race_preparation(self):
        flow = b'''<StateGroup><State id="prerace_cleanup"><Entry id="enter" target="start_driving.enter"/>
            <Node id="unblock_pause_entry"><Exit id="exit" target=".exit"/></Node></State></StateGroup>'''
        root = ET.fromstring(rally.autopilot(flow))
        cleanup = root.find("State[@id='prerace_cleanup']")
        self.assertEqual(cleanup.find("Entry").get("target"), "start_driving.enter")
        self.assertEqual(cleanup.find("Node[@id='unblock_pause_entry']/Exit").get("target"), "rally_probe_ai_reset.enter")
        self.assertEqual(cleanup.find("Node[@id='rally_probe_ai_reset']").get("state"), "global.disable_ai_player_car_control")
        self.assertEqual(cleanup.find("Node[@id='rally_probe_ai_reset']/Exit").get("target"), "rally_probe_ai.enter")
        self.assertEqual(cleanup.find("Node[@id='rally_probe_ai']").get("state"), "global.enable_ai_player_car_control")
        self.assertEqual(cleanup.find("Node[@id='rally_probe_ai']/Exit").get("target"), ".exit")

    def test_duplicate_transition_route_rejected_before_copying_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(seed=root/"seed", output=root/"output",
                                   dlc_state=root/"dlc", game_root=root/"game", route=1, next_route=1)
            with self.assertRaisesRegex(ValueError, "must differ"):
                rally.create(args)
            self.assertFalse(args.output.exists())

    def test_series_cannot_mix_with_fixed_next_stage_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = SimpleNamespace(seed=root/"seed", output=root/"output", dlc_state=root/"dlc",
                                   game_root=root/"game", route=1, next_route=2, series=7)
            with self.assertRaisesRegex(ValueError, "without --next-route"):
                rally.create(args)
            self.assertFalse(args.output.exists())

    def test_next_stage_preserves_abort_and_player_restore(self):
        flow = b'''<StateGroup><State id="postrace_internal">
            <Node id="postrace_results"><Exit id="quit" target="postrace_cleanup.enter"/></Node>
            <Node id="postrace_rivals"><Exit id="quit" target="black_out.enter"/></Node>
            <Node id="black_out" state="global.black_out"><Exit id="exit" target="postrace_cleanup.enter"/></Node>
            <Node id="postrace_cleanup" state="postrace_cleanup"><Exit id="exit" target="load_back_to_free_roam.enter"/></Node>
            </State><State id="load_back_to_free_roam">
            <Node id="restore_free_roam_car" state="global.restore_free_roam_car"/>
            <Node id="load_into_free_roam" state="global.load_into_free_roam"/>
            </State></StateGroup>'''
        root = ET.fromstring(rally.next_stage(flow, "RALLY_NEXT"))
        postrace = root.find("State[@id='postrace_internal']")
        self.assertEqual(postrace.find("Node[@id='postrace_results']/Exit").get("target"), "postrace_cleanup.enter")
        self.assertEqual(postrace.find("Node[@id='postrace_cleanup']/Exit").get("target"), "load_back_to_free_roam.enter")
        self.assertEqual(postrace.find("Node[@id='postrace_rivals']/Exit").get("target"), "rally_black_out.enter")
        self.assertEqual(postrace.find("Node[@id='rally_postrace_cleanup']/Exit").get("target"), "rally_load_next_stage.enter")
        self.assertEqual(postrace.find("Node[@id='rally_load_next_stage']").get("state"), "rally_load_next_stage")
        self.assertIsNotNone(postrace.find("Node[@id='rally_load_next_stage']/Entry[@id='enter']"))
        self.assertIsNotNone(root.find("State[@id='rally_load_next_stage']/Node[@state='global.restore_free_roam_car']"))
        self.assertEqual(root.find("State[@id='rally_next_stage']/Behaviour").get("event_id"), "RALLY_NEXT")
        self.assertIsNotNone(root.find("State[@id='load_back_to_free_roam']/Node[@state='global.load_into_free_roam']"))


if __name__ == "__main__":
    unittest.main()
