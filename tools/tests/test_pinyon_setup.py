"""tools/pinyon_setup.py and tools/pinyon_steam.py: the Linux and macOS
setup path (LX-3) and the Steam shortcut (LX-5.10)."""

import hashlib
import json
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
