#!/usr/bin/env python3
"""Run one deterministic FH1 renderer scenario without UI automation."""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
import wave
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path


SCHEMA = "pinyon-shift.fh1-render-test-result.v1"
HEADER = "pinyon-shift-fh1-render-test-v1"
# Keys a `hostkey` step may press (src/fh1_render_test.cpp ParseHostKey).
HOST_KEYS = {"f6", "f7", "f8", "f10", "enter", "escape", "up", "down", "left", "right", "space"}
PASS_FAMILY = re.compile(
    r"FH1 V5 pass family (?P<family>[0-9A-F]{16}): attachment "
    r"(?P<attachment>[0-9A-F]{16}), first family (?P<first_family>[0-9A-F]{16}), "
    r"first draw (?P<first_draw>[0-9A-F]{16}), copy (?P<copy>[0-9A-F]{16}), "
    r"samples (?P<samples>\d+), draws (?P<minimum>\d+)-(?P<maximum>\d+) "
    r"\(average (?P<average_draws>\d+)\), total (?P<total_ns>\d+) ns, "
    r"average (?P<average_ns>\d+) ns, maximum (?P<maximum_ns>\d+) ns"
    r"(?:, average draw (?P<average_draw_ns>\d+) ns, average resolve "
    r"(?P<average_resolve_ns>\d+) ns, maximum resolve "
    r"(?P<maximum_resolve_ns>\d+) ns)?"
)
DEFAULT_IMAGE_LIMITS = (12.0, 30.0, 0.60)
RALLY_STAGE_ROUTES = (*range(1, 22), *range(41, 48))
RALLY_SERIES_ROUTES = ((11, 10, 12, 44), (13, 14, 15, 45), (4, 5, 6, 42),
                      (19, 20, 21, 47), (7, 8, 9, 43), (16, 17, 18, 46), (1, 2, 3, 41))


MARKETPLACE_CONTENT = "0000000000000000"


def parse_cpu_list(text: str) -> list[int]:
    """'0,2,4,6' or '0-7' (or both) as sorted logical processor numbers."""
    cpus: set[int] = set()
    for item in text.split(","):
        first, _, last = item.strip().partition("-")
        start, end = int(first), int(last or first)
        if start > end or end >= 64:
            raise ValueError(f"bad processor list: {text}")
        cpus.update(range(start, end + 1))
    return sorted(cpus)


# Keeps one logical processor busy; run pinned by its parent.
BUSY_LOOP = "while True:\n    pass\n"


