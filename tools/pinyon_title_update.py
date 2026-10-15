#!/usr/bin/env python3
"""The optional FH1 v4 title update on every OS (TITLE_UPDATE_V4_BACKLOG, LX-3.4).

  pinyon.py title-update status   [--state-root DIR] [--json]
  pinyon.py title-update import PATH        verify against the disc and install
  pinyon.py title-update enable | disable   play v4 or the base disc
  pinyon.py title-update club-on | club-off offline 1000 Club with v4
  pinyon.py title-update restore            bring back the profile from before v4
  pinyon.py title-update build  [--jobs N]  build the v4 executable

This is the one implementation of the Windows launcher's title-update row:
tools/manage-title-update.ps1 is a thin wrapper over it. The choice is kept
in <state>/config/title-update.json ({"use": bool, "club": bool}), which
`pinyon.py launch` follows. PATH is the player's update package
(tu00000001_00000000), a folder holding it, or a ZIP of either; it is checked
by tools/verify-fh1-title-update.py and installed into
<state>/title-update-v4.

Every action prints one status object: {"result": "ok", "installed", "use",
"club", "built", "stale", "build_directory", "profiles", "pre_v4_backups"};
a failure prints {"result": "error", "error": ...}. `build` streams the
build's ::pinyon:: progress events with --json before that object.

The v4 build (out/build/<platform>-v4) translates copies of the disc's
executables with the player's patches applied (.local/game/v4-codegen into
.local/generated-v4) with the generator the base build made, then builds
the linux-amd64-v4, macos-arm64-v4 or win-amd64-v4 preset. On Windows that is
tools/build-v4.ps1.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402

TOOLS = common.ROOT / "tools"
UPDATE_FOLDER = "title-update-v4"
UPDATE_FILES = ("default.xexp", "SpeechFacade_default.xexp", "XMediaFacade_default.xexp",
                "media.zip")
MODULES = ("default", "SpeechFacade_default", "XMediaFacade_default")
# Offline 1000 Club (TU-7): report a LIVE sign-in, answer 1000 Club's server
# checks and confirm completed goals locally, as launch-preview.ps1 and
# Android's SetupActivity.setClubArguments pass them.
CLUB_ARGUMENTS = ("--pinyon_shift_car_challenge_gate_probe=true", "--xam_report_live_signin=true")


def _module(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / file)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def choice_path(state: Path) -> Path:
    return state / "config" / "title-update.json"


def read_choice(state: Path) -> dict:
    """use: run v4; club: offline 1000 Club. Only these two are kept."""
    result = {"use": False, "club": False}
    try:
        # PowerShell 5.1 writes a byte-order mark.
        saved = json.loads(choice_path(state).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return result
    if isinstance(saved, dict):
        for name in result:
            if name in saved:
                result[name] = bool(saved[name])
    return result


def write_choice(state: Path, name: str, value: bool) -> None:
    saved = read_choice(state)
    saved[name] = value
    common.write_json_atomic(choice_path(state), saved)


def installed(state: Path) -> bool:
    return all((state / UPDATE_FOLDER / name).is_file() for name in UPDATE_FILES)


def v4_build() -> Path:
    return common.build_directory(v4=True)


def v4_stale(build: Path) -> bool:
    """A release install rebuilt its source (a launcher update) since this
    v4 build: its record names another source payload."""
    marker = common.ROOT / ".pinyon-source-sha256"
    record = build / "pinyon_shift_build.json"
    if not marker.is_file() or not record.is_file():
        return False
    try:
        built_from = json.loads(record.read_text(encoding="utf-8")).get(
            "pinyon_shift_source_payload_sha256")
    except (OSError, ValueError):
        return False
    return (built_from or "").lower() != marker.read_text(encoding="ascii").strip().lower()


def profile_status(state: Path) -> dict:
    return _module("title_update_profile", "title-update-profile.py").status(state)


def status(state: Path) -> dict:
    build = v4_build()
    saved = read_choice(state)
    present = installed(state)
    built = (build / common.EXECUTABLE).is_file()
    profiles = profile_status(state)
    return {"installed": present, "use": saved["use"] and present, "club": saved["club"],
            "built": built, "stale": built and not common.WINDOWS and v4_stale(build),
            "build_directory": str(build), "profiles": profiles["profiles"],
            "pre_v4_backups": profiles["pre_v4_backups"]}


def wants_v4(state: Path) -> bool:
    saved = read_choice(state)
    return saved["use"] and installed(state)


def extract_zip(archive: Path, destination: Path) -> None:
    """Expand-Archive, without member paths that leave the folder."""
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            name = member.filename.replace("\\", "/")
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or ":" in name or "\0" in name:
                raise common.CommandError("the ZIP holds an unsafe member path")
        source.extractall(destination)


def import_update(state: Path, source: Path, game: Path) -> None:
    source = source.expanduser()
    if not source.exists():
        raise common.CommandError(f"{source} does not exist")
    extractor = common.require_extractor()
    missing = [f"{module}.xex" for module in MODULES if not (game / f"{module}.xex").is_file()]
    if missing:
        raise common.CommandError(f"The title update was not installed: the disc executables "
                                  f"({', '.join(missing)}) are missing from {game}. Set up the "
                                  "game first, or pass --game-root.")
    with tempfile.TemporaryDirectory(prefix="pinyon-tu-") as temporary:
        package = source.resolve()
        if package.is_file() and package.suffix.lower() == ".zip":
            try:
                extract_zip(package, Path(temporary))
            except zipfile.BadZipFile:
                raise common.CommandError("The title update was not installed: "
                                          "the ZIP cannot be read") from None
            package = Path(temporary)
        completed = subprocess.run(
            [common.python_executable(), str(TOOLS / "verify-fh1-title-update.py"), str(package),
             "--install", str(state), "--extractor", str(extractor), "--base-root", str(game)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        try:
            message = json.loads(completed.stdout).get("error")
        except ValueError:
            message = None
        raise common.CommandError("The title update was not installed: " +
                                  (message or "it does not apply to this disc"))


def restore(state: Path) -> None:
    try:
        _module("title_update_profile", "title-update-profile.py").restore(state)
    except (OSError, ValueError) as error:
        raise common.CommandError(f"The pre-v4 profile was not restored: {error}") from None


def backup_profiles(state: Path) -> dict:
    """Before a v4 start: a v4 save is one-way, so every base-version profile
    is copied once before its first v4 load (title-update-profile.py)."""
    try:
        return _module("title_update_profile", "title-update-profile.py").backup(state)
    except (OSError, ValueError) as error:
        raise common.CommandError(f"Could not back up the profile before its first v4 load: "
                                  f"{error}") from None


def build(state: Path, game: Path, jobs: int | None, as_json: bool) -> None:
    for module in MODULES:
        if not (game / f"{module}.xex").is_file():
            raise common.CommandError(f"The disc executable {module}.xex is missing from {game}.")
        if not (state / UPDATE_FOLDER / f"{module}.xexp").is_file():
            raise common.CommandError("Import the verified title update first.")
    common.require_game_closed("building")
    if common.WINDOWS:
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if shell is None:
            raise common.CommandError("PowerShell is needed to build v4 on Windows")
        command = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                   str(TOOLS / "build-v4.ps1"), "-StateRoot", str(state), "-GameRoot", str(game)]
        if jobs:
            command += ["-Parallel", str(jobs)]
        # Its output goes to stderr so that stdout carries only the result.
        if subprocess.run(command, stdout=sys.stderr).returncode:
            raise common.CommandError("The v4 build failed; see .local/logs/v4-build.log")
        return
    import pinyon_setup
    try:
        pinyon_setup.build_v4_from_cli(state, game, jobs, as_json)
    except pinyon_setup.SetupError as error:
        raise common.CommandError(str(error)) from None


def run(args: argparse.Namespace) -> dict:
    state = common.state_root(args.state_root)
    action = args.title_update_command
    # The choice is read at the next start; the update files and the profiles
    # are in use while v4 runs.
    if action in ("import", "restore"):
        common.require_game_closed("changing the title update")
    if action == "import":
        import_update(state, args.path, common.game_root(args.game_root))
    elif action == "enable":
        if not installed(state):
            raise common.CommandError("Import the verified title update first.")
        write_choice(state, "use", True)
    elif action == "disable":
        write_choice(state, "use", False)
    elif action == "club-on":
        write_choice(state, "club", True)
    elif action == "club-off":
        write_choice(state, "club", False)
    elif action == "restore":
        restore(state)
    elif action == "build":
        build(state, common.game_root(args.game_root), args.jobs, args.json)
    return status(state)


def add_parser(commands) -> None:
    parser = commands.add_parser("title-update", help="the optional FH1 v4 title update")
    sub = parser.add_subparsers(dest="title_update_command", required=True)
    sub.add_parser("status", help="show whether v4 is installed, chosen and built")
    importing = sub.add_parser("import", help="verify your title update and install it")
    importing.add_argument("path", type=Path, help="the package, a folder holding it, or a ZIP")
    for name, text in (("enable", "play v4"), ("disable", "play the base disc"),
                       ("club-on", "run 1000 Club offline with v4"),
                       ("club-off", "leave 1000 Club to its servers"),
                       ("restore", "restore the profile from before v4")):
        sub.add_parser(name, help=text)
    building = sub.add_parser("build", help="build the v4 executable")
    building.add_argument("--jobs", type=int, help="parallel compile jobs")
    for action in sub.choices.values():
        action.add_argument("--state-root", type=Path)
        action.add_argument("--game-root", type=Path)
        action.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(run, args)
