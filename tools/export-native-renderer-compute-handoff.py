"""Export payload-free compute handoffs for one RenderDoc resource.

Executed by qrenderdoc's bundled Python runtime. The report contains only
action, pipeline, descriptor, and resource-description metadata. It never
exports shader bytecode or resource payloads.
"""

import hashlib
import json
import os
import sys

import renderdoc as rd


SCHEMA = "pinyon-shift.native-renderer-renderdoc-compute-handoff.v1"


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


def resource_id(value):
    if value is None or value == rd.ResourceId.Null():
        return None
    return str(value)


def describe_resource(identifier, resources, textures, buffers):
    if identifier is None:
        return None
    result = {
        "resource_id": identifier,
        "resource_name": resources.get(identifier, ""),
    }
    texture = textures.get(identifier)
    if texture is not None:
        result.update(
            {
                "kind": "texture",
                "width": texture.width,
                "height": texture.height,
                "depth": texture.depth,
                "format": texture.format.Name(),
                "mips": texture.mips,
                "arraysize": texture.arraysize,
                "ms_samp": texture.msSamp,
            }
        )
    buffer = buffers.get(identifier)
    if buffer is not None:
        result.update({"kind": "buffer", "length": buffer.length})
    if "kind" not in result:
        result["kind"] = "other"
    return result


def describe_used_descriptor(used, resources, textures, buffers):
    descriptor = used.descriptor
    identifier = resource_id(descriptor.resource)
    result = {
        "access": {
            "stage": str(used.access.stage),
            "type": str(used.access.type),
            "index": used.access.index,
            "array_element": used.access.arrayElement,
        },
        "descriptor_type": str(descriptor.type),
        "byte_range": {
            "offset": descriptor.byteOffset,
            "size": descriptor.byteSize,
        },
        "resource": describe_resource(identifier, resources, textures, buffers),
    }
    if identifier is not None:
        result["subresource"] = {
            "first_mip": descriptor.firstMip,
            "num_mips": descriptor.numMips,
            "first_slice": descriptor.firstSlice,
            "num_slices": descriptor.numSlices,
        }
    return result


def main():
    capture_path = os.environ["PINYON_SHIFT_RENDERDOC_CAPTURE"]
    resource_name = os.environ["PINYON_SHIFT_RENDERDOC_RESOURCE_NAME"]
    report_path = os.environ["PINYON_SHIFT_RENDERDOC_COMPUTE_HANDOFF"]
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

        resource_list = controller.GetResources()
        matches = [resource for resource in resource_list if resource.name == resource_name]
        if len(matches) != 1:
            raise RuntimeError(
                "resource name matched {} resources: {}".format(
                    len(matches), resource_name
                )
            )
        target_id = matches[0].resourceId
        target_identifier = str(target_id)
        resources = {
            str(resource.resourceId): resource.name for resource in resource_list
        }
        textures = {
            str(texture.resourceId): texture for texture in controller.GetTextures()
        }
        buffers = {
            str(buffer.resourceId): buffer for buffer in controller.GetBuffers()
        }
        actions = {
            action.eventId: action
            for action in flatten(controller.GetRootActions())
        }
        compute_events = sorted(
            {
                usage.eventId
                for usage in controller.GetUsage(target_id)
                if usage.usage.name == "CS_Resource"
            }
        )
        handoffs = []
        for event_id in compute_events:
            action = actions.get(event_id)
            if action is None or not action.flags & rd.ActionFlags.Dispatch:
                raise RuntimeError(
                    "compute resource use is not a dispatch action: {}".format(event_id)
                )
            controller.SetFrameEvent(event_id, True)
            pipeline = controller.GetPipelineState()
            reads = [
                describe_used_descriptor(item, resources, textures, buffers)
                for item in pipeline.GetReadOnlyResources(rd.ShaderStage.Compute, True)
            ]
            writes = [
                describe_used_descriptor(item, resources, textures, buffers)
                for item in pipeline.GetReadWriteResources(rd.ShaderStage.Compute, True)
            ]
            target_reads = [
                item
                for item in reads
                if item["resource"] is not None
                and item["resource"]["resource_id"] == target_identifier
            ]
            if not target_reads:
                raise RuntimeError(
                    "dispatch does not bind the selected resource: {}".format(event_id)
                )
            handoffs.append(
                {
                    "event_id": event_id,
                    "action_name": action.customName,
                    "dispatch": {
                        "x": action.dispatchDimension[0],
                        "y": action.dispatchDimension[1],
                        "z": action.dispatchDimension[2],
                    },
                    "pipeline": describe_resource(
                        resource_id(pipeline.GetComputePipelineObject()),
                        resources,
                        textures,
                        buffers,
                    ),
                    "compute_shader": describe_resource(
                        resource_id(pipeline.GetShader(rd.ShaderStage.Compute)),
                        resources,
                        textures,
                        buffers,
                    ),
                    "selected_resource_reads": target_reads,
                    "read_only_resources": reads,
                    "read_write_resources": writes,
                    "classification": {
                        "semantic_role": "unknown_unclassified",
                        "native_coverage": False,
                        "publication_eligible": False,
                        "suppression_eligible": False,
                    },
                }
            )

        report = {
            "schema": SCHEMA,
            "capture": {
                "path": os.path.basename(capture_path),
                "sha256": sha256(capture_path),
            },
            "selected_resource": describe_resource(
                target_identifier, resources, textures, buffers
            ),
            "compute_handoffs": handoffs,
            "totals": {
                "compute_handoffs": len(handoffs),
                "read_write_bindings": sum(
                    len(item["read_write_resources"]) for item in handoffs
                ),
            },
            "qualification": {
                "compute_consumer_identity_complete": bool(handoffs),
                "output_resource_lineage_complete": False,
                "atlas_ownership_proved": False,
                "publication_allowed": False,
            },
            "safety": {
                "metadata_only": True,
                "shader_payload_exported": False,
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
    sys.stderr.write(
        "native renderer compute handoff export failed: {}\n".format(error)
    )
    sys.exit(1)