class LowSpecSimulation:
    """Sibling load and a VRAM balloon around one game run (LS-0.5)."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.load: list[subprocess.Popen] = []
        self.balloon: subprocess.Popen | None = None
        self.balloon_report: dict | None = None

    def __enter__(self) -> "LowSpecSimulation":
        try:
            if self.args.sibling_load:
                self._start_load(parse_cpu_list(self.args.sibling_load))
            if self.args.vram_balloon_gb:
                self._start_balloon(self.args.vram_balloon_gb)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _start_load(self, cpus: list[int]) -> None:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        for cpu in cpus:
            process = subprocess.Popen([sys.executable, "-c", BUSY_LOOP])
            self.load.append(process)
            if not kernel32.SetProcessAffinityMask(int(process._handle), 1 << cpu):
                raise OSError(f"could not pin the load to processor {cpu}")

    def _start_balloon(self, gigabytes: float) -> None:
        build = (self.args.build_directory or
                 Path(__file__).resolve().parents[1] / "out/build/win-amd64-release")
        executable = Path(build) / "pinyon_shift_vram_balloon.exe"
        if not executable.is_file():
            raise ValueError(f"{executable} is missing: build the pinyon_shift_vram_balloon target")
        self.balloon = subprocess.Popen(
            [str(executable), f"{gigabytes:g}"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        line = self.balloon.stdout.readline()
        if not line:
            raise RuntimeError("the VRAM balloon exited before holding memory")
        self.balloon_report = json.loads(line)

    def __exit__(self, *_exc: object) -> None:
        for process in self.load:
            process.kill()
            process.wait()
        if self.balloon:
            # The balloon frees its memory when stdin closes.
            self.balloon.stdin.close()
            try:
                self.balloon.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.balloon.kill()
                self.balloon.wait()

    def summary(self) -> dict | None:
        if not (self.args.host_cpus or self.args.sibling_load or self.args.vram_balloon_gb):
            return None
        return {
            "kind": "sensitivity",
            "host_cpus": self.args.host_cpus,
            "sibling_load": self.args.sibling_load,
            "vram_balloon": self.balloon_report,
        }


def skip_private_content(directory: str, names: list[str]) -> set[str]:
    """Leave Marketplace content for link_or_copy and drop import scratch."""
    skipped = {name for name in names if name.startswith("staging-")}
    if Path(directory).name == "user" and MARKETPLACE_CONTENT in names:
        skipped.add(MARKETPLACE_CONTENT)
    return skipped


def link_or_copy(source: str, destination: str) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def prepare_isolated_state(source: Path, destination: Path) -> None:
    if sys.platform == "win32":
        # Installed Marketplace content has deeply nested localized assets.
        def extended(path):
            value = str(path.resolve())
            if value.startswith("\\\\?\\"):
                return Path(value)
            return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)
        source, destination = extended(source), extended(destination)
    destination.mkdir(parents=True)
    # mods/ and user-modded/ carry a seed's installed mods and modded profile;
    # title-update-v4/ holds a verified title update for the v4 build.
    for name in ("user", "config", "mods", "user-modded", "dlc", "title-update-v4"):
        source_directory = source / name
        if source_directory.is_dir():
            shutil.copytree(source_directory, destination / name, ignore=skip_private_content)
    # Marketplace content (gigabytes with every DLC) is mounted read-only, so
    # hard-link it instead of copying it into every run; copying 8 GB before
    # each launch also slowed the title's DLC merge to 20 s on a full SSD.
    content = source / "user" / MARKETPLACE_CONTENT
    if content.is_dir():
        shutil.copytree(content, destination / "user" / MARKETPLACE_CONTENT, copy_function=link_or_copy)
    # Prepared owned Rally assets are a game-file overlay, not a shader cache.
    # Copy only this named artifact; other caches remain opt-in below.
    rally = source / "cache/rally_adapter"
    if rally.is_dir():
        shutil.copytree(rally, destination / "cache/rally_adapter")


def resolve_disc_shader_corpus(path: Path) -> Path:
    for candidate in (path, path / "ucode"):
        if candidate.is_dir() and (
            (candidate / "corpus.blob").is_file() or next(candidate.glob("*.bin"), None)
        ):
            return candidate.resolve()
    raise ValueError(
        "--disc-shader-corpus-dir contains no corpus.blob or .bin shaders (directly or in ucode/)"
    )


def seed_fh1_shader_storage(source: Path, destination: Path) -> list[str]:
    source_directory = source / "cache"
    destination_directory = destination / "cache"
    names = ("fh1-native-shaders-v2.bin", "fh1-native-pipelines-v1.bin")
    missing = [name for name in names if not (source_directory / name).is_file()]
    if missing:
        raise ValueError("missing FH1 shader storage: " + ", ".join(missing))
    destination_directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(source_directory / name, destination_directory / name)
    return list(names)


def seed_vulkan_shader_storage(source: Path, destination: Path) -> list[str]:
    """Copy the seed's Vulkan shader (.xsh) and pipeline (.fbo.vk.xpso) storage.

    The Vulkan backend translates at run time and recreates the stored
    pipelines at start, so a route seeded with the storage of an earlier run
    renders the race without compiling shaders on the way, which is what a
    performance measurement needs.
    """
    source_directory = source / "cache" / "shaders" / "shareable"
    names = sorted(
        path.name
        for pattern in ("*.xsh", "*.fbo.vk.xpso")
        for path in source_directory.glob(pattern)
        if path.is_file()
    )
    if not names:
        raise ValueError(f"missing Vulkan shader storage below {source_directory}")
    destination_directory = destination / "cache" / "shaders" / "shareable"
    destination_directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(source_directory / name, destination_directory / name)
    return names


def seed_fh1_pipeline_prewarm(source: Path, destination: Path) -> str:
    name = "fh1-gpu-prewarm-v3.txt"
    source_path = source / "cache" / name
    if not source_path.is_file():
        raise ValueError(f"missing FH1 pipeline prewarm allowlist: {source_path}")
    destination_path = destination / "cache" / name
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return name


def require_image_reference(image_limits, baseline_dir, record_baseline):
    if image_limits and not baseline_dir and not record_baseline:
        raise ValueError(
            "scenario has image expectations; pass --baseline-dir or "
            "--record-baseline"
        )


def compare_vehicle_poses(captures, baseline_captures, maximum_distance):
    baseline_by_frame = {capture["frame"]: capture for capture in baseline_captures}
    comparisons = []
    for capture in captures:
        baseline = baseline_by_frame.get(capture["frame"])
        if not baseline or "vehicle_pose" not in capture or "vehicle_pose" not in baseline:
            raise RuntimeError(
                f"missing vehicle pose baseline for frame {capture['frame']}"
            )
        distance = math.dist(
            (capture["vehicle_pose"][axis] for axis in ("x", "y", "z")),
            (baseline["vehicle_pose"][axis] for axis in ("x", "y", "z")),
        )
        comparisons.append(
            {"frame": capture["frame"], "distance": round(distance, 6)}
        )
        if distance > maximum_distance:
            raise RuntimeError(
                f"vehicle pose at frame {capture['frame']} differs by "
                f"{distance:.3f} m (maximum {maximum_distance:.3f} m)"
            )
    return comparisons


def parse_scenario(
    path: Path,
) -> tuple[
    list[tuple[int, str]],
    int,
    dict[str, tuple[float, float, float]],
    tuple[float, float, float, float] | None,
    float | None,
    tuple[float, float, int] | None,
    list[tuple[str, str, float]],
    set[str],
    list[set[str]],
]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != HEADER:
        raise ValueError("unsupported FH1 render-test schema")
    if (any(line.startswith("# clock-hz ") for line in lines) and
            any(line.startswith("wait ") for line in lines)):
        raise ValueError("wall-time scripts cannot use output-frame waits")
    captures: list[tuple[int, str]] = []
    stop = 0
    image_limits: dict[str, tuple[float, float, float]] = {}
    performance_limits = None
    distinct_presentation_min = None
    simulation_time_limits = None
    capture_mae_minimums: list[tuple[str, str, float]] = []
    race_hud_captures: set[str] = set()
    race_hud_any_groups: list[set[str]] = []
    previous_input = -1
    previous_wait = 0
    previous_hostkey = -1
    first_input = None
    for number, line in enumerate(lines[1:], 2):
        if line.startswith("# expect-image "):
            fields = line.split()
            if len(fields) != 6:
                raise ValueError(f"line {number}: invalid image expectation")
            limits = tuple(float(value) for value in fields[3:])
            if any(value < 0 for value in limits) or limits[2] > 1:
                raise ValueError(f"line {number}: invalid image limits")
            image_limits[fields[2]] = limits
            continue
        if line.startswith("# expect-performance "):
            fields = line.split()
            if len(fields) != 6 or performance_limits is not None:
                raise ValueError(f"line {number}: invalid performance expectation")
            performance_limits = tuple(float(value) for value in fields[2:])
            if any(value < 0 for value in performance_limits):
                raise ValueError(f"line {number}: invalid performance limits")
            continue
        if line.startswith("# expect-distinct-presentation "):
            fields = line.split()
            if len(fields) != 3 or distinct_presentation_min is not None:
                raise ValueError(
                    f"line {number}: invalid distinct-presentation expectation"
                )
            distinct_presentation_min = float(fields[2])
            if distinct_presentation_min < 0:
                raise ValueError(
                    f"line {number}: invalid distinct-presentation minimum"
                )
            continue
        if line.startswith("# expect-simulation-time "):
            fields = line.split()
            if len(fields) != 5 or simulation_time_limits is not None:
                raise ValueError(
                    f"line {number}: invalid simulation-time expectation"
                )
            simulation_time_limits = (
                float(fields[2]),
                float(fields[3]),
                int(fields[4]),
            )
            if (
                simulation_time_limits[0] < 0
                or simulation_time_limits[0] > simulation_time_limits[1]
                or simulation_time_limits[2] < 0
            ):
                raise ValueError(
                    f"line {number}: invalid simulation-time limits"
                )
            continue
        if line.startswith("# expect-capture-mae "):
            fields = line.split()
            if len(fields) != 5:
                raise ValueError(f"line {number}: invalid capture-MAE expectation")
            minimum = float(fields[4])
            if minimum < 0:
                raise ValueError(f"line {number}: invalid capture-MAE minimum")
            capture_mae_minimums.append((fields[2], fields[3], minimum))
            continue
        if line.startswith("# expect-race-hud "):
            fields = line.split()
            if len(fields) != 3:
                raise ValueError(f"line {number}: invalid race-HUD expectation")
            race_hud_captures.add(fields[2])
            continue
        if line.startswith("# expect-race-hud-any "):
            fields = line.split()
            if len(fields) < 4:
                raise ValueError(f"line {number}: invalid race-HUD-any expectation")
            race_hud_any_groups.append(set(fields[2:]))
            continue
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if fields[0] == "input" and len(fields) == 9:
            frame = int(fields[1])
            if frame <= previous_input:
                raise ValueError(f"line {number}: input frames must increase")
            int(fields[2], 16)
            values = [int(value) for value in fields[3:]]
            if not 0 <= values[0] <= 255 or not 0 <= values[1] <= 255:
                raise ValueError(f"line {number}: trigger is out of range")
            if any(value < -32768 or value > 32767 for value in values[2:]):
                raise ValueError(f"line {number}: stick is out of range")
            previous_input = frame
            if first_input is None:
                first_input = frame
        elif fields[0] == "wait" and (
            (len(fields) == 4 and fields[3] in ("vehicle", "rally-stage-saved", "freeroam"))
            or (len(fields) == 5 and fields[3] in ("vehicle-moved", "movie", "file"))
        ):
            # wait <frame> <max-frames> <condition> [argument]: the script
            # clock holds at <frame> until the game reaches the condition.
            if int(fields[1]) <= 0 or int(fields[2]) <= 0:
                raise ValueError(f"line {number}: invalid wait")
            if int(fields[1]) <= previous_wait:
                raise ValueError(f"line {number}: waits must be in increasing frame order")
            previous_wait = int(fields[1])
            if fields[3] == "vehicle-moved" and int(fields[4]) <= 0:
                raise ValueError(f"line {number}: invalid wait distance")
        elif fields[0] == "hostkey" and len(fields) == 3:
            # hostkey <frame> <key>: a key press on the window for host UI.
            if fields[2].lower() not in HOST_KEYS:
                raise ValueError(f"line {number}: unknown host key {fields[2]}")
            if int(fields[1]) <= previous_hostkey:
                raise ValueError(f"line {number}: host keys must be in increasing frame order")
            previous_hostkey = int(fields[1])
        elif fields[0] == "xamdialog" and len(fields) == 3:
            # xamdialog <frame> message|keyboard: a sample host XAM dialog.
            if fields[2] not in ("message", "keyboard", "achievements", "toast"):
                raise ValueError(f"line {number}: unknown XAM dialog {fields[2]}")
            if int(fields[1]) <= previous_hostkey:
                raise ValueError(f"line {number}: host keys must be in increasing frame order")
            previous_hostkey = int(fields[1])
        elif fields[0] == "cvar" and len(fields) == 4:
            # cvar <frame> <name> <value>: a settings change at run time.
            if int(fields[1]) <= previous_hostkey:
                raise ValueError(f"line {number}: host keys must be in increasing frame order")
            previous_hostkey = int(fields[1])
        elif (fields[0] == "mark" and len(fields) == 2) or (
            fields[0] == "scanpoke" and len(fields) in (5, 7, 9)
        ):
            # mark <frame>: keep a copy of the title's heaps; scanpoke <frame>
            # <min> <max> <float> [<min step> <max step> [<first> <count>]]: poke
            # every float in [min, max] that rose by the same step between each
            # pair of marks (three or more), or only that slice of them.
            if fields[0] == "scanpoke":
                if float(fields[2]) > float(fields[3]):
                    raise ValueError(f"line {number}: empty scanpoke range")
                float(fields[4])
            if int(fields[1]) <= previous_hostkey:
                raise ValueError(f"line {number}: host keys must be in increasing frame order")
            previous_hostkey = int(fields[1])
        elif (fields[0] == "snapshot" and len(fields) == 3) or (
            fields[0] == "poke" and len(fields) == 4
        ):
            # snapshot <frame> <name>: guest physical memory to <name>.mem;
            # poke <frame> <hex physical address> <float>: a big-endian store.
            if fields[0] == "snapshot" and not re.fullmatch(r"[A-Za-z0-9_-]+", fields[2]):
                raise ValueError(f"line {number}: invalid snapshot name")
            if fields[0] == "poke":
                if int(fields[2], 16) >= 0x20000000:
                    raise ValueError(f"line {number}: poke outside physical memory")
                float(fields[3])
            if int(fields[1]) <= previous_hostkey:
                raise ValueError(f"line {number}: host keys must be in increasing frame order")
            previous_hostkey = int(fields[1])
        elif fields[0] == "hostclick" and len(fields) == 5:
            # hostclick <frame> <left|right> <x> <y>, in 1280x720 title space.
            if fields[2] not in ("left", "right"):
                raise ValueError(f"line {number}: unknown mouse button {fields[2]}")
            if not (0 <= int(fields[3]) < 1280 and 0 <= int(fields[4]) < 720):
                raise ValueError(f"line {number}: click outside the 1280x720 title space")
            if int(fields[1]) <= previous_hostkey:
                raise ValueError(f"line {number}: host keys must be in increasing frame order")
            previous_hostkey = int(fields[1])
        elif fields[0] == "capture" and len(fields) == 3:
            captures.append((int(fields[1]), fields[2]))
        elif fields[0] == "stop" and len(fields) == 2:
            if stop:
                raise ValueError("scenario has multiple stop commands")
            stop = int(fields[1])
        else:
            raise ValueError(f"line {number}: invalid command")
    if previous_input < 0 or first_input != 0:
        raise ValueError("scenario must start with input frame 0")
    if not captures or any(
        frame <= 0 or (index and frame <= captures[index - 1][0])
        for index, (frame, _) in enumerate(captures)
    ):
        raise ValueError("capture frames must be positive and increasing")
    if stop <= captures[-1][0]:
        raise ValueError("stop frame must follow every capture")
    unknown_images = image_limits.keys() - {name for _, name in captures}
    if unknown_images:
        raise ValueError("image expectation has no capture: " + min(unknown_images))
    capture_names = {name for _, name in captures}
    unknown_race_hud = race_hud_captures - capture_names
    unknown_race_hud.update(
        name for group in race_hud_any_groups for name in group - capture_names
    )
    if unknown_race_hud:
        raise ValueError(
            "race-HUD expectation names an unknown capture: "
            + min(unknown_race_hud)
        )
    for first, second, _ in capture_mae_minimums:
        if first not in capture_names or second not in capture_names:
            raise ValueError("capture-MAE expectation names an unknown capture")
    if performance_limits and performance_limits[2] > performance_limits[3]:
        raise ValueError("simulation cadence limits are reversed")
    return (
        captures,
        stop,
        image_limits,
        performance_limits,
        distinct_presentation_min,
        simulation_time_limits,
        capture_mae_minimums,
        race_hud_captures,
        race_hud_any_groups,
    )


def ppm_payload(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    match = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", data)
    if not match:
        raise ValueError(f"{path}: invalid PPM")
    width, height = map(int, match.groups())
    pixels = data[match.end() :]
    if len(pixels) != width * height * 3:
        raise ValueError(f"{path}: truncated PPM")
    return width, height, pixels


def first_race_hud_summary(output: Path, names: set[str]):
    for name in sorted(names):
        try:
            return name, race_hud_summary(output / f"{name}.ppm")
        except RuntimeError:
            pass
    raise RuntimeError(
        "missing FH1 race HUD in every alternative capture: "
        + ", ".join(sorted(names))
    )


def ppm_summary(path: Path) -> dict[str, object]:
    width, height, pixels = ppm_payload(path)
    minimum, maximum = min(pixels), max(pixels)
    mean = sum(pixels) / len(pixels)
    if maximum - minimum < 8 or mean < 1 or mean > 254:
        raise ValueError(f"{path}: blank or degenerate output")
    return {
        "file": str(path),
        "width": width,
        "height": height,
        "minimum": minimum,
        "maximum": maximum,
        "mean": round(mean, 3),
    }


def compare_capture_mae(output: Path, first: str, second: str) -> float:
    first_width, first_height, first_pixels = ppm_payload(output / f"{first}.ppm")
    second_width, second_height, second_pixels = ppm_payload(output / f"{second}.ppm")
    if (first_width, first_height) != (second_width, second_height):
        raise RuntimeError(f"capture dimensions differ: {first}, {second}")
    return sum(abs(a - b) for a, b in zip(first_pixels, second_pixels)) / len(
        first_pixels
    )


def race_hud_summary(path: Path) -> dict[str, float]:
    width, height, pixels = ppm_payload(path)

    def fraction(bounds, predicate):
        x0, x1, y0, y1 = bounds
        matches = total = 0
        for y in range(int(height * y0), int(height * y1)):
            for x in range(int(width * x0), int(width * x1)):
                offset = (y * width + x) * 3
                red, green, blue = pixels[offset : offset + 3]
                matches += predicate(red, green, blue)
                total += 1
        return matches / total

    white = lambda red, green, blue: min(red, green, blue) > 220
    pink = lambda red, green, blue: (
        red > 170 and blue > 70 and red > green * 1.35
    )
    result = {
        "lap_white_fraction": fraction((0.03, 0.23, 0.02, 0.14), white),
        "place_white_fraction": fraction((0.78, 0.97, 0.02, 0.14), white),
        "standings_white_fraction": fraction((0.78, 0.97, 0.15, 0.40), white),
        # A solo stage (and a leader) puts the player's pink row first.
        "standings_pink_fraction": fraction((0.78, 0.97, 0.15, 0.40), pink),
    }
    if (result["lap_white_fraction"] < 0.01 or
            result["place_white_fraction"] < 0.01 or
            max(result["standings_white_fraction"],
                result["standings_pink_fraction"]) < 0.01):
        raise RuntimeError(f"missing FH1 race HUD in {path.name}: {result}")
    return result


def load_events(path: Path) -> list[dict[str, object]]:
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{number}: invalid JSONL") from error
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: event is not an object")
        events.append(value)
    return events


def shader_capture_summary(
    events: list[dict[str, object]], require_zero_misses: bool
) -> dict[str, int] | None:
    summaries = [
        event
        for event in events
        if event.get("event") == "native_renderer.shader_capture.summary"
    ]
    if not summaries:
        return None
    if len(summaries) != 1:
        raise RuntimeError("shader capture did not produce exactly one summary")
    summary = {
        name: int(summaries[0][name])
        for name in ("entries", "bytes", "duplicate_callbacks", "rejected_callbacks")
    }
    if require_zero_misses and summary["entries"]:
        raise RuntimeError(
            f"FH1 shader pack has {summary['entries']} runtime translation misses"
        )
    return summary


def rally_test_ai_driver_summary(events: list[dict], require_release: bool = False) -> dict:
    applied = [e for e in events if e.get("event") == "fh1.render_test.rally_ai_driver"]
    if not applied:
        raise RuntimeError("native Rally test AI driver was not applied")
    for driver in applied:
        if (driver.get("control_mode") != "0" or not driver.get("car") or
                int(driver.get("race_serial", 0)) <= 0 or int(driver.get("route", 0)) not in RALLY_STAGE_ROUTES):
            raise RuntimeError("native Rally test AI controller did not enable")
    released = [e for e in events if e.get("event") == "fh1.render_test.rally_ai_released"]
    if require_release:
        for driver in applied:
            matching = [e for e in released if e.get("car") == driver["car"] and
                        e.get("race_serial") == driver["race_serial"] and
                        events.index(e) > events.index(driver)]
            if len(matching) != 1 or matching[0].get("control_mode") != "1":
                raise RuntimeError("native Rally test AI did not return control to the player")
    return dict(applications=len(applied), releases=len(released), routes=[int(e["route"]) for e in applied],
                diagnostic_only=True, player_steering_qualified=False)


def race_finish_summary(events: list[dict]) -> dict:
    """Require the player's native end condition and a stable final time."""
    previous = None
    for event in events:
        if event.get("event") != "dlc.rally.race_trace":
            continue
        if (event.get("started"), event.get("ended"), event.get("end_reason")) != ("1", "1", "1"):
            previous = None
            continue
        seconds = float(event.get("time_72", "nan"))
        split = float(event.get("time_88", "nan"))
        if (not math.isfinite(seconds) or not math.isfinite(split) or seconds <= 0 or
                abs(seconds - split) > 0.000001 or not event.get("car") or
                not event.get("race_serial")):
            previous = None
            continue
        result = dict(car=event.get("car"), race_serial=event.get("race_serial"), seconds=seconds)
        if result == previous:
            return result
        previous = result
    raise RuntimeError("native player race finish and stable final time were not observed")


def active_rally_progress_path(events: list[dict], state_root: Path) -> Path:
    loaded = [event for event in events if event.get("event") == "dlc.rally.progress_loaded"]
    normalize = lambda path: str(Path(path).resolve()).removeprefix("\\\\?\\").casefold()
    paths = [path for name in ("user", "user-modded")
             for path in (state_root / name).glob("**/ForzaProfile/rally-progress.toml")
             if loaded and normalize(path) == normalize(loaded[-1]["path"])]
    if len(paths) != 1:
        raise RuntimeError("Rally progress was not saved in the active isolated profile")
    return paths[0]


def rally_builtin_summary(events: list[dict], state_root: Path) -> dict:
    """Require the owned overlay and earned ledger to use the normal profile."""
    normalize = lambda path: str(Path(path).resolve()).removeprefix("\\\\?\\").casefold()
    configured = [event for event in events if event.get("event") == "paths.configured"]
    mounts = [event for event in events if event.get("event") == "dlc.rally.overlay_mounted"]
    forbidden = {"mod.loaded", "mod.profile.created", "dlc.rally.adapter_error"}
    if (len(configured) != 1 or len(mounts) != 1 or
            normalize(configured[0].get("user", "")) != normalize(state_root / "user") or
            (state_root / "user-modded").exists() or
            any(event.get("event") in forbidden for event in events)):
        raise RuntimeError("built-in Rally did not use the normal profile and owned overlay")
    with (state_root / "config/pinyon_shift.toml").open("rb") as stream:
        settings = tomllib.load(stream)
    if settings.get("enabled_mods", ""):
        raise RuntimeError("built-in Rally test has enabled mods")
    path = active_rally_progress_path(events, state_root)
    if not path.resolve().is_relative_to((state_root / "user").resolve()):
        raise RuntimeError("built-in Rally progress escaped the normal profile")
    return dict(user=str(state_root / "user"), progress_path=str(path), owned_overlay=True)

