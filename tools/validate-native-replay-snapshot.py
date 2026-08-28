#!/usr/bin/env python3
"""Validate one local NR-02 replay snapshot against its offline contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FNV_OFFSET = 0xCBF29CE484222325
FNV_PRIME = 0x100000001B3


def fnv1a64(payload: bytes) -> str:
    value = FNV_OFFSET
    for byte in payload:
        value ^= byte
        value = (value * FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016X}"


def load_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return document


def require_safety(document: dict[str, Any], name: str) -> None:
    safety = document.get("safety")
    if not isinstance(safety, dict):
        raise ValueError(f"{name} is missing its safety record")
    if safety.get("native_upload") is not False:
        raise ValueError(f"{name} does not keep native upload disabled")
    if safety.get("native_draw") is not False:
        raise ValueError(f"{name} does not keep native drawing disabled")
    if safety.get("suppression_allowed") is not False:
        raise ValueError(f"{name} does not keep suppression disabled")
    if safety.get("xenos_authority") is not True:
        raise ValueError(f"{name} does not preserve Xenos authority")


def payload_path(root: Path, file_name: object) -> Path:
    if not isinstance(file_name, str) or not file_name:
        raise ValueError("snapshot payload has no file name")
    relative = Path(file_name)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != file_name:
        raise ValueError(f"unsafe snapshot payload path: {file_name!r}")
    return root / relative


def validate_payload(root: Path, entry: dict[str, Any], prefix: str) -> None:
    stem = f"{prefix}_" if prefix else ""
    path = payload_path(root, entry[f"{stem}file"])
    payload = path.read_bytes()
    expected_size = entry[f"{stem}bytes"]
    expected_hash = entry[f"{stem}hash"]
    if len(payload) != expected_size:
        raise ValueError(f"{path.name} size does not match the manifest")
    if fnv1a64(payload) != expected_hash:
        raise ValueError(f"{path.name} hash does not match the manifest")


def validate_snapshot(
    root: Path,
    geometry: dict[str, Any],
    draw_state: dict[str, Any],
    texture: dict[str, Any],
    pso: dict[str, Any],
) -> dict[str, Any]:
    snapshot = load_json(root / "snapshot.json")
    if snapshot.get("schema") != "pinyon-shift.native-replay-snapshot.v1":
        raise ValueError("unsupported replay snapshot schema")

    signature = snapshot.get("candidate_signature")
    if not isinstance(signature, str) or len(signature) != 16:
        raise ValueError("snapshot candidate signature is invalid")
    for name, document in (
        ("geometry", geometry),
        ("draw state", draw_state),
        ("texture provenance", texture),
        ("PSO", pso),
    ):
        if document.get("candidate_signature") != signature:
            raise ValueError(f"{name} contract signature does not match the snapshot")
        require_safety(document, name)
    require_safety(snapshot, "snapshot")

    if geometry.get("bounds", {}).get("validated") is not True:
        raise ValueError("geometry contract is not bounded")
    if texture.get("qualification", {}).get("content_stable_across_captures") is not True:
        raise ValueError("texture content is not stable across captures")
    if pso.get("support", {}).get("ready_for_pso_creation") is not True:
        raise ValueError("PSO contract is not ready for isolated creation")

    snapshot_shaders = snapshot.get("shaders", {})
    pso_key = pso.get("pso_key", {})
    shader_pairs = (
        ("vertex", "vertex_shader"),
        ("pixel", "pixel_shader"),
        ("vertex_specialization", "vertex_specialization_mask"),
        ("pixel_specialization", "pixel_specialization_mask"),
    )
    for snapshot_name, pso_name in shader_pairs:
        if snapshot_shaders.get(snapshot_name) != pso_key.get(pso_name):
            raise ValueError(f"snapshot {snapshot_name} does not match the PSO contract")
    if snapshot.get("prepared_pipeline_hash") != pso_key.get("prepared_pipeline_hash"):
        raise ValueError("prepared pipeline hash does not match the PSO contract")

    snapshot_geometry = snapshot.get("geometry", {})
    index_entry = snapshot_geometry.get("index", {})
    vertex_entry = snapshot_geometry.get("vertex", {})
    validate_payload(root, index_entry, "")
    validate_payload(root, vertex_entry, "")
    geometry_index = geometry.get("index", {})
    if index_entry.get("format") != geometry_index.get("format"):
        raise ValueError("snapshot index format does not match the geometry contract")
    if index_entry.get("endianness") != geometry_index.get("endianness"):
        raise ValueError("snapshot index endianness does not match the geometry contract")
    if index_entry.get("count") != geometry.get("index_count", {}).get("maximum_observed"):
        raise ValueError("snapshot index count does not match the geometry contract")
    if vertex_entry.get("bytes") != geometry.get("binding", {}).get("size_bytes"):
        raise ValueError("snapshot vertex allocation does not match the geometry contract")
    if vertex_entry.get("stride_words") * 4 != geometry.get("binding", {}).get("stride_bytes"):
        raise ValueError("snapshot vertex stride does not match the geometry contract")

    provenance = {
        resource["fetch_constant"]: resource
        for resource in texture.get("resources", [])
    }
    snapshot_textures = snapshot.get("textures")
    if not isinstance(snapshot_textures, list) or len(snapshot_textures) != len(provenance):
        raise ValueError("snapshot texture count does not match provenance")
    for resource in snapshot_textures:
        fetch = resource.get("fetch_constant")
        expected = provenance.get(fetch)
        if expected is None:
            raise ValueError(f"snapshot texture fetch {fetch!r} has no provenance")
        validate_payload(root, resource, "base")
        if resource.get("base_bytes") != expected.get("base_bytes"):
            raise ValueError(f"texture fetch {fetch} base size is unstable")
        if resource.get("base_hash") != expected.get("base_hash"):
            raise ValueError(f"texture fetch {fetch} base hash is unstable")
        if resource.get("mip_bytes") != expected.get("mip_bytes"):
            raise ValueError(f"texture fetch {fetch} mip size is unstable")
        if resource.get("mip_bytes"):
            validate_payload(root, resource, "mip")
            if resource.get("mip_hash") != expected.get("mip_hash"):
                raise ValueError(f"texture fetch {fetch} mip hash is unstable")
        elif resource.get("mip_file") is not None or resource.get("mip_hash") is not None:
            raise ValueError(f"texture fetch {fetch} has inconsistent empty mip metadata")

    state_fetches = {
        item.get("fetch_constant")
        for item in snapshot.get("constants", {}).get("texture_states", [])
    }
    if state_fetches != set(provenance):
        raise ValueError("snapshot texture instructions do not cover the payload set")

    return {
        "schema": "pinyon-shift.native-replay-snapshot-validation.v1",
        "candidate_signature": signature,
        "frame": snapshot.get("frame"),
        "draw": snapshot.get("draw"),
        "index_bytes": index_entry.get("bytes"),
        "vertex_bytes": vertex_entry.get("bytes"),
        "texture_resources": len(snapshot_textures),
        "texture_bytes": sum(resource["base_bytes"] + resource["mip_bytes"] for resource in snapshot_textures),
        "ready_for_isolated_upload": True,
        "native_draw": False,
        "suppression_allowed": False,
        "xenos_authority": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a local exact-signature NR-02 replay snapshot."
    )
    parser.add_argument("snapshot_dir", type=Path)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("draw_state", type=Path)
    parser.add_argument("texture", type=Path)
    parser.add_argument("pso", type=Path)
    parser.add_argument("--output", "-o", type=Path)
    args = parser.parse_args()

    result = validate_snapshot(
        args.snapshot_dir,
        load_json(args.geometry),
        load_json(args.draw_state),
        load_json(args.texture),
        load_json(args.pso),
    )
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
