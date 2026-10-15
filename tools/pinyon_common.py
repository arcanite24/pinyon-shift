#!/usr/bin/env python3
"""Paths, builds and small helpers shared by the pinyon.py commands.

Every launcher feature runs through tools/pinyon.py on every OS (D4, the
"Python core first" plan in docs/LINUX_PORT_BACKLOG.md); this module holds
what the commands have in common: where the state, the game and each build
live, the archive extractor beside the game, whether the game is running,
the install root and portable rule the launchers use, and the one-object
JSON result the launchers parse.

  pinyon.py paths [--launcher-dir DIR] [--check DIR] [--json]

`paths` reports those locations; with --check it says whether a folder can
hold an install (writable, free space, file system, case sensitivity,
symbolic links, executable files), for the launchers' install-root chooser.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
MACOS = sys.platform == "darwin"
SUFFIX = ".exe" if WINDOWS else ""
EXECUTABLE = "pinyon_shift" + SUFFIX
EXTRACTOR = "pinyon_shift_fh1_archive_extract" + SUFFIX
TITLE_ID = "4D5309C9"
CONTENT_USER = "0000000000000000"  # shared Marketplace content, not a profile
DEFAULT_XUID = "B13EBABEBABEBABE"
REPOSITORY_URL = "https://github.com/arcanite24/pinyon-shift"
# PortableMode.cs: a portable.txt beside the launcher keeps everything in data/.
PORTABLE_MARKER = "portable.txt"
PORTABLE_DATA = "data"
# PortableMode.MaximumDataRootLength: Windows' build tools stop at 260 characters.
WINDOWS_MAXIMUM_ROOT = 70


class CommandError(RuntimeError):
    """A failure the command reports as {"result": "error", "error": ...}."""


# --- Locations -------------------------------------------------------------------

def preset_prefix() -> str:
    """win-amd64, linux-amd64 or macos-arm64: the CMake preset family."""
    system = {"Windows": "win", "Darwin": "macos"}.get(platform.system(),
                                                       platform.system().lower())
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    return f"{system}-{arch}"


def build_directory(configuration: str = "Release", v4: bool = False) -> Path:
    """out/build/<preset>: the base build, or the v4 title-update build
    (win-amd64-v4, linux-amd64-v4, macos-arm64-v4)."""
    suffix = "v4" if v4 else configuration.lower()
    return ROOT / "out" / "build" / f"{preset_prefix()}-{suffix}"


def default_state_root() -> Path:
    return ROOT / ".local" / "preview"


def default_game_root() -> Path:
    return ROOT / ".local" / "game" / "base"


def state_root(value: Path | None) -> Path:
    return (value or default_state_root()).expanduser().resolve()


def game_root(value: Path | None) -> Path:
    return (value or default_game_root()).expanduser().resolve()


def find_extractor(build: Path | None = None) -> Path | None:
    """pinyon_shift_fh1_archive_extract, built beside the game by every
    platform's build (CMakeLists.txt). The base Release build first, then
    the other builds that make it."""
    candidates = [build] if build else []
    candidates += [build_directory("Release"), build_directory("RelWithDebInfo"),
                   build_directory(v4=True)]
    for directory in candidates:
        if directory and (directory / EXTRACTOR).is_file():
            return directory / EXTRACTOR
    return None


def require_extractor(build: Path | None = None) -> Path:
    extractor = find_extractor(build)
    if extractor is None:
        raise CommandError("the archive extractor is not built yet; build the game first "
                           f"({EXTRACTOR} beside {EXECUTABLE} in out/build)")
    return extractor


def game_running() -> bool:
    if os.environ.get("PINYON_SHIFT_TEST_ALLOW_RUNNING_GAME"):
        return False
    if WINDOWS:
        listing = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXECUTABLE}", "/NH"],
                                 capture_output=True, text=True)
        return EXECUTABLE.lower() in listing.stdout.lower()
    if shutil.which("pgrep"):
        return subprocess.run(["pgrep", "-x", EXECUTABLE], capture_output=True).returncode == 0
    return False


def require_game_closed(what: str) -> None:
    if game_running():
        raise CommandError(f"close Pinyon Shift before {what}")


def install_root(launcher_dir: Path | None = None) -> tuple[Path, bool]:
    """Where the launchers install, and whether that is a portable install:
    Installation.InstallRoot (Desktop) and PortableMode (Windows)."""
    if launcher_dir is not None and (launcher_dir / PORTABLE_MARKER).is_file():
        return (launcher_dir.resolve() / PORTABLE_DATA), True
    configured = os.environ.get("PINYON_SHIFT_INSTALL_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve(), False
    home = Path.home()
    if WINDOWS:
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        return Path(local) / "PinyonShift", False
    if MACOS:
        return home / "Library" / "Application Support" / "PinyonShift", False
    data = os.environ.get("XDG_DATA_HOME", "").strip()
    return (Path(data) if data else home / ".local" / "share") / "PinyonShift", False


# --- Child lookups that ignore case -------------------------------------------------

def child_ignoring_case(directory: Path, name: str) -> Path | None:
    """directory/name, matched without case: folders copied from Windows or
    Xenia keep their own spelling, and ext4 tells the spellings apart."""
    exact = directory / name
    if exact.exists():
        return exact
    try:
        for child in directory.iterdir():
            if child.name.lower() == name.lower():
                return child
    except OSError:
        pass
    return None


def path_ignoring_case(directory: Path, *parts: str) -> Path | None:
    current: Path | None = directory
    for part in parts:
        if current is None:
            return None
        current = child_ignoring_case(current, part)
    return current


# --- Results ---------------------------------------------------------------------

def emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result), flush=True)
        return
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        print(f"{key}: {value}")


def run_command(handler, args: argparse.Namespace) -> int:
    """Runs a handler that returns a dict; prints one JSON object with
    --json, and {"result": "error", "error": ...} with exit 1 on failure,
    the contract RunXeAsync and RunRadioAsync parse."""
    as_json = getattr(args, "json", False)
    try:
        result = handler(args)
    except (CommandError, OSError, ValueError) as error:
        if as_json:
            print(json.dumps({"result": "error", "error": str(error)}),
                  flush=True)
        else:
            print(f"error: {error}", file=sys.stderr)
        return 1
    result.setdefault("result", "ok")
    emit(result, as_json)
    return 0


def write_json_atomic(path: Path, value: object, indent: int | None = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=indent) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def rename(source: Path, destination: Path, attempts: int = 20) -> None:
    """Path.rename, retried on Windows: a folder whose files were just
    written can be held for a moment by an antivirus scan (WinError 5)."""
    for attempt in range(attempts):
        try:
            source.rename(destination)
            return
        except PermissionError:
            if not WINDOWS or attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def python_executable() -> str:
    return sys.executable


# --- paths --------------------------------------------------------------------------

def _filesystem(path: Path) -> str | None:
    """The file system type holding path (ext4, btrfs, exfat, apfs, ntfs...)."""
    try:
        if sys.platform.startswith("linux"):
            best, kind = "", None
            resolved = str(path.resolve())
            with open("/proc/self/mounts", encoding="utf-8", errors="replace") as mounts:
                for line in mounts:
                    fields = line.split()
                    if len(fields) < 3:
                        continue
                    point = fields[1].replace("\\040", " ")
                    if (resolved == point or resolved.startswith(point.rstrip("/") + "/")) \
                            and len(point) > len(best):
                        best, kind = point, fields[2]
            return kind
        if MACOS:
            # `mount` lines read "<device> on <point> (<type>, <options>)".
            best, kind = "", None
            resolved = str(path.resolve())
            listing = subprocess.run(["mount"], capture_output=True, text=True).stdout
            for line in listing.splitlines():
                match = re.match(r"^.+? on (?P<point>.+) \((?P<type>[^,)]+)", line)
                if not match:
                    continue
                point = match.group("point")
                if (resolved == point or resolved.startswith(point.rstrip("/") + "/")) \
                        and len(point) > len(best):
                    best, kind = point, match.group("type").strip()
            return kind
        if WINDOWS:
            import ctypes
            name = ctypes.create_unicode_buffer(64)
            drive = os.path.splitdrive(str(path.resolve()))[0] + "\\"
            if ctypes.windll.kernel32.GetVolumeInformationW(drive, None, 0, None, None, None,
                                                            name, len(name)):
                return name.value.lower()
    except (OSError, ValueError, AttributeError):
        pass
    return None


def check_folder(folder: Path) -> dict:
    """Whether folder can hold an install: the build writes ~20 GB there,
    unpacks toolchains with symbolic links and runs what it built."""
    folder = folder.expanduser()
    existing = folder
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    result: dict = {"path": str(folder.resolve() if folder.exists() else folder),
                    "exists": folder.is_dir(), "filesystem": _filesystem(existing),
                    "free_gb": round(shutil.disk_usage(existing).free / (1 << 30), 1),
                    "writable": False, "case_sensitive": None, "symlinks": None,
                    "executables": None, "problems": []}
    problems = result["problems"]
    if WINDOWS and len(str(folder)) > WINDOWS_MAXIMUM_ROOT:
        problems.append(f"the folder path is {len(str(folder))} characters long; keep it to "
                        f"{WINDOWS_MAXIMUM_ROOT} or fewer, such as D:\\PinyonShift")
    created = not folder.exists()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = Path(tempfile.mkdtemp(prefix=".pinyon-check-", dir=folder))
    except OSError as error:
        problems.append(f"the folder cannot be written ({error.strerror or error})")
        return result
    try:
        result["writable"] = True
        (probe / "case").write_bytes(b"")
        result["case_sensitive"] = not (probe / "CASE").exists()
        try:
            os.symlink("case", probe / "link")
            result["symlinks"] = True
        except (OSError, NotImplementedError):
            result["symlinks"] = False
        if not WINDOWS:
            script = probe / "run.sh"
            script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
            try:
                result["executables"] = subprocess.run([str(script)]).returncode == 0
            except OSError:
                result["executables"] = False
            if result["symlinks"] is False:
                problems.append("this file system has no symbolic links (FAT or exFAT?); the "
                                "toolchain needs them, so choose an ext4 or btrfs folder")
            if result["executables"] is False:
                problems.append("programs cannot run from this folder (mounted noexec?)")
        else:
            result["executables"] = True
    finally:
        shutil.rmtree(probe, ignore_errors=True)
        if created:
            try:
                folder.rmdir()
            except OSError:
                pass
    if result["free_gb"] < 25:
        problems.append(f"{result['free_gb']} GB free; the first build needs about 25 GB")
    return result


def paths(args: argparse.Namespace) -> dict:
    launcher = args.launcher_dir.resolve() if args.launcher_dir else None
    install, portable = install_root(launcher)
    state = default_state_root()
    result = {
        "platform": preset_prefix(),
        "install_root": str(install),
        "portable": portable,
        "source_root": str(ROOT),
        "state_root": str(state),
        "game_root": str(default_game_root()),
        "logs": str(ROOT / ".local" / "logs"),
        "saves": str(state / "user"),
        "build_directory": str(build_directory()),
        "v4_build_directory": str(build_directory(v4=True)),
        "extractor": str(find_extractor()) if find_extractor() else None,
        "game_built": (build_directory() / EXECUTABLE).is_file(),
        "v4_built": (build_directory(v4=True) / EXECUTABLE).is_file(),
        "install_root_overridden": bool(os.environ.get("PINYON_SHIFT_INSTALL_ROOT", "").strip())
                                   and not portable,
    }
    if portable:
        # PortableMode.ApplyToEnvironment: overrides would write elsewhere.
        result["ignored_overrides"] = [name for name in ("PINYON_SHIFT_INSTALL_ROOT",
                                                         "PINYON_SHIFT_STATE_ROOT",
                                                         "PINYON_SHIFT_GAME_ROOT")
                                       if os.environ.get(name, "").strip()]
    if args.check:
        result["check"] = check_folder(args.check)
    return result


def add_parser(commands) -> None:
    parser = commands.add_parser("paths", help="where the install, state and builds live")
    parser.add_argument("--launcher-dir", type=Path,
                        help="the launcher's folder: a portable.txt there means a portable install")
    parser.add_argument("--check", type=Path, help="check a folder for an install root")
    parser.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return run_command(paths, args)
