"""tools/pinyon_setup.py and tools/pinyon_steam.py: the Linux and macOS
setup path (LX-3) and the Steam shortcut (LX-5.10)."""

import argparse
import hashlib
import io
import json
import runpy
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import pinyon_setup  # noqa: E402
import pinyon_steam  # noqa: E402

SECTOR = 2048


def make_image(path: Path, files: dict, offset: int = 0x2080000) -> None:
    """A tiny XDVDFS image: a root directory with files and one folder."""
    entries = []  # (name, sector, size, attributes)
    data_sector = 40
    blobs = {}
    for name, content in files.items():
        blobs[data_sector] = content
        entries.append((name, data_sector, len(content), 0x80))
        data_sector += max(1, (len(content) + SECTOR - 1) // SECTOR)
    # One subfolder, "media", holding one file.
    sub_content = b"inner file"
    blobs[data_sector] = sub_content
    sub_entry = struct.pack("<HHIIBB", 0, 0, data_sector, len(sub_content), 0x80, 5) + b"a.bin"
    sub_entry += b"\xff" * (-len(sub_entry) % 4)
    data_sector += 1
    sub_table_sector = data_sector
    blobs[sub_table_sector] = sub_entry
    data_sector += 1
    entries.append(("media", sub_table_sector, len(sub_entry), 0x10))
    # The root table: a right-leaning chain, as small as the format allows.
    table = b""
    records = []
    for name, sector, size, attributes in entries:
        records.append((name.encode(), sector, size, attributes))
    position = 0
    offsets = []
    for name, sector, size, attributes in records:
        offsets.append(position)
        length = 14 + len(name)
        position += length + (-length % 4)
    for index, (name, sector, size, attributes) in enumerate(records):
        right = offsets[index + 1] // 4 if index + 1 < len(records) else 0
        record = struct.pack("<HHIIBB", 0, right, sector, size, attributes, len(name)) + name
        table += record + b"\xff" * (-len(record) % 4)
    root_sector = 34
    with path.open("wb") as stream:
        stream.truncate(offset + (data_sector + 2) * SECTOR)
        stream.seek(offset + 32 * SECTOR)
        stream.write(pinyon_setup.XDVDFS_MAGIC + struct.pack("<II", root_sector, len(table)))
        stream.seek(offset + root_sector * SECTOR)
        stream.write(table)
        for sector, content in blobs.items():
            stream.seek(offset + sector * SECTOR)
            stream.write(content)


class DiscImageTests(unittest.TestCase):
    DISC_FILES = {"default.xex": b"disc-main", "SpeechFacade_default.xex": b"disc-speech",
                  "XMediaFacade_default.xex": b"disc-xmedia", "nxeart": b"disc-art",
                  "readme.txt": b"hello"}
    GOD_FILES = {name: data.replace(b"disc", b"god!") for name, data in DISC_FILES.items()}

    def test_reads_files_and_folders_from_an_xgd3_image(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "disc.iso"
            make_image(image, {"default.xex": b"xex" * 1000, "readme.txt": b"hello"})
            disc = pinyon_setup.DiscImage(image)
            try:
                self.assertEqual(disc.offset, 0x2080000)
                files = {path: (sector, size) for path, sector, size in disc.files()}
                self.assertEqual(set(files), {"default.xex", "readme.txt", "media/a.bin"})
                sector, size = files["default.xex"]
                target = Path(directory) / "out.xex"
                digest = disc.copy(sector, size, target)
                self.assertEqual(target.read_bytes(), b"xex" * 1000)
                self.assertEqual(digest, hashlib.sha256(b"xex" * 1000).hexdigest().upper())
            finally:
                disc.close()

    def test_rejects_a_file_that_is_not_a_disc_image(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "not.iso"
            image.write_bytes(b"\0" * (1 << 20))
            with self.assertRaises(pinyon_setup.SetupError):
                pinyon_setup.DiscImage(image)

    def test_catalog_check_names_missing_and_extra_files(self):
        expected = {"default.xex": {"guest_path": "default.xex"},
                    "media/a.zip": {"guest_path": "media/a.zip"}}
        mismatches = pinyon_setup.check_paths([("default.xex", 0, 1), ("extra.bin", 0, 1)],
                                              expected)
        self.assertIn("Missing: media/a.zip", mismatches)
        self.assertIn("Not in the supported dump: extra.bin", mismatches)
        self.assertEqual(pinyon_setup.check_paths([("DEFAULT.XEX", 0, 1), ("media/A.zip", 0, 1)],
                                                  expected), [])

    def catalog(self, files: dict, alternate=None) -> tuple[dict, dict]:
        """A dump with three executables and optional re-signed files."""
        entries = {name.lower(): {"guest_path": name, "size_bytes": len(content),
                                  "sha256": hashlib.sha256(content).hexdigest().upper()}
                   for name, content in files.items()}
        entries["media/a.bin"] = {"guest_path": "media/a.bin", "size_bytes": 10,
                                  "sha256": hashlib.sha256(b"inner file").hexdigest().upper()}
        executables = [entries[name.lower()] for name in
                       ("default.xex", "SpeechFacade_default.xex", "XMediaFacade_default.xex")]
        dump = {"id": "test", "executables": executables}
        if alternate:
            dump["executable_revisions"] = [{"id": "games-on-demand", "files": [
                dict(entries[name.lower()], size_bytes=len(data),
                     sha256=hashlib.sha256(data).hexdigest().upper())
                for name, data in alternate.items() if data != files[name]]}]
        return dump, entries

    def test_executables_come_out_first_and_the_rest_waits_for_the_swap(self):
        # TP-7: the build starts on the executables while extraction runs.
        files = {"default.xex": b"xex" * 1000, "SpeechFacade_default.xex": b"speech",
                 "XMediaFacade_default.xex": b"xmedia", "readme.txt": b"hello"}
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "disc.iso"
            make_image(image, files)
            game = Path(directory) / "game" / "base"
            with patch.object(pinyon_setup, "load_catalog", return_value=self.catalog(files)), \
                    patch.object(pinyon_setup, "GAME", game):
                pinyon_setup.copy_executables(image, game)
                self.assertEqual(sorted(path.name for path in game.iterdir()),
                                 ["SpeechFacade_default.xex", "XMediaFacade_default.xex",
                                  "default.xex"])
                dump, revision, staging = pinyon_setup.Extraction(image).result()
                self.assertEqual(dump["id"], "test")
                self.assertEqual(revision, "disc")
                self.assertEqual((staging / "media" / "a.bin").read_bytes(), b"inner file")
                # The executables alone are not a game until the swap.
                self.assertFalse(pinyon_setup.game_ready())
                pinyon_setup.replace_game(staging)
                self.assertFalse(staging.exists())
                self.assertTrue((game / "readme.txt").is_file())
                self.assertTrue(pinyon_setup.game_ready())

    def test_another_disc_fails_before_anything_is_built(self):
        files = self.DISC_FILES
        dump, expected = self.catalog(files, self.GOD_FILES)
        dump["executables"][0] = dict(dump["executables"][0], sha256="0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "disc.iso"
            make_image(image, files)
            with patch.object(pinyon_setup, "load_catalog", return_value=(dump, expected)):
                with self.assertRaises(pinyon_setup.SetupError):
                    pinyon_setup.copy_executables(image, Path(directory) / "out")
                with self.assertRaises(pinyon_setup.SetupError):
                    pinyon_setup.copy_executables(image, Path(directory) / "posix", allow_revisions=True)
            make_image(image, dict(files, **{"extra.bin": b"x"}))
            with patch.object(pinyon_setup, "load_catalog", return_value=self.catalog(files)):
                with self.assertRaises(pinyon_setup.SetupError):
                    pinyon_setup.copy_executables(image, Path(directory) / "out2")

    def test_early_copy_accepts_disc_and_opt_in_god_but_windows_stays_disc_only(self):
        windows_copy = runpy.run_path(str(ROOT / "tools/copy-disc-executables.py"))["main"]
        for revision, files in (("disc", self.DISC_FILES), ("games-on-demand", self.GOD_FILES)):
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                image = root / "disc.iso"
                make_image(image, files, offset=0)
                with patch.object(pinyon_setup, "load_catalog", return_value=self.catalog(
                        self.DISC_FILES, self.GOD_FILES)):
                    pinyon_setup.copy_executables(image, root / "posix", allow_revisions=True)
                    copied = {p.name: p.read_bytes() for p in (root / "posix").iterdir()}
                    self.assertEqual(copied, {p: data for p, data in files.items()
                                              if p.endswith(".xex")})
                    with redirect_stderr(io.StringIO()):
                        result = windows_copy(["--iso", str(image), "--output", str(root / "win")])
                    self.assertEqual(result, 0 if revision == "disc" else 1)

    def test_early_copy_rejects_mixed_unknown_and_wrong_sized_executables(self):
        for name in (p for p in self.DISC_FILES if p.endswith(".xex")):
            for fault, data in (("mixed", self.GOD_FILES[name]),
                                ("unknown", b"?" * len(self.DISC_FILES[name])),
                                ("size", self.DISC_FILES[name] + b"!")):
                with self.subTest(name=name, fault=fault), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    image = root / "disc.iso"
                    make_image(image, dict(self.DISC_FILES, **{name: data}), offset=0)
                    with patch.object(pinyon_setup, "load_catalog", return_value=self.catalog(
                            self.DISC_FILES, self.GOD_FILES)):
                        with self.assertRaises(pinyon_setup.SetupError) as caught:
                            pinyon_setup.copy_executables(image, root / "out", allow_revisions=True)
                        self.assertEqual(caught.exception.stage, "verify")

    def test_extract_returns_revision_and_destination_for_both_replacement_modes(self):
        for revision, files in (("disc", self.DISC_FILES), ("games-on-demand", self.GOD_FILES)):
            for replace in (False, True):
                with self.subTest(revision=revision, replace=replace), \
                        tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    image, game = root / "disc.iso", root / "base"
                    make_image(image, files, offset=0)
                    game.mkdir()
                    (game / "old").write_bytes(b"previous install")
                    with patch.object(pinyon_setup, "load_catalog", return_value=self.catalog(
                            self.DISC_FILES, self.GOD_FILES)), patch.object(pinyon_setup, "GAME", game):
                        dump, actual_revision, destination = pinyon_setup.extract_iso(
                            image, lambda *_: None, replace=replace)
                        self.assertEqual((dump["id"], actual_revision), ("test", revision))
                        self.assertEqual(destination, game if replace else root / "base.extracting")
                        self.assertEqual((game / "old").exists(), not replace)
                        for name, data in dict(files, **{"media/a.bin": b"inner file"}).items():
                            self.assertEqual((destination / name).read_bytes(), data)
                        self.assertEqual(pinyon_setup.game_ready(), replace)

    def test_folder_accepts_each_complete_revision(self):
        for revision, files in (("disc", self.DISC_FILES), ("games-on-demand", self.GOD_FILES)):
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, game = root / "source", root / "base"
                for name, data in dict(files, **{"media/a.bin": b"inner file"}).items():
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
                with patch.object(pinyon_setup, "load_catalog", return_value=self.catalog(
                        self.DISC_FILES, self.GOD_FILES)), patch.object(pinyon_setup, "GAME", game):
                    dump, actual_revision = pinyon_setup.verify_folder(source, lambda *_: None)
                    self.assertEqual((dump["id"], actual_revision), ("test", revision))
                    self.assertTrue(pinyon_setup.game_ready())
                    for name, data in files.items():
                        self.assertEqual((game / name).read_bytes(), data)
                        self.assertEqual((source / name).read_bytes(), data)

    def test_full_verification_rejects_all_bad_revision_files_before_publish(self):
        # nxeart is not read by early copy, but it must agree at publication.
        for name in self.DISC_FILES:
            faults = [("unknown", b"?" * len(self.DISC_FILES[name])),
                      ("size", self.DISC_FILES[name] + b"!")]
            if self.GOD_FILES[name] != self.DISC_FILES[name]:
                faults.append(("mixed", self.GOD_FILES[name]))
            for fault, data in faults:
                for source_kind in ("iso", "folder"):
                    with self.subTest(name=name, fault=fault, source=source_kind), \
                            tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        game = root / "base"
                        game.mkdir()
                        (game / "old").write_bytes(b"previous install")
                        files = dict(self.DISC_FILES, **{name: data})
                        source = root / "source"
                        if source_kind == "iso":
                            make_image(source, files, offset=0)
                            verify = pinyon_setup.extract_iso
                        else:
                            for path, content in dict(files, **{"media/a.bin": b"inner file"}).items():
                                target = source / path
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(content)
                            verify = pinyon_setup.verify_folder
                        with patch.object(pinyon_setup, "load_catalog", return_value=self.catalog(
                                self.DISC_FILES, self.GOD_FILES)), \
                                patch.object(pinyon_setup, "GAME", game):
                            with self.assertRaises(pinyon_setup.SetupError) as caught:
                                verify(source, lambda *_: None)
                            self.assertEqual(caught.exception.stage, "verify")
                            self.assertEqual(list(game.iterdir()), [game / "old"])
                            self.assertEqual((game / "old").read_bytes(), b"previous install")
                            self.assertFalse((root / "base.extracting").exists())

    def test_background_extraction_preserves_tuple_and_errors(self):
        result = ({"id": "test"}, "games-on-demand", Path("staging"))
        with patch.object(pinyon_setup, "extract_iso", return_value=result) as extract:
            self.assertIs(pinyon_setup.Extraction(Path("disc.iso")).result(), result)
            self.assertEqual(extract.call_args.args[0], Path("disc.iso"))
            self.assertEqual(extract.call_args.kwargs, {"replace": False})
        for error in (pinyon_setup.SetupError("bad dashboard art", "verify"), OSError("read failed")):
            with self.subTest(error=error), patch.object(pinyon_setup, "extract_iso", side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    pinyon_setup.Extraction(Path("disc.iso")).result()
                self.assertIs(caught.exception, error)

    def test_ready_requires_no_incomplete_staging_and_a_supported_main_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory) / "base"
            game.mkdir()
            with patch.object(pinyon_setup, "load_catalog", return_value=self.catalog(
                    self.DISC_FILES, self.GOD_FILES)), patch.object(pinyon_setup, "GAME", game):
                for files in (self.DISC_FILES, self.GOD_FILES):
                    for name, data in files.items():
                        (game / name).write_bytes(data)
                    self.assertTrue(pinyon_setup.game_ready())
                    staging = game.with_name("base.extracting")
                    staging.mkdir()
                    self.assertFalse(pinyon_setup.game_ready())
                    staging.rmdir()
                (game / "default.xex").write_bytes(b"?" * len(self.DISC_FILES["default.xex"]))
                self.assertFalse(pinyon_setup.game_ready())
                (game / "default.xex").write_bytes(self.DISC_FILES["default.xex"])
                (game / "SpeechFacade_default.xex").write_bytes(b"")
                self.assertFalse(pinyon_setup.game_ready())
                (game / "SpeechFacade_default.xex").unlink()
                self.assertFalse(pinyon_setup.game_ready())

    def setup_environment(self, stack, root):
        """Run the real setup control flow without tools, downloads or builds."""
        for name, value in {"ROOT": root, "LOCAL": root / ".local",
                            "LOGS": root / ".local/logs", "GAME": root / ".local/game/base"}.items():
            stack.enter_context(patch.object(pinyon_setup, name, value))
        returns = {"Progress": pinyon_setup._Quiet(), "host_platform": "macos-arm64",
                   "toolchain_config": {"posix": {"macos-arm64": {
                       "disk_space_gb": {"first_build": 1}}}},
                   "load_catalog": self.catalog(self.DISC_FILES, self.GOD_FILES),
                   "provision_python": Path(sys.executable), "free_space_gb": 100,
                   "used_space_gb": 0, "provision": {}, "install_kit": root / "kit",
                   "prepare_shiftglue": root / "sdk", "build": root / "pinyon_shift"}
        calls = {name: stack.enter_context(patch.object(pinyon_setup, name, return_value=value))
                 for name, value in returns.items()}
        calls["prefetch"] = stack.enter_context(patch.object(pinyon_setup, "prefetch"))
        stack.enter_context(patch.object(pinyon_setup.subprocess, "run",
                                         side_effect=AssertionError("unexpected subprocess")))
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(redirect_stderr(io.StringIO()))
        parser = argparse.ArgumentParser()
        pinyon_setup.add_parser(parser.add_subparsers())
        return parser.parse_args(["setup", "--jobs", "2"]), calls

    def test_setup_records_the_actual_revision_for_iso_folder_and_existing_game(self):
        for source_kind in ("iso", "extracted", "existing"):
            for revision, files in (("disc", self.DISC_FILES), ("games-on-demand", self.GOD_FILES)):
                with self.subTest(source=source_kind, revision=revision), \
                        tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
                    root = Path(directory)
                    args, calls = self.setup_environment(stack, root)
                    game = pinyon_setup.GAME
                    if source_kind == "iso":
                        args.iso = root / "disc.iso"
                        make_image(args.iso, files, offset=0)
                    else:
                        source = game if source_kind == "existing" else root / "source"
                        for name, data in dict(files, **{"media/a.bin": b"inner file"}).items():
                            path = source / name
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(data)
                        if source_kind == "extracted":
                            args.extracted = source
                    # Both the prebuilt kit and source fallback keep the same setup flow.
                    use_kit = revision == "disc"
                    calls["install_kit"].return_value = root / "kit" if use_kit else None

                    def provision(*_):
                        if source_kind != "existing":
                            calls["prefetch"].return_value.join.assert_called_once_with()
                        return {}

                    def build(progress, tools, sdk, python, platform, jobs, configuration):
                        self.assertEqual(sdk, root / ("kit" if use_kit else "sdk"))
                        self.assertEqual((platform, jobs, configuration), ("macos-arm64", 2, "Release"))
                        self.assertEqual((game / "default.xex").read_bytes(), files["default.xex"])
                        if source_kind == "iso":
                            # Extraction may have finished in staging, but has not been published.
                            self.assertEqual({p.name for p in game.iterdir()},
                                             {p for p in files if p.endswith(".xex")})

                    calls["provision"].side_effect = provision
                    calls["build"].side_effect = build
                    self.assertEqual(pinyon_setup.run_setup(args), 0)
                    calls["build"].assert_called_once()
                    if use_kit:
                        calls["prepare_shiftglue"].assert_not_called()
                    else:
                        calls["prepare_shiftglue"].assert_called_once()
                    if source_kind == "existing":
                        calls["prefetch"].assert_not_called()
                    else:
                        calls["prefetch"].assert_called_once()
                    state = json.loads((pinyon_setup.LOCAL / "setup-state.json").read_text())
                    self.assertEqual((state["dump_id"], state["executable_revision"],
                                      state["source_kind"], state["result"]),
                                     ("test", revision, source_kind, "ready"))
                    self.assertEqual((game / "nxeart").read_bytes(), files["nxeart"])
                    self.assertTrue(pinyon_setup.game_ready())

    def test_failed_early_or_background_verification_removes_only_the_partial_game(self):
        for name in ("SpeechFacade_default.xex", "nxeart"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory, \
                    ExitStack() as stack:
                root = Path(directory)
                args, calls = self.setup_environment(stack, root)
                args.iso = root / "disc.iso"
                # Only the background pass checks nxeart; a mixed facade fails early.
                make_image(args.iso, dict(self.DISC_FILES, **{name: self.GOD_FILES[name]}), offset=0)
                self.assertEqual(pinyon_setup.run_setup(args), 1)
                self.assertEqual(calls["build"].call_count, 1 if name == "nxeart" else 0)
                self.assertFalse((pinyon_setup.LOCAL / "setup-state.json").exists())
                self.assertFalse(pinyon_setup.GAME.exists())
                self.assertFalse(pinyon_setup.game_ready())
                error = json.loads((pinyon_setup.LOGS / "setup-error.json").read_text())
                self.assertEqual(error["stage"], "verify")
                self.assertIn("different releases", error["message"])

    def test_failed_rebuild_preserves_the_existing_game(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            args, calls = self.setup_environment(stack, root)
            game = pinyon_setup.GAME
            game.mkdir(parents=True)
            for name, data in self.DISC_FILES.items():
                (game / name).write_bytes(data)
            calls["build"].side_effect = pinyon_setup.SetupError("build failed", "build")
            self.assertEqual(pinyon_setup.run_setup(args), 1)
            self.assertTrue(pinyon_setup.game_ready())
            for name, data in self.DISC_FILES.items():
                self.assertEqual((game / name).read_bytes(), data)

    def test_verify_only_checks_inventory_without_copying_building_or_prefetching(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            args, calls = self.setup_environment(stack, root)
            args.iso, args.verify_only = root / "disc.iso", True
            files = dict(self.DISC_FILES, **{"default.xex": b"not an accepted executable"})
            make_image(args.iso, files, offset=0)
            with patch.object(pinyon_setup, "copy_executables") as copy, \
                    patch.object(pinyon_setup, "Extraction") as extraction:
                self.assertEqual(pinyon_setup.run_setup(args), 0)
                copy.assert_not_called()
                extraction.assert_not_called()
            make_image(args.iso, dict(files, **{"extra.bin": b"extra"}), offset=0)
            self.assertEqual(pinyon_setup.run_setup(args), 1)
            for name in ("prefetch", "provision", "install_kit", "prepare_shiftglue", "build"):
                calls[name].assert_not_called()
            self.assertFalse(pinyon_setup.GAME.exists())
            self.assertFalse((pinyon_setup.LOCAL / "setup-state.json").exists())

    def test_the_supported_catalog_matches_the_dump_manifest(self):
        dump, expected = pinyon_setup.load_catalog()
        self.assertEqual(len(expected), dump["extraction"]["file_count"])
        self.assertIn("default.xex", expected)

    def test_games_on_demand_executables_are_a_second_accepted_revision(self):
        """The Games on Demand release of the same build ships re-signed
        executables and dashboard art; every other file matches the disc."""
        dump, expected = pinyon_setup.load_catalog()
        accepted = pinyon_setup.executable_hashes(dump, expected)
        revisions = [r["id"] for r in dump["executable_revisions"]]
        self.assertEqual(revisions, ["games-on-demand"])
        for item in dump["executable_revisions"][0]["files"]:
            key = item["guest_path"].lower()
            self.assertIn(key, expected)
            self.assertEqual(item["size_bytes"], expected[key]["size_bytes"])
            self.assertNotEqual(item["sha256"], expected[key]["sha256"])
            self.assertRegex(item["sha256"], r"^[0-9A-F]{64}$")
            self.assertEqual(sorted(accepted[key].values()), ["disc", "games-on-demand"])
        self.assertEqual(sorted(accepted), ["default.xex", "nxeart", "speechfacade_default.xex",
                                            "xmediafacade_default.xex"])

    def test_executable_revision_refuses_mixed_or_unknown_executables(self):
        dump, expected = pinyon_setup.load_catalog()
        disc = {e["guest_path"]: e["sha256"] for e in dump["executables"]}
        god = {f["guest_path"]: f["sha256"] for f in dump["executable_revisions"][0]["files"]}
        self.assertEqual(pinyon_setup.executable_revision(disc, dump, expected), "disc")
        self.assertEqual(pinyon_setup.executable_revision(god, dump, expected), "games-on-demand")
        mixed = dict(disc, **{"nxeart": god["nxeart"]})
        with self.assertRaises(pinyon_setup.SetupError):
            pinyon_setup.executable_revision(mixed, dump, expected)
        unknown = dict(disc, **{"default.xex": "00" * 32})
        with self.assertRaises(pinyon_setup.SetupError):
            pinyon_setup.executable_revision(unknown, dump, expected)


class ToolchainPinTests(unittest.TestCase):
    def test_posix_downloads_are_https_and_sha256_pinned(self):
        config = json.loads((ROOT / "config/release-toolchain.json").read_text(encoding="utf-8"))
        for name in ("linux-x86_64", "macos-arm64", "macos-x86_64"):
            tools = config["posix"][name]
            self.assertGreater(tools["disk_space_gb"]["first_build"], 0)
            for key, item in tools.items():
                if key == "disk_space_gb":
                    continue
                self.assertTrue(item["url"].startswith("https://"), key)
                self.assertRegex(item["sha256"], r"^[0-9A-F]{64}$", key)
                self.assertTrue(item["install_path"].startswith(".local/toolchain/"), key)
        linux = config["posix"]["linux-x86_64"]
        for key in ("cmake", "ninja", "llvm", "sysroot"):
            self.assertIn(key, linux)
        # The sysroot matches the one the toolchain file was written for.
        self.assertIn("sniper", linux["sysroot"]["url"])

    def test_only_libxml2_and_its_icu_are_given_to_the_host_programs(self):
        # #472: ld.lld and wayland-scanner get libxml2.so.2 from the sysroot;
        # zlib, liblzma and everything else stay the host's.
        match = pinyon_setup.HOST_LIBRARY.match
        for name in ("libxml2.so.2", "libicuuc.so.67", "libicudata.so.67"):
            self.assertTrue(match(name), name)
        for name in ("libxml2.so", "libxml2.so.2.9.10", "libicuuc.so", "libicuuc.so.67.1",
                     "libz.so.1", "liblzma.so.5", "libicui18n.so.67"):
            self.assertFalse(match(name), name)

    @unittest.skipIf(sys.platform == "win32", "symlinks and sh wrappers")
    def test_host_wrappers_point_at_the_pinned_programs(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            libs = temp / "sysroot/usr/lib/x86_64-linux-gnu"
            libs.mkdir(parents=True)
            for name in ("libxml2.so.2", "libicuuc.so.67", "libz.so.1"):
                (libs / name).write_bytes(b"")
            tools = {"llvm": {"install_path": str(temp / "llvm")},
                     "sysroot": {"install_path": str(temp / "sysroot")}}
            folder = temp / "linux-x86_64"
            folder.mkdir()
            pinyon_setup.prepare_host_wrappers(folder, tools)
            self.assertEqual(sorted(p.name for p in (folder / "host-libs").iterdir()),
                             ["libicuuc.so.67", "libxml2.so.2"])
            wrapper = (folder / "bin/ld.lld").read_text(encoding="utf-8")
            self.assertIn(str(temp / "llvm/bin/ld.lld"), wrapper)
            self.assertIn("host-libs", wrapper)
            self.assertTrue((folder / "bin/wayland-scanner").stat().st_mode & 0o100)

    def test_an_unfinished_configure_starts_over(self):
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp)
            (build / "CMakeFiles").mkdir()
            (build / "CMakeCache.txt").write_text("CMAKE_EXE_LINKER_FLAGS:STRING=old\n")
            pinyon_setup.discard_unfinished_configure(build)
            self.assertFalse((build / "CMakeCache.txt").exists())
            self.assertFalse((build / "CMakeFiles").exists())
            # A finished configure keeps its cache.
            (build / "CMakeCache.txt").write_text("")
            (build / "build.ninja").write_text("")
            pinyon_setup.discard_unfinished_configure(build)
            self.assertTrue((build / "CMakeCache.txt").exists())

    def test_a_build_whose_translation_rewrote_the_lists_runs_again(self):
        with tempfile.TemporaryDirectory() as temp:
            build = Path(temp) / "build"
            generated = Path(temp) / "generated"
            build.mkdir()
            (build / "build.ninja").write_text("")
            for tree in ("default", "speech", "xmedia"):
                (generated / tree).mkdir(parents=True)
                (generated / tree / "sources.cmake").write_text("")
            old = (build / "build.ninja").stat().st_mtime - 60
            for tree in ("default", "speech", "xmedia"):
                pinyon_setup.os.utime(generated / tree / "sources.cmake", (old, old))
            logs = []

            def fake_run(command, log, *rest):
                logs.append(log.name)
                if len(logs) == 1:
                    if rewrite:
                        # The translation step rewrote one list mid-build.
                        newer = (build / "build.ninja").stat().st_mtime + 60
                        pinyon_setup.os.utime(generated / "xmedia" / "sources.cmake",
                                              (newer, newer))
                    raise pinyon_setup.SetupError("Building the game failed", "build")

            saved = pinyon_setup.run_logged
            pinyon_setup.run_logged = fake_run
            try:
                rewrite = True
                pinyon_setup.run_game_build(["cmake"], Path(temp) / "preview-build.log",
                                            None, 30, "Building the game", {}, build, generated)
                self.assertEqual(logs, ["preview-build.log", "preview-build-retry.log"])
                # Lists older than the graph: the failure is real and is not retried.
                for tree in ("default", "speech", "xmedia"):
                    pinyon_setup.os.utime(generated / tree / "sources.cmake", (old, old))
                logs.clear()
                rewrite = False
                with self.assertRaises(pinyon_setup.SetupError):
                    pinyon_setup.run_game_build(["cmake"], Path(temp) / "preview-build.log",
                                                None, 30, "Building the game", {}, build,
                                                generated)
                self.assertEqual(logs, ["preview-build.log"])
            finally:
                pinyon_setup.run_logged = saved

    def test_the_cpu_baseline_follows_the_build_cpu(self):
        deck = ("fpu sse4_1 sse4_2 movbe popcnt aes xsave avx f16c rdrand abm fma bmi1 "
                "avx2 bmi2")
        cases = {deck: "v3", "sse4_1 fma avx avx2": "fma", "sse4_1 sse4_2": "sse4.1"}
        with tempfile.TemporaryDirectory() as temp:
            cpuinfo = Path(temp) / "cpuinfo"
            saved = pinyon_setup.os.environ.pop("PINYON_SHIFT_CPU_BASELINE", None)
            try:
                for flags, expected in cases.items():
                    cpuinfo.write_text(f"processor\t: 0\nflags\t\t: {flags}\n")
                    self.assertEqual(pinyon_setup.cpu_baseline("linux-x86_64", cpuinfo),
                                     expected)
                pinyon_setup.os.environ["PINYON_SHIFT_CPU_BASELINE"] = "sse4.1"
                cpuinfo.write_text(f"flags\t\t: {deck}\n")
                self.assertEqual(pinyon_setup.cpu_baseline("linux-x86_64", cpuinfo), "sse4.1")
                pinyon_setup.os.environ["PINYON_SHIFT_CPU_BASELINE"] = "avx512"
                with self.assertRaises(pinyon_setup.SetupError):
                    pinyon_setup.cpu_baseline("linux-x86_64", cpuinfo)
            finally:
                pinyon_setup.os.environ.pop("PINYON_SHIFT_CPU_BASELINE", None)
                if saved is not None:
                    pinyon_setup.os.environ["PINYON_SHIFT_CPU_BASELINE"] = saved
        self.assertEqual(pinyon_setup.cpu_baseline("macos-arm64"), "native")

    def test_an_intel_mac_picks_its_baseline_from_sysctl(self):
        # Experimental Intel Mac port: sysctl's feature names map to
        # /proc/cpuinfo's, and Rosetta keeps SSE4.1.
        def fake(features, translated="0"):
            def run(command, **_):
                keys = command[2:]
                out = translated if keys == ["sysctl.proc_translated"] else features
                return pinyon_setup.subprocess.CompletedProcess(command, 0, out + "\n", "")
            return run
        kaby_lake = ("FPU SSE SSE2 SSE3 SSSE3 SSE4.1 SSE4.2 FMA MOVBE POPCNT AVX F16C "
                     "AVX2 BMI1 BMI2 SYSCALL LZCNT")
        flags = pinyon_setup.macos_cpu_flags(fake(kaby_lake))
        self.assertTrue(set(pinyon_setup.V3_CPU_FLAGS) <= flags)
        self.assertEqual(pinyon_setup.macos_cpu_flags(fake(kaby_lake, translated="1")), set())
        saved = pinyon_setup.macos_cpu_flags
        try:
            pinyon_setup.macos_cpu_flags = lambda: flags
            self.assertEqual(pinyon_setup.cpu_baseline("macos-x86_64"), "v3")
            pinyon_setup.macos_cpu_flags = lambda: set()
            self.assertEqual(pinyon_setup.cpu_baseline("macos-x86_64"), "sse4.1")
        finally:
            pinyon_setup.macos_cpu_flags = saved

    def test_intel_mac_presets_exist_for_setup(self):
        presets = json.loads((ROOT / "CMakePresets.json").read_text(encoding="utf-8"))
        configure = {item["name"]: item for item in presets["configurePresets"]}
        build = {item["name"] for item in presets["buildPresets"]}
        game = pinyon_setup.PRESETS["macos-x86_64"]["game"]
        for suffix in ("release", "v4"):
            self.assertIn(f"{game}-{suffix}", configure)
            self.assertIn(f"{game}-{suffix}", build)
        base = configure["macos-amd64-base"]["cacheVariables"]
        self.assertEqual(base["CMAKE_OSX_ARCHITECTURES"], "x86_64")
        self.assertIn("-msse4.1", base["CMAKE_CXX_FLAGS"])
        # The kit, the translator and the game share one deployment target.
        target = pinyon_setup.MACOS_DEPLOYMENT_TARGET["macos-x86_64"]
        self.assertEqual(base["CMAKE_OSX_DEPLOYMENT_TARGET"], target)
        self.assertIn(f"-DCMAKE_OSX_DEPLOYMENT_TARGET={target}",
                      pinyon_setup.KIT_CACHE["macos-x86_64"])
        sdk_presets = ROOT / "thirdparty/shiftglue-sdk/CMakePresets.json"
        if not sdk_presets.is_file():
            return  # a checkout without the submodule
        sdk = json.loads(sdk_presets.read_text(encoding="utf-8"))
        self.assertIn(pinyon_setup.PRESETS["macos-x86_64"]["sdk"],
                      {item["name"] for item in sdk["configurePresets"]})

    def test_the_payload_ships_the_posix_setup(self):
        script = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        include = script.split("$include = @(", 1)[1].split("\n)", 1)[0]
        for required in ("tools/pinyon_setup.py", "tools/pinyon_steam.py", "config/steam",
                         "tools/verify-codegen-log.py", "cmake"):
            self.assertIn(f"'{required}'", include)
            self.assertTrue((ROOT / required).exists(), required)


class MacPchTests(unittest.TestCase):
    def prepare_failure(self, directory):
        build = directory / "sdk/out/build/mac-arm64"
        build.mkdir(parents=True)
        log = directory / "rexglue-build.log"
        output = "src/filesystem/CMakeFiles/rexfilesystem.dir/Release/cmake_pch.hxx.pch"
        log.write_text(f"FAILED: [code=1] {output}\nno member named 'bit_cast'\n")
        args = ["/usr/bin/clang++", "-std=c++2b", "-arch", "arm64", "-isysroot",
                "/SDK path", "-I/include path", "-DKEEP=1", "-Xclang", "-emit-pch",
                "-Xclang", "-include", "-Xclang", "/PCH path/cmake_pch.hxx",
                "-x", "c++-header", "-MD", "-MT", output, "-MF", output + ".d",
                "-o", output, "-c", "/PCH path/cmake_pch.hxx.cxx"]
        # Include another config to ensure only the failed command is replayed.
        entries = [{"directory": str(build), "command": pinyon_setup.shlex.join(args),
                    "file": args[-1], "output": output}]
        entries.append(dict(entries[0], output=output.replace("/Release/", "/Debug/")))
        (build / "compile_commands.json").write_text(json.dumps(entries))
        return build, log

    def test_diagnostics_retain_the_failed_pch_flags_without_writing_build_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            build, log = self.prepare_failure(Path(temp))
            original = log.read_bytes()
            environment = {"CPATH": "/custom headers", "TOKEN": "not-for-the-log"}

            def fake_run(command, **kwargs):
                kwargs["stdout"].write("compiler output\n")
                return subprocess.CompletedProcess(command, 1)

            with patch.object(pinyon_setup.subprocess, "run", side_effect=fake_run) as run:
                diagnostic = pinyon_setup.diagnose_macos_pch(build, log, environment)
            self.assertEqual(run.call_count, 5)
            headers, macros = [call.args[0] for call in run.call_args_list[-2:]]
            for command in (headers, macros):
                self.assertIn("-I/include path", command)
                self.assertIn("/SDK path", command)
                self.assertIn("/PCH path/cmake_pch.hxx", command)
                self.assertIn("-DKEEP=1", command)
                self.assertNotIn("-emit-pch", command)
                for removed in ("-c", "-MD", "-MF", "-MT"):
                    self.assertNotIn(removed, command)
            self.assertEqual(headers[-9:], ["-E", "-H", "-v", "-Xclang", "-header-include-file",
                                           "-Xclang", "-", "-o", pinyon_setup.os.devnull])
            self.assertEqual(macros[-2:], ["-E", "-dM"])
            for call in run.call_args_list:
                self.assertIs(call.kwargs["env"], environment)
                self.assertEqual(call.kwargs["cwd"], str(build))
            text = diagnostic.read_text()
            self.assertIn("CPATH=/custom headers", text)
            self.assertIn("exit: 1", text)
            self.assertNotIn("not-for-the-log", text)
            self.assertEqual(log.read_bytes(), original)
            self.assertEqual(sorted(p.name for p in build.iterdir()), ["compile_commands.json"])

    def test_non_pch_failure_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "build.log"
            log.write_text("FAILED: other.cpp.o\n")
            with patch.object(pinyon_setup.subprocess, "run") as run:
                self.assertIsNone(pinyon_setup.diagnose_macos_pch(Path(temp), log, {}))
                run.assert_not_called()

    def test_missing_database_and_failed_probe_preserve_the_translator_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build, log = self.prepare_failure(root)
            for failure in (FileNotFoundError("compiler missing"),
                            subprocess.TimeoutExpired("clang++", 30), None):
                if failure is None:
                    (build / "compile_commands.json").unlink()
                with patch.object(pinyon_setup, "LOGS", root), \
                        patch.object(pinyon_setup.subprocess, "run", side_effect=failure), \
                        patch.object(pinyon_setup, "run_logged") as run:
                    run.side_effect = [None, pinyon_setup.SetupError("translator failed", "build")]
                    with self.assertRaisesRegex(pinyon_setup.SetupError, "translator failed") as caught:
                        pinyon_setup.build(None, {"cmake": "cmake"}, root / "sdk",
                                           Path(sys.executable), "macos-arm64", 2)
                self.assertEqual(caught.exception.stage, "build")
                self.assertIn("rexglue-pch-diagnostics.log", str(caught.exception))
                self.assertIn("-DCMAKE_EXPORT_COMPILE_COMMANDS=ON", run.call_args_list[0].args[0])
                self.assertIn("Could not finish PCH diagnostics", (root /
                              "rexglue-pch-diagnostics.log").read_text())

    @unittest.skipUnless(sys.platform == "darwin", "native AppleClang PCH regression")
    def test_types_bit_apis_compile_as_a_pch_and_can_be_consumed(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            header = temp / "bit-apis.h"
            header.write_text("""#include <rex/types.h>
static_assert(std::bit_cast<uint32_t>(1.0f) == 0x3f800000);
static_assert(std::byteswap(uint32_t{0x12345678}) == 0x78563412);
static_assert(rex::byte_swap(uint16_t{0x1234}) == 0x3412);
static_assert(rex::byte_swap(uint32_t{0x12345678}) == 0x78563412);
static_assert(rex::byte_swap(uint64_t{0x0123456789abcdef}) == 0xefcdab8967452301);
""")
            source = temp / "cmake_pch.hxx.cxx"
            source.write_text("static_assert(rex::byte_swap(uint8_t{42}) == 42);\n")
            common = ["/usr/bin/clang++", "-std=c++23", "-arch", "arm64",
                      "-I" + str(ROOT / "thirdparty/shiftglue-sdk/include")]
            pch = temp / "bit-apis.pch"
            for command in (common + ["-x", "c++-header", str(header), "-o", str(pch)],
                            common + ["-include-pch", str(pch), "-fsyntax-only", str(source)]):
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # CMake force-includes its PCH header; -H alone omits that header tree.
            output = "cmake_pch.hxx.pch"
            command = common + ["-Xclang", "-emit-pch", "-Xclang", "-include", "-Xclang",
                                str(header), "-x", "c++-header", "-o", output, "-c", str(source)]
            (temp / "compile_commands.json").write_text(json.dumps([{
                "directory": str(temp), "arguments": command, "file": str(source), "output": output}]))
            log = temp / "build.log"
            log.write_text(f"FAILED: {output}\n")
            before = pch.read_bytes()
            diagnostic = pinyon_setup.diagnose_macos_pch(temp, log, dict(pinyon_setup.os.environ))
            text = diagnostic.read_text()
            self.assertEqual(text.count("exit: 0"), 5, text)
            self.assertIn("/rex/types.h", text)
            self.assertIn("/include/c++/v1/bit", text)
            self.assertIn("__cpp_lib_byteswap 202110L", text)
            self.assertEqual(pch.read_bytes(), before)
            self.assertFalse((temp / output).exists())


class SteamShortcutTests(unittest.TestCase):
    def test_binary_vdf_round_trips(self):
        value = {"shortcuts": {"0": {"appid": -12345, "AppName": "Pinyon Shift",
                                     "Exe": '"/x/pinyon-shift.sh"', "IsHidden": 0,
                                     "tags": {"0": "Racing"}}}}
        data = pinyon_steam.dump_vdf(value)
        parsed, end = pinyon_steam.parse_vdf(data)
        self.assertEqual(parsed, value)
        self.assertEqual(end, len(data))
        self.assertEqual(pinyon_steam.dump_vdf(parsed), data)

    def test_shortcut_app_id_has_the_non_steam_bit(self):
        app_id = pinyon_steam.shortcut_app_id('"/x/pinyon-shift.sh"', "Pinyon Shift")
        self.assertTrue(app_id & 0x80000000)
        self.assertEqual(app_id, pinyon_steam.shortcut_app_id('"/x/pinyon-shift.sh"', "Pinyon Shift"))

    def test_artwork_is_present(self):
        for name in ("capsule.png", "wide.png", "hero.png", "logo.png", "icon.png"):
            self.assertTrue((ROOT / "config/steam" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
