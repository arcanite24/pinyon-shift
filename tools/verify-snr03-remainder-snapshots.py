#!/usr/bin/env python3
"""Check same-frame geometry snapshots for the three remaining Gate A families."""

import collections
import json
from pathlib import Path
import runpy
import sys


FAMILIES = {"selected_car_scene_list", "selected_animated",
            "selected_car_presentation"}


def verify(log_path: Path, ledger_path: Path):
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    role = runpy.run_path(str(Path(__file__).with_name(
        "partition-snr00-gate-a-slice.py")))["role"]
    selected = {row["ordinal"]: role(row) for row in ledger["draws"]
                if role(row) in FAMILIES}
    frame = ledger["backend_frame"]
    prepared, fetches, indices = {}, collections.defaultdict(dict), {}
    for line in log_path.open(encoding="utf-8", errors="replace"):
        for marker in ("FH1 SNR01 prepared draw ",
                       "FH1 SNR01 prepared vertex fetch ",
                       "FH1 SNR03 probe index snapshot "):
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            if row["frame"] != frame:
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
    return {"backend_frame": frame, "draws": dict(counts),
            "stable_vertex_ranges": len(stable_fetch),
            "stable_guest_index_ranges": len(stable_index)}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify-snr03-remainder-snapshots.py LOG LEDGER")
    print(json.dumps(verify(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True))
