"""Export the paired NR-02E RenderDoc marker outputs.

This script is executed by qrenderdoc's bundled Python runtime. Inputs are
passed through environment variables by export-native-renderer-renderdoc.ps1
so RenderDoc's command-line parser never needs to understand tool arguments.
"""

import hashlib
import json
import os
import sys
import traceback

import renderdoc as rd


ISOLATED_MARKER = os.environ.get(
    "PINYON_SHIFT_RENDERDOC_NATIVE_MARKER",
    "PinyonShift NR-02E isolated native draw",
)
XENOS_MARKER = os.environ.get(
    "PINYON_SHIFT_RENDERDOC_XENOS_MARKER",
    "PinyonShift NR-02E authoritative Xenos draw",
)
COMPLETE_PASS = os.environ.get(
    "PINYON_SHIFT_RENDERDOC_COMPLETE_PASS", "0"
) == "1"
PASS_NATIVE_ANCHOR_MARKER = "PinyonShift NR-02F isolated native pass anchor"
PASS_XENOS_ANCHOR_MARKER = "PinyonShift NR-02F authoritative Xenos pass anchor"
PASS_NATIVE_FOLLOWER_MARKER = "PinyonShift NR-02F isolated native pass follower"
PASS_XENOS_FOLLOWER_MARKER = "PinyonShift NR-02F authoritative Xenos pass follower"
SCHEMA = "pinyon-shift.native-renderer-renderdoc-export.v1"
COMPLETE_PASS_SCHEMA = "pinyon-shift.native-renderer-pass-renderdoc-export.v1"


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


def _first_named_after(actions, name, event_id):
    return next(
        (action for action in actions
         if action.customName == name and action.eventId > event_id),
        None,
    )


def _export_bound_state(controller, output_dir, basename):
    colors, depth = _bound_targets(controller)
    if not colors:
        raise RuntimeError("complete pass has no color output at {}".format(basename))
    result = {
        "color": _export_texture(
            controller, colors[0], os.path.join(output_dir, basename + ".png")
        ),
        "depth": None,
    }
    if depth.resource != rd.ResourceId.Null():
        result["depth"] = _export_texture(
            controller,
            depth,
            os.path.join(output_dir, basename + "-depth.png"),
            channel_extract=0,
        )
    return result


def _export_pass_span(controller, first_marker, last_marker, output_dir, basename):
    first_draw = _first_draw(first_marker)
    last_draw = _first_draw(last_marker)
    if first_draw is None or last_draw is None:
        raise RuntimeError("complete-pass marker span contains no draw")
    if not (
        first_marker.eventId <= first_draw.eventId < last_marker.eventId <= last_draw.eventId
    ):
        raise RuntimeError("complete-pass marker/draw order is invalid")

    controller.SetFrameEvent(first_marker.eventId, True)
    before = _export_bound_state(controller, output_dir, basename + "-before")
    controller.SetFrameEvent(last_draw.eventId, True)
    after = _export_bound_state(controller, output_dir, basename)

    for target in ("color", "depth"):
        before_target = before[target]
        after_target = after[target]
        if (before_target is None) != (after_target is None):
            raise RuntimeError("{} attachment presence changed across pass".format(target))
        if before_target is None:
            continue
        if before_target["resource_id"] != after_target["resource_id"]:
            raise RuntimeError("{} resource changed across pass".format(target))
        if (before_target["width"], before_target["height"]) != (
            after_target["width"], after_target["height"]
        ):
            raise RuntimeError("{} dimensions changed across pass".format(target))

    return {
        "start_marker": first_marker.customName,
        "start_marker_event_id": first_marker.eventId,
        "start_draw_event_id": first_draw.eventId,
        "end_marker": last_marker.customName,
        "end_marker_event_id": last_marker.eventId,
        "end_draw_event_id": last_draw.eventId,
        "draw_count": 2,
        "before": before,
        "after": after,
    }


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


