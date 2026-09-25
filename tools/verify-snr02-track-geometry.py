"""Join selected view-8 track draws to bounded CPU geometry snapshots."""

import collections
import json
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


def read_fixture(path: Path):
    data = path.read_bytes()
    magic, source, targets, draws, vertices, indices = struct.unpack_from(
        "<8sQ4I", data)
    assert magic in (b"SNR02T1\0", b"SNR02T2\0", b"SNR02T3\0",
                     b"SNR02T4\0", b"SNR02T5\0")
    assert targets <= 256 and draws <= 4096
    assert vertices <= 4096 and indices <= 4096
    offset = 32
    camera = struct.unpack_from("<32I", data, offset)
    offset += 128
    assert any(camera)
    title_targets = set(struct.unpack_from(f"<{targets}I", data, offset))
    assert len(title_targets) == targets
    offset += targets * 4
    ranges = []
    for count in (vertices, indices):
        owned = {}
        for _ in range(count):
            base, length = struct.unpack_from("<II", data, offset)
            offset += 8
            assert 0 < length <= 512 * 1024 and offset + length <= len(data)
            key = (base, length)
            assert key not in owned
            owned[key] = data[offset:offset + length]
            offset += length
        ranges.append(owned)
    records = {}
    for _ in range(draws):
        values = struct.unpack_from("<QQQ8I", data, offset)
        offset += 56
        assert values[0] not in records
        final = None
        if magic in (b"SNR02T2\0", b"SNR02T3\0", b"SNR02T4\0", b"SNR02T5\0"):
            if magic in (b"SNR02T3\0", b"SNR02T4\0", b"SNR02T5\0"):
                (specialization, dynamic, host_index_format,
                 host_primitive, host_restart, index_endianness) = (
                    struct.unpack_from("<QQ4I", data, offset))
                offset += 32
            else:
                specialization, dynamic, host_index_format = struct.unpack_from(
                    "<QQI", data, offset)
                offset += 20
                host_primitive = host_restart = index_endianness = None
            bitmap = struct.unpack_from("<4Q", data, offset)
            offset += 32
            packed_count, = struct.unpack_from("<I", data, offset)
            offset += 4
            assert packed_count <= 1024
            packed = struct.unpack_from(f"<{packed_count}I", data, offset)
            offset += packed_count * 4
            system = struct.unpack_from("<64I", data, offset)
            offset += 256
            fetch47 = struct.unpack_from("<4I", data, offset)
            offset += 16
            raster = None
            if magic in (b"SNR02T4\0", b"SNR02T5\0"):
                raster = struct.unpack_from("<3I6f4i", data, offset)
                offset += 52
            material = None
            if magic == b"SNR02T5\0":
                pixel_specialization, = struct.unpack_from("<Q", data, offset)
                offset += 8
                pixel_bitmap = struct.unpack_from("<4Q", data, offset)
                offset += 32
                pixel_count, = struct.unpack_from("<I", data, offset)
                offset += 4
                assert pixel_count <= 1024 and pixel_count % 4 == 0
                assert sum(word.bit_count() for word in pixel_bitmap) * 4 == pixel_count
                pixel_packed = struct.unpack_from(f"<{pixel_count}I", data, offset)
                offset += pixel_count * 4
                texture_count, = struct.unpack_from("<I", data, offset)
                offset += 4
                assert texture_count <= 32
                textures = []
                for _ in range(texture_count):
                    textures.append(struct.unpack_from("<9I", data, offset))
                    offset += 36
                assert all(0 <= tex[0] < 32 for tex in textures)
                assert all(a[0] < b[0] for a, b in zip(textures, textures[1:]))
                material = (pixel_specialization, pixel_bitmap,
                            pixel_packed, textures)
            assert sum(word.bit_count() for word in bitmap) * 4 == packed_count
            final = (specialization, dynamic, host_index_format,
                     host_primitive, host_restart, index_endianness,
                     bitmap, packed, system, fetch47, raster, material)
        records[values[0]] = (values, final)
    assert offset == len(data)
    return source, title_targets, ranges[0], ranges[1], records, magic


