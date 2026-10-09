#!/usr/bin/env python3
"""Pinyon Shift in Steam and the desktop menu on Linux (LX-5.10).

  pinyon.py shortcuts add [--no-steam] [--no-desktop] [--state-root DIR]
  pinyon.py shortcuts remove

`add` writes a start script beside this checkout, a non-Steam game entry with
the project's artwork in every Steam user's shortcuts.vdf, and a desktop
entry. Steam keeps shortcuts.vdf in memory and writes it back when it exits,
so a running Steam is shut down first and started again afterwards; on a
Steam Deck, switching back to Game Mode starts it too. The entry starts the
game through `pinyon.py launch`, so mods and the state folder work as they do
from the launchers, and Steam Input gives the game a gamepad.
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Pinyon Shift"
ARTWORK = ROOT / "config" / "steam"
SCRIPT = ROOT / ".local" / "pinyon-shift.sh"


# --- Binary VDF (shortcuts.vdf) ------------------------------------------------

MAP, STRING, INT32, END = 0x00, 0x01, 0x02, 0x08


def _cstring(data: bytes, position: int) -> tuple[str, int]:
    end = data.index(b"\0", position)
    return data[position:end].decode("utf-8", errors="surrogateescape"), end + 1


def parse_vdf(data: bytes, position: int = 0) -> tuple[dict, int]:
    result: dict = {}
    while position < len(data):
        kind = data[position]
        position += 1
        if kind == END:
            return result, position
        key, position = _cstring(data, position)
        if kind == MAP:
            result[key], position = parse_vdf(data, position)
        elif kind == STRING:
            result[key], position = _cstring(data, position)
        elif kind == INT32:
            result[key] = struct.unpack_from("<i", data, position)[0]
            position += 4
        else:
            raise ValueError(f"unsupported VDF field type {kind}")
    return result, position


def dump_vdf(value: dict) -> bytes:
    out = bytearray()
    for key, item in value.items():
        name = key.encode("utf-8", errors="surrogateescape") + b"\0"
        if isinstance(item, dict):
            out += bytes([MAP]) + name + dump_vdf(item)
        elif isinstance(item, int):
            out += bytes([INT32]) + name + struct.pack("<i", item)
        else:
            out += bytes([STRING]) + name + str(item).encode(
                "utf-8", errors="surrogateescape") + b"\0"
    return bytes(out) + bytes([END])


def shortcut_app_id(exe: str, name: str) -> int:
    """Steam's id for a non-Steam game, which also names its artwork."""
    return zlib.crc32((exe + name).encode("utf-8")) | 0x80000000


# --- Steam ---------------------------------------------------------------------