def _export_complete_pass(controller, actions, capture_path, output_dir):
    native_anchors = [
        action for action in actions
        if action.customName == PASS_NATIVE_ANCHOR_MARKER
    ]
    if not native_anchors:
        available_markers = sorted(
            set(
                action.customName
                for action in actions
                if action.customName and "PinyonShift" in action.customName
            )
        )
        raise RuntimeError(
            "no complete-pass native anchor marker was found; "
            "available PinyonShift markers={}".format(available_markers)
        )
    native_anchor = native_anchors[0]
    xenos_anchor = _first_named_after(
        actions, PASS_XENOS_ANCHOR_MARKER, native_anchor.eventId
    )
    native_follower = _first_named_after(
        actions, PASS_NATIVE_FOLLOWER_MARKER,
        xenos_anchor.eventId if xenos_anchor else native_anchor.eventId,
    )
    xenos_follower = _first_named_after(
        actions, PASS_XENOS_FOLLOWER_MARKER,
        native_follower.eventId if native_follower else native_anchor.eventId,
    )
    if not xenos_anchor or not native_follower or not xenos_follower:
        raise RuntimeError("a complete native/Xenos anchor/follower marker chain was not found")
    marker_order = [
        native_anchor.eventId,
        xenos_anchor.eventId,
        native_follower.eventId,
        xenos_follower.eventId,
    ]
    if marker_order != sorted(marker_order) or len(set(marker_order)) != 4:
        raise RuntimeError("complete-pass markers are not strictly ordered")

    native = _export_pass_span(
        controller, native_anchor, native_follower, output_dir, "isolated-native"
    )
    xenos = _export_pass_span(
        controller, xenos_anchor, xenos_follower, output_dir, "authoritative-xenos"
    )
    native_color = native["after"]["color"]
    xenos_color = xenos["after"]["color"]
    if native_color["resource_id"] == xenos_color["resource_id"]:
        raise RuntimeError("native and Xenos pass outputs alias")
    if (native_color["width"], native_color["height"]) != (
        xenos_color["width"], xenos_color["height"]
    ):
        raise RuntimeError("native and Xenos pass output dimensions differ")

    return {
        "schema": COMPLETE_PASS_SCHEMA,
        "capture": {
            "path": os.path.basename(capture_path),
            "sha256": _sha256(capture_path),
        },
        "marker_counts": {
            "native_anchor": len(native_anchors),
            "xenos_anchor": sum(
                action.customName == PASS_XENOS_ANCHOR_MARKER for action in actions
            ),
            "native_follower": sum(
                action.customName == PASS_NATIVE_FOLLOWER_MARKER for action in actions
            ),
            "xenos_follower": sum(
                action.customName == PASS_XENOS_FOLLOWER_MARKER for action in actions
            ),
        },
        "marker_order": marker_order,
        "native_pass": native,
        "xenos_pass": xenos,
        "safety": {
            "xenos_draws_preserved": True,
            "draw_suppression_implemented": False,
            "resolve_suppression_implemented": False,
            "suppression_allowed": False,
        },
    }


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
        if COMPLETE_PASS:
            report = _export_complete_pass(
                controller, actions, capture_path, output_dir
            )
            with open(report_path, "w") as output:
                json.dump(report, output, indent=2, sort_keys=True)
                output.write("\n")
            print(report_path)
            return 0

        isolated = [a for a in actions if a.customName == ISOLATED_MARKER]
        xenos = [a for a in actions if a.customName == XENOS_MARKER]
        if not isolated or not xenos:
            available_markers = sorted(
                set(
                    a.customName
                    for a in actions
                    if a.customName and "PinyonShift" in a.customName
                )
            )
            raise RuntimeError(
                "paired markers were not found (isolated={}, xenos={}); "
                "available PinyonShift markers={}".format(
                    len(isolated), len(xenos), available_markers
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


def _entrypoint():
    try:
        return main()
    except Exception as error:
        message = "native renderer RenderDoc export failed: {}\n{}".format(
            error, traceback.format_exc()
        )
        output_dir = os.environ.get("PINYON_SHIFT_RENDERDOC_EXPORT_DIR")
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            with open(
                os.path.join(output_dir, "renderdoc-export-error.txt"), "w"
            ) as output:
                output.write(message)
        sys.stderr.write(message)
        return 1


if __name__ == "__main__":
    sys.exit(_entrypoint())
