"""Xenia save import: XUID detection, no overwrite, and setting selection."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "import-xenia-save.ps1"


def run(*args):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOL), *args],
                          capture_output=True, text=True,
                          env=os.environ | {"PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME": "1"})


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell required")
class ImportXeniaSaveTests(unittest.TestCase):
    def fixture(self, root: Path, xuid: str = "E030000012345678") -> tuple[Path, Path]:
        title = root / "xenia" / "content" / xuid / "4D5309C9"
        profile = title / "00000001" / "ForzaProfile"
        profile.mkdir(parents=True)
        (profile / "ForzaProfile").write_bytes(b"imported")
        (title / "Headers" / "00000001").mkdir(parents=True)
        (title / "Headers" / "00000001" / "ForzaProfile.header").write_bytes(b"h")
        state = root / "state"
        native = state / "user" / "B13EBABEBABEBABE" / "4D5309C9" / "00000001" / "ForzaProfile"
        native.mkdir(parents=True)
        (native / "ForzaProfile").write_bytes(b"native")
        (state / "config").mkdir()
        (state / "config" / "pinyon_shift.toml").write_text("pinyon_shift_config_schema = 28\r\nuser_name = \"Ann\"\r\n")
        return title, state

    def test_imports_beside_native_save_and_selects_the_xuid(self):
        with tempfile.TemporaryDirectory() as directory:
            title, state = self.fixture(Path(directory))
            result = run("-StateRoot", str(state), "-Source", str(title))
            self.assertEqual(result.returncode, 0, result.stderr)
            copied = state / "user" / "E030000012345678" / "4D5309C9"
            self.assertEqual((copied / "00000001/ForzaProfile/ForzaProfile").read_bytes(), b"imported")
            self.assertTrue((copied / "Headers/00000001/ForzaProfile.header").is_file())
            native = state / "user/B13EBABEBABEBABE/4D5309C9/00000001/ForzaProfile/ForzaProfile"
            self.assertEqual(native.read_bytes(), b"native")
            config = (state / "config/pinyon_shift.toml").read_text()
            self.assertIn('user_xuid = "E030000012345678"\n', config)
            self.assertIn('user_name = "Ann"', config)
            self.assertEqual(len(list((state / "config/backups").glob("*.toml"))), 1)
            # A second import never overwrites the copied save.
            (title / "00000001/ForzaProfile/ForzaProfile").write_bytes(b"newer")
            result = run("-StateRoot", str(state), "-Source", str(title.parent))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("left unchanged", result.stderr)
            self.assertEqual((copied / "00000001/ForzaProfile/ForzaProfile").read_bytes(), b"imported")
            result = run("-StateRoot", str(state), "-Restore")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('user_xuid = "B13EBABEBABEBABE"', (state / "config/pinyon_shift.toml").read_text())
            self.assertTrue(copied.is_dir())

    def test_requires_a_usable_xuid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            title, state = self.fixture(root)
            loose = root / "loose" / "4D5309C9"
            shutil.copytree(title, loose)
            result = run("-StateRoot", str(state), "-Source", str(loose))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("-Xuid", result.stderr)
            for bad in ("0000000000000000", "00C0000000000001", "XYZ"):
                result = run("-StateRoot", str(state), "-Source", str(loose), "-Xuid", bad)
                self.assertNotEqual(result.returncode, 0, bad)
            result = run("-StateRoot", str(state), "-Source", str(loose), "-Xuid", "e0300000abcdef01")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((state / "user/E0300000ABCDEF01/4D5309C9/00000001/ForzaProfile/ForzaProfile").is_file())
            self.assertFalse(list((state / "user/E0300000ABCDEF01").glob("*.import-*")))

    def test_rejects_a_folder_without_a_save(self):
        with tempfile.TemporaryDirectory() as directory:
            _, state = self.fixture(Path(directory))
            empty = Path(directory) / "content" / "E030000012345678"
            empty.mkdir(parents=True)
            result = run("-StateRoot", str(state), "-Source", str(empty))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No Forza Horizon save", result.stderr)
            self.assertFalse((state / "user/E030000012345678").exists())


if __name__ == "__main__":
    unittest.main()
