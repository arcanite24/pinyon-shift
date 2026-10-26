#!/usr/bin/env python3
"""Build the archive member overrides of a state's enabled mods (NP-10.1).

The title reads most of its data from zip archives (LZX, method 21) whose
central directories are listed in media/zipmanifest.xml, so a mod that
replaced a whole archive had to ship all of it. A mod may instead ship single
members:

  mods/<name>/members/<archive path>/<member path>
  e.g. mods/my_mod/members/media/StringTables/EN.zip/PauseMenu.str

or add members the archive does not have (new textures, decals, string
tables; #503), stored after the existing ones:

  mods/<name>/add/<archive path>/<member path>
  e.g. mods/my_mod/add/media/ui/Textures.zip/A_Map/MyLogo.xds

A name under members/ or merge/ must exist and one under add/ must not, so a
misspelt replacement fails instead of adding a member nothing reads.

String tables take new and changed strings by IDS_ name, in every part of the
table (the key is a hash of the name; fh1-strings.py string_reference gives
the "_&N" a database row uses), for one language or ALL of them:

  mods/<name>/strings/<language or ALL>/<Table>.toml
  e.g. mods/my_mod/strings/ALL/List_CarMake.toml: IDS_Make_Pinyon = "Pinyon"

or edit single settings by key, so that several mods can change the same
member (NP-10.2):

  mods/<name>/merge/<archive path>/<member path>
  e.g. mods/my_mod/merge/media/physics.zip/PhysicsSettings.ini

The v4 update's own archive members use an explicit, separate tree:

  mods/<name>/merge-update/media.zip/camera/cameraphysics.xml

These merge against <state>/title-update-v4 and build under the generated
mod's update/ overlay, mounted only by the v4 host. They are inactive when
the update is absent. Neither the verified update nor the disc is written.
The update also carries v4's own db/gamedb.slt, which the title reads
instead of game:\\media\\db\\gamedb.slt, so the enabled mods' db/*.sql scripts
(see build-mod-patches.py) are applied to that member of the same overlay.

A merged .ini lists the lines to set (`Section\\Key value`; other keys keep the
player's values, unknown keys are added). A merged .xml mirrors the member's
structure with only the elements to change: an element matches the member's
element of the same tag with the same id, name, model, key or type
attribute (or, without one, at the same position among its tag), its
attributes and text replace the member's, and unmatched elements are added;
`pinyon-remove="true"` removes the matched element. Merges apply on top of
the winning replacement (or the player's member, decompressed with
--archive-extractor for LZX members), the earliest mod last so that it wins.

This tool rewrites each affected archive from the player's own copy: every
other member keeps its compressed bytes and headers, replaced members are
stored uncompressed (method 0), and the archive's line in zipmanifest.xml
gets the new central directory. The results form the asset-only mod
<state>/mods/zz-archive-patches, listed first in enabled_mods; an earlier mod
in the load order wins a member two mods replace. Nothing from the disc is
distributed: the archives are built on the player's machine. With no member
overrides enabled the generated mod is removed. launch-preview.ps1 runs it
before each start.

  build-mod-archives.py <state-root> [--game-root DIR] [--archive-extractor EXE]
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import zlib
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
GENERATED = "zz-archive-patches"
MANIFEST = Path("media") / "zipmanifest.xml"
# Where the v4 title update keeps the game database (archive, member).
UPDATE_DATABASE = ("media.zip", "db\\gamedb.slt")

LOCAL = struct.Struct("<IHHHHHIIIHH")
CENTRAL = struct.Struct("<IHHHHHHIIIHHHHHII")
END = struct.Struct("<IHHHHIIH")
LOCAL_SIGNATURE = 0x04034B50
CENTRAL_SIGNATURE = 0x02014B50
END_SIGNATURE = 0x06054B50
DATA_OFFSET_EXTRA = 0x1123
# Offset of the local header offset inside a central directory record.
CENTRAL_OFFSET_FIELD = 42


class ArchiveError(ValueError):
    pass


def _patches_module():
    spec = importlib.util.spec_from_file_location(
        "build_mod_patches", Path(__file__).with_name("build-mod-patches.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _strings_module():
    spec = importlib.util.spec_from_file_location(
        "fh1_strings", Path(__file__).with_name("fh1-strings.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


def read_central(data: bytes) -> tuple[list[tuple[bytes, dict]], int]:
    """The central directory records (raw bytes, fields) and its offset."""
    at = data.rfind(struct.pack("<I", END_SIGNATURE))
    if at < 0 or at + END.size > len(data):
        raise ArchiveError("no end of central directory")
    _, _, _, _, count, size, offset, _ = END.unpack_from(data, at)
    records = []
    cursor = offset
    for _ in range(count):
        if cursor + CENTRAL.size > len(data):
            raise ArchiveError("central directory is truncated")
        fields = CENTRAL.unpack_from(data, cursor)
        if fields[0] != CENTRAL_SIGNATURE:
            raise ArchiveError(f"bad central record at {cursor}")
        name_size, extra_size, comment_size = fields[10], fields[11], fields[12]
        length = CENTRAL.size + name_size + extra_size + comment_size
        raw = data[cursor:cursor + length]
        name = raw[CENTRAL.size:CENTRAL.size + name_size].decode("cp437")
        records.append((raw, {"name": name, "method": fields[4], "crc": fields[7],
                              "compressed": fields[8], "size": fields[9],
                              "offset": fields[16]}))
        cursor += length
    if cursor - offset != size:
        raise ArchiveError("central directory size mismatch")
    return records, offset


def _set_data_offset(record: bytearray, offset: int) -> None:
    """The title's archives carry an extra field (id 0x1123, 4 bytes) in each
    central record holding the absolute offset of the member's data, which
    the title reads instead of walking the local header."""
    fields = CENTRAL.unpack_from(record)
    at = CENTRAL.size + fields[10]
    end = at + fields[11]
    while at + 4 <= end:
        key, size = struct.unpack_from("<HH", record, at)
        if key == DATA_OFFSET_EXTRA and size == 4:
            struct.pack_into("<I", record, at + 4, offset)
            return
        at += 4 + size


def rebuild(data: bytes, replacements: dict[str, bytes],
            additions: dict[str, bytes] | None = None) -> tuple[bytes, int, int, int]:
    """The archive with `replacements` (lower-case member name with
    backslashes -> bytes) stored uncompressed, and `additions` (new member
    name as stored, with forward slashes -> bytes) stored after the existing
    members; returns (archive, dirstart, dirsize, direntries).
    As in the title's zipmanifest.xml, dirsize covers the central directory
    and the end record after it."""
    records, _ = read_central(data)
    out = bytearray()
    central = bytearray()
    for raw, info in records:
        header = LOCAL.unpack_from(data, info["offset"])
        if header[0] != LOCAL_SIGNATURE:
            raise ArchiveError(f"bad local header for {info['name']}")
        body_at = info["offset"] + LOCAL.size + header[9] + header[10]
        new_offset = len(out)
        record = bytearray(raw)
        replacement = replacements.get(info["name"].replace("/", "\\").lower())
        if replacement is None:
            out += data[info["offset"]:body_at + info["compressed"]]
        else:
            crc = zlib.crc32(replacement) & 0xFFFFFFFF
            fields = list(header)
            fields[2] &= ~0x0008  # no data descriptor
            fields[3] = 0  # stored
            fields[6], fields[7], fields[8] = crc, len(replacement), len(replacement)
            out += LOCAL.pack(*fields)
            out += data[info["offset"] + LOCAL.size:body_at]
            out += replacement
            central_fields = list(CENTRAL.unpack_from(record))
            central_fields[3] &= ~0x0008
            central_fields[4] = 0
            central_fields[7], central_fields[8], central_fields[9] = (
                crc, len(replacement), len(replacement))
            record[:CENTRAL.size] = CENTRAL.pack(*central_fields)
        struct.pack_into("<I", record, CENTRAL_OFFSET_FIELD, new_offset)
        _set_data_offset(record, new_offset + (body_at - info["offset"]))
        central += record
    # New members are appended: the title's archives are not all sorted
    # (ui/Textures.zip, gamemodes.zip), so it does not search them by order.
    # Their headers copy the first member's version and time, as the title's
    # writer made them, with the data-offset extra field.
    count = len(records)
    if additions:
        first = CENTRAL.unpack_from(records[0][0]) if records else None
        version, time, date = (first[2], first[5], first[6]) if first else (10, 0, 0x21)
        for name, body in additions.items():
            encoded = name.encode("cp437")
            crc = zlib.crc32(body) & 0xFFFFFFFF
            offset = len(out)
            out += LOCAL.pack(LOCAL_SIGNATURE, version, 0, 0, time, date, crc, len(body), len(body),
                              len(encoded), 0)
            out += encoded + body
            extra = struct.pack("<HHI", DATA_OFFSET_EXTRA, 4, offset + LOCAL.size + len(encoded))
            central += CENTRAL.pack(CENTRAL_SIGNATURE, version, version, 0, 0, time, date, crc,
                                    len(body), len(body), len(encoded), len(extra), 0, 0, 0, 0,
                                    offset)
            central += encoded + extra
            count += 1
    dirstart = len(out)
    out += central
    out += END.pack(END_SIGNATURE, 0, 0, count, count, len(central), dirstart, 0)
    return bytes(out), dirstart, len(central) + END.size, count


def _manifest_line(text: str, archive: str) -> re.Match:
    guest = "game:\\" + archive.replace("/", "\\")
    pattern = re.compile(r'(<Zip\b[^>]*\bpath="' + re.escape(guest) + r'"[^>]*/>)', re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        raise ArchiveError(f"{guest} is not in zipmanifest.xml")
    return match


def check_supported(data: bytes, text: str, archive: str) -> None:
    """Only archives whose end record agrees with their manifest line are
    rebuilt. The largest track archive has more than 65,535 entries and an end
    record with truncated counts; the title reads its manifest line instead."""
    line = _manifest_line(text, archive).group(1)
    values = {key: int(re.search(rf'\b{key}="(\d+)"', line).group(1))
              for key in ("dirstart", "dirsize", "direntries")}
    at = data.rfind(struct.pack("<I", END_SIGNATURE))
    if at < 0:
        raise ArchiveError(f"{archive} has no end of central directory")
    _, disk, _, _, count, size, offset, _ = END.unpack_from(data, at)
    if (disk, offset, size + END.size, count) != (
            0, values["dirstart"], values["dirsize"], values["direntries"]):
        raise ArchiveError(f"{archive} is not a plain zip archive; replace it whole instead")


def update_manifest(text: str, archive: str, dirstart: int, dirsize: int, direntries: int) -> str:
    match = _manifest_line(text, archive)
    guest = "game:\\" + archive.replace("/", "\\")
    line = match.group(1)
    for key, value in (("dirstart", dirstart), ("dirsize", dirsize), ("direntries", direntries)):
        line, count = re.subn(rf'\b{key}="\d+"', f'{key}="{value}"', line)
        if count != 1:
            raise ArchiveError(f"{guest} has no {key} in zipmanifest.xml")
    return text[:match.start()] + line + text[match.end():]


def collect(state: Path, mods: list[str]) -> dict[str, dict[str, tuple[str, Path]]]:
    """archive (lower case, as named under members/) -> member -> (mod, file);
    the earliest mod in the load order wins."""
    archives: dict[str, dict[str, tuple[str, Path]]] = {}
    for mod in mods:
        root = state / "mods" / mod / "members"
        if not root.is_dir():
            continue
        for file in sorted(p for p in root.rglob("*") if p.is_file()):
            parts = file.relative_to(root).parts
            split = next((i for i, part in enumerate(parts) if part.lower().endswith(".zip")), None)
            if split is None or split == len(parts) - 1:
                continue
            archive = "/".join(parts[:split + 1]).lower()
            member = "\\".join(parts[split + 1:]).lower()
            archives.setdefault(archive, {}).setdefault(member, (mod, file))
    return archives


def collect_additions(state: Path, mods: list[str]) -> dict[str, dict[str, tuple[str, str, Path]]]:
    """archive -> lower-case member -> (mod, member name as stored, file)
    from add/ folders; the earliest mod wins, as for replacements."""
    archives: dict[str, dict[str, tuple[str, str, Path]]] = {}
    for mod in mods:
        root = state / "mods" / mod / "add"
        if not root.is_dir():
            continue
        for file in sorted(p for p in root.rglob("*") if p.is_file()):
            parts = file.relative_to(root).parts
            split = next((i for i, part in enumerate(parts) if part.lower().endswith(".zip")), None)
            if split is None or split == len(parts) - 1:
                continue
            archive = "/".join(parts[:split + 1]).lower()
            stored = "/".join(parts[split + 1:])
            member = stored.replace("/", "\\").lower()
            archives.setdefault(archive, {}).setdefault(member, (mod, stored, file))
    return archives


STRING_TABLES = "media/stringtables"


def collect_strings(state: Path, mods: list[str],
                    game_root: Path) -> dict[str, dict[str, list[tuple[str, dict[str, str]]]]]:
    """archive -> lower-case table member -> [(mod, {IDS_ name: text})] in
    load order, from mods/<mod>/strings/<language or ALL>/<Table>.toml."""
    tables_dir = find_case_insensitive(game_root, STRING_TABLES)
    languages = sorted(p.stem for p in tables_dir.iterdir()
                       if p.suffix.lower() == ".zip") if tables_dir else []
    archives: dict[str, dict[str, list[tuple[str, dict[str, str]]]]] = {}
    for mod in mods:
        root = state / "mods" / mod / "strings"
        if not root.is_dir():
            continue
        for file in sorted(root.glob("*/*.toml")):
            language = file.parent.name
            targets = languages if language.upper() == "ALL" else [
                next((name for name in languages if name.lower() == language.lower()), None)]
            if targets == [None]:
                raise ArchiveError(f"{mod}: no string tables for language {language}")
            with file.open("rb") as handle:
                strings = tomllib.load(handle)
            if not all(isinstance(text, str) for text in strings.values()):
                raise ArchiveError(f"{file}: every value must be a string")
            for target in targets:
                archive = f"{STRING_TABLES}/{target}.zip".lower()
                member = (file.stem + ".str").lower()
                archives.setdefault(archive, {}).setdefault(member, []).append((mod, strings))
    return archives


def collect_merges(state: Path, mods: list[str], tree: str = "merge") -> dict[str, dict[str, list[tuple[str, Path]]]]:
    """archive -> member -> [(mod, merge file)] in load order."""
    archives: dict[str, dict[str, list[tuple[str, Path]]]] = {}
    for mod in mods:
        root = state / "mods" / mod / tree
        if not root.is_dir():
            continue
        for file in sorted(p for p in root.rglob("*") if p.is_file()):
            parts = file.relative_to(root).parts
            split = next((i for i, part in enumerate(parts) if part.lower().endswith(".zip")), None)
            if split is None or split == len(parts) - 1:
                continue
            archive = "/".join(parts[:split + 1]).lower()
            member = "\\".join(parts[split + 1:]).lower()
            archives.setdefault(archive, {}).setdefault(member, []).append((mod, file))
    return archives


def _ini_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith((";", "//", "#")):
        return None
    return re.split(r"[\s=]", stripped, maxsplit=1)[0].lower()


def merge_ini(base: bytes, patch: bytes) -> bytes:
    """`patch`'s keys set on `base` (`Section\\Key value` or `Key = value`
    lines), keeping the base's line order, separators and line endings."""
    newline = "\r\n" if b"\r\n" in base else "\n"
    lines = base.decode("utf-8").splitlines()
    index = {key: i for i, line in enumerate(lines) if (key := _ini_key(line)) is not None}
    for line in patch.decode("utf-8-sig").splitlines():
        key = _ini_key(line)
        if key is None:
            continue
        value = re.split(r"[\s=]+", line.strip(), maxsplit=1)
        value = value[1].strip() if len(value) > 1 else ""
        if key in index:
            old = lines[index[key]]
            match = re.match(r"(\s*\S+?)(\s*=\s*|\s+)", old)
            separator = match.group(2) if match else " "
            name = match.group(1) if match else old.strip()
            lines[index[key]] = name + separator + value
        else:
            index[key] = len(lines)
            lines.append(line.strip())
    return (newline.join(lines) + newline).encode("utf-8")


