"""Export bounded read-only bindings for one verified presentation draw."""

import hashlib
import json
import os
import sys

import renderdoc as rd


SCHEMA = "pinyon-shift.native-renderer-presentation-bindings.v1"


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


def format_name(value):
    name = getattr(value, "Name", None)
    return name() if callable(name) else str(value)


def resource_description(identifier, resource_names, textures, buffers):
    result = {
        "resource_id": identifier,
        "resource_name": resource_names.get(identifier, ""),
        "resource_kind": "unknown",
    }
    texture = textures.get(identifier)
    if texture is not None:
        result.update(
            {
                "resource_kind": "texture",
                "width": texture.width,
                "height": texture.height,
                "format": texture.format.Name(),
                "mips": texture.mips,
                "arraysize": texture.arraysize,
                "ms_samp": texture.msSamp,
            }
        )
    buffer = buffers.get(identifier)
    if buffer is not None:
        result.update(
            {
                "resource_kind": "buffer",
                "length": buffer.length,
            }
        )
    return result


def main():
    capture_path = os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"]
    report_path = os.environ["PINYON_SHIFT_RENDERDOC_PRESENTATION_BINDINGS"]
    event_id = int(os.environ["PINYON_SHIFT_RENDERDOC_PRESENTATION_EVENT"])
    if event_id <= 0:
        raise RuntimeError("presentation event must be positive")
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
        matches = [action for action in actions if action.eventId == event_id]
        if len(matches) != 1 or not matches[0].flags & rd.ActionFlags.Drawcall:
            raise RuntimeError("presentation event is not one exact draw")
        present_flag = getattr(rd.ActionFlags, "Present", None)
        later_present = next(
            (
                action.eventId
                for action in actions
                if action.eventId > event_id
                and present_flag is not None
                and action.flags & present_flag
            ),
            None,
        )
        if later_present is None:
            raise RuntimeError("presentation draw has no later present boundary")

        resources = controller.GetResources()
        resource_names = {
            str(resource.resourceId): resource.name for resource in resources
        }
        textures = {
            str(texture.resourceId): texture for texture in controller.GetTextures()
        }
        buffers = {
            str(buffer.resourceId): buffer for buffer in controller.GetBuffers()
        }
        resource_ids = {
            str(resource.resourceId): resource.resourceId for resource in resources
        }
        controller.SetFrameEvent(event_id, True)
        pipeline = controller.GetPipelineState()
        outputs = [
            target
            for target in pipeline.GetOutputTargets()
            if target.resource != rd.ResourceId.Null()
        ]
        if len(outputs) != 1:
            raise RuntimeError("presentation draw must bind one color target")
        output_id = str(outputs[0].resource)
        output_name = resource_names.get(output_id, "")
        if not output_name.startswith("Swapchain Image "):
            raise RuntimeError("presentation draw does not target the swapchain")

        bindings = []
        seen = set()
        for used in pipeline.GetReadOnlyResources(rd.ShaderStage.Pixel):
            descriptor = used.descriptor
            access = used.access
            identifier = str(descriptor.resource)
            if identifier == str(rd.ResourceId.Null()):
                continue
            key = (
                identifier,
                int(access.index),
                int(access.arrayElement),
            )
            if key in seen:
                raise RuntimeError("duplicate presentation binding")
            seen.add(key)
            resource = resource_ids.get(identifier)
            if resource is None:
                raise RuntimeError("bound presentation resource is unknown")
            bindings.append(
                {
                    **resource_description(
                        identifier, resource_names, textures, buffers
                    ),
                    "stage": str(access.stage),
                    "descriptor_type": str(access.type),
                    "index": int(access.index),
                    "array_element": int(access.arrayElement),
                    "statically_unused": bool(access.staticallyUnused),
                    "byte_offset": int(descriptor.byteOffset),
                    "byte_size": int(descriptor.byteSize),
                    "first_mip": int(descriptor.firstMip),
                    "num_mips": int(descriptor.numMips),
                    "first_slice": int(descriptor.firstSlice),
                    "num_slices": int(descriptor.numSlices),
                    "view_format": format_name(descriptor.format),
                    "texture_type": str(descriptor.textureType),
                    "usages": [
                        {
                            "event_id": usage.eventId,
                            "usage": usage.usage.name,
                        }
                        for usage in controller.GetUsage(resource)
                    ],
                }
            )
        bindings.sort(
            key=lambda binding: (
                binding["index"],
                binding["array_element"],
                binding["resource_id"],
            )
        )
        if not bindings:
            raise RuntimeError("presentation draw has no pixel read-only binding")
        report = {
            "schema": SCHEMA,
            "capture": {
                "path": os.path.basename(capture_path),
                "sha256": sha256(capture_path),
            },
            "presentation": {
                "draw_event": event_id,
                "present_event": later_present,
                "output_resource_id": output_id,
                "output_resource_name": output_name,
                "output": resource_description(
                    output_id, resource_names, textures, buffers
                ),
            },
            "bindings": bindings,
            "totals": {
                "bindings": len(bindings),
                "statically_unused": sum(
                    binding["statically_unused"] for binding in bindings
                ),
            },
            "safety": {
                "resource_payload_exported": False,
                "action_metadata_only": True,
                "xenos_authority": True,
                "native_coverage": False,
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
        "native renderer presentation binding export failed: {}\n".format(error)
    )
    sys.exit(1)
