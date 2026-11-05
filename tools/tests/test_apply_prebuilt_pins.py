import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("apply_prebuilt_pins",
                                              ROOT / "tools" / "apply-prebuilt-pins.py")
PINS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PINS)

REVISION = "9e7e6a562a1ec31fac66cc97c53ffca080cfc3b0"


class ApplyPrebuiltPinsTest(unittest.TestCase):
    def assets(self, folder: Path, name: str, meta: dict) -> None:
        (folder / name).write_bytes(b"objects")
        (folder / f"{name}.json").write_text(json.dumps(meta), encoding="utf-8")

    def test_pins_host_objects_per_platform_and_variant(self):
        config = {"rexglue": {"revision": REVISION}}
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for variant in ("base", "v4"):
                self.assets(folder, f"host-objects-0.8.0-windows-x64-{variant}.zip",
                            {"kind": "host-objects", "platform": "windows-x64",
                             "variant": variant, "revision": REVISION, "version": "0.8.0"})
            changes = PINS.apply(config, folder, "https://example.invalid/v0.8.0/")
        self.assertEqual(len(changes), 2)
        pinned = config["host_objects"]["windows-x64"]
        self.assertEqual(sorted(pinned), ["base", "v4"])
        self.assertEqual(pinned["v4"]["url"],
                         "https://example.invalid/v0.8.0/host-objects-0.8.0-windows-x64-v4.zip")
        self.assertEqual(pinned["base"]["version"], "0.8.0")
        self.assertEqual(len(pinned["base"]["sha256"]), 64)

    def test_rejects_host_objects_from_another_revision(self):
        config = {"rexglue": {"revision": REVISION}}
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            self.assets(folder, "host-objects-0.8.0-android-arm64-base.tar.xz",
                        {"kind": "host-objects", "platform": "android-arm64",
                         "variant": "base", "revision": "0" * 40, "version": "0.8.0"})
            with self.assertRaises(SystemExit):
                PINS.apply(config, folder, "https://example.invalid/")

    def test_rejects_unknown_variant(self):
        config = {"rexglue": {"revision": REVISION}}
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            self.assets(folder, "host-objects-0.8.0-linux-x86_64-v5.tar.xz",
                        {"kind": "host-objects", "platform": "linux-x86_64",
                         "variant": "v5", "revision": REVISION, "version": "0.8.0"})
            with self.assertRaises(SystemExit):
                PINS.apply(config, folder, "https://example.invalid/")


if __name__ == "__main__":
    unittest.main()