def verify(log_path: Path, ledger_path: Path, fixture_path: Path) -> dict:
    ledger = json.loads(ledger_path.read_text())
    backend = ledger["backend_frame"]
    source = backend - 1
    selected = {
        row["ordinal"]: row for row in ledger["draws"]
        if row["classification"] == "view_owner"
        and row["view_call"] == 8
        and row["flush_caller_lr"] == 0x824170BC
        and row["target"] in CANDIDATE
    }
    assert selected and len(selected) <= 4096
    title_targets = set()
    prepared, vertices, indices, finals, rasters = {}, {}, {}, {}, {}
    for line in log_path.open(encoding="utf-8-sig", errors="replace"):
        for marker, destination in (
            ("FH1 SNR01 scene indirect packet ", "title"),
            ("FH1 SNR01 prepared draw ", "draw"),
            ("FH1 SNR01 prepared vertex fetch ", "vertex"),
            ("FH1 SNR02 track geometry ", "index"),
            ("FH1 SNR02 track final state ", "final"),
            ("FH1 SNR02 track raster state ", "raster"),
        ):
            if marker not in line:
                continue
            row = json.loads(line.split(marker, 1)[1])
            if destination == "title":
                if (row["frame"] == source and row["view_call"] == 8
                        and row["flush_caller_lr"] == 0x824170BC):
                    title_targets.add(row["target_physical"])
            elif row["frame"] == backend:
                if destination == "draw":
                    assert row["ordinal"] not in prepared
                    prepared[row["ordinal"]] = row
                elif destination == "vertex" and row["fetch_constant"] == 95:
                    assert row["draw"] not in vertices
                    vertices[row["draw"]] = row
                elif destination == "index":
                    assert row["sequence"] not in indices
                    assert row["captured"]
                    indices[row["sequence"]] = row
                elif destination == "final":
                    assert row["sequence"] not in finals
                    finals[row["sequence"]] = row
                elif destination == "raster":
                    assert row["sequence"] not in rasters
                    rasters[row["sequence"]] = row
            break
    assert title_targets == {row["execution_command_buffer"]
                             for row in selected.values()}
    assert len(indices) == len(selected)
    fixture_source, fixture_targets, owned_vertices, owned_indices, records, magic = (
        read_fixture(fixture_path))
    assert fixture_source == source and fixture_targets == title_targets
    assert len(records) == len(selected)
    if magic in (b"SNR02T2\0", b"SNR02T3\0", b"SNR02T4\0", b"SNR02T5\0"):
        assert len(finals) == len(selected)
    if magic in (b"SNR02T4\0", b"SNR02T5\0"):
        assert len(rasters) == len(selected)
    vertex_versions = collections.defaultdict(set)
    index_versions = collections.defaultdict(set)
    failures = collections.Counter()
    vertex_bytes = index_bytes = 0
    for ordinal, row in selected.items():
        draw = prepared[ordinal]
        vertex = vertices[ordinal]
        index = indices[draw["sequence"]]
        assert draw["packet_physical"] == row["packet_physical"] == index["packet"]
        assert draw["command_buffer"] == row["execution_command_buffer"]
        assert draw["index_buffer_guest_base"] == index["index_base"]
        assert draw["index_buffer_length"] == index["index_length"]
        assert draw["guest_primitive_type"] in (4, 6) and \
            draw["index_buffer_type"] == 1
        assert 4 <= vertex["stride_words"] <= 9 and draw["vertex_fetch_count"] == 1
        record, final = records[draw["sequence"]]
        assert record[1:7] == (draw["vertex_shader"], draw["pixel_shader"],
                               draw["packet_physical"], draw["command_buffer"],
                               draw["index_count"], vertex["stride_words"])
        assert record[7:9] == (vertex["guest_base"], vertex["length"])
        assert record[9:11] == (index["index_base"], index["index_length"])
        if final:
            (specialization, dynamic, host_index_format, host_primitive,
             host_restart, index_endianness, bitmap, packed, system, fetch47,
             raster, material) = final
            final_log = finals[draw["sequence"]]
            assert (specialization, host_index_format) == (
                index["specialization"], index["host_index_format"])
            if magic in (b"SNR02T3\0", b"SNR02T4\0", b"SNR02T5\0"):
                assert (host_primitive, host_restart, index_endianness) == (
                    index["host_primitive"], index["host_restart"],
                    index["index_endianness"])
                assert host_primitive == draw["guest_primitive_type"]
                assert host_restart == (host_primitive == 6)
                assert system[4] == index_endianness
            if raster:
                mode, clip, depth = raster[:3]
                viewport_words = struct.unpack("<6I", struct.pack("<6f", *raster[3:9]))
                scissor_words = [word & 0xFFFFFFFF for word in raster[9:13]]
                assert (mode, clip, depth, hash_words(viewport_words),
                        hash_words(scissor_words)) == (
                    rasters[draw["sequence"]]["mode"],
                    rasters[draw["sequence"]]["clip"],
                    rasters[draw["sequence"]]["depth"],
                    rasters[draw["sequence"]]["viewport_hash"],
                    rasters[draw["sequence"]]["scissor_hash"])
            assert list(bitmap) == index["bitmap"]
            assert len(packed) == index["packed_words"]
            assert hash_words(packed) == index["packed_hash"]
            assert final_log["packet"] == draw["packet_physical"]
            assert final_log["dynamic"] == dynamic
            assert not final_log["vertex_changed"] and not final_log["bound_changed"]
            assert hash_words(system) == final_log["system_hash"]
            assert hash_words(fetch47) == final_log["fetch47_hash"]
            assert hash_words(packed) == final_log["bound_hash"]
        vertex_bytes += vertex["length"]
        index_bytes += index["index_length"]
        if vertex["cpu_snapshot_status"] != 1:
            failures[f"vertex_status_{vertex['cpu_snapshot_status']}"] += 1
        else:
            vertex_versions[(vertex["guest_base"], vertex["length"])].add(
                vertex["cpu_snapshot_hash"])
            assert hash_bytes(owned_vertices[record[7:9]]) == vertex["cpu_snapshot_hash"]
        if index["index_status"] != 1:
            failures[f"index_status_{index['index_status']}"] += 1
        else:
            index_versions[(index["index_base"], index["index_length"])].add(
                index["index_hash"])
            assert hash_bytes(owned_indices[record[9:11]]) == index["index_hash"]
    assert len(owned_vertices) == len(vertex_versions)
    assert len(owned_indices) == len(index_versions)
    return {
        "schema": ("pinyon-shift.snr02-track-geometry.v5"
                   if magic == b"SNR02T5\0" else
                   "pinyon-shift.snr02-track-geometry.v4"
                   if magic == b"SNR02T4\0" else
                   "pinyon-shift.snr02-track-geometry.v3"
                   if magic == b"SNR02T3\0" else
                   "pinyon-shift.snr02-track-geometry.v2"
                   if magic == b"SNR02T2\0" else
                   "pinyon-shift.snr02-track-geometry.v1"),
        "source_frame": source,
        "draws": len(selected),
        "final_draws": len(finals),
        "title_targets": len(title_targets),
        "vertex_bytes_repeated": vertex_bytes,
        "index_bytes_repeated": index_bytes,
        "vertex_ranges": len(vertex_versions),
        "index_ranges": len(index_versions),
        "vertex_ranges_mutated": sum(len(v) > 1 for v in vertex_versions.values()),
        "index_ranges_mutated": sum(len(v) > 1 for v in index_versions.values()),
        "owned_bytes": sum(map(len, owned_vertices.values())) +
                       sum(map(len, owned_indices.values())),
        "fixture_bytes": fixture_path.stat().st_size,
        "failures": dict(sorted(failures.items())),
    }


if __name__ == "__main__":
    assert len(sys.argv) == 4, "usage: verify-snr02-track-geometry.py LOG LEDGER FIXTURE"
    result = verify(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print(json.dumps(result, sort_keys=True))
    assert not result["failures"]
    assert not result["vertex_ranges_mutated"]
    assert not result["index_ranges_mutated"]
