"""Export payload-free usage metadata for every authoritative color target."""

import hashlib
import json
import os
import sys

import renderdoc as rd


SCHEMA = "pinyon-shift.native-renderer-renderdoc-target-usage.v1"
ISOLATED_MARKER = "PinyonShift NR-02E isolated native draw"


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


def texture_description(resource, texture, resource_names):
    return {
        "resource_id": str(resource),
        "resource_name": resource_names.get(str(resource), ""),
        "width": texture.width,
        "height": texture.height,
        "format": texture.format.Name(),
        "mips": texture.mips,
        "arraysize": texture.arraysize,
        "ms_samp": texture.msSamp,
    }


def main():
    capture_path = os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"]
    report_path = os.environ["PINYON_SHIFT_RENDERDOC_TARGET_USAGE"]
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
        for action in actions:
            if action.customName == ISOLATED_MARKER:
                isolated_events.update(child.eventId for child in descendants(action))
        textures = {
            str(texture.resourceId): texture for texture in controller.GetTextures()
        }
        resource_names = {
            str(resource.resourceId): resource.name
            for resource in controller.GetResources()
        }
        targets = {}
        transfers = []
        skipped_non_texture_transfers = 0
        for action in actions:
            if (
                not action.flags & rd.ActionFlags.Drawcall
                or action.eventId in isolated_events
            ):
                continue
            controller.SetFrameEvent(action.eventId, True)
            for target in controller.GetPipelineState().GetOutputTargets():
                if target.resource == rd.ResourceId.Null():
                    continue
                identifier = str(target.resource)
                texture = textures.get(identifier)
                if texture is None:
                    raise RuntimeError(
                        "color target texture description was not found: "
                        + identifier
                    )
                targets[identifier] = (target.resource, texture)

        for action in actions:
            transfer_kind = None
            copy_flag = getattr(rd.ActionFlags, "Copy", None)
            resolve_flag = getattr(rd.ActionFlags, "Resolve", None)
            if copy_flag is not None and action.flags & copy_flag:
                transfer_kind = "copy"
            elif resolve_flag is not None and action.flags & resolve_flag:
                transfer_kind = "resolve"
            if transfer_kind is None:
                continue
            source = getattr(action, "copySource", rd.ResourceId.Null())
            destination = getattr(action, "copyDestination", rd.ResourceId.Null())
            if (
                source == rd.ResourceId.Null()
                or destination == rd.ResourceId.Null()
            ):
                continue
            destination_id = str(destination)
            destination_texture = textures.get(destination_id)
            if destination_texture is None:
                skipped_non_texture_transfers += 1
                continue
            targets[destination_id] = (destination, destination_texture)
            transfers.append(
                {
                    "event_id": action.eventId,
                    "kind": transfer_kind,
                    "source_resource_id": str(source),
                    "destination_resource_id": destination_id,
                }
            )

        resources = []
        for identifier in sorted(targets):
            resource, texture = targets[identifier]
            usages = [
                {
                    "event_id": usage.eventId,
                    "usage": usage.usage.name,
                }
                for usage in controller.GetUsage(resource)
            ]
            resources.append(
                {
                    **texture_description(resource, texture, resource_names),
                    "usages": usages,
                }
            )
        report = {
            "schema": SCHEMA,
            "capture": {
                "path": os.path.basename(capture_path),
                "sha256": sha256(capture_path),
            },
            "resources": resources,
            "transfers": transfers,
            "totals": {
                "color_target_resources": len(resources),
                "transfers": len(transfers),
                "skipped_non_texture_transfers": skipped_non_texture_transfers,
                "usage_references": sum(
                    len(resource["usages"]) for resource in resources
                ),
            },
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
    sys.stderr.write("native renderer target usage failed: {}\n".format(error))
    sys.exit(1)
