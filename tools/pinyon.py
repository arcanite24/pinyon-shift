#!/usr/bin/env python3
"""Pinyon Shift command-line launcher for Windows, Linux and macOS (NP-12.7).

`launch` does what tools/launch-preview.ps1 does without PowerShell: it
checks the build and the game files, prepares the state directory, rebuilds
the enabled mods' database patches, archive members and merges, sets the
environment the game reads and starts it, then reports how it exited:

  pinyon.py launch [--state-root DIR] [--game-root DIR] [--build-directory DIR]
                   [--configuration Release|RelWithDebInfo] [--hidden] [--json]
                   [--title-update-v4 | --base-disc] [--skip-shader-preparation]
                   [--render-test-script FILE --render-test-output DIR]
                   [-- game arguments...]

Play follows the title-update choice the launchers record
(<state>/config/title-update.json, `pinyon.py title-update`), as the
Windows launcher's Play does: with v4 chosen and installed it builds the v4
executable when it is missing, backs up the base-version profile before its
first v4 load, adds the offline 1000 Club arguments when chosen and skips the
base-disc Rally preparation; the XE mod, made for the base disc, wins over
v4. --title-update-v4 or --base-disc choose explicitly; render tests and an
explicit --build-directory never follow the saved choice.

Before the first start Vulkan shader storage is prepared (Windows:
tools/prepare-fh1-shaders.ps1; elsewhere tools/pinyon_shaders.py); skip it
with --skip-shader-preparation.

With --json the result is one object: {"result": ..., "process_id",
"exit_code"}, where result is normal-exit, crash (with crash_id, bundle and
issue_url of the bundle tools/pinyon_crash.py made), graphics-unavailable,
config-unavailable (with config), saved-content-unavailable, or error (with
error and a reason: not-built, game-files-missing, already-running,
title-update-missing, build-failed, profile-backup-failed, mods-failed,
rally-unavailable, shaders-failed, timeout).

Other commands, each printing one JSON object with --json:

  setup         build the game from the player's disc (LX-3); pinyon_setup.py
  shortcuts     add it to Steam and the desktop menu (LX-5.10); pinyon_steam.py
  dlc           import and manage owned DLC (LX-3.4); pinyon_dlc.py
  title-update  the optional v4 title update (LX-3.4); pinyon_title_update.py
  import-save   bring a save from another install or Xenia (LX-3.8); pinyon_saves.py
  crash-report  sanitized crash bundles (LX-3.5); pinyon_crash.py
  config        the launcher's runtime settings; pinyon_config.py
  hardware      GPU, CPU and display, and a preset for them; pinyon_hardware.py
  paths         install, state and build locations, install-root checks (LX-3.6);
                pinyon_common.py
  prepare-shaders  Vulkan shader preparation (LX-3.3); pinyon_shaders.py
  xe            the Forza Horizon XE mod (XE-1); pinyon_xe.py
  import-mod    a mod from an FH1 mod of modified game files (FB-9.2); pinyon_game_mod.py
  assets        export the player's own game files (#446); pinyon_assets.py
  radio         custom radio stations (#445); pinyon_radio.py
  mods          list, switch, order, install and remove mods (FB-9.1); pinyon_mods.py
  android       build, install and run on Android (AP-6.1); pinyon_android.py
  deck          copy a Linux build to a Steam Deck (LX-2.1); pinyon_deck.py
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_android  # noqa: E402
import pinyon_assets  # noqa: E402
import pinyon_common  # noqa: E402
import pinyon_config  # noqa: E402
import pinyon_crash  # noqa: E402
import pinyon_deck  # noqa: E402
import pinyon_dlc  # noqa: E402
import pinyon_game_mod  # noqa: E402
import pinyon_hardware  # noqa: E402
import pinyon_mods  # noqa: E402
import pinyon_radio  # noqa: E402
import pinyon_saves  # noqa: E402
import pinyon_setup  # noqa: E402
import pinyon_shaders  # noqa: E402
import pinyon_steam  # noqa: E402
import pinyon_title_update  # noqa: E402
import pinyon_xe  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
EXECUTABLE = "pinyon_shift.exe" if WINDOWS else "pinyon_shift"
EXTRACTOR = "pinyon_shift_fh1_archive_extract" + (".exe" if WINDOWS else "")
STATE_DIRECTORIES = ("cache", "config", "crashes", "logs", "reports", "update", "user")
# Exits the game takes on purpose (src/pinyon_shift_app.cpp,
# pinyon_shift_runtime_hooks.cpp); a crash report would not help. POSIX keeps
# only the low 8 bits of an exit status.
GAME_EXITS = {1306: "config-unavailable", 1307: "saved-content-unavailable",
              1308: "graphics-unavailable"}


class LaunchError(RuntimeError):
    def __init__(self, message: str, reason: str = "error"):
        super().__init__(message)
        self.reason = reason


def default_build_directory(configuration: str) -> Path:
    system = {"Windows": "win", "Darwin": "macos"}.get(platform.system(),
                                                       platform.system().lower())
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    return ROOT / "out" / "build" / f"{system}-{arch}-{configuration.lower()}"


def v4_build_directory() -> Path:
    return default_build_directory("v4")


def game_running() -> bool:
    return pinyon_common.game_running()


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
    (NP-10.1, NP-10.2), rebuilt from the player's files before each start.
    The first step also installs the built-in optional mods."""
    patches = [sys.executable, str(ROOT / "tools" / "build-mod-patches.py"), str(state),
               "--game-root", str(game)]
    if subprocess.run(patches, stdout=subprocess.DEVNULL).returncode:
        raise LaunchError("could not build the mods' database patches", "mods-failed")
    archives = [sys.executable, str(ROOT / "tools" / "build-mod-archives.py"), str(state),
                "--game-root", str(game)]
    extractor = build / EXTRACTOR
    if extractor.is_file():
        archives += ["--archive-extractor", str(extractor)]
    if subprocess.run(archives, stdout=subprocess.DEVNULL).returncode:
        raise LaunchError("could not build the mods' archive members", "mods-failed")


