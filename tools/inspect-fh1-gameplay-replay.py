#!/usr/bin/env python3
"""Read gameplay replay stream metadata from a running Windows preview (#492).

Research only: this neither saves a playable replay nor changes guest memory.
Use a private render-test run, its PID and its runtime.log. The observations
are live samples, not an atomic snapshot or evidence of restart equivalence.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import re
import struct
import sys
import time
from contextlib import nullcontext
from pathlib import Path


SCHEMA = "pinyon-shift.gameplay-replay-probe.v1"
# Base-disc contract; see docs/GAMEPLAY_REPLAYS.md. Do not guess v4 offsets.
MANAGER_POINTER = 0x834B35E4
MANAGER_VTABLE = 0x82249498
STREAM_VTABLE = 0x822493EC
BASE_LAYOUT = {MANAGER_VTABLE: 0x82E42F00, STREAM_VTABLE: 0x82E3DED8}
MAX_STREAMS = 64
MAX_INDEX_ENTRIES = 1_000_000


class ProbeError(ValueError):
    pass


def virtual_base(log: str) -> int:
    bases = re.findall(r"Guest memory arena mapped: virtual base 0x([0-9A-Fa-f]+)", log)
    if len(bases) != 1:
        raise ProbeError("runtime.log must describe exactly one guest memory arena")
    return int(bases[0], 16)


def word(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def address(value: int) -> str:
    return f"0x{value:08X}"


class Guest:
    def __init__(self, read):
        self.read = read

    def bytes(self, at: int, size: int) -> bytes:
        if at < 0x10000 or size < 0 or size > 1 << 20 or at + size > 1 << 32:
            raise ProbeError("invalid guest memory range")
        data = self.read(at, size)
        if len(data) != size:
            raise ProbeError(f"short read at {address(at)}")
        return data

    def u32(self, at: int) -> int:
        return word(self.bytes(at, 4))

    def name(self, at: int, data: bytes) -> str:
        length, capacity = word(data, 16), word(data, 20)
        if length > 128 or capacity < length or capacity > 1 << 24:
            raise ProbeError("invalid stream name")
        raw = data[:length] if capacity < 16 else self.bytes(word(data), length)
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError as error:
            raise ProbeError(f"non-ASCII stream name at {address(at)}") from error


def sample(guest: Guest) -> dict:
    if any(guest.u32(at) != expected for at, expected in BASE_LAYOUT.items()):
        raise ProbeError("unsupported executable layout; expected the base-disc replay vtables")
    manager = guest.u32(MANAGER_POINTER)
    if not manager:
        return {"state": "not_created", "streams": []}
    if guest.u32(manager) != MANAGER_VTABLE:
        raise ProbeError("replay manager vtable mismatch; only the base-disc layout is supported")
    tree = guest.bytes(manager + 412, 16)
    sentinel, count = word(tree, 4), word(tree, 8)
    if count > MAX_STREAMS:
        raise ProbeError("too many replay streams")
    header = guest.bytes(sentinel, 70)
    if header[69] != 1:
        raise ProbeError("invalid stream tree sentinel")
    todo = [word(header, 4)]
    seen = set()
    streams = []
    while todo:
        node = todo.pop()
        if node == sentinel:
            continue
        if node in seen or len(seen) >= count:
            raise ProbeError("stream tree changed, contains a cycle or exceeds its count")
        seen.add(node)
        entry = guest.bytes(node, 70)
        if entry[69] != 0:
            raise ProbeError("invalid stream tree node")
        todo.extend((word(entry), word(entry, 8)))
        stream = word(entry, 16)
        body = guest.bytes(stream, 48)
        if word(body) != STREAM_VTABLE:
            raise ProbeError("unknown replay stream implementation")
        index_begin, index_end, index_capacity = (word(body, at) for at in (24, 28, 32))
        if not index_begin == index_end == index_capacity == 0:
            if (index_begin < 0x10000 or index_begin % 4 or index_end % 4 or
                    index_capacity % 4 or not index_begin <= index_end <= index_capacity or
                    index_capacity - index_begin > MAX_INDEX_ENTRIES * 4):
                raise ProbeError("invalid replay index bounds")
        anchor_time = struct.unpack_from(">f", body, 8)[0]
        if not math.isfinite(anchor_time):
            raise ProbeError("non-finite replay anchor time")
        backing = word(body, 12)
        backing_vtable = guest.u32(backing)
        streams.append({
            "id": word(entry, 12),
            "name": guest.name(node + 32, entry[32:56]),
            "mode": word(entry, 20),
            "kind": word(entry, 24),
            "parent_id": word(entry, 64),
            "stream": address(stream),
            "anchor_time": anchor_time,
            "backing": address(backing),
            "backing_vtable": address(backing_vtable),
            "index_entries": (index_end - index_begin) // 4,
            "index_flag_16": body[16],
        })
        if guest.bytes(node, 70) != entry:
            raise ProbeError("stream metadata changed during the sample; retry")
    if (len(streams) != count or guest.bytes(sentinel, 70) != header or
            guest.bytes(manager + 412, 16) != tree or
            guest.u32(MANAGER_POINTER) != manager):
        raise ProbeError("replay manager changed during the sample; retry")
    return {"state": "observed", "manager": address(manager),
            "streams": sorted(streams, key=lambda s: s["id"])}


class WindowsReader:
    def __init__(self, pid: int, base: int):
        if sys.platform != "win32":
            raise ProbeError("live observation requires Windows")
        from ctypes import wintypes as wt
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        self.api.OpenProcess.restype = wt.HANDLE
        self.api.CloseHandle.argtypes = [wt.HANDLE]
        self.api.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                              ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        self.api.ReadProcessMemory.restype = wt.BOOL
        self.api.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR,
                                                       ctypes.POINTER(wt.DWORD)]
        self.api.QueryFullProcessImageNameW.restype = wt.BOOL
        # Query the executable and read memory only; no write or suspend access.
        self.handle = self.api.OpenProcess(0x1000 | 0x10, False, pid)
        if not self.handle:
            raise ProbeError(f"OpenProcess failed ({ctypes.get_last_error()})")
        self.base = base
        try:
            name = ctypes.create_unicode_buffer(32768)
            length = wt.DWORD(len(name))
            if (not self.api.QueryFullProcessImageNameW(self.handle, 0, name, ctypes.byref(length)) or
                    Path(name.value).name.lower() != "pinyon_shift.exe"):
                raise ProbeError("PID does not identify a pinyon_shift.exe preview")
        except BaseException:
            self.close()
            raise

    def read(self, at: int, size: int) -> bytes:
        data = ctypes.create_string_buffer(size)
        count = ctypes.c_size_t()
        if not self.api.ReadProcessMemory(self.handle, self.base + at, data, size, ctypes.byref(count)):
            raise ProbeError(f"unreadable guest memory at {address(at)} ({ctypes.get_last_error()})")
        return data.raw[:count.value]

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    arena = parser.add_mutually_exclusive_group(required=True)
    arena.add_argument("--log", type=Path, help="the private run's readable runtime.log")
    arena.add_argument("--guest-base", type=lambda s: int(s, 0),
                       help="virtual membase from the run's log if Windows locks the file")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.5, help="seconds between samples")
    parser.add_argument("--output", type=Path, help="new JSONL file (never overwritten)")
    args = parser.parse_args()
    if (args.pid <= 0 or not 1 <= args.samples <= 3600 or
            not math.isfinite(args.interval) or not 0.01 <= args.interval <= 60):
        parser.error("use a positive PID, 1..3600 samples and a 0.01..60 second interval")
    reader = None
    failed = False
    try:
        base = (virtual_base(args.log.read_text(encoding="utf-8", errors="replace"))
                if args.log else args.guest_base)
        if base < 1 << 32 or base + (1 << 32) > 1 << 64:
            raise ProbeError("invalid host virtual membase")
        reader = WindowsReader(args.pid, base)
        guest = Guest(reader.read)
        output = args.output.open("x", encoding="utf-8") if args.output else nullcontext(sys.stdout)
        with output as stream:
            started = time.monotonic()
            for i in range(args.samples):
                row = {"schema": SCHEMA, "pid": args.pid, "sample": i,
                       "elapsed_seconds": time.monotonic() - started}
                try:
                    row.update(sample(guest))
                except ProbeError as error:
                    row.update(state="unavailable", error=str(error))
                    failed = True
                stream.write(json.dumps(row, allow_nan=False) + "\n")
                stream.flush()
                if i + 1 < args.samples:
                    time.sleep(args.interval)
        return int(failed)
    except (ProbeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        if reader:
            reader.close()


if __name__ == "__main__":
    raise SystemExit(main())
