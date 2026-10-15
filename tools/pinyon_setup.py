#!/usr/bin/env python3
"""Disc to play on Linux and macOS, without PowerShell (LX-3, MAC-3).

`pinyon.py setup --iso FILE` does what tools/setup-preview.ps1 does on
Windows: it reads the player's own disc image, keeps only an exact match of
the supported dump, provisions the pinned toolchain, prepares ShiftGlue,
translates the game and builds it, then records that the install is ready.

  pinyon.py setup --iso FILE | --extracted DIR [--json] [--jobs N]
  pinyon.py setup --build-only              rebuild from the extracted game
  pinyon.py setup --verify-only --iso FILE  check a disc image and stop
  pinyon.py setup --tools-only              provision the toolchain and stop

With --json every step prints a `::pinyon::{"stage", "percent", "message"}`
line, the same protocol the launchers read from setup-preview.ps1.

The disc is read in place and never changed. Its files are checked one by
one against config/supported-extracted-ms-2505.json while they are copied out,
so nothing that differs from the supported dump reaches the build.

This module keeps to Python 3.9 syntax: macOS ships Python 3.9, which only
provisions the pinned Python and hands over to it (MAC-3.1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
GAME = LOCAL / "game" / "base"
LOGS = LOCAL / "logs"
DOWNLOADS = LOCAL / "downloads"
SECTOR = 2048
SYSTEM_UPDATE = "$SystemUpdate"
SOURCE_DATE_EPOCH = "1784764800"


class SetupError(RuntimeError):
    def __init__(self, message: str, stage: str = "setup"):
        super().__init__(message)
        self.stage = stage


# --- Progress ----------------------------------------------------------------

class Progress:
    """Prints the launcher protocol (--json) or plain lines."""

    def __init__(self, as_json: bool):
        self.as_json = as_json
        self.stage = "setup"
        self.percent = 0.0

    def __call__(self, stage: str, percent: float | None, message: str) -> None:
        """percent None keeps the stage's current value (download progress)."""
        if percent is None:
            percent = self.percent if stage == self.stage else 0.0
        self.stage = stage
        self.percent = percent
        if self.as_json:
            event = {"stage": stage, "percent": round(percent, 1), "message": message}
            print("::pinyon::" + json.dumps(event), flush=True)
        else:
            print(f"[{stage} {percent:5.1f}%] {message}", flush=True)


# --- Platform ----------------------------------------------------------------

def host_platform() -> str:
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return "linux-x86_64"
    if sys.platform == "darwin" and machine in ("arm64", "aarch64"):
        return "macos-arm64"
    raise SetupError(f"no build for {sys.platform} on {machine}: Pinyon Shift builds on "
                     "x86-64 Linux, Apple silicon Macs and Windows")


def toolchain_config() -> dict:
    data = json.loads((ROOT / "config" / "release-toolchain.json").read_text(encoding="utf-8"))
    return data


def platform_tools(config: dict, name: str) -> dict:
    return config["posix"][name]


def job_count() -> int:
    """As Get-PinyonBuildJobCount: one core free, about 1.5 GB per job."""
    cores = os.cpu_count() or 2
    jobs = max(2, min(16, cores - 1))
    memory = total_memory_gb()
    if memory:
        jobs = max(1, min(jobs, int((memory - 2) / 1.5)))
    return jobs


def total_memory_gb() -> float:
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
            return int(out.stdout.strip()) / (1 << 30)
        with open("/proc/meminfo", encoding="ascii") as stream:
            for line in stream:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1 << 20)
    except (OSError, ValueError):
        pass
    return 0.0


def _macos_available_bytes(path: Path) -> int:
    """What Finder shows as available: free space plus the purgeable space
    (local snapshots, caches) macOS frees when an app needs it (#461).
    0 when it cannot be read."""
    import ctypes
    try:
        cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        key = ctypes.c_void_p.in_dll(cf, "kCFURLVolumeAvailableCapacityForImportantUsageKey")
    except (OSError, ValueError):
        return 0
    cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
    cf.CFURLCopyResourcePropertyForKey.restype = ctypes.c_bool
    cf.CFURLCopyResourcePropertyForKey.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    raw = os.fsencode(str(path))
    url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), True)
    if not url:
        return 0
    value = ctypes.c_void_p()
    try:
        if not cf.CFURLCopyResourcePropertyForKey(url, key, ctypes.byref(value), None) \
                or not value.value:
            return 0
        number = ctypes.c_int64()
        ok = cf.CFNumberGetValue(value, 4, ctypes.byref(number))  # kCFNumberSInt64Type
        cf.CFRelease(value)
        return number.value if ok else 0
    finally:
        cf.CFRelease(url)


