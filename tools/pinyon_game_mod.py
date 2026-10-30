#!/usr/bin/env python3
"""Turn an FH1 mod made of modified game files into a Pinyon Shift mod (FB-9.2).

Mods made for the Xbox 360 or Xenia usually ship the game's own files,
changed: a modded copy of the game folder, or only the files to copy over
it. This compares such a download with the player's own game and keeps only
what differs, as an asset mod <state>/mods/<name> whose game/ files replace
the game's (docs/MODDING.md). The XE installer (pinyon_xe.py) does the same
for XE's two known archives; this takes any folder or archive.

  pinyon.py import-mod SOURCE... [--name NAME] [--title TITLE] [--version V]
                       [--new-save | --keeps-save] [--any-build] [--enable]
                       [--replace] [--state-root DIR] [--game-root DIR] [--json]

Each SOURCE is a folder, a ZIP, or a 7z or RAR archive (7-Zip or bsdtar
extracts those); later sources apply over earlier ones, as a hotfix over
its release. The files may sit in a copy of the game folder (anything with
a media folder, at any depth up to three) or start inside media itself
(cars/, db/, ui/ and the like).

Only files under media/ are taken. Executables are left out: a recompiled
game cannot run a modified default.xex, so a mod that changes it is
imported with a warning, and parts of it may not work. Other files outside
media/ are listed as skipped, except readmes, which are kept with the mod.
The game accepts the replaced files without the hash-check patch some mods
need on a console or in Xenia.

The mod plays the shared modded copy of the player's save unless
--new-save (its own new save, for mods whose readme asks for one, such as
those that renumber cars) or --keeps-save (it only changes looks or sound).
It targets the base disc unless --any-build: title update v4 replaces some
of the disc's files, the database among them, from its own archive. It is
installed switched off unless --enable; the launcher's Mods panel lists
it either way.

Prints one JSON object with --json: {"result": "ok", "mod", "replaced",
"added", "unchanged", "skipped", "code_changed", "warnings"} or
{"result": "error", "error"}.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402
import pinyon_xe as xe  # noqa: E402

NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
# Mods Pinyon Shift makes and manages itself.
RESERVED = {"xe", "custom_radio", "zz-db-patches", "zz-archive-patches"}
EXECUTABLE_SUFFIXES = (".xex", ".xexp")
MEDIA_DEPTH = 3


def mod_name(value: str) -> str:
    name = re.sub(r"[^a-z0-9_-]+", "_", value.lower()).strip("_-")[:64]
    if not NAME.fullmatch(name or ""):
        raise common.CommandError("give the mod a name with --name (letters, digits, _ and -)")
    return name


def unpack(source: Path, destination: Path) -> Path:
    """A folder as it is; an archive extracted into destination."""
    if source.is_dir():
        return source
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or ":" in name or "\0" in name:
                    raise common.CommandError(f"{source.name} holds an unsafe member path")
            archive.extractall(destination)
        return destination
    if source.suffix.lower() not in (".7z", ".rar"):
        raise common.CommandError(f"{source.name} is not a folder, ZIP, 7z or RAR archive")
    try:
        extractor = xe.find_extractor()
        xe.probe(extractor, source)
        xe.extract(extractor, source, destination)
    except xe.XeError as error:
        raise common.CommandError(str(error).replace("Install XE", "import it")) from None
    root = destination.resolve()
    for path in destination.rglob("*"):
        if not path.resolve().is_relative_to(root):
            raise common.CommandError(f"{source.name} holds an unsafe member path")
    return destination


def media_prefix(root: Path, game: Path) -> tuple[Path, str]:
    """Where the game's files start in an unpacked source, and what to put in
    front of its paths: ("<folder holding media>", "") for a copy of the game
    folder, or (root, "media/") for files that start inside media."""
    level = [root]
    for _ in range(MEDIA_DEPTH + 1):
        for directory in level:
            if common.child_ignoring_case(directory, "media") is not None and \
                    common.child_ignoring_case(directory, "media").is_dir():
                return directory, ""
        level = [c for d in level for c in sorted(d.iterdir()) if c.is_dir()]
    media = common.child_ignoring_case(game, "media")
    known = {c.name.lower() for c in media.iterdir()} if media else set()
    for directory in [root] + sorted(c for c in root.iterdir() if c.is_dir()):
        if any(c.name.lower() in known for c in directory.iterdir()):
            return directory, "media/"
    raise common.CommandError("no game files found: a mod of game files has a media folder, "
                              "or folders that go in it (cars, db, ui and so on)")


def toml_string(value: str) -> str:
    # A JSON string is a TOML basic string for the text this writes.
    return json.dumps(value, ensure_ascii=False)


def mod_toml(name: str, title: str, version: str, description: str, args) -> str:
    lines = ["# Made by tools/pinyon_game_mod.py from the player's own download and game files.",
             f"name = {toml_string(name)}", f"version = {toml_string(version)}", "abi = 1",
             f"title = {toml_string(title)}", f"description = {toml_string(description)}"]
    if not args.any_build:
        lines += ["# Made for the disc: title update v4 replaces some of its files.",
                  f'game_version = "{xe.BASE_EXECUTABLE}"']
    if args.new_save:
        lines += ["# Plays its own new save.", f"profile = {toml_string(name)}"]
    if args.keeps_save:
        lines += ["# Changes only looks or sound: keeps the player's save.", "shares_save = true"]
    return "\n".join(lines) + "\n"


def import_mod(args: argparse.Namespace) -> dict:
    state = common.state_root(args.state_root)
    game = common.game_root(args.game_root)
    if not (game / "default.xex").is_file() or common.child_ignoring_case(game, "media") is None:
        raise common.CommandError(f"the game files are not at {game}; finish setup first")
    sources = [Path(s).expanduser().resolve() for s in args.sources]
    for source in sources:
        if not source.exists():
            raise common.CommandError(f"{source} does not exist")
    download = re.sub(r"\.(zip|7z|rar)$", "", sources[0].name, flags=re.I)
    name = mod_name(args.name or download)
    mods = state / "mods"
    target = mods / name
    if name in RESERVED or name.startswith("zz-"):
        raise common.CommandError(f"{name} is a name Pinyon Shift uses itself; choose another")
    if (target / ".pinyon-builtin").is_file():
        raise common.CommandError(f"{name} is a built-in mod; choose another name")
    if target.exists() and not args.replace:
        raise common.CommandError(f"{name} is already installed; pass --replace to replace it")
    common.require_game_closed("importing a mod")
    mods.mkdir(parents=True, exist_ok=True)
    quiet = args.json
    with tempfile.TemporaryDirectory(prefix=f".{name}-import-", dir=mods) as temporary:
        work = Path(temporary)
        disc = xe.index_tree(game)
        merged: dict[str, tuple[str, Path]] = {}
        outside: dict[str, Path] = {}
        for index, source in enumerate(sources):
            xe.say(f"Reading {source.name}", quiet)
            root = unpack(source, work / "sources" / str(index))
            base, prefix = media_prefix(root, game)
            # Readmes and the like beside a wrapped game folder.
            for path in (root.iterdir() if base != root else []):
                if path.is_file():
                    outside[path.name.lower()] = path
            for relative, (spelled, path) in xe.index_tree(base).items():
                # Loose files beside media's folders are the author's, not the game's.
                loose = prefix and "/" not in relative and f"media/{relative}" not in disc
                if (prefix + relative).startswith("media/") and not loose:
                    merged[prefix + relative] = (prefix + spelled, path)
                else:
                    outside[relative] = path
        xe.say("Comparing with your game files", quiet)
        output = work / "mod"
        files, unchanged = {}, 0
        for relative, (spelled_in_source, path) in sorted(merged.items()):
            original = disc[relative][1] if relative in disc else None
            sha = xe.digest(path, "sha256").upper()
            if original is not None and original.stat().st_size == path.stat().st_size \
                    and xe.digest(original, "sha256").upper() == sha:
                unchanged += 1
                continue
            spelled = xe.disc_spelling(game, spelled_in_source)
            destination = output / "game" / spelled
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            files[spelled] = {"sha256": sha, "replaces": original is not None}
        code_changed, skipped, readmes = [], [], []
        for relative, path in sorted(outside.items()):
            original = disc[relative][1] if relative in disc else None
            if relative.endswith(EXECUTABLE_SUFFIXES):
                if original is None or xe.digest(original, "sha256") != xe.digest(path, "sha256"):
                    code_changed.append(relative)
            elif PurePosixPath(relative).name.startswith("readme") and \
                    PurePosixPath(relative).suffix in (".txt", ".md", ".rtf", ".pdf"):
                readmes.append(path)
            elif original is None or original.stat().st_size != path.stat().st_size:
                skipped.append(relative)
        if not files:
            raise common.CommandError("every game file in it matches your game; there is "
                                      "nothing to import")
        replaced = sum(1 for f in files.values() if f["replaces"])
        added = len(files) - replaced
        warnings = []
        if code_changed:
            warnings.append("it also changes the game's code (" + ", ".join(code_changed)
                            + "), which Pinyon Shift cannot run; only its files were imported, "
                            "so parts of it may not work")
        if any(f.lower() == "media/db/gamedb.slt" for f in files) and not args.new_save:
            warnings.append("it replaces the game database; if its readme asks for a new save, "
                            "import it again with --new-save")
        for readme in readmes:
            shutil.copy2(readme, output / readme.name.replace(" ", "-"))
        names = ", ".join(s.name for s in sources)
        def files_text(count: int) -> str:
            return f"{count} game file{'' if count == 1 else 's'}"
        description = (f"Imported from {names}: {files_text(replaced)} replaced and "
                       f"{files_text(added)} added."
                       + (" Its changes to the game's code were left out." if code_changed else ""))
        (output / "mod.toml").write_text(
            mod_toml(name, args.title or download, args.version, description, args),
            encoding="utf-8", newline="\n")
        record = {"schema_version": 1, "sources": [s.name for s in sources],
                  "imported_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "replaced": replaced, "added": added, "unchanged_skipped": unchanged,
                  "code_changed": code_changed, "skipped": skipped, "files": files}
        (output / "import.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        if target.exists():
            xe._patches().remove_written_directory(target)
        common.rename(output, target)
    if args.enable:
        config = state / "config" / "pinyon_shift.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        patches = xe._patches()
        patches.set_enabled_mods(config, [m for m in patches.enabled_mods(config) if m != name]
                                 + [name])
    return {"result": "ok", "mod": str(target), "name": name, "enabled": args.enable,
            "replaced": replaced, "added": added, "unchanged": unchanged,
            "skipped": skipped, "code_changed": code_changed, "warnings": warnings}


def add_parser(commands) -> None:
    parser = commands.add_parser(
        "import-mod", help="make a mod from an FH1 mod of modified game files")
    parser.add_argument("sources", nargs="+",
                        help="folders or archives (ZIP, 7z, RAR); later ones apply over earlier")
    parser.add_argument("--name", help="the mod's folder name (default: from the first source)")
    parser.add_argument("--title", help="the name the launcher shows")
    parser.add_argument("--version", default="1.0")
    saves = parser.add_mutually_exclusive_group()
    saves.add_argument("--new-save", action="store_true",
                       help="play its own new save, as some mods' readmes ask")
    saves.add_argument("--keeps-save", action="store_true",
                       help="it only changes looks or sound: keep the player's save")
    parser.add_argument("--any-build", action="store_true",
                        help="also load it on title update v4 (default: the base disc only)")
    parser.add_argument("--enable", action="store_true", help="switch it on")
    parser.add_argument("--replace", action="store_true",
                        help="replace an installed mod of the same name")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(import_mod, args)
