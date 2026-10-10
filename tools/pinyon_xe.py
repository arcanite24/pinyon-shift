#!/usr/bin/env python3
"""Install the Forza Horizon XE mod from the player's own downloads (XE-1).

The XE mod (by Teancum, https://www.moddb.com/mods/forza-horizon-xe-mod)
adds about 60 FH2 cars, the Fast 7 cars, traffic cars and engine and
drivetrain swaps. On a console it is extracted over the base game. Its
default.xex differs from the disc's only in two names in the title's file
hash table (db\\gamedb.slt and zipmanifest.xml), so that the replaced files
pass the dirty-disc check; Pinyon Shift accepts the hashes of every file a
mod replaces, so the base build runs XE unchanged and its executables are
not used.

  pinyon.py xe install <XE 1.0 archive> [<1.01 hotfix archive>]
                       [--state-root DIR] [--game-root DIR] [--json]
  pinyon.py xe install --find [--dir DIR] [--wait SECONDS] [--open-pages] ...
  pinyon.py xe find [--dir DIR] [--json]
  pinyon.py xe status|enable|disable|remove [--state-root DIR] [--json]

`install` checks each archive's size and MD5 against ModDB's, extracts them
(the hotfix over 1.0) with 7-Zip or libarchive's bsdtar, keeps only the
files that differ from the player's game, and writes the asset mod
<state>/mods/xe. Its mod.toml targets the base executable, hides the Horizon
Rally expansion (XE replaces the database Rally extends) and plays its own
new save, <state>/user-xe, as XE's readme asks. The player's own save, DLC
and game files are never changed. Nothing from the mod is distributed.

`--find` takes the archives from the player's Downloads folder (or --dir)
instead of a list, matched by name and size. `--open-pages` opens both
ModDB download pages in the player's browser first and `--wait` keeps
looking until the downloads finish. Pinyon Shift never fetches XE itself:
ModDB's robots.txt disallows automated clients on its /downloads/start/ and
/downloads/mirror/ pages (checked 2026-10-10), so the player downloads it
from ModDB in their own browser (#426).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = "xe"
BASE_EXECUTABLE = "DB40DF605ADE49A6"
RALLY = "6F6992766050D818245ADD408031E280FB5F4E634D"

# ModDB's published sizes and MD5s.
ARCHIVES = {
    "1.0": {"file": "Forza_Horizon_1_XE_Mod_v1.0.7z", "size": 2043853238,
            "md5": "935a8562ebcc29cb3c2277c978bd687b",
            "page": "https://www.moddb.com/mods/forza-horizon-xe-mod/downloads/"
                    "forza-horizon-1-xe-mod-v10"},
    "1.01": {"file": "FH1XE_v1.01_hotfix.7z", "size": 1642312261,
             "md5": "a5cbfd944c9bc748c520a35c221a56f3",
             "page": "https://www.moddb.com/mods/forza-horizon-xe-mod/downloads/"
                     "fh1-xe-v101-hotfix"},
}
# Extracted files that are not game data, or are the author's leftovers.
SKIPPED_NAMES = {"media/db/gamedb - copy.slt"}
SKIPPED_SUFFIXES = (".backup",)
FREE_SPACE_GB = 7  # both archives unpacked (4 GB) and the installed mod (2.4 GB)


class XeError(RuntimeError):
    pass


def _patches():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_mod_patches", Path(__file__).with_name("build-mod-patches.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def say(message: str, quiet: bool) -> None:
    if not quiet:
        print(message, flush=True)


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 << 20), b""):
            value.update(block)
    return value.hexdigest()


def identify(path: Path) -> str:
    """The XE release an archive is, checked by size and MD5."""
    size = path.stat().st_size
    for version, known in ARCHIVES.items():
        if size == known["size"]:
            if digest(path, "md5") != known["md5"]:
                raise XeError(f"{path.name} has the size of {known['file']} but not its MD5; "
                              "download it again from ModDB")
            return version
    raise XeError(f"{path.name} is not a known XE download: expected "
                  + " or ".join(k["file"] for k in ARCHIVES.values()))


def download_folders() -> list[Path]:
    """Where browsers save downloads: the user's Downloads folder (its
    relocated location on Windows) and the home folder's Downloads."""
    folders = []
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            value, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            folders.append(Path(os.path.expandvars(value)))
        except OSError:
            pass
    if xdg := os.environ.get("XDG_DOWNLOAD_DIR"):
        folders.append(Path(xdg))
    folders.append(Path.home() / "Downloads")
    unique: list[Path] = []
    for folder in folders:
        if folder.is_dir() and all(folder.resolve() != u.resolve() for u in unique):
            unique.append(folder)
    return unique


