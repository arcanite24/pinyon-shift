"""Export the bound pixel inputs for one matched vegetation event in RenderDoc.

Run with qrenderdoc.exe --python and SNR04_CAPTURE, SNR04_OUTPUT, SNR04_EVENT.
"""

import json
import os
from pathlib import Path
import struct
import traceback

import renderdoc as rd


output = Path(os.environ["SNR04_OUTPUT"])
state = {"stage": "open"}
output.write_text(json.dumps(state), encoding="utf-8")
capture = replay = None
try:
    capture = rd.OpenCaptureFile()
    result = capture.OpenFile(os.environ["SNR04_CAPTURE"], "rdc", None)
    assert "Success" in str(result), result
    result, replay = capture.OpenCapture(rd.ReplayOptions(), None)
    assert "Success" in str(result), result
    event = int(os.environ["SNR04_EVENT"])
    replay.SetFrameEvent(event, True)
    pipeline = replay.GetPipelineState()
    blocks = []
    for index, count in enumerate((120, 12, 192, 8)):
        descriptor = pipeline.GetConstantBlock(rd.ShaderStage.Pixel, index, 0).descriptor
        data = bytes(replay.GetBufferData(descriptor.resource,
                                          descriptor.byteOffset, count * 4))
        assert len(data) == count * 4
        blocks.append(list(struct.unpack(f"<{count}I", data)))
    textures = [{"index": used.access.arrayElement,
                 "resource": str(used.descriptor.resource)}
                for used in pipeline.GetReadOnlyResources(rd.ShaderStage.Pixel)]
    samplers = []
    for used in pipeline.GetSamplers(rd.ShaderStage.Pixel):
        sampler = used.sampler
        samplers.append({"index": used.access.arrayElement,
                         "address_u": str(sampler.addressU),
                         "address_v": str(sampler.addressV),
                         "address_w": str(sampler.addressW),
                         "min_filter": str(sampler.filter.minify),
                         "mag_filter": str(sampler.filter.magnify),
                         "mip_filter": str(sampler.filter.mip),
                         "max_anisotropy": sampler.maxAnisotropy,
                         "min_lod": sampler.minLOD,
                         "max_lod": sampler.maxLOD,
                         "mip_bias": sampler.mipBias})
    state = {"stage": "done", "event": event,
             "shader": str(pipeline.GetShader(rd.ShaderStage.Pixel)),
             "blocks": blocks, "textures": textures, "samplers": samplers}
except Exception:
    state = {"stage": "error", "error": traceback.format_exc()}
finally:
    output.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    if replay:
        replay.Shutdown()
    if capture:
        capture.Shutdown()
