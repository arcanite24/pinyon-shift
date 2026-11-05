import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import pinyon_common as common  # noqa: E402
import pinyon_mods  # noqa: E402

BASE = "DB40DF605ADE49A6"
V4 = "74B033805AB1BCAA"


def arguments(state, command, **values):
    defaults = dict(state_root=state, json=True, mods_command=command, name=None,
                    direction=None, path=None, replace=False, key=None, value=None)
    defaults.update(values)
    return argparse.Namespace(**defaults)


def write_mod(root, name, extra="", folders=(), files=None):
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "mod.toml").write_text(f'name = "{name}"\nversion = "1.0.0"\nabi = 1\n{extra}',
                                        encoding="utf-8")
    for folder in folders:
        (directory / folder).mkdir(parents=True)
    for path, data in (files or {}).items():
        (directory / path).parent.mkdir(parents=True, exist_ok=True)
        (directory / path).write_bytes(data)
    return directory


class ModsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = self.root / "state"
        self.mods = self.state / "mods"
        self.mods.mkdir(parents=True)
        os.environ["PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME"] = "1"
        self.addCleanup(os.environ.pop, "PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME", None)

    def run_command(self, command, **values):
        return pinyon_mods.run(arguments(self.state, command, **values))

    def enabled(self):
        return pinyon_mods._patches().enabled_mods(pinyon_mods.config_path(self.state))

    def set_enabled(self, mods):
        config = pinyon_mods.config_path(self.state)
        config.parent.mkdir(parents=True, exist_ok=True)
        pinyon_mods._patches().set_enabled_mods(config, mods)

    def test_metadata_is_read_for_the_launcher(self):
        write_mod(self.mods, "shiny", '''
title = "Shiny   paint"
author = "Someone"
url = "https://example.com/shiny"
description = """
First line
of a paragraph.

Second paragraph."""
images = ["preview.png", "../outside.png", "missing.png", "notes.txt", "shots/2.JPG"]
game_version = ["DB40DF605ADE49A6", "74B033805AB1BCAA"]
shares_save = true
''', folders=("textures", "merge"),
                  files={"preview.png": b"p", "shots/2.JPG": b"j", "notes.txt": b"t"})
        (self.root / "state" / "outside.png").write_bytes(b"x")
        mod = self.run_command("list")["mods"][0]
        self.assertEqual(mod["title"], "Shiny paint")
        self.assertEqual(mod["author"], "Someone")
        self.assertEqual(mod["url"], "https://example.com/shiny")
        self.assertEqual(mod["description"], "First line of a paragraph.\n\nSecond paragraph.")
        self.assertEqual([Path(p).name for p in mod["images"]], ["preview.png", "2.JPG"])
        self.assertEqual(mod["contents"], ["merged settings", "textures"])
        self.assertEqual(mod["builds"], ["base disc", "title update v4"])
        self.assertEqual(mod["problems"], [])
        self.assertFalse(mod["enabled"])

    def test_defaults_and_unsafe_urls(self):
        write_mod(self.mods, "plain", 'url = "file:///C:/Windows/notepad.exe"\n'
                                      'library = "code/plain.dll"\n')
        mod = self.run_command("list")["mods"][0]
        self.assertEqual((mod["title"], mod["url"], mod["description"]), ("plain", "", ""))
        self.assertEqual(mod["contents"], ["native code"])

    def test_problems_match_the_game_checks(self):
        write_mod(self.mods, "renamed").joinpath("mod.toml").write_text(
            'name = "other"\nabi = 1\n', encoding="utf-8")
        write_mod(self.mods, "old_abi").joinpath("mod.toml").write_text(
            'name = "old_abi"\nabi = 0\n', encoding="utf-8")
        write_mod(self.mods, "v4_only", f'game_version = "{V4}"\n')
        write_mod(self.mods, "needs", 'requires = ["absent", "base_mod"]\n')
        write_mod(self.mods, "base_mod")
        write_mod(self.mods, "broken").joinpath("mod.toml").write_text("name = ", encoding="utf-8")
        mods = {m["name"]: m["problems"] for m in self.run_command("list")["mods"]}
        self.assertEqual(mods["renamed"], ["mod.toml names another mod"])
        self.assertEqual(mods["old_abi"], ["made for another version of the mod system"])
        self.assertEqual(mods["v4_only"],
                         ["made for the title update v4, not the build you play"])
        self.assertEqual(mods["needs"], ["needs absent, which is not installed",
                                         "needs base_mod switched on"])
        self.assertTrue(mods["broken"][0].startswith("mod.toml cannot be read"))
        self.assertEqual(mods["base_mod"], [])

    def test_enable_orders_requirements_and_refuses_conflicts(self):
        write_mod(self.mods, "lib")
        write_mod(self.mods, "user", 'requires = ["lib"]\n')
        write_mod(self.mods, "rival", 'conflicts = ["user"]\n')
        result = self.run_command("enable", name="user")
        self.assertEqual(result["also_enabled"], ["lib"])
        self.assertEqual(self.enabled(), ["lib", "user"])
        self.assertEqual([m["name"] for m in result["mods"]], ["lib", "user", "rival"])
        with self.assertRaisesRegex(common.CommandError, "cannot run with user"):
            self.run_command("enable", name="rival")
        self.run_command("disable", name="lib")
        self.assertEqual(self.enabled(), ["user"])
        listed = self.run_command("list")["mods"]
        self.assertEqual([m["name"] for m in listed], ["user", "lib", "rival"])
        self.assertEqual(listed[0]["problems"], ["needs lib switched on"])

    def test_move_skips_hidden_mods(self):
        for name in ("a", "b"):
            write_mod(self.mods, name)
        write_mod(self.mods, "camera", "always_enabled = true\nshares_save = true\n")
        (self.mods / "camera" / ".pinyon-builtin").write_text("", encoding="utf-8")
        self.set_enabled(["zz-db-patches", "a", "camera", "b"])
        self.run_command("move", name="b", direction="up")
        self.assertEqual(self.enabled(), ["zz-db-patches", "b", "camera", "a"])
        self.run_command("move", name="b", direction="up")
        self.assertEqual(self.enabled(), ["zz-db-patches", "b", "camera", "a"])
        listed = self.run_command("list")
        self.assertEqual([m["name"] for m in listed["mods"]], ["b", "a"])
        self.assertEqual(listed["missing"], [])
        with self.assertRaises(common.CommandError):
            self.run_command("disable", name="camera")

    def test_save_follows_the_switched_on_mods(self):
        write_mod(self.mods, "looks", "shares_save = true\n")
        write_mod(self.mods, "looks_db", "shares_save = true\n", folders=("db",))
        write_mod(self.mods, "game")
        write_mod(self.mods, "total", 'profile = "total"\n')
        self.assertEqual(self.run_command("list")["save"]["profile"], "user")
        self.set_enabled(["looks"])
        self.assertEqual(self.run_command("list")["save"]["kind"], "own")
        self.set_enabled(["looks", "looks_db"])
        self.assertEqual(self.run_command("list")["save"]["kind"], "modded")
        # The database patch built for looks_db stays listed until the next
        # start rebuilds it; with looks_db switched off it does not count.
        write_mod(self.mods, "zz-db-patches", folders=("game",))
        self.set_enabled(["zz-db-patches", "looks_db", "looks"])
        self.assertEqual(self.run_command("list")["save"]["kind"], "modded")
        self.run_command("disable", name="looks_db")
        self.assertEqual(self.run_command("list")["save"]["kind"], "own")
        self.assertFalse(self.run_command("list")["save"]["modded_copy"])
        (self.state / "user-modded").mkdir()
        self.assertTrue(self.run_command("list")["save"]["modded_copy"])
        self.set_enabled(["looks", "game", "total"])
        self.assertEqual(self.run_command("list")["save"],
                         {"profile": "user-total", "kind": "own-mod-save", "mod": "total",
                          "modded_copy": True})

    def test_install_from_zip_folder_and_pack(self):
        source = write_mod(self.root / "download" / "wrapper", "fresh", 'title = "Fresh"\n',
                           files={"game/media/a.txt": b"a"})
        archive = self.root / "fresh.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for path in source.rglob("*"):
                zipped.write(path, path.relative_to(self.root / "download"))
        result = self.run_command("install", path=archive)
        self.assertEqual(result["installed"], ["fresh"])
        self.assertEqual((self.mods / "fresh" / "game" / "media" / "a.txt").read_bytes(), b"a")
        self.assertEqual(list(self.mods.glob(".*")), [])
        self.assertEqual(self.enabled(), [])
        with self.assertRaisesRegex(common.CommandError, "already installed"):
            self.run_command("install", path=archive)
        (source / "game" / "media" / "a.txt").write_bytes(b"b")
        self.run_command("install", path=source, replace=True)
        self.assertEqual((self.mods / "fresh" / "game" / "media" / "a.txt").read_bytes(), b"b")
        pack = self.root / "pack"
        write_mod(pack, "one")
        write_mod(pack, "two")
        self.assertEqual(self.run_command("install", path=pack)["installed"], ["one", "two"])

    def test_install_refuses_unsafe_or_reserved_mods(self):
        archive = self.root / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("mod.toml", 'name = "evil"\nabi = 1\n')
            zipped.writestr("../escape.txt", "x")
        with self.assertRaisesRegex(common.CommandError, "unsafe"):
            self.run_command("install", path=archive)
        self.assertFalse((self.state / "escape.txt").exists())
        write_mod(self.mods, "camera")
        (self.mods / "camera" / ".pinyon-builtin").write_text("", encoding="utf-8")
        for name, message in (("camera", "built-in"), ("zz-db-patches", "Pinyon Shift itself"),
                              ("bad name", "needs a name")):
            source = self.root / "src" / "x"
            if source.exists():
                import shutil
                shutil.rmtree(source)
            source.mkdir(parents=True)
            (source / "mod.toml").write_text(f'name = "{name}"\nabi = 1\n', encoding="utf-8")
            with self.assertRaisesRegex(common.CommandError, message):
                self.run_command("install", path=source, replace=True)
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(common.CommandError, "no mod.toml"):
            self.run_command("install", path=empty)

    def test_options_are_listed_and_chosen(self):
        write_mod(self.mods, "pace", '''
[[option]]
key = "pace"
title = "Career pace"
default = "2"
choices = [{ value = "0.5", label = "Half" }, "2", "3"]
''')
        write_mod(self.mods, "plain")
        write_mod(self.mods, "broken", '[[option]]\nkey = "Bad Key"\nchoices = ["1"]\n')
        mods = {m["name"]: m for m in self.run_command("list")["mods"]}
        self.assertEqual(mods["plain"]["options"], [])
        self.assertEqual(mods["pace"]["options"], [{
            "key": "pace", "title": "Career pace", "description": "", "value": "2",
            "choices": [{"value": "0.5", "label": "Half"}, {"value": "2", "label": "2"},
                        {"value": "3", "label": "3"}]}])
        self.assertTrue(mods["broken"]["problems"][0].startswith("its options cannot be read"))
        listed = self.run_command("option", name="pace", key="pace", value="0.5")
        self.assertEqual(next(m for m in listed["mods"] if m["name"] == "pace")["options"][0]["value"], "0.5")
        for key, value, message in (("pace", "9", "not a choice"), ("speed", "2", "no option speed")):
            with self.assertRaisesRegex(common.CommandError, message):
                self.run_command("option", name="pace", key=key, value=value)
        # Choices live in their own file; the game's settings file is not touched.
        self.assertFalse(pinyon_mods.config_path(self.state).exists())
        self.assertTrue((self.state / "config" / "mod_options.json").is_file())

    def test_list_refreshes_a_stale_builtin(self):
        # An installed built-in from an older build (as after an update, before the next start).
        patches = pinyon_mods._patches()
        source = patches.BUILTIN / "photo_mode_limits"
        stale = self.mods / "photo_mode_limits"
        import shutil
        shutil.copytree(source, stale)
        (stale / patches.BUILTIN_MARKER).write_text("", encoding="utf-8")
        (stale / "mod.toml").write_text('name = "photo_mode_limits"\nversion = "0.1.0"\nabi = 1\n', encoding="utf-8")
        write_mod(self.mods, "own_marked", "")  # a marker without a built-in source stays as it is
        (self.mods / "own_marked" / patches.BUILTIN_MARKER).write_text("", encoding="utf-8")
        listed = {m["name"]: m for m in self.run_command("list")["mods"]}
        self.assertEqual((stale / "mod.toml").read_bytes(), (source / "mod.toml").read_bytes())
        self.assertEqual(listed["photo_mode_limits"]["version"], "1.0.0")
        self.assertEqual((self.mods / "own_marked" / "mod.toml").read_text(encoding="utf-8").count("version"), 1)

    def test_install_explains_archives_it_does_not_take(self):
        # The XE hotfix by name (its real size is 1.6 GB), another 7-Zip archive, a non-ZIP.
        for name, message in (("FH1XE_v1.01_hotfix.7z", "DLC > Install XE"),
                              ("roads.7z", "7-Zip archive.*Install folder"),
                              ("roads.bin", "not a ZIP")):
            (self.root / name).write_bytes(b"not a zip")
            with self.assertRaisesRegex(common.CommandError, message):
                self.run_command("install", path=self.root / name)
        self.assertEqual(pinyon_mods.installed_mods(self.state), [])

    def test_remove_switches_off_and_deletes(self):
        write_mod(self.mods, "gone")
        write_mod(self.mods, "custom_radio")
        self.set_enabled(["gone", "custom_radio"])
        self.run_command("remove", name="gone")
        self.assertFalse((self.mods / "gone").exists())
        self.assertEqual(self.enabled(), ["custom_radio"])
        with self.assertRaisesRegex(common.CommandError, "Radio screen"):
            self.run_command("remove", name="custom_radio")
        listed = self.run_command("list")["mods"]
        self.assertEqual(listed[0]["managed_by"], "Radio")

    def test_cli_prints_one_json_object(self):
        write_mod(self.mods, "cli")
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).parents[1] / "pinyon.py"), "mods", "enable", "cli",
             "--state-root", str(self.state), "--json"],
            capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual((result["result"], result["mods"][0]["enabled"]), ("ok", True))
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).parents[1] / "pinyon.py"), "mods", "enable",
             "nothing", "--state-root", str(self.state), "--json"],
            capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(json.loads(completed.stdout)["error"], "nothing is not installed")


if __name__ == "__main__":
    unittest.main()
