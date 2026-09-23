"""Compare owned procedural post-VS positions with a RenderDoc frame."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct


def fixture_draws(path):
    data = path.read_bytes()
    magic, frame, items = struct.unpack_from("<8sQI", data)
    assert magic == b"SNR02I3\0" and items <= 512
    offset = 148
    draws = []
    for _ in range(items):
        header = struct.unpack_from("<QII23I17I3I", data, offset)
        offset += 188 + header[44]
        for _ in range(header[45]):
            sequence, vs, _, _, vertices, _ = struct.unpack_from("<QQQQII", data, offset)
            offset += 40 + 72 + 32 + 4 + 4096 + 256 + 16
            draws.append({"sequence": sequence, "shader": f"{vs:016X}",
                          "vertices": vertices})
    assert offset == len(data) and len({d["sequence"] for d in draws}) == len(draws)
    return frame, sorted(draws, key=lambda d: d["sequence"])


def check(fixture, private_positions, capture_probe, capture_positions):
    frame, private = fixture_draws(fixture)
    data = private_positions.read_bytes()
    offset = 0
    for draw in private:
        size = draw["vertices"] * 16
        draw["bytes"] = data[offset:offset + size]
        assert len(draw["bytes"]) == size
        draw["sha256"] = hashlib.sha256(draw["bytes"]).hexdigest()
        offset += size
    assert offset == len(data)
    probe = json.loads(capture_probe.read_text())
    assert probe["stage"] == "done"
    captured = probe["draws"]
    captured_data = capture_positions.read_bytes()
    for draw in captured:
        size = draw["vertices"] * 16
        segment = captured_data[draw["offset"]:draw["offset"] + size]
        assert len(segment) == size and hashlib.sha256(segment).hexdigest() == draw["sha256"]
        draw["bytes"] = segment
    assert sum(d["vertices"] * 16 for d in captured) == len(captured_data)
    counts_private = Counter((d["shader"], d["vertices"]) for d in private)
    counts_capture = Counter((d["shader"], d["vertices"]) for d in captured)
    assert counts_private == counts_capture, "captured shader/vertex counts differ"
    left, right = defaultdict(list), defaultdict(list)
    for draw in private:
        left[draw["shader"]].append(draw)
    for draw in captured:
        right[draw["shader"]].append(draw)
    result = {"source_frame": frame, "draws": len(private), "shaders": {}}
    for shader, owned in left.items():
        reference = right[shader]
        exact_order = sum(a["sha256"] == b["sha256"] for a, b in zip(owned, reference))
        exact_set = sum((Counter((d["vertices"], d["sha256"]) for d in owned) &
                         Counter((d["vertices"], d["sha256"]) for d in reference)).values())
        result["shaders"][shader] = {"draws": len(owned),
                                     "exact_order": exact_order,
                                     "exact_multiset": exact_set}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-exact", action="store_true")
    for name in ("fixture", "private_positions", "capture_probe", "capture_positions"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    result = check(args.fixture, args.private_positions,
                   args.capture_probe, args.capture_positions)
    print(json.dumps(result, sort_keys=True))
    if args.require_exact:
        assert all(s["exact_multiset"] == s["draws"] for s in result["shaders"].values()), \
            "captured post-VS positions differ"