RALLY_CONTENT = "user/0000000000000000/4D5309C9/00000002/6F6992766050D818245ADD408031E280FB5F4E634D"


def prepare_rally(state: Path, game: Path, build: Path) -> bool:
    """Verify owned Rally and its generated cache before play, as
    launch-preview.ps1 does. True when the Rally entry is ready."""
    if not (state / RALLY_CONTENT).is_dir():
        return False
    extractor = build / EXTRACTOR
    completed = subprocess.run([sys.executable, str(ROOT / "tools" / "prepare-fh1-rally.py"),
                                "--state-root", str(state), "--game-root", str(game),
                                "--extractor", str(extractor)], capture_output=True, text=True)
    if completed.returncode:
        raise LaunchError("could not verify and prepare Rally; restore or re-import the "
                          "verified Rally package. Saved cars with Rally parts need it",
                          "rally-unavailable")
    try:
        return json.loads(completed.stdout).get("entry_ready") is True
    except json.JSONDecodeError:
        return False


def prepare_shaders(state: Path, game: Path, build: Path, as_json: bool = False) -> None:
    if not WINDOWS:
        try:
            pinyon_shaders.prepare(state, game, build, as_json)
        except pinyon_common.CommandError as error:
            raise LaunchError(str(error), "shaders-failed") from None
        return
    shell = powershell()
    if shell is None:
        raise LaunchError("PowerShell is needed to prepare Vulkan shader storage "
                          "(or pass --skip-shader-preparation)", "shaders-failed")
    command = [shell, "-NoProfile", "-File", str(ROOT / "tools" / "prepare-fh1-shaders.ps1"),
               "-StateRoot", str(state), "-GameRoot", str(game), "-BuildDirectory", str(build)]
    if subprocess.run(command, stdout=subprocess.DEVNULL).returncode:
        raise LaunchError("could not prepare Vulkan shader storage", "shaders-failed")


def crash_report(state: Path, executable: Path, started: datetime, pid: int,
                 exit_code: int) -> dict:
    """The sanitized bundle and issue link (tools/pinyon_crash.py)."""
    try:
        return pinyon_crash.create(state, executable, started, pid, exit_code)
    except (pinyon_common.CommandError, OSError, ValueError) as error:
        print(f"warning: the crash report could not be prepared: {error}", file=sys.stderr)
        return {}


