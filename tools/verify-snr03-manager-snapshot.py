#!/usr/bin/env python3
"""Check every selected manager draw has stable two-stream/index snapshots."""

import collections
import json
from pathlib import Path
import runpy
import sys


def verify(log_path: Path, ledger_path: Path):
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    frame = ledger["backend_frame"]
    role = runpy.run_path(str(Path(__file__).with_name(
        "partition-snr00-gate-a-slice.py")))["role"]
    selected = {row["ordinal"]: row for row in ledger["draws"]
                if role(row) == "selected_character"}
    assert selected
    prepared, snapshots = {}, {}
    fetches = collections.defaultdict(dict)
    for line in log_path.open(encoding="utf-8", errors="replace"):
        for marker in ("FH1 SNR01 prepared draw ",
                       "FH1 SNR01 prepared vertex fetch ",
                       "FH1 SNR03 manager snapshot "):
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            if row["frame"] != frame:
                break
            if marker == "FH1 SNR01 prepared draw ":
                if row["ordinal"] in selected:
                    assert row["ordinal"] not in prepared
                    prepared[row["ordinal"]] = row
            elif marker == "FH1 SNR01 prepared vertex fetch ":
                if row["draw"] in selected:
                    assert row["slot"] not in fetches[row["draw"]]
                    fetches[row["draw"]][row["slot"]] = row
            else:
                assert row["sequence"] not in snapshots
                snapshots[row["sequence"]] = row
            break
    assert set(prepared) == set(fetches) == set(selected)
    assert len(snapshots) == len(selected)
    ranges = [collections.defaultdict(set) for _ in range(3)]
    repeated = [0, 0, 0]
    for ordinal, title in selected.items():
        draw = prepared[ordinal]
        snapshot = snapshots[draw["sequence"]]
        assert title["title_direct_record"] and title["title_direct_family_object"]
        assert title["packet_physical"] == draw["packet_physical"] == snapshot["packet"]
        assert draw["vertex_shader"] == 0xB8489164D5A86043
        assert draw["guest_primitive_type"] == 4
        assert draw["index_buffer_type"] == 1
        assert draw["index_buffer_length"] == draw["index_count"] * 2
        assert snapshot["index_status"] == 1 and snapshot["index_hash"]
        assert snapshot["index_length"] == draw["index_buffer_length"]
        assert snapshot["fetches"] == draw["vertex_fetch_count"] == 2
        index_key = (draw["index_buffer_guest_base"], draw["index_buffer_length"])
        ranges[2][index_key].add(snapshot["index_hash"])
        repeated[2] += index_key[1]
        for slot, constant, stride, limit in ((0, 95, 8, 128 * 1024),
                                               (1, 94, 3, 3 * 1024 * 1024)):
            fetch = fetches[ordinal][slot]
            assert fetch["packet_physical"] == draw["packet_physical"]
            assert fetch["fetch_constant"] == constant
            assert fetch["stride_words"] == stride
            assert 0 < fetch["length"] <= limit
            assert fetch["cpu_snapshot_status"] == 1
            assert fetch["cpu_snapshot_hash"]
            key = (fetch["guest_base"], fetch["length"])
            ranges[slot][key].add(fetch["cpu_snapshot_hash"])
            repeated[slot] += key[1]
    assert all(len(hashes) == 1 for family in ranges for hashes in family.values())
    return {
        "backend_frame": frame,
        "selected_draws": len(selected),
        "title_records": len({row["title_direct_record"] for row in selected.values()}),
        "unique_ranges": [len(family) for family in ranges],
        "unique_bytes": [sum(length for _, length in family) for family in ranges],
        "repeated_bytes": repeated,
    }


if __name__ == "__main__":
    assert len(sys.argv) == 3, "usage: verify-snr03-manager-snapshot.py LOG LEDGER"
    print(json.dumps(verify(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True))
