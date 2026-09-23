#!/usr/bin/env python3
"""Join the owned procedural-character fixture to title and final GPU draws."""

import hashlib
import json
import math
from pathlib import Path
import runpy
import struct
import sys


def fnv(values):
    result = 14695981039346656037
    for value in values:
        result = ((result ^ value) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return result


def verify(fixture: Path, log: Path, ledger_path: Path):
    source = fixture.read_bytes()
    offset = 0

    def take(fmt):
        nonlocal offset
        size = struct.calcsize(fmt)
        assert offset + size <= len(source), "truncated character fixture"
        row = struct.unpack_from(fmt, source, offset)
        offset += size
        return row

    assert take("<8s")[0] == b"SNR03C1\0"
    frame, view, camera, count, draws = take("<Q4I")
    assert 0 < count <= 64 and 0 < draws <= 128
    assert any(take("<32I"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["backend_frame"] == frame + 1
    role = runpy.run_path(str(Path(__file__).with_name(
        "partition-snr00-gate-a-slice.py")))["role"]
    selected = {row["ordinal"]: row for row in ledger["draws"]
                if role(row) == "selected_procedural_character"}
    assert len(selected) == draws
    title, prepared, final, backend = {}, {}, {}, {}
    for line in log.open(encoding="utf-8", errors="replace"):
        for marker, destination in (
            ("FH1 SNR03 character item ", title),
            ("FH1 SNR03 character prepared ", prepared),
            ("FH1 SNR03 character final ", final),
            ("FH1 SNR01 prepared draw ", backend),
        ):
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            if marker == "FH1 SNR03 character item ":
                assert row["frame"] == frame and row["packet_physical"] not in destination
                destination[row["packet_physical"]] = row
            elif marker == "FH1 SNR01 prepared draw ":
                if row["frame"] == frame + 1 and row["ordinal"] in selected:
                    assert row["ordinal"] not in destination
                    destination[row["ordinal"]] = row
            else:
                assert row["frame"] == frame + 1 and row["sequence"] not in destination
                destination[row["sequence"]] = row
            break
    assert len(title) == count and len(backend) == len(prepared) == len(final) == draws
    assert {row["ordinal"] for row in title.values()} == set(range(1, count + 1))
    fixture_packets = set()
    fixture_sequences = set()
    vertex_bytes = 0
    for ordinal in range(1, count + 1):
        record, descriptor, address, size, packet, bucket = take("<5IQ")
        length, variants = take("<2I")
        assert 0 < length <= 32768 and length == (size & 0x03FFFFFC)
        assert 0 < variants <= 8 and packet not in fixture_packets
        fixture_packets.add(packet)
        row = title[packet]
        assert (row["ordinal"], row["record"], row["vertex_descriptor"],
                row["vertex_address"], row["vertex_size"], row["bucket_entry"]) == (
            ordinal, record, descriptor, address, size, bucket)
        assert offset + length <= len(source)
        vertices = source[offset:offset + length]
        offset += length
        vertex_bytes += length
        vertex_hash = fnv(vertices)
        for _ in range(variants):
            sequence, vs, ps, specialization, dynamic, count_vertices, words = take("<5Q2I")
            bitmap = take("<4Q")
            assert words <= 1024 and words == sum(x.bit_count() for x in bitmap) * 4
            packed = take(f"<{words}I")
            system = take("<64I")
            fetch = take("<4I")
            mode, clip, depth = take("<3I")
            viewport = take("<6f")
            scissor = take("<4i")
            assert sequence not in fixture_sequences and count_vertices * 4 == length
            fixture_sequences.add(sequence)
            assert fetch[2] & 0x1FFFFFFC == address & 0x1FFFFFFC
            assert fetch[3] & 0x03FFFFFC == length
            assert all(0 <= value <= 0xFFFFFFFF for value in system)
            assert all(map(math.isfinite, viewport)) and viewport[2] > 0 and viewport[3] > 0
            assert scissor[0] < scissor[2] and scissor[1] < scissor[3]
            before, after = prepared[sequence], final[sequence]
            assert (before["packet"], before["count"], before["vertex_hash"],
                    before["bitmap"], before["packed_hash"],
                    before["specialization"]) == (
                packet, count_vertices, vertex_hash, list(bitmap),
                fnv(packed), specialization)
            assert (after["packet"], after["system_hash"], after["fetch_hash"],
                    after["dynamic"], after["mode"], after["clip"],
                    after["depth"]) == (
                packet, fnv(system), fnv(fetch), dynamic, mode, clip, depth)
            expected = next(row for row in backend.values() if row["sequence"] == sequence)
            assert (expected["packet_physical"], expected["vertex_shader"],
                    expected["pixel_shader"], expected["index_count"]) == (
                packet, vs, ps, count_vertices)
            assert selected[expected["ordinal"]]["title_second_draw_bound_record"] == record
    assert offset == len(source) and fixture_sequences == {
        row["sequence"] for row in backend.values()}
    assert fixture_packets == set(title)
    assert any(f"FH1 SNR03 character owned scene output_frame={frame + 1} " in line
               and "written=true" in line for line in log.open(encoding="utf-8"))
    return {"source_frame": frame, "view": view, "camera": camera,
            "items": count, "draws": draws, "vertex_bytes": vertex_bytes,
            "fixture_sha256": hashlib.sha256(source).hexdigest()}


if __name__ == "__main__":
    assert len(sys.argv) == 4, "usage: verify-snr03-character-fixture.py FIXTURE LOG LEDGER"
    print(json.dumps(verify(*(Path(value) for value in sys.argv[1:])), sort_keys=True))
