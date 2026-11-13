#!/usr/bin/env python3
"""Guest CPU by subsystem from a CPU profile (#1071).

Reads either
  * a thread-sampler directory (tools/thread_sampler.cpp: samples.csv,
    stacks.csv, threads.csv), optionally cut to a time window, or
  * a folded-stacks file ("thread;outer;...;leaf weight" per line), such as
    simpleperf's stackcollapse.py --tid output from an Android recording
    (weights are the event counts, cycles by default),
and splits the guest threads' CPU into the subsystems named in
config/performance/subsystems.toml: a sample belongs to the first group with
one of its root functions anywhere on its stack, otherwise to "other" under
its guest thread. A root also matches a thread that starts there.

Thread-sampler input: samples whose leaf is a kernel wait are dropped. Each
remaining sample stands for the wall time since its thread's previous sample
(`--weight wall`, the default) or for the cycles the thread used since then
(`--weight cycles`; a bursty thread's cycles can land on the wait it is
found in, so this undercounts bursts). A thread that is "busy" in guest code
but uses almost no cycles (a guest-side sleep) is left out with a note.

  python tools/subsystem-cpu.py .local/thread-samples/race --from-s 78 --to-s 110
  python tools/subsystem-cpu.py odin.folded --top 15 --output odin.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ROOT / "config" / "performance" / "subsystems.toml"
GUEST = re.compile(r"(?:^|[!:_])(?:ieee_|nr_)?sub_([0-9A-Fa-f]{8})\b")
WAIT = re.compile(r"NtWaitFor|ZwWaitFor|NtDelayExecution|ZwDelayExecution|NtRemoveIoCompletion|"
                  r"RtlSleepConditionVariable|NtAlertThreadByThreadId|ZwWaitForAlertByThreadId|"
                  r"SleepEx|futex|__epoll_wait|nanosleep")
THREAD_ROLE = re.compile(r"^(Guest [0-9A-Fa-f]{8})")
SLEEPER_MCYCLES_PER_MS = 0.05


def load_groups(path: Path) -> list[tuple[str, set[str]]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    groups = []
    for group in data.get("group", []):
        roots = {a.upper() for a in group.get("base", []) + group.get("v4", [])}
        groups.append((group["name"], roots))
    return groups


def role(thread: str) -> str:
    match = THREAD_ROLE.match(thread)
    return match.group(1) if match else thread


def guest_functions(frames: list[str]) -> list[str]:
    seen, out = set(), []
    for frame in frames:
        for match in GUEST.finditer(frame):
            name = match.group(1).upper()
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def classify(functions: list[str], thread: str, groups) -> str:
    # A root also matches the guest thread's start address, which is not
    # always a frame of its stacks.
    present = set(functions)
    match = THREAD_ROLE.match(thread)
    if match:
        present.add(match.group(1)[6:].upper())
    for name, roots in groups:
        if present & roots:
            return name
    return f"other: {role(thread)}"


class Totals:
    def __init__(self) -> None:
        self.group = collections.Counter()
        self.group_cycles = collections.Counter()
        self.thread = collections.Counter()
        self.thread_cycles = collections.Counter()
        self.inclusive = collections.defaultdict(collections.Counter)

    def add(self, group: str, thread: str, functions: list[str], weight: float, cycles: float) -> None:
        self.group[group] += weight
        self.group_cycles[group] += cycles
        self.thread[thread] += weight
        self.thread_cycles[thread] += cycles
        for function in functions:
            self.inclusive[group][function] += weight


def read_sampler(directory: Path, args, groups) -> tuple[Totals, float, list[str]]:
    stacks = {}
    with (directory / "stacks.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            stacks[row["stack_id"]] = row["stack"].split(";")
    names = {}
    with (directory / "threads.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            names[row["thread"]] = row["name"]
    start = args.from_s * 1000 if args.from_s is not None else float("-inf")
    end = args.to_s * 1000 if args.to_s is not None else float("inf")
    rows = []
    last: dict[str, float] = {}
    first_t, last_t = None, None
    with (directory / "samples.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            t = float(row["t_ms"])
            previous = last.get(row["thread"])
            last[row["thread"]] = t
            if previous is None or t < start or t > end:
                continue
            name = names.get(row["thread"], row["thread"])
            if not name.startswith(args.thread_prefix):
                continue
            frames = stacks[row["stack_id"]]
            if any(WAIT.search(frame) for frame in frames[-4:]):
                continue
            first_t = t if first_t is None else min(first_t, t)
            last_t = t if last_t is None else max(last_t, t)
            rows.append((name, frames, t - previous, int(row["cycles"])))
    # Busy in guest code but almost no cycles: a guest-side sleep.
    wall = collections.Counter()
    cycles = collections.Counter()
    for name, _, dt, cyc in rows:
        wall[name] += dt
        cycles[name] += cyc
    sleepers = [n for n in wall if wall[n] > 0 and cycles[n] / 1e6 / wall[n] < SLEEPER_MCYCLES_PER_MS]
    totals = Totals()
    for name, frames, dt, cyc in rows:
        if name in sleepers:
            continue
        functions = guest_functions(frames)
        weight = dt if args.weight == "wall" else cyc / 1e6
        totals.add(classify(functions, name, groups), name, functions, weight, cyc / 1e6)
    if args.from_s is not None and args.to_s is not None:
        seconds = args.to_s - args.from_s
    else:
        seconds = ((last_t or 0) - (first_t or 0)) / 1000 or 1.0
    return totals, seconds, sleepers


def read_folded(path: Path, args, groups) -> tuple[Totals, float, list[str]]:
    totals = Totals()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            stack, _, count = line.rpartition(" ")
            frames = stack.split(";")
            thread = frames[0]
            if not thread.startswith(args.thread_prefix):
                continue
            weight = float(count) / 1e6
            functions = guest_functions(frames[1:])
            totals.add(classify(functions, thread, groups), role(thread), functions, weight, weight)
    return totals, args.seconds or 1.0, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("profile", type=Path, help="thread-sampler directory or folded-stacks file")
    parser.add_argument("--groups", type=Path, default=GROUPS)
    parser.add_argument("--from-s", type=float)
    parser.add_argument("--to-s", type=float)
    parser.add_argument("--weight", choices=("wall", "cycles"), default="wall",
                        help="thread-sampler input only (folded input is always its event count)")
    parser.add_argument("--thread-prefix", default="Guest ",
                        help="only threads whose name starts with this (default: guest threads)")
    parser.add_argument("--seconds", type=float,
                        help="folded input: the recording's length, to report per second")
    parser.add_argument("--fps", type=float, help="also report per frame at this rate")
    parser.add_argument("--top", type=int, default=8, help="inclusive functions listed per group")
    parser.add_argument("--output", type=Path, help="write the report as JSON")
    args = parser.parse_args()

    groups = load_groups(args.groups)
    if args.profile.is_dir():
        totals, seconds, sleepers = read_sampler(args.profile, args, groups)
        unit = "ms CPU/s" if args.weight == "wall" else "Mcycles/s"
    else:
        totals, seconds, sleepers = read_folded(args.profile, args, groups)
        unit = "Mevents/s" if args.seconds else "Mevents"
    total = sum(totals.group.values()) or 1.0

    report = {"profile": str(args.profile), "seconds": seconds, "unit": unit,
              "total": total / seconds, "left_out_sleeping_threads": sleepers, "groups": []}
    print(f"{args.profile}: {seconds:.1f} s, guest total {total / seconds:.1f} {unit}")
    if sleepers:
        print(f"  left out (busy in guest code, almost no cycles): {', '.join(sleepers)}")
    for group, value in totals.group.most_common():
        share = 100 * value / total
        per_frame = f"  {value / seconds / args.fps:6.2f} per frame" if args.fps else ""
        print(f"  {value / seconds:9.1f}  {share:5.1f} %  {group}{per_frame}")
        # Frames on (nearly) every sample of the group are its ancestors:
        # the thread entry and the root's callers. List what lies below.
        top = [(f, w) for f, w in totals.inclusive[group].most_common()
               if w < 0.995 * value][:args.top]
        for function, weight in top:
            print(f"        {100 * weight / value:5.1f} %  sub_{function}")
        report["groups"].append({
            "name": group, "per_second": value / seconds, "share": share,
            "cycles_per_second_m": totals.group_cycles[group] / seconds,
            "inclusive": [{"function": f"sub_{f}", "share_of_group": 100 * w / value} for f, w in top]})
    report["threads"] = [{"thread": t, "per_second": v / seconds, "cycles_per_second_m":
                          totals.thread_cycles[t] / seconds} for t, v in totals.thread.most_common()]
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
