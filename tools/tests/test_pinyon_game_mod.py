import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import pinyon_common as common  # noqa: E402
import pinyon_game_mod  # noqa: E402


def write(root, files):
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def zip_folder(folder, archive):
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(folder))


class ImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = self.root / "state"
        self.game = self.root / "game"
        # A stand-in for the player's game: the disc spells media/DB/gamedb.slt.
        write(self.game, {"default.xex": b"code", "nxeart": b"art",
                          "media/DB/gamedb.slt": b"database",
                          "media/cars/ABA_500_11.zip": b"car",
                          "media/UI/Textures/Horizon.zip": b"ui"})
        os.environ["PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME"] = "1"
        self.addCleanup(os.environ.pop, "PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME", None)

    def run_import(self, *sources, **values):
        defaults = dict(sources=[str(s) for s in sources], name=None, title=None,
                        version="1.0", new_save=False, keeps_save=False, any_build=False,
                        enable=False, replace=False, state_root=self.state,
                        game_root=self.game, json=True)
        defaults.update(values)
        return pinyon_game_mod.import_mod(argparse.Namespace(**defaults))

    def manifest(self, name):
        return tomllib.loads((self.state / "mods" / name / "mod.toml").read_text(encoding="utf-8"))

    def test_a_modded_game_folder_keeps_only_what_differs(self):
        modded = self.root / "Cool Cars Mod"
        write(modded / "Forza Horizon", {
            "default.xex": b"patched code", "nxeart": b"art",
            "media/db/gamedb.slt": b"new database",       # spelled differently from the disc
            "media/cars/ABA_500_11.zip": b"car",            # unchanged
            "media/cars/NEW_CAR_99.zip": b"new car",
            "media/UI/Textures/Horizon.zip": b"ui"})
        write(modded, {"README.txt": b"Install over the game.", "notes.url": b"x"})
        result = self.run_import(modded, title="Cool cars")
        mod = self.state / "mods" / "cool_cars_mod"
        self.assertEqual(result["name"], "cool_cars_mod")
        self.assertEqual((result["replaced"], result["added"], result["unchanged"]), (1, 1, 2))
        self.assertEqual((mod / "game/media/DB/gamedb.slt").read_bytes(), b"new database")
        self.assertEqual((mod / "game/media/cars/NEW_CAR_99.zip").read_bytes(), b"new car")
        self.assertFalse((mod / "game/media/cars/ABA_500_11.zip").exists())
        self.assertFalse((mod / "game/default.xex").exists())
        self.assertTrue((mod / "README.txt").is_file())
        self.assertEqual(result["code_changed"], ["default.xex"])
        self.assertEqual(result["skipped"], ["notes.url"])
        self.assertEqual(len(result["warnings"]), 2)  # code left out, database replaced
        manifest = self.manifest("cool_cars_mod")
        self.assertEqual((manifest["name"], manifest["title"], manifest["abi"]),
                         ("cool_cars_mod", "Cool cars", 1))
        self.assertEqual(manifest["game_version"], "DB40DF605ADE49A6")
        self.assertNotIn("profile", manifest)
        self.assertIn("code were left out", manifest["description"])
        record = json.loads((mod / "import.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(record["files"]), ["media/DB/gamedb.slt", "media/cars/NEW_CAR_99.zip"])
        self.assertEqual(list(self.state.glob("mods/.*")), [])

    def test_files_that_start_inside_media_and_layered_archives(self):
        release = self.root / "release"
        write(release, {"cars/NEW_CAR_99.zip": b"v1", "UI/Textures/Horizon.zip": b"new ui",
                        "readme.txt": b"hi"})
        hotfix = self.root / "hotfix"
        write(hotfix, {"cars/NEW_CAR_99.zip": b"v2"})
        zip_folder(release, self.root / "Shiny UI.zip")
        result = self.run_import(self.root / "Shiny UI.zip", hotfix, keeps_save=True,
                                 any_build=True, enable=True, version="1.1")
        mod = self.state / "mods" / "shiny_ui"
        self.assertEqual((mod / "game/media/cars/NEW_CAR_99.zip").read_bytes(), b"v2")
        self.assertEqual((mod / "game/media/UI/Textures/Horizon.zip").read_bytes(), b"new ui")
        self.assertFalse((mod / "game/media/readme.txt").exists())
        self.assertTrue((mod / "readme.txt").is_file())
        self.assertEqual(result["warnings"], [])
        manifest = self.manifest("shiny_ui")
        self.assertTrue(manifest["shares_save"])
        self.assertEqual(manifest["title"], "Shiny UI")
        self.assertIn("1 game file replaced and 1 game file added", manifest["description"])
        self.assertEqual(manifest["version"], "1.1")
        self.assertNotIn("game_version", manifest)
        config = (self.state / "config" / "pinyon_shift.toml").read_text(encoding="utf-8")
        self.assertIn('enabled_mods = "shiny_ui"', config)

    def test_new_save_and_replacing(self):
        modded = self.root / "renumber"
        write(modded, {"media/db/gamedb.slt": b"renumbered"})
        self.run_import(modded, name="Renumber", new_save=True)
        self.assertEqual(self.manifest("renumber")["profile"], "renumber")
        with self.assertRaisesRegex(common.CommandError, "already installed"):
            self.run_import(modded, name="renumber")
        write(modded, {"media/db/gamedb.slt": b"renumbered again"})
        self.run_import(modded, name="renumber", replace=True)
        self.assertEqual((self.state / "mods/renumber/game/media/DB/gamedb.slt").read_bytes(),
                         b"renumbered again")

    def test_refusals(self):
        same = self.root / "same"
        write(same, {"media/cars/ABA_500_11.zip": b"car"})
        with self.assertRaisesRegex(common.CommandError, "nothing to import"):
            self.run_import(same)
        stray = self.root / "stray"
        write(stray, {"photos/a.png": b"x"})
        with self.assertRaisesRegex(common.CommandError, "no game files found"):
            self.run_import(stray)
        for name in ("xe", "zz-db-patches", "custom_radio"):
            with self.assertRaisesRegex(common.CommandError, "uses itself"):
                self.run_import(same, name=name)
        builtin = self.state / "mods" / "camera"
        builtin.mkdir(parents=True)
        (builtin / ".pinyon-builtin").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(common.CommandError, "built-in"):
            self.run_import(same, name="camera", replace=True)
        evil = self.root / "evil.zip"
        with zipfile.ZipFile(evil, "w") as zipped:
            zipped.writestr("media/cars/x.zip", "x")
            zipped.writestr("../escape.txt", "x")
        with self.assertRaisesRegex(common.CommandError, "unsafe"):
            self.run_import(evil)
        self.assertFalse((self.state / "escape.txt").exists())
        text = self.root / "notes.txt"
        text.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(common.CommandError, "not a folder, ZIP"):
            self.run_import(text)
        shutil.rmtree(self.game / "media")
        with self.assertRaisesRegex(common.CommandError, "finish setup"):
            self.run_import(same)

    def test_cli_prints_one_json_object(self):
        modded = self.root / "cli mod"
        write(modded, {"media/cars/NEW.zip": b"x"})
        command = [sys.executable, str(Path(__file__).parents[1] / "pinyon.py"), "import-mod",
                   str(modded), "--state-root", str(self.state), "--game-root", str(self.game),
                   "--json"]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual((result["result"], result["name"], result["added"]), ("ok", "cli_mod", 1))
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("already installed", json.loads(completed.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
