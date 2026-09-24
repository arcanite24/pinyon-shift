#!/usr/bin/env python3
"""Validate a bounded SNR-03 owned-scene fixture against its replay log."""

import argparse
import hashlib
import json
from pathlib import Path
import struct


def verify(path, log_path):
    data = path.read_bytes()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    position = 0

    def take(fmt):
        nonlocal position
        size = struct.calcsize(fmt)
        assert position + size <= len(data), "truncated fixture"
        value = struct.unpack_from(fmt, data, position)
        position += size
        return value

    magic = take("<8s")[0]
    assert magic in (b"SNR03F1\0", b"SNR03F2\0", b"SNR03F3\0", b"SNR03F4\0")
    extended = magic != b"SNR03F1\0"
    sequenced = magic in (b"SNR03F3\0", b"SNR03F4\0")
    final_bound = magic == b"SNR03F4\0"
    source_frame, view, camera, count = take("<QIII")
    assert 0 < count <= 512
    camera80 = take("<16I")
    camera144 = take("<16I")
    items = []
    states = {}
    total_bytes = total_variants = 0
    for _ in range(count):
        owner, record, descriptor, address, size, packet, bucket = take("<6IQ")
        guest_count, byte_count, constant_count, variant_count = take("<4I")
        assert constant_count == 24 and 0 < variant_count <= 4
        assert byte_count <= 32768 and byte_count == (size & 0x03FFFFFC)
        assert guest_count > 0 and guest_count % 4 == 0
        assert guest_count * 4 == byte_count
        constants = take("<96I")
        assert len(constants) == 96
        pixel_registers = take("<3I") if extended else ()
        pixel_constants = take("<12I") if extended else ()
        if extended:
            assert 0 <= pixel_registers[0] < pixel_registers[1] < pixel_registers[2] < 256
        assert position + byte_count <= len(data), "truncated vertex bytes"
        vertices = data[position:position + byte_count]
        position += byte_count
        variants = {}
        for _ in range(variant_count):
            dynamic = take("<Q")[0]
            sequence = take("<Q")[0] if sequenced else None
            system = take("<64I" if extended else "<40I")
            fetch = take("<4I")
            final_constants = take("<92I") if final_bound else constants
            assert dynamic not in variants
            assert fetch[2] & 0x1FFFFFFC == address & 0x1FFFFFFC
            assert fetch[3] & 0x03FFFFFC == byte_count
            variants[dynamic] = (system, fetch)
            states[packet, f"{dynamic:016X}"] = (
                sequence, system, fetch, final_constants)
        items.append(dict(owner=owner, record=record,
                          vertex_descriptor=descriptor, vertex_address=address,
                          vertex_size=size, packet_physical=packet,
                          bucket_entry=bucket, vertex_sha256=hashlib.sha256(vertices).hexdigest(),
                          variants=len(variants), constants=constants,
                          pixel_registers=pixel_registers,
                          pixel_constants=pixel_constants))
        total_bytes += byte_count
        total_variants += variant_count
    assert position == len(data), "trailing fixture bytes"
    assert len({item["packet_physical"] for item in items}) == count

    published = [json.loads(line.split("FH1 SNR03 item ", 1)[1])
                 for line in lines if "FH1 SNR03 item {" in line
                 and f'"frame":{source_frame},' in line]
    assert len(published) == count
    for index, (actual, expected) in enumerate(zip(items, published), 1):
        assert expected["frame"] == source_frame and expected["ordinal"] == index
        assert all(actual[key] == expected[key] for key in (
            "owner", "record", "vertex_descriptor", "vertex_address",
            "vertex_size", "packet_physical", "bucket_entry"))
    registers = (128, 129, 130, 131, 157, 158, 159, 160, 161, 163,
                 214, 215, 221, 241, 242, 243, 244, 245, 250, 251,
                 253, 254, 255, 256)
    by_packet = {item["packet_physical"]: item for item in items}
    bindings = [json.loads(line.split("FH1 scene binding ", 1)[1])
                for line in lines if "FH1 scene binding {" in line
                and f'"frame":{source_frame + 1},' in line]
    selected = [row for row in bindings if row["packet_physical"] in by_packet]
    assert selected
    for row in selected:
        constants = {int(key): value for part in row["constants"].split(";")
                     if ":" in part and part[0].isdigit()
                     for key, value in [part.split(":", 1)]}
        words = by_packet[row["packet_physical"]]["constants"]
        for index, register in enumerate(registers):
            raw = constants[0x4000 + register * 4]
            assert words[index * 4:index * 4 + 4] == tuple(
                int(raw[i:i + 8], 16) for i in range(0, 32, 8))
        if extended:
            item = by_packet[row["packet_physical"]]
            for index, register in enumerate(item["pixel_registers"]):
                raw = constants[0x4000 + (256 + register) * 4]
                assert item["pixel_constants"][index * 4:index * 4 + 4] == tuple(
                    int(raw[i:i + 8], 16) for i in range(0, 32, 8))
    if extended:
        pixel_rows = [json.loads(line.split("FH1 SNR03 pixel constant ", 1)[1])
                      for line in lines if "FH1 SNR03 pixel constant {" in line
                      and f'"frame":{source_frame + 1},' in line]
        expected_pixels = {
            (item["packet_physical"], register):
            item["pixel_constants"][index * 4:index * 4 + 4]
            for item in items
            for index, register in enumerate(item["pixel_registers"])
        }
        assert len(pixel_rows) == len(expected_pixels) == 3 * count
        for row in pixel_rows:
            assert row["frame"] == source_frame + 1
            assert tuple(row["words"]) == expected_pixels.pop(
                (row["packet"], row["register"]))
        assert not expected_pixels
    final = [json.loads(line.split("FH1 SNR03 final draw state ", 1)[1])
             for line in lines if "FH1 SNR03 final draw state {" in line
             and f'"frame":{source_frame + 1},' in line]
    assert len(final) == len(states)
    assert {(row["packet"], row["dynamic"]) for row in final} == set(states)
    for row in final:
        sequence, system, fetch, final_constants = states[
            row["packet"], row["dynamic"]]
        if sequenced:
            assert row["sequence"] == sequence
        assert system[:8] == tuple(row["system0"] + row["system1"])
        assert system[32:40] == tuple(row["system8"] + row["system9"])
        if extended:
            assert system[56:64] == tuple(row["system14"] + row["system15"])
        assert fetch == tuple(row["fetch47"])
        if final_bound:
            value = 14695981039346656037
            for word in final_constants:
                value = ((value ^ word) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
            assert value == row["bound_vertex_hash"]
    if sequenced:
        selected_color = [row for row in selected
                          if row["vertex_shader"] == "5834939992FFC765" and
                          row["pixel_shader"] == "C2F1242C2535A57E"]
        assert {(row["packet_physical"], row["dynamic"], row["sequence"])
                for row in selected_color} == {
                    (packet, dynamic, state[0])
                    for (packet, dynamic), state in states.items()}
        assert len({state[0] for state in states.values()}) == len(states)
        rows = [json.loads(line.split("FH1 SNR03 camera row ", 1)[1])
            for line in lines if "FH1 SNR03 camera row {" in line
            and f'"frame":{source_frame},' in line]
    assert len(rows) == 8
    for offset, words in ((80, camera80), (144, camera144)):
        assert tuple(word for row in sorted(
            (row for row in rows if row["offset"] == offset),
            key=lambda row: row["row"]) for word in row["words"]) == words
    consumed = [line for line in lines if "FH1 SNR03 geometry consumed " in line
                and f"source_frame={source_frame} " in line]
    assert len(consumed) == 1
    assert all(token in consumed[0] for token in (
        f"source_frame={source_frame}", f"items={count}",
        f"bytes={total_bytes}", f"final_variants={total_variants}"))
    assert any(f"FH1 SNR03 fixture output_frame={source_frame + 1} written=true"
               in line for line in lines)
    return dict(schema=magic.decode("ascii").rstrip("\0"),
                source_frame=source_frame, view=view, camera=camera,
                items=count, vertex_bytes=total_bytes,
                final_variants=total_variants,
                fixture_sha256=hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.fixture, args.log), sort_keys=True))


if __name__ == "__main__":
    main()