KEY_ATTRIBUTES = ("id", "name", "model", "key", "type")
REMOVE_ATTRIBUTE = "pinyon-remove"
# Appends the element instead of matching one, for lists of unkeyed
# elements such as CameraPhysics.xml's layers.
ADD_ATTRIBUTE = "pinyon-add"


def _key(element: ElementTree.Element) -> tuple[str, str] | None:
    lowered = {name.lower(): value for name, value in element.attrib.items()}
    for attribute in KEY_ATTRIBUTES:
        if attribute in lowered:
            return attribute, lowered[attribute]
    return None


def _merge_element(base: ElementTree.Element, patch: ElementTree.Element) -> None:
    for name, value in patch.attrib.items():
        base.set(name, value)
    if patch.text and patch.text.strip() and not len(patch):
        base.text = patch.text
    positions: dict[str, int] = {}
    for child in patch:
        if not isinstance(child.tag, str):
            continue  # comments in the patch
        if child.get(ADD_ATTRIBUTE, "").lower() == "true":
            del child.attrib[ADD_ATTRIBUTE]
            base.append(child)
            continue
        key = _key(child)
        candidates = [c for c in base if c.tag == child.tag]
        if key is not None:
            match = next((c for c in candidates if _key(c) == key), None)
        else:
            position = positions.get(child.tag, 0)
            positions[child.tag] = position + 1
            match = candidates[position] if position < len(candidates) else None
        if child.get(REMOVE_ATTRIBUTE, "").lower() == "true":
            if match is not None:
                base.remove(match)
            continue
        if match is None:
            base.append(child)
        else:
            _merge_element(match, child)


