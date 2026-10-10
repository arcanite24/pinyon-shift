#!/usr/bin/env python3
"""Build the database patches of a state's enabled mods (NP-10.2).

A mod may ship SQL scripts in db/*.sql. This tool copies the player's own
media/db/gamedb.slt (a plain SQLite database the title opens loose), applies
every enabled mod's scripts in load order, and writes the result as the
asset-only mod <state>/mods/zz-db-patches, listed first in enabled_mods so
its database wins over the game's. Nothing from the disc is distributed: the
patched copy is built on the player's machine from their files. With no
scripts enabled the generated mod is removed. Run it after changing mods
(the launcher runs it before each start).

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


def install_builtin_mods(state: Path, source: Path = BUILTIN) -> list[str]:
    """Copy the project's own optional mods (such as the immersive camera)
    into <state>/mods, replacing an older copy, so the player can switch them
    on in the MODS or CAMERA settings. They are not enabled here."""
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
            shutil.rmtree(target)
        staging.rename(target)
        installed.append(mod.name)
    return installed


def shares_save(state: Path, mod: str) -> bool:
    """mod.toml declares `shares_save = true` (it never changes saved data)."""
    manifest = state / "mods" / mod / "mod.toml"
    text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    return re.search(r"^shares_save[ \t]*=[ \t]*true[ \t]*(#.*)?$", text, re.MULTILINE) is not None


def build(state: Path, game_root: Path) -> dict:
    config = state / "config" / "pinyon_shift.toml"
    mods = [m for m in enabled_mods(config) if m != GENERATED]
    scripts = []
    for mod in mods:
        for script in sorted((state / "mods" / mod / "db").glob("*.sql")):
            scripts.append((mod, script))
    target = state / "mods" / GENERATED
    if not scripts:
        if target.exists():
            shutil.rmtree(target)
        set_enabled_mods(config, mods)
        return {"patched": False, "mods": mods}
    base = effective_game_file(state, mods, game_root, "media/db/gamedb.slt")
    database = target / "game" / "media" / "db" / "gamedb.slt"
    staging = database.with_suffix(".building")
    database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base, staging)
    applied = []
    connection = sqlite3.connect(staging)
    try:
        for mod, script in scripts:
            connection.executescript(script.read_text(encoding="utf-8"))
            applied.append({"mod": mod, "script": script.name, "sha256": sha256(script)})
        connection.commit()
    finally:
        connection.close()
    os.replace(staging, database)
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
    result = build(args.state_root.resolve(), args.game_root.resolve())
    result["builtin_installed"] = installed
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
