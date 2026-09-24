"""Census captured versus owned vertex inputs for one foliage output frame.

Run with qrenderdoc --python. Set SNR04_CAPTURE, SNR04_FIXTURE,
SNR04_EVENTS_JSON and SNR04_OUTPUT. The event/sequence join uses ordered draws
within the same 45/67/67 EDRAM bands and checks every fetched vertex range.
"""

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
import traceback

import renderdoc as rd


def fixture_draws(data):
    assert data[:8] in (b"SNR03F3\0", b"SNR03F4\0")
    final_bound = data[:8] == b"SNR03F4\0"
    position = 8 + 8 + 4 + 4
    items = struct.unpack_from("<I", data, position)[0]
    position += 4 + 128
    assert 0 < items <= 512
    draws = []
    for item in range(items):
        position += 20 + 4 + 8
        vertices, size, constants, variants = struct.unpack_from(
            "<4I", data, position)
        position += 16
        assert vertices * 4 == size and constants == 24 and 0 < variants <= 4
        words = struct.unpack_from("<96I", data, position)
        position += 384 + 12 + 48
        vertex_hash = hashlib.sha256(data[position:position + size]).hexdigest()
        position += size
        for _ in range(variants):
            _, sequence = struct.unpack_from("<2Q", data, position)
            position += 16
            system = struct.unpack_from("<64I", data, position)
            position += 256 + 16
            final_words = (struct.unpack_from("<92I", data, position)
                           if final_bound else words[:92])
            if final_bound:
                position += 368
            draws.append((sequence, item, size, vertex_hash, final_words,
                          words[:92], system))
    assert position == len(data) and 0 < len(draws) <= 512
    return sorted(draws)


out = Path(os.environ["SNR04_OUTPUT"])
state = {"stage": "open"}
out.write_text(json.dumps(state))
cap = replay = None
try:
    fixture = Path(os.environ["SNR04_FIXTURE"]).read_bytes()
    draws = fixture_draws(fixture)
    events = sorted(row["event"] for row in json.loads(Path(
        os.environ["SNR04_EVENTS_JSON"]).read_text())["matches"])
    assert len(events) == len(draws)
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(os.environ["SNR04_CAPTURE"], "rdc", None)
    assert "Success" in str(result), result
    result, replay = cap.OpenCapture(rd.ReplayOptions(), None)
    assert "Success" in str(result), result
    constant_patterns = Counter()
    prepared_patterns = Counter()
    system_patterns = Counter()
    vertex_mismatches = []
    captured_by_item = {}
    for event, (sequence, item, size, vertex_hash, words, prepared, system) in zip(events, draws):
        replay.SetFrameEvent(event, True)
        pipeline = replay.GetPipelineState()
        blocks = []
        for index, count in enumerate((120, 96, 192)):
            descriptor = pipeline.GetConstantBlock(rd.ShaderStage.Vertex,
                                                   index, 0).descriptor
            raw = bytes(replay.GetBufferData(descriptor.resource,
                                             descriptor.byteOffset, count * 4))
            assert len(raw) == count * 4
            blocks.append(struct.unpack(f"<{count}I", raw))
        fetch = blocks[2][-4:]
        assert fetch[3] & 0x03FFFFFC == size
        resources = pipeline.GetReadOnlyResources(rd.ShaderStage.Vertex)
        assert len(resources) == 1
        raw = bytes(replay.GetBufferData(resources[0].descriptor.resource,
                                         fetch[2] & 0x1FFFFFFC, size))
        if hashlib.sha256(raw).hexdigest() != vertex_hash:
            vertex_mismatches.append([event, sequence])
        captured_by_item.setdefault(item, set()).add(blocks[1][:92])
        constant_patterns[tuple(i for i, (a, b) in enumerate(
            zip(words, blocks[1][:92])) if a != b)] += 1
        prepared_patterns[tuple(i for i, (a, b) in enumerate(
            zip(prepared, blocks[1][:92])) if a != b)] += 1
        system_patterns[tuple(i for i, (a, b) in enumerate(
            zip(system, blocks[0])) if a != b)] += 1
    assert not vertex_mismatches, vertex_mismatches
    state = {"stage": "done", "actions": len(events),
             "fixture_sha256": hashlib.sha256(fixture).hexdigest(),
             "vertex_ranges_exact": len(events),
             "constant_patterns": [dict(words=list(key), draws=value)
                                   for key, value in constant_patterns.items()],
             "prepared_patterns": [dict(words=list(key), draws=value)
                                   for key, value in prepared_patterns.items()],
             "system_patterns": [dict(words=list(key), draws=value)
                                 for key, value in system_patterns.items()],
             "captured_constant_variants_per_item": dict(sorted(Counter(
                 len(values) for values in captured_by_item.values()).items()))}
except Exception:
    state = {"stage": "error", "error": traceback.format_exc()}
finally:
    out.write_text(json.dumps(state, indent=2) + "\n")
    if replay:
        replay.Shutdown()
    if cap:
        cap.Shutdown()
