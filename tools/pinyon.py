#!/usr/bin/env python3
"""Pinyon Shift command-line launcher for Windows and Linux (NP-12.7).

`launch` does what tools/launch-preview.ps1 does without PowerShell: it
checks the build and the game files, prepares the state directory, rebuilds
the enabled mods' database patches, archive members and merges, sets the
environment the game reads and starts it, then reports how it exited:

  pinyon.py launch [--state-root DIR] [--game-root DIR] [--build-directory DIR]
                   [--configuration Release|RelWithDebInfo] [--hidden] [--json]
                   [--render-test-script FILE --render-test-output DIR]
                   [-- game arguments...]

On Windows Vulkan shader storage is prepared first through
tools/prepare-fh1-shaders.ps1 (skip it with --skip-shader-preparation); on
Linux the game runs on Vulkan and translates shaders itself, so there is
nothing to prepare. A crash on Windows is bundled by
tools/create-crash-report.ps1; elsewhere the exit code is reported.

`android` builds, installs and runs the game on an Android device from this
PC (AP-6.1); see tools/pinyon_android.py. `deck` copies a Linux build and the
game to a Steam Deck and runs it there over SSH (LX-2.1); see
tools/pinyon_deck.py.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_android  # noqa: E402
import pinyon_deck  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
EXECUTABLE = "pinyon_shift.exe" if WINDOWS else "pinyon_shift"
STATE_DIRECTORIES = ("cache", "config", "crashes", "logs", "reports", "update", "user")


class LaunchError(RuntimeError):
    pass


def default_build_directory(configuration: str) -> Path:
    system = "win" if WINDOWS else platform.system().lower()
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    return ROOT / "out" / "build" / f"{system}-{arch}-{configuration.lower()}"


def game_running() -> bool:
    if WINDOWS:
        listing = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXECUTABLE}", "/NH"],
                                 capture_output=True, text=True)
        return EXECUTABLE.lower() in listing.stdout.lower()
    if shutil.which("pgrep"):
        return subprocess.run(["pgrep", "-x", EXECUTABLE], capture_output=True).returncode == 0
    return False


def powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def prepare_state(state: Path) -> None:
    for directory in ("",) + STATE_DIRECTORIES:
        (state / directory).mkdir(parents=True, exist_ok=True)
    pending = state / "reports" / "pending-report.json"
    if pending.is_file():
        pending.unlink()


def build_mods(state: Path, game: Path, build: Path) -> None:
    """Mods' database patches (NP-10.2) and archive members and merges
    (NP-10.1, NP-10.2), rebuilt from the player's files before each start."""
    if not (state / "mods").is_dir():
        return
    patches = [sys.executable, str(ROOT / "tools" / "build-mod-patches.py"), str(state),
               "--game-root", str(game)]
    if subprocess.run(patches, stdout=subprocess.DEVNULL).returncode:
        raise LaunchError("could not build the mods' database patches")
    archives = [sys.executable, str(ROOT / "tools" / "build-mod-archives.py"), str(state),
                "--game-root", str(game)]
    extractor = build / ("pinyon_shift_fh1_archive_extract" + (".exe" if WINDOWS else ""))
    if extractor.is_file():
        archives += ["--archive-extractor", str(extractor)]
    if subprocess.run(archives, stdout=subprocess.DEVNULL).returncode:
        raise LaunchError("could not build the mods' archive members")


def prepare_shaders(state: Path, game: Path, build: Path) -> None:
    shell = powershell()
    if shell is None:
        raise LaunchError("PowerShell is needed to prepare Vulkan shader storage "
                          "(or pass --skip-shader-preparation)")
    command = [shell, "-NoProfile", "-File", str(ROOT / "tools" / "prepare-fh1-shaders.ps1"),
               "-StateRoot", str(state), "-GameRoot", str(game), "-BuildDirectory", str(build)]
    if subprocess.run(command, stdout=subprocess.DEVNULL).returncode:
        raise LaunchError("could not prepare Vulkan shader storage")


