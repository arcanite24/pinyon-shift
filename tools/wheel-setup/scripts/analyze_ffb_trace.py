"""Summarise a Pinyon Shift force feedback trace (ffb-trace-*.csv).

Usage:  python analyze_ffb_trace.py ffb-trace-20261014-201500.csv

Two kinds of rows:
- ffb_* rows: the game driving the wheel the way it drove an Xbox 360 FFB wheel
  (XInputdFF calls): the five effects it downloads (inertia, friction, damper,
  spring, constant force), its per-frame updates and its rumble.
- set / caps / vibration_level rows: the plain XInput path (motor values), which the
  game uses for a controller or a wheel without the effects path.
"""
import csv
import statistics
import sys
from collections import Counter, defaultdict


def corr(xs, ys):
    if len(xs) < 3 or statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
        return float("nan")
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / len(xs)
    return cov / (statistics.pstdev(xs) * statistics.pstdev(ys))


def wheel_effects(rows):
    ffb = [r for r in rows if r["event"].startswith("ffb_")]
    if not ffb:
        print("\nNo XInputdFF calls: the game did not use its wheel force feedback path.")
        return
    print(f"\nWheel force feedback calls ({len(ffb)}):")
    for event, count in Counter(r["event"] for r in ffb).most_common():
        print(f"  {event:20s} {count}")

    print("\nEffects the game downloaded:")
    for r in ffb:
        if r["event"] == "ffb_set_effect":
            print("  " + r.get("detail", "").split(" | ")[0])

    updates = defaultdict(list)
    for r in ffb:
        if r["event"] == "ffb_update_effect":
            words = r.get("detail", "").split(" | ")[-1].split()
            if len(words) > 16:
                effect_id = int(words[0], 16)
                as_signed = lambda w: int(w, 16) - (1 << 32) if int(w, 16) >= 1 << 31 else int(w, 16)
                updates[effect_id].append((float(r["t_ms"]), int(r["steering"]),
                                           as_signed(words[3]), as_signed(words[11])))
    for effect_id, values in sorted(updates.items()):
        gains = [v[2] for v in values]
        mags = [v[3] for v in values]
        steer = [v[1] for v in values]
        print(f"\nEffect #{effect_id}: {len(values)} updates")
        print(f"  gain (+12):      min {min(gains)} max {max(gains)}")
        print(f"  magnitude (+44): min {min(mags)} max {max(mags)} "
              f"(the full scale the game uses is probably the largest absolute value)")
        print(f"  correlation of magnitude with steering: {corr(mags, steer):+.3f}")

    rumble = [(int(r["left"]), int(r["right"])) for r in ffb if r["event"] == "ffb_rumble"]
    if rumble:
        print(f"\nRumble: {len(rumble)} calls, left max {max(l for l, _ in rumble)}, "
              f"right max {max(rr for _, rr in rumble)}")


def motor_path(rows):
    sets = [r for r in rows if r["event"] == "set"]
    print(f"\nPlain XInput path: {len(sets)} XamInputSetState calls")
    for r in rows:
        if r["event"] == "caps":
            print(f"  caps from {r['caller']}: result {r['result']} type {r['left']} subtype {r['right']} "
                  f"flags {r['extra']}")
    if not sets:
        return
    left = [int(r["left"]) for r in sets]
    right = [int(r["right"]) for r in sets]
    steer = [int(r["steering"]) for r in sets]
    print(f"  left motor min {min(left)} max {max(left)}; right motor min {min(right)} max {max(right)}")
    print(f"  right - left vs steering: {corr([r - l for l, r in zip(left, right)], steer):+.3f}")


def main(path):
    rows = list(csv.DictReader(open(path, newline="")))
    print(f"{path}: {len(rows)} rows")
    if rows:
        print(f"  span {(float(rows[-1]['t_ms']) - float(rows[0]['t_ms'])) / 1000:.1f} s")
    wheel_effects(rows)
    motor_path(rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
