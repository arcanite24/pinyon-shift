import importlib.util
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "build-mod-patches.py"
SPEC = importlib.util.spec_from_file_location("build_mod_patches", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class BuildModPatchesTests(unittest.TestCase):
    def test_hidden_cars_exposes_only_the_explicit_player_model_allowlist(self):
        script = MODULE.BUILTIN / "hidden_cars" / "db" / "10-hidden-cars.sql"
        hidden = (282, 414, 1215, 1241, 1340, 1365, 1529, 1530, 1531, 1532,
                  1541, 1542, 1543, 1546, 1549, 1550, 1560, 1561, 1562,
                  1565, 1566, 1567, 1568, 9999)
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute("create table Data_Car (Id integer, IsSelectable integer, IsDrivable integer, BaseCost integer)")
            db.executemany("insert into Data_Car values (?,0,1,0)", [(i,) for i in hidden])
            db.execute("insert into Data_Car values (1496,1,1,120000)")
            db.executescript(script.read_text(encoding="utf-8"))
            self.assertEqual([1496, 1565, 1566, 1567, 1568], [r[0] for r in db.execute(
                "select Id from Data_Car where IsSelectable=1 order by Id")])
            self.assertEqual(299000, db.execute("select sum(BaseCost) from Data_Car").fetchone()[0])
            self.assertEqual(100000, db.execute("select BaseCost from Data_Car where Id=1529").fetchone()[0])

    def make(self, directory: Path):
        game = directory / "game"
        (game / "media" / "db").mkdir(parents=True)
        with closing(sqlite3.connect(game / "media" / "db" / "gamedb.slt")) as connection:
            connection.execute("create table Data_Car (Id integer, BaseCost integer)")
            connection.execute("insert into Data_Car values (1496, 120000)")
            connection.commit()
        state = directory / "state"
        (state / "config").mkdir(parents=True)
        (state / "config" / "pinyon_shift.toml").write_text(
            'vsync = true\nenabled_mods = "cheap,plain"\n', encoding="utf-8")
        (state / "mods" / "cheap" / "db").mkdir(parents=True)
        (state / "mods" / "cheap" / "db" / "10-price.sql").write_text(
            "update Data_Car set BaseCost = 1000 where Id = 1496;", encoding="utf-8")
        (state / "mods" / "plain").mkdir(parents=True)
        return game, state

    def test_applies_scripts_to_a_copy_and_lists_it_first(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            result = MODULE.build(state, game)
            self.assertTrue(result["patched"])
            patched = state / "mods" / MODULE.GENERATED / "game" / "media" / "db" / "gamedb.slt"
            with closing(sqlite3.connect(patched)) as connection:
                self.assertEqual(1000, connection.execute(
                    "select BaseCost from Data_Car where Id = 1496").fetchone()[0])
            with closing(sqlite3.connect(game / "media" / "db" / "gamedb.slt")) as connection:
                self.assertEqual(120000, connection.execute(
                    "select BaseCost from Data_Car where Id = 1496").fetchone()[0])
            self.assertIn(f'enabled_mods = "{MODULE.GENERATED},cheap,plain"',
                          (state / "config" / "pinyon_shift.toml").read_text(encoding="utf-8"))

    def test_options_fill_only_the_scripts_of_mods_that_declare_them(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            (state / "mods" / "cheap" / "mod.toml").write_text(
                'name = "cheap"\nabi = 1\n\n[[option]]\nkey = "divide"\ndefault = "2"\n'
                'choices = ["2", { value = "4", label = "Quarter" }]\n', encoding="utf-8")
            (state / "mods" / "cheap" / "db" / "10-price.sql").write_text(
                "update Data_Car set BaseCost = BaseCost / {{divide}} where Id = 1496;", encoding="utf-8")
            # A mod without options keeps a literal {{...}} and an unrelated `option` key, as before.
            (state / "mods" / "plain" / "mod.toml").write_text(
                'name = "plain"\nabi = 1\noption = "not a table"\n', encoding="utf-8")
            (state / "mods" / "plain" / "db").mkdir()
            (state / "mods" / "plain" / "db" / "20-note.sql").write_text(
                "create table Notes (Text text); insert into Notes values ('{{left alone}}');",
                encoding="utf-8")
            patched = state / "mods" / MODULE.GENERATED / "game" / "media" / "db" / "gamedb.slt"

            def price():
                with closing(sqlite3.connect(patched)) as connection:
                    return connection.execute("select BaseCost from Data_Car where Id = 1496").fetchone()[0]

            result = MODULE.build(state, game)
            self.assertEqual(60000, price())
            self.assertEqual([{"divide": "2"}, None], [s.get("options") for s in result["scripts"]])
            with closing(sqlite3.connect(patched)) as connection:
                self.assertEqual("{{left alone}}", connection.execute("select Text from Notes").fetchone()[0])
            options = MODULE._mod_options()
            options.choose(state, "cheap", options.read_declared(state / "mods" / "cheap"), "divide", "4")
            MODULE.build(state, game)
            self.assertEqual(30000, price())
            # A value edited by hand to one the mod does not offer falls back to the default.
            (state / "config" / "mod_options.json").write_text('{"cheap": {"divide": "1; drop table Data_Car"}}',
                                                               encoding="utf-8")
            MODULE.build(state, game)
            self.assertEqual(60000, price())
            # A placeholder the mod does not declare is refused rather than reaching the database.
            (state / "mods" / "cheap" / "db" / "20-typo.sql").write_text(
                "update Data_Car set BaseCost = {{devide}};", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "devide"):
                MODULE.build(state, game)

    def test_patches_the_database_of_a_mod_that_replaces_it(self):
        # A total conversion (the XE mod) ships its own gamedb.slt; scripts
        # of smaller mods must apply to it, not to the disc's.
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            replaced = state / "mods" / "plain" / "game" / "Media" / "DB" / "gamedb.slt"
            replaced.parent.mkdir(parents=True)
            with closing(sqlite3.connect(replaced)) as connection:
                connection.execute("create table Data_Car (Id integer, BaseCost integer)")
                connection.execute("insert into Data_Car values (1496, 120000)")
                connection.execute("insert into Data_Car values (2164, 400000)")
                connection.commit()
            result = MODULE.build(state, game)
            self.assertEqual(replaced.as_posix(), result["base"])
            patched = state / "mods" / MODULE.GENERATED / "game" / "media" / "db" / "gamedb.slt"
            with closing(sqlite3.connect(patched)) as connection:
                self.assertEqual([(1496, 1000), (2164, 400000)], connection.execute(
                    "select Id, BaseCost from Data_Car order by Id").fetchall())

    def test_reads_the_dlc_enabled_mods_hide(self):
        with tempfile.TemporaryDirectory() as directory:
            _, state = self.make(Path(directory))
            (state / "mods" / "plain" / "mod.toml").write_text(
                'name = "plain"\nhide_dlc = ["6f6992766050d818245add408031e280fb5f4e634d"]\n',
                encoding="utf-8")
            (state / "mods" / "off").mkdir()
            (state / "mods" / "off" / "mod.toml").write_text(
                'name = "off"\nhide_dlc = ["ABC"]\n', encoding="utf-8")
            self.assertEqual({"6F6992766050D818245ADD408031E280FB5F4E634D": "plain"},
                             MODULE.hidden_dlc(state))

    def test_removes_the_generated_mod_without_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state = self.make(Path(directory))
            MODULE.build(state, game)
            (state / "mods" / "cheap" / "db" / "10-price.sql").unlink()
            result = MODULE.build(state, game)
            self.assertFalse(result["patched"])
            self.assertFalse((state / "mods" / MODULE.GENERATED).exists())
            self.assertIn('enabled_mods = "cheap,plain"',
                          (state / "config" / "pinyon_shift.toml").read_text(encoding="utf-8"))

    def test_installs_builtin_mods_and_leaves_the_players_own(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "builtin"
            for name in ("camera", "taken"):
                (source / name / "merge").mkdir(parents=True)
                (source / name / "mod.toml").write_text(f'name = "{name}"\n', encoding="utf-8")
                (source / name / "merge" / "a.xml").write_text("<A/>", encoding="utf-8")
            state = root / "state"
            (state / "mods" / "taken").mkdir(parents=True)
            (state / "mods" / "taken" / "mod.toml").write_text("mine", encoding="utf-8")
            self.assertEqual(["camera"], MODULE.install_builtin_mods(state, source))
            self.assertEqual("<A/>", (state / "mods" / "camera" / "merge" / "a.xml")
                             .read_text(encoding="utf-8"))
            self.assertEqual("mine", (state / "mods" / "taken" / "mod.toml")
                             .read_text(encoding="utf-8"))
            # Unchanged: not copied again. Updated: replaced.
            self.assertEqual([], MODULE.install_builtin_mods(state, source))
            (source / "camera" / "merge" / "a.xml").write_text("<B/>", encoding="utf-8")
            self.assertEqual(["camera"], MODULE.install_builtin_mods(state, source))
            self.assertEqual("<B/>", (state / "mods" / "camera" / "merge" / "a.xml")
                             .read_text(encoding="utf-8"))
            # Not enabled by installing.
            self.assertFalse((state / "config" / "pinyon_shift.toml").exists())

    def test_enables_always_enabled_builtin_mods(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "builtin"
            (source / "camera").mkdir(parents=True)
            (source / "camera" / "mod.toml").write_text(
                'name = "camera"\nalways_enabled = true\n'
                'off_settings = ["camera_shake = 0.0", "camera_lean = 0.0"]\n', encoding="utf-8")
            (source / "optional").mkdir(parents=True)
            (source / "optional" / "mod.toml").write_text('name = "optional"\n', encoding="utf-8")
            state = root / "state"
            config = state / "config" / "pinyon_shift.toml"
            config.parent.mkdir(parents=True)
            # Switched off before: enabled with its off settings, keeping a
            # value the player already has.
            config.write_text('camera_lean = 0.5\nenabled_mods = "other"\n', encoding="utf-8")
            MODULE.install_builtin_mods(state, source)
            self.assertEqual(["camera"], MODULE.enable_builtin_mods(state))
            text = config.read_text(encoding="utf-8")
            self.assertIn('enabled_mods = "other,camera"', text)
            self.assertIn("camera_shake = 0.0", text)
            self.assertIn("camera_lean = 0.5", text)
            self.assertNotIn("camera_lean = 0.0", text)
            # Already enabled: nothing changes.
            self.assertEqual([], MODULE.enable_builtin_mods(state))
            self.assertEqual(text, config.read_text(encoding="utf-8"))
            # A player's own mod of that name is not touched.
            other = root / "other-state"
            (other / "mods" / "camera").mkdir(parents=True)
            (other / "mods" / "camera" / "mod.toml").write_text("always_enabled = true\n",
                                                                encoding="utf-8")
            self.assertEqual([], MODULE.enable_builtin_mods(other))

    def test_reads_shares_save(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for name, text in (("look", "shares_save = true  # camera only\n"),
                               ("data", "shares_save = false\n"), ("plain", "")):
                (state / "mods" / name).mkdir(parents=True)
                (state / "mods" / name / "mod.toml").write_text(text, encoding="utf-8")
            self.assertTrue(MODULE.shares_save(state, "look"))
            self.assertFalse(MODULE.shares_save(state, "data"))
            self.assertFalse(MODULE.shares_save(state, "plain"))
            self.assertFalse(MODULE.shares_save(state, "missing"))


if __name__ == "__main__":
    unittest.main()
