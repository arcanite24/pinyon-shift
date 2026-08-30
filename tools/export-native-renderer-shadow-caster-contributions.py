"""Export local-only before/after depth images for exact caster writes."""

import hashlib
import json
import os
import sys
import traceback

import renderdoc as rd


SCHEMA = "pinyon-shift.native-renderer-shadow-caster-contributions.v1"


def flatten(actions):
    result = []
    for action in actions:
        result.append(action)
        result.extend(flatten(action.children))
    return result


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def parse_event_ids(value):
    try:
        event_ids = [int(item) for item in value.split(",") if item]
    except ValueError as error:
        raise RuntimeError("event ids must be decimal integers") from error
    if not event_ids or len(event_ids) > 128:
        raise RuntimeError("event inventory must contain 1 through 128 events")
    if event_ids != sorted(set(event_ids)) or event_ids[0] <= 0:
        raise RuntimeError("event ids must be positive, unique, and ordered")
    return event_ids


def save_texture(controller, resource_id, output_path):
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
        "path": os.path.basename(output_path),
        "bytes": os.path.getsize(output_path),
        "sha256": sha256(output_path),
    }


def main():
    capture_path = os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"]
    output_dir = os.environ["PINYON_SHIFT_RENDERDOC_EXPORT_DIR"]
    resource_name = os.environ["PINYON_SHIFT_RENDERDOC_RESOURCE_NAME"]
    event_ids = parse_event_ids(os.environ["PINYON_SHIFT_RENDERDOC_EVENT_IDS"])
    report_path = os.path.join(output_dir, "shadow-caster-contributions.json")
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

        resources = [
            resource
            for resource in controller.GetResources()
            if resource.name == resource_name
        ]
        if len(resources) != 1:
            raise RuntimeError(
                "resource name matched {} resources: {}".format(
                    len(resources), resource_name
                )
            )
        resource = resources[0]
        textures = {
            texture.resourceId: texture for texture in controller.GetTextures()
        }
        texture = textures.get(resource.resourceId)
        if texture is None:
            raise RuntimeError("selected resource is not a texture")
        actions = {
            action.eventId: action
            for action in flatten(controller.GetRootActions())
        }
        exports = []
        for event_id in event_ids:
            action = actions.get(event_id)
            if action is None or not action.flags & rd.ActionFlags.Drawcall:
                raise RuntimeError(
                    "event {} is not an exact draw action".format(event_id)
                )
            before_path = os.path.join(
                output_dir, "event-{:04d}-before.png".format(event_id)
            )
            after_path = os.path.join(
                output_dir, "event-{:04d}-after.png".format(event_id)
            )
            controller.SetFrameEvent(event_id - 1, True)
            before = save_texture(controller, resource.resourceId, before_path)
            controller.SetFrameEvent(event_id, True)
            after = save_texture(controller, resource.resourceId, after_path)
            exports.append(
                {
                    "event_id": event_id,
                    "action_name": action.customName,
                    "before": before,
                    "after": after,
                }
            )

        report = {
            "schema": SCHEMA,
            "capture": {
                "path": os.path.basename(capture_path),
                "sha256": sha256(capture_path),
            },
            "resource": {
                "resource_id": str(resource.resourceId),
                "resource_name": resource.name,
                "width": texture.width,
                "height": texture.height,
                "format": texture.format.Name(),
                "mips": texture.mips,
                "arraysize": texture.arraysize,
                "ms_samp": texture.msSamp,
            },
            "events": exports,
            "safety": {
                "local_resource_payload_exported": True,
                "tracked_payload_allowed": False,
                "xenos_authority": True,
                "native_rendering_changed": False,
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
    message = "shadow caster contribution export failed: {}\n{}".format(
        error, traceback.format_exc()
    )
    output_dir = os.environ.get("PINYON_SHIFT_RENDERDOC_EXPORT_DIR")
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        with open(
            os.path.join(output_dir, "shadow-caster-contributions-error.txt"),
            "w",
        ) as output:
            output.write(message)
    sys.stderr.write(message)
    sys.exit(1)
