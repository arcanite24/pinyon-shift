"""Find exact translated vegetation draws in a RenderDoc capture.

Run with qrenderdoc --python and SNR04_CAPTURE, SNR04_OUTPUT. Feed the report
to probe-snr04-vegetation-pixel-census.py as SNR04_EVENTS_JSON.
"""

import hashlib
import json
import os
from pathlib import Path
import traceback

import renderdoc as rd


expected_vs_sha = "2adfe080228c468ce9aec7e21d19798fc8aaa32cdba5d7325c4fac4070f21faa"
output = Path(os.environ["SNR04_OUTPUT"])
state = {"stage": "open", "matches": []}
output.write_text(json.dumps(state))
cap = replay = None
try:
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(os.environ["SNR04_CAPTURE"], "rdc", None)
    if "Success" not in str(result):
        raise RuntimeError(str(result))
    result, replay = cap.OpenCapture(rd.ReplayOptions(), None)
    if "Success" not in str(result):
        raise RuntimeError(str(result))

    def walk(actions):
        for action in actions:
            yield action
            yield from walk(action.children)

    draws = [action for action in walk(replay.GetRootActions())
             if action.flags & rd.ActionFlags.Drawcall]
    for index, action in enumerate(draws):
        replay.SetFrameEvent(action.eventId, True)
        pipeline = replay.GetPipelineState()
        vertex = pipeline.GetShaderReflection(rd.ShaderStage.Vertex)
        if vertex and hashlib.sha256(bytes(vertex.rawBytes)).hexdigest() == expected_vs_sha:
            state["matches"].append({
                "event": action.eventId,
                "pixel_textures": len(pipeline.GetReadOnlyResources(rd.ShaderStage.Pixel)),
            })
        if index % 500 == 0:
            state.update(stage="scan", index=index, draws=len(draws),
                         last_event=action.eventId, matched=len(state["matches"]))
            output.write_text(json.dumps(state))
    if not state["matches"]:
        raise RuntimeError("no vegetation draws matched the exact vertex shader")
    state.update(stage="done", matched=len(state["matches"]))
except Exception:
    state.update(stage="error", error=traceback.format_exc())
finally:
    output.write_text(json.dumps(state, indent=2))
    if replay:
        replay.Shutdown()
    if cap:
        cap.Shutdown()
