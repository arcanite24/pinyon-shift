"""Export a payload-free draw/target trace from a RenderDoc capture.

Executed by qrenderdoc's bundled Python runtime. The resulting trace contains
only event metadata and resource descriptions; it never exports game images or
resource bytes.
"""

import hashlib
import json
import os
import sys

import renderdoc as rd


ISOLATED_MARKER = "PinyonShift NR-02E isolated native draw"
XENOS_MARKER = "PinyonShift NR-02E authoritative Xenos draw"
SCHEMA = "pinyon-shift.native-renderer-renderdoc-pass-trace.v1"


def flatten(actions):
    result = []
    for action in actions:
        result.append(action)
        result.extend(flatten(action.children))
    return result


def descendants(action):
    result = []
    for child in action.children:
        result.append(child)
        result.extend(descendants(child))
    return result


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def texture_map(controller):
    return {str(texture.resourceId): texture for texture in controller.GetTextures()}


def target_description(target, textures):
    if target.resource == rd.ResourceId.Null():
        return None
    resource_id = str(target.resource)
    texture = textures.get(resource_id)
    if texture is None:
        raise RuntimeError("target texture description was not found: " + resource_id)
    return {
        "resource_id": resource_id,
        "width": texture.width,
        "height": texture.height,
        "mip": getattr(target, "firstMip", 0),
        "slice": getattr(target, "firstSlice", 0),
        "format": texture.format.Name(),
    }


def boundary_kinds(action):
    kinds = []
    for name in ("Clear", "Copy", "Resolve", "Present", "Dispatch"):
        flag = getattr(rd.ActionFlags, name, None)
        if flag is not None and action.flags & flag:
            kinds.append(name.lower())
    return kinds


def main():
    capture_path = os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"]
    report_path = os.environ["PINYON_SHIFT_RENDERDOC_PASS_TRACE"]
    capture = rd.OpenCaptureFile()
    controller = None
    try:
        result = capture.OpenFile(capture_path, "", None)
        if result != rd.ResultCode.Succeeded:
            raise RuntimeError("could not open capture: {}".format(result))
        if not capture.LocalReplaySupport():
            raise RuntimeError("capture does not support local replay")
        result, controller = capture.OpenCapture(rd.ReplayOptions(), None)
        if result != rd.ResultCode.Succeeded:
            raise RuntimeError("could not initialise replay: {}".format(result))

        actions = flatten(controller.GetRootActions())
        isolated_events = set()
        authoritative_events = set()
        for action in actions:
            if action.customName == ISOLATED_MARKER:
                isolated_events.update(child.eventId for child in descendants(action))
            elif action.customName == XENOS_MARKER:
                authoritative_events.update(child.eventId for child in descendants(action))

        textures = texture_map(controller)
        events = []
        for action in actions:
            kinds = boundary_kinds(action)
            if kinds:
                events.append({
                    "event_id": action.eventId,
                    "kind": "boundary",
                    "boundary_kinds": kinds,
                })
            if not action.flags & rd.ActionFlags.Drawcall:
                continue
            controller.SetFrameEvent(action.eventId, True)
            pipeline = controller.GetPipelineState()
            colors = [
                target_description(target, textures)
                for target in pipeline.GetOutputTargets()
                if target.resource != rd.ResourceId.Null()
            ]
            events.append({
                "event_id": action.eventId,
                "kind": "draw",
                "index_count": action.numIndices,
                "instance_count": action.numInstances,
                "color_targets": colors,
                "depth_target": target_description(
                    pipeline.GetDepthTarget(), textures
                ),
                "isolated_native": action.eventId in isolated_events,
                "authoritative_candidate": action.eventId in authoritative_events,
            })

        events.sort(key=lambda event: (event["event_id"], event["kind"] != "boundary"))
        report = {
            "schema": SCHEMA,
            "capture": {
                "path": os.path.basename(capture_path),
                "sha256": sha256(capture_path),
            },
            "events": events,
            "safety": {
                "resource_payload_exported": False,
                "xenos_authority": True,
                "suppression_allowed": False,
            },
        }
        with open(report_path, "w") as output:
            json.dump(report, output, indent=2, sort_keys=True)
            output.write("\n")
        print(report_path)
        return 0
    finally:
        if controller is not None:
            controller.Shutdown()
        capture.Shutdown()


try:
    sys.exit(main())
except Exception as error:
    sys.stderr.write("native renderer pass trace failed: {}\n".format(error))
    sys.exit(1)