def rally_normal_entry_summary(events: list[dict], state_root: Path) -> dict:
    result = rally_builtin_summary(events, state_root)
    verified = [e for e in events if e.get("event") == "dlc.rally.prepared_entry"]
    loaders = [e for e in events if e.get("event") == "dlc.rally.series_loader_installed"]
    if (len(verified) != 1 or verified[0].get("verification") != "launch_preflight" or
            len(loaders) != 1 or loaders[0].get("stage_count") != "28" or loaders[0].get("series_id") != "0"):
        raise RuntimeError("normal Rally entry did not pass launch preflight and install all stages")
    return result | dict(launch_preflight=True, stages=28)

def rally_entry_positions_summary(events: list[dict], state_root: Path) -> dict:
    """Match the native generic trigger parser to the owned activation data."""
    import xml.etree.ElementTree as ET
    path = state_root / "cache/rally_adapter/game/media/gamemodes/ColoradoDirt/rally_event_activations.xml"
    owned = ET.parse(path).getroot()
    loaded = [e for e in events if e.get("event") == "dlc.rally.entry_position_loaded"]
    if len(loaded) != 7 or len({e.get("name") for e in loaded}) != 7:
        raise RuntimeError("Rally requires seven distinct native entry positions")
    for id in range(1, 8):
        node = owned.find(f"Activity[@name='MS_RALLY_{id:02}']/TriggerZone")
        native = next((e for e in loaded if e.get("name") == f"horizon_rally_{id:02}"), None)
        if node is None or native is None:
            raise RuntimeError("Rally native entry position differs from owned activation")
        for axis in ("x", "z"):
            observed, expected = float(native[axis]), float(node.attrib[f"position.{axis}"])
            if not math.isfinite(observed) or not math.isfinite(expected) or abs(observed - expected) > 0.001:
                raise RuntimeError("Rally native entry position differs from owned activation")
    return dict(entries=7, owned_coordinates=True, activity_activation_qualified=False)


def rally_car_database_summary(events: list[dict], state_root: Path, initial_progress: list[bytes]) -> dict:
    result = rally_normal_entry_summary(events, state_root)
    complete = [e for e in events if e.get("event") == "dlc.car_trace_complete"]
    if len(complete) != 1 or any(e.get("event") in
            ("dlc.car_trace_error", "dlc.rally.stage_completed", "dlc.rally.progress_error") for e in events):
        raise RuntimeError("native Rally car database trace failed or awarded progress")
    cache = state_root / "cache/rally_adapter"
    recipe = json.loads((cache / "preparation.json").read_text())["recipe"]
    record = json.loads((state_root / "dlc" / (recipe["package_id"] + ".json")).read_text())
    mask = int(record["license_mask"], 16)
    with closing(sqlite3.connect((cache / "reference/rally.slt").resolve().as_uri() + "?mode=ro", uri=True)) as db:
        cars = db.execute("SELECT Id,IsInstalled,IsPurchased,IsSelectable,IsDrivable FROM Data_Car ORDER BY Id").fetchall()
        native = [e for e in events if e.get("event") == "dlc.car_database"]
        ids = [int(e["car_id"]) for e in native]
        if ids != [row[0] for row in cars] or complete[0].get("rows") != str(len(cars)):
            raise RuntimeError("native Rally car rows are missing or ambiguous")
        for original, observed in zip(cars, native):
            if [int(observed[k]) for k in ("installed", "purchased", "selectable", "drivable")] != list(original[1:]):
                raise RuntimeError("native Rally car flags differ from the owned database")
            for field, table in (("tire_options", "List_UpgradeTireCompound"),
                                 ("suspension_options", "List_UpgradeSpringDamper"),
                                 ("engine_options", "List_UpgradeEngine")):
                expected = db.execute(f"SELECT COUNT(*) FROM {table} WHERE Ordinal=?", (original[0],)).fetchone()[0]
                if expected <= 0 or int(observed[field]) != expected:
                    raise RuntimeError("native Rally upgrade rows differ from the owned database")
        owned = []
        for type, id, license, hidden in db.execute("SELECT M.ContentType,M.ContentId,O.LicenseMask,O.Hidden FROM ContentOffersMapping M JOIN ContentOffers O ON M.OfferId=O.OfferId"):
            matches = [e for e in events if e.get("event") == "dlc.content_entitlement" and
                       e.get("content_type") == str(type) and e.get("content_id") == str(id)]
            purchased = (mask & license) == license
            if (len(matches) != 1 or matches[0].get("installed") != "1" or
                    matches[0].get("purchased") != str(int(purchased)) or
                    matches[0].get("base") != "0" or matches[0].get("visible") != str(int(purchased or not hidden))):
                raise RuntimeError("native Rally entitlement differs from the imported licence")
            if type == 1 and purchased and next(row for row in cars if row[0] == id)[3]: owned.append(id)
    if active_rally_progress_path(events, state_root).read_bytes() not in initial_progress:
        raise RuntimeError("native Rally database trace changed earned progress")
    return result | dict(car_rows=len(cars), selectable_owned_cars=owned, license_mask=record["license_mask"],
                         native_merge=True, native_entitlements=True, native_upgrade_rows=True,
                         purchase_driving_and_upgrade_ui_qualified=False)


def rally_entry_summary(events: list[dict], state_root: Path, series_id: int) -> dict:
    """Require a normal owned activity to start its first native stage and checkpoint."""
    if series_id not in range(1, 8):
        raise RuntimeError("invalid Rally entry championship")
    result = rally_normal_entry_summary(events, state_root)
    if any(e.get("event") in ("dlc.rally.progress_error", "dlc.rally.series_error", "dlc.rally.hub_error", "dlc.rally.stage_completed") for e in events):
        raise RuntimeError("Rally entry reported an error or unexpected award")
    hub = [e for e in events if e.get("event") == "dlc.rally.hub_selected"]
    if hub and (len(hub) != 1 or hub[0].get("series_id") != str(series_id) or
                hub[0].get("source") not in ("player", "private_probe")):
        raise RuntimeError("Rally entry has an ambiguous hub selection")
    route = RALLY_SERIES_ROUTES[series_id - 1][0]
    previous = running = None
    for event in events:
        if event.get("event") != "dlc.rally.race_trace":
            continue
        valid = (event.get("route") == str(route) and event.get("mode") == "3" and
                 event.get("started") == "1" and event.get("ended") == "0" and
                 event.get("end_reason") == "0" and event.get("car") and
                 int(event.get("event_id", 0)) > 0 and int(event.get("race_serial", 0)) > 0)
        seconds = float(event.get("time_72", "nan"))
        if not valid or not math.isfinite(seconds) or seconds <= 0:
            previous = None
            continue
        if (previous and all(event.get(key) == previous.get(key) for key in ("car", "event_id", "race_serial"))
                and seconds > float(previous["time_72"])):
            running = event
            break
        previous = event
    if not running:
        raise RuntimeError("normal Rally activity did not enter and advance its first stage")
    path = active_rally_progress_path(events, state_root)
    data = tomllib.loads(path.read_text())
    attempt = data.get("attempt", {})
    if (data.get("version") != 3 or attempt.get("series_id") != series_id or
            attempt.get("active") is not True or attempt.get("completed") != 0 or
            attempt.get("seconds") != [0, 0, 0, 0] or attempt.get("total_seconds") != 0 or
            [stage.get("route") for stage in data.get("stages", [])] != list(RALLY_STAGE_ROUTES) or
            [series.get("id") for series in data.get("series", [])] != list(range(1, 8)) or
            any(row.get("completions") != 0 or row.get("best_seconds") != 0
                for row in data["stages"] + data["series"])):
        raise RuntimeError("Rally first-stage entry did not preserve a fresh championship checkpoint")
    return result | dict(series_id=series_id, route=route, event_id=running["event_id"],
                         race_serial=running["race_serial"], seconds=float(running["time_72"]),
                         checkpoint_started=True, completion_qualified=False,
                         entry_source=hub[0]["source"] if hub else "native_trigger",
                         hub_ui_qualified=False)


def rally_hub_ui_summary(events: list[dict], state_root: Path, series_id: int) -> dict:
    entry = rally_entry_summary(events, state_root, series_id)
    if entry["entry_source"] != "player":
        raise RuntimeError("Rally hub UI requires player selection without the private probe")
    rally_hub_menu_summary(events, series_id)
    return entry | dict(hub_keyboard_entry=True, visual_review=False, all_series_qualified=False)


def rally_service_entry_guard_summary(events: list[dict]) -> dict:
    """Require a blocked garage selection followed by a free-roam selection."""
    captures, context, screen = {}, {}, ""
    selected = []
    for i, event in enumerate(events):
        kind = event.get("event")
        if kind == "dlc.rally.hub_context":
            context = event
        elif kind in ("hostui.open", "hostui.screen"):
            screen = event.get("screen", "")
        elif kind == "hostui.closed":
            screen = ""
        elif kind == "dlc.rally.hub_selected":
            selected.append((i, event, context))
        elif kind == "fh1.render_test.capture" and event.get("name") in (
                "garage-rally-disabled", "garage-rally-blocked", "restored-free-roam"):
            name = event["name"]
            if name in captures or event.get("game_mode") != "17":
                raise RuntimeError("Rally service guard requires one capture of each native mode-17 context")
            captures[name] = (i, context, screen)
    if len(captures) != 3 or len(selected) != 1:
        raise RuntimeError("Rally service guard lacks the blocked garage and subsequent player entry")
    first, blocked, free = (captures[name] for name in (
        "garage-rally-disabled", "garage-rally-blocked", "restored-free-roam"))
    for _, observation, page in (first, blocked):
        if (page != "HORIZON RALLY" or observation.get("available") != "0" or
                observation.get("control_available") != "0" or
                observation.get("host_ui") != "1" or observation.get("loader_idle") != "1" or
                observation.get("control_owner") in (None, "00000000", "FFFFFFFF")):
            raise RuntimeError("Rally service guard did not disable entry while native game control was held")
    chosen, selection, observation = selected[0]
    if free[1].get("control_owner") != "00000000":
        raise RuntimeError("Rally service guard requires driving with native control released")
    for state in (free[1], observation):
        if any(state.get(key) != value for key, value in dict(
                control_available="1", available="1", host_ui="0", loader_idle="1").items()):
            raise RuntimeError("Rally service guard did not restore ready free-roam entry")
    if observation.get("control_owner") != "00000000" and observation.get("owner_name") != "pause":
        raise RuntimeError("Rally service guard allowed a service owner at player entry")
    attempted = any(first[0] < i < blocked[0] and e.get("event") == "fh1.render_test.hostkey" and
                    e.get("key") == "13" for i, e in enumerate(events))
    if (not first[0] < blocked[0] < free[0] < chosen or not attempted or free[2] or
            selection.get("source") != "player" or
            any(e.get("event") == "dlc.rally.hub_error" for e in events)):
        raise RuntimeError("Rally service guard lacks the ordered blocked attempt and successful player selection")
    return dict(garage_entry_blocked=True, free_roam_entry_restored=True,
                native_control_guard=True, other_services_qualified=False)


def rally_hub_menu_summary(events: list[dict], series_id: int) -> None:
    hub = [e for e in events if e.get("event") == "dlc.rally.hub_selected"]
    if (len(hub) != 1 or hub[0].get("source") != "player" or
            hub[0].get("series_id") != str(series_id) or
            any(e.get("event") == "dlc.rally.hub_error" for e in events)):
        raise RuntimeError("Rally hub UI requires one player championship selection")
    sequence = [(i, e) for i, e in enumerate(events)]
    opened = next((i for i, e in sequence if e.get("event") == "hostui.open" and e.get("screen") == "SETTINGS"), -1)
    page = next((i for i, e in sequence if i > opened and e.get("event") == "hostui.screen" and e.get("screen") == "HORIZON RALLY"), -1)
    closed = next((i for i, e in sequence if i > page and e.get("event") == "hostui.closed"), -1)
    selected = next((i for i, e in sequence if e.get("event") == "dlc.rally.hub_selected"), -1)
    layouts = [e for e in events if e.get("event") == "hostui.layout" and e.get("screen") in ("SETTINGS", "HORIZON RALLY")]
    if not (0 <= opened < page < closed < selected) or {e.get("screen") for e in layouts} != {"SETTINGS", "HORIZON RALLY"} or any(e.get("inside") != "1" for e in layouts):
        raise RuntimeError("Rally hub UI lacks the ordered menu flow or a valid layout")


def rally_hub_resume_summary(events: list[dict], state_root: Path, series_id: int,
                             route: int, initial_progress: list[bytes]) -> dict:
    result = rally_normal_entry_summary(events, state_root)
    rally_hub_menu_summary(events, series_id)
    result |= rally_resume_summary(events, state_root, series_id, route, initial_progress)
    selected = next(i for i, e in enumerate(events) if e.get("event") == "dlc.rally.hub_selected")
    resumed = next(i for i, e in enumerate(events) if e.get("event") == "dlc.rally.series_load")
    if resumed <= selected:
        raise RuntimeError("Rally resumed before the player selected its championship")
    return result | dict(hub_keyboard_resume=True, visual_review=False)


