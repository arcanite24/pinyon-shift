"""Build a payload-free spatial catalog of title-authored world instances."""

import argparse
import hashlib
import json
import math
import pathlib
import sys
import xml.etree.ElementTree as ET


SCHEMA = "pinyon-shift.native-renderer-static-world-instance-catalog.v1"
MAX_INSTANCES_PER_SOURCE = 100_000
AXES = ("XAxis", "YAxis", "ZAxis")


def fnv1a64(value):
    result = 0xCBF29CE484222325
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{result:016X}"


def source_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def vector(element, label):
    if element is None:
        raise ValueError(f"instance is missing {label}")
    try:
        values = [float(element.attrib[axis]) for axis in ("x", "y", "z")]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"instance has an invalid {label}") from error
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"instance has a non-finite {label}")
    return values


def identity_fields(element, category):
    if category == "collision_prop":
        fields = ("PhysicsType", "GraphicsName")
    else:
        fields = ("GameplayID",)
    values = []
    for field in fields:
        value = element.attrib.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{category} instance is missing {field}")
        values.append(value)
    return fields, values


def read_instances(path, expected_root, category):
    instances = []
    root = None
    try:
        for event, element in ET.iterparse(path, events=("start", "end")):
            if root is None and event == "start":
                root = element
                if root.tag != expected_root:
                    raise ValueError(
                        f"expected {expected_root} root, found {root.tag}"
                    )
            if event != "end" or element is root:
                continue
            if not element.tag.startswith("Obj"):
                continue
            if len(instances) >= MAX_INSTANCES_PER_SOURCE:
                raise ValueError(f"{category} instance capacity exceeded")
            fields, values = identity_fields(element, category)
            position = vector(element.find("Pos"), "position")
            orientation = element.find("Orientation")
            if orientation is None:
                raise ValueError("instance is missing orientation")
            axes = [vector(orientation.find(axis), axis) for axis in AXES]
            joined_identity = "\0".join(values)
            instances.append(
                {
                    "category": category,
                    "source_ordinal": len(instances),
                    "identity_hash": fnv1a64(joined_identity),
                    "identity_field_hashes": {
                        field: fnv1a64(value)
                        for field, value in zip(fields, values)
                    },
                    "position": position,
                    "orientation": axes,
                }
            )
            element.clear()
    except ET.ParseError as error:
        raise ValueError(f"invalid {category} XML") from error
    if root is None:
        raise ValueError(f"empty {category} XML")
    return instances


def build(collision_path, gameplay_path):
    collision_path = pathlib.Path(collision_path)
    gameplay_path = pathlib.Path(gameplay_path)
    collision = read_instances(collision_path, "CollObjs", "collision_prop")
    gameplay = read_instances(gameplay_path, "GameObjs", "gameplay_object")
    instances = collision + gameplay
    return {
        "schema": SCHEMA,
        "status": "complete",
        "sources": [
            {
                "kind": "collision_prop",
                "sha256": source_sha256(collision_path),
                "instance_count": len(collision),
            },
            {
                "kind": "gameplay_object",
                "sha256": source_sha256(gameplay_path),
                "instance_count": len(gameplay),
            },
        ],
        "instance_count": len(instances),
        "instances": instances,
        "qualification": {
            "title_authored_spatial_classes_cataloged": bool(instances),
            "runtime_transform_join_proved": False,
            "building_or_prop_instance_identity_proved": False,
        },
        "safety": {
            "source_files_changed": False,
            "plaintext_identity_exported": False,
            "game_asset_payload_exported": False,
            "numeric_spatial_metadata_only": True,
            "guest_state_changed": False,
            "native_admission": False,
            "native_draw": False,
            "suppression_allowed": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collision", required=True, type=pathlib.Path)
    parser.add_argument("--gameplay", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    arguments = parser.parse_args()
    try:
        document = build(arguments.collision, arguments.gameplay)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
