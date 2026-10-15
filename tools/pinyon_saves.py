#!/usr/bin/env python3
"""Bring a save in from another Pinyon Shift install or from Xenia (LX-3.8).

  pinyon.py import-save PATH [--state-root DIR] [--json]
  pinyon.py import-save --xenia PATH [--xuid XUID] [--state-root DIR] [--json]
  pinyon.py import-save --default-profile [--state-root DIR] [--json]

PATH is another install's state (its .local/preview folder or the
%LOCALAPPDATA%\\PinyonShift\\source\\<version>\\.local\\preview folder of a
Windows PC), its user folder, or a ZIP of either. As the Android app does
with a PC's save (SetupActivity.backUpSave), the profiles here are first
copied to <state>/backups/before-import-<time>/user, the shared DLC content
(user/0000000000000000) is left alone, and the source is never changed.
Each source tree goes to the same tree here: user to user, and user-modded
(the profile the game plays while cheats or mods are on) to user-modded, so
cheated progress never reaches the player's own save (src/cheats.cpp). When
the imported profile is not the one selected, user_xuid in pinyon_shift.toml
selects it (with a backup of the file).

--xenia is tools/import-xenia-save.ps1 (now a wrapper over this): FH1 signs
its saves with the profile's XUID, so a save from Xenia's
content/<XUID>/4D5309C9 is copied to <state>/user/<XUID>/4D5309C9 beside the
current save, which is never changed, and user_xuid selects it.
--default-profile selects the default profile again.

Prints one JSON object; a failure prints {"result": "error", "error": ...}.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402
import pinyon_config as config  # noqa: E402

TITLE = common.TITLE_ID
PROFILE_FILE = ("00000001", "ForzaProfile", "ForzaProfile")


class SaveError(common.CommandError):
    pass


def usable_xuid(value: str) -> bool:
    if len(value) != 16:
        return False
    try:
        number = int(value, 16)
    except ValueError:
        return False
    # Titles refuse XUIDs with these bits; the runtime falls back to its default.
    return number != 0 and number & 0x00C0000000000000 == 0


def config_path(state: Path) -> Path:
    return state / "config" / "pinyon_shift.toml"


def select_xuid(state: Path, xuid: str) -> str | None:
    """user_xuid = "<xuid>", after a backup of the settings file."""
    path = config_path(state)
    text = config.read_config(path)
    backup = config.backup_config(path)
    config.write_config(path, config.set_value(text, "user_xuid", f'"{xuid}"'))
    return backup


def selected_xuid(state: Path) -> str:
    return (config.get_value(config.read_config(config_path(state)), "user_xuid",
                             common.DEFAULT_XUID) or common.DEFAULT_XUID).upper()


def has_save(title: Path) -> bool:
    return common.path_ignoring_case(title, *PROFILE_FILE) is not None and \
        common.path_ignoring_case(title, *PROFILE_FILE).is_file()


def copy_into_place(source: Path, destination: Path) -> None:
    """Copies source to destination through a staging folder beside it, so a
    failed copy never leaves a partial save where the game looks."""
    staging = destination.with_name(f"{destination.name}.import-{uuid.uuid4().hex}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source, staging, symlinks=False)
        common.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


# --- From Xenia ---------------------------------------------------------------------

def import_xenia(state: Path, source: Path, xuid: str | None) -> dict:
    source = source.expanduser()
    if not source.exists():
        raise SaveError(f"{source} does not exist")
    source = source.resolve()
    title = source if source.name.lower() == TITLE.lower() else \
        common.child_ignoring_case(source, TITLE) or source / TITLE
    if not has_save(title):
        raise SaveError(f"No Forza Horizon save found. Choose the Xenia folder "
                        f"content/<XUID>/{TITLE}.")
    if not xuid:
        # The folder that holds 4D5309C9 is named after the profile's XUID.
        xuid = title.parent.name
        if not usable_xuid(xuid):
            raise SaveError("Could not find the profile XUID in the path. Pass --xuid "
                            f"(-Xuid) with the 16-digit name of the folder above {TITLE}.")
    if not usable_xuid(xuid):
        raise SaveError(f"'{xuid}' is not a usable 16-digit profile XUID.")
    xuid = xuid.upper()
    destination = state / "user" / xuid / TITLE
    if destination.exists():
        raise SaveError(f"A save for profile {xuid} already exists at {destination}; "
                        "it was left unchanged.")
    copy_into_place(title, destination)
    backup = select_xuid(state, xuid)
    return {"xuid": xuid, "save": str(destination), "config_backup": backup,
            "previous_save_kept": True}


def default_profile(state: Path) -> dict:
    backup = select_xuid(state, common.DEFAULT_XUID)
    return {"xuid": common.DEFAULT_XUID, "config_backup": backup}


# --- From another install -----------------------------------------------------------

TREES = ("user", "user-modded")


def profiles_in(user: Path) -> list[Path]:
    """The player profiles in a user tree: <xuid>/4D5309C9 with a save, not
    the shared Marketplace content."""
    if not user.is_dir():
        return []
    found = []
    for entry in sorted(user.iterdir()):
        if not entry.is_dir() or entry.name.upper() == common.CONTENT_USER:
            continue
        title = common.child_ignoring_case(entry, TITLE)
        if title is not None and has_save(title):
            found.append(entry)
    return found


def find_source_trees(root: Path) -> dict[str, Path]:
    """The save trees to import from root, by the tree they go to: a state
    folder (user/ and user-modded/), a folder holding one (.local/preview,
    preview, state), or a bare user folder (it goes to user)."""
    for state in (root, common.path_ignoring_case(root, ".local", "preview"),
                  common.path_ignoring_case(root, "preview"),
                  common.child_ignoring_case(root, "state")):
        if state is None or not state.is_dir():
            continue
        trees = {}
        for name in TREES:
            tree = common.child_ignoring_case(state, name)
            if tree is not None and profiles_in(tree):
                trees[name] = tree
        if trees:
            return trees
    if profiles_in(root):
        return {"user": root}
    raise SaveError("No Pinyon Shift save found there. Choose the other install's "
                    ".local/preview folder (or its user folder), or a ZIP of it.")


def safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            name = member.filename.replace("\\", "/")
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or ":" in name or "\0" in name:
                raise SaveError("the ZIP holds an unsafe member path")
        source.extractall(destination)


def back_up_profiles(state: Path, replaced: dict[str, set[str]]) -> Path | None:
    """SetupActivity.backUpSave: every profile of each tree that receives
    profiles (not the DLC content) into <state>/backups/before-import-<time>/
    <tree>. The profiles about to be replaced are moved there; the others
    are copied."""
    found = {}
    for name in replaced:
        tree = state / name
        entries = [entry for entry in sorted(tree.iterdir())
                   if entry.name.upper() != common.CONTENT_USER] if tree.is_dir() else []
        if entries:
            found[name] = entries
    if not found:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = state / "backups" / f"before-import-{stamp}"
    while backup.exists():
        backup = backup.with_name(f"before-import-{stamp}-{uuid.uuid4().hex[:6]}")
    for name, entries in found.items():
        target = backup / name
        target.mkdir(parents=True)
        for entry in entries:
            if entry.name.upper() in replaced[name]:
                continue
            if entry.is_dir():
                shutil.copytree(entry, target / entry.name, symlinks=False)
            else:
                shutil.copy2(entry, target / entry.name)
        for entry in entries:
            if entry.name.upper() in replaced[name]:
                common.rename(entry, target / entry.name)
    return backup


def import_install(state: Path, source: Path) -> dict:
    source = source.expanduser()
    if not source.exists():
        raise SaveError(f"{source} does not exist")
    source = source.resolve()
    own_trees = [state.resolve() / name for name in TREES]
    # This install's own save trees cannot be the source; its backups can.
    for own in [state.resolve()] + own_trees:
        if source == own or own in source.parents and own != state.resolve():
            raise SaveError("choose another install's save, not this one")
    with tempfile.TemporaryDirectory(prefix="pinyon-save-") as temporary:
        root = source
        if source.is_file():
            if source.suffix.lower() != ".zip" or not zipfile.is_zipfile(source):
                raise SaveError("choose a folder or a ZIP")
            safe_extract(source, Path(temporary))
            root = Path(temporary)
        trees = find_source_trees(root)
        if any(tree.resolve() in own_trees for tree in trees.values()):
            raise SaveError("choose another install's save, not this one")
        profiles = {name: profiles_in(tree) for name, tree in trees.items()}
        replaced = {name: {profile.name.upper() for profile in found}
                    for name, found in profiles.items()}
        state.mkdir(parents=True, exist_ok=True)
        backup = back_up_profiles(state, replaced)
        imported: dict[str, list[str]] = {}
        for name, found in profiles.items():
            for profile in found:
                copy_into_place(profile, state / name / profile.name.upper())
                imported.setdefault(name, []).append(profile.name.upper())
    own = imported.get("user", [])
    result = {"imported_profiles": own, "imported_modded_profiles": imported.get("user-modded", []),
              "source_trees": sorted(imported), "backup": str(backup) if backup else None,
              "config_backup": None, "xuid": selected_xuid(state)}
    if own and result["xuid"] not in own:
        # The game loads the selected profile; select the imported one (the
        # default profile when it is among them).
        chosen = common.DEFAULT_XUID if common.DEFAULT_XUID in own else own[0]
        result["config_backup"] = select_xuid(state, chosen)
        result["xuid"] = chosen
    return result


def run(args: argparse.Namespace) -> dict:
    state = common.state_root(args.state_root)
    common.require_game_closed("changing saves")
    if args.default_profile:
        if not state.is_dir():
            raise SaveError(f"{state} does not exist")
        return default_profile(state)
    if args.xenia:
        if not state.is_dir():
            raise SaveError(f"{state} does not exist")
        return import_xenia(state, args.xenia, args.xuid)
    if args.path is None:
        raise SaveError("choose the save to import (a folder or a ZIP), or --xenia PATH")
    return import_install(state, args.path)


def add_parser(commands) -> None:
    parser = commands.add_parser("import-save", help="bring a save from another install or Xenia")
    parser.add_argument("path", type=Path, nargs="?",
                        help="another install's .local/preview (or user) folder, or a ZIP of it")
    parser.add_argument("--xenia", type=Path, help="a Xenia content/<XUID>/4D5309C9 folder")
    parser.add_argument("--xuid", help="with --xenia: the profile XUID, when the path lacks it")
    parser.add_argument("--default-profile", action="store_true",
                        help="select the default profile again")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(run, args)
