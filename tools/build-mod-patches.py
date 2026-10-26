#!/usr/bin/env python3
"""Build the database patches of a state's enabled mods (NP-10.2).

A mod may ship SQL scripts in db/*.sql. This tool copies the player's own
media/db/gamedb.slt (a plain SQLite database the title opens loose), applies
every enabled mod's scripts in load order, and writes the result as the
asset-only mod <state>/mods/zz-db-patches, listed first in enabled_mods so
its database wins over the game's. Nothing from the disc is distributed: the
patched copy is built on the player's machine from their files. With no
scripts enabled the generated mod is removed. Run it after changing mods
(the launcher runs it before each start). The v4 title update reads its own
database from update:\\media.zip instead; build-mod-archives.py applies the
same scripts there.

  build-mod-patches.py <state-root> [--game-root DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = "zz-db-patches"
# Mods these tools write; never a base for another generated file.
GENERATED_MODS = ("zz-db-patches", "zz-archive-patches")


def enabled_mods(config: Path) -> list[str]:
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    match = re.search(r'^enabled_mods[ \t]*=[ \t]*"([^"]*)"[ \t]*$', text, re.MULTILINE)
    return [name.strip() for name in (match.group(1).split(",") if match else []) if name.strip()]


def set_enabled_mods(config: Path, mods: list[str]) -> None:
    text = config.read_text(encoding="utf-8") if config.exists() else ""
    line = f'enabled_mods = "{",".join(mods)}"'
    match = re.search(r'^enabled_mods[ \t]*=[ \t]*"([^"]*)"[ \t]*$', text, re.MULTILINE)
    if match:
        text = text[:match.start()] + line + text[match.end():]
    elif mods:
        text = text.rstrip("\n") + ("\n" if text else "") + line + "\n"
    config.write_text(text, encoding="utf-8", newline="\n")


def effective_game_file(state: Path, mods: list[str], game_root: Path, relative: str) -> Path:
    """The file the title opens at `relative`: the earliest enabled mod's
    whole-file replacement under game/ (as the host matches it, ignoring
    case), otherwise the player's own copy. A total conversion such as the
    XE mod replaces gamedb.slt and zipmanifest.xml, and generated patches
    must build on its files, not on the disc's."""
    for mod in mods:
        if mod in GENERATED_MODS:
            continue
        current = state / "mods" / mod / "game"
        for part in relative.split("/"):
            if not current.is_dir():
                break
            current = next((c for c in current.iterdir() if c.name.lower() == part.lower()),
                           current / part)
        if current.is_file():
            return current
    return game_root / relative


def hidden_dlc(state: Path) -> dict[str, str]:
    """Marketplace package ID -> the enabled mod whose mod.toml hides it
    (`hide_dlc`), as the game's mod host reads it. The XE mod cannot run
    with Rally, so the launchers leave Rally unprepared while it is on."""
    hidden: dict[str, str] = {}
    for mod in enabled_mods(state / "config" / "pinyon_shift.toml"):
        manifest = state / "mods" / mod / "mod.toml"
        text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
        match = re.search(r'^hide_dlc[ \t]*=[ \t]*\[([^\]]*)\]', text, re.MULTILINE)
        for package in re.findall(r'"([0-9A-Fa-f]{1,42})"', match.group(1) if match else ""):
            hidden.setdefault(package.upper(), mod)
    return hidden


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


BUILTIN = ROOT / "mods_src" / "builtin"
# Written into each installed built-in mod; a player's own mod of the same
# name (without it) is never replaced.
BUILTIN_MARKER = ".pinyon-builtin"


def _tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file() and path.name != BUILTIN_MARKER}


def rename_written_directory(source: Path, target: Path) -> None:
    """Rename a directory just written. On Windows a scanner can still hold
    the new files for a moment, and the rename is then denied."""
    for attempt in range(20):
        try:
            source.rename(target)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.25)


IN_USE = ("is in use by another program, such as a Pinyon Shift that is still "
          "closing or antivirus scanning the file; wait a moment and start the game "
          "again, or add the install folder to the antivirus exclusions")


