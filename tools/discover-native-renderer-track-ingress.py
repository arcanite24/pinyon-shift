"""Prove title-owned track presentation and world-resource ingress types."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys


SCHEMA = "pinyon-shift.native-renderer-track-ingress.v1"
IMAGE_BASE = 0x82000000
FUNCTION_RE = re.compile(r"^DEFINE_REX_FUNC\(sub_([0-9A-F]{8})\) \{")


CLASSES = {
    "track_presentation": {
        "decorated_name": ".?AVCTrackPresentation@@",
        "vtable": 0x82239AB4,
        "slots": 135,
        "destructor": 0x82D6AC10,
        "role": "legacy_track_presentation_baseline",
    },
    "track_presentation_unified": {
        "decorated_name": ".?AVCTrackPresentation@Presentation_Unified@@",
        "vtable": 0x82243774,
        "slots": 135,
        "destructor": 0x82DF3C80,
        "role": "active_unified_track_presentation",
    },
    "track_render_model": {
        "decorated_name": ".?AVCTrackRenderModel@@",
        "vtable": 0x82243414,
        "slots": 18,
        "destructor": 0x82DEA670,
        "role": "legacy_track_render_model_baseline",
    },
    "track_render_model_unified": {
        "decorated_name": ".?AVCTrackRenderModel_Unified@Presentation_Unified@@",
        "vtable": 0x82001D74,
        "slots": 18,
        "destructor": 0x82DF1D98,
        "role": "active_unified_track_render_model",
    },
    "track_render_model_instance": {
        "decorated_name": ".?AVCTrackRenderModelInstance@@",
        "vtable": 0x82243464,
        "slots": 15,
        "destructor": 0x82DEA6B8,
        "role": "legacy_track_render_instance_baseline",
    },
    "track_render_model_instance_unified": {
        "decorated_name": ".?AVCTrackRenderModelInstance_Unified@Presentation_Unified@@",
        "vtable": 0x820019CC,
        "slots": 15,
        "destructor": 0x82DEA6B8,
        "role": "active_unified_track_render_instance",
    },
    "track_texture": {
        "decorated_name": ".?AVCTrackTexture@@",
        "vtable": 0x822433D8,
        "slots": 14,
        "destructor": 0x82DEA608,
        "role": "legacy_track_texture_provider_baseline",
    },
    "track_texture_unified": {
        "decorated_name": ".?AVCTrackTexture_Unified@Presentation_Unified@@",
        "vtable": 0x82001708,
        "slots": 14,
        "destructor": 0x82DF13C8,
        "role": "active_unified_track_texture_provider",
    },
    "track_model": {
        "decorated_name": ".?AVCTrackModel@@",
        "vtable": 0x820016B4,
        "slots": 20,
        "destructor": 0x82C26B40,
        "role": "track_model_resource_graph",
    },
    "track_mesh": {
        "decorated_name": ".?AVCTrackMesh@@",
        "vtable": 0x8200143C,
        "slots": 6,
        "destructor": 0x82C25CE8,
        "role": "track_mesh_resource",
    },
    "track_sub_model": {
        "decorated_name": ".?AVCTrackSubModel@@",
        "vtable": 0x82001474,
        "slots": 7,
        "destructor": 0x82C26940,
        "role": "track_submodel_resource",
    },
    "track_procedural_geometry_object": {
        "decorated_name": ".?AVCTrackProceduralGeometryObject@@",
        "vtable": 0x82144CF8,
        "slots": 7,
        "destructor": 0x82C22A78,
        "role": "world_section_procedural_geometry_object",
    },
    "track_procedural_geometry_resource": {
        "decorated_name": ".?AVCTrackProceduralGeometryResource@@",
        "vtable": 0x82144D7C,
        "slots": 23,
        "destructor": 0x82C23190,
        "role": "world_section_procedural_geometry_resource",
    },
    "track_pvs_zone_object": {
        "decorated_name": ".?AVCTrackPVSZoneObject@@",
        "vtable": 0x82144DE0,
        "slots": 7,
        "destructor": 0x82C23668,
        "role": "world_section_visibility_zone_object",
    },
    "track_pvs_zone_resource": {
        "decorated_name": ".?AVCTrackPVSZoneResource@@",
        "vtable": 0x82144E64,
        "slots": 23,
        "destructor": 0x82C23CE0,
        "role": "world_section_visibility_zone_resource",
    },
}

RELATIONSHIPS = (
    ("track_presentation_unified", "track_presentation", "unified_presentation_overrides"),
    ("track_render_model_unified", "track_render_model", "unified_render_model_overrides"),
    ("track_render_model_instance_unified", "track_render_model_instance", "unified_render_instance_overrides"),
    ("track_texture_unified", "track_texture", "unified_track_texture_overrides"),
    ("track_procedural_geometry_resource", "track_pvs_zone_resource", "geometry_vs_visibility_resource_specialization"),
)

KEY_SLOTS = {
    "track_presentation_unified": {
        38: 0x82DF2D40, 52: 0x82DEC6F0, 53: 0x82DEEAE0,
        68: 0x82DF2528, 77: 0x82DF3AC0, 79: 0x8240E7B0,
        97: 0x82DF1A98,
        98: 0x82DF1FD0, 99: 0x82DF2068, 100: 0x82DF2100,
        101: 0x82DF16B8, 102: 0x82DF16F0, 103: 0x82DEE690,
        121: 0x82DEB800, 127: 0x82DEC800, 131: 0x82DE6CE0,
        132: 0x82DF3F00, 133: 0x82DF3CD0,
    },
    "track_render_model_unified": {
        8: 0x82DF2420, 13: 0x82413228, 16: 0x82DF14B8,
    },
    "track_render_model_instance_unified": {
        2: 0x82DEBDF8, 3: 0x82DEBD58, 5: 0x8243BCF8,
        6: 0x82DEB7B0, 8: 0x8243BC80, 9: 0x824416A0,
        10: 0x82463710, 11: 0x824416C8, 12: 0x824416B0,
        13: 0x82DEB7D8, 14: 0x82DEB7F0,
    },
    "track_texture_unified": {
        6: 0x824107C8,
        9: 0x824108D0,
        10: 0x82DF1300,
        11: 0x82DF0B40,
    },
    "track_procedural_geometry_resource": {
        15: 0x82C22E60, 16: 0x82C22EE8, 19: 0x82C22BE0,
        22: 0x82C222C8,
    },
}


def parse_function_addresses(paths: list[pathlib.Path]) -> set[int]:
    functions = set()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = FUNCTION_RE.match(line)
            if match:
                functions.add(int(match.group(1), 16))
    return functions


def image_u32(image: bytes, address: int) -> int:
    offset = address - IMAGE_BASE
    if offset < 0 or offset + 4 > len(image):
        raise ValueError(f"image address is out of range: {address:08X}")
    return int.from_bytes(image[offset : offset + 4], "big")


def image_string(image: bytes, address: int) -> str:
    offset = address - IMAGE_BASE
    if offset < 0 or offset >= len(image):
        raise ValueError(f"image string is out of range: {address:08X}")
    end = image.find(b"\0", offset, min(offset + 160, len(image)))
    if end < 0:
        raise ValueError(f"image string is unterminated: {address:08X}")
    return image[offset:end].decode("ascii")


def build(functions: set[int], image: bytes) -> dict:
    rows = {}
    slot_tables = {}
    for name, spec in CLASSES.items():
        vtable = spec["vtable"]
        locator = image_u32(image, vtable - 4)
        type_descriptor = image_u32(image, locator + 12)
        decorated_name = image_string(image, type_descriptor + 8)
        if decorated_name != spec["decorated_name"]:
            raise ValueError(f"{name} RTTI evidence drifted")
        slots = [image_u32(image, vtable + index * 4) for index in range(spec["slots"])]
        if slots[0] != spec["destructor"]:
            raise ValueError(f"{name} deleting destructor drifted")
        if any(target not in functions for target in slots):
            raise ValueError(f"{name} vtable contains a non-AOT target")
        for index, target in KEY_SLOTS.get(name, {}).items():
            if slots[index] != target:
                raise ValueError(f"{name} key slot {index} drifted")
        slot_tables[name] = slots
        rows[name] = {
            "decorated_name": decorated_name,
            "complete_object_locator": f"{locator:08X}",
            "type_descriptor": f"{type_descriptor:08X}",
            "vtable_address": f"{vtable:08X}",
            "vtable_slot_count": len(slots),
            "deleting_destructor": f"{slots[0]:08X}",
            "role": spec["role"],
        }

    comparisons = []
    for derived, baseline, label in RELATIONSHIPS:
        derived_slots = slot_tables[derived]
        baseline_slots = slot_tables[baseline]
        if len(derived_slots) != len(baseline_slots):
            raise ValueError(f"{label} vtable length mismatch")
        changed = [
            {
                "slot": index,
                "derived_target": f"{target:08X}",
                "baseline_target": f"{baseline_slots[index]:08X}",
            }
            for index, target in enumerate(derived_slots)
            if target != baseline_slots[index]
        ]
        if not changed:
            raise ValueError(f"{label} has no specialized slots")
        comparisons.append({
            "classification": label,
            "derived_class": derived,
            "baseline_class": baseline,
            "changed_slot_count": len(changed),
            "changed_slots": changed,
        })

    return {
        "schema": SCHEMA,
        "status": "complete",
        "classification": "title_track_world_ingress_statically_proved",
        "classes": rows,
        "specialization_comparisons": comparisons,
        "passive_observation_candidates": {
            name: [
                {"slot": index, "target": f"{target:08X}"}
                for index, target in sorted(slots.items())
            ]
            for name, slots in KEY_SLOTS.items()
        },
        "next_runtime_join": {
            "source": "title_track_presentation_model_and_world_resource_lifetimes",
            "destination": "proceduralGeometry_CProceduralModels_prepared_record_identity",
            "proved": False,
            "required_evidence": "exact_shared_object_or_resource_identity_at_both_boundaries",
        },
        "runtime_graph_probe": {
            "source_scope": "8240EC80_8240ECAC",
            "child_bytes": 64,
            "descriptor_bytes": 248,
            "direct_vtable_classes": [
                "track_model",
                "track_mesh",
                "track_sub_model",
                "track_procedural_geometry_object",
                "track_procedural_geometry_resource",
                "track_pvs_zone_object",
                "track_pvs_zone_resource",
            ],
            "cache_capacity": 1024,
            "reference_capacity": 16,
            "identity_join": (
                "exact_address_equality_to_procedural_submission_objects_or_resources"
            ),
            "pointer_validation": "heap_readable_and_host_page_mapped",
            "guest_state_changed": False,
            "native_admission": False,
            "suppression_allowed": False,
        },
        "safety": {
            "static_analysis_only": True,
            "guest_payload_exported": False,
            "runtime_hook_enabled": False,
            "native_admission": False,
            "suppression_allowed": False,
            "xenos_authority_required": True,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("generated_root", type=pathlib.Path)
    parser.add_argument("--image", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        paths = list(args.generated_root.glob("pinyon_shift_recomp.*.cpp"))
        if not paths:
            raise ValueError("no generated AOT C++ files found")
        document = build(parse_function_addresses(paths), args.image.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(f"native renderer track-ingress discovery failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
