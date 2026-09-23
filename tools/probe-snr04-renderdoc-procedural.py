"""Export procedural draw positions from a matching RenderDoc frame.

Run with qrenderdoc --python and SNR04_CAPTURE, SNR04_OUTPUT,
SNR04_POSITIONS, SNR04_SHADERS, and SNR04_LAYERED_HEADER set.
"""

import collections
import hashlib
import json
import os
from pathlib import Path
import re
import traceback

import renderdoc as rd


def shader_bytes_from_header(path):
    source = path.read_text()
    source = source[source.index("const BYTE fh1_layered_scene_vs[]"):]
    source = source[source.index("{") + 1:source.index("}")]
    return bytes(map(int, re.findall(r"\d+", source)))


capture = Path(os.environ["SNR04_CAPTURE"])
output = Path(os.environ["SNR04_OUTPUT"])
positions_path = Path(os.environ["SNR04_POSITIONS"])
shaders = Path(os.environ["SNR04_SHADERS"])
layered = Path(os.environ["SNR04_LAYERED_HEADER"])
known = {hashlib.sha256(path.read_bytes()).hexdigest(): path.name.split("_")[1]
         for path in shaders.glob("vertex_*.dxil")
         if path.name.split("_")[1] in {"3BC346726C1C2535", "BDFD2AD68464101A",
                                      "CB8AC98467C0C283", "A715C815EDB8EEE8"}}
known[hashlib.sha256(shader_bytes_from_header(layered)).hexdigest()] = "3BC346726C1C2535"
assert len(known) == 5, "four guest shaders and one replacement are required"
state = {"stage": "open", "capture": capture.name, "draws": []}
cap = replay = None
try:
    output.write_text(json.dumps(state))
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(str(capture), "rdc", None)
    assert "Success" in str(result), str(result)
    result, replay = cap.OpenCapture(rd.ReplayOptions(), None)
    assert "Success" in str(result), str(result)
    with positions_path.open("wb") as positions:
        for action in replay.GetRootActions():
            if not action.flags & rd.ActionFlags.Drawcall:
                continue
            replay.SetFrameEvent(action.eventId, True)
            reflection = replay.GetPipelineState().GetShaderReflection(rd.ShaderStage.Vertex)
            if not reflection:
                continue
            shader = known.get(hashlib.sha256(bytes(reflection.rawBytes)).hexdigest())
            if not shader:
                continue
            mesh = replay.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
            assert mesh.numIndices == action.numIndices and mesh.vertexByteStride >= 16
            raw = bytes(replay.GetBufferData(mesh.vertexResourceId,
                                             mesh.vertexByteOffset, mesh.vertexByteSize))
            assert len(raw) >= (mesh.numIndices - 1) * mesh.vertexByteStride + 16
            data = b"".join(raw[i * mesh.vertexByteStride:i * mesh.vertexByteStride + 16]
                            for i in range(mesh.numIndices))
            offset = positions.tell()
            positions.write(data)
            state["draws"].append({"event": action.eventId, "shader": shader,
                                   "vertices": mesh.numIndices, "offset": offset,
                                   "sha256": hashlib.sha256(data).hexdigest()})
            if len(state["draws"]) % 20 == 0:
                state["stage"] = "reading"
                output.write_text(json.dumps(state))
    state["counts"] = dict(collections.Counter(d["shader"] for d in state["draws"]))
    state["stage"] = "done"
except Exception:
    state.update(stage="error", error=traceback.format_exc())
finally:
    output.write_text(json.dumps(state))
    if replay:
        replay.Shutdown()
    if cap:
        cap.Shutdown()