def merge_xml(base: bytes, patch: bytes) -> bytes:
    """`patch`'s elements merged into `base` by tag and key attribute."""
    newline = "\r\n" if b"\r\n" in base else "\n"
    parser = lambda: ElementTree.XMLParser(target=ElementTree.TreeBuilder(insert_comments=True))
    root = ElementTree.fromstring(base, parser=parser())
    patch_root = ElementTree.fromstring(patch, parser=parser())
    if patch_root.tag != root.tag:
        raise ArchiveError(f"merge root <{patch_root.tag}> does not match <{root.tag}>")
    _merge_element(root, patch_root)
    text = ElementTree.tostring(root, encoding="unicode")
    declaration = re.match(rb"<\?xml[^>]*\?>", base.lstrip(b"\xef\xbb\xbf"))
    if declaration:
        text = declaration.group(0).decode("utf-8") + "\n" + text
    return (text.replace("\n", newline) + newline).encode("utf-8")


def merge_member(member: str, base: bytes, patch: bytes) -> bytes:
    if member.endswith(".ini"):
        return merge_ini(base, patch)
    if member.endswith(".xml"):
        return merge_xml(base, patch)
    raise ArchiveError(f"{member}: only .ini and .xml members can be merged")


def read_member(archive: Path, data: bytes, member: str, extractor: Path | None) -> bytes:
    """The player's member, decompressed."""
    records, _ = read_central(data)
    info = next(i for _, i in records if i["name"].replace("/", "\\").lower() == member)
    header = LOCAL.unpack_from(data, info["offset"])
    body = info["offset"] + LOCAL.size + header[9] + header[10]
    compressed = data[body:body + info["compressed"]]
    if info["method"] == 0:
        return compressed
    if info["method"] == 8:
        return zlib.decompress(compressed, -15)
    if info["method"] != 21:
        raise ArchiveError(f"{member}: unknown compression {info['method']}")
    if extractor is None or not extractor.is_file():
        raise ArchiveError(f"{member} is LZX-compressed: pass --archive-extractor "
                           "(pinyon_shift_fh1_archive_extract)")
    with tempfile.TemporaryDirectory(prefix="pinyon-merge-") as temporary:
        output = Path(temporary) / "member.bin"
        completed = subprocess.run(
            [str(extractor), str(archive), str(body), str(info["compressed"]), str(info["size"]),
             str(output)], capture_output=True, text=True)
        if completed.returncode:
            raise ArchiveError(f"{member}: extraction failed: {completed.stderr.strip()}")
        return output.read_bytes()


