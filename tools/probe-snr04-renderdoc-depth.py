"""Read depth samples around one or more draws via qrenderdoc --python.

Set SNR04_CAPTURE and SNR04_OUTPUT. Set SNR04_EVENT for one draw, or
SNR04_EVENTS_JSON to a pixel-input census for all its textured draws.
"""

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import traceback

import renderdoc as rd

capture = Path(os.environ['SNR04_CAPTURE'])
out = Path(os.environ['SNR04_OUTPUT'])
batch = 'SNR04_EVENTS_JSON' in os.environ
events = ([row['event'] for row in json.loads(Path(
    os.environ['SNR04_EVENTS_JSON']).read_text())['draws']]
          if batch else [int(os.environ['SNR04_EVENT'])])
assert events and len(events) == len(set(events))
state = {'stage': 'open', 'capture': capture.name, 'events': events,
         'completed': []}


def save():
    out.write_text(json.dumps(state))


def capture_draw(replay, event, path, textures):
    detail = {'stage': 'read', 'capture': capture.name, 'event': event}

    def save_detail():
        path.write_text(json.dumps(detail))

    replay.SetFrameEvent(event, True)
    pipeline = replay.GetPipelineState()
    target = pipeline.GetDepthTarget()
    texture = textures[target.resource]
    viewport = pipeline.GetViewport(0)
    detail.update(depth_resource=str(target.resource),
                  format=texture.format.Name(), width=texture.width,
                  height=texture.height, samples=texture.msSamp,
                  viewport=[viewport.x, viewport.y, viewport.width,
                            viewport.height, viewport.minDepth, viewport.maxDepth])
    save_detail()
    assert detail['format'] == 'D32S8_TYPELESS' and texture.msSamp == 4
    subresource = rd.Subresource()
    subresource.mip = target.firstMip
    subresource.slice = target.firstSlice
    detail['sample_details'] = []
    coverage = bytearray(texture.width * texture.height)
    for sample in range(texture.msSamp):
        subresource.sample = sample
        data = []
        sample_detail = {'sample': sample}
        for label, frame_event in (('before', event - 1), ('after', event)):
            replay.SetFrameEvent(frame_event, True)
            value = bytes(replay.GetTextureData(target.resource, subresource))
            assert len(value) == texture.width * texture.height * 8
            suffix = '' if sample == 0 else f'-s{sample}'
            (path.parent / f'{path.stem}-{label}{suffix}.depth').write_bytes(value)
            sample_detail[label] = {'bytes': len(value),
                                    'sha256': hashlib.sha256(value).hexdigest()}
            data.append(value)
        changes = [i for i in range(texture.width * texture.height)
                   if data[0][i * 8:i * 8 + 4] != data[1][i * 8:i * 8 + 4]]
        for pixel in changes:
            coverage[pixel] |= 1 << sample
        sample_detail['changed_depth_samples'] = len(changes)
        sample_detail['changed_depth_range'] = [
            min(struct.unpack_from('<f', data[1], i * 8)[0] for i in changes),
            max(struct.unpack_from('<f', data[1], i * 8)[0] for i in changes)] if changes else []
        detail['sample_details'].append(sample_detail)
        if sample == 0:
            detail['before'], detail['after'] = sample_detail['before'], sample_detail['after']
            detail['changed_texels_sample0'] = len(changes)
            detail['changed_depth_range_sample0'] = sample_detail['changed_depth_range']
    coverage_path = path.parent / f'{path.stem}-coverage.u8'
    coverage_path.write_bytes(coverage)
    detail['coverage'] = {'bytes': len(coverage),
                          'sha256': hashlib.sha256(coverage).hexdigest(),
                          'pixels': sum(bool(mask) for mask in coverage),
                          'samples': sum(bin(mask).count('1') for mask in coverage)}
    detail['stage'] = 'done'
    save_detail()
    return detail


cap = replay = None
try:
    save()
    cap = rd.OpenCaptureFile()
    result = cap.OpenFile(str(capture), 'rdc', None)
    if 'Success' not in str(result):
        raise RuntimeError(str(result))
    result, replay = cap.OpenCapture(rd.ReplayOptions(), None)
    if 'Success' not in str(result):
        raise RuntimeError(str(result))
    textures = {texture.resourceId: texture for texture in replay.GetTextures()}
    for event in events:
        path = (out.parent / f'{out.stem}-{event}.json') if batch else out
        state['current_event'] = event
        state['stage'] = 'read'
        save()
        detail = capture_draw(replay, event, path, textures)
        if batch:
            state['completed'].append(event)
        else:
            state = detail
        save()
    state['stage'] = 'done'
except Exception:
    state.update(stage='error', error=traceback.format_exc())
finally:
    save()
    if replay:
        replay.Shutdown()
    if cap:
        cap.Shutdown()
sys.exit(0)
