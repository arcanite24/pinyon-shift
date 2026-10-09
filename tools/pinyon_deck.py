#!/usr/bin/env python3
"""Pinyon Shift on a Steam Deck, driven from the PC (LX-2.1).

The Linux build holds the game translated from the player's own disc, so,
like pinyon_shift.exe, it is built on their machine and copied only to their
own Deck. The developer loop reaches the Deck over SSH, by default with the
key Valve's SteamOS Devkit Client pairs. Everything goes under one folder in
the Deck's home (~/pinyon-shift-dev by default); the Deck's own Steam library
and saves are never touched, and routes run from private state roots under
its qual/ folder.

  pinyon.py deck doctor                  check the connection and the Deck
  pinyon.py deck install                 copy the Linux build (changed files)
  pinyon.py deck push-data               copy the extracted game (changed files)
  pinyon.py deck run [--null-gpu] [--route FILE [--seed DIR]] [--wait] [-- args]
  pinyon.py deck pull-logs [--state NAME] copy a state's logs and route output
  pinyon.py deck stop                    stop the game on the Deck
  pinyon.py deck shortcut [--seed DIR]   add the game to Steam (LX-2.3)

`run` starts the game inside a headless gamescope by default, so scripted
routes do not take over the screen; --display runs it in the Deck's own
session (Game Mode's Xwayland) instead. A game started over SSH gets no game
power profile from Steam, which may hold the GPU at its lowest clock; `deck
shortcut` registers the build as a native (no compatibility tool) devkit game,
so it starts from Game Mode like any other and keeps its save under play/.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"
WORK = ROOT / ".local" / "deck"
REMOTE = "pinyon-shift-dev"
# What a Linux build directory needs at run time: the game, its modules, the
# GPU plugin and the build's provenance.
BUILD_FILES = ("pinyon_shift", "*.so", "pinyon_shift_build.json", "gamecontrollerdb.txt")


class DeckError(RuntimeError):
    pass


def devkit_key() -> Path | None:
    """The key Valve's SteamOS Devkit Client made when it paired the Deck."""
    candidates = []
    if WINDOWS:
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "steamos-devkit" / "steamos-devkit" / "devkit_rsa")
    else:
        data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        candidates.append(Path(data) / "steamos-devkit" / "devkit_rsa")
    return next((path for path in candidates if path.is_file()), None)


