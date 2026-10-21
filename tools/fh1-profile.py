"""Decode and edit the plaintext body of a Forza Horizon profile save.

The title encrypts its profile at 0x82C666D0 and decrypts it at 0x82C66594;
with PINYON_SHIFT_M5_SAVE_TRACE=1 both bodies are written to
<state>/logs/save-snapshots (payload-plaintext-*.bin and payload-loaded-*.bin).
The body begins with a self-describing section: a big-endian field count, then
per field [u32 name length][name][u32 0x20][u32 0][u8 type][value], where a
struct (0x0F) holds its own count and fields. What follows the section
(class-serialised states, 0xBB padding) is kept as raw bytes, so encoding a
decoded body gives back the same bytes.

  fh1-profile.py dump BODY                     every field as JSON
  fh1-profile.py get BODY Main/Credits         one value
  fh1-profile.py set BODY Main/Credits 1000000 --output OUT
  fh1-profile.py check BODY                    decode, encode, compare
  fh1-profile.py recover-car --state-root STATE back up the modded save and
                                               reset its selected car on load
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

HEADER_TAG = 0x20
STRUCT = 0x0F
SCALARS = {
    0x00: ("bool", ">B"),
    0x01: ("uint8", ">B"),
    0x03: ("uint32", ">I"),
    0x04: ("uint64", ">Q"),
    0x07: ("int32", ">i"),
    0x09: ("float", ">f"),
}
MAX_DEPTH = 8


@dataclass
class Field:
    name: str
    type: int
    value: object = None  # a number, or a list of Field for a struct
    raw: bytes = b""      # a scalar's bytes as stored (floats round-trip exactly)
    children: list["Field"] = field(default_factory=list)


@dataclass
class Profile:
    fields: list[Field]
    tail: bytes


class ProfileError(ValueError):
    pass


def _u32(body: bytes, offset: int) -> int:
    if offset + 4 > len(body):
        raise ProfileError(f"truncated at {offset}")
    return struct.unpack_from(">I", body, offset)[0]


def _decode_fields(body: bytes, offset: int, count: int, depth: int) -> tuple[list[Field], int]:
    if depth > MAX_DEPTH:
        raise ProfileError("structs nest too deeply")
    fields = []
    for _ in range(count):
        length = _u32(body, offset)
        if not 0 < length <= 256:
            raise ProfileError(f"bad name length {length} at {offset}")
        name = body[offset + 4:offset + 4 + length].decode("ascii")
        offset += 4 + length
        if _u32(body, offset) != HEADER_TAG or _u32(body, offset + 4) != 0:
            raise ProfileError(f"bad field header for {name} at {offset}")
        if offset + 9 > len(body):
            raise ProfileError(f"truncated at {offset}")
        kind = body[offset + 8]
        offset += 9
        if kind == STRUCT:
            children, offset = _decode_fields(body, offset + 4, _u32(body, offset), depth + 1)
            fields.append(Field(name, kind, children=children))
            continue
        if kind not in SCALARS:
            raise ProfileError(f"unknown type 0x{kind:02X} for {name} at {offset}")
        size = struct.calcsize(SCALARS[kind][1])
        raw = body[offset:offset + size]
        if len(raw) != size:
            raise ProfileError(f"truncated value for {name}")
        fields.append(Field(name, kind, struct.unpack(SCALARS[kind][1], raw)[0], raw))
        offset += size
    return fields, offset


def decode(body: bytes) -> Profile:
    fields, end = _decode_fields(body, 4, _u32(body, 0), 0)
    return Profile(fields, body[end:])


def _encode_fields(fields: list[Field]) -> bytes:
    out = bytearray()
    for item in fields:
        name = item.name.encode("ascii")
        out += struct.pack(">I", len(name)) + name + struct.pack(">II", HEADER_TAG, 0)
        out.append(item.type)
        if item.type == STRUCT:
            out += struct.pack(">I", len(item.children)) + _encode_fields(item.children)
        else:
            out += item.raw
    return bytes(out)


def encode(profile: Profile) -> bytes:
    return struct.pack(">I", len(profile.fields)) + _encode_fields(profile.fields) + profile.tail


def find(profile: Profile, path: str) -> Field:
    fields = profile.fields
    parts = path.split("/")
    for index, part in enumerate(parts):
        match = next((item for item in fields if item.name == part), None)
        if match is None:
            raise KeyError(path)
        if index == len(parts) - 1:
            return match
        fields = match.children
    raise KeyError(path)


def set_value(profile: Profile, path: str, text: str) -> Field:
    item = find(profile, path)
    if item.type == STRUCT:
        raise ProfileError(f"{path} is a struct")
    name, fmt = SCALARS[item.type]
    value = float(text) if name == "float" else int(text, 0)
    try:
        item.raw = struct.pack(fmt, value)
    except struct.error as error:
        raise ProfileError(f"{text} does not fit {path} ({name})") from error
    item.value = struct.unpack(fmt, item.raw)[0]
    return item


def _as_json(fields: list[Field]) -> dict:
    return {
        item.name: _as_json(item.children) if item.type == STRUCT else item.value
        for item in fields
    }


def recover_car(state: Path) -> dict:
    """Queue the title's normal missing-car fallback, never edit encrypted saves."""
    import pinyon_common as common
    import pinyon_config as config
    import pinyon_saves as saves

    common.require_game_closed("recovering the selected car")
    path = state / "config" / "pinyon_shift.toml"
    text = config.read_config(path)
    if config.get_value(text, "cheat_set_profile_fields", ""):
        raise ProfileError("cheat_set_profile_fields is already pending; finish or clear it first")
    # A named mod profile takes precedence over user-modded in the host.
    for mod in (config.get_value(text, "enabled_mods", "") or "").split(","):
        manifest = state / "mods" / mod.strip() / "mod.toml"
        if manifest.is_file() and config.get_value(config.read_config(manifest), "profile", ""):
            raise ProfileError("disable mods with a named profile before recovering user-modded")
    xuid = saves.selected_xuid(state)
    if not saves.usable_xuid(xuid):
        raise ProfileError("user_xuid is not a usable profile ID")
    source = common.child_ignoring_case(state / "user-modded", xuid)
    title = common.child_ignoring_case(source, common.TITLE_ID) if source else None
    if title is None or not saves.has_save(title):
        raise ProfileError("no existing selected user-modded profile; nothing changed")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = state / "backups" / f"before-car-recovery-{stamp}-{uuid.uuid4().hex[:6]}"
    staging = backup.with_name(backup.name + ".partial")
    destination = staging / "user-modded" / source.name
    try:
        shutil.copytree(source, destination)
        if path.is_file():
            (staging / "config").mkdir()
            shutil.copy2(path, staging / "config" / path.name)
        manifest = {p.relative_to(staging).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(staging.rglob("*")) if p.is_file()}
        # Verify the backup before publishing the request.
        for original in source.rglob("*"):
            if original.is_file() and original.read_bytes() != (destination / original.relative_to(source)).read_bytes():
                raise ProfileError("the profile changed during backup; close the game and retry")
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        common.rename(staging, backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    text = config.set_value(text, "cheat_set_profile_fields", '"Main/CareerCar=0"')
    config.write_config(path, text)
    return {"backup": str(backup), "profile": str(source),
            "queued": "Main/CareerCar=0", "note": "Start the same title version, let it save, then restart. "
            "The title resets the selection; owned cars, parts and credits stay in the modded profile. "
            "Keep using that profile to continue its progress."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("dump", "check"):
        commands.add_parser(name).add_argument("body", type=Path)
    get = commands.add_parser("get")
    get.add_argument("body", type=Path)
    get.add_argument("path")
    put = commands.add_parser("set")
    put.add_argument("body", type=Path)
    put.add_argument("path")
    put.add_argument("value")
    put.add_argument("--output", type=Path, required=True)
    recover = commands.add_parser("recover-car", help="back up and recover an existing modded profile")
    recover.add_argument("--state-root", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "recover-car":
            print(json.dumps(recover_car(args.state_root.resolve()), indent=2))
            return 0
        body = args.body.read_bytes()
        profile = decode(body)
        if args.command == "dump":
            print(json.dumps({"fields": _as_json(profile.fields), "tail_bytes": len(profile.tail)},
                             indent=2))
        elif args.command == "check":
            if encode(profile) != body:
                print("round trip differs", file=sys.stderr)
                return 1
            print(f"round trip identical ({len(body)} bytes, {len(profile.tail)} kept raw)")
        elif args.command == "get":
            print(find(profile, args.path).value)
        else:
            if args.output.resolve() == args.body.resolve():
                raise ProfileError("--output must differ from the input")
            item = set_value(profile, args.path, args.value)
            encoded = encode(profile)
            assert len(encoded) == len(body)
            args.output.write_bytes(encoded)
            print(f"{args.path} = {item.value}")
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
