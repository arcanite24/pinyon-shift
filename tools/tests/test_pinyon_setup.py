"""tools/pinyon_setup.py and tools/pinyon_steam.py: the Linux and macOS
setup path (LX-3) and the Steam shortcut (LX-5.10)."""

import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_the_supported_catalog_matches_the_dump_manifest(self):
        dump, expected = pinyon_setup.load_catalog()
        self.assertEqual(len(expected), dump["extraction"]["file_count"])
        self.assertIn("default.xex", expected)


class ToolchainPinTests(unittest.TestCase):
    def test_posix_downloads_are_https_and_sha256_pinned(self):
        config = json.loads((ROOT / "config/release-toolchain.json").read_text(encoding="utf-8"))
        for name in ("linux-x86_64", "macos-arm64"):
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

    def test_the_payload_ships_the_posix_setup(self):
        script = (ROOT / "tools/package-launcher.ps1").read_text(encoding="utf-8")
        include = script.split("$include = @(", 1)[1].split("\n)", 1)[0]
        for required in ("tools/pinyon_setup.py", "tools/pinyon_steam.py", "config/steam",
                         "tools/verify-codegen-log.py", "cmake"):
            self.assertIn(f"'{required}'", include)
            self.assertTrue((ROOT / required).exists(), required)


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