def crash_report(state: Path, executable: Path, started: datetime, pid: int,
                 exit_code: int) -> dict:
    shell = powershell()
    if not WINDOWS or shell is None:
        return {}
    command = [shell, "-NoProfile", "-File", str(ROOT / "tools" / "create-crash-report.ps1"),
               "-StateRoot", str(state), "-Executable", str(executable),
               "-StartedUtc", started.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
               "-ProcessId", str(pid), "-ExitCode", str(exit_code), "-Json"]
    completed = subprocess.run(command, capture_output=True, text=True)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}


def launch(args: argparse.Namespace) -> dict:
    build = (args.build_directory or default_build_directory(args.configuration)).resolve()
    executable = build / EXECUTABLE
    game = (args.game_root or ROOT / ".local" / "game" / "base").resolve()
    state = (args.state_root or ROOT / ".local" / "preview").resolve()
    if not executable.is_file():
        raise LaunchError(f"the game is not built at {build}")
    if not (game / "default.xex").is_file():
        raise LaunchError(f"game files are missing at {game}")
    if game_running():
        raise LaunchError("Pinyon Shift is already running")
    prepare_state(state)
    if WINDOWS and not args.skip_shader_preparation and not args.render_test_script:
        prepare_shaders(state, game, build)
    build_mods(state, game, build)

    environment = dict(os.environ)
    environment.update({"PINYON_SHIFT_STATE_ROOT": str(state),
                        "PINYON_SHIFT_GAME_ROOT": str(game),
                        "REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING": "false"})
    arguments = list(args.game_arguments)
    if args.hidden:
        environment["REX_WINDOW_HIDDEN"] = "1"
        arguments.append("--audio_mute=true")
    if args.render_test_script:
        environment["PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT"] = str(args.render_test_script.resolve())
        if args.render_test_output:
            environment["PINYON_SHIFT_FH1_RENDER_TEST_OUTPUT"] = str(
                args.render_test_output.resolve())
        if not args.include_opening_movies:
            arguments.append("--pinyon_shift_skip_opening_movies=true")
    started = datetime.now(timezone.utc)
    process = subprocess.Popen([str(executable)] + arguments, cwd=str(build), env=environment)
    try:
        exit_code = process.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise LaunchError(f"timed out after {args.timeout} seconds")
    if WINDOWS and exit_code >= 0x80000000:
        exit_code -= 1 << 32  # NTSTATUS, as launch-preview.ps1 reports it
    result = {"result": "normal-exit" if exit_code == 0 else "crash",
              "process_id": process.pid, "exit_code": exit_code}
    if exit_code:
        report = crash_report(state, executable, started, process.pid, exit_code)
        for key in ("crash_id", "bundle", "issue_url"):
            if key in report:
                result[key] = report[key]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("launch", help="start the game")
    start.add_argument("--configuration", choices=("Release", "RelWithDebInfo"),
                       default="Release")
    start.add_argument("--build-directory", type=Path)
    start.add_argument("--game-root", type=Path)
    start.add_argument("--state-root", type=Path)
    start.add_argument("--hidden", action="store_true", help="no window, audio muted")
    start.add_argument("--skip-shader-preparation", action="store_true")
    start.add_argument("--render-test-script", type=Path)
    start.add_argument("--render-test-output", type=Path)
    start.add_argument("--include-opening-movies", action="store_true",
                       help="play the opening movies in a render test")
    start.add_argument("--timeout", type=float, help="seconds before the game is stopped")
    start.add_argument("--json", action="store_true", help="print the result as JSON")
    start.add_argument("game_arguments", nargs="*", help="after --, passed to the game")
    pinyon_android.add_parser(commands)
    pinyon_deck.add_parser(commands)
    args = parser.parse_args(argv)
    if args.command == "android":
        return pinyon_android.main(args)
    if args.command == "deck":
        return pinyon_deck.main(args)
    try:
        result = launch(args)
    except LaunchError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result) if args.json else "\n".join(f"{k}: {v}" for k, v in result.items()))
    return 0 if result["result"] == "normal-exit" else 1


if __name__ == "__main__":
    sys.exit(main())
