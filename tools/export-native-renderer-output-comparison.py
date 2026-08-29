"""Export same-frame Xenos/native output and GPU timings from RenderDoc.

This script runs inside qrenderdoc's bundled Python runtime. The PowerShell
wrapper passes local paths through environment variables so captures and
game-derived images never enter the public source tree.
"""

import hashlib
import json
import os
import sys
import traceback

import renderdoc as rd


COMPOSITION_MARKER = os.environ.get(
    "PINYON_SHIFT_RENDERDOC_COMPOSITION_MARKER",
    "PinyonShift NR-04C native display composition",
)
SELECTION_MARKER = os.environ.get(
    "PINYON_SHIFT_RENDERDOC_SELECTION_MARKER",
    "PinyonShift NR-04C native output selection",
)
SCHEMA = "pinyon-shift.native-output-comparison.v1"


def _flatten(actions):
    result = []
    for action in actions:
        result.append(action)
        result.extend(_flatten(action.children))
    return result


def _first_action(marker, flag):
    for action in _flatten(marker.children):
        if action.flags & flag:
            return action
    return None


def _action_name(action, structured_file):
    """Return RenderDoc's displayed action name, including debug markers."""
    name = action.GetName(structured_file)
    return name if name else action.customName


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
    raise RuntimeError("comparison texture description was not found")


def _texture_summary(texture_by_id, resource_id):
    texture = texture_by_id.get(resource_id)
    if texture is None:
        return None
    return {
        "resource_id": str(resource_id),
        "width": texture.width,
        "height": texture.height,
    }


def _export_resource(controller, resource_id, output_path):
    if resource_id == rd.ResourceId.Null():
        raise RuntimeError("comparison action references a null texture")
    texture = _texture_description(controller, resource_id)
    save = rd.TextureSave()
    save.resourceId = resource_id
    save.destType = rd.FileType.PNG
    save.alpha = rd.AlphaMapping.Preserve
    result = controller.SaveTexture(save, output_path)
    if hasattr(result, "code") and result.code != rd.ResultCode.Succeeded:
        raise RuntimeError(
            "RenderDoc failed to save '{}': {}".format(output_path, result)
        )
    if not os.path.isfile(output_path):
        raise RuntimeError("RenderDoc did not create '{}'".format(output_path))
    return {
        "resource_id": str(resource_id),
        "width": texture.width,
        "height": texture.height,
        "path": os.path.basename(output_path),
        "sha256": _sha256(output_path),
    }


def _gpu_durations(controller):
    available = controller.EnumerateCounters()
    counter = rd.GPUCounter.EventGPUDuration
    if counter not in available:
        raise RuntimeError("RenderDoc replay does not expose GPU duration")
    results = controller.FetchCounters([counter])
    return {result.eventId: float(result.value.d) for result in results}


def _timing(event_id, durations):
    if event_id not in durations:
        raise RuntimeError(
            "RenderDoc returned no GPU duration for event {}".format(event_id)
        )
    seconds = durations[event_id]
    return {"event_id": event_id, "seconds": seconds, "microseconds": seconds * 1e6}


