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


def free_space_gb(path: Path) -> float:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(str(path)).free / (1 << 30)


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


def cpu_baseline(name: str) -> str:
    if name != "linux-x86_64":
        return "native"
    try:
        flags = Path("/proc/cpuinfo").read_text(encoding="ascii", errors="replace")
    except OSError:
        return "sse4.1"
    return "fma" if " fma " in flags and " avx2 " in flags else "sse4.1"


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
    if baseline == "fma":
        flags = ["-DPINYON_SHIFT_CPU_BASELINE=fma",
                 "-DCMAKE_C_FLAGS=-msse4.1 -mfma -ffp-contract=off",
                 "-DCMAKE_CXX_FLAGS=-msse4.1 -mfma -ffp-contract=off"]
    run_logged([cmake, "--preset", preset, f"-DREXSDK_DIR={sdk}", f"-DPYTHON_EXECUTABLE={python}",
                "-DREXGLUE_ENABLE_TRACY=OFF", "-DSDL_HIDAPI_LIBUSB=OFF"] + flags,
               LOGS / "preview-configure.log", progress, "build", 28, 30,
               "Configuring the game", environment)
    run_logged([cmake, "--build", "--preset", preset, "--parallel", str(jobs)],
               LOGS / "preview-build.log", progress, "build", 30, 100,
               "Building the game", environment)
    directory = ROOT / "out" / "build" / preset
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
                     baseline: str) -> None:
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
    text = json.dumps(record, indent=2) + "\n"
    (LOCAL / "build.json").write_text(text, encoding="utf-8")
    (directory / "pinyon_shift_build.json").write_text(text, encoding="utf-8")


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
