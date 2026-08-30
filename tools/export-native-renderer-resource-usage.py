"""Export payload-free RenderDoc resource-usage metadata through qrenderdoc."""

import hashlib
import json
import os
import sys

import renderdoc as rd


SCHEMA = "pinyon-shift.native-renderer-renderdoc-resource-usage.v1"


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
    return digest.hexdigest()


def main():
    capture_path = os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"]
    resource_name = os.environ["PINYON_SHIFT_RENDERDOC_RESOURCE_NAME"]
    report_path = os.environ["PINYON_SHIFT_RENDERDOC_RESOURCE_USAGE"]
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

        matches = [
            resource
            for resource in controller.GetResources()
            if resource.name == resource_name
        ]
        if len(matches) != 1:
            raise RuntimeError(
                "resource name matched {} resources: {}".format(
                    len(matches), resource_name
                )
            )
        resource = matches[0]
        textures = {
            str(texture.resourceId): texture
            for texture in controller.GetTextures()
        }
        texture = textures.get(str(resource.resourceId))
        actions = {
            action.eventId: action
            for action in flatten(controller.GetRootActions())
        }
        usages = []
        for usage in controller.GetUsage(resource.resourceId):
            action = actions.get(usage.eventId)
            usages.append(
                {
                    "event_id": usage.eventId,
                    "usage": usage.usage.name,
                    "action_name": None if action is None else action.customName,
                    "action_flags": None if action is None else str(action.flags),
                }
            )
        target = {
            "resource_id": str(resource.resourceId),
            "resource_name": resource.name,
        }
        if texture is not None:
            target.update(
                {
                    "width": texture.width,
                    "height": texture.height,
                    "format": texture.format.Name(),
                    "mips": texture.mips,
                    "arraysize": texture.arraysize,
                    "ms_samp": texture.msSamp,
                }
            )
        report = {
            "schema": SCHEMA,
            "capture": {
                "path": os.path.basename(capture_path),
                "sha256": sha256(capture_path),
            },
            "resource": target,
            "usages": usages,
            "safety": {
                "resource_payload_exported": False,
                "action_metadata_only": True,
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
    sys.stderr.write(
        "native renderer resource usage export failed: {}\n".format(error)
    )
    sys.exit(1)