def xe_enabled(state: Path) -> bool:
    try:
        status = pinyon_xe.status(argparse.Namespace(state_root=state, game_root=None))
    except (OSError, ValueError, KeyError):
        return False
    return bool(status.get("installed") and status.get("enabled"))


def choose_title_update(args: argparse.Namespace, state: Path) -> bool:
    """True to start v4: chosen on the command line, or the saved choice for
    Play. XE, made for the base disc, wins over a saved v4 choice."""
    if args.title_update_v4:
        return True
    if args.base_disc or args.render_test_script or args.build_directory:
        return False
    if not pinyon_title_update.wants_v4(state):
        return False
    if xe_enabled(state):
        print("Starting the XE mod on the base disc; title update v4 is not used while XE is on.",
              file=sys.stderr)
        return False
    return True


def prepare_title_update(args: argparse.Namespace, state: Path, game: Path, build: Path) -> list:
    """The v4 start: the verified update, the build, the one-way profile
    backup and the offline 1000 Club arguments. Returns extra game arguments."""
    if not pinyon_title_update.installed(state):
        raise LaunchError("The v4 build needs the verified title update in "
                          f"{state / pinyon_title_update.UPDATE_FOLDER}. Import it with "
                          "pinyon.py title-update import.", "title-update-missing")
    executable = build / EXECUTABLE
    stale = not WINDOWS and pinyon_title_update.v4_stale(build)
    if (not executable.is_file() or stale) and not args.build_directory:
        print("Building the FH1 v4 title update from your disc and your verified update. "
              "This takes a while the first time.", file=sys.stderr, flush=True)
        try:
            pinyon_title_update.build(state, game, None, args.json)
        except pinyon_common.CommandError as error:
            raise LaunchError(str(error), "build-failed") from None
    if not executable.is_file():
        raise LaunchError(f"the v4 build is missing at {build}", "not-built")
    try:
        pinyon_title_update.backup_profiles(state)
    except pinyon_common.CommandError as error:
        raise LaunchError(str(error), "profile-backup-failed") from None
    print("FH1 v4 title update: saves written by this build cannot be loaded by the base build.",
          file=sys.stderr)
    if args.render_test_script or not pinyon_title_update.read_choice(state)["club"]:
        return []
    print("FH1 v4 title update: 1000 Club runs offline.", file=sys.stderr)
    return list(pinyon_title_update.CLUB_ARGUMENTS)


def exit_result(exit_code: int) -> str | None:
    for code, result in GAME_EXITS.items():
        if exit_code == code or (not WINDOWS and exit_code == code & 0xFF):
            return result
    return None