def rally_hub_retirement_summary(events: list[dict], state_root: Path, series_id: int,
                                 initial_progress: list[bytes]) -> dict:
    result = rally_normal_entry_summary(events, state_root)
    loaded = [e for e in events if e.get("event") == "dlc.rally.series_loaded"]
    retired = [e for e in events if e.get("event") == "dlc.rally.series_retired"]
    if (len(loaded) != 1 or loaded[0].get("series_id") != str(series_id) or
            loaded[0].get("active") != "1" or len(retired) != 1 or
            retired[0].get("source") != "player" or any(e.get("event") in
            ("dlc.rally.hub_selected", "dlc.rally.hub_error", "dlc.rally.series_error",
             "dlc.rally.progress_error", "dlc.rally.stage_completed") for e in events)):
        raise RuntimeError("Rally hub retirement did not cancel one saved player attempt")
    opened = next((i for i, e in enumerate(events) if e.get("event") == "hostui.open" and e.get("screen") == "SETTINGS"), -1)
    page = next((i for i, e in enumerate(events) if i > opened and e.get("event") == "hostui.screen" and e.get("screen") == "HORIZON RALLY"), -1)
    confirmations = [i for i, e in enumerate(events) if e.get("event") == "hostui.screen" and e.get("screen") == "RETIRE CHAMPIONSHIP?"]
    index = events.index(retired[0])
    closed = next((i for i, e in enumerate(events) if i > index and e.get("event") == "hostui.closed"), -1)
    captures = [e for i, e in enumerate(events) if i > closed and e.get("event") == "fh1.render_test.capture"]
    screens = {"SETTINGS", "HORIZON RALLY", "RETIRE CHAMPIONSHIP?"}
    layouts = [e for e in events if e.get("event") == "hostui.layout" and e.get("screen") in screens]
    if (len(confirmations) != 2 or not 0 <= opened < page < confirmations[0] < confirmations[1] < index < closed or
            len(captures) < 2 or any(e.get("game_mode") != "17" for e in captures) or
            {e.get("screen") for e in layouts} != screens or any(e.get("inside") != "1" for e in layouts)):
        raise RuntimeError("Rally hub retirement lacks keep-then-confirm flow or safe layouts")
    before = [e for i, e in enumerate(events) if i < opened and
              e.get("event") == "fh1.render_test.capture" and e.get("vehicle_pose_valid") == "1"]
    if not before:
        raise RuntimeError("Rally hub retirement lacks a pre-menu vehicle capture")
    origin = [float(before[-1].get(f"vehicle_{axis}", "nan")) for axis in "xyz"]
    distances = [math.hypot(*(float(e.get(f"vehicle_{axis}", "nan")) - origin[i]
                             for i, axis in enumerate("xyz")))
                 for e in captures if e.get("vehicle_pose_valid") == "1"]
    if not distances or any(not math.isfinite(d) for d in distances) or max(distances) < 30:
        raise RuntimeError("Rally hub retirement did not restore free-roam driving")
    path = active_rally_progress_path(events, state_root)
    data = tomllib.loads(path.read_text())
    attempt = data.get("attempt", {})
    if (data.get("version") != 3 or attempt.get("series_id") != 0 or
            attempt.get("active") is not False or attempt.get("completed") != 0 or
            attempt.get("seconds") != [0, 0, 0, 0] or attempt.get("total_seconds") != 0 or
            not any(all(data.get(key) == tomllib.loads(record.decode()).get(key)
                        for key in ("stages", "series")) for record in initial_progress)):
        raise RuntimeError("Rally hub retirement changed earned records or kept its attempt")
    return result | dict(series_id=series_id, hub_keyboard_retirement=True,
                         earned_records_preserved=True, post_retirement_driving=True, visual_review=False)


def rally_progress_summary(events: list[dict], state_root: Path, finish: dict) -> dict:
    """Require one native award and the same result in the isolated profile."""
    awards = [event for event in events if event.get("event") == "dlc.rally.stage_completed"]
    if len(awards) != 1 or any(event.get("event") == "dlc.rally.progress_error" for event in events):
        raise RuntimeError("expected one saved Rally stage completion without progress errors")
    award = awards[0]
    route, count = int(award["route"]), int(award["completions"])
    seconds, best = float(award["seconds"]), float(award["best_seconds"])
    if (route not in RALLY_STAGE_ROUTES or count < 1 or
            award["race_serial"] != finish["race_serial"] or
            not math.isfinite(seconds) or not math.isfinite(best) or best <= 0 or
            best > seconds or abs(seconds - finish["seconds"]) > 0.000001):
        raise RuntimeError("saved Rally completion does not match the native finish")
    # Only read files inside this run, even if an event contains another path.
    path = active_rally_progress_path(events, state_root)
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    stages = data.get("stages", [])
    expected_routes = RALLY_STAGE_ROUTES[:21] if data.get("version") == 1 else RALLY_STAGE_ROUTES
    if data.get("version") not in (1, 2, 3) or [stage.get("route") for stage in stages] != list(expected_routes):
        raise RuntimeError("invalid saved Rally stage progress")
    if route not in expected_routes:
        raise RuntimeError("Rally completion did not persist to disk")
    saved = stages[expected_routes.index(route)]
    if (saved.get("route") != route or saved.get("completions") != count or
            not math.isfinite(saved.get("best_seconds", math.nan)) or
            abs(saved["best_seconds"] - best) > 0.000001):
        raise RuntimeError("Rally completion did not persist to disk")
    return dict(route=route, completions=count, best_seconds=saved["best_seconds"],
                path=str(path))


def rally_transition_summary(events: list[dict], first_route: int, next_route: int) -> dict:
    """Require a saved first stage followed by a different running native race."""
    if first_route not in RALLY_STAGE_ROUTES or next_route not in RALLY_STAGE_ROUTES or first_route == next_route:
        raise RuntimeError("invalid Rally transition routes")
    award = previous = None
    for event in events:
        if (event.get("event") == "dlc.rally.stage_completed" and int(event["route"]) == first_route and
                int(event.get("event_id", 0)) > 0 and int(event.get("race_serial", 0)) > 0):
            award, previous = event, None
        elif event.get("event") == "dlc.rally.race_trace" and award:
            if (event.get("route") != str(next_route) or event.get("mode") != "3" or
                    event.get("started") != "1" or event.get("ended") != "0" or
                    event.get("end_reason") != "0" or not event.get("car") or
                    int(event.get("event_id", 0)) <= 0 or event["event_id"] == award.get("event_id") or
                    int(event.get("race_serial", 0)) <= 0 or event["race_serial"] == award.get("race_serial")):
                previous = None
                continue
            seconds = float(event.get("time_72", "nan"))
            if not math.isfinite(seconds) or seconds <= 0:
                previous = None
                continue
            sample = dict(route=next_route, event_id=event["event_id"],
                          race_serial=event["race_serial"], car=event["car"], seconds=seconds)
            if (previous and all(sample[key] == previous[key] for key in
                                 ("route", "event_id", "race_serial", "car")) and
                    seconds > previous["seconds"]):
                return sample
            previous = sample
    raise RuntimeError("saved Rally stage did not transition to the next running native race")


def rally_series_summary(events: list[dict], state_root: Path, series_id: int) -> dict:
    """Qualify all four native finishes, one saved total, and final return."""
    if series_id not in range(1, 8) or any(event.get("event") in
            ("dlc.rally.series_error", "dlc.rally.progress_error") for event in events):
        raise RuntimeError("Rally series reported an error")
    routes = RALLY_SERIES_ROUTES[series_id - 1]
    awards = [event for event in events if event.get("event") == "dlc.rally.stage_completed"]
    saved = [event for event in events if event.get("event") == "dlc.rally.series_stage_saved"]
    if (tuple(int(event["route"]) for event in awards) != routes or len(saved) != 4 or
            len({event.get("event_id") for event in awards}) != 4 or
            len({event.get("race_serial") for event in awards}) != 4):
        raise RuntimeError("Rally series did not save four distinct stages in order")
    stage_results, times = [], []
    for i, award in enumerate(awards):
        traces = [event for event in events if event.get("event") == "dlc.rally.race_trace" and
                  event.get("route") == award["route"] and event.get("event_id") == award.get("event_id") and
                  event.get("race_serial") == award["race_serial"]]
        finish = race_finish_summary(traces)
        stage_results.append(rally_progress_summary(
            [event for event in events if event.get("event") != "dlc.rally.stage_completed" or event is award],
            state_root, finish))
        times.append(finish["seconds"])
        row = saved[i]
        if (int(row["series_id"]) != series_id or int(row["route"]) != routes[i] or
                int(row["completed"]) != i + 1 or int(row["next_route"]) != (routes[i + 1] if i < 3 else 0) or
                not math.isfinite(float(row["total_seconds"])) or
                abs(float(row["total_seconds"]) - sum(times)) > 0.000003):
            raise RuntimeError("Rally series saved an invalid stage total or next route")
    with Path(stage_results[0]["path"]).open("rb") as stream:
        data = tomllib.load(stream)
    attempt, series = data.get("attempt", {}), data.get("series", [])
    total = sum(times)
    if (data.get("version") != 3 or len(series) != 7 or
            [row.get("id") for row in series] != list(range(1, 8)) or
            attempt.get("series_id") != series_id or attempt.get("completed") != 4 or
            attempt.get("active") is not False or len(attempt.get("seconds", [])) != 4 or
            any(not math.isfinite(value) or abs(value - expected) > 0.000001
                for value, expected in zip(attempt["seconds"], times)) or
            not math.isfinite(attempt.get("total_seconds", math.nan)) or
            abs(attempt["total_seconds"] - total) > 0.000003):
        raise RuntimeError("completed Rally attempt did not persist to disk")
    result = series[series_id - 1]
    count, best = result.get("completions", 0), result.get("best_seconds", math.nan)
    if count < 1 or count != int(saved[-1]["series_completions"]) or not math.isfinite(best) or best <= 0 or best > attempt["total_seconds"]:
        raise RuntimeError("Rally series award did not persist to disk")
    final = events.index(awards[-1])
    returned = [i for i, event in enumerate(events) if event.get("event") == "dlc.rally.series_return" and
                event.get("event_id") == awards[-1]["event_id"] and i > final]
    if not returned or not any(i > returned[-1] and event.get("event") == "fh1.render_test.capture" and
            event.get("game_mode") == "17" for i, event in enumerate(events)):
        raise RuntimeError("completed Rally series did not return to native free roam")
    return dict(series_id=series_id, completions=count, best_seconds=best,
                total_seconds=attempt["total_seconds"], stages=stage_results, path=stage_results[0]["path"])


def rally_return_entry_summary(events: list[dict]) -> dict:
    """Require live Rally worlds, Colorado return and the original native anchor."""
    def capture(name):
        matches = [(i, e) for i, e in enumerate(events) if
                   e.get("event") == "fh1.render_test.capture" and e.get("name") == name]
        if len(matches) != 1 or matches[0][1].get("game_mode") != "17":
            raise RuntimeError(f"missing native free-roam capture {name}")
        return matches[0]

    def world_before(index):
        worlds = [e for e in events[:index] if e.get("event") == "dlc.rally.world_loaded"]
        if not worlds:
            raise RuntimeError("Rally return has no live world evidence")
        return worlds[-1]

    entry_index, entry = capture("event-ready")
    final_index, final = capture("series-return")
    returned = [i for i, e in enumerate(events) if e.get("event") == "dlc.rally.series_return"]
    if len(returned) != 1 or not entry_index < returned[0] < final_index:
        raise RuntimeError("Rally entry and return captures are out of order")
    for index in (entry_index, final_index):
        world = world_before(index)
        if (world.get("mode"), world.get("track_id"), world.get("media_name")) != ("17", "317", "Colorado"):
            raise RuntimeError("Rally did not enter or return to the live Colorado world")
    if not any(e.get("event") == "dlc.rally.world_loaded" and e.get("mode") == "17"
               for e in events[returned[0] + 1:final_index]):
        raise RuntimeError("Rally has no new Colorado world after its series return")
    awards = [(i, e) for i, e in enumerate(events) if e.get("event") == "dlc.rally.stage_completed"]
    worlds = [world_before(i) for i, _ in awards]
    if len(worlds) != 4 or len({e.get("track_id") for e in worlds}) != 4 or any(
            e.get("mode") != "3" or e.get("media_name") != "ColoradoDirt" or
            int(e.get("track_id", 0)) <= 0 for e in worlds):
        raise RuntimeError("Rally did not finish in four distinct live Rally worlds")
    anchors = [(i, e) for i, e in enumerate(events[:final_index]) if
               e.get("event") == "dlc.rally.return_anchor"]
    fields = ("x", "y", "z", "forward_x", "forward_y", "forward_z")
    if not anchors or anchors[0][0] >= entry_index:
        raise RuntimeError("Rally has no native entry anchor")
    if any(not any(j < i and anchor.get("mode") == "3" and
                   anchor.get("event_id") == award.get("event_id") for j, anchor in anchors)
           for i, award in awards) or not any(j > returned[0] and anchor.get("mode") == "17"
                                             for j, anchor in anchors):
        raise RuntimeError("Rally anchor was not observed through all stages and return")
    initial = tuple(float(anchors[0][1].get(key, "nan")) for key in fields)
    if not all(math.isfinite(value) for value in initial) or any(
            e.get("valid") != "1" or any(not math.isfinite(value := float(e.get(key, "nan"))) or
            abs(value - expected) > 0.001 for key, expected in zip(fields, initial))
            for _, e in anchors):
        raise RuntimeError("Rally changed its native return anchor")
    distances = []
    for event, maximum in ((entry, 25), (final, 250)):
        pose = tuple(float(event.get("vehicle_" + axis, "nan")) for axis in ("x", "y", "z"))
        distance = math.dist(pose, initial[:3])
        if event.get("vehicle_pose_valid") != "1" or not math.isfinite(distance) or distance > maximum:
            raise RuntimeError("Rally free-roam car did not return near its original entry")
        distances.append(distance)
    return dict(track_id=317, media_name="Colorado", anchor=dict(zip(fields, initial)),
                entry_distance=distances[0], return_distance=distances[1])


