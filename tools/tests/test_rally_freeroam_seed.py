"""Qualification probes must never write the pinned profile or owned inputs."""
from contextlib import ExitStack, closing
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

SPEC = importlib.util.spec_from_file_location("rally_freeroam", Path(__file__).parents[1] / "create-rally-freeroam-seed.py")
rally = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rally)

FLOW = b'<StateGroup id="game_start_free_roam"><State id="setup_free_roam"><Node id="place_car" state="global.restore_car_position"><Entry id="enter"/><Exit id="exit" target="enable_map_discovery.enter"/></Node></State></StateGroup>'
ROUTE = b'<TrackRoute><NamedTransforms><NamedTransform name="start_location_00"><Transform pos.x="1" pos.y="2" pos.z="3" facing.x="-1" facing.z="0"/></NamedTransform></NamedTransforms></TrackRoute>'


def database(path, *, owned=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db, db:
        schema = """
            CREATE TABLE Environments (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE Tracks (id INTEGER PRIMARY KEY, MediaName TEXT, DevName TEXT,
                                 RouteId INTEGER, EnvironmentId INTEGER, MiniRibbonPath TEXT);
        """
        db.executescript(schema.replace(" PRIMARY KEY", "") if owned else schema)
        db.execute("INSERT INTO Environments VALUES (?,?)", (111, "Rally") if owned else (1, "base"))
        db.execute("INSERT INTO Tracks VALUES (?,?,?,?,?,?)",
                   (1112, "ColoradoDirt", "DirtFreeRoam", 0, 111, "owned-map") if owned else
                   (317, "Colorado", "FreeRoam", 0, 1, "base-map"))
        if not owned:
            db.execute("INSERT INTO Tracks VALUES (99,'other','race',9,1,'leave-me')")


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class RallyFreeRoamTests(unittest.TestCase):
    def fixture(self, root):
        seed, owned, game = (root / name for name in ("seed", "owned", "game"))
        profile = seed / "user/player/4D5309C9/00000001/ForzaProfile/ForzaProfile"
        profile.parent.mkdir(parents=True)
        profile.write_bytes(b"pinned save")
        (seed / "config").mkdir()
        (seed / "config/pinyon_shift.toml").write_text('enabled_mods = "old"\n')
        (seed / "cache").mkdir()
        for name in ("fh1-native-shaders-v2.bin", "fh1-native-pipelines-v1.bin", "fh1-gpu-prewarm-v3.txt"):
            (seed / "cache" / name).write_bytes(b"catalog")
        (seed / "seed.json").write_text(json.dumps(dict(schema="pinyon-shift.render-seed.v1",
            profiles={profile.relative_to(seed).as_posix(): hashlib.sha256(profile.read_bytes()).hexdigest().upper()})))
        content, _, header = rally.assets.dlc.package_paths(owned, rally.assets.RALLY)
        header.parent.mkdir(parents=True)
        header.write_bytes(b"original licence")
        media = content / "Media/DLCZips/1600_pri_65/Media"
        media.mkdir(parents=True)
        (media / "zipmanifest.xml").write_bytes(b"owned manifest")
        merge = root / "merge.slt"
        database(merge, owned=True)
        with zipfile.ZipFile(content / "Media/DLCZips/1600_pri_65.zip", "w") as archive:
            archive.writestr("media/db/patch/1600000_merge.slt", merge.read_bytes())
            archive.writestr("media/Tracks/ColoradoDirt/Ribbon_00/TrackRoute001.xml", ROUTE)
        database(game / "media/db/gamedb.slt")
        with zipfile.ZipFile(game / "media/gamemodes.zip", "w") as archive:
            archive.writestr("game_free_roam_flow.xml", FLOW)
            archive.writestr("untouched", b"opaque bytes")
        args = SimpleNamespace(seed=seed, dlc_state=owned, game_root=game,
                               output=root / "output", extractor=root / "extractor")

        def extract(command, **kwargs):
            with zipfile.ZipFile(command[2]) as archive:
                Path(command[4]).write_bytes(archive.read(command[3]))
            return subprocess.CompletedProcess(command, 0)

        mocks = (patch.object(rally.assets, "verify_base"),
                 patch.object(rally.assets.dlc, "verified_content", return_value=(content, {"payload_sha256": "owned"}, {"verified": True})),
                 patch.object(rally.subprocess, "run", side_effect=extract))
        return args, mocks

    def test_owned_descriptor_preserves_all_fields_and_unrelated_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, merge = root / "base.slt", root / "merge.slt"
            database(base)
            database(merge, owned=True)
            before = merge.read_bytes()
            self.assertEqual(rally.free_roam_database(base, merge), 1112)
            with closing(sqlite3.connect(base)) as db:
                self.assertEqual(db.execute("SELECT * FROM Tracks WHERE id=317").fetchone(),
                                 (317, "ColoradoDirt", "DirtFreeRoam", 0, 111, "owned-map"))
                self.assertEqual(db.execute("SELECT MiniRibbonPath FROM Tracks WHERE id=99").fetchone(), ("leave-me",))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM Environments").fetchone(), (2,))
            self.assertEqual(merge.read_bytes(), before)

    def test_invalid_descriptor_does_not_partially_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, merge = root / "base.slt", root / "merge.slt"
            database(base)
            database(merge, owned=True)
            with closing(sqlite3.connect(merge)) as db, db:
                db.execute("UPDATE Tracks SET RouteId=1")
            before = base.read_bytes()
            with self.assertRaisesRegex(ValueError, "one owned"):
                rally.free_roam_database(base, merge)
            self.assertEqual(base.read_bytes(), before)

    def test_placement_uses_owned_facing_and_retains_flow_exit(self):
        spawn = rally.start_transform(ROUTE)
        self.assertEqual(spawn, dict(x="1.0", y="2.0", z="3.0", rotation="270.0"))
        flow = ET.fromstring(rally.place_initial_car(FLOW, spawn))
        self.assertEqual(flow.find("State/Node/Exit").get("target"), "enable_map_discovery.enter")
        self.assertEqual(flow.find("State[@id='pinyon_rally_spawn']/Behaviour").get("y"), "2.0")
        for route in (b"<TrackRoute/>", ROUTE.replace(b'pos.y="2"', b'pos.y="nan"'),
                      ROUTE.replace(b'facing.x="-1"', b'facing.x="0"')):
            with self.assertRaises(ValueError):
                rally.start_transform(route)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            rally.place_initial_car(FLOW.replace(b"global.restore_car_position", b"other"), spawn)

    def test_create_publishes_complete_private_seed_and_preserves_inputs(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            args, mocks = self.fixture(root)
            for mock in mocks:
                stack.enter_context(mock)
            before = {name: hashes(root / name) for name in ("seed", "owned", "game")}
            rally.create(args)
            for name, expected in before.items():
                self.assertEqual(hashes(root / name), expected)
            output = args.output
            self.assertEqual((output / "config/pinyon_shift.toml").read_text(), f'enabled_mods = "{rally.MOD}"\n')
            self.assertEqual(hashes(output / "user-rally-probe"), hashes(args.seed / "user"))
            receipt = json.loads((output / "rally-freeroam-probe.json").read_text())
            self.assertTrue(receipt["initial_placement_only"])
            self.assertIn("save/reload", receipt["unqualified"])
            with zipfile.ZipFile(output / "mods" / rally.MOD / "game/media/gamemodes.zip") as archive:
                self.assertEqual(archive.read("untouched"), b"opaque bytes")
            rally.verify_seed(output.resolve())
            with self.assertRaisesRegex(ValueError, "new private"):
                rally.create(args)

    def test_failure_does_not_publish_or_touch_inputs(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            args, mocks = self.fixture(root)
            for mock in mocks[:2]:
                stack.enter_context(mock)
            before = hashes(args.seed)
            with patch.object(rally.subprocess, "run", side_effect=RuntimeError("extractor failed")):
                with self.assertRaisesRegex(RuntimeError, "extractor failed"):
                    rally.create(args)
            self.assertFalse(args.output.exists())
            self.assertEqual(hashes(args.seed), before)
            self.assertEqual(list(root.glob("rally-freeroam-*")), [])

    def test_seed_tampering_and_v4_are_rejected_before_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args, _ = self.fixture(root)
            (args.seed / "title-update-v4").mkdir()
            with self.assertRaisesRegex(ValueError, "base-disc"):
                rally.create(args)
            (args.seed / "title-update-v4").rmdir()
            flags = args.seed / "user/player/4D5309C9/00000001/ForzaProfile/VersionFlags"
            flags.write_bytes(b"cmss" + b"\1" + bytes(7))
            with self.assertRaisesRegex(ValueError, "base-disc"):
                rally.create(args)
            manifest = json.loads((args.seed / "seed.json").read_text())
            manifest["profiles"] = {"../outside": "1234"}
            (args.seed / "seed.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "escapes"):
                rally.verify_seed(args.seed.resolve())


if __name__ == "__main__":
    unittest.main()
