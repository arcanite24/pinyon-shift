#!/usr/bin/env python3
"""Make a diagnostic SNR03F3 fixture with event 11204's captured VS constants."""

import argparse
import hashlib
import json
from pathlib import Path
import struct


def match(fixture, captured, output):
    state = json.loads(captured.read_text(encoding="utf-8"))
    assert state["stage"] == "done" and state["event"] == 11204
    assert len(state["vertex_constants"]) == 96
    assert len(state["vertex_system"]) == 64
    data = bytearray(fixture.read_bytes())
    assert data[:8] == b"SNR03F3\0"
    position = 8 + 8 + 4 + 4
    count = struct.unpack_from("<I", data, position)[0]
    position += 4 + 128
    assert 0 < count <= 512
    matches = []
    for item in range(count):
        position += 20 + 4 + 8  # Metadata, packet, bucket entry.
        vertices, size, constants, variants = struct.unpack_from(
            "<4I", data, position)
        position += 16
        assert vertices * 4 == size and constants == 24 and 0 < variants <= 4
        constant_offset = position
        position += 384 + 12 + 48  # VS constants, pixel registers/constants.
        vertex_data = data[position:position + size]
        position += size
        for variant in range(variants):
            _, sequence = struct.unpack_from("<2Q", data, position)
            position += 16
            system = struct.unpack_from("<64I", data, position)
            position += 256 + 16  # System and fetch.
            if sequence == 10125747:
                assert size == state["vertex_bytes"]
                assert hashlib.sha256(vertex_data).hexdigest() == state["vertex_sha256"]
                assert list(system) == state["vertex_system"]
                before = struct.unpack_from("<96I", data, constant_offset)
                changed = sum(a != b for a, b in zip(
                    before, state["vertex_constants"]))
                struct.pack_into("<96I", data, constant_offset,
                                 *state["vertex_constants"])
                matches.append({"item": item, "variant": variant,
                                "changed_words": changed})
    assert position == len(data) and len(matches) == 1
    assert changed == 39  # This captured fixture's drift, not a generic patch.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return {"output": str(output), "fixture_sha256": hashlib.sha256(data).hexdigest(),
            "match": matches[0]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fixture", "captured", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    assert ".local" in args.output.resolve().parts
    assert args.fixture.resolve() != args.output.resolve()
    print(json.dumps(match(args.fixture, args.captured, args.output),
                     sort_keys=True))