def rally_retirement_summary(events: list[dict], route: int, state_root: Path | None = None,
                             initial_progress: list[bytes] | None = None) -> dict:
    """Require an unfinished mapped stage to return without a saved award."""
    if route not in RALLY_STAGE_ROUTES or any(event.get("event") in
            ("dlc.rally.stage_completed", "dlc.rally.progress_error", "dlc.rally.series_error") for event in events):
        raise RuntimeError("Rally retirement awarded progress or reported an error")
    attempt = None
    for event in events:
        if attempt and event.get("event") == "fh1.render_test.capture" and event.get("game_mode") == "17":
            break
        if event.get("event") != "dlc.rally.race_trace":
            continue
        if event.get("route") == str(route) and event.get("mode") == "3":
            if event.get("ended") == "1" and event.get("end_reason") == "1":
                raise RuntimeError("Rally retirement completed the stage")
            seconds = float(event.get("time_72", "nan"))
            if (event.get("started") == "1" and event.get("ended") == "0" and
                    math.isfinite(seconds) and seconds > 0):
                attempt = dict(route=route, event_id=event["event_id"], race_serial=event["race_serial"])
        elif attempt and event.get("mode") == "17" and event.get("route") == "0":
            break
    else:
        raise RuntimeError("unfinished Rally stage did not return to native free roam")
    loaded = [e for e in events if e.get("event") == "dlc.rally.series_loaded"]
    if loaded:
        if (state_root is None or len(loaded) != 1 or
                sum(e.get("event") == "dlc.rally.series_retired" for e in events) != 1):
            raise RuntimeError("Rally retirement did not cancel its saved series attempt")
        path = active_rally_progress_path(events, state_root)
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        saved, rows = data.get("attempt", {}), data.get("series", [])
        sid = int(loaded[0]["series_id"])
        if (data.get("version") != 3 or sid not in range(1, 8) or
                [row.get("id") for row in rows] != list(range(1, 8)) or
                saved.get("series_id") != 0 or saved.get("completed") != 0 or
                saved.get("active") is not False or saved.get("seconds") != [0.0] * 4 or
                saved.get("total_seconds") != 0.0 or
                rows[sid - 1].get("completions") != int(loaded[0]["series_completions"]) or
                abs(rows[sid - 1].get("best_seconds", math.inf) - float(loaded[0]["best_seconds"])) > 0.000001):
            raise RuntimeError("Rally retirement changed its series result or kept an active attempt")
        if initial_progress and not any(
                all(data.get(key, []) == tomllib.loads(record.decode("utf-8")).get(key, [])
                    for key in ("stages", "series")) for record in initial_progress):
            raise RuntimeError("Rally retirement changed previously saved stage or series results")
        attempt.update(series_id=sid, path=str(path))
    return attempt


def rally_resume_summary(events: list[dict], state_root: Path, series_id: int, route: int,
                         initial_progress: list[bytes]) -> dict:
    if series_id not in range(1, 8) or route not in RALLY_SERIES_ROUTES[series_id - 1]:
        raise RuntimeError("invalid Rally resume route")
    completed = RALLY_SERIES_ROUTES[series_id - 1].index(route)
    loaded = [e for e in events if e.get("event") == "dlc.rally.series_loaded"]
    resumed = [e for e in events if e.get("event") == "dlc.rally.series_load" and e.get("resume") == "1"]
    if (len(loaded) != 1 or len(resumed) != 1 or
            loaded[0].get("active") != "1" or int(loaded[0]["completed"]) != completed or
            int(loaded[0]["series_id"]) != series_id or int(loaded[0]["next_route"]) != route or
            int(resumed[0]["route"]) != route or any(e.get("event") in
                ("dlc.rally.series_error", "dlc.rally.progress_error", "dlc.rally.stage_completed",
                 "dlc.rally.series_retired") for e in events)):
        raise RuntimeError("Rally resume did not load the saved incomplete attempt")
    previous = None
    for event in events[events.index(resumed[0]) + 1:]:
        if event.get("event") != "dlc.rally.race_trace":
            continue
        seconds = float(event.get("time_72", "nan"))
        if (event.get("route") != str(route) or event.get("event_id") != resumed[0]["event_id"] or
                event.get("mode") != "3" or event.get("started") != "1" or event.get("ended") != "0" or
                event.get("end_reason") != "0" or not event.get("car") or
                int(event.get("race_serial", 0)) <= 0 or not math.isfinite(seconds) or seconds <= 0):
            previous = None
            continue
        sample = (event.get("car"), event.get("race_serial"), seconds)
        if previous and sample[:2] == previous[:2] and seconds > previous[2]:
            break
        previous = sample
    else:
        raise RuntimeError("resumed Rally stage did not start and advance")
    path = active_rally_progress_path(events, state_root)
    if path.read_bytes() not in initial_progress:
        raise RuntimeError("Rally resume changed the saved attempt")
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    attempt = data.get("attempt", {})
    total = float(loaded[0]["total_seconds"])
    if (data.get("version") != 3 or attempt.get("series_id") != series_id or
            attempt.get("completed") != completed or attempt.get("active") is not True or
            not math.isfinite(total) or total < 0 or (completed == 0 and total != 0) or
            (completed > 0 and total <= 0) or
            abs(attempt.get("total_seconds", math.inf) - total) > 0.000001):
        raise RuntimeError("Rally resume changed the saved attempt")
    return dict(series_id=series_id, route=route, completed=completed, total_seconds=attempt["total_seconds"],
                event_id=resumed[0]["event_id"], race_serial=sample[1], path=str(path))


def rally_series_reload_summary(events: list[dict], state_root: Path, series_id: int,
                                initial_progress: list[bytes]) -> dict:
    loaded = [e for e in events if e.get("event") == "dlc.rally.series_loaded"]
    if (series_id not in range(1, 8) or len(loaded) != 1 or
            int(loaded[0]["series_id"]) != series_id or loaded[0].get("active") != "0" or
            int(loaded[0]["completed"]) != 4 or int(loaded[0]["next_route"]) != 0 or
            int(loaded[0]["series_completions"]) < 1 or any(e.get("event") in
                ("dlc.rally.stage_completed", "dlc.rally.series_error", "dlc.rally.progress_error",
                 "dlc.rally.series_retired") for e in events)):
        raise RuntimeError("completed Rally series was not reloaded without changes")
    path = active_rally_progress_path(events, state_root)
    if path.read_bytes() not in initial_progress:
        raise RuntimeError("Rally reload changed its progress record")
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    rows, attempt = data.get("series", []), data.get("attempt", {})
    if data.get("version") != 3 or [row.get("id") for row in rows] != list(range(1, 8)):
        raise RuntimeError("Rally reload has an invalid series record")
    series = rows[series_id - 1]
    total, best = float(loaded[0]["total_seconds"]), float(loaded[0]["best_seconds"])
    if (series["completions"] != int(loaded[0]["series_completions"]) or
            attempt.get("series_id") != series_id or attempt.get("completed") != 4 or
            attempt.get("active") is not False or
            not math.isfinite(total) or not math.isfinite(best) or total <= 0 or best <= 0 or
            abs(total - attempt["total_seconds"]) > 0.000001 or abs(best - series["best_seconds"]) > 0.000001):
        raise RuntimeError("Rally reload does not match the saved series")
    return dict(series_id=series_id, completions=series["completions"], best_seconds=series["best_seconds"],
                total_seconds=attempt["total_seconds"], path=str(path))


def rally_stage_reload_summary(events: list[dict], state: Path, route: int,
                               initial_progress: list[bytes]) -> dict:
    """Require a saved stage to load, run again and retain its earned record."""
    loaded = [e for e in events if e.get("event") == "dlc.rally.progress_loaded"]
    if (route not in RALLY_STAGE_ROUTES or len(loaded) != 1 or
            int(loaded[0]["route"]) != route or any(e.get("event") in
                ("dlc.rally.stage_completed", "dlc.rally.progress_error", "dlc.rally.series_error")
                for e in events)):
        raise RuntimeError("Rally stage did not reload without awards or errors")
    path = active_rally_progress_path(events, state)
    saved_bytes = path.read_bytes()
    current = [p.read_bytes() for name in ("user", "user-modded")
               for p in (state / name).glob("**/ForzaProfile/rally-progress.toml")]
    if saved_bytes not in initial_progress or sorted(current) != sorted(initial_progress):
        raise RuntimeError("Rally stage reload changed its earned records")
    data = tomllib.loads(saved_bytes.decode("utf-8"))
    rows = data.get("stages", [])
    expected = RALLY_STAGE_ROUTES[:21] if data.get("version") == 1 else RALLY_STAGE_ROUTES
    if data.get("version") not in (1, 2, 3) or [r.get("route") for r in rows] != list(expected):
        raise RuntimeError("Rally stage reload has an invalid ledger")
    row = next((r for r in rows if r["route"] == route), None)
    count, best = int(loaded[0]["completions"]), float(loaded[0]["best_seconds"])
    saved_best = float(row.get("best_seconds", math.nan)) if row else math.nan
    if (not row or count < 1 or not math.isfinite(best) or best <= 0 or
            not math.isfinite(saved_best) or row.get("completions") != count or abs(saved_best - best) > 1e-6 or
            int(loaded[0]["completed_stages"]) != sum(r["completions"] > 0 for r in rows)):
        raise RuntimeError("Rally stage reload does not match its saved count and best")
    previous = None
    for e in events:
        if e.get("event") != "dlc.rally.race_trace":
            continue
        seconds = float(e["time_72"])
        if (e.get("route") != str(route) or e.get("mode") != "3" or e.get("started") != "1" or
                e.get("ended") != "0" or e.get("end_reason") != "0" or not e.get("car") or
                int(e.get("event_id", 0)) <= 0 or int(e.get("race_serial", 0)) <= 0 or
                not math.isfinite(seconds) or seconds < 5):
            previous = None
            continue
        identity = (e["car"], e["event_id"], e["race_serial"])
        if previous and previous[0] == identity and seconds > previous[1]:
            return dict(route=route, completions=count, best_seconds=row["best_seconds"],
                        race_serial=int(e["race_serial"]), earned_records_preserved=True, path=str(path))
        previous = (identity, seconds)
    raise RuntimeError("Rally stage reload lacks an advancing native race")


def require_free_roam_capture(events: list[dict], name: str) -> None:
    captures = [event for event in events if event.get("event") == "fh1.render_test.capture"
                and event.get("name") == name]
    if len(captures) != 1 or captures[0].get("game_mode") != "17":
        raise RuntimeError(f"capture {name} did not return to native free roam")


def rally_audio_summary(events: list[dict], output: Path, language: str) -> dict:
    """Qualify one native cue start plus captured mix; not speech or route timing."""
    if language not in {"EN", "MX"}:
        raise ValueError("Rally audio probe language must be EN or MX")
    names = ("bank_loaded", "cue_created", "play")
    stages = []
    for name in names:
        matches = [(i, e) for i, e in enumerate(events)
                   if e.get("event") == f"dlc.rally.audio_probe_{name}"]
        if len(matches) != 1 or matches[0][1].get("language") != language:
            raise RuntimeError(f"Rally audio {name} missing or wrong language")
        stages.append(matches[0])
    captures = [(i, e) for i, e in enumerate(events)
                if e.get("event") == "dlc.rally.audio_capture_saved"]
    if len(captures) != 1 or not stages[0][0] < stages[1][0] < stages[2][0] < captures[0][0]:
        raise RuntimeError("Rally audio observations missing or out of order")
    bank, cue, play = (e for _, e in stages)
    capture = captures[0][1]
    expected_bank = f"Game:\\Media\\Audio\\VO\\CoDriver_{language}.fev"
    if (bank.get("bank") != expected_bank or play.get("bank") != expected_bank or
        play.get("group") != f"CoDriver_{language}/CoDriver/Turns/Right" or
        play.get("cue") != "MedRight" or play.get("project") != bank.get("project") or
        play.get("handle") != cue.get("handle")):
        raise RuntimeError("Rally audio native bank/cue mismatch")
    if any(int(play.get(field, "0"), 16) == 0 for field in ("project", "handle", "voice")):
        raise RuntimeError("Rally audio native voice did not start")
    return dict(language=language, cue=play["cue"], voice=play["voice"],
                **rally_pcm_summary(capture, output), scope="single_cue_and_mix")


def rally_pcm_summary(capture: dict, output: Path) -> dict:
    """Validate the bounded native mix shared by single-cue and pace probes."""
    path = output / "rally-audio-probe.wav"
    if (Path(capture.get("path", "")).resolve() != path.resolve() or
        capture.get("source") != "native_pre_device_pcm"):
        raise RuntimeError("Rally audio capture path or source mismatch")
    with wave.open(str(path), "rb") as recording:
        if (recording.getframerate(), recording.getnchannels(), recording.getsampwidth(),
            recording.getnframes()) != (48000, 6, 2, 384000):
            raise RuntimeError("Rally audio capture format or duration mismatch")
        pcm = array.array("h", recording.readframes(384000))
    if sys.byteorder != "little":
        pcm.byteswap()
    if len(pcm) != 2304000:
        raise RuntimeError("Rally audio capture is truncated")
    rms = math.sqrt(sum(float(sample) ** 2 for sample in pcm) / len(pcm)) / 32767
    peak = max(abs(sample) for sample in pcm) / 32767
    if not rms > 0.0001:
        raise RuntimeError("Rally audio captured only silence")
    for field, value in (("rms", rms), ("peak", peak)):
        logged = float(capture.get(field, "nan"))
        if not math.isfinite(logged) or abs(logged - value) > 0.0001:
            raise RuntimeError(f"Rally audio capture {field} mismatch")
    return dict(path=str(path),
                duration_seconds=8, channels=6, frequency=48000, rms=rms, peak=peak,
                source="native_pre_device_pcm")