class Deck:
    def __init__(self, args: argparse.Namespace):
        self.host = args.host or os.environ.get("PINYON_DECK_HOST", "steamdeck")
        self.user = args.user
        key = args.key or devkit_key()
        self.ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
        if key:
            self.ssh += ["-i", str(key), "-o", "IdentitiesOnly=yes"]
        self.target = f"{self.user}@{self.host}"
        self.root = args.remote_root or REMOTE

    def run(self, command: str, check: bool = True, **kwargs) -> subprocess.CompletedProcess:
        """Runs a shell command on the Deck from its home directory."""
        completed = subprocess.run(self.ssh + [self.target, command], **kwargs)
        if check and completed.returncode:
            raise DeckError(f"on the Deck: {command} (exit {completed.returncode})")
        return completed

    def output(self, command: str, check: bool = True) -> str:
        return self.run(command, check=check, capture_output=True, text=True).stdout

    def send(self, files: list[tuple[Path, str]], destination: str) -> None:
        """Streams files to destination/<name> as a tar archive over SSH."""
        process = subprocess.Popen(
            self.ssh + [self.target, f"mkdir -p {shlex.quote(destination)} && "
                        f"tar -x -C {shlex.quote(destination)}"],
            stdin=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdin, mode="w|") as archive:
            for source, name in files:
                info = archive.gettarinfo(str(source), arcname=name)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                if os.access(source, os.X_OK) and not WINDOWS:
                    info.mode = 0o755
                elif name.endswith(".so") or "/" not in name and name == "pinyon_shift":
                    info.mode = 0o755
                with source.open("rb") as stream:
                    archive.addfile(info, stream)
        process.stdin.close()
        if process.wait():
            raise DeckError(f"copying to {destination} failed")

    def receive(self, source: str, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(
            self.ssh + [self.target, f"tar -c -C {shlex.quote(source)} ."],
            stdout=subprocess.PIPE)
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            archive.extractall(destination, filter="data")
        process.wait()


def remote_listing(deck: Deck, folder: str, hashes: bool) -> dict[str, tuple[int, str]]:
    """Path -> (size, sha256 or '') of every file under folder on the Deck."""
    if hashes:
        script = (f"cd {shlex.quote(folder)} 2>/dev/null && find . -type f -printf '%P\\t%s\\t' "
                  f"-exec sh -c 'sha256sum \"$1\" | cut -d\" \" -f1' _ {{}} \\;")
    else:
        script = f"cd {shlex.quote(folder)} 2>/dev/null && find . -type f -printf '%P\\t%s\\t\\n'"
    listing = {}
    for line in deck.output(script, check=False).splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            listing[parts[0]] = (int(parts[1]), parts[2])
    return listing


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sync(deck: Deck, source: Path, files: list[Path], destination: str, hashes: bool) -> int:
    """Sends the files that are missing or differ; returns how many were sent."""
    remote = remote_listing(deck, destination, hashes)
    changed = []
    for path in files:
        name = path.relative_to(source).as_posix()
        size = path.stat().st_size
        have = remote.get(name)
        if have and have[0] == size and (not hashes or have[1] == sha256(path)):
            continue
        changed.append((path, name))
    total = sum(path.stat().st_size for path, _ in changed)
    print(f"{len(changed)} of {len(files)} files to send ({total / 1e6:.1f} MB)")
    # Batches keep one tar stream from holding the whole game in flight.
    batch: list[tuple[Path, str]] = []
    batch_size = 0
    for item in changed:
        batch.append(item)
        batch_size += item[0].stat().st_size
        if batch_size > 512 << 20:
            deck.send(batch, destination)
            batch, batch_size = [], 0
    if batch:
        deck.send(batch, destination)
    return len(changed)


def build_directory(args: argparse.Namespace) -> Path:
    if args.build_directory:
        return args.build_directory.resolve()
    return ROOT / "out" / "build" / f"linux-amd64-{args.configuration.lower()}"


def doctor(args: argparse.Namespace) -> int:
    deck = Deck(args)
    print(f"key: {devkit_key() or 'none (ssh defaults)'}")
    print(deck.output("uname -sr; . /etc/os-release; echo \"$PRETTY_NAME $VERSION_ID\"; "
                      "cat /sys/devices/virtual/dmi/id/product_name; nproc; "
                      "free -g | awk '/Mem/{print $2\" GiB\"}'; df -h ~ | tail -1; "
                      "command -v gamescope; pgrep -a gamescope | head -1; "
                      f"ls {deck.root} 2>/dev/null; true"))
    return 0


def install(args: argparse.Namespace) -> int:
    build = build_directory(args)
    if not (build / "pinyon_shift").is_file():
        raise DeckError(f"no Linux build at {build}")
    files = sorted({path for pattern in BUILD_FILES for path in build.glob(pattern)
                    if path.is_file()})
    deck = Deck(args)
    sync(deck, build, files, f"{deck.root}/build", hashes=True)
    deck.run(f"chmod +x {deck.root}/build/pinyon_shift")
    return 0


def push_data(args: argparse.Namespace) -> int:
    game = (args.game_root or ROOT / ".local" / "game" / "base").resolve()
    if not (game / "default.xex").is_file():
        raise DeckError(f"no extracted game at {game}")
    files = sorted(path for path in game.rglob("*") if path.is_file())
    deck = Deck(args)
    sync(deck, game, files, f"{deck.root}/game/base", hashes=False)
    return 0


def run_game(args: argparse.Namespace) -> int:
    deck = Deck(args)
    state = f"{deck.root}/qual/{args.state}"
    game_arguments = list(args.game_arguments)
    if args.null_gpu:
        game_arguments.append("--gpu_backend=null")
    if not args.display and not any("audio_mute" in argument for argument in game_arguments):
        # Nobody sees a headless run; nobody should hear it either.
        game_arguments.append("--audio_mute=true")
    if args.seed:
        # As on Android (AP-8.1): a private state per run from a pinned seed;
        # only the logs, crash reports and route output carry over.
        seed = args.seed.resolve()
        if not (seed / "user").is_dir():
            raise DeckError(f"{seed} is not a render seed (no user folder)")
        deck.run(f"mkdir -p {state} && cd {state} && find . -mindepth 1 -maxdepth 1 "
                 "! -name logs ! -name crashes ! -name reports ! -name render-test-output "
                 "-exec rm -rf {} +")
        files = sorted(path for folder in ("user", "config") if (seed / folder).is_dir()
                       for path in (seed / folder).rglob("*") if path.is_file())
        deck.send([(path, path.relative_to(seed).as_posix()) for path in files], state)
    environment = {
        "PINYON_SHIFT_STATE_ROOT": f"$HOME/{state}",
        "PINYON_SHIFT_GAME_ROOT": f"$HOME/{deck.root}/game/base",
    }
    if args.route:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output = f"{state}/render-test-output/{args.route.stem}-{stamp}"
        deck.send([(args.route.resolve(), args.route.name)], f"{state}/render-tests")
        environment["PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT"] = (
            f"$HOME/{state}/render-tests/{args.route.name}")
        environment["PINYON_SHIFT_FH1_RENDER_TEST_OUTPUT"] = f"$HOME/{output}"
        game_arguments.append("--pinyon_shift_skip_opening_movies=true")
        if not any("pinyon_shift_repair_car_cards" in argument for argument in game_arguments):
            game_arguments.append("--pinyon_shift_repair_car_cards=false")
        print(f"route output: {output}")
    exports = " ".join(f'{key}="{value}"' for key, value in environment.items())
    game = f"./pinyon_shift {' '.join(shlex.quote(argument) for argument in game_arguments)}"
    if args.display:
        # Game Mode's gamescope serves Xwayland on :0 for games.
        launcher = f"DISPLAY={args.display} {game}"
    else:
        launcher = (f"gamescope --backend headless -W {args.width} -H {args.height} "
                    f"-r {args.refresh} -- {game}")
    console = f"$HOME/{state}/logs/deck-console.log"
    command = (f"mkdir -p {state}/logs && cd {deck.root}/build && export {exports} && "
               f"nohup {launcher} > {console} 2>&1 < /dev/null & echo $!")
    pid = deck.output(command).strip()
    print(f"started on the Deck (pid {pid})")
    if not args.wait:
        return 0
    deadline = time.monotonic() + args.timeout
    while deck.run(f"kill -0 {pid} 2>/dev/null", check=False).returncode == 0:
        if time.monotonic() > deadline:
            stop(args)
            raise DeckError(f"timed out after {args.timeout} seconds")
        time.sleep(3)
    if not args.route:
        return 0
    result = route_result(deck, state)
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "pass" else 1


def route_result(deck: Deck, state: str) -> dict:
    """The newest session's events, judged as tools/run-fh1-render-test.py
    judges a Windows run's: completed once, no failure event."""
    sessions = [name for name in deck.output(f"ls -t {state}/logs/", check=False).split()
                if name.endswith(".jsonl")]
    if not sessions:
        return {"result": "fail", "reason": "no session log on the Deck"}
    destination = WORK / "logs" / "routes"
    destination.mkdir(parents=True, exist_ok=True)
    stem = sessions[0][: -len(".jsonl")]
    for name in (sessions[0], stem + ".perf.csv", "deck-console.log", "runtime.log"):
        data = deck.run(f"cat {state}/logs/{name}", check=False, capture_output=True).stdout
        if data:
            (destination / (name if name.startswith(stem) else f"{stem}.{name}")).write_bytes(data)
    events = []
    for line in (destination / sessions[0]).read_text(encoding="utf-8",
                                                     errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    failures = [event for event in events if str(event.get("event", "")).endswith(".failure")]
    completed = [event for event in events if event.get("event") == "fh1.render_test.complete"]
    captures = [event for event in events if event.get("event") == "fh1.render_test.capture"]
    result = {
        "result": "pass" if completed and not failures else "fail",
        "session": sessions[0],
        "captures": [{"name": event.get("name"), "frame": event.get("frame")}
                     for event in captures],
        "failures": failures[:3],
        "events": len(events),
        "log": str(destination / sessions[0]),
    }
    perf = destination / (stem + ".perf.csv")
    if perf.is_file():
        summary = subprocess.run([sys.executable, str(ROOT / "tools" / "summarize-performance.py"),
                                  str(perf), "--format", "json"], capture_output=True, text=True)
        try:
            performance = json.loads(summary.stdout)
            result["simulation_time"] = performance.get("presentation", {}).get("simulation_time")
            result["frame_time_us"] = performance["frames"]["frame_time_us"]
        except (json.JSONDecodeError, KeyError):
            pass
    return result


def stop(args: argparse.Namespace) -> int:
    Deck(args).run("pkill -x pinyon_shift; true", check=False)
    return 0


def pull_logs(args: argparse.Namespace) -> int:
    deck = Deck(args)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = (args.output or WORK / "logs" / f"{args.state}-{stamp}").resolve()
    for folder in ("logs", "crashes", "reports", "render-test-output"):
        remote = f"{deck.root}/qual/{args.state}/{folder}"
        if deck.run(f"test -d {remote}", check=False).returncode == 0:
            deck.receive(remote, destination / folder)
    print(destination)
    return 0


SHORTCUT_GAMEID = "PinyonShift"
SHORTCUT_LAUNCHER = """#!/bin/sh
# Written by tools/pinyon.py deck shortcut: Steam starts this from Game Mode.
root="$HOME/{root}"
export PINYON_SHIFT_STATE_ROOT="$root/play"
export PINYON_SHIFT_GAME_ROOT="$root/game/base"
mkdir -p "$PINYON_SHIFT_STATE_ROOT/logs"
cd "$root/build" || exit 1
exec ./pinyon_shift "$@" > "$PINYON_SHIFT_STATE_ROOT/logs/steam-console.log" 2>&1
"""


def shortcut(args: argparse.Namespace) -> int:
    deck = Deck(args)
    if deck.run(f"test -x {deck.root}/build/pinyon_shift && "
                f"test -f {deck.root}/game/base/default.xex", check=False).returncode:
        raise DeckError("install the build and push the game data first")
    play = f"{deck.root}/play"
    if args.seed and deck.run(f"test -d {play}/user", check=False).returncode:
        # Only into an empty play state: its save is the player's from then on.
        seed = args.seed.resolve()
        if not (seed / "user").is_dir():
            raise DeckError(f"{seed} is not a render seed (no user folder)")
        files = sorted(path for folder in ("user", "config") if (seed / folder).is_dir()
                       for path in (seed / folder).rglob("*") if path.is_file())
        deck.send([(path, path.relative_to(seed).as_posix()) for path in files], play)
        print(f"seeded {play} from {seed.name}")
    # The devkit tools register ~/devkit-game/<gameid> and run argv from it.
    folder = f"devkit-game/{SHORTCUT_GAMEID}"
    deck.run(f"mkdir -p {folder} && cat > {folder}/pinyon-shift.sh && "
             f"chmod +x {folder}/pinyon-shift.sh",
             # Bytes: a text-mode pipe on Windows would end lines with CRLF.
             input=SHORTCUT_LAUNCHER.format(root=deck.root).encode())
    parms = {
        "gameid": SHORTCUT_GAMEID,
        "directory": f"/home/{deck.user}/{folder}",
        "argv": ["./pinyon-shift.sh"],
        "env": {},
        "settings": {"steam_play": "0", "compat_tool": ""},
        "force_appid": "",
        "lepton_args": "",
    }
    reply = deck.output("python3 ~/devkit-utils/steam-client-create-shortcut --parms "
                        + shlex.quote(json.dumps(parms)))
    result = json.loads(reply.strip().splitlines()[-1])
    if "error" in result:
        raise DeckError(f"Steam did not add the shortcut: {result['error']}")
    print(f"added {SHORTCUT_GAMEID} to Steam on the Deck")
    return 0


def add_parser(commands) -> None:
    deck = commands.add_parser("deck", help="run the Linux build on a Steam Deck over SSH")
    sub = deck.add_subparsers(dest="deck_command", required=True)

    def command(name: str, handler, help_text: str) -> argparse.ArgumentParser:
        parser = sub.add_parser(name, help=help_text)
        parser.add_argument("--host", help="the Deck's address (default $PINYON_DECK_HOST "
                            "or steamdeck)")
        parser.add_argument("--user", default="deck")
        parser.add_argument("--key", type=Path, help="SSH key (default: the devkit client's)")
        parser.add_argument("--remote-root", help=f"folder in the Deck's home (default {REMOTE})")
        parser.set_defaults(deck_handler=handler)
        return parser

    command("doctor", doctor, "check the connection and the Deck")
    parser = command("install", install, "copy the Linux build to the Deck")
    parser.add_argument("--build-directory", type=Path)
    parser.add_argument("--configuration", choices=("Release", "RelWithDebInfo"),
                        default="Release")
    parser = command("push-data", push_data, "copy the extracted game to the Deck")
    parser.add_argument("--game-root", type=Path)
    parser = command("run", run_game, "start the game on the Deck")
    parser.add_argument("--state", default="default",
                        help="private state root under qual/ (default: default)")
    parser.add_argument("--null-gpu", action="store_true", help="no renderer (gpu_backend=null)")
    parser.add_argument("--route", type=Path, help="a render-test route to run")
    parser.add_argument("--seed", type=Path, help="a render seed for the state (user, config)")
    parser.add_argument("--display", help="run in this X display (Game Mode: :0) "
                        "instead of a headless gamescope")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--refresh", type=int, default=60)
    parser.add_argument("--wait", action="store_true", help="wait until the game exits")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("game_arguments", nargs="*", help="after --, passed to the game")
    command("stop", stop, "stop the game on the Deck")
    parser = command("shortcut", shortcut, "add the game to Steam on the Deck")
    parser.add_argument("--seed", type=Path,
                        help="a render seed for an empty play state (user, config)")
    parser = command("pull-logs", pull_logs, "copy a state's logs and route output back")
    parser.add_argument("--state", default="default")
    parser.add_argument("--output", type=Path)


def main(args: argparse.Namespace) -> int:
    try:
        return args.deck_handler(args)
    except DeckError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    top = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_parser(top.add_subparsers(dest="command", required=True))
    sys.exit(main(top.parse_args()))
