#!/usr/bin/env python3
"""Verify the owned car/scalar fixture against its strict same-frame ledger."""

import collections
import hashlib
import json
from pathlib import Path
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
        assert offset + size <= len(source), "truncated remainder fixture"
        result = struct.unpack_from(fmt, source, offset)
        offset += size
        return result

    def data(length):
        nonlocal offset
        assert offset + length <= len(source), "truncated remainder bytes"
        result = source[offset:offset + length]
        offset += length
        return result

    assert take("<8s")[0] == b"SNR03R1\0"
    frame, view, camera, car_count, scalar_count, draw_count, vertex_count, index_count = \
        take("<Q7I")
    assert view and camera and 0 < car_count <= 512 and 0 < scalar_count <= 512
    assert 0 < draw_count <= 4096 and vertex_count <= 4096 and index_count <= 4096
    assert any(take("<32I")), "missing title camera matrices"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["backend_frame"] == frame + 1
    role = runpy.run_path(str(Path(__file__).with_name(
        "partition-snr00-gate-a-slice.py")))["role"]
    families = {"selected_car_scene_list": 1, "selected_animated": 2,
                "selected_car_presentation": 3}
    selected = {row["ordinal"]: families[role(row)] for row in ledger["draws"]
                if role(row) in families}
    assert len(selected) == draw_count

    car = {}
    for _ in range(car_count):
        dispatch, target, words, owner, vtable, input_value = take("<6I")
        owner_call = take("<Q")[0]
        args = take("<7I")
        assert dispatch and target and owner and vtable in (0x82001618, 0x82003A54)
        assert dispatch not in car
        car[dispatch] = (target, words, owner, vtable, input_value,
                         owner_call, args)
    scalar = {}
    for _ in range(scalar_count):
        direct, ordinal = take("<2Q")
        packet, caller, obj, vtable, command, selector, count = take("<7I")
        assert packet and caller in (0x82415A28, 0x82443B98,
                                    0x82443C40, 0x82444018)
        assert packet not in scalar
        scalar[packet] = (direct, ordinal, caller, obj, vtable,
                          command, selector, count)

    ranges = []
    for count in (vertex_count, index_count):
        owned = {}
        for _ in range(count):
            key = take("<2I")
            assert 0 < key[1] <= 3 * 1024 * 1024 and key not in owned
            owned[key] = data(key[1])
        ranges.append(owned)
    range_hashes = [{key: fnv(value) for key, value in owned.items()}
                    for owned in ranges]

    prepared, fetches, indices, textures = {}, collections.defaultdict(dict), {}, \
        collections.defaultdict(dict)
    before, after, title_car, title_scalar, output = {}, {}, {}, {}, None
    for line in log_path.open(encoding="utf-8", errors="replace"):
        for marker in ("FH1 SNR01 prepared draw ",
                       "FH1 SNR01 prepared vertex fetch ",
                       "FH1 SNR03 probe index snapshot ",
                       "FH1 SNR01 prepared texture fetch ",
                       "FH1 SNR03 remainder prepared ",
                       "FH1 SNR03 remainder final ",
                       "FH1 SNR01 scene indirect packet ",
                       "FH1 SNR03 scalar title record "):
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            if row["frame"] != (frame if marker.endswith((
                    "scene indirect packet ", "scalar title record ")) else frame + 1):
                break
            if marker.endswith("prepared draw ") and row["ordinal"] in selected:
                assert row["ordinal"] not in prepared
                prepared[row["ordinal"]] = row
            elif marker.endswith("prepared vertex fetch ") and row["draw"] in selected:
                assert row["slot"] not in fetches[row["draw"]]
                fetches[row["draw"]][row["slot"]] = row
            elif marker.endswith("index snapshot "):
                assert row["sequence"] not in indices
                indices[row["sequence"]] = row
            elif marker.endswith("prepared texture fetch ") and row["draw"] in selected:
                assert row["fetch_constant"] not in textures[row["draw"]]
                textures[row["draw"]][row["fetch_constant"]] = row
            elif marker.endswith("remainder prepared "):
                assert row["sequence"] not in before
                before[row["sequence"]] = row
            elif marker.endswith("remainder final "):
                assert row["sequence"] not in after
                after[row["sequence"]] = row
            elif marker.endswith("scene indirect packet ") and \
                    row["header_physical"] in car:
                assert row["header_physical"] not in title_car
                title_car[row["header_physical"]] = row
            elif marker.endswith("scalar title record "):
                assert row["packet"] not in title_scalar
                title_scalar[row["packet"]] = row
            break
        if "FH1 SNR03 remainder owned scene output_frame=" in line and \
                f"output_frame={frame + 1} " in line:
            assert output is None
            output = line
    assert set(prepared) == set(selected)
    assert set(car) == set(title_car) and set(scalar) == set(title_scalar)
    assert len(before) == len(after) == draw_count
    assert output and f"draws={draw_count} " in output and \
        "rejected=false" in output and "written=true" in output
    for dispatch, row in car.items():
        title = title_car[dispatch]
        assert row == (title["target_physical"], title["words"],
                       title["flush_owner"], title["flush_owner_first_word"],
                       title["flush_input"], title["owner_call"],
                       tuple(title["owner_args"]))
    for packet, row in scalar.items():
        title = title_scalar[packet]
        assert row == (title["direct"], title["scalar"], title["caller"],
                       title["object"], title["vtable"], title["command"],
                       title["selector"], title["count"])

    by_sequence = {row["sequence"]: (ordinal, row)
                   for ordinal, row in prepared.items()}
    seen, used_vertices, used_indices = set(), set(), set()
    counts = collections.Counter()
    for _ in range(draw_count):
        family, title_key = take("<2I")
        sequence = take("<Q")[0]
        packet = take("<I")[0]
        shader, pixel, specialization, dynamic = take("<4Q")
        count, guest_primitive, host_primitive, index_type, host_format, endian = \
            take("<6I")
        fetch_count = take("<I")[0]
        assert 0 < fetch_count <= 3
        owned_fetches = [take("<4I") for _ in range(fetch_count)]
        index_range = take("<2I")
        texture_count = take("<I")[0]
        assert texture_count <= 16
        owned_textures = [take("<9I") for _ in range(texture_count)]
        bitmap = take("<4Q")
        packed_count = take("<I")[0]
        assert packed_count <= 1024 and packed_count == 4 * sum(
            bits.bit_count() for bits in bitmap)
        packed = take(f"<{packed_count}I")
        system = take("<64I")
        bound_fetch = take("<192I")
        raster, clip, depth = take("<3I")
        viewport = take("<6f")
        scissor = take("<4i")
        assert sequence in by_sequence and sequence not in seen
        seen.add(sequence)
        ordinal, draw = by_sequence[sequence]
        assert family == selected[ordinal] and packet == draw["packet_physical"]
        assert shader == draw["vertex_shader"] and pixel == draw["pixel_shader"]
        assert count == draw["index_count"] and index_type == draw["index_buffer_type"]
        assert guest_primitive == draw["guest_primitive_type"]
        assert fetch_count == draw["vertex_fetch_count"]
        assert texture_count == draw["texture_fetch_count"]
        assert index_range == (draw["index_buffer_guest_base"],
                               draw["index_buffer_length"])
        assert 0 <= host_primitive <= 32 and host_format <= 2 and endian <= 3
        assert title_key in (car if family == 1 else scalar)
        assert title_key == (draw["dispatch_packet_physical"] if family == 1
                             else packet)
        for slot, (constant, stride, base, length) in enumerate(owned_fetches):
            logged = fetches[ordinal][slot]
            assert (constant, stride, base, length) == (
                logged["fetch_constant"], logged["stride_words"],
                logged["guest_base"], logged["length"])
            key = (base, length)
            assert range_hashes[0].get(key) == logged["cpu_snapshot_hash"]
            assert bound_fetch[constant * 2] & 0x1FFFFFFC == base
            assert bound_fetch[constant * 2 + 1] & 0x03FFFFFC == length
            used_vertices.add(key)
        index = indices[sequence]
        assert index["packet"] == packet and index["status"] == 1
        assert range_hashes[1].get(index_range) == index["hash"]
        used_indices.add(index_range)
        assert {row[0] for row in owned_textures} == set(textures[ordinal])
        for texture in owned_textures:
            row = textures[ordinal][texture[0]]
            assert texture == tuple(row[key] for key in (
                "fetch_constant", "type", "base_address", "mip_address",
                "format", "dimension", "width", "height", "stack_depth"))
        assert before[sequence]["packet"] == packet
        assert before[sequence]["family"] == family
        assert before[sequence]["packed_hash"] == fnv(packed)
        final = after[sequence]
        assert (final["packet"], final["family"], final["dynamic"],
                final["raster"], final["clip"], final["depth"]) == (
                packet, family, dynamic, raster, clip, depth)
        assert final["system_hash"] == fnv(system)
        assert final["fetch_hash"] == fnv(bound_fetch)
        assert viewport[2] > 0 and viewport[3] > 0 and scissor[2] > scissor[0]
        counts[family] += 1
    assert seen == set(by_sequence) and used_vertices == set(ranges[0])
    assert used_indices == set(ranges[1]) and offset == len(source)
    return {"source_frame": frame, "draws": dict(counts),
            "vertex_ranges": len(ranges[0]), "index_ranges": len(ranges[1]),
            "fixture_sha256": hashlib.sha256(source).hexdigest()}


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: verify-snr03-remainder-fixture.py FIXTURE LOG LEDGER")
    print(json.dumps(verify(Path(sys.argv[1]), Path(sys.argv[2]),
                            Path(sys.argv[3])), sort_keys=True))
