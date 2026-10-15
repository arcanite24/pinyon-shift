"""What a copied Linux build needs on a Steam Deck: the archive extractor (for
DLC import and Rally preparation) with a relocatable library path, and a v4
build that stages librexruntime beside the game."""
import argparse
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pinyon_deck  # noqa: E402
import pinyon_setup  # noqa: E402


class DeckInstallTests(unittest.TestCase):
    def test_install_copies_and_marks_the_extractor_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp)
            for name in ("pinyon_shift", "pinyon_shift_fh1_archive_extract", "librexruntime.so",
                         "pinyon_shift_build.json", "pinyon_shift_fh1_texture_import",
                         "build.ninja"):
                (build / name).write_bytes(b"x")
            sent, commands = [], []
            deck = mock.Mock(root="pinyon-shift-dev")
            deck.run.side_effect = lambda command, **kwargs: commands.append(command)
            args = argparse.Namespace(build_directory=build, configuration="Release")
            with mock.patch.object(pinyon_deck, "Deck", return_value=deck), \
                    mock.patch.object(pinyon_deck, "sync",
                                      side_effect=lambda d, s, files, *rest, **kw: sent.extend(
                                          p.name for p in files)):
                self.assertEqual(pinyon_deck.install(args), 0)
            self.assertEqual(sorted(sent), ["librexruntime.so", "pinyon_shift",
                                            "pinyon_shift_build.json",
                                            "pinyon_shift_fh1_archive_extract"])
            self.assertEqual(commands, ["chmod +x pinyon-shift-dev/build/pinyon_shift "
                                        "pinyon-shift-dev/build/pinyon_shift_fh1_archive_extract"])

    def test_a_build_without_the_extractor_still_installs(self):
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp)
            (build / "pinyon_shift").write_bytes(b"x")
            commands = []
            deck = mock.Mock(root="d")
            deck.run.side_effect = lambda command, **kwargs: commands.append(command)
            args = argparse.Namespace(build_directory=build, configuration="Release")
            with mock.patch.object(pinyon_deck, "Deck", return_value=deck), \
                    mock.patch.object(pinyon_deck, "sync"):
                pinyon_deck.install(args)
            self.assertEqual(commands, ["chmod +x d/build/pinyon_shift"])


class RelocatableBuildTests(unittest.TestCase):
    def test_the_v4_build_stages_the_runtime_and_builds_the_extractor(self):
        self.assertIn("pinyon_shift_stage_rexruntime", pinyon_setup.V4_BUILD_TARGETS)
        self.assertIn("pinyon_shift_fh1_archive_extract", pinyon_setup.V4_BUILD_TARGETS)

    def test_the_linux_extractor_finds_the_runtime_beside_itself(self):
        text = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        block = re.search(r"set_target_properties\(pinyon_shift_fh1_archive_extract PROPERTIES"
                          r"(.*?)\)", text, re.S)
        self.assertIsNotNone(block)
        self.assertIn('INSTALL_RPATH "$ORIGIN', block.group(1))
        self.assertIn("BUILD_WITH_INSTALL_RPATH ON", block.group(1))


if __name__ == "__main__":
    unittest.main()