def find_case_insensitive(root: Path, relative: str) -> Path | None:
    current = root
    for part in relative.split("/"):
        if not current.is_dir():
            return None
        match = next((c for c in current.iterdir() if c.name.lower() == part.lower()), None)
        if match is None:
            return None
        current = match
    return current


def build_update_merges(state: Path, mods: list[str], staging: Path,
                        extractor: Path | None) -> list[dict]:
    """Explicit update: members, separate from game: and the disc manifest.

    v4 reads its database from update:\\media.zip, which the game: database
    that build-mod-patches.py writes cannot shadow, so the enabled mods'
    db/*.sql scripts are applied again to the update's own copy (#895).
    No installed v4 update means these optional patches are inactive. Never
    replace or write the verified title update itself.
    """
    update = state / "title-update-v4"
    if not update.is_dir():
        return []
    patches = _patches_module()
    scripts = patches.database_scripts(state, mods)
    merges = collect_merges(state, mods, "merge-update")
    if scripts:
        merges.setdefault(UPDATE_DATABASE[0], {})
    results = []
    for archive, members in sorted(merges.items()):
        base = find_case_insensitive(update, archive)
        if base is None or not base.is_file():
            raise ArchiveError(f"update:/{archive} is not in the installed title update")
        # As with game: merges, keep the winning whole-archive replacement.
        for mod in reversed(mods):
            replacement = find_case_insensitive(state / "mods" / mod / "update", archive)
            if replacement is not None and replacement.is_file():
                base = replacement
        data = base.read_bytes()
        names = {info["name"].replace("/", "\\").lower()
                 for _, info in read_central(data)[0]}
        missing = sorted(set(members) - names)
        if missing:
            raise ArchiveError(f"update:/{archive} has no member {missing[0]}")
        replacements = {}
        for member, edits in sorted(members.items()):
            body = read_member(base, data, member, extractor)
            for _, patch in reversed(edits):
                body = merge_member(member, body, patch.read_bytes())
            replacements[member] = body
        applied = []
        if scripts and archive == UPDATE_DATABASE[0]:
            if UPDATE_DATABASE[1] not in names:
                raise ArchiveError(f"update:/{archive} has no member {UPDATE_DATABASE[1]}")
            with tempfile.TemporaryDirectory(prefix="pinyon-db-") as temporary:
                database = Path(temporary) / "gamedb.slt"
                database.write_bytes(read_member(base, data, UPDATE_DATABASE[1], extractor))
                applied = patches.apply_scripts(state, database, scripts)
                replacements[UPDATE_DATABASE[1]] = database.read_bytes()
        rebuilt, _, _, _ = rebuild(data, replacements)
        output = staging / "update" / archive
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rebuilt)
        result = {"update_archive": archive,
                  "merged": {m: [mod for mod, _ in edits]
                             for m, edits in sorted(members.items())},
                  "base_sha256": hashlib.sha256(data).hexdigest().upper(),
                  "sha256": hashlib.sha256(rebuilt).hexdigest().upper()}
        if applied:
            result["database_scripts"] = applied
        results.append(result)
    return results


