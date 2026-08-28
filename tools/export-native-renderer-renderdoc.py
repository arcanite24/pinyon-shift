"""Export the paired NR-02E RenderDoc marker outputs.

This script is executed by qrenderdoc's bundled Python runtime. Inputs are
passed through environment variables by export-native-renderer-renderdoc.ps1
so RenderDoc's command-line parser never needs to understand tool arguments.
"""

import hashlib
import json
import os
import sys

import renderdoc as rd


ISOLATED_MARKER = "PinyonShift NR-02E isolated native draw"
XENOS_MARKER = "PinyonShift NR-02E authoritative Xenos draw"
SCHEMA = "pinyon-shift.native-renderer-renderdoc-export.v1"


def _flatten(actions):
    result = []
    for action in actions:
        result.append(action)
        result.extend(_flatten(action.children))
    return result


def _first_draw(action):
    if action.flags & rd.ActionFlags.Drawcall:
        return action
    for child in action.children:
        draw = _first_draw(child)
        if draw is not None:
            return draw
    return None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _texture_description(controller, resource_id):
    for texture in controller.GetTextures():
        if texture.resourceId == resource_id:
            return texture
    raise RuntimeError("output target texture description was not found")


def _export_texture(controller, target, output_path, channel_extract=-1):
    texture = _texture_description(controller, target.resource)
    save = rd.TextureSave()
    save.resourceId = target.resource
    save.destType = rd.FileType.PNG
    save.alpha = rd.AlphaMapping.Preserve
    save.mip = getattr(target, "firstMip", 0)
    save.slice.sliceIndex = getattr(target, "firstSlice", 0)
    save.channelExtract = channel_extract
    result = controller.SaveTexture(save, output_path)
    if hasattr(result, "code") and result.code != rd.ResultCode.Succeeded:
        raise RuntimeError(
            "RenderDoc failed to save '{}': {}".format(output_path, result)
        )
    if not os.path.isfile(output_path):
        raise RuntimeError("RenderDoc did not create '{}'".format(output_path))

    return {
        "resource_id": str(target.resource),
        "width": texture.width,
        "height": texture.height,
        "mip": save.mip,
        "slice": save.slice.sliceIndex,
        "channel_extract": channel_extract,
        "path": os.path.basename(output_path),
        "sha256": _sha256(output_path),
    }


def _bound_targets(controller):
    pipeline = controller.GetPipelineState()
    colors = [
        target
        for target in pipeline.GetOutputTargets()
        if target.resource != rd.ResourceId.Null()
    ]
    depth = pipeline.GetDepthTarget()
    return colors, depth


def _export_marker(controller, marker, output_dir, basename):
    draw = _first_draw(marker)
    if draw is None:
        raise RuntimeError("marker '{}' contains no draw".format(marker.customName))

    controller.SetFrameEvent(marker.eventId, True)
    before_colors, before_depth = _bound_targets(controller)
    if not before_colors:
        raise RuntimeError(
            "marker '{}' has no pre-draw color output".format(marker.customName)
        )
    before_color_path = os.path.join(output_dir, basename + "-before.png")
    before_depth_path = os.path.join(output_dir, basename + "-depth-before.png")
    before = {
        "color": _export_texture(
            controller, before_colors[0], before_color_path
        ),
        "depth": (
            _export_texture(
                controller, before_depth, before_depth_path, channel_extract=0
            )
            if before_depth.resource != rd.ResourceId.Null()
            else None
        ),
    }

    controller.SetFrameEvent(draw.eventId, True)
    targets, depth = _bound_targets(controller)
    if not targets:
        raise RuntimeError(
            "marker '{}' draw has no color output".format(marker.customName)
        )
    color_path = os.path.join(output_dir, basename + ".png")
    depth_path = os.path.join(output_dir, basename + "-depth.png")
    result = {
        "marker": marker.customName,
        "marker_event_id": marker.eventId,
        "draw_event_id": draw.eventId,
        "before": before,
        "color": _export_texture(controller, targets[0], color_path),
    }
    if depth.resource != rd.ResourceId.Null():
        result["depth"] = _export_texture(
            controller, depth, depth_path, channel_extract=0
        )
    else:
        result["depth"] = None
    return result


def main():
    capture_path = os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"]
    output_dir = os.environ["PINYON_SHIFT_RENDERDOC_EXPORT_DIR"]
    report_path = os.path.join(output_dir, "renderdoc-export.json")
    os.makedirs(output_dir, exist_ok=True)

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

        actions = _flatten(controller.GetRootActions())
        isolated = [a for a in actions if a.customName == ISOLATED_MARKER]
        xenos = [a for a in actions if a.customName == XENOS_MARKER]
        if not isolated or not xenos:
            raise RuntimeError(
                "paired markers were not found (isolated={}, xenos={})".format(
                    len(isolated), len(xenos)
                )
            )

        isolated_marker = isolated[0]
        paired_xenos = next(
            (a for a in xenos if a.eventId > isolated_marker.eventId), None
        )
        if paired_xenos is None:
            raise RuntimeError("no authoritative Xenos marker follows the native marker")

        report = {
            "schema": SCHEMA,
            "capture": {
                "path": os.path.basename(capture_path),
                "sha256": _sha256(capture_path),
            },
            "marker_counts": {
                "isolated_native": len(isolated),
                "authoritative_xenos": len(xenos),
            },
            "isolated_native": _export_marker(
                controller, isolated_marker, output_dir, "isolated-native"
            ),
            "authoritative_xenos": _export_marker(
                controller, paired_xenos, output_dir, "authoritative-xenos"
            ),
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
    sys.stderr.write("native renderer RenderDoc export failed: {}\n".format(error))
    sys.exit(1)
