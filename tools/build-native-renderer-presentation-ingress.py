"""Join one presentation binding report to the fail-closed post-chain census."""

import argparse
from fractions import Fraction
import hashlib
import json
import pathlib
import sys


BINDING_SCHEMA = "pinyon-shift.native-renderer-presentation-bindings.v1"
POST_SCHEMA = "pinyon-shift.native-renderer-post-chain-census.v1"
SCHEMA = "pinyon-shift.native-renderer-presentation-ingress.v1"
WRITE_USAGES = {
    "ColorTarget",
    "CopyDst",
    "ResolveDst",
    "CS_RWResource",
    "PS_RWResource",
}


def ratio(output_size, input_size):
    if type(output_size) is not int or type(input_size) is not int:
        raise ValueError("presentation dimensions must be integers")
    if output_size <= 0 or input_size <= 0:
        raise ValueError("presentation dimensions must be positive")
    value = Fraction(output_size, input_size)
    return {"numerator": value.numerator, "denominator": value.denominator}


def build_ingress(bindings, post_census):
    if bindings.get("schema") != BINDING_SCHEMA:
        raise ValueError("unsupported presentation-binding schema")
    if post_census.get("schema") != POST_SCHEMA:
        raise ValueError("unsupported post-chain census schema")
    binding_safety = bindings.get("safety", {})
    census_safety = post_census.get("safety", {})
    if binding_safety.get("resource_payload_exported") is not False:
        raise ValueError("binding report does not prove its payload-free boundary")
    if binding_safety.get("action_metadata_only") is not True:
        raise ValueError("binding report is not action-metadata-only")
    if census_safety.get("metadata_only") is not True:
        raise ValueError("post-chain census is not metadata-only")
    for safety in (binding_safety, census_safety):
        if safety.get("xenos_authority") is not True:
            raise ValueError("Xenos authority changed")
        if safety.get("suppression_allowed") is not False:
            raise ValueError("suppression was allowed")
    if bindings.get("capture", {}).get("sha256") != post_census.get(
        "capture", {}
    ).get("sha256"):
        raise ValueError("presentation bindings and post census captures differ")

    presentation = bindings.get("presentation")
    binding_items = bindings.get("bindings")
    sinks = post_census.get("presentation_sinks")
    if not isinstance(presentation, dict) or not isinstance(binding_items, list):
        raise ValueError("presentation binding report is incomplete")
    if not isinstance(sinks, list) or len(sinks) != 1:
        raise ValueError("post census must contain one presentation sink")
    sink = sinks[0]
    if (
        sink.get("producer_event") != presentation.get("draw_event")
        or sink.get("present_event") != presentation.get("present_event")
        or sink.get("resource_id") != presentation.get("output_resource_id")
    ):
        raise ValueError("presentation sink identity drifted")
    if len(binding_items) != 1:
        raise ValueError("presentation draw must have one bounded ingress")
    binding = binding_items[0]
    if binding.get("stage") != "ShaderStage.Pixel":
        raise ValueError("presentation ingress is not a pixel binding")
    if binding.get("descriptor_type") != "DescriptorType.Image":
        raise ValueError("presentation ingress is not an image")
    if binding.get("statically_unused") is not False:
        raise ValueError("presentation ingress is statically unused")
    if binding.get("resource_kind") != "texture":
        raise ValueError("presentation ingress is not a texture")
    usages = binding.get("usages")
    if not isinstance(usages, list):
        raise ValueError("presentation ingress has no usage inventory")
    draw_event = presentation.get("draw_event")
    matching_reads = [
        usage
        for usage in usages
        if usage.get("event_id") == draw_event
        and usage.get("usage") == "PS_Resource"
    ]
    if len(matching_reads) != 1:
        raise ValueError("presentation ingress read identity drifted")
    prior_writes = [
        usage
        for usage in usages
        if isinstance(usage.get("event_id"), int)
        and usage["event_id"] < draw_event
        and usage.get("usage") in WRITE_USAGES
    ]

    output = presentation.get("output")
    if not isinstance(output, dict) or output.get("resource_kind") != "texture":
        raise ValueError("presentation output texture is missing")
    width_ratio = ratio(output.get("width"), binding.get("width"))
    height_ratio = ratio(output.get("height"), binding.get("height"))
    uniform_scale = width_ratio == height_ratio
    upscale = uniform_scale and width_ratio["numerator"] > width_ratio["denominator"]
    capture_local_producer = bool(prior_writes)
    return {
        "schema": SCHEMA,
        "capture": bindings.get("capture"),
        "presentation": {
            "draw_event": draw_event,
            "present_event": presentation.get("present_event"),
            "input": {
                key: binding.get(key)
                for key in (
                    "resource_id",
                    "resource_name",
                    "resource_kind",
                    "width",
                    "height",
                    "format",
                    "view_format",
                    "stage",
                    "descriptor_type",
                    "index",
                    "array_element",
                )
            },
            "output": output,
            "width_scale": width_ratio,
            "height_scale": height_ratio,
            "uniform_scale": uniform_scale,
            "upscale": upscale,
        },
        "lineage": {
            "capture_local_producer_observed": capture_local_producer,
            "prior_write_usages": prior_writes,
            "external_or_pre_capture_ingress": not capture_local_producer,
            "guest_post_chain_joined": capture_local_producer,
        },
        "qualification": {
            "presentation_ingress_resolved": True,
            "presentation_upscale_boundary_proven": upscale,
            "upscale_algorithm_proven": False,
            "guest_post_chain_joined": capture_local_producer,
            "effect_semantics_proven": False,
            "ui_composite_boundary_proven": False,
            "native_implementation_ready": False,
        },
        "safety": {
            "metadata_only": True,
            "resource_payload_exported": False,
            "xenos_authority": True,
            "native_coverage": False,
            "suppression_allowed": False,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("bindings", type=pathlib.Path)
    parser.add_argument("post_census", type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        binding_bytes = args.bindings.read_bytes()
        census_bytes = args.post_census.read_bytes()
        result = build_ingress(json.loads(binding_bytes), json.loads(census_bytes))
        result["bindings_sha256"] = hashlib.sha256(binding_bytes).hexdigest().upper()
        result["post_census_sha256"] = hashlib.sha256(census_bytes).hexdigest().upper()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(result["qualification"], sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print("native renderer presentation ingress failed: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