def build(state: Path, game_root: Path, extractor: Path | None = None) -> dict:
    patches = _patches_module()
    config = state / "config" / "pinyon_shift.toml"
    mods = [m for m in patches.enabled_mods(config) if m != GENERATED]
    archives = collect(state, mods)
    merges = collect_merges(state, mods)
    additions = collect_additions(state, mods)
    string_edits = collect_strings(state, mods, game_root)
    for archive in list(merges) + list(additions) + list(string_edits):
        archives.setdefault(archive, {})
    target = state / "mods" / GENERATED
    update_merges = (state / "title-update-v4").is_dir() and (
        collect_merges(state, mods, "merge-update") or patches.database_scripts(state, mods))
    if not archives and not update_merges:
        if target.exists():
            patches.remove_written_directory(target)
        patches.set_enabled_mods(config, mods)
        return {"patched": False, "mods": mods}
    # A mod that replaces whole archives or the manifest (a total conversion
    # such as the XE mod) is the base its members are patched on.
    manifest = (patches.effective_game_file(state, mods, game_root, MANIFEST.as_posix())
                .read_bytes().decode("utf-8-sig")) if archives else ""
    staging = state / "mods" / (GENERATED + ".building")
    if staging.exists():
        patches.remove_written_directory(staging)
    results = []
    for archive, members in sorted(archives.items()):
        disc = find_case_insensitive(game_root, archive)
        replaced = patches.effective_game_file(state, mods, game_root, archive)
        base = replaced if replaced.is_file() else disc
        if base is None:
            raise ArchiveError(f"{archive} is not in the game files")
        # Named as on the disc where it exists there, as the manifest names it.
        relative = disc.relative_to(game_root) if disc is not None else Path(archive)
        data = base.read_bytes()
        check_supported(data, manifest, relative.as_posix())
        names ={info["name"].replace("/", "\\").lower() for _, info in read_central(data)[0]}
        archive_merges = merges.get(archive, {})
        archive_strings = string_edits.get(archive, {})
        missing = sorted((set(members) | set(archive_merges) | set(archive_strings)) - names)
        if missing:
            raise ArchiveError(f"{archive} has no member {missing[0]}: put new members under "
                               "add/ instead of members/ or merge/")
        archive_additions = additions.get(archive, {})
        present = sorted(set(archive_additions) & names)
        if present:
            raise ArchiveError(f"{archive} already has {present[0]}: put replacements under "
                               "members/ instead of add/")
        replacements = {member: file.read_bytes() for member, (_, file) in members.items()}
        for member, edits in sorted(archive_merges.items()):
            merged = replacements.get(member)
            if merged is None:
                merged = read_member(base, data, member, extractor)
            for _, file in reversed(edits):
                merged = merge_member(member, merged, file.read_bytes())
            replacements[member] = merged
        # New and changed strings (#503) on top of the winning table.
        strings_module = _strings_module() if archive_strings else None
        for member, edits in sorted(archive_strings.items()):
            table = replacements.get(member)
            if table is None:
                table = read_member(base, data, member, extractor)
            for mod, strings in reversed(edits):
                try:
                    table = strings_module.add_strings(table, strings)
                except strings_module.StringTableError as error:
                    raise ArchiveError(f"{mod}: {archive}/{member}: {error}") from error
            replacements[member] = table
        rebuilt, dirstart, dirsize, direntries = rebuild(
            data, replacements,
            {stored: file.read_bytes() for _, stored, file in archive_additions.values()})
        output = staging / "game" / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rebuilt)
        manifest = update_manifest(manifest, relative.as_posix(), dirstart, dirsize, direntries)
        results.append({"archive": relative.as_posix(),
                        "members": {m: mod for m, (mod, _) in sorted(members.items())},
                        "merged": {m: [mod for mod, _ in edits]
                                   for m, edits in sorted(archive_merges.items())},
                        "strings": {m: [mod for mod, _ in edits]
                                    for m, edits in sorted(archive_strings.items())},
                        "added": {stored: mod
                                  for mod, stored, _ in sorted(archive_additions.values(),
                                                               key=lambda item: item[1])},
                        "base_sha256": hashlib.sha256(data).hexdigest().upper(),
                        "sha256": hashlib.sha256(rebuilt).hexdigest().upper()})
    results.extend(build_update_merges(state, mods, staging, extractor))
    if archives:
        (staging / "game" / MANIFEST).parent.mkdir(parents=True, exist_ok=True)
        (staging / "game" / MANIFEST).write_bytes(b"\xef\xbb\xbf" + manifest.encode("utf-8"))
    # Built only from mods that keep the player's save, it keeps it too.
    shares = all(patches.shares_save(state, mod) for mod in mods)
    (staging / "mod.toml").write_text(
        "# Generated by tools/build-mod-archives.py; rebuilt when mods change.\n"
        f'name = "{GENERATED}"\nversion = "1"\nabi = 1\n'
        + ("shares_save = true\n" if shares else ""), encoding="utf-8", newline="\n")
    (staging / "archives.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    patches.replace_written_directory(staging, target)
    patches.set_enabled_mods(config, [GENERATED] + mods)
    return {"patched": True, "archives": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("state_root", type=Path)
    parser.add_argument("--game-root", type=Path, default=ROOT / ".local" / "game" / "base")
    parser.add_argument("--archive-extractor", type=Path,
                        help="pinyon_shift_fh1_archive_extract, for merging LZX members")
    args = parser.parse_args()
    try:
        result = build(args.state_root.resolve(), args.game_root.resolve(),
                       args.archive_extractor.resolve() if args.archive_extractor else None)
    except (ArchiveError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
