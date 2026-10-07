import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("profile_tool", ROOT / "tools/title-update-profile.py")
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)

BASE_FLAGS = b"cmss" + bytes(132)
V4_FLAGS = b"cmss" + bytes.fromhex("0000000400000002") + bytes(124)


def make_profile(state: Path, flags: bytes, body: bytes = b"save") -> Path:
    profile = state / "user" / "B13EBABEBABEBABE" / "4D5309C9" / "00000001" / "ForzaProfile"
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "VersionFlags").write_bytes(flags)
    (profile / "ForzaProfile").write_bytes(body)
    dlc = state / "user" / "0000000000000000" / "4D5309C9" / "00000002" / "PKG"
    dlc.mkdir(parents=True, exist_ok=True)
    (dlc / "payload").write_bytes(b"dlc")
    return profile


class TitleUpdateProfileTests(unittest.TestCase):
    def test_version_detection(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            make_profile(state, BASE_FLAGS)
            self.assertEqual(TOOL.status(state)["profiles"], {"B13EBABEBABEBABE": "base"})
            make_profile(state, V4_FLAGS)
            self.assertEqual(TOOL.status(state)["profiles"], {"B13EBABEBABEBABE": "v4"})

    def test_backup_once_then_restore_keeps_v4_saves(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            profile = make_profile(state, BASE_FLAGS, b"base save")
            result = TOOL.backup(state)
            self.assertEqual(result["profiles"], ["B13EBABEBABEBABE"])
            backup = Path(result["backed_up"])
            self.assertFalse((backup / "0000000000000000").exists())  # DLC is never copied
            # v4 rewrites the profile; a second backup is refused.
            (profile / "VersionFlags").write_bytes(V4_FLAGS)
            (profile / "ForzaProfile").write_bytes(b"v4 save")
            self.assertIsNone(TOOL.backup(state)["backed_up"])
            restored = TOOL.restore(state)
            self.assertEqual((profile / "ForzaProfile").read_bytes(), b"base save")
            self.assertEqual(TOOL.status(state)["profiles"]["B13EBABEBABEBABE"], "base")
            kept = Path(restored["v4_saves_kept_in"]) / "B13EBABEBABEBABE" / "4D5309C9" / "00000001"
            self.assertEqual((kept / "ForzaProfile" / "ForzaProfile").read_bytes(), b"v4 save")
            self.assertTrue((state / "user" / "0000000000000000" / "4D5309C9").is_dir())

    def test_restore_refuses_a_changed_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            make_profile(state, BASE_FLAGS)
            backup = Path(TOOL.backup(state)["backed_up"])
            next(backup.rglob("ForzaProfile/ForzaProfile")).write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                TOOL.restore(state)
            with self.assertRaises(ValueError):
                TOOL.restore(Path(temporary) / "empty")


if __name__ == "__main__":
    unittest.main()
