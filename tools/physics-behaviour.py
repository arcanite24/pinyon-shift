#!/usr/bin/env python3
"""Physics behaviour from a pinyon_shift_physics_trace run (#1071 P0).

A native subsystem has to drive like the translated one closely enough
for play, not bit for bit. This reads the fh1.physics_trace events of a
render-test run (the session JSONL, or the runner's result JSON, which names
it) and reports, at the route's fixed clock:

  * the player's 0-60 and 0-100 km/h times from the first sample with the
    throttle pressed at a standstill (the #1019 acceleration check; the game
    ramps the throttle to full over about 0.2 s),
  * each car's distance (integrated speed) and top speed, the AI cars' mean
    distance, and the order by distance at the last sample,
  * the player's race time when the run finished a race (dlc.rally.race_trace).

`compare` checks a second run against a reference and exits 1 when it
fails: the player's 0-60, 0-100 and race time within 2 %, the AI cars' mean
distance within 3 %. Single AI cars and the order are listed but not gated
(--strict gates the order): two runs of the same build move single cars by
up to 4 % and swap places, from thread timing.

  python tools/physics-behaviour.py summary .local/render-tests/race/result.json
  python tools/physics-behaviour.py compare translated.json native.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

KMH = 3.6
RACE_MODES = {3, 20}


def event_log(path: Path) -> tuple[Path, float | None]:
    """The session JSONL and the route's fixed clock, if the runner's result
    names a route with `# clock-hz`."""
    if path.suffix == ".jsonl":
        return path, None
    result = json.loads(path.read_text(encoding="utf-8"))
    clock = None
    scenario = Path(result.get("scenario", ""))
    if scenario.is_file():
        for line in scenario.read_text(encoding="utf-8").splitlines():
            if line.startswith("# clock-hz "):
                clock = float(line.split()[2])
    return Path(result["event_log"]), clock


def load(path: Path) -> tuple[list[dict], float | None]:
    events = []
    log, clock = event_log(path)
    with log.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("{"):
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events, clock


def samples(events: list[dict]) -> list[tuple[int, int, list[dict]]]:
    out = []
    for event in events:
        if event.get("event") != "fh1.physics_trace":
            continue
        cars = []
        for packed in filter(None, event.get("cars", "").split("|")):
            index, car, driver, speed, rpm, gear, gas, brake, steer = packed.split(":")
            cars.append(dict(index=int(index), car=car, driver=int(driver), speed=float(speed), rpm=float(rpm),
                             gear=int(gear), gas=float(gas), brake=float(brake), steer=float(steer)))
        out.append((int(event["frame"]), int(event.get("mode", "0")), cars,
                    float(event["t_ms"]) / 1000 if "t_ms" in event else None))
    out.sort(key=lambda s: s[0])
    return out


def crossing(points: list[tuple[float, float]], start: float, kmh: float) -> float | None:
    target = kmh / KMH
    previous = None
    for t, speed in points:
        if t < start:
            continue
        if speed >= target:
            if previous is None or previous[1] >= target:
                return t - start
            t0, s0 = previous
            return t0 + (target - s0) * (t - t0) / (speed - s0) - start
        previous = (t, speed)
    return None


def race_seconds(events: list[dict]) -> float | None:
    for event in reversed(events):
        if (event.get("event") == "dlc.rally.race_trace" and
                (event.get("started"), event.get("ended"), event.get("end_reason")) == ("1", "1", "1")):
            seconds = float(event.get("time_72", "nan"))
            if math.isfinite(seconds) and seconds > 0:
                return seconds
    return None


def summarize(path: Path, clock_hz: float | None, from_frame: int | None, to_frame: int | None,
              all_modes: bool = False) -> dict:
    events, route_clock = load(path)
    # Time from the route's fixed clock (frame numbers are wall time), from
    # --clock-hz, or else from the host time in each sample: without a fixed
    # clock frame numbers count output frames.
    clock_hz = clock_hz or route_clock
    trace = [s for s in samples(events)
             if (from_frame is None or s[0] >= from_frame) and (to_frame is None or s[0] <= to_frame)]
    # A race (mode 3) or a Rally stage (mode 20); free roam before it has
    # other cars in the vector.
    race = any(s[1] in RACE_MODES for s in trace)
    if not all_modes and race:
        trace = [s for s in trace if s[1] in RACE_MODES]
    if not trace:
        raise SystemExit(f"{path}: no fh1.physics_trace samples (run with --pinyon_shift_physics_trace=6)")
    cars: dict[int, dict] = {}
    player_points: list[tuple[float, float]] = []
    launch = None
    previous_t = None
    if clock_hz is None and any(s[3] is None for s in trace):
        raise SystemExit(f"{path}: route has no fixed clock and samples have no t_ms; pass --clock-hz")
    for frame, _, entries, host_s in trace:
        t = frame / clock_hz if clock_hz else host_s
        dt = 0.0 if previous_t is None else t - previous_t
        previous_t = t
        for car in entries:
            state = cars.setdefault(car["car"], dict(index=car["index"], car=car["car"],
                                                     driver=car["driver"], distance_m=0.0,
                                                     top_kmh=0.0, last=None))
            if state["last"] is not None:
                state["distance_m"] += 0.5 * (state["last"] + abs(car["speed"])) * dt
            state["last"] = abs(car["speed"])
            # The vector's order changes while cars join; a car is named by
            # its place at the last sample.
            state["index"] = car["index"]
            state["top_kmh"] = max(state["top_kmh"], abs(car["speed"]) * KMH)
            if car["driver"] == 0:
                player_points.append((t, abs(car["speed"])))
                if launch is None and car["gas"] > 0.05 and abs(car["speed"]) < 1.0:
                    launch = t
    order = sorted(cars.values(), key=lambda c: -c["distance_m"])
    for state in cars.values():
        state.pop("last")
    player = next((c for c in cars.values() if c["driver"] == 0), None)
    ai = [c["distance_m"] for c in cars.values() if c["driver"] != 0]
    return dict(
        source=str(path), samples=len(trace), clock_hz=clock_hz, race=race,
        first_frame=trace[0][0], last_frame=trace[-1][0],
        player=dict(index=player["index"] if player else None,
                    launch_s=launch,
                    zero_to_60_kmh_s=crossing(player_points, launch, 60) if launch is not None else None,
                    zero_to_100_kmh_s=crossing(player_points, launch, 100) if launch is not None else None,
                    distance_m=player["distance_m"] if player else None,
                    race_seconds=race_seconds(events)),
        ai=dict(count=len(ai), mean_distance_m=sum(ai) / len(ai) if ai else None),
        cars=sorted(cars.values(), key=lambda c: c["index"]),
        order=[c["index"] for c in order])


def within(reference: float | None, value: float | None, tolerance: float) -> bool:
    if reference is None or value is None:
        return reference is None and value is None
    return abs(value - reference) <= tolerance * max(abs(reference), 1e-6)


def compare(reference: dict, run: dict, player_tol: float, ai_tol: float,
            strict: bool = False) -> tuple[list[str], list[str]]:
    """Gates and notes. Two runs of one build differ: thread timing moves
    single AI cars by up to 4 % over the sustained race and swaps places,
    and the player's distance with no steering by about 3 %. So the gates
    are the player's 0-60/0-100 and race time and the field's mean
    distance; single cars and the order are notes unless strict."""
    problems, notes = [], []
    for key in ("zero_to_60_kmh_s", "zero_to_100_kmh_s", "race_seconds"):
        a, b = reference["player"][key], run["player"][key]
        if not within(a, b, player_tol):
            problems.append(f"player {key}: {a} -> {b} (tolerance {100 * player_tol:.0f} %)")
    if not (reference["race"] and run["race"]):
        # Free roam: the other cars are traffic, not a field to compare.
        pass
    elif reference["ai"]["count"] != run["ai"]["count"]:
        problems.append(f"AI cars: {reference['ai']['count']} -> {run['ai']['count']}")
    elif not within(reference["ai"]["mean_distance_m"], run["ai"]["mean_distance_m"], ai_tol):
        problems.append(f"AI mean distance: {reference['ai']['mean_distance_m']:.1f} -> "
                        f"{run['ai']['mean_distance_m']:.1f} m (tolerance {100 * ai_tol:.0f} %)")
    a, b = reference["player"]["distance_m"], run["player"]["distance_m"]
    if a and b:
        notes.append(f"player distance {a:.1f} -> {b:.1f} m ({100 * (b - a) / a:+.1f} %)")
    reference_cars = {c["index"]: c for c in reference["cars"]
                      if c["driver"] != 0 and reference["race"] and run["race"]}
    for car in run["cars"]:
        base = reference_cars.get(car["index"])
        if car["driver"] != 0 and base and base["distance_m"]:
            delta = 100 * (car["distance_m"] - base["distance_m"]) / base["distance_m"]
            notes.append(f"car {car['index']} distance {base['distance_m']:.1f} -> "
                         f"{car['distance_m']:.1f} m ({delta:+.1f} %)")
    if reference["race"] and run["race"] and reference["order"] != run["order"]:
        (problems if strict else notes).append(f"order: {reference['order']} -> {run['order']}")
    return problems, notes


def print_summary(report: dict) -> None:
    p = report["player"]
    fmt = lambda v, unit="s": "-" if v is None else f"{v:.2f} {unit}"
    clock = f"{report['clock_hz']:g} Hz" if report["clock_hz"] else "host time"
    print(f"{report['source']}: {report['samples']} samples, frames {report['first_frame']}-"
          f"{report['last_frame']}, {clock}")
    print(f"  player car {p['index']}: 0-60 {fmt(p['zero_to_60_kmh_s'])}, 0-100 "
          f"{fmt(p['zero_to_100_kmh_s'])}, distance {fmt(p['distance_m'], 'm')}, race {fmt(p['race_seconds'])}")
    for car in report["cars"]:
        who = "player" if car["driver"] == 0 else f"driver {car['driver']}"
        print(f"  car {car['index']:2} {who:10} {car['distance_m']:8.1f} m  top {car['top_kmh']:6.1f} km/h")
    if report["ai"]["count"] and report["race"]:
        print(f"  {report['ai']['count']} AI cars, mean distance {report['ai']['mean_distance_m']:.1f} m")
    print(f"  order by distance: {report['order']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("summary", "compare"):
        command = sub.add_parser(name)
        command.add_argument("runs", type=Path, nargs=1 if name == "summary" else 2,
                             help="session JSONL or render-test result JSON")
        command.add_argument("--clock-hz", type=float,
                             help="frames per second (default: the route's # clock-hz, else host time)")
        command.add_argument("--from-frame", type=int)
        command.add_argument("--to-frame", type=int)
        command.add_argument("--all-modes", action="store_true",
                             help="keep samples outside a race or Rally stage")
        command.add_argument("--output", type=Path, help="write the report(s) as JSON")
        if name == "compare":
            command.add_argument("--player-tolerance", type=float, default=0.02)
            command.add_argument("--ai-tolerance", type=float, default=0.03,
                                 help="on the AI cars' mean distance")
            command.add_argument("--strict", action="store_true",
                                 help="also fail when the order by distance changes")
    args = parser.parse_args()
    reports = [summarize(run, args.clock_hz, args.from_frame, args.to_frame, args.all_modes) for run in args.runs]
    for report in reports:
        print_summary(report)
    result: dict = dict(runs=reports)
    status = 0
    if args.command == "compare":
        problems, notes = compare(reports[0], reports[1], args.player_tolerance, args.ai_tolerance,
                                  args.strict)
        result["problems"] = problems
        result["notes"] = notes
        print("compare: " + ("PASS" if not problems else "FAIL"))
        for problem in problems:
            print(f"  {problem}")
        for note in notes:
            print(f"  note: {note}")
        status = 1 if problems else 0
    if args.output:
        args.output.write_text(json.dumps(result if args.command == "compare" else reports[0], indent=2),
                               encoding="utf-8")
    return status


if __name__ == "__main__":
    sys.exit(main())
