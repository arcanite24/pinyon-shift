#!/usr/bin/env python3
"""Check same-frame geometry snapshots for the three remaining Gate A families."""

import collections
import json
from pathlib import Path
import runpy
import sys


FAMILIES = {"selected_car_scene_list", "selected_animated",
            "selected_car_presentation"}


def verify(log_path: Path, ledger_path: Path, require_car_title=False,
           require_scalar_title=False):
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    role = runpy.run_path(str(Path(__file__).with_name(
        "partition-snr00-gate-a-slice.py")))["role"]
    selected = {row["ordinal"]: role(row) for row in ledger["draws"]
                if role(row) in FAMILIES}
    selected_rows = {row["ordinal"]: row for row in ledger["draws"]
                     if row["ordinal"] in selected}
    frame = ledger["backend_frame"]
    prepared, fetches, indices = {}, collections.defaultdict(dict), {}
    title, joins, scalar_title, scalar_joins = {}, {}, {}, {}
    for line in log_path.open(encoding="utf-8", errors="replace"):
        for marker in ("FH1 SNR01 prepared draw ",
                       "FH1 SNR01 prepared vertex fetch ",
                       "FH1 SNR03 probe index snapshot ",
                       "FH1 SNR01 scene indirect packet ",
                       "FH1 SNR03 car title join ",
                       "FH1 SNR03 scalar title record ",
                       "FH1 SNR03 scalar title join "):
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            if row["frame"] != (frame - 1 if marker.endswith(
                    ("scene indirect packet ", "scalar title record ")) else frame):
                break
            if marker.endswith("prepared draw ") and row["ordinal"] in selected:
                assert row["ordinal"] not in prepared, "duplicate prepared draw"
                prepared[row["ordinal"]] = row
            elif marker.endswith("prepared vertex fetch ") and row["draw"] in selected:
                assert row["slot"] not in fetches[row["draw"]], "duplicate fetch"
                fetches[row["draw"]][row["slot"]] = row
            elif marker.endswith("index snapshot "):
                assert row["sequence"] not in indices, "duplicate index snapshot"
                indices[row["sequence"]] = row
            elif marker.endswith("scene indirect packet ") and \
                    row["view_call"] == 8 and row["flush_owner_first_word"] \
                    in (0x82001618, 0x82003A54):
                assert row["header_physical"] not in title, "duplicate car title packet"
                title[row["header_physical"]] = row
            elif marker.endswith("car title join "):
                assert row["sequence"] not in joins, "duplicate car title join"
                joins[row["sequence"]] = row
            elif marker.endswith("scalar title record "):
                assert row["packet"] not in scalar_title, "duplicate scalar title packet"
                scalar_title[row["packet"]] = row
            elif marker.endswith("scalar title join "):
                assert row["sequence"] not in scalar_joins, "duplicate scalar join"
                scalar_joins[row["sequence"]] = row
            break
    assert set(prepared) == set(selected), "selected/prepared draw mismatch"
    stable_fetch, stable_index = {}, {}
    counts = collections.Counter()
    missing = []
    for ordinal, family in selected.items():
        draw = prepared[ordinal]
        counts[family] += 1
        assert set(fetches[ordinal]) == set(range(draw["vertex_fetch_count"])), \
            f"incomplete fetches for draw {ordinal}"
        for fetch in fetches[ordinal].values():
            if fetch["cpu_snapshot_status"] != 1 or not fetch["cpu_snapshot_hash"]:
                missing.append((ordinal, "vertex", fetch["slot"]))
                continue
            key = fetch["guest_base"], fetch["length"]
            previous = stable_fetch.setdefault(key, fetch["cpu_snapshot_hash"])
            assert previous == fetch["cpu_snapshot_hash"], \
                f"mutable repeated vertex range {key}"
        assert draw["index_buffer_type"] in (1, 2), \
            f"unexpected index source {ordinal}"
        if draw["index_buffer_type"] == 2:
            counts["host_converted_indices"] += 1
        index = indices.get(draw["sequence"])
        if not index or index["status"] != 1 or not index["hash"]:
            missing.append((ordinal, "index", 0))
            continue
        assert index["packet"] == draw["packet_physical"] and \
            index["length"] == draw["index_buffer_length"], \
            f"index/draw mismatch {ordinal}"
        key = draw["index_buffer_guest_base"], index["length"]
        previous = stable_index.setdefault(key, index["hash"])
        assert previous == index["hash"], f"mutable repeated index range {key}"
    assert not missing, f"missing snapshots: {missing[:20]} (total {len(missing)})"
    if require_car_title:
        car = {prepared[ordinal]["sequence"]: (ordinal, prepared[ordinal])
               for ordinal, family in selected.items()
               if family == "selected_car_scene_list"}
        assert set(joins) == set(car), "car title join/selected draw mismatch"
        for sequence, (ordinal, draw) in car.items():
            join = joins[sequence]
            assert join["valid"] and join["packet"] == draw["packet_physical"] \
                and join["dispatch"] == draw["dispatch_packet_physical"] \
                and join["target"] == draw["command_buffer"] \
                and join["fetches"] == draw["vertex_fetch_count"] \
                and join["index_type"] == draw["index_buffer_type"], \
                f"invalid car title join {ordinal}"
            record = title.get(join["dispatch"])
            assert record and record["target_physical"] == join["target"] \
                and record["flush_owner"] == join["owner"] \
                and record["flush_owner_first_word"] == join["owner_vtable"] \
                and record["owner_call"] == join["owner_call"], \
                f"unowned car title join {ordinal}"
            assert selected_rows[ordinal]["owner"] == join["owner"] and \
                selected_rows[ordinal]["owner_first_word"] == join["owner_vtable"] \
                and selected_rows[ordinal]["scene_source_frame"] == frame - 1, \
                f"car ledger ownership mismatch {ordinal}"
    if require_scalar_title:
        scalar = {prepared[ordinal]["sequence"]: (ordinal, prepared[ordinal])
                  for ordinal, family in selected.items()
                  if family in ("selected_animated", "selected_car_presentation")}
        assert set(scalar_joins) == set(scalar), \
            "scalar title join/selected draw mismatch"
        for sequence, (ordinal, draw) in scalar.items():
            join = scalar_joins[sequence]
            record = scalar_title.get(join["packet"])
            row = selected_rows[ordinal]
            assert join["valid"] and join["packet"] == draw["packet_physical"] \
                and join["fetches"] == draw["vertex_fetch_count"] \
                and join["index_type"] == draw["index_buffer_type"] \
                and record and record["caller"] == join["caller"] \
                and record["object"] == join["object"] \
                and record["vtable"] == join["vtable"] \
                and record["scalar"] == join["scalar"] \
                and row["title_scalar_caller_lr"] == join["caller"] \
                and row["title_scalar_object"] == join["object"] \
                and row["title_packet_source_frame"] == frame - 1, \
                f"invalid scalar title join {ordinal}"
    return {"backend_frame": frame, "draws": dict(counts),
            "stable_vertex_ranges": len(stable_fetch),
            "stable_guest_index_ranges": len(stable_index),
            "car_title_records": len(title) if require_car_title else None,
            "car_title_joins": len(joins) if require_car_title else None,
            "scalar_title_records": len(scalar_title) if require_scalar_title else None,
            "scalar_title_joins": len(scalar_joins) if require_scalar_title else None}


if __name__ == "__main__":
    options = set(sys.argv[3:])
    if len(sys.argv) < 3 or len(options) != len(sys.argv[3:]) or \
            not options <= {"--require-car-title", "--require-scalar-title"}:
        raise SystemExit("usage: verify-snr03-remainder-snapshots.py LOG LEDGER "
                         "[--require-car-title] [--require-scalar-title]")
    print(json.dumps(verify(Path(sys.argv[1]), Path(sys.argv[2]),
                            "--require-car-title" in options,
                            "--require-scalar-title" in options), sort_keys=True))
