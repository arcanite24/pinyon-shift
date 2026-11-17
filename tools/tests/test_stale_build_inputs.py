"""An update must not leave a build tree on inputs Ninja cannot see changed:
kit files unpacked with the archives' fixed 1980 date (#1097, #1098) and
precompiled headers made with another MSVC or kit (#1096)."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pinyon_setup  # noqa: E402

OLD = 315532800  # the archives' fixed date


class FreshenTimesTests(unittest.TestCase):
    def test_unpacked_files_get_the_current_time_once_per_key(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            header = root / "include" / "rex" / "ppc" / "context.h"
            header.parent.mkdir(parents=True)
            header.write_bytes(b"struct Context {};\n")
            os.utime(header, (OLD, OLD))
            before = time.time() - 5
            pinyon_setup.freshen_times(root, "rev-a")
            self.assertGreater(header.stat().st_mtime, before)
            # Same key: left alone, so a rebuild is not forced every setup.
            os.utime(header, (OLD, OLD))
            pinyon_setup.freshen_times(root, "rev-a")
            self.assertEqual(int(header.stat().st_mtime), OLD)
            # A new kit revision freshens again.
            pinyon_setup.freshen_times(root, "rev-b")
            self.assertGreater(header.stat().st_mtime, before)


class StalePchTests(unittest.TestCase):
    def build_tree(self, temp: str) -> tuple[Path, Path, Path]:
        tree = Path(temp) / "out"
        pch = tree / "CMakeFiles" / "pinyon_shift_recomp.dir" / "cmake_pch.hxx.pch"
        obj = tree / "CMakeFiles" / "pinyon_shift_recomp.dir" / "a.cpp.obj"
        pch.parent.mkdir(parents=True)
        pch.write_bytes(b"pch")
        obj.write_bytes(b"obj")
        return tree, pch, obj

    def run_drop(self, tree: Path, msvc: str, kit_root: Path) -> None:
        with mock.patch.object(pinyon_setup, "KIT", kit_root), \
                mock.patch.object(pinyon_setup, "toolchain_config",
                                  return_value={"rexglue": {"revision": "r1"}}):
            pinyon_setup.drop_stale_pch(tree, {"VCToolsVersion": msvc, "CXX": "clang++"})

    def test_pch_survives_an_unchanged_setup_and_goes_when_msvc_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            tree, pch, obj = self.build_tree(temp)
            kit = Path(temp) / "kit"
            # A tree from before the record loses its PCH once.
            self.run_drop(tree, "14.44.35229", kit)
            self.assertFalse(pch.exists())
            self.assertTrue(obj.exists())
            pch.write_bytes(b"pch")
            self.run_drop(tree, "14.44.35229", kit)
            self.assertTrue(pch.exists())
            self.run_drop(tree, "14.44.35230", kit)
            self.assertFalse(pch.exists())

    def test_pch_goes_when_the_kit_revision_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            tree, pch, _ = self.build_tree(temp)
            kit = Path(temp) / "kit"
            kit.mkdir()
            (kit / "kit.json").write_text('{"shiftglue_revision": "a"}', encoding="utf-8")
            self.run_drop(tree, "", kit)
            pch.write_bytes(b"pch")
            self.run_drop(tree, "", kit)
            self.assertTrue(pch.exists())
            (kit / "kit.json").write_text('{"shiftglue_revision": "b"}', encoding="utf-8")
            self.run_drop(tree, "", kit)
            self.assertFalse(pch.exists())

    def test_a_missing_tree_is_left_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "none"
            self.run_drop(missing, "", Path(temp))
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