def rally_pace_summary(events: list[dict], state: Path, language: str, output: Path) -> dict:
    """Check native serialized phrases against the run's owned metadata."""
    if language not in {"EN", "MX"}:
        raise ValueError("Rally pace probe language must be EN or MX")
    adapter = "cache/rally_adapter" if any(
        event.get("event") == "dlc.rally.overlay_mounted" for event in events) else "mods/rally_stage_probe"
    calls = tomllib.loads((state / adapter / "rally-pace.toml").read_text(encoding="utf-8"))["calls"]
    loaded = [event for event in events if event.get("event") == "dlc.rally.pace_loaded"]
    if len(loaded) != 1 or loaded[0].get("language") != language:
        raise RuntimeError("Rally pace metadata missing or wrong language")
    active = None
    completed = set()
    seen = set()
    last_call = None
    next_sample = 0
    plays = 0
    ready = False
    for event in events:
        name = event.get("event")
        if name == "dlc.rally.pace_loaded":
            ready = True
        if name == "dlc.rally.pace_error":
            raise RuntimeError(f"Rally pace error: {event.get('error')}")
        if name == "dlc.rally.pace_cancelled":
            active = last_call = None
            next_sample = 0
            seen.clear()
        if name == "dlc.rally.pace_play":
            if not ready:
                raise RuntimeError("Rally pace play before metadata load")
            index, sample_index = int(event["call_index"]), int(event["sample_index"])
            if not 0 <= index < len(calls) or not 0 <= sample_index < len(calls[index]["samples"]):
                raise RuntimeError("Rally pace metadata index mismatch")
            call, sample = calls[index], calls[index]["samples"][sample_index]
            identity = (int(event["race_serial"]), index)
            if identity != last_call:
                if next_sample or identity in seen:
                    raise RuntimeError("Rally pace phrase interrupted or repeated")
                last_call = identity
            if (active is not None or sample_index != next_sample or event.get("language") != language or
                    int(event["route"]) != call["route"] or identity[0] <= 0 or
                    not math.isfinite(float(event["seconds"])) or float(event["seconds"]) < 0 or
                    event.get("group") != f"CoDriver_{language}/{sample['group']}" or
                    event.get("cue") != sample["cue"] or event.get("icon") != sample["icon"] or
                    any(int(event.get(field, "0"), 16) == 0 for field in ("handle", "voice"))):
                raise RuntimeError("Rally pace native voice, mapping or phrase order mismatch")
            active = (index, sample_index)
            plays += 1
        if name == "dlc.rally.pace_finished":
            identity = (int(event["call_index"]), int(event["sample_index"]))
            if active != identity:
                raise RuntimeError("Rally pace finish without matching voice")
            active = None
            next_sample += 1
            if next_sample == len(calls[identity[0]]["samples"]):
                completed.add(last_call)
                seen.add(last_call)
                next_sample = 0
    if len(completed) < 2:
        raise RuntimeError("Rally pace requires at least two complete authored phrases")
    captures = [(i, event) for i, event in enumerate(events) if event.get("event") == "dlc.rally.audio_capture_saved"]
    first_play = next(i for i, event in enumerate(events) if event.get("event") == "dlc.rally.pace_play")
    if len(captures) != 1 or captures[0][0] <= first_play:
        raise RuntimeError("Rally pace PCM capture missing or out of order")
    return dict(language=language, native_plays=plays, completed_phrases=len(completed),
                mix=rally_pcm_summary(captures[0][1], output),
                scope="private_solo_native_phrase_order", speech_intelligibility=False,
                rewind_qualified=False, hud_qualified=False)


def rally_default_pace_summary(events: list[dict], state: Path, language: str) -> dict:
    """Reject private scheduler overrides, mod isolation and the single-cue probe."""
    rally_builtin_summary(events, state)
    loaded = [event for event in events if event.get("event") == "dlc.rally.pace_loaded"]
    if (len(loaded) != 1 or loaded[0].get("language") != language or
            loaded[0].get("source") != "owned_content" or
            any(event.get("event") == "dlc.rally.audio_probe_play" for event in events)):
        raise RuntimeError("Rally co-driver did not activate from owned content and console locale")
    return dict(default_enabled=True, language_source="console_locale", owned_overlay=True,
                **rally_audio_owner_summary(events))


def rally_audio_owner_summary(events: list[dict]) -> dict:
    """Require cue lifetimes to run on the title's native audio update thread."""
    installed = [e for e in events if e.get("event") == "dlc.rally.pace_update_installed"]
    updated = [e for e in events if e.get("event") == "dlc.rally.pace_update"]
    if (len(installed) != 1 or len(updated) != 1 or
            installed[0].get("owner") != "native_audio_update" or
            any(e.get("method") != "82BB5918" for e in [installed[0], updated[0]]) or
            not updated[0].get("tid") or int(updated[0].get("manager", "0"), 16) == 0):
        raise RuntimeError("Rally native audio update owner missing or invalid")
    thread = updated[0]["tid"]
    operations = {"dlc.rally.pace_loaded", "dlc.rally.pace_play", "dlc.rally.pace_finished",
                  "dlc.rally.pace_cancelled", "dlc.rally.pace_resumed",
                  "dlc.rally.audio_cue_cleanup", "dlc.rally.audio_cue_methods"}
    if any(e.get("tid") != thread for e in events if e.get("event") in operations):
        raise RuntimeError("Rally cue lifetime operation ran outside the native audio update thread")
    return dict(audio_owner="native_audio_update", audio_thread=thread)


def rally_pace_suspend_summary(events: list[dict]) -> dict:
    """Require a live voice interruption, frozen race clock and clean resume."""
    active = None
    seen = set()
    for index, event in enumerate(events):
        name = event.get("event")
        if name == "dlc.rally.pace_play":
            active = event
            seen.add((event["race_serial"], event["route"], event["call_index"]))
        elif name == "dlc.rally.pace_finished":
            active = None
        elif name == "dlc.rally.pace_cancelled":
            if event.get("reason") != "pose_suspended" or event.get("had_voice") != "1" or active is None:
                active = None
                continue
            resumed = next((i for i in range(index + 1, len(events))
                            if events[i].get("event") == "dlc.rally.pace_resumed"), None)
            if resumed is None:
                raise RuntimeError("Rally pace suspension did not resume")
            resume = events[resumed]
            identity = (event["race_serial"], event["route"])
            seconds = float(event["seconds"])
            resumed_seconds = float(resume["seconds"])
            if ((active["race_serial"], active["route"]) != identity or
                (resume["race_serial"], resume["route"]) != identity or
                not math.isfinite(seconds) or seconds < 0 or not math.isfinite(resumed_seconds) or
                abs(resumed_seconds - seconds) > 0.25):
                raise RuntimeError("Rally pace suspension changed race or advanced its clock")
            gap = events[index + 1:resumed]
            frozen = [e for e in gap if e.get("event") == "dlc.rally.race_trace"]
            if len(frozen) < 3 or any((e.get("race_serial"), e.get("route")) != identity or
                    not math.isfinite(float(e["time_72"])) or
                    abs(float(e["time_72"]) - seconds) > 0.001 for e in frozen):
                raise RuntimeError("Rally pace suspension lacks a frozen race clock")
            if any(e.get("event") == "dlc.rally.pace_play" or
                   (e.get("event") == "dlc.rally.pace_hud" and e.get("visible") == "1") for e in gap):
                raise RuntimeError("Rally pace suspension retained speech or icons")
            if not any(e.get("event") == "dlc.rally.pace_hud" and e.get("visible") == "0" for e in gap):
                raise RuntimeError("Rally pace suspension did not clear the HUD")
            later = [e for e in events[resumed + 1:] if e.get("event") == "dlc.rally.pace_play"]
            if not later or any((e["race_serial"], e["route"]) != identity or
                    (e["race_serial"], e["route"], e["call_index"]) in seen for e in later):
                raise RuntimeError("Rally pace resume missing or replayed an earlier gate")
            return dict(scope="private_solo_active_phrase_pause", route=int(identity[1]),
                        race_serial=int(identity[0]), interrupted_call=int(active["call_index"]),
                        frozen_observations=len(frozen), seconds=seconds,
                        hud_cleared=True, visual_hud_qualified=False)
    raise RuntimeError("Rally pace requires suspension during an active native phrase")


def rally_pace_retry_summary(events: list[dict], state: Path, initial_progress: list[bytes]) -> dict:
    """Require a native pre-race reset and re-armed phrase in the same stage."""
    if any(e.get("event") in ("dlc.rally.stage_completed", "dlc.rally.progress_error",
                              "dlc.rally.series_error") for e in events):
        raise RuntimeError("Rally retry awarded a finish or reported a progress error")
    starts = [(i, e) for i, e in enumerate(events) if e.get("event") == "dlc.rally.pace_play"
              and e.get("call_index") == "0" and e.get("sample_index") == "0"]
    if len(starts) != 2:
        raise RuntimeError("Rally retry requires the first phrase in two attempts")
    (before, first), (after, second) = starts
    if first["route"] != second["route"] or any(first[key] != second[key] for key in ("group", "cue", "icon")):
        raise RuntimeError("Rally retry changed stage or authored first phrase")
    gap = events[before + 1:after]
    resets = [e for e in gap if e.get("event") == "dlc.rally.pace_cancelled" and
              e.get("reason") == "race_reset" and e.get("route") == second["route"] and
              e.get("race_serial") == second["race_serial"] and e.get("seconds") == "0.000000"]
    prepared = [e for e in gap if e.get("event") == "dlc.rally.race_trace" and
                e.get("route") == second["route"] and e.get("race_serial") == second["race_serial"] and
                e.get("started") == "0" and e.get("ended") == "0" and float(e["time_72"]) == 0]
    if not resets or len(prepared) < 2:
        raise RuntimeError("Rally retry lacks a native zero-clock pre-race phase")
    later = [e for e in events[after + 1:] if e.get("event") == "dlc.rally.pace_play"]
    if not any(e.get("call_index") != "0" and e.get("route") == second["route"] and
               e.get("race_serial") == second["race_serial"] for e in later):
        raise RuntimeError("Rally retry did not continue to later authored gates")
    saved = [p.read_bytes() for name in ("user", "user-modded")
             for p in (state / name).glob("**/ForzaProfile/rally-progress.toml")]
    if sorted(saved) != sorted(initial_progress):
        raise RuntimeError("Rally retry changed earned stage records")
    return dict(scope="private_solo_native_restart", route=int(second["route"]),
                first_car_serial=int(first["race_serial"]), retried_car_serial=int(second["race_serial"]),
                serial_reused=first["race_serial"] == second["race_serial"],
                pre_race_observations=len(prepared), earned_records_preserved=True,
                completed_retry_qualified=False)


