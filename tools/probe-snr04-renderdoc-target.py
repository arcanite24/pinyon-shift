"""Export bound color targets at selected events via qrenderdoc --python.

Set SNR04_CAPTURE, SNR04_OUTPUT and comma-separated SNR04_EVENTS.
"""

import hashlib
import json
import os
from pathlib import Path
import traceback

import renderdoc as rd


capture = Path(os.environ["SNR04_CAPTURE"])
output = Path(os.environ["SNR04_OUTPUT"])
events = [int(value) for value in os.environ["SNR04_EVENTS"].split(",")]
assert events and all(event > 0 for event in events)
state = {"stage": "open", "capture": capture.name, "events": events}
output.write_text(json.dumps(state))
cap = replay = None
try:
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(str(capture), "rdc", None)
    if "Success" not in str(result):
        raise RuntimeError(str(result))
    result, replay = cap.OpenCapture(rd.ReplayOptions(), None)
    if "Success" not in str(result):
        raise RuntimeError(str(result))
    textures = {str(texture.resourceId): texture for texture in replay.GetTextures()}
    rows = []
    for event in events:
        replay.SetFrameEvent(event, True)
        pipeline = replay.GetPipelineState()
        viewport = pipeline.GetViewport(0)
        vertex = pipeline.GetShaderReflection(rd.ShaderStage.Vertex)
        target = next((target for target in pipeline.GetOutputTargets()
                       if target.resource != rd.ResourceId.Null()), None)
        if not target:
            rows.append({"event": event, "target": None})
            continue
        desc = textures[str(target.resource)]
        path = output.parent / f"{output.stem}-{event}.png"
        save = rd.TextureSave()
        save.resourceId = target.resource
        save.destType = rd.FileType.PNG
        save.alpha = rd.AlphaMapping.Preserve
        result = replay.SaveTexture(save, str(path))
        if hasattr(result, "code") and result.code != rd.ResultCode.Succeeded:
            raise RuntimeError(f"SaveTexture {event}: {result}")
        rows.append({"event": event, "target": str(target.resource),
                     "vertex_sha256": hashlib.sha256(bytes(vertex.rawBytes)).hexdigest()
                     if vertex else None,
                     "format": desc.format.Name(),
                     "size": [desc.width, desc.height],
                     "viewport": [viewport.x, viewport.y,
                                  viewport.width, viewport.height],
                     "file": path.name})
        state.update(stage="export", last_event=event)
        output.write_text(json.dumps(state))
    state.update(stage="done", rows=rows)
except Exception:
    state.update(stage="error", error=traceback.format_exc())
finally:
    output.write_text(json.dumps(state, indent=2))
    if replay:
        replay.Shutdown()
    if cap:
        cap.Shutdown()
