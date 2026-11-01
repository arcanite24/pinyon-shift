#!/usr/bin/env python3
"""Vulkan shader preparation off Windows (LX-3.3): what
tools/prepare-fh1-shaders.ps1 and prepare-fh1-vulkan.ps1 do for Vulkan.

Vulkan translates shaders and creates pipelines as the game runs, and keeps
them for later launches: its shader and pipeline storage, the Vulkan pipeline
cache and the driver's own shader cache. A first launch without any of them
stalls for seconds, inside races too (DR-1.3). So before the first start
`pinyon.py launch` plays the shader preparation route once, hidden, with the
player's settings, in a private state folder, which fills the driver's cache,
and keeps the storage it wrote. Storage the player already has is never
replaced. A failure is a warning: the game still plays, it only stutters the
first time.

The attempt is recorded for each build (fh1-vulkan-preparation-skipped.json),
so a preparation that failed or was stopped is not retried at every start.

The route covers the opening only. Free roam's pipelines come from a catalog
of earlier play (config/fh1-aot-pipelines.json, AOT-4): its shaders are
rebuilt from the player's own disc and DLC and written to
4D5309C9.fbo.aot.xpso, which the game builds behind the title. That file is
rewritten when the catalog or the installed DLC change.

  pinyon.py prepare-shaders [--state-root DIR] [--game-root DIR]
                            [--build-directory DIR] [--pipelines-only] [--json]

--pipelines-only writes the ahead-of-time list and nothing else; Windows
setup (tools/prepare-fh1-shaders.ps1) runs it before its own route.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pinyon_common as common  # noqa: E402
import fh1_aot_pipelines as aot  # noqa: E402

ROUTE = common.ROOT / "config" / "render-tests" / "fh1-shader-preparation.fh1test"
SKIPPED = "fh1-vulkan-preparation-skipped.json"
STORAGE = (("cache/shaders/shareable", ("*.xsh", "*.vk.xpso")),
           ("cache/shaders", ("*.vkpipelinecache.*.bin",)))
# The route plays the opening, hidden; a stuck run is stopped after this.
ROUTE_TIMEOUT = 3600
CATALOG = common.ROOT / "config" / "fh1-aot-pipelines.json"
AOT_FILE = "4D5309C9.fbo.aot.xpso"
AOT_RECORD = "fh1-aot-pipelines.json"
CONTENT = Path("user/0000000000000000/4D5309C9/00000002")


def event(percent: int, message: str, as_json: bool) -> None:
    """The launchers' progress protocol, on stderr so stdout keeps the result."""
    if as_json:
        print("::pinyon::" + json.dumps({"stage": "shaders", "percent": percent,
                                         "message": message}), file=sys.stderr, flush=True)
    else:
        print(f"[SHADERS] {message}", file=sys.stderr, flush=True)


def build_key(build: Path) -> str:
    executable = build / common.EXECUTABLE
    if not executable.is_file():
        return "none"
    info = executable.stat()
    return f"{info.st_size} {info.st_mtime_ns}"


def stored(cache: Path) -> list[Path]:
    folder = cache / "shaders" / "shareable"
    return sorted(folder.glob("*.vk.xpso")) if folder.is_dir() else []


@contextlib.contextmanager
def preparation_lock(cache: Path):
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / "fh1-preparation.lock").open("a+b") as lock:
        try:
            if common.WINDOWS:
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise common.CommandError("Another launcher is preparing graphics for this "
                                      "installation. Wait for it to finish.") from None
        yield


def route_completed(state: Path) -> bool:
    completions = 0
    for log in (state / "logs").glob("*.jsonl"):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                completions += json.loads(line).get("event") == "fh1.render_test.complete"
            except (ValueError, AttributeError):
                continue
    return completions == 1


def keep_storage(route_state: Path, state: Path) -> int:
    copied = 0
    for relative, patterns in STORAGE:
        source, destination = route_state / relative, state / relative
        for pattern in patterns:
            for file in sorted(source.glob(pattern)) if source.is_dir() else []:
                target = destination / file.name
                if not file.is_file() or target.exists():
                    continue
                destination.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
                shutil.copyfile(file, temporary)
                os.replace(temporary, target)
                copied += 1
    return copied


def prepare_aot(state: Path, game: Path, build: Path, as_json: bool) -> str:
    """Writes the ahead-of-time pipelines; returns what happened, for the log."""
    cache = state / "cache"
    output = cache / "shaders" / "shareable" / AOT_FILE
    content = state / CONTENT
    packages = sorted(path for path in content.iterdir() if path.is_dir()) if content.is_dir() else []
    key = hashlib.sha256(CATALOG.read_bytes()).hexdigest() if CATALOG.is_file() else None
    key = {"catalog": key, "content": [path.name for path in packages]}
    try:
        current = json.loads((cache / AOT_RECORD).read_text(encoding="utf-8")) == key
    except (OSError, ValueError):
        current = False
    if key["catalog"] is None or (current and output.is_file()):
        return "ready" if key["catalog"] else "no catalog"
    extractor = build / common.EXTRACTOR
    if not extractor.is_file():
        return f"skipped: {extractor} is not built"
    event(0, "Preparing Vulkan pipelines for free roam from the game files.", as_json)
    work = common.ROOT / ".local" / "native-renderer" / f"aot-pipelines-{uuid.uuid4().hex}"
    command = [common.python_executable(), str(common.ROOT / "tools" / "extract-fh1-shader-corpus.py"),
               str(game), "--output", str(work / "corpus.json"), "--binary-dir", str(work / "corpus"),
               "--archive-extractor", str(extractor),
               *[f"--content-root={path}" for path in packages]]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, errors="replace")
        if completed.returncode:
            return f"skipped: shader extraction failed ({completed.stderr.strip()[-300:]})"
        result = aot.generate(work / "corpus", CATALOG, output)
        common.write_json_atomic(cache / AOT_RECORD, key)
    except (OSError, ValueError) as error:
        return f"skipped: {error}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return f"{result['pipelines']} pipelines from {result['shaders']} shaders"


