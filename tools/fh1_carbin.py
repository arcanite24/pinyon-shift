#!/usr/bin/env python3
"""Read and write FH1 car models (.carbin), for the car importer (#496).

FH1 keeps each car's meshes in its archive, media/cars/<MediaName>.zip:
<car>.carbin (LOD1-5), <car>_lod0.carbin, <car>_cockpit.carbin, one caliper
and one rotor carbin per wheel, and a stripped_* twin of each. This module
reads a carbin into its parts and writes it back. Every part it knows the
layout of is decoded (sections, their vertex pools and the index buffer of
each sub-section); fields whose meaning is not known yet are kept as the
bytes they were, so a write of an unchanged read is byte-identical
(`roundtrip`). The layout is our own reading of the player's files; it is
documented in site/findings/files.toml.

  fh1_carbin.py dump <file.carbin> [--sections]
  fh1_carbin.py roundtrip <file or directory> [...]

Nothing here contains game data; it works on the player's extracted files.
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

SECTION_MARKER = 5
FLT_MAX = struct.unpack(">f", bytes.fromhex("7f7fffff"))[0]
# Bytes per vertex of the pools whose layout is decoded: 4 x int16 position
# (a unit direction and a length; see positions), UV0 and UV1 as 2 x uint16 each, a 4 x int16
# quaternion tangent frame and 4 bytes of baked lighting.
VERTEX28 = struct.Struct(">4h4H4h4B")


class CarbinError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes, at: int = 0) -> None:
        self.data = data
        self.at = at

    def need(self, size: int) -> None:
        if size < 0 or self.at + size > len(self.data):
            raise CarbinError(f"read of {size} bytes at {self.at:#x} runs past the end")

    def u8(self) -> int:
        self.need(1)
        value = self.data[self.at]
        self.at += 1
        return value

    def u32(self) -> int:
        self.need(4)
        value = struct.unpack_from(">I", self.data, self.at)[0]
        self.at += 4
        return value

    def raw(self, size: int) -> bytes:
        self.need(size)
        value = self.data[self.at:self.at + size]
        self.at += size
        return value


def _floats_sane(data: bytes, at: int, count: int) -> bool:
    for value in struct.unpack_from(f">{count}f", data, at):
        # An empty section's bounds are +/-FLT_MAX (an empty box).
        if value != value or (abs(value) >= 1e5 and abs(value) != FLT_MAX):
            return False
    return True


@dataclass
class Pool:
    """A vertex pool: `count` vertices of `stride` bytes. `bone_weights`
    (and `section_id` when it is not zero) precede the vertices."""
    count: int
    stride: int
    bone_weights: int
    section_id: int | None
    vertices: list[tuple] | bytes

    def encode(self) -> bytes:
        out = bytearray(struct.pack(">III", self.count & 0xFFFFFFFF, self.stride, self.bone_weights))
        if self.bone_weights:
            out += struct.pack(">I", self.section_id)
        if isinstance(self.vertices, bytes):
            out += self.vertices
        else:
            out += b"".join(VERTEX28.pack(*v) for v in self.vertices)
        return bytes(out)


def _read_pool(r: Reader) -> Pool:
    count = r.u32()
    stride = r.u32()
    bone_weights = r.u32()
    section_id = r.u32() if bone_weights else None
    signed = count - (1 << 32) if count & 0x80000000 else count
    body = r.raw(max(signed, 0) * stride)
    vertices: list[tuple] | bytes = body
    if stride == VERTEX28.size:
        vertices = list(VERTEX28.iter_unpack(body))
    return Pool(count, stride, bone_weights, section_id, vertices)


@dataclass
class Subsection:
    """One material's triangles in a section: an index buffer into the
    section's pool for one LOD, with the material's UV offset and scale."""
    head: bytes          # 5 bytes, not decoded
    uv_transform: tuple  # 8 floats: UV0 and UV1 offset and scale
    unknown1: bytes      # 36 bytes, not decoded
    name: str
    lod: int
    index_type: int      # 4 = triangle list, 6 = strip with restarts
    unknown2: bytes      # 56 bytes (14 floats), not decoded
    version_words: tuple # (4, 0) in FH1
    index_size: int      # 2 or 4
    indices: list[int]
    end: bytes           # 4 bytes

    def encode(self) -> bytes:
        name = self.name.encode("latin-1")
        out = bytearray(self.head)
        out += struct.pack(">8f", *self.uv_transform)
        out += self.unknown1
        out += struct.pack(">I", len(name)) + name
        out += struct.pack(">iI", self.lod, self.index_type)
        out += self.unknown2
        out += struct.pack(f">{len(self.version_words)}I", *self.version_words)
        out += struct.pack(">iI", len(self.indices), self.index_size)
        out += struct.pack(f">{len(self.indices)}{'H' if self.index_size == 2 else 'I'}", *self.indices)
        out += self.end
        return bytes(out)


def _read_subsection(r: Reader) -> Subsection:
    head = r.raw(5)
    uv = struct.unpack(">8f", r.raw(32))
    unknown1 = r.raw(36)
    name_size = r.u32()
    if name_size > 256:
        raise CarbinError(f"sub-section name of {name_size} bytes at {r.at:#x}")
    name = r.raw(name_size).decode("latin-1")
    lod, index_type = struct.unpack(">iI", r.raw(8))
    unknown2 = r.raw(56)
    version_words = struct.unpack(">II", r.raw(8))
    count = r.u32()
    size = r.u32()
    if size not in (2, 4):
        raise CarbinError(f"index size {size} in sub-section {name!r}")
    indices = list(struct.unpack(f">{count}{'H' if size == 2 else 'I'}", r.raw(count * size)))
    end = r.raw(4)
    return Subsection(head, uv, unknown1, name, lod, index_type, unknown2, version_words, size,
                      indices, end)


@dataclass
class Section:
    """A named part of the car (body, hood, glass, a light, ...): its
    bounds, its LOD vertex pool and sub-sections, its LOD0 pool and a tail
    that is kept as bytes until its layout is known."""
    bounds: tuple        # 9 floats: offset, minimum, maximum
    unknown1: bytes      # 28 bytes: mass, centre of mass and damage fields
    permutations: bytes  # count u32 + 16 bytes each
    unknown2: bytes      # 4 bytes
    shorts: bytes        # count u32 + 2 bytes each
    unknown3: bytes      # 12 bytes
    name: str
    version: int
    lod_pool: Pool
    unknown4: bytes      # 4 bytes
    subsections: list[Subsection]
    unknown5: bytes      # 4 bytes
    lod0_pool: Pool
    tail_word: int = 1
    damage_flag: int = 0
    # One per pool (LOD, then LOD0): (kind, count, stride, extra words,
    # count x stride bytes, extra x 4 bytes). The per-vertex table holds the
    # damage deformation of the pool's vertices when damage_flag is 1.
    damage: list = field(default_factory=list)

    def encode(self) -> bytes:
        name = self.name.encode("latin-1")
        out = bytearray(struct.pack(">I", SECTION_MARKER))
        out += struct.pack(">9f", *self.bounds)
        out += self.unknown1 + self.permutations + self.unknown2 + self.shorts + self.unknown3
        out += bytes([len(name)]) + name
        out += struct.pack(">I", self.version)
        out += self.lod_pool.encode()
        out += self.unknown4
        out += struct.pack(">I", len(self.subsections))
        for subsection in self.subsections:
            out += subsection.encode()
        out += self.unknown5
        out += self.lod0_pool.encode()
        out += struct.pack(">IB", self.tail_word, self.damage_flag)
        for kind, count, stride, extra, table, words in self.damage:
            out += struct.pack(">IIII", kind, count, stride, extra) + table + words
        return bytes(out)


def _read_section(r: Reader) -> Section:
    if r.u32() != SECTION_MARKER:
        raise CarbinError(f"no section marker at {r.at - 4:#x}")
    bounds = struct.unpack(">9f", r.raw(36))
    unknown1 = r.raw(28)
    start = r.at
    count = r.u32()
    r.raw(count * 16)
    permutations = r.data[start:r.at]
    unknown2 = r.raw(4)
    start = r.at
    count = r.u32()
    r.raw(count * 2)
    shorts = r.data[start:r.at]
    unknown3 = r.raw(12)
    name = r.raw(r.u8()).decode("latin-1")
    version = r.u32()
    lod_pool = _read_pool(r)
    unknown4 = r.raw(4)
    count = r.u32()
    if count > 4096:
        raise CarbinError(f"{count} sub-sections in {name!r}")
    subsections = [_read_subsection(r) for _ in range(count)]
    unknown5 = r.raw(4)
    lod0_pool = _read_pool(r)
    tail_word = r.u32()
    damage_flag = r.u8()
    damage = []
    for _ in range(2):
        kind, count, stride, extra = struct.unpack(">IIII", r.raw(16))
        if count > 1 << 22 or stride > 64 or extra > 1 << 16:
            raise CarbinError(f"damage block {count}x{stride}+{extra} in {name!r}")
        damage.append((kind, count, stride, extra, r.raw(count * stride), r.raw(extra * 4)))
    return Section(bounds, unknown1, permutations, unknown2, shorts, unknown3, name, version,
                   lod_pool, unknown4, subsections, unknown5, lod0_pool, tail_word, damage_flag,
                   damage)


def _plausible_section(data: bytes, at: int) -> bool:
    if at + 4 + 36 + 28 > len(data) or struct.unpack_from(">I", data, at)[0] != SECTION_MARKER:
        return False
    if not _floats_sane(data, at + 4, 9):
        return False
    try:
        section = _read_section(Reader(data, at))
    except (CarbinError, struct.error, UnicodeDecodeError):
        return False
    return (0 < len(section.name) <= 64 and section.name.isprintable()
            and section.version in (2, 3))


@dataclass
class Carbin:
    head: bytes          # everything before the section count, not decoded
    sections: list[Section] = field(default_factory=list)
    footer: bytes = b""  # after the last section, not decoded

    def encode(self) -> bytes:
        out = bytearray(self.head)
        if not self.sections:  # a model with no parts: kept whole in head
            return bytes(out + self.footer)
        out += struct.pack(">I", len(self.sections))
        for section in self.sections:
            out += section.encode()
        out += self.footer
        return bytes(out)


def find_sections(data: bytes) -> tuple[int, int]:
    """(offset of the section count, count): the first u32 in 1..1024
    followed by a section that parses."""
    # The count is not always 4-byte aligned (the head's strings are not padded).
    for at in range(0, len(data) - 48):
        count = struct.unpack_from(">I", data, at)[0]
        if 1 <= count <= 1024 and _plausible_section(data, at + 4):
            return at, count
    raise CarbinError("no sections found")


def parse(data: bytes) -> Carbin:
    try:
        count_at, count = find_sections(data)
    except CarbinError:
        # The F-350 Super Duty's lod0 is a 1,232-byte header with no parts.
        if len(data) <= 4096 and struct.unpack_from(">I", data, 0)[0] == SECTION_MARKER:
            return Carbin(data)
        raise
    carbin = Carbin(data[:count_at])
    r = Reader(data, count_at + 4)
    for _ in range(count):
        carbin.sections.append(_read_section(r))
    carbin.footer = data[r.at:]
    return carbin


def positions(section: Section, pool: Pool) -> list[tuple[float, float, float]]:
    """The pool's vertex positions in car space. A vertex stores its
    position relative to the section's offset as a direction and a length:
    the first three shorts are a unit vector (over 32767) and the fourth is
    the length as a fraction (over 32767) of the length of the section's
    half-extent vector. The game's vertex shader receives the offset and
    that length as one constant (#496 phase 1)."""
    offset = section.bounds[0:3]
    scale = math.sqrt(sum(e * e for e in section.bounds[6:9]))
    return [tuple(v[axis] / 32767 * (v[3] / 32767) * scale + offset[axis] for axis in range(3))
            for v in pool.vertices]


def set_positions(section: Section, moved: dict[str, list[tuple[float, float, float]]]) -> None:
    """Replace the positions of the section's pools ("lod", "lod0"),
    refitting the section's box (offset and half-extents) to every
    position it keeps and re-encoding each as a direction and a length."""
    pools = {"lod": section.lod_pool, "lod0": section.lod0_pool}
    every = []
    for name, pool in pools.items():
        every += moved[name] if name in moved else positions(section, pool)
    if not every:
        return
    low = [min(p[axis] for p in every) for axis in range(3)]
    high = [max(p[axis] for p in every) for axis in range(3)]
    offset = [(low[axis] + high[axis]) / 2 for axis in range(3)]
    extent = [(high[axis] - low[axis]) / 2 for axis in range(3)]
    scale = math.sqrt(sum(e * e for e in extent))
    for name, pool in pools.items():
        points = moved[name] if name in moved else positions(section, pool)
        encoded = []
        for v, p in zip(pool.vertices, points):
            d = [p[axis] - offset[axis] for axis in range(3)]
            length = math.sqrt(sum(x * x for x in d))
            if length == 0 or scale == 0:
                direction, size = (32767, 0, 0), 0
            else:
                direction = tuple(round(x / length * 32767) for x in d)
                size = min(32767, round(length / scale * 32767))
            encoded.append(direction + (size,) + tuple(v[4:]))
        pool.vertices = encoded
    section.bounds = tuple(offset) + tuple(-e for e in extent) + tuple(extent)


def roundtrip(path: Path) -> str | None:
    data = path.read_bytes()
    try:
        carbin = parse(data)
    except CarbinError as error:
        return f"parse: {error}"
    out = carbin.encode()
    if out != data:
        at = next((i for i, (a, b) in enumerate(zip(out, data)) if a != b), min(len(out), len(data)))
        return f"differs at {at:#x} (sizes {len(out)} and {len(data)})"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    dump = sub.add_parser("dump")
    dump.add_argument("file", type=Path)
    dump.add_argument("--sections", action="store_true")
    trip = sub.add_parser("roundtrip")
    trip.add_argument("paths", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if args.command == "dump":
        carbin = parse(args.file.read_bytes())
        print(f"head {len(carbin.head)} bytes, {len(carbin.sections)} sections")
        for section in carbin.sections:
            print(f"  {section.name}: v{section.version} lod {section.lod_pool.count}x"
                  f"{section.lod_pool.stride} lod0 {section.lod0_pool.count}x"
                  f"{section.lod0_pool.stride} subs {len(section.subsections)} "
                  f"damage {section.damage_flag} {[d[1:4] for d in section.damage]}")
            if args.sections:
                for s in section.subsections:
                    print(f"      {s.name} lod {s.lod} type {s.index_type} "
                          f"{len(s.indices)}x{s.index_size}")
        return 0
    files = []
    for path in args.paths:
        files += sorted(p for p in path.rglob("*.carbin")) if path.is_dir() else [path]
    files = [path for path in files if not path.name.lower().startswith("stripped_")]
    failures = 0
    for path in files:
        problem = roundtrip(path)
        if problem:
            failures += 1
            print(f"FAIL {path}: {problem}")
    print(f"{len(files) - failures} of {len(files)} round-trip")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
