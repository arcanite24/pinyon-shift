"""Replay a verified Gate A draw order through one carried private target."""

import argparse
import collections
import hashlib
import json
from itertools import groupby
from pathlib import Path
import struct
import subprocess


FAMILY = {
    "selected_car_scene_list": ("snr03-remainder", "remainder"),
    "selected_animated": ("snr03-remainder", "remainder"),
    "selected_car_presentation": ("snr03-remainder", "remainder"),
    "selected_shared_track_procedural": ("snr02-track", "track"),
    "selected_procedural_item": ("snr02-items", "procedural"),
    "selected_procedural_character": ("snr03-characters", "procedural"),
    "selected_character": ("snr03-manager", "procedural"),
    "selected_vegetation": ("snr03-scene", "vegetation"),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(args):
    order = json.loads(args.order.read_text(encoding="utf-8"))
    draws = order["order"]
    assert len(draws) == order["selected_draws"] and draws
    assert all(draws[i]["sequence"] < draws[i + 1]["sequence"]
               for i in range(len(draws) - 1))
    assert all(row["family"] in FAMILY for row in draws)
    output = args.output.resolve()
    assert ".local" in output.parts, "diagnostic output must stay under .local"
    output.mkdir(parents=True, exist_ok=True)
    shaders = {"remainder": args.remainder_shaders,
               "track": args.track_shaders,
               "procedural": args.procedural_shaders,
               "vegetation": args.vegetation_shader}
    previous = None
    runs = []
    next_id = 1
    for number, (family, group) in enumerate(groupby(draws, key=lambda r: r["family"])):
        rows = list(group)
        stem, shader = FAMILY[family]
        fixture = args.fixtures / f"{stem}-{order['source_frame']}.bin"
        directory = output / f"step-{number:02d}"
        directory.mkdir(exist_ok=True)
        command = [str(args.executable.resolve()), str(fixture.resolve()),
                   str(shaders[shader].resolve()), str(directory),
                   "--segment", str(rows[0]["sequence"]),
                   str(rows[-1]["sequence"]), str(next_id), str(len(rows)),
                   str(previous) if previous else "-"]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"{family} run {number}: {result.stderr.strip()}")
        summary = json.loads((directory / "summary.json").read_text())
        assert summary["schema"] == "pinyon-shift.snr04-segment.v1"
        assert (summary["source_frame"], summary["first_sequence"],
                summary["last_sequence"], summary["first_id"],
                summary["draws"], summary["fixture_sha256"]) == (
                    order["source_frame"], rows[0]["sequence"],
                    rows[-1]["sequence"], next_id, len(rows), sha(fixture))
        assert (directory / "color.rgba").stat().st_size == 1280 * 720 * 4
        assert (directory / "depth.f32").stat().st_size == 1280 * 720 * 4
        runs.append({"family": family, "draws": len(rows),
                     "first_id": next_id,
                     "covered_pixels_after": summary["covered_pixels"]})
        previous = directory
        next_id += len(rows)
    assert next_id - 1 == len(draws)
    color = (previous / "color.rgba").read_bytes()
    depth = (previous / "depth.f32").read_bytes()
    identities = collections.Counter()
    zero_depth = 0
    for pixel, value in zip(struct.iter_unpack("<I", color),
                            struct.iter_unpack("<f", depth)):
        raw, z = pixel[0], value[0]
        identity = (raw & 255) | ((raw >> 8) & 255) << 8
        if identity:
            assert 1 <= identity <= len(draws) and 0 <= z <= 1
            identities[identity] += 1
            zero_depth += z == 0
    result = {"schema": "pinyon-shift.snr04-complete-slice.v1",
              "source_frame": order["source_frame"],
              "draws": len(draws), "runs": runs,
              "covered_pixels": sum(identities.values()),
              "visible_draws": len(identities),
              "zero_depth_pixels": zero_depth,
              "identity_sha256": sha(previous / "identity.ppm"),
              "color_sha256": sha(previous / "color.rgba"),
              "depth_sha256": sha(previous / "depth.f32")}
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n",
                                          encoding="utf-8")
    return {key: value for key, value in result.items() if key != "runs"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("order", "fixtures", "executable", "remainder_shaders",
                 "track_shaders", "procedural_shaders", "vegetation_shader",
                 "output"):
        parser.add_argument(name, type=Path)
    print(json.dumps(replay(parser.parse_args()), sort_keys=True))