def find_archives(folders: list[Path]) -> dict[str, Path]:
    """XE downloads in the folders, by version: a file with the archive's size,
    named as ModDB names it (browsers may add " (1)"). Partial downloads are
    smaller and are skipped; install checks the MD5."""
    found: dict[str, Path] = {}
    for folder in folders:
        for version, known in ARCHIVES.items():
            if version in found:
                continue
            stem = known["file"][:-len(".7z")].lower()
            for candidate in sorted(folder.glob("*.7z")):
                if candidate.name.lower().startswith(stem) and candidate.is_file() \
                        and candidate.stat().st_size == known["size"]:
                    found[version] = candidate
                    break
    return found


def wait_for_archives(folders: list[Path], seconds: float, quiet: bool,
                      poll: float = 5.0) -> dict[str, Path]:
    """Look for both downloads until they are complete or the time runs out;
    returns what was found (1.0 alone is enough to install)."""
    deadline = time.monotonic() + seconds
    announced: set[str] = set()
    while True:
        found = find_archives(folders)
        for version in sorted(found.keys() - announced):
            say(f"Found {found[version].name}", quiet)
            announced.add(version)
        if len(found) == len(ARCHIVES) or time.monotonic() >= deadline:
            return found
        time.sleep(poll)


def open_pages(quiet: bool) -> None:
    for known in ARCHIVES.values():
        say(f"Opening {known['page']}", quiet)
        webbrowser.open(known["page"])


def find_extractor() -> list[str]:
    """7-Zip, else libarchive's bsdtar (Windows 10's tar.exe, macOS's tar and
    SteamOS's bsdtar are libarchive and read XE's LZMA2 archives)."""
    for name in ("7zz", "7z", "7za"):
        if found := shutil.which(name):
            return [found, "x", "-y", "-bso0", "-bsp0"]
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432")):
            candidate = Path(base or "") / "7-Zip" / "7z.exe"
            if base and candidate.is_file():
                return [str(candidate), "x", "-y", "-bso0", "-bsp0"]
        system_tar = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
        if system_tar.is_file():
            return [str(system_tar), "-xf"]
    if found := shutil.which("bsdtar"):
        return [found, "-xf"]
    if sys.platform == "darwin" and Path("/usr/bin/tar").is_file():
        return ["/usr/bin/tar", "-xf"]
    raise XeError("no 7-Zip or bsdtar found to extract the archives; install 7-Zip "
                  "(p7zip, 7zip) or libarchive's bsdtar (libarchive-tools)")