def _same_tree(left: Path, right: Path) -> bool:
    def files(root: Path) -> dict[str, Path]:
        return {path.relative_to(root).as_posix(): path
                for path in root.rglob("*") if path.is_file()}
    a, b = files(left), files(right)
    if a.keys() != b.keys() or any(a[k].stat().st_size != b[k].stat().st_size for k in a):
        return False
    return all(hashlib.sha256(a[k].read_bytes()).digest()
               == hashlib.sha256(b[k].read_bytes()).digest() for k in a)


def remove_written_directory(target: Path) -> None:
    """Delete a generated directory. A read-only file is made writable; a file
    still open in the game or held by a scanner is retried for a few seconds,
    then reported by name (#616)."""
    def writable(function, path, _):
        os.chmod(path, 0o666)
        function(path)

    handler = {"onexc": writable} if sys.version_info >= (3, 12) else {"onerror": writable}
    for attempt in range(20):
        try:
            shutil.rmtree(target, **handler)
            return
        except PermissionError as error:
            if attempt == 19:
                name = error.filename or str(target)
                raise PermissionError(error.errno, f"{name} {IN_USE}") from error
            time.sleep(0.25)


def _replace_file(source: Path, target: Path) -> None:
    for attempt in range(20):
        try:
            os.replace(source, target)
            return
        except PermissionError as error:
            if attempt == 19:
                raise PermissionError(error.errno, f"{target} {IN_USE}") from error
            time.sleep(0.25)


def replace_written_directory(staging: Path, target: Path) -> bool:
    """Put a freshly built directory in place of target. When nothing changed
    the old copy is kept, so a relaunch never has to delete files the game
    or a scanner may still hold. Returns whether target changed."""
    if target.is_dir() and _same_tree(staging, target):
        remove_written_directory(staging)
        return False
    if target.exists():
        remove_written_directory(target)
    rename_written_directory(staging, target)
    return True


def install_builtin_mods(state: Path, source: Path = BUILTIN) -> list[str]:
    """Copy the project's own optional mods (such as the immersive camera)
    into <state>/mods, replacing an older copy, so the player can switch them
    on in the MODS settings. They are not enabled here (see
    enable_builtin_mods)."""
    installed = []
    if not source.is_dir():
        return installed
    for mod in sorted(p for p in source.iterdir() if p.is_dir()):
        target = state / "mods" / mod.name
        if target.exists() and not (target / BUILTIN_MARKER).is_file():
            continue
        if target.exists() and _tree(target) == _tree(mod):
            continue
        staging = target.with_name(target.name + ".installing")
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(mod, staging)
        (staging / BUILTIN_MARKER).write_text("Installed by tools/build-mod-patches.py; "
                                              "replaced when the game updates.\n",
                                              encoding="utf-8", newline="\n")
        if target.exists():
            remove_written_directory(target)
        rename_written_directory(staging, target)
        installed.append(mod.name)
    return installed


def _manifest(state: Path, mod: str) -> str:
    manifest = state / "mods" / mod / "mod.toml"
    return manifest.read_text(encoding="utf-8") if manifest.is_file() else ""


def enable_builtin_mods(state: Path) -> list[str]:
    """Enable each installed built-in mod whose mod.toml says
    `always_enabled = true` (the immersive camera, whose strength is a
    setting since #443). A player who had it switched off gets its
    `off_settings` ("key = value" lines, written only where the settings
    file has no such key), so the game looks as before. Returns the mods
    enabled here."""
    config = state / "config" / "pinyon_shift.toml"
    mods = enabled_mods(config)
    added = []
    for marker in sorted((state / "mods").glob(f"*/{BUILTIN_MARKER}")):
        mod = marker.parent.name
        text = _manifest(state, mod)
        if mod in mods or not re.search(r"^always_enabled[ \t]*=[ \t]*true[ \t]*(#.*)?$", text,
                                        re.MULTILINE):
            continue
        settings = config.read_text(encoding="utf-8") if config.exists() else ""
        match = re.search(r"^off_settings[ \t]*=[ \t]*\[([^\]]*)\]", text, re.MULTILINE)
        for line in re.findall(r'"([A-Za-z0-9_]+[ \t]*=[^"]*)"', match.group(1) if match else ""):
            key = line.split("=", 1)[0].strip()
            if not re.search(rf"^{key}[ \t]*=", settings, re.MULTILINE):
                settings = settings.rstrip("\n") + ("\n" if settings else "") + line + "\n"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(settings, encoding="utf-8", newline="\n")
        mods.append(mod)
        added.append(mod)
    if added:
        set_enabled_mods(config, mods)
    return added


