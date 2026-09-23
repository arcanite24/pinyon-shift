"""Inspect event 11204's single-fragment pixels and first VS output quad.

Run with qrenderdoc --python and SNR04_CAPTURE/SNR04_OUTPUT/SNR04_EVENT.
"""

import hashlib
import json
import os
from pathlib import Path
import struct
import traceback

import renderdoc as rd


out = Path(os.environ["SNR04_OUTPUT"])
event = int(os.environ["SNR04_EVENT"])
pixels = ((1143, 50), (1153, 51), (1154, 47))
state = {"stage": "open", "event": event}
out.write_text(json.dumps(state))
cap = replay = None
try:
    assert event == 11204
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(os.environ["SNR04_CAPTURE"], "rdc", None)
    assert "Success" in str(result), result
    result, replay = cap.OpenCapture(rd.ReplayOptions(), None)
    assert "Success" in str(result), result
    replay.SetFrameEvent(event, True)
    pipeline = replay.GetPipelineState()
    target = pipeline.GetDepthTarget()
    sub = rd.Subresource()
    sub.mip, sub.slice, sub.sample = target.firstMip, target.firstSlice, 0

    rows = []
    for x, y in pixels:
        history = replay.PixelHistory(target.resource, x, y, sub,
                                      rd.CompType.Typeless)
        fragments = [m for m in history if m.eventId == event]
        assert len(fragments) == 1, (x, y, len(fragments))
        inputs = rd.DebugPixelInputs()
        inputs.sample = 0
        trace = replay.DebugPixel(x, y, inputs)
        try:
            values = {v.name: list(v.value.f32v)[:4] for v in trace.inputs}
            assert "v0" in values and "v4" in values
            rows.append({"pixel": [x, y], "uv": values["v0"][:2],
                         "fade": values["v4"][3],
                         "shader_discarded": fragments[0].shaderDiscarded})
        finally:
            replay.FreeTrace(trace)

    mesh = replay.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
    raw = bytes(replay.GetBufferData(mesh.vertexResourceId,
                                     mesh.vertexByteOffset,
                                     mesh.vertexByteSize))
    assert mesh.numIndices >= 4 and mesh.vertexByteStride >= 16
    positions = [struct.unpack_from("<4f", raw, i * mesh.vertexByteStride)
                 for i in range(4)]
    blocks = []
    for index, words in enumerate((120, 96, 192)):
        descriptor = pipeline.GetConstantBlock(rd.ShaderStage.Vertex,
                                               index, 0).descriptor
        data = bytes(replay.GetBufferData(descriptor.resource,
                                          descriptor.byteOffset, words * 4))
        assert len(data) == words * 4
        blocks.append(struct.unpack(f"<{words}I", data))
    fetch = blocks[2][-4:]
    vertex_offset = fetch[2] & 0x1FFFFFFC
    vertex_bytes = fetch[3] & 0x03FFFFFC
    assert 0 < vertex_bytes <= 32768
    resources = pipeline.GetReadOnlyResources(rd.ShaderStage.Vertex)
    assert len(resources) == 1
    data = bytes(replay.GetBufferData(resources[0].descriptor.resource,
                                      vertex_offset, vertex_bytes))
    assert len(data) == vertex_bytes
    state = {"stage": "done", "event": event, "pixels": rows,
             "first_vs_quad": positions,
             "vertex_constants": list(blocks[1]),
             "vertex_system": list(blocks[0][:64]),
             "vertex_bytes": vertex_bytes,
             "vertex_sha256": hashlib.sha256(data).hexdigest()}
except Exception:
    state = {"stage": "error", "error": traceback.format_exc()}
finally:
    out.write_text(json.dumps(state, indent=2) + "\n")
    if replay:
        replay.Shutdown()
    if cap:
        cap.Shutdown()
