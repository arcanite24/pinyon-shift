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


if __name__ == "__main__":
    unittest.main()