def shares_save(state: Path, mod: str) -> bool:
    """mod.toml declares `shares_save = true` (it never changes saved data)."""
    manifest = state / "mods" / mod / "mod.toml"
    text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    return re.search(r"^shares_save[ \t]*=[ \t]*true[ \t]*(#.*)?$", text, re.MULTILINE) is not None


def _mod_options():
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mod_options  # noqa: PLC0415
    return mod_options


def option_values(state: Path, mod: str) -> dict[str, str] | None:
    """The values of a mod's options (tools/mod_options.py), or None for a mod
    without [[option]] tables, whose scripts run exactly as written. A mod.toml
    this cannot read counts as having none, as before options existed."""
    import tomllib  # noqa: PLC0415
    try:
        manifest = tomllib.loads((state / "mods" / mod / "mod.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    tables = manifest.get("option")
    if not isinstance(tables, list) or not tables or not all(isinstance(t, dict) for t in tables):
        return None
    options = _mod_options()
    return options.chosen(state, mod, options.declared(manifest))


def database_scripts(state: Path, mods: list[str]) -> list[tuple[str, Path]]:
    """(mod, script) for every enabled mod's db/*.sql, in load order."""
    scripts = []
    for mod in mods:
        if mod in GENERATED_MODS:
            continue
        for script in sorted((state / "mods" / mod / "db").glob("*.sql")):
            scripts.append((mod, script))
    return scripts


def apply_scripts(state: Path, database: Path, scripts: list[tuple[str, Path]]) -> list[dict]:
    """Run the scripts on a database file in place; returns what was applied.
    A mod with options has its {{key}} placeholders filled with the state's
    chosen values first."""
    values = {mod: option_values(state, mod) for mod in dict.fromkeys(m for m, _ in scripts)}
    applied = []
    connection = sqlite3.connect(database)
    try:
        for mod, script in scripts:
            text = script.read_text(encoding="utf-8")
            entry = {"mod": mod, "script": script.name, "sha256": sha256(script)}
            if values[mod] is not None:
                # Only a mod with options: its {{key}} placeholders take the chosen values.
                text = _mod_options().fill(text, values[mod], f"{mod}/db/{script.name}")
                entry["options"] = values[mod]
            connection.executescript(text)
            applied.append(entry)
        connection.commit()
    finally:
        connection.close()
    return applied


def build(state: Path, game_root: Path) -> dict:
    config = state / "config" / "pinyon_shift.toml"
    mods = [m for m in enabled_mods(config) if m != GENERATED]
    scripts = database_scripts(state, mods)
    target = state / "mods" / GENERATED
    if not scripts:
        if target.exists():
            remove_written_directory(target)
        set_enabled_mods(config, mods)
        return {"patched": False, "mods": mods}
    base = effective_game_file(state, mods, game_root, "media/db/gamedb.slt")
    database = target / "game" / "media" / "db" / "gamedb.slt"
    staging = database.with_suffix(".building")
    database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base, staging)
    applied = apply_scripts(state, staging, scripts)
    if database.is_file() and sha256(database) == sha256(staging):
        staging.unlink()
    else:
        _replace_file(staging, database)
    (target / "mod.toml").write_text(
        f'# Generated by tools/build-mod-patches.py; rebuilt when mods change.\n'
        f'name = "{GENERATED}"\nversion = "1"\nabi = 1\n', encoding="utf-8", newline="\n")
    manifest = {"base": base.as_posix(), "base_sha256": sha256(base),
                "patched_sha256": sha256(database),
                "scripts": applied}
    (target / "patches.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    set_enabled_mods(config, [GENERATED] + mods)
    return {"patched": True, **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("state_root", type=Path)
    parser.add_argument("--game-root", type=Path, default=ROOT / ".local" / "game" / "base")
    args = parser.parse_args()
    (args.state_root / "mods").mkdir(parents=True, exist_ok=True)
    installed = install_builtin_mods(args.state_root.resolve())
    enabled = enable_builtin_mods(args.state_root.resolve())
    result = build(args.state_root.resolve(), args.game_root.resolve())
    result["builtin_installed"] = installed
    result["builtin_enabled"] = enabled
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