def free_space_gb(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(str(path)).free
    if sys.platform == "darwin":
        free = max(free, _macos_available_bytes(path))
    return free / (1 << 30)


def used_space_gb(*paths: Path) -> float:
    """What an earlier, interrupted setup already put on disk."""
    total = 0
    for path in paths:
        for directory, _, names in os.walk(str(path)):
            for name in names:
                try:
                    total += os.lstat(os.path.join(directory, name)).st_size
                except OSError:
                    pass
    return total / (1 << 30)


# --- Downloads and archives ----------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def download(item: dict, progress: Progress, label: str) -> Path:
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    name = item["url"].rsplit("/", 1)[1].replace("%2B", "+").replace("%2C", ",")
    target = DOWNLOADS / name
    if target.is_file() and sha256_file(target) == item["sha256"].upper():
        return target
    partial = target.with_name(target.name + ".partial")
    request = urllib.request.Request(item["url"], headers={"User-Agent": "pinyon-shift-setup"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response, \
                    partial.open("wb") as stream:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                last = 0.0
                while True:
                    block = response.read(1 << 20)
                    if not block:
                        break
                    stream.write(block)
                    done += len(block)
                    if total and time.monotonic() - last > 2:
                        last = time.monotonic()
                        progress(progress.stage, None, f"Downloading {label}: "
                                 f"{done >> 20} of {total >> 20} MB")
            break
        except OSError as error:
            if attempt == 2:
                raise SetupError(f"could not download {label}: {error}", "tools")
            time.sleep(3 * (attempt + 1))
    actual = sha256_file(partial)
    if actual != item["sha256"].upper():
        partial.unlink()
        raise SetupError(f"{label} failed its SHA-256 check (got {actual})", "tools")
    partial.replace(target)
    return target


def _extract_all(archive: tarfile.TarFile, destination: Path) -> None:
    # The archives are pinned by SHA-256; the sniper sysroot holds absolute
    # symlinks, which make_links_relative() rewrites afterwards.
    if hasattr(tarfile, "fully_trusted_filter"):
        archive.extractall(str(destination), filter="fully_trusted")
    else:
        archive.extractall(str(destination))


def unpack(archive: Path, install: Path, strip_top: bool = True) -> None:
    """Unpacks into install, dropping the archive's single top folder."""
    staging = install.with_name(install.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(str(archive)) as zipped:
            for info in zipped.infolist():
                path = zipped.extract(info, str(staging))
                mode = (info.external_attr >> 16) & 0o777
                if mode:
                    os.chmod(path, mode)
    else:
        with tarfile.open(str(archive)) as tarred:
            _extract_all(tarred, staging)
    entries = list(staging.iterdir())
    source = entries[0] if strip_top and len(entries) == 1 and entries[0].is_dir() else staging
    if install.exists():
        shutil.rmtree(install)
    install.parent.mkdir(parents=True, exist_ok=True)
    source.rename(install)
    if staging.exists():
        shutil.rmtree(staging)


def make_links_relative(sysroot: Path) -> int:
    """Absolute symlinks in the sysroot point at the build host's /; point
    them inside the sysroot instead (LX-1.1)."""
    fixed = 0
    for directory, folders, files in os.walk(str(sysroot)):
        for name in folders + files:
            path = Path(directory) / name
            if not path.is_symlink():
                continue
            target = os.readlink(str(path))
            if not target.startswith("/"):
                continue
            relative = os.path.relpath(str(sysroot) + target, directory)
            path.unlink()
            os.symlink(relative, str(path))
            fixed += 1
    return fixed


# --- Toolchain ----------------------------------------------------------------

def tool_path(item: dict) -> Path:
    return ROOT / item["install_path"] / item["executable"]


def provision_python(progress: Progress, config: dict, name: str) -> Path:
    """The pinned Python (3.13) when the running one cannot run the build's
    scripts, which need tomllib (3.11)."""
    tools = platform_tools(config, name)
    item = tools.get("python")
    if sys.version_info >= (3, 11) and (item is None or name.startswith("linux")):
        return Path(sys.executable)
    if item is None:
        raise SetupError("Python 3.11 or newer is needed", "tools")
    executable = tool_path(item)
    if not executable.is_file():
        progress("tools", 2, "Downloading Python")
        archive = download(item, progress, "Python")
        unpack(archive, ROOT / item["install_path"])
        archive.unlink()
    return executable


def provision(progress: Progress, config: dict, name: str) -> dict:
    """Downloads and unpacks every pinned tool for this platform; returns
    name -> executable."""
    tools = platform_tools(config, name)
    found = {}
    ordered = [key for key in ("cmake", "ninja", "llvm", "sysroot") if key in tools]
    for index, key in enumerate(ordered):
        item = tools[key]
        install = ROOT / item["install_path"]
        stamp = install / ".pinyon-sha256"
        if not (stamp.is_file() and stamp.read_text(encoding="ascii").strip() == item["sha256"]):
            progress("tools", 5 + 85 * index / len(ordered),
                     f"Getting {item.get('label', key)} {item['version']}")
            archive = download(item, progress, f"{key} {item['version']}")
            progress("tools", 5 + 85 * (index + 0.5) / len(ordered),
                     f"Unpacking {item.get('label', key)}")
            unpack(archive, install, strip_top=item.get("strip_top", True))
            if key == "sysroot":
                make_links_relative(install)
            stamp.write_text(item["sha256"] + "\n", encoding="ascii")
            archive.unlink()  # LLVM alone is 2 GB; a new pin downloads again
        found[key] = install / item["executable"] if item.get("executable") else install
    if name == "linux-x86_64":
        prepare_linux_toolchain(tools)
    if name == "macos-arm64":
        require_xcode_tools()
    progress("tools", 100, "Toolchain ready")
    return found


def prepare_linux_toolchain(tools: dict) -> None:
    """The layout cmake/toolchains/linux-x86_64-sniper.cmake reads:
    llvm/, sniper-sdk/ and sniper-libgcc/ (libgcc_s.so and libgcc_eh.a, which
    the sysroot ships only beside GCC 10)."""
    folder = LOCAL / "toolchain" / "linux-x86_64"
    folder.mkdir(parents=True, exist_ok=True)
    for link, key in (("llvm", "llvm"), ("sniper-sdk", "sysroot")):
        path = folder / link
        target = ROOT / tools[key]["install_path"]
        if path.is_symlink() or path.exists():
            if path.is_symlink() and Path(os.readlink(str(path))) == target:
                continue
            if path.is_symlink():
                path.unlink()
            else:
                shutil.rmtree(path)
        os.symlink(str(target), str(path))
    overlay = folder / "sniper-libgcc"
    overlay.mkdir(exist_ok=True)
    gcc10 = ROOT / tools["sysroot"]["install_path"] / "usr/lib/gcc/x86_64-linux-gnu/10"
    for name in ("libgcc_s.so", "libgcc_eh.a"):
        shutil.copyfile(str(gcc10 / name), str(overlay / name))
    prepare_host_wrappers(folder, tools)


# libxml2 2.14 renamed its library libxml2.so.16, so SteamOS, Arch and other
# current distributions no longer have the libxml2.so.2 that the LLVM
# release's ld.lld and the sysroot's wayland-scanner link (#472, #474, #514).
HOST_LIBRARY = re.compile(r"^lib(xml2\.so\.2|icuuc\.so\.\d+|icudata\.so\.\d+)$")


def prepare_host_wrappers(folder: Path, tools: dict) -> None:
    """host-libs/ holds the sysroot's libxml2.so.2 and the ICU it needs, and
    nothing else; bin/ wraps the two programs so only they load it."""
    sysroot = ROOT / tools["sysroot"]["install_path"]
    libs = folder / "host-libs"
    if libs.exists():
        shutil.rmtree(libs)
    libs.mkdir()
    source = sysroot / "usr/lib/x86_64-linux-gnu"
    for entry in sorted(source.iterdir()):
        if HOST_LIBRARY.match(entry.name):
            os.symlink(str(entry), str(libs / entry.name))
    wrappers = folder / "bin"
    wrappers.mkdir(exist_ok=True)
    for name, target in (("ld.lld", ROOT / tools["llvm"]["install_path"] / "bin/ld.lld"),
                         ("wayland-scanner", sysroot / "usr/bin/wayland-scanner")):
        wrapper = wrappers / name
        wrapper.write_text(
            "#!/bin/sh\n"
            "# Written by tools/pinyon_setup.py: runs the pinned program with the\n"
            "# libxml2.so.2 the host may lack.\n"
            'libs="$(dirname -- "$0")/../host-libs"\n'
            'LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" '
            f'exec {shlex.quote(str(target))} "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)


def require_xcode_tools() -> None:
    probe = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True)
    if probe.returncode or not shutil.which("clang++"):
        # Opens Apple's installer; the player runs setup again afterwards.
        subprocess.run(["xcode-select", "--install"], capture_output=True)
        raise SetupError("Apple's Command Line Tools are needed. Finish the installer that "
                         "just opened, then run setup again.", "tools")


# --- Disc image (XDVDFS) -------------------------------------------------------

XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"
# Where the game partition starts: rebuilt images, XGD3, XGD2, XGD1.
PARTITION_OFFSETS = (0, 0x2080000, 0xFD90000, 0x18300000)


class DiscImage:
    """Reads the Xbox file system on a disc image, read-only."""

    def __init__(self, path: Path):
        self.path = path
        self.stream = path.open("rb")
        self.offset = None
        for offset in PARTITION_OFFSETS:
            self.stream.seek(offset + 32 * SECTOR)
            if self.stream.read(len(XDVDFS_MAGIC)) == XDVDFS_MAGIC:
                self.offset = offset
                break
        if self.offset is None:
            raise SetupError("this is not an Xbox 360 disc image", "verify")
        self.stream.seek(self.offset + 32 * SECTOR + 20)
        self.root_sector, self.root_size = struct.unpack("<II", self.stream.read(8))

    def close(self) -> None:
        self.stream.close()

    def _read(self, sector: int, size: int) -> bytes:
        self.stream.seek(self.offset + sector * SECTOR)
        return self.stream.read(size)

    def files(self) -> list[tuple[str, int, int]]:
        """(path, first sector, size) of every file, directories walked."""
        found = []
        pending = [("", self.root_sector, self.root_size)]
        while pending:
            prefix, sector, size = pending.pop()
            if size == 0:
                continue
            table = self._read(sector, size)
            nodes = [0]
            seen = set()
            while nodes:
                position = nodes.pop()
                if position in seen or position + 14 > len(table):
                    continue
                seen.add(position)
                left, right, start, length, attributes, name_length = struct.unpack_from(
                    "<HHIIBB", table, position)
                if left == 0xFFFF and right == 0xFFFF:
                    continue  # sector padding
                name = table[position + 14: position + 14 + name_length].decode("latin-1")
                if left:
                    nodes.append(left * 4)
                if right:
                    nodes.append(right * 4)
                path = f"{prefix}{name}"
                if attributes & 0x10:
                    pending.append((path + "/", start, length))
                else:
                    found.append((path, start, length))
        return found

    def copy(self, sector: int, size: int, destination: Path) -> str:
        """Copies one file out; returns its SHA-256."""
        digest = hashlib.sha256()
        self.stream.seek(self.offset + sector * SECTOR)
        remaining = size
        with destination.open("wb") as out:
            while remaining:
                block = self.stream.read(min(remaining, 8 << 20))
                if not block:
                    raise SetupError("the disc image ends early", "extract")
                out.write(block)
                digest.update(block)
                remaining -= len(block)
        return digest.hexdigest().upper()


def load_catalog() -> tuple[dict, dict]:
    """The supported dump and its file catalog."""
    manifest = json.loads((ROOT / "config" / "supported-dumps.json").read_text(encoding="utf-8"))
    dump = manifest["dumps"][0]
    catalog = json.loads((ROOT / "config" / dump["extraction"]["file_catalog"]).read_text(
        encoding="utf-8"))
    if (catalog["dump_id"] != dump["id"]
            or len(catalog["files"]) != dump["extraction"]["file_count"]):
        raise SetupError("the extracted-file catalog does not match the supported dump")
    return dump, {entry["guest_path"].lower(): entry for entry in catalog["files"]}


def check_paths(files: list[tuple[str, int, int]], expected: dict) -> list[str]:
    names = {path.lower() for path, _, _ in files}
    mismatches = [f"Missing: {entry['guest_path']}" for key, entry in expected.items()
                  if key not in names]
    mismatches += [f"Not in the supported dump: {path}" for path, _, _ in files
                   if path.lower() not in expected]
    return mismatches


def extract_iso(iso: Path, progress: Progress) -> dict:
    """Copies the game out of the disc image, checking each file against the
    catalog; an image that is not the supported dump leaves nothing behind."""
    dump, expected = load_catalog()
    disc = DiscImage(iso)
    try:
        files = [entry for entry in disc.files()
                 if not entry[0].split("/", 1)[0].lower() == SYSTEM_UPDATE.lower()]
        mismatches = check_paths(files, expected)
        if mismatches:
            raise SetupError("This disc image is not the supported Forza Horizon (USA, "
                             f"MS-2505) dump: {mismatches[0]}", "verify")
        # The game executable first: a different disc fails in seconds.
        files.sort(key=lambda entry: (entry[0].lower() != "default.xex", entry[1]))
        staging = GAME.with_name(GAME.name + ".extracting")
        if staging.exists():
            shutil.rmtree(staging)
        total = sum(size for _, _, size in files)
        done = 0
        for index, (path, sector, size) in enumerate(files):
            entry = expected[path.lower()]
            target = staging / entry["guest_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if size != entry["size_bytes"] or disc.copy(sector, size, target) != entry["sha256"]:
                shutil.rmtree(staging)
                raise SetupError(f"This disc image is not the supported dump: "
                                 f"{entry['guest_path']} differs", "verify")
            done += size
            if index % 40 == 0:
                progress("extract", 100 * done / total,
                         f"Copying the game files ({done / 1e9:.1f} of {total / 1e9:.1f} GB)")
    finally:
        disc.close()
    replace_game(staging)
    return dump


def verify_folder(source: Path, progress: Progress) -> dict:
    """An already extracted game folder: same catalog, copied in."""
    dump, expected = load_catalog()
    files = []
    for directory, folders, names in os.walk(str(source)):
        relative = Path(directory).relative_to(source).as_posix()
        if relative == ".":
            relative = ""
            folders[:] = [name for name in folders if name.lower() != SYSTEM_UPDATE.lower()]
        for name in names:
            path = f"{relative}/{name}" if relative else name
            if Path(directory, name).is_symlink():
                raise SetupError(f"Linked game files are not supported: {path}", "verify")
            files.append((path, 0, (Path(directory) / name).stat().st_size))
    mismatches = check_paths(files, expected)
    if mismatches:
        raise SetupError(f"This folder is not the supported dump: {mismatches[0]}", "verify")
    staging = GAME.with_name(GAME.name + ".extracting")
    if staging.exists():
        shutil.rmtree(staging)
    total = sum(size for _, _, size in files)
    done = 0
    for index, (path, _, size) in enumerate(files):
        entry = expected[path.lower()]
        target = staging / entry["guest_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source / path), str(target))
        if size != entry["size_bytes"] or sha256_file(target) != entry["sha256"]:
            shutil.rmtree(staging)
            raise SetupError(f"This folder is not the supported dump: {path} differs", "verify")
        done += size
        if index % 40 == 0:
            progress("extract", 100 * done / total, f"Checking the game files "
                     f"({done / 1e9:.1f} of {total / 1e9:.1f} GB)")
    replace_game(staging)
    return dump


def replace_game(staging: Path) -> None:
    if GAME.is_symlink():
        raise SetupError(f"{GAME} is a link; remove it first", "extract")
    if GAME.exists():
        shutil.rmtree(GAME)
    staging.rename(GAME)


def game_ready() -> bool:
    """The extracted game is there and its executables still match."""
    dump, _ = load_catalog()
    for executable in dump["executables"]:
        path = GAME / executable["guest_path"]
        if not path.is_file() or path.stat().st_size != executable["size_bytes"]:
            return False
    return sha256_file(GAME / "default.xex") == dump["executables"][0]["sha256"]


# --- ShiftGlue -----------------------------------------------------------------

def git(*arguments: str, cwd: Path = ROOT) -> None:
    command = ["git", "-c", "http.version=HTTP/1.1"] + list(arguments)
    for attempt in range(3):
        if subprocess.run(command, cwd=str(cwd)).returncode == 0:
            return
        time.sleep(3 * (attempt + 1))
    raise SetupError(f"git {' '.join(arguments)} failed", "tools")


def prepare_shiftglue(progress: Progress, config: dict) -> Path:
    """The submodule in a git checkout, otherwise a pinned clone in
    .local/rexglue (as prepare-rexglue.ps1)."""
    rexglue = config["rexglue"]
    override = os.environ.get("PINYON_REXSDK_DIR")
    if override:
        # A ShiftGlue tree the developer manages, as pinyon_android.py allows.
        return Path(override).resolve()
    if not shutil.which("git"):
        raise SetupError("git is needed to fetch ShiftGlue", "tools")
    progress("tools", 92, "Preparing ShiftGlue")
    if (ROOT / ".git").exists():
        sdk = ROOT / rexglue["submodule_path"]
        git("submodule", "update", "--init", "--recursive", "--jobs", "8", "--",
            rexglue["submodule_path"])
        return sdk
    sdk = ROOT / rexglue["fallback_path"]
    head = subprocess.run(["git", "-C", str(sdk), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    if head.returncode == 0 and head.stdout.strip() == rexglue["revision"]:
        git("submodule", "update", "--init", "--recursive", "--jobs", "8", cwd=sdk)
        return sdk
    if sdk.exists():
        shutil.rmtree(sdk)
    git("clone", "--no-checkout", "--no-tags", rexglue["repository"], str(sdk))
    git("fetch", "--depth", "1", "origin", rexglue["revision"], cwd=sdk)
    git("checkout", "--detach", rexglue["revision"], cwd=sdk)
    git("submodule", "update", "--init", "--recursive", "--jobs", "8", cwd=sdk)
    return sdk


# --- Build ---------------------------------------------------------------------

PRESETS = {
    "linux-x86_64": {"sdk": "linux-amd64", "game": "linux-amd64",
                     "generator": "out/linux-amd64/Release/rexglue"},
    "macos-arm64": {"sdk": "mac-arm64", "game": "macos-arm64",
                    "generator": "out/mac-arm64/Release/rexglue"},
}


def run_logged(command: list, log: Path, progress: Progress, stage: str, start: float,
               end: float, message: str, environment: dict, cwd: Path = ROOT) -> None:
    """Runs a build step into its log; Ninja's [n/m] lines move the bar."""
    LOGS.mkdir(parents=True, exist_ok=True)
    progress(stage, start, message)
    last = 0.0
    with log.open("w", encoding="utf-8", errors="replace") as stream:
        process = subprocess.Popen([str(part) for part in command], cwd=str(cwd),
                                   env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, errors="replace")
        assert process.stdout is not None
        for line in process.stdout:
            stream.write(line)
            if line.startswith("[") and "/" in line.split("]", 1)[0]:
                try:
                    done, total = line[1:].split("]", 1)[0].split("/")
                    fraction = int(done) / max(1, int(total))
                except ValueError:
                    continue
                if time.monotonic() - last > 1:
                    last = time.monotonic()
                    progress(stage, start + (end - start) * fraction,
                             f"{message} ({done}/{total})")
        if process.wait():
            raise SetupError(f"{message} failed; see {log}", stage)
    progress(stage, end, message)


def build_environment(tools: dict) -> dict:
    environment = dict(os.environ)
    paths = [str(Path(tools[key]).parent) for key in ("cmake", "ninja") if key in tools]
    environment["PATH"] = os.pathsep.join(paths + [environment.get("PATH", "")])
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    environment["PINYON_LINUX_TOOLCHAIN"] = str(LOCAL / "toolchain" / "linux-x86_64")
    return environment


# x86-64-v3 as /proc/cpuinfo names it (abm is LZCNT); every one of them
# implies the FMA3 variant's fma and avx2.
V3_CPU_FLAGS = ("avx2", "bmi1", "bmi2", "fma", "movbe", "f16c", "abm")
CPU_BASELINE_FLAGS = {
    "v3": "-msse4.1 -mfma -ffp-contract=off -march=x86-64-v3",
    "fma": "-msse4.1 -mfma -ffp-contract=off",
    "sse4.1": "-msse4.1",
}


def cpu_baseline(name: str, cpuinfo: Path = Path("/proc/cpuinfo")) -> str:
    """The game is built on the machine that runs it (a Deck builds its own),
    so the baseline follows this CPU: x86-64-v3 when it has it (Haswell, Zen
    and later, the Steam Deck included; NN-1.8), the FMA3 variant, or SSE4.1.
    PINYON_SHIFT_CPU_BASELINE (sse4.1, fma or v3) overrides it, for example
    for a build copied to an older PC; the game's own guard stops a build on
    a CPU without its baseline."""
    if name != "linux-x86_64":
        return "native"
    chosen = os.environ.get("PINYON_SHIFT_CPU_BASELINE", "").strip()
    if chosen:
        if chosen not in CPU_BASELINE_FLAGS:
            raise SetupError(f"PINYON_SHIFT_CPU_BASELINE must be one of "
                             f"{', '.join(CPU_BASELINE_FLAGS)}, not {chosen!r}", "build")
        return chosen
    try:
        text = cpuinfo.read_text(encoding="ascii", errors="replace")
    except OSError:
        return "sse4.1"
    flags = set()
    for line in text.splitlines():
        if line.startswith("flags"):
            flags = set(line.split(":", 1)[-1].split())
            break
    if all(flag in flags for flag in V3_CPU_FLAGS):
        return "v3"
    return "fma" if {"fma", "avx2"} <= flags else "sse4.1"


def discard_unfinished_configure(directory: Path) -> None:
    """A configure that failed before writing build.ninja may have cached
    flags from an older toolchain; the retry starts that configure over."""
    if (directory / "CMakeCache.txt").is_file() and not (directory / "build.ninja").is_file():
        (directory / "CMakeCache.txt").unlink()
        shutil.rmtree(directory / "CMakeFiles", ignore_errors=True)


def run_game_build(command: list, log: Path, progress: Progress, start: float, message: str,
                   environment: dict, directory: Path, generated: Path) -> None:
    """The game build. Its dependency-tracked translation step can rewrite a
    tree's sources.cmake partway through, as when a ShiftGlue update adds a
    generated file (pinyon_shift_folds.cpp). The graph Ninja started with
    then misses that file and the link fails; one more build reconfigures
    from the new lists and finishes. Any other failure stands."""
    ninja = directory / "build.ninja"
    configured = ninja.stat().st_mtime if ninja.is_file() else 0.0
    try:
        run_logged(command, log, progress, "build", start, 100, message, environment)
    except SetupError:
        lists = [generated / tree / "sources.cmake" for tree in ("default", "speech", "xmedia")]
        if not any(path.is_file() and path.stat().st_mtime > configured for path in lists):
            raise
        run_logged(command, log.with_name(log.stem + "-retry" + log.suffix), progress, "build",
                   start, 100, message, environment)


def build(progress: Progress, tools: dict, sdk: Path, python: Path, name: str,
          jobs: int, configuration: str = "Release") -> Path:
    presets = PRESETS[name]
    environment = build_environment(tools)
    cmake = str(tools["cmake"])
    toolchain = []
    if name == "linux-x86_64":
        # ShiftGlue's preset names plain clang; the toolchain file's pinned
        # paths must win or every configure discards the cache.
        llvm = LOCAL / "toolchain" / "linux-x86_64" / "llvm" / "bin"
        toolchain = [f"-DCMAKE_TOOLCHAIN_FILE={ROOT / 'cmake/toolchains/linux-x86_64-sniper.cmake'}",
                     f"-DCMAKE_C_COMPILER={llvm / 'clang'}",
                     f"-DCMAKE_CXX_COMPILER={llvm / 'clang++'}"]
    generator = sdk / presets["generator"]
    discard_unfinished_configure(sdk / "out" / "build" / presets["sdk"])
    run_logged([cmake, "--preset", presets["sdk"], "-DREXGLUE_ENABLE_TRACY=OFF",
                "-DSDL_HIDAPI_LIBUSB=OFF"] + toolchain, LOGS / "rexglue-configure.log",
               progress, "build", 0, 2, "Configuring ShiftGlue", environment, cwd=sdk)
    run_logged([cmake, "--build", "--preset", f"{presets['sdk']}-release", "--target", "rexglue",
                "--parallel", str(jobs)], LOGS / "rexglue-build.log", progress, "build", 2, 20,
               "Building the translator", environment, cwd=sdk)

    generated = LOCAL / "generated"
    stamps = [generated / "default" / "codegen.build.stamp"] + [
        generated / module / "sources.cmake" for module in ("default", "speech", "xmedia")]
    if not all(path.is_file() for path in stamps):
        run_logged([generator, "--log-level", "info", "--log-file", LOGS / "codegen.log",
                    "codegen", "config/rexglue/pinyon_shift_manifest.toml"],
                   LOGS / "codegen-console.log", progress, "build", 20, 28,
                   "Translating the game", environment)
        check = subprocess.run([str(python), str(ROOT / "tools" / "verify-codegen-log.py"),
                                str(LOGS / "codegen.log"), "--allowlist",
                                str(ROOT / "config/rexglue/accepted-codegen-warnings.json")],
                               capture_output=True, text=True)
        if check.returncode:
            for path in stamps:
                if path.is_file():
                    path.unlink()
            raise SetupError("the translation reported unexpected warnings; see "
                             f"{LOGS / 'codegen.log'}\n{check.stdout}{check.stderr}", "build")

    preset = f"{presets['game']}-{configuration.lower()}"
    baseline = cpu_baseline(name)
    flags = []
    if baseline in CPU_BASELINE_FLAGS:
        # Always passed: a reconfigure must not keep an earlier baseline.
        flags = [f"-DPINYON_SHIFT_CPU_BASELINE={baseline}",
                 f"-DCMAKE_C_FLAGS={CPU_BASELINE_FLAGS[baseline]}",
                 f"-DCMAKE_CXX_FLAGS={CPU_BASELINE_FLAGS[baseline]}"]
    discard_unfinished_configure(ROOT / "out" / "build" / preset)
    run_logged([cmake, "--preset", preset, f"-DREXSDK_DIR={sdk}", f"-DPYTHON_EXECUTABLE={python}",
                "-DREXGLUE_ENABLE_TRACY=OFF", "-DSDL_HIDAPI_LIBUSB=OFF"] + flags,
               LOGS / "preview-configure.log", progress, "build", 28, 30,
               "Configuring the game", environment)
    directory = ROOT / "out" / "build" / preset
    run_game_build([cmake, "--build", "--preset", preset, "--parallel", str(jobs)],
                   LOGS / "preview-build.log", progress, 30, "Building the game", environment,
                   directory, generated)
    executable = directory / "pinyon_shift"
    if not executable.is_file():
        raise SetupError(f"the build finished without {executable}", "build")
    write_provenance(directory, executable, sdk, configuration, baseline)
    controller_db = ROOT / "config" / "gamecontrollerdb.txt"
    if controller_db.is_file():
        shutil.copyfile(str(controller_db), str(directory / "gamecontrollerdb.txt"))
    return executable


def git_output(*arguments: str, cwd: Path = ROOT) -> str:
    completed = subprocess.run(["git"] + list(arguments), cwd=str(cwd), capture_output=True,
                               text=True)
    return completed.stdout.strip() if completed.returncode == 0 else ""


def write_provenance(directory: Path, executable: Path, sdk: Path, configuration: str,
                     baseline: str, title_update: str | None = None) -> None:
    payload = ROOT / ".pinyon-source-sha256"
    record = {
        "schema_version": 3,
        "configuration": configuration,
        "cpu_baseline": baseline,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "executable": str(executable.relative_to(ROOT)),
        "executable_sha256": sha256_file(executable),
        "generated_locally": True,
        "platform": host_platform(),
        "pinyon_shift_commit": git_output("rev-parse", "HEAD"),
        "pinyon_shift_dirty": bool(git_output("status", "--porcelain", "--untracked-files=no")),
        "pinyon_shift_source_payload_sha256": (payload.read_text(encoding="ascii").strip()
                                               if payload.is_file() else None),
        "rexglue_commit": git_output("rev-parse", "HEAD", cwd=sdk),
        "guest_executable_sha256": sha256_file(GAME / "default.xex"),
    }
    if title_update:
        # The v4 build records itself only: .local/build.json is the base
        # build the launchers check for readiness.
        record["title_update"] = title_update
    text = json.dumps(record, indent=2) + "\n"
    if not title_update:
        (LOCAL / "build.json").write_text(text, encoding="utf-8")
    (directory / "pinyon_shift_build.json").write_text(text, encoding="utf-8")


# --- Title update v4 ---------------------------------------------------------------

V4_MODULES = ("default", "SpeechFacade_default", "XMediaFacade_default")
V4_TREES = ("default", "speech", "xmedia")
V4_BUILD_TARGETS = ("pinyon_shift", "pinyon_shift_fh1_archive_extract",
                    "pinyon_shift_stage_rexruntime")


def shiftglue_root(config: dict) -> Path:
    """The SDK the base build used, without fetching (Resolve-PinyonRexGlueRoot)."""
    override = os.environ.get("PINYON_REXSDK_DIR")
    if override:
        return Path(override).resolve()
    rexglue = config["rexglue"]
    return ROOT / (rexglue["submodule_path"] if (ROOT / ".git").exists()
                   else rexglue["fallback_path"])


def build_v4(progress: Progress, tools: dict, sdk: Path, python: Path, name: str, jobs: int,
             state: Path, game: Path) -> Path:
    """tools/build-v4.ps1 off Windows: the FH1 v4 title-update executable in
    out/build/<platform>-v4. The generator applies the player's patches to
    copies of the disc executables in .local/game/v4-codegen; the disc
    folder, the update package and the base build are left untouched."""
    presets = PRESETS[name]
    update = state / "title-update-v4"
    for module in V4_MODULES:
        if not (game / f"{module}.xex").is_file():
            raise SetupError(f"The disc executable {module}.xex is missing from {game}.", "build")
        if not (update / f"{module}.xexp").is_file():
            raise SetupError("Install the verified title update first (pinyon.py title-update "
                             "import).", "build")
    generator = sdk / presets["generator"]
    if not generator.is_file():
        raise SetupError("The ShiftGlue generator is missing. Build the base game first "
                         "(pinyon.py setup).", "build")
    codegen = LOCAL / "game" / "v4-codegen"
    codegen.mkdir(parents=True, exist_ok=True)
    for module in V4_MODULES:
        # copy2 keeps the times, so the build's regeneration step sees no change.
        shutil.copy2(str(game / f"{module}.xex"), str(codegen / f"{module}.xex"))
        shutil.copy2(str(update / f"{module}.xexp"), str(codegen / f"{module}.xexp"))
    environment = build_environment(tools)
    cmake = str(tools["cmake"])
    LOGS.mkdir(parents=True, exist_ok=True)
    # Configure reads the generated tree's sources.cmake, so a first v4 build
    # generates it here; later builds regenerate through the build's own
    # dependency-tracked step (#540).
    generated = LOCAL / "generated-v4"
    stamps = [generated / "default" / "codegen.build.stamp"] + [
        generated / tree / "sources.cmake" for tree in V4_TREES]
    log = LOGS / "codegen-v4.log"
    if not all(path.is_file() for path in stamps):
        generated.mkdir(parents=True, exist_ok=True)
        if log.is_file():
            log.unlink()
        try:
            run_logged([generator, "--log-level", "info", "--log-file", log, "codegen",
                        "config/rexglue/pinyon_shift_v4_manifest.toml",
                        "--xex_apply_patches=true"],
                       LOGS / "codegen-v4-console.log", progress, "build", 0, 10,
                       "Translating the v4 game code", environment)
        except SetupError:
            for tree in V4_TREES:
                stamp = generated / tree / "codegen.build.stamp"
                if stamp.is_file():
                    stamp.unlink()
            raise SetupError("v4 code generation failed; incomplete generation stamps were "
                             f"removed. See {LOGS / 'codegen-v4-console.log'}", "build")
    preset = f"{presets['game']}-v4"
    baseline = cpu_baseline(name)
    flags = []
    if baseline in CPU_BASELINE_FLAGS:
        # As the base build: the baseline follows this CPU (NN-1.8).
        flags = [f"-DPINYON_SHIFT_CPU_BASELINE={baseline}",
                 f"-DCMAKE_C_FLAGS={CPU_BASELINE_FLAGS[baseline]}",
                 f"-DCMAKE_CXX_FLAGS={CPU_BASELINE_FLAGS[baseline]}"]
    directory = ROOT / "out" / "build" / preset
    discard_unfinished_configure(directory)
    # A release install keeps the SDK in .local/rexglue, not in the submodule
    # path the preset names (#459).
    run_logged([cmake, "--preset", preset, f"-DREXSDK_DIR={sdk}", f"-DPYTHON_EXECUTABLE={python}",
                "-DREXGLUE_ENABLE_TRACY=OFF", "-DSDL_HIDAPI_LIBUSB=OFF"] + flags,
               LOGS / "v4-configure.log", progress, "build", 10, 12, "Configuring the v4 build",
               environment)
    # The staging target copies librexruntime beside the game. Building only
    # pinyon_shift skips it (it is an ALL target), and off Windows nothing
    # else copies the library, so the v4 game would not start.
    run_game_build([cmake, "--build", str(directory), "--parallel", str(jobs), "--target",
                    *V4_BUILD_TARGETS],
                   LOGS / "v4-build.log", progress, 12, "Building the v4 executable",
                   environment, directory, generated)
    executable = directory / "pinyon_shift"
    if not executable.is_file():
        raise SetupError(f"the v4 build finished without {executable}", "build")
    runtime = directory / ("librexruntime.dylib" if sys.platform == "darwin" else "librexruntime.so")
    if not runtime.is_file():
        raise SetupError(f"the v4 build finished without {runtime}", "build")
    if log.is_file():
        check = subprocess.run([str(python), str(ROOT / "tools" / "verify-codegen-log.py"),
                                str(log), "--allowlist",
                                str(ROOT / "config/rexglue/accepted-codegen-warnings-v4.json")],
                               capture_output=True, text=True)
        if check.returncode:
            raise SetupError("The v4 code generation log has unreviewed warnings.\n"
                             f"{check.stdout}{check.stderr}", "build")
    write_provenance(directory, executable, sdk, "Release", baseline, title_update="v4")
    controller_db = ROOT / "config" / "gamecontrollerdb.txt"
    if controller_db.is_file():
        shutil.copyfile(str(controller_db), str(directory / "gamecontrollerdb.txt"))
    progress("build", 100, f"v4 build ready: {executable}")
    return executable


def build_v4_from_cli(state: Path, game: Path, jobs: int | None, as_json: bool) -> Path:
    """`pinyon.py title-update build` on Linux and macOS. Progress goes to
    stderr, so the command's stdout holds only its result."""
    progress = Progress(as_json)
    name = host_platform()
    config = toolchain_config()
    stdout = sys.stdout
    sys.stdout = sys.stderr
    awake = keep_awake()
    try:
        python = provision_python(progress, config, name)
        tools = provision(progress, config, name)
        sdk = shiftglue_root(config)
        return build_v4(progress, tools, sdk, python, name, jobs or job_count(), state, game)
    finally:
        sys.stdout = stdout
        if awake:
            awake.terminate()


# --- Setup ---------------------------------------------------------------------

def keep_awake() -> subprocess.Popen | None:
    """Holds off idle sleep for the build: a Steam Deck would otherwise sleep
    in the middle of it."""
    if sys.platform == "darwin":
        command = ["caffeinate", "-i", "-w", str(os.getpid())]
    elif shutil.which("systemd-inhibit"):
        command = ["systemd-inhibit", "--what=idle:sleep", "--who=Pinyon Shift",
                   "--why=Building the game", "--mode=block", "sleep", "infinity"]
    else:
        return None
    try:
        return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


def setup(args: argparse.Namespace) -> int:
    awake = keep_awake()
    try:
        return run_setup(args)
    finally:
        if awake:
            awake.terminate()


def run_setup(args: argparse.Namespace) -> int:
    progress = Progress(args.json)
    name = host_platform()
    config = toolchain_config()
    LOGS.mkdir(parents=True, exist_ok=True)
    error_file = LOGS / "setup-error.json"
    if error_file.exists():
        error_file.unlink()
    try:
        python = provision_python(progress, config, name)
        if Path(sys.executable).resolve() != python.resolve():
            # Hand over to the pinned Python (macOS ships 3.9).
            return subprocess.run([str(python), str(Path(__file__).resolve())]
                                  + sys.argv[1:]).returncode
        needed = platform_tools(config, name)["disk_space_gb"]["first_build"]
        if not args.tools_only and not (LOCAL / "build.json").is_file():
            # The first build's total, less what a resumed setup already has.
            remaining = needed - used_space_gb(LOCAL, ROOT / "out")
            if free_space_gb(LOCAL) < remaining:
                raise SetupError(f"{remaining:.0f} GB of free space is needed to finish the "
                                 f"first build ({free_space_gb(LOCAL):.0f} GB free)", "verify")
        if args.tools_only:
            provision(progress, config, name)
            prepare_shiftglue(progress, config)
            return 0
        dump = None
        source_kind = None
        if args.iso or args.extracted:
            progress("verify", 0, "Checking the game")
            if args.iso:
                if not args.iso.is_file():
                    raise SetupError(f"{args.iso} does not exist", "verify")
                source_kind = "iso"
                if args.verify_only:
                    _, expected = load_catalog()
                    disc = DiscImage(args.iso)
                    mismatches = check_paths([entry for entry in disc.files()
                                              if not entry[0].lower().startswith(
                                                  SYSTEM_UPDATE.lower())], expected)
                    disc.close()
                    if mismatches:
                        raise SetupError(f"Not the supported dump: {mismatches[0]}", "verify")
                    progress("verify", 100, "The disc image has the supported dump's files")
                    return 0
                dump = extract_iso(args.iso, progress)
            else:
                source_kind = "extracted"
                dump = verify_folder(args.extracted.resolve(), progress)
            progress("extract", 100, "Game files ready")
        elif not game_ready():
            raise SetupError("choose your disc image (--iso) first", "verify")
        tools = provision(progress, config, name)
        sdk = prepare_shiftglue(progress, config)
        jobs = args.jobs or job_count()
        build(progress, tools, sdk, python, name, jobs, args.configuration)
        if dump is None:
            dump, _ = load_catalog()
        state = {
            "schema_version": 1,
            "completed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dump_id": dump["id"],
            "source_kind": source_kind or "existing",
            "iso_sha256": None,
            "verified_by": "extracted-file-catalog",
            "platform": name,
            "result": "ready",
        }
        (LOCAL / "setup-state.json").write_text(json.dumps(state, indent=2) + "\n",
                                                encoding="utf-8")
        progress("play", 100, "Ready to play")
        return 0
    except SetupError as error:
        error_file.write_text(json.dumps({"stage": error.stage, "message": str(error),
                                          "utc": datetime.now(timezone.utc).isoformat()},
                                         indent=2) + "\n", encoding="utf-8")
        if args.json:
            print("::pinyon::" + json.dumps({"stage": error.stage, "percent": 0,
                                             "error": str(error)}), flush=True)
        print(f"==== SETUP FAILED ====\n{error}", file=sys.stderr)
        return 1


def add_parser(commands) -> None:
    parser = commands.add_parser("setup", help="build the game from your disc (Linux, macOS)")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--iso", type=Path, help="your Forza Horizon disc image")
    source.add_argument("--extracted", type=Path, help="an already extracted game folder")
    parser.add_argument("--verify-only", action="store_true", help="check the disc and stop")
    parser.add_argument("--build-only", action="store_true",
                        help="rebuild from the game files already extracted")
    parser.add_argument("--tools-only", action="store_true",
                        help="provision the toolchain and ShiftGlue, then stop")
    parser.add_argument("--configuration", choices=("Release", "RelWithDebInfo"),
                        default="Release")
    parser.add_argument("--jobs", type=int, help="parallel compile jobs")
    parser.add_argument("--json", action="store_true", help="print ::pinyon:: progress events")


def main(args: argparse.Namespace) -> int:
    return setup(args)


if __name__ == "__main__":
    top = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_parser(top.add_subparsers(dest="command", required=True))
    arguments = sys.argv[1:]
    if not arguments or arguments[0] != "setup":
        arguments = ["setup"] + arguments
    sys.exit(main(top.parse_args(arguments)))