def prepare(state: Path, game: Path, build: Path, as_json: bool) -> dict:
    """Returns {"shaders": "ready" | "prepared" | "skipped", "message", "aot"}."""
    common.require_game_closed("preparing graphics")
    with preparation_lock(state / "cache"):
        pipelines = prepare_aot(state, game, build, as_json)
    result = prepare_route(state, game, build, as_json)
    result["aot"] = pipelines
    return result


def prepare_route(state: Path, game: Path, build: Path, as_json: bool) -> dict:
    cache = state / "cache"
    skipped = cache / SKIPPED
    key = build_key(build)
    try:
        previous = json.loads(skipped.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    if stored(cache) or (isinstance(previous, dict) and previous.get("build") == key):
        event(100, "Vulkan shaders are prepared.", as_json)
        return {"shaders": "ready", "message": "Vulkan shaders are prepared."}
    with preparation_lock(cache):
        common.write_json_atomic(skipped, {"schema_version": 1, "build": key})
        work = common.ROOT / ".local" / "native-renderer" / f"vulkan-preparation-{uuid.uuid4().hex}"
        route_state = work / "state"
        (route_state / "config").mkdir(parents=True)
        config = state / "config" / "pinyon_shift.toml"
        if config.is_file():
            shutil.copyfile(config, route_state / "config" / "pinyon_shift.toml")
        # The v4 build loads the player's title update from the state it
        # runs in. Without it the v4 executable starts the base disc's code,
        # finds none of its functions and quits at once, so v4 would never
        # be prepared. The base build never mounts this folder.
        update = state / "title-update-v4"
        if update.is_dir():
            shutil.copytree(update, route_state / "title-update-v4")
        # The route's start builds the ahead-of-time pipelines too, so the
        # driver keeps them and the player's first start finds them compiled.
        pipelines = cache / "shaders" / "shareable" / AOT_FILE
        if pipelines.is_file():
            (route_state / "cache" / "shaders" / "shareable").mkdir(parents=True)
            shutil.copyfile(pipelines, route_state / "cache" / "shaders" / "shareable" / AOT_FILE)

        def skip(reason: str) -> dict:
            message = (f"Vulkan shader preparation was skipped: {reason} The first race may "
                       f"stutter while shaders are prepared. Details: {work}")
            event(100, message, as_json)
            return {"shaders": "skipped", "message": message}

        event(0, "Preparing Vulkan shaders: playing the opening once, hidden. This takes a few "
                 "minutes, once.", as_json)
        command = [common.python_executable(), str(common.ROOT / "tools" / "pinyon.py"), "launch",
                   "--state-root", str(route_state), "--game-root", str(game),
                   "--build-directory", str(build), "--render-test-script", str(ROUTE),
                   "--render-test-output", str(work / "output"), "--include-opening-movies",
                   "--hidden", "--timeout", str(ROUTE_TIMEOUT), "--json"]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, errors="replace")
        except OSError as error:
            return skip(f"the preparation route did not start ({error}).")
        lines = [line for line in completed.stdout.splitlines() if line.startswith("{")]
        try:
            result = json.loads(lines[-1]).get("result") if lines else None
        except ValueError:
            result = None
        if result != "normal-exit" or not route_completed(route_state):
            return skip(f"the preparation route did not complete (result {result}).")
        copied = keep_storage(route_state, state)
        if not stored(cache):
            return skip("the preparation route wrote no Vulkan pipeline storage.")
        shutil.rmtree(work, ignore_errors=True)
        message = f"Vulkan shaders are prepared ({copied} storage files kept)."
        event(100, message, as_json)
        return {"shaders": "prepared", "message": message, "copied": copied}


def run(args: argparse.Namespace) -> dict:
    build = (args.build_directory or common.build_directory()).resolve()
    if not (build / common.EXECUTABLE).is_file():
        raise common.CommandError(f"the game is not built at {build}")
    state, game = common.state_root(args.state_root), common.game_root(args.game_root)
    if args.pipelines_only:
        common.require_game_closed("preparing graphics")
        with preparation_lock(state / "cache"):
            pipelines = prepare_aot(state, game, build, args.json)
        event(100, f"Ahead-of-time Vulkan pipelines: {pipelines}.", args.json)
        return {"aot": pipelines}
    return prepare(state, game, build, args.json)


def add_parser(commands) -> None:
    parser = commands.add_parser("prepare-shaders",
                                 help="fill Vulkan shader storage before the first start")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--game-root", type=Path)
    parser.add_argument("--build-directory", type=Path)
    parser.add_argument("--pipelines-only", action="store_true",
                        help="only write the ahead-of-time pipeline list")
    parser.add_argument("--json", action="store_true")


def main(args: argparse.Namespace) -> int:
    return common.run_command(run, args)
