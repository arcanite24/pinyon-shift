import argparse
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))
import pinyon_xe  # noqa: E402


def archive(path: Path, data: bytes) -> dict:
    path.write_bytes(data)
    return {"file": path.name, "size": len(data), "md5": hashlib.md5(data).hexdigest(),
            "page": "https://example.invalid"}


class PinyonXeTests(unittest.TestCase):
    def make(self, directory: Path):
        game = directory / "game"
        (game / "media" / "Cars").mkdir(parents=True)
        (game / "media" / "db").mkdir(parents=True)
        (game / "default.xex").write_bytes(b"base xex")
        (game / "media" / "db" / "gamedb.slt").write_bytes(b"base db")
        (game / "media" / "Cars" / "JAG_XKRS_12.zip").write_bytes(b"jaguar")
        (game / "media" / "Cars" / "FER_FXX_05.zip").write_bytes(b"fxx")
        downloads = directory / "downloads"
        downloads.mkdir()
        archives = {"1.0": archive(downloads / "xe-1.0.7z", b"one" * 5),
                    "1.01": archive(downloads / "xe-1.01.7z", b"hotfix" * 3)}
        # What each archive holds, as the XE releases lay it out.
        contents = {
            "xe-1.0.7z": {"default.xex": b"xe xex", "readme.txt": b"XE",
                          "media/cars/JAG_XKRS_12.zip": b"jaguar",
                          "media/cars/FER_FXX_05.zip": b"xe fxx",
                          "media/cars/LAM_Huracan_15.zip": b"huracan",
                          "media/db/gamedb.slt": b"xe db 1.0",
                          "media/db/gamedb - Copy.slt": b"leftover",
                          "media/db/gamedb.slt.BACKUP": b"leftover"},
            "xe-1.01.7z": {"media/db/gamedb.slt": b"xe db 1.01"},
        }

        def extract(_, source: Path, destination: Path) -> None:
            for name, data in contents[source.name].items():
                (destination / name).parent.mkdir(parents=True, exist_ok=True)
                (destination / name).write_bytes(data)

        state = directory / "state"
        (state / "config").mkdir(parents=True)
        (state / "config" / "pinyon_shift.toml").write_text(
            'enabled_mods = "other"\n', encoding="utf-8")
        return game, state, downloads, archives, extract

    def args(self, state: Path, game: Path, *archives: Path, **extra) -> argparse.Namespace:
        values = dict(xe_command="install", archives=list(archives), state_root=state,
                      game_root=game, replace=False, no_enable=False, json=True)
        values.update(extra)
        return argparse.Namespace(**values)

    def test_installs_the_files_that_differ_with_the_hotfix_over_1_0(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state, downloads, archives, extract = self.make(Path(directory))
            with mock.patch.object(pinyon_xe, "ARCHIVES", archives), \
                    mock.patch.object(pinyon_xe, "find_extractor", return_value=["7z"]), \
                    mock.patch.object(pinyon_xe, "extract", side_effect=extract), \
                    mock.patch.object(pinyon_xe, "FREE_SPACE_GB", 0):
                result = pinyon_xe.run(self.args(state, game, downloads / "xe-1.01.7z",
                                                 downloads / "xe-1.0.7z"))
            mod = state / "mods" / "xe"
            installed = sorted(p.relative_to(mod / "game").as_posix()
                               for p in (mod / "game").rglob("*") if p.is_file())
            # Unchanged files, executables and the author's leftovers are not
            # installed; paths follow the disc's spelling (media/Cars).
            self.assertEqual(["media/Cars/FER_FXX_05.zip", "media/Cars/LAM_Huracan_15.zip",
                              "media/db/gamedb.slt"], installed)
            self.assertEqual(b"xe db 1.01", (mod / "game/media/db/gamedb.slt").read_bytes())
            self.assertEqual((2, 1), (result["replaced"], result["added"]))
            toml = (mod / "mod.toml").read_text(encoding="utf-8")
            for line in ('name = "xe"', 'version = "1.01"', 'profile = "xe"',
                         f'game_version = "{pinyon_xe.BASE_EXECUTABLE}"',
                         f'hide_dlc = ["{pinyon_xe.RALLY}"]'):
                self.assertIn(line, toml)
            self.assertIn('enabled_mods = "other,xe"',
                          (state / "config" / "pinyon_shift.toml").read_text(encoding="utf-8"))
            self.assertFalse((state / "mods" / ".xe-staging").exists())
            self.assertEqual(b"base db", (game / "media/db/gamedb.slt").read_bytes())

    def test_refuses_unknown_archives_and_a_missing_1_0(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state, downloads, archives, extract = self.make(Path(directory))
            (downloads / "other.7z").write_bytes(b"something else")
            with mock.patch.object(pinyon_xe, "ARCHIVES", archives):
                with self.assertRaisesRegex(pinyon_xe.XeError, "not a known XE download"):
                    pinyon_xe.run(self.args(state, game, downloads / "other.7z"))
                with self.assertRaisesRegex(pinyon_xe.XeError, "full 1.0 download"):
                    pinyon_xe.run(self.args(state, game, downloads / "xe-1.01.7z"))
                (downloads / "xe-1.0.7z").write_bytes(b"one" * 4 + b"two")  # same size
                with self.assertRaisesRegex(pinyon_xe.XeError, "not its MD5"):
                    pinyon_xe.run(self.args(state, game, downloads / "xe-1.0.7z"))
            self.assertFalse((state / "mods").exists())

    def test_disable_enable_and_remove_keep_the_save(self):
        with tempfile.TemporaryDirectory() as directory:
            game, state, downloads, archives, extract = self.make(Path(directory))
            with mock.patch.object(pinyon_xe, "ARCHIVES", archives), \
                    mock.patch.object(pinyon_xe, "find_extractor", return_value=["7z"]), \
                    mock.patch.object(pinyon_xe, "extract", side_effect=extract), \
                    mock.patch.object(pinyon_xe, "FREE_SPACE_GB", 0):
                pinyon_xe.run(self.args(state, game, downloads / "xe-1.0.7z", no_enable=True))
                config = state / "config" / "pinyon_shift.toml"
                self.assertIn('enabled_mods = "other"', config.read_text(encoding="utf-8"))
                status = pinyon_xe.run(self.args(state, game, xe_command="status"))
                self.assertEqual((True, False, "1.0"),
                                 (status["installed"], status["enabled"], status["version"]))
                pinyon_xe.run(self.args(state, game, xe_command="enable"))
                self.assertIn('enabled_mods = "other,xe"', config.read_text(encoding="utf-8"))
                (state / "user-xe" / "save").mkdir(parents=True)
                pinyon_xe.run(self.args(state, game, xe_command="remove"))
                self.assertIn('enabled_mods = "other"', config.read_text(encoding="utf-8"))
                self.assertFalse((state / "mods" / "xe").exists())
                self.assertTrue((state / "user-xe" / "save").is_dir())


if __name__ == "__main__":
    unittest.main()
