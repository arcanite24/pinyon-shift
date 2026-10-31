#!/usr/bin/env python3
"""The launcher's mod manager (FB-9.1): list, switch, order, install and
remove the mods in <state>/mods.

  pinyon.py mods list [--state-root DIR] [--json]
  pinyon.py mods enable NAME
  pinyon.py mods disable NAME
  pinyon.py mods move NAME up|down
  pinyon.py mods option NAME KEY VALUE      (a choice of the mod's [[option]])
  pinyon.py mods install PATH [--replace]   (a ZIP or a folder)
  pinyon.py mods remove NAME

Every command takes --state-root and --json and prints one object:
{"result": "ok", "mods": [...], "save": {...}, ...} or {"result": "error",
"error": ...}. Mods are switched by rewriting `enabled_mods` in
<state>/config/pinyon_shift.toml, as F6 > SETTINGS > MODS does; the game
reads it at the next start, and the launcher rebuilds the generated database
and archive mods (build-mod-patches.py, build-mod-archives.py) before then.

Each listed mod carries what its mod.toml says for the player (title,
description, author, url, images; docs/MODDING.md), what it contains, and
the problems that would keep the game from loading it: the same checks as
src/mod/mod_host.cpp (name, abi, game_version, requires, conflicts). The
generated mods and the built-in mods that are always on are not listed, as
on F6 > MODS. Changes refuse while the game runs, which keeps its own
settings file from writing the list back.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import re
import shutil
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mod_options  # noqa: E402
import pinyon_common as common  # noqa: E402

ABI = 1  # PINYON_MOD_ABI_VERSION, include/pinyon_mod.h
BUILDS = {"DB40DF605ADE49A6": "base disc", "74B033805AB1BCAA": "title update v4"}
NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
TITLE_LIMIT = 80
TEXT_LIMIT = 4000
IMAGE_LIMIT = 8
# Mods another launcher screen makes and switches.
MANAGED = {"custom_radio": "Radio", "xe": "DLC"}
CONTENTS = (("code", "native code"), ("game", "game files"), ("members", "archive members"),
            ("add", "archive members"), ("merge", "merged settings"),
            ("merge-update", "merged settings"), ("strings", "text"), ("db", "database"),
            ("textures", "textures"), ("shaders", "shaders"), ("update", "title update files"))


@functools.lru_cache(maxsize=None)
def _patches():
    spec = importlib.util.spec_from_file_location(
        "build_mod_patches", Path(__file__).with_name("build-mod-patches.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_mod_patches"] = module
    spec.loader.exec_module(module)
    return module


def config_path(state: Path) -> Path:
    return state / "config" / "pinyon_shift.toml"


def read_manifest(directory: Path) -> tuple[dict, str | None]:
    try:
        text = (directory / "mod.toml").read_text(encoding="utf-8")
    except OSError:
        return {}, "mod.toml cannot be read"
    try:
        return tomllib.loads(text), None
    except tomllib.TOMLDecodeError as error:
        return {}, f"mod.toml cannot be read: {error}"


def _text(manifest: dict, key: str, limit: int) -> str:
    value = manifest.get(key)
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _description(manifest: dict) -> str:
    # Paragraphs survive; lines inside a paragraph join, as in Markdown.
    value = manifest.get("description")
    if not isinstance(value, str):
        return ""
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n[ \t]*\n", value.strip())]
    return "\n\n".join(p for p in paragraphs if p)[:TEXT_LIMIT]


def _strings(manifest: dict, key: str) -> list[str]:
    value = manifest.get(key, [])
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _images(directory: Path, manifest: dict) -> list[str]:
    """`images`, in order, that are PNG or JPEG files inside the mod."""
    found = []
    root = directory.resolve()
    for entry in _strings(manifest, "images")[:IMAGE_LIMIT]:
        path = (directory / entry).resolve()
        if path.suffix.lower() in IMAGE_SUFFIXES and path.is_relative_to(root) and path.is_file():
            found.append(str(path))
    return found


def _url(manifest: dict) -> str:
    url = _text(manifest, "url", 500)
    return url if re.match(r"https?://[^\s\"<>]+$", url) else ""


def _game_versions(manifest: dict) -> list[str]:
    value = manifest.get("game_version", "")
    values = value if isinstance(value, list) else [value]
    return [v for v in values if isinstance(v, str) and v]


def _matches(game: str, executable: str) -> bool:
    # mod_host.cpp: either is a prefix of the other.
    return executable.startswith(game) or game.startswith(executable)


def active_executable(state: Path, enabled: list[str]) -> str:
    """The build the next start runs: v4 when it is chosen and installed,
    except while XE is on (it targets the base disc)."""
    import pinyon_title_update  # noqa: PLC0415  (imports the build tools)
    v4 = pinyon_title_update.wants_v4(state) and "xe" not in enabled
    return next(sha for sha, build in BUILDS.items() if build == ("title update v4" if v4
                                                                    else "base disc"))


def describe(state: Path, name: str, enabled: list[str], installed: set[str],
             executable: str) -> dict:
    directory = state / "mods" / name
    manifest, problem = read_manifest(directory)
    problems = [problem] if problem else []
    if not problem:
        if manifest.get("name") != name:
            problems.append("mod.toml names another mod")
        if manifest.get("abi") != ABI:
            problems.append("made for another version of the mod system")
        versions = _game_versions(manifest)
        if versions and not any(_matches(v, executable) for v in versions):
            builds = sorted({BUILDS.get(sha) for v in versions for sha in BUILDS
                             if _matches(v, sha)} - {None})
            problems.append(f"made for the {' and '.join(builds)}, not the build you play"
                            if builds else "made for another game executable")
    for requirement in _strings(manifest, "requires"):
        if requirement not in installed:
            problems.append(f"needs {requirement}, which is not installed")
        elif requirement not in enabled:
            problems.append(f"needs {requirement} switched on")
    for other in _strings(manifest, "conflicts"):
        if other in enabled and other != name:
            problems.append(f"cannot run with {other}")
    # Options as build-mod-patches.py's option_values reads them: only [[option]] tables.
    options = []
    tables = manifest.get("option")
    if isinstance(tables, list) and tables and all(isinstance(t, dict) for t in tables):
        try:
            declared = mod_options.declared(manifest)
            values = mod_options.chosen(state, name, declared)
            options = [{"key": o.key, "title": o.title, "description": o.description,
                        "choices": [{"value": c.value, "label": c.label} for c in o.choices],
                        "value": values[o.key]} for o in declared]
        except mod_options.OptionError as error:
            problems.append(f"its options cannot be read: {error}")
    builtin = (directory / _patches().BUILTIN_MARKER).is_file()
    versions = _game_versions(manifest)
    contents = list(dict.fromkeys(label for folder, label in CONTENTS
                                  if (directory / folder).is_dir()))
    if isinstance(manifest.get("library"), str) and "native code" not in contents:
        contents.insert(0, "native code")
    profile = manifest.get("profile") if isinstance(manifest.get("profile"), str) else ""
    return {
        "name": name,
        "title": _text(manifest, "title", TITLE_LIMIT) or name,
        "version": _text(manifest, "version", 40),
        "author": _text(manifest, "author", TITLE_LIMIT),
        "description": _description(manifest),
        "url": _url(manifest),
        "images": _images(directory, manifest),
        "enabled": name in enabled,
        "builtin": builtin,
        "managed_by": MANAGED.get(name),
        "shares_save": manifest.get("shares_save") is True,
        "profile": profile if profile and NAME.fullmatch(profile) else "",
        "contents": contents,
        "builds": sorted({BUILDS[sha] for v in versions for sha in BUILDS if _matches(v, sha)}),
        "requires": _strings(manifest, "requires"),
        "conflicts": _strings(manifest, "conflicts"),
        "options": options,
        "problems": problems,
    }


def hidden(state: Path, name: str) -> bool:
    """Generated mods and built-ins that are always on: not the player's to
    switch (F6 > MODS leaves them out too)."""
    if name in _patches().GENERATED_MODS:
        return True
    directory = state / "mods" / name
    if not (directory / _patches().BUILTIN_MARKER).is_file():
        return False
    manifest, _ = read_manifest(directory)
    return manifest.get("always_enabled") is True


def installed_mods(state: Path) -> list[str]:
    root = state / "mods"
    if not root.is_dir():
        return []
    return sorted((p.name for p in root.iterdir()
                   if p.is_dir() and NAME.fullmatch(p.name) and (p / "mod.toml").is_file()),
                  key=str.lower)


def save_choice(state: Path, mods: list[dict]) -> dict:
    """The profile the switched-on mods play (mod_host.cpp RequestedProfile
    and ModsShareSave): none, or all sharing the save, keep the player's own;
    the first with `profile` plays its own new save; otherwise the shared
    modded copy. A database patch never shares the save. The generated mods
    follow their sources: the next start rebuilds or removes them, so one
    left in enabled_mods after its sources are switched off does not count."""
    on = [m for m in mods if m["enabled"] and not m["problems"]
          and m["name"] not in _patches().GENERATED_MODS]
    profile = next((m["profile"] for m in on if m["profile"]), "")
    if profile:
        return {"profile": f"user-{profile}", "kind": "own-mod-save", "mod": next(
            m["name"] for m in on if m["profile"] == profile)}
    if all(m["shares_save"] and "database" not in m["contents"] for m in on):
        return {"profile": "user", "kind": "own"}
    return {"profile": "user-modded", "kind": "modded"}


def listing(state: Path) -> dict:
    enabled = _patches().enabled_mods(config_path(state))
    names = installed_mods(state)
    installed = set(names)
    executable = active_executable(state, enabled)
    # Hidden mods still count for requires, conflicts and the save.
    every = [describe(state, name, enabled, installed, executable) for name in names]
    order = {name: index for index, name in enumerate(enabled)}
    every.sort(key=lambda m: (not m["enabled"], order.get(m["name"], 0), m["title"].lower()))
    shown = [m for m in every if not hidden(state, m["name"])]
    missing = [name for name in enabled
               if name not in installed and name not in _patches().GENERATED_MODS]
    save = save_choice(state, every)
    # Whether the shared modded copy has been made: the launcher tells the player
    # where their modded progress went when the next start leaves it.
    save["modded_copy"] = (state / "user-modded").is_dir()
    return {"mods": shown, "save": save, "missing": missing,
            "build": BUILDS[executable], "mods_root": str(state / "mods")}


def refresh_builtins(state: Path) -> list[str]:
    """Bring installed built-in mods up to date with this build's copies, as the
    next start would (build-mod-patches.py), so the Mods view shows an updated
    built-in's options and text before then. Only runs when a built-in copy is
    stale and the game is closed; a copy in use is refreshed at the next start."""
    patches = _patches()
    stale = [marker.parent.name for marker in (state / "mods").glob(f"*/{patches.BUILTIN_MARKER}")
             if (patches.BUILTIN / marker.parent.name).is_dir()
             and patches._tree(marker.parent) != patches._tree(patches.BUILTIN / marker.parent.name)]
    if not stale or common.game_running():
        return []
    try:
        return patches.install_builtin_mods(state)
    except OSError:
        return []


def require_installed(state: Path, name: str) -> None:
    if not NAME.fullmatch(name) or not (state / "mods" / name / "mod.toml").is_file():
        raise common.CommandError(f"{name} is not installed")
    if hidden(state, name):
        raise common.CommandError(f"{name} is managed by Pinyon Shift itself")


def set_enabled(state: Path, name: str, on: bool) -> list[str]:
    """Switches a mod and returns the other mods switched on with it."""
    config = config_path(state)
    mods = _patches().enabled_mods(config)
    if not on:
        _patches().set_enabled_mods(config, [m for m in mods if m != name])
        return []
    if name in mods:
        return []
    manifest, _ = read_manifest(state / "mods" / name)
    clashes = [m for m in mods if m in _strings(manifest, "conflicts")]
    clashes += [m for m in mods if name in _strings(read_manifest(state / "mods" / m)[0],
                                                       "conflicts")]
    if clashes:
        raise common.CommandError(f"{name} cannot run with {clashes[0]}; switch that off first")
    # Installed requirements come on too, ahead of the mod (requires load
    # first anyway; the list just reads in the same order).
    added = [r for r in _strings(manifest, "requires")
             if r not in mods and (state / "mods" / r / "mod.toml").is_file()]
    _patches().set_enabled_mods(config, mods + added + [name])
    return added


def move(state: Path, name: str, direction: str) -> None:
    """Swaps a switched-on mod with its neighbour among the listed ones; the
    hidden mods keep their places. Earlier mods win where files overlap."""
    config = config_path(state)
    mods = _patches().enabled_mods(config)
    if name not in mods:
        raise common.CommandError(f"{name} is not switched on")
    visible = [i for i, m in enumerate(mods) if not hidden(state, m)]
    position = visible.index(mods.index(name))
    other = position + (-1 if direction == "up" else 1)
    if 0 <= other < len(visible):
        a, b = visible[position], visible[other]
        mods[a], mods[b] = mods[b], mods[a]
        _patches().set_enabled_mods(config, mods)


ARCHIVE_KINDS = {".7z": "7-Zip", ".rar": "RAR", ".tar": "TAR", ".gz": "gzip", ".xz": "xz",
                 ".bz2": "bzip2", ".zst": "Zstandard"}


def _not_a_zip(path: Path) -> str:
    """Why a file is not something `install` takes, and what to do instead. The XE
    archives have their own installer (pinyon_xe.py, DLC > Install XE), which needs
    both; they are known by name or size, so this never reads 2 GB."""
    import pinyon_xe  # noqa: PLC0415  (only for its archive list)
    size = path.stat().st_size
    if any(path.name.lower() == known["file"].lower() or size == known["size"]
           for known in pinyon_xe.ARCHIVES.values()):
        return (f"{path.name} is part of the Forza Horizon XE mod; install XE from DLC > "
                "Install XE, which takes both of its archives")
    kind = ARCHIVE_KINDS.get(path.suffix.lower())
    if kind:
        return (f"{path.name} is a {kind} archive, and mods install from a ZIP or a folder; "
                "extract it, then use Install folder on the folder with mod.toml")
    return f"{path.name} is not a ZIP; choose a mod's ZIP or its folder"


def _safe_members(archive: zipfile.ZipFile) -> None:
    for member in archive.infolist():
        name = member.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or ":" in name or "\0" in name:
            raise common.CommandError("the ZIP holds an unsafe member path")


def _sources(root: Path) -> list[Path]:
    """The mod folders in an unpacked download: the folder itself when it has
    a mod.toml, else each child folder with one (a pack of mods), else one
    level further down (a ZIP that wraps them in its own folder)."""
    if (root / "mod.toml").is_file():
        return [root]
    children = sorted(p for p in root.iterdir() if p.is_dir())
    found = [p for p in children if (p / "mod.toml").is_file()]
    if not found and len(children) == 1:
        return _sources(children[0])
    return found


def install(state: Path, source: Path, replace: bool) -> list[str]:
    source = source.expanduser()
    if not source.exists():
        raise common.CommandError(f"{source} does not exist")
    mods_root = state / "mods"
    mods_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".installing-", dir=mods_root) as temporary:
        root = source.resolve()
        if root.is_file():
            try:
                with zipfile.ZipFile(root) as archive:
                    _safe_members(archive)
                    archive.extractall(temporary)
            except zipfile.BadZipFile:
                raise common.CommandError(_not_a_zip(root)) from None
            root = Path(temporary)
        folders = _sources(root)
        if not folders:
            raise common.CommandError("no mod.toml found; a mod's folder holds one")
        plan = []
        for folder in folders:
            manifest, problem = read_manifest(folder)
            if problem:
                raise common.CommandError(problem)
            name = manifest.get("name")
            if not isinstance(name, str) or not NAME.fullmatch(name):
                raise common.CommandError("mod.toml needs a name of letters, digits, _ and -")
            target = mods_root / name
            if name in _patches().GENERATED_MODS or name in MANAGED:
                raise common.CommandError(f"{name} is made by Pinyon Shift itself")
            if (target / _patches().BUILTIN_MARKER).is_file():
                raise common.CommandError(f"{name} is a built-in mod and cannot be replaced")
            if target.exists() and not replace:
                raise common.CommandError(f"{name} is already installed")
            plan.append((folder, name, target))
        for folder, name, target in plan:
            staging = Path(temporary) / f".{name}.staging"
            shutil.copytree(folder, staging)
            if target.exists():
                _patches().remove_written_directory(target)
            common.rename(staging, target)
    return [name for _, name, _ in plan]


def remove(state: Path, name: str) -> None:
    require_installed(state, name)
    directory = state / "mods" / name
    if (directory / _patches().BUILTIN_MARKER).is_file():
        raise common.CommandError(f"{name} is built in; switch it off instead")
    if name in MANAGED:
        raise common.CommandError(f"{name} is removed on the {MANAGED[name]} screen")
    set_enabled(state, name, False)
    _patches().remove_written_directory(directory)


def run(args: argparse.Namespace) -> dict:
    state = common.state_root(args.state_root)
    command = args.mods_command
    notes = {}
    if command == "list":
        refresh_builtins(state)
    else:
        common.require_game_closed("changing mods")
        config_path(state).parent.mkdir(parents=True, exist_ok=True)
    if command in ("enable", "disable", "move", "option"):
        require_installed(state, args.name)
    if command == "option":
        try:
            declared = mod_options.read_declared(state / "mods" / args.name)
            mod_options.choose(state, args.name, declared, args.key, args.value)
        except mod_options.OptionError as error:
            raise common.CommandError(str(error)) from None
    if command == "enable":
        notes["also_enabled"] = set_enabled(state, args.name, True)
    elif command == "disable":
        set_enabled(state, args.name, False)
    elif command == "move":
        move(state, args.name, args.direction)
    elif command == "install":
        notes["installed"] = install(state, args.path, args.replace)
    elif command == "remove":
        remove(state, args.name)
    return {"result": "ok", **listing(state), **notes}


def add_parser(commands) -> None:
    parser = commands.add_parser("mods", help="list, switch, order, install and remove mods")
    sub = parser.add_subparsers(dest="mods_command", required=True)
    sub.add_parser("list", help="the installed mods, switched-on ones first in load order")
    for action, text in (("enable", "switch a mod on (and the mods it requires)"),
                         ("disable", "switch a mod off"),
                         ("remove", "switch a mod off and delete its folder")):
        sub.add_parser(action, help=text).add_argument("name")
    moving = sub.add_parser("move", help="load a switched-on mod earlier (up) or later (down)")
    moving.add_argument("name")
    moving.add_argument("direction", choices=("up", "down"))
    choosing = sub.add_parser("option", help="choose a value of a mod's option (applies at the next start)")
    choosing.add_argument("name")
    choosing.add_argument("key")
    choosing.add_argument("value")
    installing = sub.add_parser("install", help="install mods from a ZIP or a folder")
    installing.add_argument("path", type=Path)
    installing.add_argument("--replace", action="store_true",
                            help="replace an installed mod of the same name")
    for action in sub.choices.values():
        action.add_argument("--state-root", type=Path)
        action.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(run, args)