def launch(args: argparse.Namespace) -> dict:
    game = (args.game_root or ROOT / ".local" / "game" / "base").resolve()
    state = (args.state_root or ROOT / ".local" / "preview").resolve()
    v4 = choose_title_update(args, state)
    if args.build_directory:
        build = args.build_directory.resolve()
    elif v4:
        build = v4_build_directory()
    else:
        build = default_build_directory(args.configuration).resolve()
    executable = build / EXECUTABLE
    if not v4 and not executable.is_file():
        raise LaunchError(f"the game is not built at {build}", "not-built")
    if not (game / "default.xex").is_file():
        raise LaunchError(f"game files are missing at {game}", "game-files-missing")
    if game_running():
        raise LaunchError("Pinyon Shift is already running", "already-running")
    arguments = list(args.game_arguments)
    if v4:
        arguments += prepare_title_update(args, state, game, build)
    elif not args.render_test_script and (refusal := pinyon_title_update.base_build_refusal(state)):
        raise LaunchError(refusal, "v4-save")
    prepare_state(state)
    if not args.skip_shader_preparation and not args.render_test_script:
        prepare_shaders(state, game, build, args.json)
    build_mods(state, game, build)
    # v4's own code replaces the base-disc Rally preparation.
    rally_ready = not v4 and not args.render_test_script and prepare_rally(state, game, build)

    environment = dict(os.environ)
    environment.update({"PINYON_SHIFT_STATE_ROOT": str(state),
                        "PINYON_SHIFT_GAME_ROOT": str(game),
                        "REX_D3D12_ALLOW_VARIABLE_REFRESH_RATE_AND_TEARING": "false"})
    environment.pop("PINYON_SHIFT_RALLY_PREPARED", None)
    if rally_ready:
        environment["PINYON_SHIFT_RALLY_PREPARED"] = "1"
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
    if args.json:
        print("::pinyon::" + json.dumps({"stage": "play", "percent": 100,
                                         "message": "Starting game."}), file=sys.stderr,
              flush=True)
    process = subprocess.Popen([str(executable)] + arguments, cwd=str(build), env=environment)
    try:
        exit_code = process.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise LaunchError(f"timed out after {args.timeout} seconds", "timeout")
    if WINDOWS and exit_code >= 0x80000000:
        exit_code -= 1 << 32  # NTSTATUS, as launch-preview.ps1 reports it
    result = {"result": "normal-exit" if exit_code == 0 else "crash",
              "process_id": process.pid, "exit_code": exit_code,
              "title_update": "v4" if v4 else "base"}
    if not WINDOWS and exit_code < 0:
        try:
            result["signal"] = signal.Signals(-exit_code).name
        except ValueError:
            pass
    special = exit_result(exit_code) if exit_code > 0 else None
    if special:
        # The game said why; the player can fix it, a crash report would not help.
        result["result"] = special
        if special == "config-unavailable":
            result["config"] = str(state / "config" / "pinyon_shift.toml")
    elif exit_code:
        report = crash_report(state, executable, started, process.pid, exit_code)
        for key in ("crash_id", "bundle", "issue_url", "graphics_driver", "graphics_memory"):
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
    version = start.add_mutually_exclusive_group()
    version.add_argument("--title-update-v4", action="store_true",
                         help="start the v4 title-update build")
    version.add_argument("--base-disc", action="store_true",
                         help="start the base disc even when v4 is chosen")
    start.add_argument("--render-test-script", type=Path)
    start.add_argument("--render-test-output", type=Path)
    start.add_argument("--include-opening-movies", action="store_true",
                       help="play the opening movies in a render test")
    start.add_argument("--timeout", type=float, help="seconds before the game is stopped")
    start.add_argument("--json", action="store_true", help="print the result as JSON")
    start.add_argument("game_arguments", nargs="*", help="after --, passed to the game")
    modules = {"android": pinyon_android, "assets": pinyon_assets, "config": pinyon_config,
               "crash-report": pinyon_crash, "deck": pinyon_deck, "dlc": pinyon_dlc,
               "hardware": pinyon_hardware, "import-mod": pinyon_game_mod, "import-save": pinyon_saves,
               "mods": pinyon_mods, "paths": pinyon_common, "prepare-shaders": pinyon_shaders,
               "radio": pinyon_radio, "setup": pinyon_setup, "shortcuts": pinyon_steam,
               "title-update": pinyon_title_update, "xe": pinyon_xe}
    for module in dict.fromkeys(modules.values()):
        module.add_parser(commands)
    args = parser.parse_args(argv)
    if args.command in modules:
        return modules[args.command].main(args)
    try:
        result = launch(args)
    except LaunchError as error:
        if args.json:
            print(json.dumps({"result": "error", "reason": error.reason, "error": str(error)}))
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result) if args.json else "\n".join(f"{k}: {v}" for k, v in result.items()))
    return 0 if result["result"] == "normal-exit" else 1


def pinned_python() -> Path | None:
    """The toolchain's Python once setup has provisioned it."""
    try:
        config = pinyon_setup.toolchain_config()
        item = pinyon_setup.platform_tools(config, pinyon_setup.host_platform()).get("python")
        executable = pinyon_setup.tool_path(item) if item else None
    except (OSError, ValueError, KeyError, pinyon_setup.SetupError):
        return None
    return executable if executable is not None and executable.is_file() else None


if __name__ == "__main__":
    # macOS's /usr/bin/python3 is 3.9: setup runs on it, but the DLC, title
    # update and save tools hash with hashlib.file_digest (3.11). Once setup
    # has provisioned the pinned Python, every command runs on that.
    if sys.version_info < (3, 11) and not os.environ.get("PINYON_SHIFT_PINNED_PYTHON"):
        pinned = pinned_python()
        if pinned is not None:
            os.environ["PINYON_SHIFT_PINNED_PYTHON"] = "1"
            os.execv(str(pinned), [str(pinned), str(Path(__file__).resolve()), *sys.argv[1:]])
    sys.exit(main())