def extract(extractor: list[str], archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    if Path(extractor[0]).stem.lower().startswith("7z"):
        command = extractor + [f"-o{destination}", str(archive)]
    else:
        command = extractor + [str(archive), "-C", str(destination)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode:
        raise XeError(f"could not extract {archive.name}: "
                      f"{(completed.stderr or completed.stdout).strip()[-400:]}")


def index_tree(root: Path) -> dict[str, tuple[str, Path]]:
    """Lower-case relative path -> (relative path as spelled, file), with /."""
    files = {}
    for directory, _, names in os.walk(root):
        for name in names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix().replace("\\", "/")
            files[relative.lower()] = (relative, path)
    return files


def disc_spelling(game: Path, relative: str) -> str:
    """The path as the disc spells it, as far as the disc has it, so the mod's
    tree matches the game's on case-sensitive file systems."""
    current, parts = game, []
    pieces = relative.split("/")
    for index, piece in enumerate(pieces):
        match = None
        if current.is_dir():
            match = next((c for c in current.iterdir() if c.name.lower() == piece.lower()), None)
        if match is None:
            parts += pieces[index:]
            break
        parts.append(match.name)
        current = match
    return "/".join(parts)


def state_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    state = (args.state_root or ROOT / ".local" / "preview").resolve()
    game = (getattr(args, "game_root", None) or ROOT / ".local" / "game" / "base").resolve()
    return state, game


def mod_toml(version: str) -> str:
    return (
        "# Installed by tools/pinyon_xe.py from the player's own XE downloads.\n"
        f'name = "{MOD}"\n'
        f'version = "{version}"\n'
        "abi = 1\n"
        "# XE is made for the base game without title updates.\n"
        f'game_version = "{BASE_EXECUTABLE}"\n'
        "# XE replaces the database the Horizon Rally expansion extends.\n"
        f'hide_dlc = ["{RALLY}"]\n'
        "# XE needs a new save; it plays <state>/user-xe.\n"
        f'profile = "{MOD}"\n')


def install(args: argparse.Namespace) -> dict:
    state, game = state_paths(args)
    quiet = args.json
    if not (game / "default.xex").is_file() or not (game / "media" / "db" / "gamedb.slt").is_file():
        raise XeError(f"the game files are not at {game}; finish setup first")
    versions: dict[str, Path] = {}
    archives = list(args.archives)
    if args.find:
        folders = [d.resolve() for d in args.dir] if args.dir else download_folders()
        if args.open_pages:
            open_pages(quiet)
        say("Looking for the XE downloads in " + ", ".join(str(f) for f in folders), quiet)
        found = wait_for_archives(folders, args.wait, quiet)
        if "1.0" not in found:
            raise XeError(f"{ARCHIVES['1.0']['file']} was not found in "
                          + (", ".join(str(f) for f in folders) or "a Downloads folder")
                          + f"; download it from {ARCHIVES['1.0']['page']}")
        archives += [found[v] for v in ARCHIVES if v in found]
    if not archives:
        raise XeError("choose the XE archives, or pass --find to look in Downloads")
    for archive in archives:
        archive = archive.resolve()
        if not archive.is_file():
            raise XeError(f"{archive} does not exist")
        say(f"Checking {archive.name}", quiet)
        version = identify(archive)
        if version in versions:
            raise XeError(f"two copies of XE {version} were given")
        versions[version] = archive
    if "1.0" not in versions:
        raise XeError(f"XE needs its full 1.0 download, {ARCHIVES['1.0']['file']}; "
                      "the 1.01 hotfix applies over it")
    mods = state / "mods"
    target = mods / MOD
    if target.exists() and not args.replace:
        raise XeError(f"XE is already installed at {target}; pass --replace to reinstall")
    mods.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(mods).free / (1 << 30)
    if free_gb < FREE_SPACE_GB:
        raise XeError(f"{FREE_SPACE_GB} GB free is needed under {mods} ({free_gb:.1f} GB free)")
    extractor = find_extractor()
    staging = mods / f".{MOD}-staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        layers = []
        for version in ("1.0", "1.01"):
            if version in versions:
                say(f"Extracting XE {version} (a few minutes)", quiet)
                layer = staging / "archives" / version
                extract(extractor, versions[version], layer)
                layers.append(index_tree(layer))
        merged: dict[str, tuple[str, Path]] = {}
        for layer in layers:
            merged.update(layer)
        say("Comparing with your game files", quiet)
        disc = index_tree(game)
        output = staging / MOD
        files, skipped_same = {}, 0
        for relative, (spelled_in_archive, source) in sorted(merged.items()):
            if not relative.startswith("media/") or relative in SKIPPED_NAMES \
                    or relative.endswith(SKIPPED_SUFFIXES):
                continue  # executables, readmes and leftovers
            base = disc[relative][1] if relative in disc else None
            sha = digest(source, "sha256").upper()
            if base is not None and base.stat().st_size == source.stat().st_size \
                    and digest(base, "sha256").upper() == sha:
                skipped_same += 1
                continue
            spelled = disc_spelling(game, spelled_in_archive)
            if ".." in spelled.split("/"):
                raise XeError(f"unexpected path in the archive: {relative}")
            destination = output / "game" / spelled
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            files[spelled] = {"sha256": sha, "replaces": base is not None}
        for readme in ("readme.txt", "readme 1.1 hotfix.txt"):
            if readme in merged:
                shutil.copy2(merged[readme][1], output / readme.replace(" ", "-"))
        version = "1.01" if "1.01" in versions else "1.0"
        (output / "mod.toml").write_text(mod_toml(version), encoding="utf-8", newline="\n")
        record = {"schema_version": 1, "version": version,
                  "archives": {v: {"file": p.name, "md5": ARCHIVES[v]["md5"],
                                   "size": ARCHIVES[v]["size"]} for v, p in versions.items()},
                  "installed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "replaced": sum(1 for f in files.values() if f["replaces"]),
                  "added": sum(1 for f in files.values() if not f["replaces"]),
                  "unchanged_skipped": skipped_same, "files": files}
        (output / "xe-install.json").write_text(json.dumps(record, indent=1) + "\n",
                                                encoding="utf-8")
        if target.exists():
            shutil.rmtree(target)
        output.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    if not args.no_enable:
        set_enabled(state, True)
    result = {"result": "installed", "version": version, "mod": str(target),
              "enabled": not args.no_enable, "replaced": record["replaced"],
              "added": record["added"], "profile": str(state / f"user-{MOD}")}
    if "1.01" not in versions:
        result["warning"] = ("the 1.01 hotfix is not installed; it fixes engines, models "
                             "and audio: " + ARCHIVES["1.01"]["page"])
    return result


def set_enabled(state: Path, enabled: bool) -> list[str]:
    patches = _patches()
    config = state / "config" / "pinyon_shift.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    mods = [m for m in patches.enabled_mods(config) if m != MOD]
    if enabled:
        mods.append(MOD)  # last: smaller mods made for XE win over it
    patches.set_enabled_mods(config, mods)
    return mods


def status(args: argparse.Namespace) -> dict:
    state, _ = state_paths(args)
    target = state / "mods" / MOD
    record_path = target / "xe-install.json"
    if not record_path.is_file():
        return {"installed": False}
    record = json.loads(record_path.read_text(encoding="utf-8"))
    enabled = MOD in _patches().enabled_mods(state / "config" / "pinyon_shift.toml")
    return {"installed": True, "enabled": enabled, "version": record["version"],
            "replaced": record["replaced"], "added": record["added"], "mod": str(target),
            "profile": str(state / f"user-{MOD}")}


def run(args: argparse.Namespace) -> dict:
    state, _ = state_paths(args)
    if args.xe_command == "install":
        return install(args)
    if args.xe_command == "status":
        return status(args)
    if args.xe_command == "find":
        folders = [d.resolve() for d in args.dir] if args.dir else download_folders()
        found = find_archives(folders)
        return {"folders": [str(f) for f in folders],
                "found": {v: str(p) for v, p in found.items()},
                "missing": [ARCHIVES[v]["file"] for v in ARCHIVES if v not in found],
                "pages": {v: k["page"] for v, k in ARCHIVES.items()}}
    if not (state / "mods" / MOD / "mod.toml").is_file():
        raise XeError("XE is not installed")
    if args.xe_command in ("enable", "disable"):
        set_enabled(state, args.xe_command == "enable")
        return status(args)
    # remove: the mod's files only; its save (user-xe) is kept.
    set_enabled(state, False)
    shutil.rmtree(state / "mods" / MOD)
    return {"installed": False, "profile_kept": str(state / f"user-{MOD}")}


def add_parser(commands) -> None:
    parser = commands.add_parser("xe", help="install and manage the Forza Horizon XE mod")
    sub = parser.add_subparsers(dest="xe_command", required=True)
    installing = sub.add_parser("install", help="install XE from its downloaded archives")
    installing.add_argument("archives", type=Path, nargs="*",
                            help="Forza_Horizon_1_XE_Mod_v1.0.7z and FH1XE_v1.01_hotfix.7z")
    installing.add_argument("--find", action="store_true",
                            help="take the archives from the Downloads folder (or --dir)")
    installing.add_argument("--open-pages", action="store_true",
                            help="with --find: open both ModDB download pages in the browser")
    installing.add_argument("--wait", type=float, default=0,
                            help="with --find: seconds to keep looking for downloads to finish")
    installing.add_argument("--game-root", type=Path)
    installing.add_argument("--replace", action="store_true", help="reinstall over XE")
    installing.add_argument("--no-enable", action="store_true", help="install but leave it off")
    for name, text in (("status", "show whether XE is installed and enabled"),
                       ("enable", "play with XE"), ("disable", "play without XE"),
                       ("remove", "delete XE's files; its save is kept"),
                       ("find", "look for the XE downloads in the Downloads folder")):
        sub.add_parser(name, help=text)
    for action in (installing, sub.choices["find"]):
        action.add_argument("--dir", type=Path, action="append",
                            help="a folder to look in instead of Downloads (repeatable)")
    for action in sub.choices.values():
        action.add_argument("--state-root", type=Path)
        action.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    try:
        result = run(args)
    except (XeError, OSError) as error:
        if args.json:
            print(json.dumps({"result": "error", "error": str(error)}))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result) if args.json else "\n".join(f"{k}: {v}" for k, v in result.items()))
    return 0