def steam_roots() -> list[Path]:
    home = Path.home()
    candidates = [home / ".local/share/Steam", home / ".steam/steam",
                  home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    roots = []
    for candidate in candidates:
        if (candidate / "userdata").is_dir() and candidate.resolve() not in [
                root.resolve() for root in roots]:
            roots.append(candidate)
    return roots


def steam_users(root: Path) -> list[Path]:
    return [path for path in (root / "userdata").iterdir()
            if path.is_dir() and path.name.isdigit() and path.name != "0"]


def steam_running() -> bool:
    return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0


def stop_steam() -> bool:
    """Asks Steam to exit; returns whether it was running."""
    if not steam_running():
        return False
    print("Closing Steam so it does not overwrite the new shortcut...")
    subprocess.run(["steam", "-shutdown"], capture_output=True)
    deadline = time.monotonic() + 60
    while steam_running():
        if time.monotonic() > deadline:
            raise RuntimeError("Steam did not close; quit it and run this again")
        time.sleep(1)
    return True


def start_steam() -> None:
    if shutil.which("steam"):
        subprocess.Popen(["steam"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


def write_script(state_root: Path | None) -> Path:
    """The start script Steam and the desktop entry run."""
    SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    state = f' --state-root "{state_root}"' if state_root else ""
    SCRIPT.write_bytes((
        "#!/bin/sh\n"
        "# Written by tools/pinyon.py shortcuts add.\n"
        f'cd "{ROOT}" || exit 1\n'
        f'exec "{sys.executable}" tools/pinyon.py launch{state} -- "$@"\n').encode())
    SCRIPT.chmod(0o755)
    return SCRIPT


def add_to_steam(script: Path) -> list[str]:
    roots = steam_roots()
    if not roots:
        return []
    exe = f'"{script}"'
    app_id = shortcut_app_id(exe, NAME)
    signed = struct.unpack("<i", struct.pack("<I", app_id))[0]
    restart = stop_steam()
    added = []
    try:
        for root in roots:
            for user in steam_users(root):
                config = user / "config"
                config.mkdir(parents=True, exist_ok=True)
                path = config / "shortcuts.vdf"
                shortcuts: dict = {}
                if path.is_file() and path.stat().st_size:
                    shortcuts = parse_vdf(path.read_bytes())[0].get("shortcuts", {})
                    backup = path.with_suffix(".vdf.pinyon-backup")
                    if not backup.exists():
                        shutil.copyfile(path, backup)
                entries = [entry for entry in shortcuts.values()
                           if entry.get("AppName", entry.get("appname")) != NAME]
                entries.append({
                    "appid": signed,
                    "AppName": NAME,
                    "Exe": exe,
                    "StartDir": f'"{ROOT}"',
                    "icon": str(ARTWORK / "icon.png"),
                    "ShortcutPath": "",
                    "LaunchOptions": "",
                    "IsHidden": 0,
                    "AllowDesktopConfig": 1,
                    "AllowOverlay": 1,
                    "OpenVR": 0,
                    "Devkit": 0,
                    "DevkitGameID": "",
                    "DevkitOverrideAppID": 0,
                    "LastPlayTime": 0,
                    "FlatpakAppID": "",
                    "tags": {},
                })
                data = dump_vdf({"shortcuts": {str(index): entry
                                               for index, entry in enumerate(entries)}})
                temporary = path.with_suffix(".vdf.tmp")
                temporary.write_bytes(data)
                temporary.replace(path)
                grid = config / "grid"
                grid.mkdir(exist_ok=True)
                for source, name in (("capsule.png", f"{app_id}p.png"),
                                     ("wide.png", f"{app_id}.png"),
                                     ("hero.png", f"{app_id}_hero.png"),
                                     ("logo.png", f"{app_id}_logo.png"),
                                     ("icon.png", f"{app_id}_icon.png")):
                    shutil.copyfile(ARTWORK / source, grid / name)
                added.append(user.name)
    finally:
        if restart:
            start_steam()
    return added


def remove_from_steam() -> int:
    removed = 0
    restart = stop_steam() if steam_roots() else False
    try:
        for root in steam_roots():
            for user in steam_users(root):
                path = user / "config" / "shortcuts.vdf"
                if not path.is_file() or not path.stat().st_size:
                    continue
                shortcuts = parse_vdf(path.read_bytes())[0].get("shortcuts", {})
                entries = [entry for entry in shortcuts.values()
                           if entry.get("AppName", entry.get("appname")) != NAME]
                if len(entries) == len(shortcuts):
                    continue
                path.write_bytes(dump_vdf({"shortcuts": {str(index): entry
                                                         for index, entry in enumerate(entries)}}))
                removed += 1
    finally:
        if restart:
            start_steam()
    return removed


# --- Desktop entry -------------------------------------------------------------

def desktop_entry_path() -> Path:
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / "applications" / "pinyon-shift.desktop"


def add_desktop_entry(script: Path) -> Path:
    path = desktop_entry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NAME}\n"
        "Comment=Forza Horizon, rebuilt from your own disc\n"
        f'Exec="{script}"\n'
        f"Icon={ARTWORK / 'icon.png'}\n"
        "Categories=Game;\n"
        "Terminal=false\n", encoding="utf-8")
    return path


# --- Commands ------------------------------------------------------------------

def add(args: argparse.Namespace) -> int:
    if sys.platform != "linux":
        print("error: shortcuts are made on Linux; the Windows and macOS launchers make "
              "their own", file=sys.stderr)
        return 1
    script = write_script(args.state_root.resolve() if args.state_root else None)
    print(f"start script: {script}")
    if not args.no_desktop:
        print(f"desktop entry: {add_desktop_entry(script)}")
    if not args.no_steam:
        try:
            users = add_to_steam(script)
        except RuntimeError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"added to Steam for {len(users)} user(s)" if users
              else "Steam is not installed for this account; skipped")
    return 0


def remove(args: argparse.Namespace) -> int:
    print(f"removed from Steam for {remove_from_steam()} user(s)")
    entry = desktop_entry_path()
    if entry.is_file():
        entry.unlink()
    return 0


def add_parser(commands) -> None:
    parser = commands.add_parser("shortcuts", help="add the game to Steam and the desktop menu")
    sub = parser.add_subparsers(dest="shortcuts_command", required=True)
    adding = sub.add_parser("add", help="add Pinyon Shift to Steam and the menu")
    adding.add_argument("--no-steam", action="store_true")
    adding.add_argument("--no-desktop", action="store_true")
    adding.add_argument("--state-root", type=Path)
    adding.set_defaults(shortcuts_handler=add)
    removing = sub.add_parser("remove", help="remove the entries again")
    removing.set_defaults(shortcuts_handler=remove)


def main(args: argparse.Namespace) -> int:
    return args.shortcuts_handler(args)
