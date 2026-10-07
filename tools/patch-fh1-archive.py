#!/usr/bin/env python3
"""Write a new FH1 ZIP with selected members replaced, retaining XMem members.

Ordinary ZIP writers cannot copy FH1's method-21 members, and the title reads
absolute payload offsets from extra field 0x1123. Recalculate those offsets
alongside the normal local-header offsets. Originals are never overwritten.
"""
from __future__ import annotations

import argparse
import struct
import zipfile
import zlib
from pathlib import Path


def xmem_stored(data: bytes) -> bytes:
    """Wrap literal bytes in LZX type-3 blocks and FH1 XMem frame headers.

    Disable the Intel E8 transform and retain 32 KiB frame/block boundaries.
    The host extractor validates these streams; native UI delivery remains
    experimental and must be qualified separately.
    """
    output = bytearray()
    for offset in range(0, len(data), 0x8000):
        chunk = data[offset:offset + 0x8000]
        bits = ("0" if offset == 0 else "") + "011" + f"{len(chunk):024b}"
        bits += "0" * (-len(bits) % 16)
        block = b"".join(struct.pack("<H", int(bits[n:n + 16], 2))
                         for n in range(0, len(bits), 16))
        block += struct.pack("<3I", 1, 1, 1) + chunk
        if len(chunk) % 2:
            block += b"\0"
        output += (struct.pack(">H", len(block)) if len(chunk) == 0x8000
                   else b"\xff" + struct.pack(">2H", len(chunk), len(block)))
        output += block
    return bytes(output)


def patch_archive(source: Path, destination: Path, replacements: dict[str, bytes],
                  *, xmem: bool = False) -> None:
    replacements = {name.lower(): data for name, data in replacements.items()}
    with zipfile.ZipFile(source) as archive, source.open("rb") as original:
        members = archive.infolist()
        names = [member.filename.lower() for member in members]
        if len(names) != len(set(names)) or not replacements.keys() <= set(names):
            raise ValueError("duplicate members or unknown replacement name")
        if len(members) > 65535:
            raise ValueError("ZIP64 is not supported")
        original.seek(archive.start_dir)
        records = []
        for member in members:
            central = bytearray(original.read(46))
            if len(central) != 46 or central[:4] != b"PK\x01\x02":
                raise ValueError("invalid central directory")
            lengths = struct.unpack_from("<HHH", central, 28)
            extra = original.read(sum(lengths))
            if len(extra) != sum(lengths) or member.flag_bits & 8:
                raise ValueError("truncated directory or unsupported data descriptor")
            central.extend(extra)
            records.append((member, central, lengths))
        # Exclusive creation also rejects source==destination, without touching it.
        with destination.open("xb") as output:
            try:
                for member, central, lengths in records:
                    offset = output.tell()
                    replacement = replacements.get(member.filename.lower())
                    if replacement is not None:
                        name = bytes(central[46:46 + lengths[0]])
                        crc = zlib.crc32(replacement)
                        payload = xmem_stored(replacement) if xmem else replacement
                        method = 21 if xmem else 0
                        flags = member.flag_bits & 0x800  # retain UTF-8 names
                        output.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20 if xmem else 10,
                            flags, method, 0, 0, crc, len(payload), len(replacement), len(name), 0))
                        output.write(name)
                        payload_offset = output.tell()
                        output.write(payload)
                        struct.pack_into("<HH", central, 8, flags, method)
                        struct.pack_into("<III", central, 16, crc, len(payload), len(replacement))
                    else:
                        original.seek(member.header_offset)
                        header = original.read(30)
                        if len(header) != 30 or header[:4] != b"PK\x03\x04":
                            raise ValueError("expected a local ZIP header")
                        name_size, extra_size = struct.unpack_from("<HH", header, 26)
                        output.write(header)
                        remaining = name_size + extra_size + member.compress_size
                        payload_offset = offset + 30 + name_size + extra_size
                        while remaining:
                            block = original.read(min(remaining, 1024 * 1024))
                            if not block:
                                raise ValueError("truncated member")
                            output.write(block)
                            remaining -= len(block)
                    extra_at = 46 + lengths[0]
                    extra_end = extra_at + lengths[1]
                    while extra_at < extra_end:
                        if extra_at + 4 > extra_end:
                            raise ValueError("invalid central extra field")
                        tag, length = struct.unpack_from("<HH", central, extra_at)
                        if extra_at + 4 + length > extra_end:
                            raise ValueError("truncated central extra field")
                        if tag == 0x1123:
                            if length != 4:
                                raise ValueError("invalid FH1 payload offset")
                            struct.pack_into("<I", central, extra_at + 4, payload_offset)
                        extra_at += 4 + length
                    struct.pack_into("<I", central, 42, offset)
                directory_offset = output.tell()
                for _, central, _ in records:
                    output.write(central)
                directory_size = output.tell() - directory_offset
                output.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0,
                    len(members), len(members), directory_size, directory_offset, 0))
            except Exception:
                output.close()
                destination.unlink()
                raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, help="new output file; must not exist")
    parser.add_argument("--replace", action="append", required=True, metavar="MEMBER=FILE")
    parser.add_argument("--xmem", action="store_true",
                        help="wrap replacements in method-21 LZX; native UI delivery is experimental")
    args = parser.parse_args()
    try:
        replacements = {}
        for item in args.replace:
            name, separator, path = item.partition("=")
            if not separator or name.lower() in replacements:
                raise ValueError("expected a unique MEMBER=FILE replacement")
            replacements[name.lower()] = Path(path).read_bytes()
        patch_archive(args.source, args.destination, replacements, xmem=args.xmem)
    except (OSError, ValueError, zipfile.BadZipFile, struct.error) as error:
        parser.exit(1, f"{error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
