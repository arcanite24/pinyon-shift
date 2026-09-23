#!/usr/bin/env python3
"""Verify the owned manager fixture against title, GPU, and frame ledger."""

import collections
import hashlib
import json
from pathlib import Path
import re
import runpy
import struct
import sys


def fnv(values):
    result = 14695981039346656037
    for value in values:
        result = ((result ^ value) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return result


def verify(fixture: Path, log_path: Path, ledger_path: Path):
    source = fixture.read_bytes()
    offset = 0

    def take(fmt):
        nonlocal offset
        size = struct.calcsize(fmt)
        assert offset + size <= len(source), "truncated manager fixture"
        values = struct.unpack_from(fmt, source, offset)
        offset += size
        return values

    assert take("<8s")[0] == b"SNR03M1\0"
    frame, view, camera, records, draws, *range_counts = take("<Q7I")
    assert 0 < records <= 256 and 0 < draws <= 512
    assert all(0 < count <= 512 for count in range_counts)
    assert any(take("<32I"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["backend_frame"] == frame + 1
    role = runpy.run_path(str(Path(__file__).with_name(
        "partition-snr00-gate-a-slice.py")))["role"]
    selected = {row["ordinal"]: row for row in ledger["draws"]
                if role(row) == "selected_character"}
    assert len(selected) == draws
    title, packets, prepared, fetches, textures = {}, {}, {}, {}, collections.defaultdict(dict)
    title_thread = None
    snapshots, before, after = {}, {}, {}
    for line in log_path.open(encoding="utf-8", errors="replace"):
        for marker in ("FH1 SNR01 direct family record ",
                       "FH1 SNR01 direct packet ",
                       "FH1 SNR01 prepared draw ",
                       "FH1 SNR01 prepared vertex fetch ",
                       "FH1 SNR01 prepared texture fetch ",
                       "FH1 SNR03 manager snapshot ",
                       "FH1 SNR03 manager prepared ",
                       "FH1 SNR03 manager final "):
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            thread = re.search(r"\[t(\d+)\]", line)
            assert thread
            thread = int(thread.group(1))
            if marker == "FH1 SNR01 direct family record ":
                if row["frame"] == frame and row["view_call"] == 8:
                    if title_thread is None:
                        title_thread = thread
                    assert thread == title_thread
                    assert row["next_direct"] not in title
                    title[row["next_direct"]] = row
            elif marker == "FH1 SNR01 direct packet ":
                if row["frame"] == frame:
                    key = (thread, row["ordinal"])
                    assert key not in packets
                    packets[key] = row
            elif marker == "FH1 SNR01 prepared draw ":
                if row["frame"] == frame + 1 and row["ordinal"] in selected:
                    assert row["ordinal"] not in prepared
                    prepared[row["ordinal"]] = row
            elif marker == "FH1 SNR01 prepared vertex fetch ":
                if row["frame"] == frame + 1 and row["draw"] in selected:
                    fetches[(row["draw"], row["slot"])] = row
            elif marker == "FH1 SNR01 prepared texture fetch ":
                if row["frame"] == frame + 1 and row["draw"] in selected:
                    assert row["fetch_constant"] not in textures[row["draw"]]
                    textures[row["draw"]][row["fetch_constant"]] = row
            elif row["frame"] == frame + 1:
                destination = (snapshots if marker == "FH1 SNR03 manager snapshot "
                               else before if marker == "FH1 SNR03 manager prepared "
                               else after)
                assert row["sequence"] not in destination
                destination[row["sequence"]] = row
            break
    assert len(title) == records and len(prepared) == draws
    assert len(snapshots) == len(before) == len(after) == draws
    fixture_packets = set()
    for _ in range(records):
        next_direct, record, origin, packet, *words = take("<Q10I")
        assert next_direct in title and (title_thread, next_direct) in packets
        assert packet == packets[(title_thread, next_direct)]["header_physical"]
        row = title[next_direct]
        assert (record, origin, words[:4], words[4:]) == (
            row["record"], row["source"], row["record_words"], row["source_words"])
        assert packet not in fixture_packets
        fixture_packets.add(packet)
    assert len(fixture_packets) == records
    ranges = []
    for slot, count in enumerate(range_counts):
        owned = {}
        for _ in range(count):
            key = take("<2I")
            length = key[1]
            assert 0 < length <= (3 * 1024 * 1024 if slot == 1 else 128 * 1024)
            assert key not in owned and offset + length <= len(source)
            owned[key] = source[offset:offset + length]
            offset += length
        ranges.append(owned)
    range_hashes = [{key: fnv(data) for key, data in family.items()}
                    for family in ranges]
    sequences = set()
    used_packets = set()
    for _ in range(draws):
        (sequence, packet, shader, pixel, specialization, dynamic, count,
         host_format, endianness, *flat_ranges) = take("<QI4Q3I6I")
        assert sequence not in sequences and packet in fixture_packets
        sequences.add(sequence)
        used_packets.add(packet)
        keys = [tuple(flat_ranges[i:i + 2]) for i in (0, 2, 4)]
        assert all(key in ranges[slot] for slot, key in enumerate(keys))
        texture_rows = [take("<9I") for _ in range(2)]
        bitmap = take("<4Q")
        packed_count = take("<I")[0]
        assert packed_count <= 1024 and packed_count == 4 * sum(
            bits.bit_count() for bits in bitmap)
        packed = take(f"<{packed_count}I")
        system = take("<64I")
        fetch47 = take("<4I")
        raster, clip, depth = take("<3I")
        viewport = take("<6f")
        scissor = take("<4i")
        expected = next(row for row in prepared.values() if row["sequence"] == sequence)
        ordinal = expected["ordinal"]
        title_row = selected[ordinal]
        assert (expected["packet_physical"], expected["vertex_shader"],
                expected["pixel_shader"], expected["index_count"],
                expected["index_buffer_guest_base"], expected["index_buffer_length"]) == (
            packet, shader, pixel, count, *keys[2])
        assert title_row["title_direct_record"]
        assert host_format <= 2 and endianness <= 3
        assert keys[2][1] == count * 2
        assert (before[sequence]["packet"], before[sequence]["packed_hash"],
                before[sequence]["specialization"]) == (
            packet, fnv(packed), specialization)
        assert (after[sequence]["packet"], after[sequence]["system_hash"],
                after[sequence]["fetch_hash"], after[sequence]["dynamic"],
                after[sequence]["raster"], after[sequence]["clip"],
                after[sequence]["depth"]) == (
            packet, fnv(system), fnv(fetch47), dynamic, raster, clip, depth)
        assert viewport[2] > 0 and viewport[3] > 0
        assert scissor[0] < scissor[2] and scissor[1] < scissor[3]
        snapshot = snapshots[sequence]
        assert snapshot["packet"] == packet and snapshot["index_status"] == 1
        assert snapshot["index_hash"] == range_hashes[2][keys[2]]
        for slot, constant, stride in ((0, 95, 8), (1, 94, 3)):
            row = fetches[(ordinal, slot)]
            assert (row["fetch_constant"], row["stride_words"],
                    row["guest_base"], row["length"],
                    row["cpu_snapshot_status"], row["cpu_snapshot_hash"]) == (
                constant, stride, *keys[slot], 1, range_hashes[slot][keys[slot]])
        assert {row[0] for row in texture_rows} == set(textures[ordinal])
        for descriptor in texture_rows:
            row = textures[ordinal][descriptor[0]]
            assert descriptor == tuple(row[key] for key in (
                "fetch_constant", "type", "base_address", "mip_address",
                "format", "dimension", "width", "height", "stack_depth"))
    assert offset == len(source) and used_packets == fixture_packets
    assert sequences == set(snapshots) == set(before) == set(after)
    assert any(f"FH1 SNR03 manager owned scene output_frame={frame + 1} " in line
               and "written=true" in line for line in log_path.open(encoding="utf-8"))
    return {"source_frame": frame, "records": records, "draws": draws,
            "ranges": range_counts, "owned_bytes": sum(
                len(data) for family in ranges for data in family.values()),
            "fixture_sha256": hashlib.sha256(source).hexdigest()}


if __name__ == "__main__":
    assert len(sys.argv) == 4, "usage: verify-snr03-manager-fixture.py FIXTURE LOG LEDGER"
    print(json.dumps(verify(*(Path(value) for value in sys.argv[1:])), sort_keys=True))