def run(args: argparse.Namespace) -> dict[str, object]:
    scenario = args.scenario.resolve()
    scenario_lines = scenario.read_text(encoding="utf-8").splitlines()
    audio_languages = [line.split()[2] for line in scenario_lines if line.startswith("# expect-rally-audio ")]
    if len(audio_languages) > 1 or any(language not in {"EN", "MX"} for language in audio_languages):
        raise ValueError("expect-rally-audio requires one language: EN or MX")
    pace_languages = [line.split()[2] for line in scenario_lines if line.startswith("# expect-rally-pace ")]
    default_pace_languages = [line.split()[2] for line in scenario_lines if line.startswith("# expect-rally-pace-default ")]
    pace_languages += default_pace_languages
    if (len(pace_languages) > 1 or any(language not in {"EN", "MX"} for language in pace_languages) or
            (pace_languages and audio_languages)):
        raise ValueError("expect-rally-pace requires one EN or MX language without expect-rally-audio")
    pace_suspend = "# expect-rally-pace-suspend" in scenario_lines
    if pace_suspend and not pace_languages:
        raise ValueError("expect-rally-pace-suspend requires expect-rally-pace")
    pace_retry = "# expect-rally-pace-retry" in scenario_lines
    if pace_retry and not pace_languages:
        raise ValueError("expect-rally-pace-retry requires expect-rally-pace")
    series = [int(line.split()[2]) for line in scenario_lines if line.startswith("# expect-rally-series ")]
    reloads = [int(line.split()[2]) for line in scenario_lines if line.startswith("# expect-rally-series-reload ")]
    stage_reloads = [int(line.split()[2]) for line in scenario_lines if line.startswith("# expect-rally-stage-reload ")]
    if len(stage_reloads) > 1 or any(route not in RALLY_STAGE_ROUTES for route in stage_reloads):
        raise ValueError("expect-rally-stage-reload requires one Rally stage route")
    if len(reloads) > 1 or any(value not in range(1, 8) for value in reloads):
        raise ValueError("expect-rally-series-reload requires one series ID from 1 to 7")
    resumes = [tuple(map(int, line.split()[2:])) for line in scenario_lines
               if line.startswith("# expect-rally-resume ")]
    if len(resumes) > 1 or any(len(value) != 2 or value[0] not in range(1, 8) or
            value[1] not in RALLY_SERIES_ROUTES[value[0] - 1] for value in resumes):
        raise ValueError("expect-rally-resume requires a series ID and one of its stage routes")
    if len(series) > 1 or any(value not in range(1, 8) for value in series):
        raise ValueError("expect-rally-series requires one series ID from 1 to 7")
    expect_rally_return_entry = "# expect-rally-return-entry" in scenario_lines
    if expect_rally_return_entry and not series:
        raise ValueError("expect-rally-return-entry requires a full Rally series")
    transitions = [tuple(map(int, line.split()[2:])) for line in scenario_lines
                   if line.startswith("# expect-rally-transition ")]
    retirements = [int(line.split()[2]) for line in scenario_lines
                   if line.startswith("# expect-rally-retirement ")]
    if any(route not in RALLY_STAGE_ROUTES for route in retirements):
        raise ValueError("expect-rally-retirement requires a Rally stage route")
    for transition in transitions:
        if (len(transition) != 2 or any(route not in RALLY_STAGE_ROUTES for route in transition) or
                transition[0] == transition[1]):
            raise ValueError("expect-rally-transition requires two distinct Rally stage routes")
    expect_rally_progress = bool(series or transitions) or "# expect-rally-progress" in scenario_lines
    expect_rally_builtin = "# expect-rally-builtin" in scenario_lines
    expect_rally_normal_entry = "# expect-rally-normal-entry" in scenario_lines
    expect_rally_car_database = "# expect-rally-car-database" in scenario_lines
    # Trace-only: record the native entitlement cache and car rows without
    # the base adapter's Rally assertions (used on the v4 build).
    dlc_car_trace = "# dlc-car-trace" in scenario_lines
    # Optional car list for that trace: "# dlc-car-ids 1103,1131" (Rally's
    # roster when absent).
    dlc_car_ids = ",".join(line.split(None, 2)[2].replace(" ", "") for line in scenario_lines
                           if line.startswith("# dlc-car-ids "))
    expect_rally_entry_positions = "# expect-rally-entry-positions" in scenario_lines
    expect_rally_service_guard = "# expect-rally-service-entry-guard" in scenario_lines
    expect_rally_test_ai = "# expect-rally-test-ai-driver" in scenario_lines
    entries = [int(line.split()[2]) for line in scenario_lines if line.startswith("# expect-rally-entry ")]
    if len(entries) > 1 or any(id not in range(1, 8) for id in entries):
        raise ValueError("expect-rally-entry requires one championship from 1 to 7")
    hub_ui_entries = [int(line.split()[2]) for line in scenario_lines if line.startswith("# expect-rally-hub-ui ")]
    if hub_ui_entries and (len(hub_ui_entries) != 1 or hub_ui_entries != entries):
        raise ValueError("expect-rally-hub-ui must match the single Rally entry championship")
    hub_resumes = [tuple(map(int, line.split()[2:])) for line in scenario_lines
                   if line.startswith("# expect-rally-hub-resume ")]
    if hub_resumes and (len(hub_resumes) != 1 or hub_resumes != resumes):
        raise ValueError("expect-rally-hub-resume must match the single Rally resume")
    hub_retirements = [int(line.split()[2]) for line in scenario_lines
                       if line.startswith("# expect-rally-hub-retirement ")]
    if (len(hub_retirements) > 1 or any(id not in range(1, 8) for id in hub_retirements) or
            (hub_retirements and (entries or resumes or retirements))):
        raise ValueError("expect-rally-hub-retirement requires one championship without a race entry")
    expect_rally_normal_entry = expect_rally_normal_entry or expect_rally_car_database or bool(entries or hub_resumes or hub_retirements)
    if expect_rally_builtin and expect_rally_normal_entry:
        raise ValueError("normal Rally entry cannot use the private built-in probe")
    expect_race_finish = expect_rally_progress or "# expect-race-finish" in scenario_lines
    state_root = args.state_root.resolve()
    (
        captures,
        stop,
        image_limits,
        performance_limits,
        distinct_presentation_min,
        simulation_time_limits,
        capture_mae_minimums,
        race_hud_captures,
        race_hud_any_groups,
    ) = (
        parse_scenario(scenario)
    )
    if args.null_gpu and (args.baseline_dir or args.record_baseline):
        raise ValueError("--null-gpu runs have no images to compare or record")
    if args.null_gpu:
        image_limits = {}
    require_image_reference(image_limits, args.baseline_dir, args.record_baseline)
    if args.require_zero_shader_misses and not (
        args.shader_pack and args.shader_capture_dir
    ):
        raise ValueError(
            "--require-zero-shader-misses requires --shader-pack and "
            "--shader-capture-dir"
        )
    if args.disc_shader_corpus_dir and not args.shader_capture_dir:
        raise ValueError(
            "--disc-shader-corpus-dir requires --shader-capture-dir"
        )
    disc_shader_corpus_dir = (
        resolve_disc_shader_corpus(args.disc_shader_corpus_dir)
        if args.disc_shader_corpus_dir
        else None
    )
    profiles = list((state_root / "user").glob("**/ForzaProfile/ForzaProfile"))
    if not profiles and not args.fresh_profile:
        raise ValueError(f"no FH1 profile below {state_root / 'user'}")
    output = (
        args.output.resolve()
        if args.output
        else (
            Path(".local/native-renderer/automated")
            / f"{scenario.stem}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
        ).resolve()
    )
    if output.exists():
        raise ValueError(f"refusing stale output directory: {output}")

    run_state_root = output.with_name(f"{output.name}.state")
    if run_state_root.exists():
        raise ValueError(f"refusing stale isolated state directory: {run_state_root}")
    prepare_isolated_state(state_root, run_state_root)
    initial_rally_progress = [path.read_bytes() for name in ("user", "user-modded")
                             for path in (run_state_root / name).glob("**/ForzaProfile/rally-progress.toml")] if resumes or reloads or stage_reloads or retirements or hub_retirements or expect_rally_car_database or pace_retry else []
    seeded_shader_storage = (
        seed_fh1_shader_storage(state_root, run_state_root)
        if args.seed_shader_storage or args.shader_pack
        else []
    )
    seeded_pipeline_prewarm = (
        seed_fh1_pipeline_prewarm(state_root, run_state_root)
        if args.seed_pipeline_prewarm
        else None
    )
    seeded_vulkan_shader_storage = (
        seed_vulkan_shader_storage(state_root, run_state_root)
        if args.seed_vulkan_shader_storage
        else []
    )
    # Each pack is staged under its own name, so packs for several scales can
    # be present for a run that switches scale.
    staged_shader_packs = []
    for shader_pack in args.shader_pack or []:
        stage = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("native-shader-pack.py")),
                "stage",
                str(shader_pack.resolve()),
                "--state-root",
                str(run_state_root),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        staged_shader_packs.append(Path(json.loads(stage.stdout)["destination"]))
    staged_shader_pack = staged_shader_packs[0] if staged_shader_packs else None

    logs = run_state_root / "logs"
    previous_logs = set(logs.glob("*.jsonl")) if logs.exists() else set()
    runtime_log = logs / "runtime.log"
    runtime_offset = runtime_log.stat().st_size if runtime_log.exists() else 0
    timeout = args.timeout or max(180, stop // 30 + 180)
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(Path(__file__).with_name("launch-preview.ps1")),
        "-StateRoot",
        str(run_state_root),
        "-RenderTestScript",
        str(scenario),
        "-RenderTestOutput",
        str(output),
        "-RenderTestTimeoutSeconds",
        str(timeout),
    ]
    if args.configuration:
        command += ["-Configuration", args.configuration]
    if args.game_root:
        command += ["-GameRoot", str(args.game_root.resolve())]
    if args.build_directory:
        command += ["-BuildDirectory", str(args.build_directory.resolve())]
    if args.hidden:
        command.append("-Hidden")
    if expect_rally_normal_entry:
        command.append("-VerifyRally")
    if args.collect_pass_inventory:
        command.append("-CollectFh1PassInventory")
    if args.nsight_gpu_trace:
        if not args.nsight_output_dir:
            raise SystemExit("--nsight-output-dir is required with --nsight-gpu-trace")
        command += [
            "-NsightCommand", str(args.nsight_gpu_trace),
            "-NsightOutputDir", str(args.nsight_output_dir.resolve()),
            "-NsightStartAfterFrames", str(args.nsight_start_after_frames),
            "-NsightFrames", str(args.nsight_frames),
        ]
    if args.shader_capture_dir:
        command.extend(
            ["-ShaderCaptureDir", str(args.shader_capture_dir.resolve())]
        )
    if disc_shader_corpus_dir:
        command.extend(
            ["-DiscShaderCorpusDir", str(disc_shader_corpus_dir)]
        )
    if args.include_opening_movies:
        command.append("-RenderTestIncludeOpeningMovies")
    game_arguments = list(args.game_argument)
    # Seeds are fixed snapshots: keep their car cards as saved (the routes
    # through car select wait for the title to open them) unless a test asks
    # for the start-up card repair.
    if not any("pinyon_shift_repair_car_cards" in argument for argument in game_arguments):
        game_arguments.append("--pinyon_shift_repair_car_cards=false")
    if args.null_gpu:
        game_arguments.append("--gpu_backend=null")
    if args.host_cpus:
        game_arguments.append(f"--host_cpu_simulation={args.host_cpus}")
    command.extend(["-GameArgumentsJson", json.dumps(game_arguments)])
    command.append("-Json")
    environment = dict(os.environ)
    if expect_rally_car_database or dlc_car_trace:
        environment["PINYON_SHIFT_DLC_TRACE"] = "1"
    else:
        environment.pop("PINYON_SHIFT_DLC_TRACE", None)
    if dlc_car_ids:
        environment["PINYON_SHIFT_DLC_TRACE_CARS"] = dlc_car_ids
    else:
        environment.pop("PINYON_SHIFT_DLC_TRACE_CARS", None)
    if hub_ui_entries or hub_resumes or hub_retirements:
        environment.pop("PINYON_SHIFT_RALLY_HUB_PROBE", None)
    if expect_rally_builtin:
        environment["PINYON_SHIFT_RALLY_BUILTIN_PROBE"] = "1"
    elif expect_rally_normal_entry:
        environment.pop("PINYON_SHIFT_RALLY_BUILTIN_PROBE", None)
    if entries or expect_race_finish or retirements or hub_retirements or resumes or reloads or stage_reloads or audio_languages or pace_languages or expect_rally_service_guard:
        environment["PINYON_SHIFT_RALLY_TRACE"] = "1"
    if expect_rally_progress or retirements or hub_retirements or resumes or reloads or stage_reloads or audio_languages or pace_languages:
        environment["PINYON_SHIFT_RALLY_PROGRESS"] = "1"
    if audio_languages:
        environment["PINYON_SHIFT_RALLY_AUDIO_PROBE"] = audio_languages[0]
    if pace_languages:
        if default_pace_languages:
            environment.pop("PINYON_SHIFT_RALLY_PACE_PROBE", None)
        else:
            environment["PINYON_SHIFT_RALLY_PACE_PROBE"] = pace_languages[0]
        environment["PINYON_SHIFT_RALLY_AUDIO_PROBE"] = pace_languages[0]
    with LowSpecSimulation(args) as simulation:
        process = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout + 30, check=False,
            env=environment
        )
    if process.returncode:
        raise RuntimeError(
            f"FH1 render test failed ({process.returncode}):\n"
            f"{process.stdout}\n{process.stderr}"
        )
    new_logs = sorted(set(logs.glob("*.jsonl")) - previous_logs)
    if len(new_logs) != 1:
        raise RuntimeError(f"expected one new JSONL session, found {len(new_logs)}")
    event_log = new_logs[0]
    events = load_events(event_log)
    failures = [
        event for event in events
        if str(event.get("event", "")).endswith(".failure")
        or str(event.get("event", "")) in {"process.crash", "device.lost"}
    ]
    if failures:
        raise RuntimeError(f"diagnostic failure: {failures[0]}")
    for line in scenario_lines:
        if line.startswith("# expect-freeroam-return "):
            require_free_roam_capture(events, line.split()[2])
    race_finish = race_finish_summary(events) if expect_race_finish else None
    rally_progress = rally_progress_summary(events, run_state_root, race_finish) if expect_rally_progress and not series else None
    rally_series = rally_series_summary(events, run_state_root, series[0]) if series else None
    rally_return_entry = rally_return_entry_summary(events) if expect_rally_return_entry else None
    rally_audio = rally_audio_summary(events, output, audio_languages[0]) if audio_languages else None
    rally_pace = rally_pace_summary(events, run_state_root, pace_languages[0], output) if pace_languages else None
    if default_pace_languages:
        rally_pace |= rally_default_pace_summary(events, run_state_root, pace_languages[0])
    rally_pace_suspend = rally_pace_suspend_summary(events) if pace_suspend else None
    rally_pace_retry = rally_pace_retry_summary(events, run_state_root, initial_rally_progress) if pace_retry else None
    rally_transitions = [rally_transition_summary(events, first, following)
                         for first, following in transitions]
    rally_retirements = [rally_retirement_summary(events, route, run_state_root, initial_rally_progress) for route in retirements]
    rally_resumes = [rally_resume_summary(events, run_state_root, sid, route, initial_rally_progress)
                    for sid, route in resumes]
    rally_reloads = [rally_series_reload_summary(events, run_state_root, sid, initial_rally_progress) for sid in reloads]
    rally_stage_reloads = [rally_stage_reload_summary(events, run_state_root, route, initial_rally_progress)
                          for route in stage_reloads]
    rally_builtin = rally_builtin_summary(events, run_state_root) if expect_rally_builtin else None
    rally_normal_entry = rally_normal_entry_summary(events, run_state_root) if expect_rally_normal_entry else None
    rally_service_guard = rally_service_entry_guard_summary(events) if expect_rally_service_guard else None
    rally_test_ai = rally_test_ai_driver_summary(events, "# expect-rally-test-ai-release" in scenario_lines) if expect_rally_test_ai or any(
        e.get("event") == "fh1.render_test.rally_ai_driver" for e in events) else None
    rally_entry_positions = rally_entry_positions_summary(events, run_state_root) if expect_rally_entry_positions else None
    rally_car_database = rally_car_database_summary(events, run_state_root, initial_rally_progress) if expect_rally_car_database else None
    rally_entries = [rally_entry_summary(events, run_state_root, id) for id in entries]
    rally_hub_ui = [rally_hub_ui_summary(events, run_state_root, id) for id in hub_ui_entries]
    rally_hub_resumes = [rally_hub_resume_summary(events, run_state_root, sid, route, initial_rally_progress)
                         for sid, route in hub_resumes]
    rally_hub_retirements = [rally_hub_retirement_summary(events, run_state_root, sid, initial_rally_progress)
                             for sid in hub_retirements]
    shader_capture = shader_capture_summary(
        events, args.require_zero_shader_misses
    )
    by_name: dict[str, list[dict[str, object]]] = {}
    for event in events:
        by_name.setdefault(str(event.get("event", "")), []).append(event)
    configured = by_name.get("fh1.render_test.configured", [])
    completed = by_name.get("fh1.render_test.complete", [])
    captured_events = by_name.get("fh1.render_test.capture", [])
    if len(configured) != 1 or len(completed) != 1:
        raise RuntimeError("render test did not configure and complete exactly once")
    if completed[0].get("captures") != str(len(captures)):
        raise RuntimeError("render test completed with missing captures")
    if len(captured_events) != len(captures):
        raise RuntimeError("capture event count does not match the scenario")
    expected_captures = {(str(frame), name) for frame, name in captures}
    observed_captures = {
        (str(event.get("frame")), str(event.get("name")))
        for event in captured_events
    }
    if observed_captures != expected_captures:
        raise RuntimeError("capture events do not match requested frames and names")
    runtime_slice = ""
    if runtime_log.exists():
        with runtime_log.open("rb") as stream:
            stream.seek(runtime_offset)
            runtime_slice = stream.read().decode("utf-8", errors="replace")
    lowered = runtime_slice.lower()
    forbidden = (
        "device_removed",
        "device_hung",
        "device_reset",
        "device removed",
        "pipeline creation failed",
        "resource state warning",
        "tdr",
        "[critical] [gpu]",
        "[error] [gpu]",
    )
    hit = next((pattern for pattern in forbidden if pattern in lowered), None)
    if hit:
        raise RuntimeError(f"renderer log contains forbidden failure: {hit}")
    pass_families_by_id = {}
    for match in PASS_FAMILY.finditer(runtime_slice):
        family = {
            key: (
                value or None
                if key
                in {"family", "attachment", "first_family", "first_draw", "copy"}
                else int(value) if value is not None else None
            )
            for key, value in match.groupdict().items()
        }
        previous = pass_families_by_id.get(family["family"])
        if previous is None or family["samples"] >= previous["samples"]:
            pass_families_by_id[family["family"]] = family
    pass_families = sorted(
        pass_families_by_id.values(),
        key=lambda family: family["total_ns"],
        reverse=True,
    )

    image_results = []
    captured_by_key = {
        (str(event.get("frame")), str(event.get("name"))): event
        for event in captured_events
    }
    headless = args.null_gpu
    for frame, name in captures:
        event = captured_by_key[(str(frame), name)]
        if headless:
            # The null GPU backend draws nothing; the capture marks the frame.
            summary = {"name": name, "image": None}
        else:
            summary = ppm_summary(output / f"{name}.ppm")
        summary["frame"] = frame
        summary["game_mode"] = int(event.get("game_mode", "0"))
        if event.get("vehicle_pose_valid") == "1":
            summary["vehicle_pose"] = {
                axis: float(event[f"vehicle_{axis}"]) for axis in ("x", "y", "z")
            }
        image_results.append(summary)

    capture_mae = []
    if headless:
        capture_mae_minimums = []
        race_hud_captures = set()
        race_hud_any_groups = []
    for first, second, minimum in capture_mae_minimums:
        actual = compare_capture_mae(output, first, second)
        if actual < minimum:
            raise RuntimeError(
                f"captures {first} and {second} differ by only {actual:.3f} MAE "
                f"(minimum {minimum:.3f})"
            )
        capture_mae.append(
            {"first": first, "second": second, "minimum": minimum, "actual": actual}
        )

    race_hud = {
        name: race_hud_summary(output / f"{name}.ppm")
        for name in sorted(race_hud_captures)
    }
    for names in race_hud_any_groups:
        name, summary = first_race_hud_summary(output, names)
        race_hud[name] = summary

    perf_csv = event_log.with_suffix(".perf.csv")
    perf = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("summarize-performance.py")),
            str(perf_csv),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    performance = json.loads(perf.stdout)
    if performance_limits:
        median_max, present_min, simulation_min, simulation_max = performance_limits
        median = performance["frames"]["frame_time_us"]["median"]
        cadence = performance["presentation"]["cadence_hz"]
        present = cadence["present"]
        simulation = cadence["simulation_tick"]
        if median > median_max:
            raise RuntimeError(f"median frame time {median} us exceeds {median_max}")
        if present < present_min:
            raise RuntimeError(f"present cadence {present} Hz is below {present_min}")
        if not simulation_min <= simulation <= simulation_max:
            raise RuntimeError(
                f"simulation cadence {simulation} Hz is outside "
                f"{simulation_min}..{simulation_max}"
            )
    if distinct_presentation_min is not None:
        presentation = performance.get("presentation")
        if not presentation:
            raise RuntimeError("missing presentation telemetry")
        counters = presentation["counters"]
        distinct_count = max(
            0, counters["present_count"] - counters["duplicate_present_count"]
        )
        duration = performance["frames"]["measured_duration_seconds"]
        distinct_hz = distinct_count / duration
        if distinct_hz < distinct_presentation_min:
            raise RuntimeError(
                f"distinct presentation cadence {distinct_hz:.3f} Hz is below "
                f"{distinct_presentation_min}"
            )
    if simulation_time_limits is not None:
        simulation_time = performance.get("presentation", {}).get(
            "simulation_time"
        )
        if not simulation_time:
            raise RuntimeError("missing title simulation-time telemetry")
        minimum_ratio, maximum_ratio, maximum_invalid = simulation_time_limits
        ratio = simulation_time["wall_time_ratio"]
        invalid = simulation_time["invalid_deltas"]
        if not minimum_ratio <= ratio <= maximum_ratio:
            raise RuntimeError(
                f"title simulation-time ratio {ratio} is outside "
                f"{minimum_ratio}..{maximum_ratio}"
            )
        if invalid > maximum_invalid:
            raise RuntimeError(
                f"invalid title simulation deltas {invalid} exceed "
                f"{maximum_invalid}"
            )

    comparisons = []
    if args.baseline_dir:
        baseline_dir = args.baseline_dir.resolve()
        compare = Path(__file__).with_name("compare-native-renderer-images.py")
        comparison_names = image_limits or {
            name: DEFAULT_IMAGE_LIMITS for _, name in captures
        }
        for name, limits in comparison_names.items():
            comparison_path = output / f"{name}.comparison.json"
            comparison = subprocess.run(
                [
                    sys.executable,
                    str(compare),
                    str(output / f"{name}.ppm"),
                    str(baseline_dir / f"{name}.ppm"),
                    "--output",
                    str(comparison_path),
                    "--mean-absolute-error-max",
                    str(limits[0]),
                    "--root-mean-square-error-max",
                    str(limits[1]),
                    "--different-pixel-ratio-max",
                    str(limits[2]),
                    "--coverage-iou-min",
                    "0",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if comparison.returncode not in (0, 2):
                raise RuntimeError(
                    f"image comparison failed for {name}: {comparison.stderr}"
                )
            report = json.loads(comparison_path.read_text(encoding="utf-8"))
            comparisons.append(report)
            if comparison.returncode == 2:
                failed = [key for key, passed in report["checks"].items() if not passed]
                raise RuntimeError(
                    f"image regression for {name}: {', '.join(failed)}"
                )
    pose_comparisons = []
    if args.pose_baseline_result:
        baseline_result = json.loads(
            args.pose_baseline_result.read_text(encoding="utf-8")
        )
        pose_comparisons = compare_vehicle_poses(
            image_results,
            baseline_result.get("captures", []),
            args.pose_distance_max,
        )
    result = {
        "schema": SCHEMA,
        "result": "pass",
        "scenario": str(scenario),
        "state_root": str(run_state_root),
        "session": events[0].get("session"),
        "event_log": str(event_log),
        "performance_log": str(perf_csv),
        "captures": image_results,
        "fh1_pass_families": pass_families,
        "pass_inventory_enabled": args.collect_pass_inventory,
        "shader_capture_dir": (
            str(args.shader_capture_dir.resolve()) if args.shader_capture_dir else None
        ),
        "disc_shader_corpus_dir": (
            str(disc_shader_corpus_dir) if disc_shader_corpus_dir else None
        ),
        "shader_pack": str(staged_shader_pack) if staged_shader_pack else None,
        "shader_packs": [str(path) for path in staged_shader_packs],
        "shader_capture": shader_capture,
        "seeded_shader_storage": seeded_shader_storage,
        "seeded_pipeline_prewarm": seeded_pipeline_prewarm,
        "seeded_vulkan_shader_storage": seeded_vulkan_shader_storage,
        "opening_movies_included": args.include_opening_movies,
        "performance": performance,
        "low_spec_simulation": simulation.summary(),
        "game_arguments": game_arguments,
        "comparisons": comparisons,
        "vehicle_pose_comparisons": pose_comparisons,
        "capture_mae": capture_mae,
        "race_hud": race_hud,
        "race_finish": race_finish,
        "rally_progress": rally_progress,
        "rally_transitions": rally_transitions,
        "rally_retirements": rally_retirements,
        "rally_series": rally_series,
        "rally_return_entry": rally_return_entry,
        "rally_audio": rally_audio,
        "rally_pace": rally_pace,
        "rally_pace_suspend": rally_pace_suspend,
        "rally_pace_retry": rally_pace_retry,
        "rally_resumes": rally_resumes,
        "rally_series_reloads": rally_reloads,
        "rally_stage_reloads": rally_stage_reloads,
        "rally_builtin": rally_builtin,
        "rally_normal_entry": rally_normal_entry,
        "rally_service_entry_guard": rally_service_guard,
        "rally_test_ai_driver": rally_test_ai,
        "rally_entry_positions": rally_entry_positions,
        "rally_car_database": rally_car_database,
        "rally_hub_ui": rally_hub_ui,
        "rally_hub_resumes": rally_hub_resumes,
        "rally_hub_retirements": rally_hub_retirements,
        "rally_entries": rally_entries,
        "automation": (
            "fh1_wall_time_script"
            if "# clock-hz " in scenario.read_text(encoding="utf-8")
            else "fh1_guest_output_frame_script"
        ),
        "human_input": False,
        "computer_use": False,
    }
    (output / "result.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a deterministic FH1 renderer scenario."
    )
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--record-baseline", action="store_true")
    parser.add_argument("--fresh-profile", action="store_true",
                        help="allow a seed without an FH1 profile (the new-player opening)")
    parser.add_argument("--pose-baseline-result", type=Path)
    parser.add_argument("--pose-distance-max", type=float, default=1.25)
    parser.add_argument("--collect-pass-inventory", action="store_true")
    parser.add_argument("--shader-capture-dir", type=Path)
    parser.add_argument("--disc-shader-corpus-dir", type=Path)
    parser.add_argument(
        "--shader-pack", type=Path, action="append", help="stage this pack (repeatable)"
    )
    parser.add_argument("--seed-shader-storage", action="store_true")
    parser.add_argument("--seed-pipeline-prewarm", action="store_true")
    parser.add_argument(
        "--seed-vulkan-shader-storage", action="store_true",
        help="copy the seed's Vulkan shader and pipeline storage into the run",
    )
    parser.add_argument("--require-zero-shader-misses", action="store_true")
    parser.add_argument("--include-opening-movies", action="store_true")
    parser.add_argument(
        "--null-gpu",
        action="store_true",
        help="run on the null GPU backend: guest GPU packets only, no images",
    )
    parser.add_argument("--timeout", type=int)
    parser.add_argument(
        "--nsight-gpu-trace", type=Path, metavar="NGFX",
        help="trace frames with Nsight Graphics GPU Trace (path to ngfx.exe)",
    )
    parser.add_argument("--nsight-output-dir", type=Path, help="where the GPU trace goes")
    parser.add_argument(
        "--nsight-start-after-frames", type=int, default=0,
        help="presents to wait before the GPU trace",
    )
    parser.add_argument("--nsight-frames", type=int, default=1, help="frames to trace")
    parser.add_argument(
        "--configuration", choices=("Release", "RelWithDebInfo"),
        help="preview build to launch (launch-preview.ps1 default: Release)",
    )
    parser.add_argument(
        "--hidden", action="store_true",
        help="hide the window; frame pacing then matches routes recorded hidden",
    )
    parser.add_argument(
        "--game-root", type=Path,
        help="game files to run instead of .local/game/base (e.g. a link mirror)",
    )
    parser.add_argument(
        "--build-directory", type=Path,
        help="directory holding pinyon_shift.exe (e.g. a saved control build for an A/B)",
    )
    parser.add_argument("--game-argument", action="append", default=[])
    # Low-end hardware sensitivity runs (LOW_SPEC_BACKLOG LS-0.5). They keep
    # this machine's caches, memory and driver: label results as sensitivity
    # data, not another machine's numbers.
    parser.add_argument(
        "--host-cpus", metavar="LIST",
        help="run the game on these logical processors only (host_cpu_simulation), "
             "such as 0,2,4,6 for 4 cores without SMT or 0-7 for 4 cores with it",
    )
    parser.add_argument(
        "--sibling-load", metavar="LIST",
        help="keep these logical processors busy (the SMT siblings of --host-cpus) "
             "to approximate slower cores",
    )
    parser.add_argument(
        "--vram-balloon-gb", type=float,
        help="hold this much device-local memory in another process during the run "
             "(pinyon_shift_vram_balloon), shrinking the game's VRAM budget",
    )
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
