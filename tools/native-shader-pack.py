#!/usr/bin/env python3
"""Build and verify deterministic Pinyon Shift native shader packs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import struct
import sys
import tempfile
from dataclasses import dataclass


SCHEMA = "pinyon-shift.native-shader-pack.v1"
MAGIC = b"PNYNSHPK"
VERSION = 1
HEADER = struct.Struct("<8sIIIIQQQ32s")
ENTRY = struct.Struct("<BBHQQQQ32s")
STAGES = {"vertex": 1, "pixel": 2}
STAGE_NAMES = {value: key for key, value in STAGES.items()}
BYTECODE_FORMAT_DXIL = 1
MAX_ENTRY_COUNT = 65_535
MAX_BYTECODE_SIZE = 16 * 1024 * 1024
MAX_PACK_SIZE = 512 * 1024 * 1024
HEX_64 = re.compile(r"^[0-9A-Fa-f]{16}$")
HEX_256 = re.compile(r"^[0-9A-Fa-f]{64}$")


class PackError(ValueError):
    """Raised when a shader manifest or pack violates the format contract."""


@dataclass(frozen=True, order=True)
class ShaderIdentity:
    stage: int
    guest_hash: int
    specialization_mask: int


@dataclass(frozen=True)
class ShaderEntry:
    identity: ShaderIdentity
    bytecode: bytes
    bytecode_sha256: bytes


def _parse_hex64(value: object, field: str) -> int:
    if not isinstance(value, str) or not HEX_64.fullmatch(value):
        raise PackError(f"{field} must contain exactly 16 hexadecimal digits")
    return int(value, 16)


def _parse_sha256(value: object, field: str) -> bytes:
    if not isinstance(value, str) or not HEX_256.fullmatch(value):
        raise PackError(f"{field} must contain exactly 64 hexadecimal digits")
    return bytes.fromhex(value)


def _checked_local_file(root: pathlib.Path, relative: object) -> pathlib.Path:
    if not isinstance(relative, str) or not relative:
        raise PackError("bytecode must be a non-empty relative path")
    candidate = pathlib.Path(relative)
    if candidate.is_absolute():
        raise PackError("bytecode paths must be relative to the manifest")
    try:
        resolved = (root / candidate).resolve(strict=True)
    except OSError as error:
        raise PackError(f"bytecode file is unavailable: {relative}") from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise PackError("bytecode path escapes the manifest directory") from error
    if not resolved.is_file():
        raise PackError(f"bytecode path is not a regular file: {relative}")
    return resolved


def load_manifest(path: pathlib.Path) -> list[ShaderEntry]:
    manifest_path = path.resolve(strict=True)
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PackError(f"unable to read shader manifest: {error}") from error
    if not isinstance(document, dict):
        raise PackError("shader manifest must be a JSON object")
    if document.get("schema") != SCHEMA:
        raise PackError(f"shader manifest schema must be {SCHEMA}")
    if document.get("backend") != "d3d12":
        raise PackError("shader manifest backend must be d3d12")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise PackError("shader manifest entries must be a non-empty array")
    if len(raw_entries) > MAX_ENTRY_COUNT:
        raise PackError(f"shader manifest exceeds {MAX_ENTRY_COUNT} entries")

    root = manifest_path.parent.resolve(strict=True)
    entries: list[ShaderEntry] = []
    identities: set[ShaderIdentity] = set()
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise PackError(f"entries[{index}] must be a JSON object")
        stage_name = raw.get("stage")
        if stage_name not in STAGES:
            raise PackError(f"entries[{index}].stage must be vertex or pixel")
        identity = ShaderIdentity(
            stage=STAGES[stage_name],
            guest_hash=_parse_hex64(raw.get("guest_hash"), f"entries[{index}].guest_hash"),
            specialization_mask=_parse_hex64(
                raw.get("specialization_mask"),
                f"entries[{index}].specialization_mask",
            ),
        )
        if identity in identities:
            raise PackError(f"entries[{index}] duplicates a shader identity")
        identities.add(identity)

        bytecode_path = _checked_local_file(root, raw.get("bytecode"))
        bytecode = bytecode_path.read_bytes()
        if not bytecode:
            raise PackError(f"entries[{index}] bytecode is empty")
        if len(bytecode) > MAX_BYTECODE_SIZE:
            raise PackError(
                f"entries[{index}] bytecode exceeds {MAX_BYTECODE_SIZE} bytes"
            )
        if not bytecode.startswith(b"DXBC"):
            raise PackError(f"entries[{index}] is not a DXIL container")
        actual_digest = hashlib.sha256(bytecode).digest()
        expected_digest = _parse_sha256(
            raw.get("sha256"), f"entries[{index}].sha256"
        )
        if actual_digest != expected_digest:
            raise PackError(f"entries[{index}] bytecode SHA-256 does not match")
        entries.append(ShaderEntry(identity, bytecode, actual_digest))

    return sorted(entries, key=lambda entry: entry.identity)


def serialize(entries: list[ShaderEntry]) -> bytes:
    if not entries or len(entries) > MAX_ENTRY_COUNT:
        raise PackError("shader pack must contain a bounded non-empty entry set")
    index_offset = HEADER.size
    data_offset = index_offset + ENTRY.size * len(entries)
    index = bytearray()
    data = bytearray()
    for shader in entries:
        alignment = (-len(data)) % 16
        data.extend(b"\0" * alignment)
        entry_data_offset = len(data)
        data.extend(shader.bytecode)
        index.extend(
            ENTRY.pack(
                shader.identity.stage,
                BYTECODE_FORMAT_DXIL,
                0,
                shader.identity.guest_hash,
                shader.identity.specialization_mask,
                entry_data_offset,
                len(shader.bytecode),
                shader.bytecode_sha256,
            )
        )
    content = bytes(index + data)
    total_size = HEADER.size + len(content)
    if total_size > MAX_PACK_SIZE:
        raise PackError(f"shader pack exceeds {MAX_PACK_SIZE} bytes")
    return HEADER.pack(
        MAGIC,
        VERSION,
        HEADER.size,
        ENTRY.size,
        len(entries),
        index_offset,
        data_offset,
        len(data),
        hashlib.sha256(content).digest(),
    ) + content


def verify_pack(data: bytes) -> dict[str, object]:
    if len(data) < HEADER.size or len(data) > MAX_PACK_SIZE:
        raise PackError("shader pack size is outside the supported range")
    (
        magic,
        version,
        header_size,
        entry_size,
        entry_count,
        index_offset,
        data_offset,
        data_size,
        content_digest,
    ) = HEADER.unpack_from(data)
    if magic != MAGIC or version != VERSION:
        raise PackError("shader pack magic or version is unsupported")
    if header_size != HEADER.size or entry_size != ENTRY.size:
        raise PackError("shader pack layout size is invalid")
    if not 0 < entry_count <= MAX_ENTRY_COUNT:
        raise PackError("shader pack entry count is invalid")
    expected_data_offset = index_offset + entry_count * entry_size
    if index_offset != header_size or data_offset != expected_data_offset:
        raise PackError("shader pack index offsets are invalid")
    if data_size > MAX_PACK_SIZE or data_offset + data_size != len(data):
        raise PackError("shader pack payload range is invalid")
    if hashlib.sha256(data[index_offset:]).digest() != content_digest:
        raise PackError("shader pack content SHA-256 does not match")

    identities: list[ShaderIdentity] = []
    previous_payload_end = 0
    for index in range(entry_count):
        offset = index_offset + index * entry_size
        (
            stage,
            bytecode_format,
            reserved,
            guest_hash,
            specialization_mask,
            entry_data_offset,
            bytecode_size,
            bytecode_digest,
        ) = ENTRY.unpack_from(data, offset)
        if stage not in STAGE_NAMES or bytecode_format != BYTECODE_FORMAT_DXIL:
            raise PackError(f"shader pack entry {index} has unsupported identity data")
        if (
            reserved != 0
            or not 0 < bytecode_size <= MAX_BYTECODE_SIZE
            or entry_data_offset % 16 != 0
            or entry_data_offset < previous_payload_end
        ):
            raise PackError(f"shader pack entry {index} has invalid bounds")
        bytecode_start = data_offset + entry_data_offset
        bytecode_end = bytecode_start + bytecode_size
        if bytecode_start < data_offset or bytecode_end > len(data):
            raise PackError(f"shader pack entry {index} escapes the payload")
        bytecode = data[bytecode_start:bytecode_end]
        if not bytecode.startswith(b"DXBC"):
            raise PackError(f"shader pack entry {index} is not a DXIL container")
        if hashlib.sha256(bytecode).digest() != bytecode_digest:
            raise PackError(f"shader pack entry {index} SHA-256 does not match")
        padding = data[
            data_offset + previous_payload_end : data_offset + entry_data_offset
        ]
        if any(padding):
            raise PackError(f"shader pack entry {index} has non-zero padding")
        identity = ShaderIdentity(stage, guest_hash, specialization_mask)
        if identities and identity <= identities[-1]:
            raise PackError("shader pack identities are duplicated or not sorted")
        identities.append(identity)
        previous_payload_end = entry_data_offset + bytecode_size

    if previous_payload_end != data_size:
        raise PackError("shader pack payload contains unreferenced trailing data")

    return {
        "schema": SCHEMA,
        "backend": "d3d12",
        "entry_count": entry_count,
        "content_sha256": content_digest.hex().upper(),
        "pack_sha256": hashlib.sha256(data).hexdigest().upper(),
        "size_bytes": len(data),
    }


def _write_atomic(path: pathlib.Path, data: bytes) -> None:
    output = path.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output.parent, prefix=f".{output.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, output)
    finally:
        if temporary_name:
            pathlib.Path(temporary_name).unlink(missing_ok=True)


def _build(arguments: argparse.Namespace) -> dict[str, object]:
    entries = load_manifest(arguments.manifest)
    data = serialize(entries)
    verify = verify_pack(data)
    _write_atomic(arguments.output, data)
    return {"operation": "build", "output": str(arguments.output), **verify}


def _verify(arguments: argparse.Namespace) -> dict[str, object]:
    try:
        data = arguments.pack.read_bytes()
    except OSError as error:
        raise PackError(f"unable to read shader pack: {error}") from error
    return {"operation": "verify", "pack": str(arguments.pack), **verify_pack(data)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify deterministic native D3D12 shader packs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="build a pack from a manifest")
    build_parser.add_argument("manifest", type=pathlib.Path)
    build_parser.add_argument("--output", required=True, type=pathlib.Path)
    build_parser.set_defaults(handler=_build)
    verify_parser = subparsers.add_parser("verify", help="verify a completed pack")
    verify_parser.add_argument("pack", type=pathlib.Path)
    verify_parser.set_defaults(handler=_verify)
    arguments = parser.parse_args(argv)
    try:
        result = arguments.handler(arguments)
    except (PackError, OSError) as error:
        print(f"native-shader-pack: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
