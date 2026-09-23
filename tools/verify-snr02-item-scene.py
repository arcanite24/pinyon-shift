"""Verify the owned procedural-item frame fixture against its title/GPU trace."""

import collections
import json
import math
from pathlib import Path
import struct
import sys


CANDIDATE = {
    "14020500/00030000/00010400/00000003",
    "14020500/000C0000/00010400/00000003",
}


def hash_bytes(data: bytes) -> int:
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def hash_words(words) -> int:
    value = 14695981039346656037
    for word in words:
        value = ((value ^ word) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def verify(fixture: Path, log: Path, ledger: Path) -> dict:
    census = json.loads(ledger.read_text())
    source_frame = census["backend_frame"] - 1
    selected = collections.defaultdict(list)
    for row in census["draws"]:
        if row["target"] in CANDIDATE and row["title_packet_caller_lr"] == 0x82415D1C:
            assert row["title_packet_source_frame"] == source_frame
            selected[row["title_item_call"]].append(row)
    assert selected
    title, fetches, prepared, draw_states, final_states = {}, {}, {}, {}, {}
    textures = collections.defaultdict(list)
    for line in log.read_text(encoding="utf-8-sig").splitlines():
        for marker, destination in (("FH1 SNR02 item payload ", title),
                                    ("FH1 SNR01 prepared vertex fetch ", fetches),
                                    ("FH1 SNR01 prepared draw ", prepared),
                                    ("FH1 SNR02 item draw state ", draw_states),
                                    ("FH1 SNR02 item final state ", final_states),
                                    ("FH1 SNR01 prepared texture fetch ", textures)):
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            frame = source_frame if destination is title else census["backend_frame"]
            if row["frame"] != frame:
                continue
            if destination is fetches and (row["fetch_constant"], row["stride_words"]) != (95, 10):
                continue
            key = (row["call"] if destination is title else
                   row["ordinal"] if destination is prepared else
                   row["sequence"] if destination is draw_states or destination is final_states else
                   row["draw"])
            if destination is textures:
                destination[key].append(row)
                continue
            assert key not in destination
            destination[key] = row
    data = fixture.read_bytes()
    magic, frame, count = struct.unpack_from("<8sQI", data)
    assert magic in (b"SNR02I1\0", b"SNR02I2\0", b"SNR02I3\0") and frame == source_frame
    assert count == len(selected) and count <= 512
    camera = struct.unpack_from("<32I", data, 20)
    assert any(camera)
    offset = 148
    calls, total_draws, total_bytes = set(), 0, 0
    shader_bitmaps = collections.defaultdict(set)
    for _ in range(count):
        values = struct.unpack_from("<QII23I17I3I", data, offset)
        offset += 188
        call, packet, kind = values[:3]
        descriptor, runtime = values[3:26], values[26:43]
        base, length, draws = values[43:46]
        assert 0 < length <= 256 * 1024 and offset + length <= len(data)
        vertex = data[offset:offset + length]
        offset += length
        assert call in selected and call not in calls
        calls.add(call)
        item = title[call]
        assert kind == item["kind"]
        assert "".join(f"{word:08X}" for word in descriptor) == item["descriptor_words"]
        assert "".join(f"{word:08X}" for word in runtime) == item["runtime_words"]
        assert draws == len(selected[call])
        expected = {}
        for row in selected[call]:
            fetch = fetches[row["ordinal"]]
            assert row["packet_physical"] == packet == fetch["packet_physical"]
            assert (fetch["guest_base"], fetch["length"],
                    fetch["cpu_snapshot_status"], fetch["cpu_snapshot_hash"]) == (
                base, length, 1, hash_bytes(vertex))
            if magic != b"SNR02I1\0":
                observed = prepared[row["ordinal"]]
                assert observed["packet_physical"] == packet
                assert observed["sequence"] not in expected
                expected[observed["sequence"]] = (row, observed)
        if magic != b"SNR02I1\0":
            seen = set()
            for _ in range(draws):
                sequence, vs, ps, dynamic, count_vertices, count_textures = struct.unpack_from(
                    "<QQQQII", data, offset)
                offset += 40
                texture_words = struct.unpack_from("<18I", data, offset)
                offset += 72
                if magic == b"SNR02I3\0":
                    bitmap = struct.unpack_from("<4Q", data, offset)
                    offset += 32
                    mapped, = struct.unpack_from("<I", data, offset)
                    offset += 4
                    assert mapped == sum(word.bit_count() for word in bitmap)
                    assert mapped == (25 if vs in (0x3BC346726C1C2535,
                                                   0xBDFD2AD68464101A) else 23)
                    shader_bitmaps[vs].add(bitmap)
                vertex_constants = struct.unpack_from("<1024I", data, offset)
                offset += 4096
                system = struct.unpack_from("<64I", data, offset)
                offset += 256
                fetch47 = struct.unpack_from("<4I", data, offset)
                offset += 16
                if magic == b"SNR02I3\0":
                    assert count_vertices > 0 and count_vertices % 4 == 0
                    assert not system[0] & 1 and system[4] == system[5] == 0
                    assert system[6] <= system[7]
                    assert fetch47[2] & 3 == 3
                    assert fetch47[2] & 0x1FFFFFFC == base & 0x1FFFFFFC
                    assert fetch47[3] & 0x03FFFFFC == length
                    floats = [struct.unpack("<f", struct.pack("<I", system[i]))[0]
                              for i in (32, 33, 34, 36, 37, 38)]
                    sx, sy, sz, ox, oy, oz = floats
                    assert sx == 1 and sz == -1 and oz == 1
                    assert math.isfinite(sy) and sy > 0 and math.isfinite(oy)
                    assert abs(ox - 1 / 1280) < 1e-6
                    assert abs((oy + 1) / sy - 1 + 1 / 720) < 1e-5
                assert sequence in expected and sequence not in seen
                seen.add(sequence)
                row, observed = expected[sequence]
                assert (vs, ps, count_vertices, count_textures) == (
                    row["vertex_shader"], row["pixel_shader"],
                    row["index_count"], observed["texture_fetch_count"])
                assert count_textures <= 2
                assert len(textures[row["ordinal"]]) == count_textures
                for slot, fetch in enumerate(textures[row["ordinal"]]):
                    actual = tuple(texture_words[slot * 9:(slot + 1) * 9])
                    assert actual == tuple(fetch[key] for key in (
                        "fetch_constant", "type", "base_address", "mip_address",
                        "format", "dimension", "width", "height", "stack_depth"))
                expected_draw_state = {
                    "frame": census["backend_frame"], "packet": packet,
                    "sequence": sequence, "vertex_hash": hash_words(vertex_constants)}
                if magic == b"SNR02I3\0":
                    expected_draw_state.update(bitmap=list(bitmap), mapped=mapped)
                assert draw_states[sequence] == expected_draw_state
                expected_final = {
                    "frame": census["backend_frame"], "packet": packet,
                    "sequence": sequence, "dynamic": dynamic,
                    "system_hash": hash_words(system),
                    "fetch47_hash": hash_words(fetch47)}
                if "vertex_changed" in final_states[sequence]:
                    expected_final.update(vertex_changed=False,
                                          final_vertex_hash=hash_words(vertex_constants))
                if "bound_changed" in final_states[sequence]:
                    packed = [word for reg in range(256)
                              if bitmap[reg // 64] & (1 << (reg % 64))
                              for word in vertex_constants[reg * 4:reg * 4 + 4]]
                    expected_final.update(bound_changed=False,
                                          bound_vertex_hash=hash_words(packed))
                assert final_states[sequence] == expected_final
            assert seen == set(expected)
        total_draws += draws
        total_bytes += length
    assert calls == set(selected) and offset == len(data)
    assert all(len(bitmaps) == 1 for bitmaps in shader_bitmaps.values())
    return {"source_frame": frame, "version": magic.decode().rstrip("\0"),
            "calls": count, "draws": total_draws,
            "owned_vertex_bytes": total_bytes, "fixture_bytes": len(data),
            "vertex_registers": {
                f"{shader:016X}": [reg for reg in range(256)
                                 if next(iter(bitmaps))[reg // 64] & (1 << (reg % 64))]
                for shader, bitmaps in sorted(shader_bitmaps.items())}}


if __name__ == "__main__":
    assert len(sys.argv) == 4, "usage: verify-snr02-item-scene.py FIXTURE LOG LEDGER"
    print(json.dumps(verify(*(Path(arg) for arg in sys.argv[1:])), sort_keys=True))