def main():
    capture_path = os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"]
    output_dir = os.environ["PINYON_SHIFT_RENDERDOC_EXPORT_DIR"]
    report_path = os.path.join(output_dir, "native-output-comparison.json")
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
        structured_file = controller.GetStructuredFile()
        action_names = {
            action.eventId: _action_name(action, structured_file)
            for action in actions
        }
        texture_by_id = {
            texture.resourceId: texture for texture in controller.GetTextures()
        }
        compositions = [
            action
            for action in actions
            if action_names[action.eventId] == COMPOSITION_MARKER
        ]
        selections = [
            action
            for action in actions
            if action_names[action.eventId] == SELECTION_MARKER
        ]
        if not compositions or not selections:
            marker_actions = [
                action
                for action in actions
                if action.flags
                & (rd.ActionFlags.PushMarker | rd.ActionFlags.SetMarker)
            ]
            available_markers = sorted(
                set(action_names[action.eventId] for action in marker_actions)
            )
            copy_actions = [
                {
                    "event_id": action.eventId,
                    "name": action_names[action.eventId],
                    "source": _texture_summary(texture_by_id, action.copySource),
                    "destination": _texture_summary(
                        texture_by_id, action.copyDestination
                    ),
                }
                for action in actions
                if action.flags & rd.ActionFlags.Copy
                and "CopyResource" in action_names[action.eventId]
            ][:64]
            raise RuntimeError(
                "NR-04C markers were not found (composition={}, selection={}); "
                "action_count={}, marker_actions={}, available={}, copies={}, "
                "sample_actions={}".format(
                    len(compositions),
                    len(selections),
                    len(actions),
                    len(marker_actions),
                    available_markers,
                    copy_actions,
                    [
                        (action.eventId, action_names[action.eventId], int(action.flags))
                        for action in actions[:20] + actions[-20:]
                    ],
                )
            )

        selection = selections[0]
        composition = next(
            (a for a in reversed(compositions) if a.eventId < selection.eventId),
            None,
        )
        if composition is None:
            raise RuntimeError("native selection has no preceding composition marker")
        dispatch = _first_action(composition, rd.ActionFlags.Dispatch)
        copy = _first_action(selection, rd.ActionFlags.Copy)
        if dispatch is None:
            raise RuntimeError("composition marker contains no dispatch")
        if copy is None:
            raise RuntimeError("selection marker contains no copy")
        if copy.copySource == rd.ResourceId.Null():
            raise RuntimeError("selection copy has no native source")
        if copy.copyDestination == rd.ResourceId.Null():
            raise RuntimeError("selection copy has no guest-output destination")
        if copy.copySource == copy.copyDestination:
            raise RuntimeError("native and Xenos outputs alias the same resource")

        controller.SetFrameEvent(copy.eventId - 1, True)
        xenos = _export_resource(
            controller,
            copy.copyDestination,
            os.path.join(output_dir, "xenos-output.png"),
        )
        native_private = _export_resource(
            controller,
            copy.copySource,
            os.path.join(output_dir, "native-private.png"),
        )
        controller.SetFrameEvent(copy.eventId, True)
        native_selected = _export_resource(
            controller,
            copy.copyDestination,
            os.path.join(output_dir, "native-selected.png"),
        )
        if native_private["sha256"] != native_selected["sha256"]:
            raise RuntimeError(
                "selected native output differs from the private display target"
            )
        if (xenos["width"], xenos["height"]) != (
            native_selected["width"],
            native_selected["height"],
        ):
            raise RuntimeError("paired output dimensions do not match")

        durations = _gpu_durations(controller)
        report = {
            "schema": SCHEMA,
            "capture": {
                "path": os.path.basename(capture_path),
                "sha256": _sha256(capture_path),
            },
            "marker_counts": {
                "composition": len(compositions),
                "selection": len(selections),
            },
            "markers": {
                "composition_event_id": composition.eventId,
                "selection_event_id": selection.eventId,
            },
            "selected_output": "native",
            "same_frame": True,
            "sequential_guest_output_writers": True,
            "xenos_before_selection": xenos,
            "native_private": native_private,
            "native_after_selection": native_selected,
            "gpu_timing": {
                "native_composition": _timing(dispatch.eventId, durations),
                "native_selection_copy": _timing(copy.eventId, durations),
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
    message = "native output comparison export failed: {}\n{}".format(
        error, traceback.format_exc()
    )
    output_dir = os.environ.get("PINYON_SHIFT_RENDERDOC_EXPORT_DIR")
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        with open(
            os.path.join(output_dir, "native-output-comparison-error.txt"), "w"
        ) as output:
            output.write(message)
    sys.stderr.write(message)
    sys.exit(1)
