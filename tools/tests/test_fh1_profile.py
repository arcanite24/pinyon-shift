import importlib.util
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "fh1-profile.py"
SPEC = importlib.util.spec_from_file_location("fh1_profile", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
# Dataclasses look their module up while the class is built.
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
sys.path.insert(0, str(MODULE_PATH.parent))
import pinyon_common as COMMON
import pinyon_config as CONFIG


def field(name, kind, payload):
    encoded = name.encode("ascii")
    return struct.pack(">I", len(encoded)) + encoded + struct.pack(">II", 0x20, 0) + bytes([kind]) + payload


def body():
    main = (field("Credits", 0x03, struct.pack(">I", 167700))
            + field("XP", 0x07, struct.pack(">i", -5))
            + field("Exposure", 0x09, struct.pack(">f", 0.1))
            + field("SatNav", 0x01, b"\x01")
            + field("UpTime", 0x04, struct.pack(">Q", 49217825)))
    fields = (field("Options", 0x0F, struct.pack(">I", 1) + field("Tutorial", 0x00, b"\x00"))
              + field("Main", 0x0F, struct.pack(">I", 5) + main))
    return struct.pack(">I", 2) + fields + b"\x00\x00\x00\x02tail" + b"\xbb" * 8


class Fh1ProfileTests(unittest.TestCase):
    def test_round_trips_and_reads_nested_fields(self):
        data = body()
        profile = MODULE.decode(data)
        self.assertEqual(data, MODULE.encode(profile))
        self.assertEqual(167700, MODULE.find(profile, "Main/Credits").value)
        self.assertEqual(-5, MODULE.find(profile, "Main/XP").value)
        self.assertEqual(16, len(profile.tail))

    def test_set_keeps_the_size_and_rejects_values_that_do_not_fit(self):
        profile = MODULE.decode(body())
        MODULE.set_value(profile, "Main/Credits", "1000000")
        encoded = MODULE.encode(profile)
        self.assertEqual(len(body()), len(encoded))
        self.assertEqual(1000000, MODULE.find(MODULE.decode(encoded), "Main/Credits").value)
        with self.assertRaises(MODULE.ProfileError):
            MODULE.set_value(profile, "Main/Credits", "-1")
        with self.assertRaises(KeyError):
            MODULE.find(profile, "Main/Missing")

    def test_rejects_a_body_that_is_not_a_profile(self):
        with self.assertRaises(MODULE.ProfileError):
            MODULE.decode(struct.pack(">I", 1) + b"\x00\x00\x1f\x4d" + b"\x00" * 16)

    def test_cli_set_writes_a_new_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "in.bin"
            target = Path(directory) / "out.bin"
            source.write_bytes(body())
            self.assertEqual(0, MODULE.main(["set", str(source), "Main/Credits", "5", "--output", str(target)]))
            self.assertEqual(5, MODULE.find(MODULE.decode(target.read_bytes()), "Main/Credits").value)
            self.assertEqual(body(), source.read_bytes())

    def recovery_state(self, directory):
        state = Path(directory)
        profile = state / "user-modded" / COMMON.DEFAULT_XUID / COMMON.TITLE_ID / "00000001" / "ForzaProfile"
        profile.mkdir(parents=True)
        (profile / "ForzaProfile").write_bytes(b"encrypted profile")
        (profile / "PlayerDatabase").write_bytes(b"encrypted garage and parts")
        (state / "user").mkdir()
        (state / "user" / "untouched").write_bytes(b"normal save")
        config = state / "config" / "pinyon_shift.toml"
        CONFIG.write_config(config, 'enabled_mods = "hidden_cars"\nvsync = false\n')
        return state, config

    @patch.object(COMMON, "game_running", return_value=False)
    def test_recovery_backs_up_all_selected_profile_files_and_config(self, _):
        with tempfile.TemporaryDirectory() as directory:
            state, config = self.recovery_state(directory)
            CONFIG.write_config(config, CONFIG.read_config(config) +
                                'pinyon_shift_cheats = false\ncheat_set_credits = 12345\ncheat_time_scale = 2.0\n')
            before = {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()}
            result = MODULE.recover_car(state)
            backup = Path(result["backup"])
            for relative, data in before.items():
                if relative.parts[0] != "user":
                    self.assertEqual(data, (backup / relative).read_bytes())
                if relative.parts[0] != "config":
                    self.assertEqual(data, (state / relative).read_bytes())
            text = CONFIG.read_config(config)
            self.assertEqual("Main/CareerCar=0", CONFIG.get_value(text, "cheat_set_profile_fields", None))
            self.assertEqual("false", CONFIG.get_value(text, "pinyon_shift_cheats", None))
            self.assertEqual("12345", CONFIG.get_value(text, "cheat_set_credits", None))
            self.assertEqual("2.0", CONFIG.get_value(text, "cheat_time_scale", None))
            self.assertEqual("hidden_cars", CONFIG.get_value(text, "enabled_mods", None))
            self.assertTrue((backup / "manifest.json").is_file())
            manifest = json.loads((backup / "manifest.json").read_text())
            self.assertEqual(manifest, {p.relative_to(backup).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in backup.rglob("*") if p.is_file() and p.name != "manifest.json"})

    @patch.object(COMMON, "game_running", return_value=False)
    def test_recovery_follows_the_selected_xuid(self, _):
        with tempfile.TemporaryDirectory() as directory:
            state, config = self.recovery_state(directory)
            xuid = "1234567890123456"
            profile = state / "user-modded" / xuid
            MODULE.shutil.copytree(state / "user-modded" / COMMON.DEFAULT_XUID, profile)
            CONFIG.write_config(config, CONFIG.set_value(CONFIG.read_config(config), "user_xuid", f'"{xuid}"'))
            result = MODULE.recover_car(state)
            self.assertEqual(str(profile), result["profile"])
            backup = Path(result["backup"]) / "user-modded"
            self.assertTrue((backup / xuid).is_dir())
            self.assertFalse((backup / COMMON.DEFAULT_XUID).exists())

    def test_recovery_refuses_a_running_game(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(COMMON, "game_running", return_value=True):
            state, config = self.recovery_state(directory)
            before = config.read_bytes()
            with self.assertRaises(COMMON.CommandError):
                MODULE.recover_car(state)
            self.assertEqual(before, config.read_bytes())
            self.assertFalse((state / "backups").exists())

    @patch.object(COMMON, "game_running", return_value=False)
    def test_recovery_refuses_missing_profile_pending_fields_and_named_profile(self, _):
        with tempfile.TemporaryDirectory() as directory:
            state, config = self.recovery_state(directory)
            initial = config.read_bytes()
            CONFIG.write_config(config, CONFIG.set_value(initial.decode(), "cheat_set_profile_fields", '"Main/XP=5"'))
            with self.assertRaisesRegex(MODULE.ProfileError, "already pending"):
                MODULE.recover_car(state)
            CONFIG.write_config(config, initial.decode())
            manifest = state / "mods" / "hidden_cars" / "mod.toml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text('profile = "other"\n')
            with self.assertRaisesRegex(MODULE.ProfileError, "named profile"):
                MODULE.recover_car(state)
            manifest.unlink()
            CONFIG.write_config(config, CONFIG.set_value(initial.decode(), "user_xuid", '"1234567890123456"'))
            with self.assertRaisesRegex(MODULE.ProfileError, "no existing"):
                MODULE.recover_car(state)
            self.assertFalse((state / "backups").exists())

    @patch.object(COMMON, "game_running", return_value=False)
    def test_recovery_does_not_queue_a_change_if_backup_fails(self, _):
        with tempfile.TemporaryDirectory() as directory:
            state, config = self.recovery_state(directory)
            before = config.read_bytes()
            with patch.object(MODULE.shutil, "copytree", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    MODULE.recover_car(state)
            self.assertEqual(before, config.read_bytes())


if __name__ == "__main__":
    unittest.main()
