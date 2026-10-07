#!/usr/bin/env python3
"""Re-encode one authored UI4 scene member for the UI-14 stream route.

The pause screen is built from ``GAME:\\Media\\UI\\Scenes\\UI4\\
925_PAUSE_MENU.bgf``.  The title's item deserializer (``sub_82F26560``) walks
one length-prefixed item section whose loop count is
``*(section+16) + *(section+20)`` and whose byte length is an equality check
against the 4-byte declaration in front of the items.  The item count is not a
stream value: the two words are copied out of the member's fixed header at
offsets ``0x24``/``0x28`` (element and wrapper item counts), so an extra item
needs the declaration, the two header words and the item bytes to change
together.  Feeding a longer member at the loader boundary therefore requires
this bounded re-encoder, not an in-place payload patch.

The tool parses the section strictly (a parse that does not consume exactly the
declared length is rejected, never guessed at), rebuilds the section from the
parsed item slices, and only then duplicates one row.  A no-change run must
reproduce its input byte for byte; ``--check-roundtrip`` asserts that before any
modification is written.

Two record counts besides the item count are read out of the same header: the
total property-entry count at ``0x2C`` (mirrored at ``0x78``) sizes the document
arena as ``(elements * 4 + properties) * 8 + wrappers * 68``, so an insert that
does not raise it writes past the arena.  ``--clone subtree`` (the default)
carries the row's whole contiguous record subtree, its owned identities, and
its companion records;
``--clone pair`` copies only the wrapper and element records and is kept as the
diagnostic comparison that shares the source row's objects.

This edits BGF only. Its native-object IDs also reference the companion FBF;
BGF-only subtree remapping does not create those objects and is unqualified
for gameplay. ``fh1-ui-fbf.py --clone-row`` coordinates experimental BGF/FBF/BSG
copies with separate ID domains. Check output against FBF with ``--bgf`` before
interpreting BGF structural checks as native graph validation.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Iterable

MARKER = b"AnarkBGF"
MARKER_OFFSET = 6
HEADER_RECORD_LENGTH = 0x1A
# sub_82F260C8 reads this packed header word as the native object-ID ceiling.
# sub_82F248F0 allocates both binding tables for ceiling + 1 entries.
NATIVE_OBJECT_CEILING_OFFSET = 0x1B
ITEM_HEADER_BYTES = 14
WRAPPER_EXTRA_BYTES = 5
PROPERTY_STRIDE = 8
MAXIMUM_ITEMS = 8192
MAXIMUM_PROPERTIES = 512
# Header words the deserializer copies into the section at +16/+20.  The file
# stores the pair twice; both copies are kept consistent.
ELEMENT_COUNT_OFFSET = 0x24
WRAPPER_COUNT_OFFSET = 0x28
# Word 0x2C is the section's total property-entry count.  The title sizes the
# document arena from the three counts as (elements * 4 + properties) * 8 +
# wrappers * 68, so an inserted record must raise the property count too or the
# arena is written past its end.
PROPERTY_COUNT_OFFSET = 0x2C
ELEMENT_COUNT_REPEAT_OFFSET = 0x70
WRAPPER_COUNT_REPEAT_OFFSET = 0x74
PROPERTY_COUNT_REPEAT_OFFSET = 0x78
RELATION_COUNT_OFFSET = 0x30
RELATION_CHILD_COUNT_OFFSET = 0x34
IDENTITY_COUNT_OFFSET = 0x3C
RELATION_COUNT_REPEAT_OFFSET = 0x7C
RELATION_CHILD_COUNT_REPEAT_OFFSET = 0x80
IDENTITY_SECTION_OFFSET = 0x88
STYLE_COUNT_OFFSET = 0x44
STYLE_CHILD_COUNT_OFFSET = 0x48
TRACK_COUNT_OFFSET = 0x4C
TRACK_CHILD_COUNT_OFFSET = 0x50
TRACK_KEY_COUNT_OFFSET = 0x54
ANIMATION_COUNT_OFFSET = 0x5C
ANIMATION_TRACK_COUNT_OFFSET = 0x60
ANIMATION_KEY_COUNT_OFFSET = 0x64
ANIMATION_EVENT_COUNT_OFFSET = 0x68
ANIMATION_AUX_COUNT_OFFSET = 0x6C
# Contract hash of the seven pause rows' element records (PAUSE_MENU_BUTTON).
PAUSE_ROW_CONTRACT = 0xBDF05338
# Wrapper name hashes of the seven authored pause rows.
PAUSE_ROW_NAMES = (
    0x22352942,
    0x22362981,
    0x223729C0,
    0x223829FF,
    0x22392A3E,
    0x223A2A7D,
    0x223B2ABC,
)
INSERTED_ROW_NAME = 0x223C2AFB


class SceneInsertError(ValueError):
    """The member does not match the verified pause-item stream format."""


def u32be(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise SceneInsertError(f"word at {offset:#x} is outside the member")
    return struct.unpack_from(">I", data, offset)[0]


def put_u32be(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into(">I", data, offset, value & 0xFFFFFFFF)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclasses.dataclass(frozen=True)
class Item:
    start: int
    end: int
    name: int
    parent: int
    value: int
    kind: int
    flags: int
    properties: tuple[tuple[int, int], ...]

    @property
    def wrapper(self) -> bool:
        return bool(self.flags & 0x04)

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclasses.dataclass(frozen=True)
class Section:
    start: int
    declared: int
    items: tuple[Item, ...]

    @property
    def end(self) -> int:
        return self.start + 4 + self.declared

    @property
    def elements(self) -> int:
        return sum(1 for item in self.items if not item.wrapper)

    @property
    def wrappers(self) -> int:
        return sum(1 for item in self.items if item.wrapper)

    @property
    def properties(self) -> int:
        return sum(len(item.properties) for item in self.items)


@dataclasses.dataclass(frozen=True)
class Relation:
    parent: int
    children: tuple[int, ...]


@dataclasses.dataclass(frozen=True)
class IdentitySection:
    declared: int
    records: tuple[tuple[int, int], ...]

    @property
    def end(self) -> int:
        return IDENTITY_SECTION_OFFSET + 4 + self.declared


def parse_identity_section(data: bytes) -> IdentitySection:
    """Parse the length-prefixed identity strings before the item section."""
    declared = u32be(data, IDENTITY_SECTION_OFFSET)
    end = IDENTITY_SECTION_OFFSET + 4 + declared
    if end > len(data):
        raise SceneInsertError("identity section extends past the member")
    cursor = IDENTITY_SECTION_OFFSET + 4
    records = []
    for _ in range(u32be(data, IDENTITY_COUNT_OFFSET)):
        size = u32be(data, cursor)
        record_end = cursor + 4 + size
        if record_end > end:
            raise SceneInsertError("identity string extends past its section")
        records.append((cursor, record_end))
        cursor = record_end
    if cursor != end:
        raise SceneInsertError("identity strings do not consume their declaration")
    return IdentitySection(declared, tuple(records))


def parse_relations(data: bytes, start: int) -> tuple[int, tuple[Relation, ...], int]:
    """Parse the item-parent table that immediately follows the item section."""
    declared = u32be(data, start)
    end = start + 4 + declared
    if end > len(data):
        raise SceneInsertError("relationship section extends past the member")
    cursor = start + 4
    relations = []
    for _ in range(u32be(data, RELATION_COUNT_OFFSET)):
        parent = u32be(data, cursor)
        count = u32be(data, cursor + 4)
        cursor += 8
        children = tuple(u32be(data, cursor + index * 4) for index in range(count))
        cursor += count * 4
        if cursor > end:
            raise SceneInsertError("relationship record extends past its section")
        relations.append(Relation(parent, children))
    if cursor != end:
        raise SceneInsertError("relationship records do not consume their declaration")
    return declared, tuple(relations), end


def encode_relations(relations: Iterable[Relation]) -> bytes:
    body = bytearray()
    for relation in relations:
        body += struct.pack(">II", relation.parent, len(relation.children))
        for child in relation.children:
            body += struct.pack(">I", child)
    return struct.pack(">I", len(body)) + body


def clone_companion_sections(data: bytes, start: int,
                             item_map: dict[int, int],
                             shifted_items: dict[int, int] | None = None,
                             identity_map: dict[int, int] | None = None) -> tuple[bytes, dict]:
    """Clone row companions and relocate later items' existing references.

    Inserting before the scene's trailing items moves their indexes too; their
    existing style/track/animation records must still address those same items.
    Clone from the original records so source and shifted domains stay distinct.
    """
    cursor = start
    shifted_items = shifted_items or {}
    identity_map = identity_map or {}

    def remap_string_keys(record: bytearray, offsets: list[int]) -> None:
        # sub_82F26D90 and sub_82F284A8 resolve only type 20 key values
        # through the identity table. Float/integer payloads are literals.
        for offset in offsets:
            tag = u32be(record, offset)
            value = u32be(record, offset + 4)
            # The loader unpacks the tag before masking type bits 2..4.
            # Serialized bit 30 is an independent flag (A... and E... both
            # carry string values); test bits 31, 29 and 28 only.
            if (tag & 0xB0000000) == 0xA0000000 and value in identity_map:
                put_u32be(record, offset + 4, identity_map[value])

    style_start = cursor
    style_declared = u32be(data, cursor)
    cursor += 4
    styles: list[bytes] = []
    cloned_styles: list[bytes] = []
    style_map: dict[int, int] = {}
    style_children = 0
    for _ in range(u32be(data, STYLE_COUNT_OFFSET)):
        record_start = cursor
        child_count = struct.unpack_from(">H", data, cursor + 10)[0]
        cursor += 12 + child_count * 24
        record = data[record_start:cursor]
        owner = u32be(record, 0)
        relocated = bytearray(record)
        if owner in shifted_items:
            put_u32be(relocated, 0, shifted_items[owner])
        styles.append(bytes(relocated))
        if owner in item_map:
            style_map[len(styles) - 1] = u32be(data, STYLE_COUNT_OFFSET) + len(cloned_styles)
            copy = bytearray(record)
            put_u32be(copy, 0, item_map[owner])
            cloned_styles.append(bytes(copy))
            style_children += child_count
    if cursor != style_start + 4 + style_declared:
        raise SceneInsertError("style records do not consume their declaration")

    track_start = cursor
    track_declared = u32be(data, cursor)
    cursor += 4
    tracks: list[bytes] = []
    cloned_tracks: list[bytes] = []
    track_children = track_keys = 0
    source_track_keys = 0
    track_key_map: dict[int, int] = {}
    for _ in range(u32be(data, TRACK_COUNT_OFFSET)):
        record_start = cursor
        owner, child_count = struct.unpack_from(">II", data, cursor)
        cursor += 8
        reference_offsets = []
        string_key_offsets = []
        keys = 0
        for _ in range(child_count):
            key_count = u32be(data, cursor + 4)
            cursor += 8
            keys += key_count
            for _ in range(key_count):
                reference_offsets.extend((cursor - record_start,
                                          cursor - record_start + 4))
                string_key_offsets.append(cursor - record_start + 12)
                cursor += 20
        record = data[record_start:cursor]
        relocated = bytearray(record)
        for offset in (0, *reference_offsets):
            value = u32be(relocated, offset)
            if value in shifted_items:
                put_u32be(relocated, offset, shifted_items[value])
        tracks.append(bytes(relocated))
        if owner in item_map:
            for index in range(keys):
                track_key_map[source_track_keys + index] = track_keys + index
            copy = bytearray(record)
            put_u32be(copy, 0, item_map[owner])
            for offset in reference_offsets:
                value = u32be(copy, offset)
                if value in item_map:
                    put_u32be(copy, offset, item_map[value])
            remap_string_keys(copy, string_key_offsets)
            cloned_tracks.append(bytes(copy))
            track_children += child_count
            track_keys += keys
        source_track_keys += keys
    if cursor != track_start + 4 + track_declared:
        raise SceneInsertError("track records do not consume their declaration")
    track_key_map = {old: source_track_keys + copied
                     for old, copied in track_key_map.items()}

    empty_declared = u32be(data, cursor)
    empty_section = data[cursor:cursor + 4 + empty_declared]
    cursor += len(empty_section)
    if empty_declared:
        raise SceneInsertError("unsupported non-empty companion table")

    animation_start = cursor
    animation_declared = u32be(data, cursor)
    cursor += 4
    animations: list[bytes] = []
    cloned_animations: list[bytes] = []
    animation_tracks = animation_keys = animation_events = animation_aux = 0
    for _ in range(u32be(data, ANIMATION_COUNT_OFFSET)):
        record_start = cursor
        cursor += 16
        owner = u32be(data, cursor)
        owner_offset = cursor - record_start
        cursor += 13
        track_count = u32be(data, cursor)
        cursor += 4
        keys = events = aux = 0
        track_owner_offsets = []
        string_key_offsets = []
        event_offsets = []
        for _ in range(track_count):
            track_owner_offsets.append(cursor - record_start)
            cursor += 5
            key_count = u32be(data, cursor)
            cursor += 4
            keys += key_count
            string_key_offsets.extend(cursor - record_start + index * 8
                                      for index in range(key_count))
            cursor += key_count * 8
            event_count = u32be(data, cursor)
            cursor += 4
            events += event_count
            aux += event_count & 1
            event_offsets.extend(cursor - record_start + index * 4
                                 for index in range(event_count))
            cursor += event_count * 4
        record = data[record_start:cursor]
        relocated = bytearray(record)
        for offset in (owner_offset, *track_owner_offsets):
            value = u32be(relocated, offset)
            if value in shifted_items:
                put_u32be(relocated, offset, shifted_items[value])
        animations.append(bytes(relocated))
        if owner in item_map:
            copy = bytearray(record)
            put_u32be(copy, owner_offset, item_map[owner])
            for offset in track_owner_offsets:
                value = u32be(copy, offset)
                if value in item_map:
                    put_u32be(copy, offset, item_map[value])
            remap_string_keys(copy, string_key_offsets)
            # 82F284A8 reads each entry as {byte, byte, uint16}; 82F2A380
            # packs the first byte's inverse into bit 14. Zero selects a
            # style-record index; nonzero selects a property-track key index.
            # Leaving these indexes unchanged animates the original row.
            for offset in event_offsets:
                index = struct.unpack_from(">H", copy, offset + 2)[0]
                mapping = track_key_map if copy[offset] else style_map
                if index in mapping:
                    target = mapping[index]
                    if target >= 0x4000:
                        raise SceneInsertError("cloned animation reference exceeds its 14-bit index")
                    struct.pack_into(">H", copy, offset + 2, target)
            cloned_animations.append(bytes(copy))
            animation_tracks += track_count
            animation_keys += keys
            animation_events += events
            animation_aux += aux
    if cursor != animation_start + 4 + animation_declared or cursor != len(data):
        raise SceneInsertError("animation records do not consume the member")

    def section(records: list[bytes]) -> bytes:
        body = b"".join(records)
        return struct.pack(">I", len(body)) + body

    tail = (
        section(styles + cloned_styles)
        + section(tracks + cloned_tracks)
        + empty_section
        + section(animations + cloned_animations)
    )
    return tail, {
        "styles": len(cloned_styles),
        "style_children": style_children,
        "tracks": len(cloned_tracks),
        "track_children": track_children,
        "track_keys": track_keys,
        "animations": len(cloned_animations),
        "animation_tracks": animation_tracks,
        "animation_keys": animation_keys,
        "animation_events": animation_events,
        "animation_aux": animation_aux,
    }


def parse_item(data: bytes, start: int) -> Item:
    """Parse one item record; reject anything the deserializer cannot walk."""
    limit = len(data)
    if start + ITEM_HEADER_BYTES > limit:
        raise SceneInsertError(f"item at {start:#x} runs past the member")
    name = u32be(data, start)
    parent = u32be(data, start + 4)
    value = u32be(data, start + 8)
    kind = data[start + 12]
    flags = data[start + 13]
    cursor = start + ITEM_HEADER_BYTES
    if flags & 0x04:
        cursor += WRAPPER_EXTRA_BYTES
    if cursor + 4 > limit:
        raise SceneInsertError(f"item at {start:#x} truncates before its count")
    count = u32be(data, cursor)
    cursor += 4
    if count > MAXIMUM_PROPERTIES:
        raise SceneInsertError(
            f"item at {start:#x} declares {count} properties, beyond "
            f"{MAXIMUM_PROPERTIES}"
        )
    end = cursor + count * PROPERTY_STRIDE
    if end > limit:
        raise SceneInsertError(f"item at {start:#x} runs past the member")
    properties = tuple(
        (u32be(data, cursor + index * PROPERTY_STRIDE),
         u32be(data, cursor + index * PROPERTY_STRIDE + 4))
        for index in range(count)
    )
    return Item(start, end, name, parent, value, kind, flags, properties)


def parse_section(data: bytes, start: int) -> Section:
    """Parse one item section; the items must consume the declared length."""
    if start < 0 or start + 4 > len(data):
        raise SceneInsertError(f"section at {start:#x} is outside the member")
    declared = u32be(data, start)
    end = start + 4 + declared
    if declared == 0 or end > len(data):
        raise SceneInsertError(
            f"section at {start:#x} declares {declared} bytes past the member"
        )
    items: list[Item] = []
    cursor = start + 4
    while cursor < end:
        if len(items) >= MAXIMUM_ITEMS:
            raise SceneInsertError(
                f"section at {start:#x} exceeds {MAXIMUM_ITEMS} items"
            )
        item = parse_item(data, cursor)
        if item.end > end:
            raise SceneInsertError(
                f"item at {cursor:#x} overruns the declared section length"
            )
        items.append(item)
        cursor = item.end
    if cursor != end:
        raise SceneInsertError(f"section at {start:#x} does not end cleanly")
    return Section(start, declared, tuple(items))


def find_pause_section(data: bytes) -> Section:
    """Locate the unique item section that carries the seven pause rows."""
    if data[:4] != b"\x01\x04\x00\x00" or data[MARKER_OFFSET:MARKER_OFFSET + 8] != MARKER:
        raise SceneInsertError("member does not start with the AnarkBGF header")
    if u32be(data, 2) != HEADER_RECORD_LENGTH:
        raise SceneInsertError("member header record length is not 0x1A")
    candidates: list[Section] = []
    errors: list[str] = []
    for start in range(0x20, len(data) - 4):
        try:
            section = parse_section(data, start)
        except SceneInsertError as error:
            errors.append(str(error))
            continue
        names = {item.name for item in section.items if item.wrapper}
        if set(PAUSE_ROW_NAMES) <= names:
            candidates.append(section)
    if len(candidates) != 1:
        raise SceneInsertError(
            f"expected exactly one item section with the seven pause rows, "
            f"found {len(candidates)}"
        )
    section = candidates[0]
    rows = [item for item in section.items if item.name in PAUSE_ROW_NAMES]
    for item in rows:
        position = section.items.index(item)
        following = section.items[position + 1]
        if following.wrapper or following.parent != position:
            raise SceneInsertError(
                f"row wrapper {item.name:#010x} is not followed by its element"
            )
    return section


def pause_row_pairs(section: Section) -> list[tuple[int, Item, Item]]:
    """Return (row index, wrapper, element) for the seven authored rows."""
    pairs: list[tuple[int, Item, Item]] = []
    for index, item in enumerate(section.items):
        if not item.wrapper or item.name not in PAUSE_ROW_NAMES:
            continue
        element = section.items[index + 1]
        if element.parent != index:
            raise SceneInsertError(
                f"row {item.name:#010x} element parent is {element.parent:#x}, "
                f"expected {index:#x}"
            )
        if element.name != PAUSE_ROW_CONTRACT:
            raise SceneInsertError(
                f"row {item.name:#010x} next record is {element.name:#010x}, "
                "not the pause button contract"
            )
        pairs.append((PAUSE_ROW_NAMES.index(item.name), item, element))
    if len(pairs) != len(PAUSE_ROW_NAMES):
        raise SceneInsertError(
            f"found {len(pairs)} pause row pairs, expected {len(PAUSE_ROW_NAMES)}"
        )
    return pairs


# Each pause row owns 72 consecutive property identity indexes. The copied row
# also needs fresh item-value identities; reusing either set leaves scaler
# bindings pointed at the source row or at raw identity values.
ROW_OBJECT_STRIDE = 72
ROW_OBJECT_BASE = 20


def row_subtree(section: Section, wrapper: Item) -> tuple[int, int]:
    """Return the contiguous item-index range of one row's authored subtree."""
    wrapper_index = section.items.index(wrapper)
    children: dict[int, list[int]] = {}
    for index, item in enumerate(section.items):
        children.setdefault(item.parent, []).append(index)
    seen = {wrapper_index}
    pending = [wrapper_index]
    while pending:
        node = pending.pop()
        for child in children.get(node, ()):
            if child not in seen:
                seen.add(child)
                pending.append(child)
    first, last = min(seen), max(seen)
    if seen != set(range(first, last + 1)):
        raise SceneInsertError(
            f"row {wrapper.name:#010x} subtree is not contiguous"
        )
    return first, last


def encode_subtree(data: bytes, row_index: int,
                   native_object_map: dict[int, int] | None = None) -> tuple[bytes, dict]:
    """Clone one authored row with its relationship records.

    The row-owned graph receives fresh item and property identities. Action
    identities stay shared while animation records receive remapped item owners.
    """
    section = find_pause_section(data)
    pairs = pause_row_pairs(section)
    if not 0 <= row_index < len(pairs):
        raise SceneInsertError(
            f"row index {row_index} is outside the seven authored rows"
        )
    if section.declared != sum(item.size for item in section.items):
        raise SceneInsertError("section length is not the sum of its items")
    roundtrip = rebuild(section, data, section.items, section.declared)
    if roundtrip != data:
        raise SceneInsertError("no-change roundtrip does not reproduce the input")

    counts = check_section_counts(data, section)

    _, wrapper, _ = pairs[row_index]
    first, last = row_subtree(section, wrapper)
    block = section.items[first:last + 1]
    block_objects = [
        value
        for item in block
        for _, value in item.properties
        if ROW_OBJECT_BASE <= value < ROW_OBJECT_BASE + ROW_OBJECT_STRIDE * len(PAUSE_ROW_NAMES)
    ]
    if not block_objects:
        raise SceneInsertError("row carries no object-slot references")
    low, high = min(block_objects), max(block_objects)
    if len(block_objects) != len(set(block_objects)):
        raise SceneInsertError("row object-slot references are not unique")
    if high - low + 1 != ROW_OBJECT_STRIDE:
        raise SceneInsertError("row does not cover one complete object block")
    identities = parse_identity_section(data)
    if identities.end != section.start:
        raise SceneInsertError("identity section is not adjacent to the items")
    relation_declared, relations, relation_end = parse_relations(data, section.end)
    relation_children = sum(len(relation.children) for relation in relations)
    source_relations = [
        relation for relation in relations if first <= relation.parent <= last
    ]
    if not source_relations:
        raise SceneInsertError("row subtree carries no relationship records")
    source_relation_children = tuple(
        child for relation in source_relations for child in relation.children
    )
    if any(child >= len(identities.records) for child in source_relation_children):
        raise SceneInsertError("row relationship references an absent identity")
    action_identities = tuple(dict.fromkeys(source_relation_children))
    if action_identities and action_identities != tuple(
        range(action_identities[0], action_identities[-1] + 1)
    ):
        raise SceneInsertError("row relationship identities are not contiguous")
    # Native object IDs and BGF string indexes are separate domains. Preserve
    # the old BGF-only experiment as a comparison, but a coordinated clone
    # copies only the row's authored string slots into the string table.
    owned_identity_set = set(block_objects)
    if native_object_map is None:
        owned_identity_set |= {item.value for item in block if item.value != 0}
    owned_identities = tuple(sorted(owned_identity_set))
    if any(index >= len(identities.records) for index in owned_identities):
        raise SceneInsertError("row references an absent identity")
    new_low = len(identities.records)
    identity_map = {
        source: new_low + offset
        for offset, source in enumerate(owned_identities)
    }
    identity_records = []
    for index in owned_identities:
        start, end = identities.records[index]
        identity_records.append(data[start:end])
    identity_copy = b"".join(identity_records)
    insertion_index = max(
        row_subtree(section, row_wrapper)[1]
        for _, row_wrapper, _ in pairs
    ) + 1
    block_length = len(block)
    copied = bytearray()
    for item in block:
        record = bytearray(data[item.start:item.end])
        if item is block[0]:
            put_u32be(record, 0, INSERTED_ROW_NAME)
        parent = item.parent
        if first <= parent <= last:
            put_u32be(record, 4, parent - first + insertion_index)
        value_map = identity_map if native_object_map is None else native_object_map
        if item.kind in (1, 4, 5, 6, 7) and item.value in value_map:
            put_u32be(record, 8, value_map[item.value])
        property_cursor = (
            ITEM_HEADER_BYTES
            + (WRAPPER_EXTRA_BYTES if item.flags & 0x04 else 0)
            + 4
        )
        for index, (_, value) in enumerate(item.properties):
            if value in identity_map and (native_object_map is None or low <= value <= high):
                put_u32be(
                    record,
                    property_cursor + index * PROPERTY_STRIDE + 4,
                    identity_map[value],
                )
        copied += record

    declared = section.declared + len(copied)
    existing = []
    for item in section.items:
        record = bytearray(data[item.start:item.end])
        if insertion_index <= item.parent < len(section.items):
            put_u32be(record, 4, item.parent + block_length)
        existing.append(bytes(record))
    body = b"".join(existing[:insertion_index]) + bytes(copied) + b"".join(
        existing[insertion_index:]
    )
    if len(body) != declared:
        raise SceneInsertError("patched item body does not match its declaration")
    shifted_relations = tuple(
        Relation(
            relation.parent + block_length
            if relation.parent >= insertion_index
            else relation.parent,
            relation.children,
        )
        for relation in relations
    )
    cloned_relations = []
    for relation in source_relations:
        cloned_relations.append(
            Relation(
                relation.parent - first + insertion_index,
                relation.children,
            )
        )
    relation_bytes = encode_relations((*shifted_relations, *cloned_relations))
    relation_child_delta = sum(len(relation.children) for relation in cloned_relations)
    companion_bytes, companion = clone_companion_sections(
        data,
        relation_end,
        {
            source: source - first + insertion_index
            for source in range(first, last + 1)
        },
        {source: source + block_length
         for source in range(insertion_index, len(section.items))},
        identity_map,
    )
    patched = bytearray(
        data[:identities.end]
        + identity_copy
        + struct.pack(">I", declared)
        + body
        + relation_bytes
        + companion_bytes
    )
    if native_object_map:
        put_u32be(patched, NATIVE_OBJECT_CEILING_OFFSET,
                  max(u32be(data, NATIVE_OBJECT_CEILING_OFFSET),
                      max(native_object_map.values())))
    bump_section_counts(
        patched,
        data,
        sum(1 for item in block if not item.wrapper),
        sum(1 for item in block if item.wrapper),
        sum(len(item.properties) for item in block),
    )
    for offset in (RELATION_COUNT_OFFSET, RELATION_COUNT_REPEAT_OFFSET):
        put_u32be(patched, offset, len(relations) + len(cloned_relations))
    for offset in (
        RELATION_CHILD_COUNT_OFFSET,
        RELATION_CHILD_COUNT_REPEAT_OFFSET,
    ):
        put_u32be(patched, offset, relation_children + relation_child_delta)
    put_u32be(
        patched,
        IDENTITY_SECTION_OFFSET,
        identities.declared + len(identity_copy),
    )
    put_u32be(
        patched,
        IDENTITY_COUNT_OFFSET,
        len(identities.records) + len(owned_identities),
    )
    for offset, key in (
        (STYLE_COUNT_OFFSET, "styles"),
        (STYLE_CHILD_COUNT_OFFSET, "style_children"),
        (TRACK_COUNT_OFFSET, "tracks"),
        (TRACK_CHILD_COUNT_OFFSET, "track_children"),
        (TRACK_KEY_COUNT_OFFSET, "track_keys"),
        (ANIMATION_COUNT_OFFSET, "animations"),
        (ANIMATION_TRACK_COUNT_OFFSET, "animation_tracks"),
        (ANIMATION_KEY_COUNT_OFFSET, "animation_keys"),
        (ANIMATION_EVENT_COUNT_OFFSET, "animation_events"),
        (ANIMATION_AUX_COUNT_OFFSET, "animation_aux"),
    ):
        put_u32be(patched, offset, u32be(data, offset) + companion[key])
    summary = {
        "input_bytes": len(data),
        "output_bytes": len(patched),
        "input_sha256": sha256(data),
        "output_sha256": sha256(bytes(patched)),
        "section_offset": section.start + len(identity_copy),
        "section_declared_before": section.declared,
        "section_declared_after": declared,
        "items_before": len(section.items),
        "items_after": len(section.items) + len(block),
        "elements_before": counts[0],
        "wrappers_before": counts[1],
        "elements_after": counts[0] + sum(1 for item in block if not item.wrapper),
        "wrappers_after": counts[1] + sum(1 for item in block if item.wrapper),
        "insert_offset": section.items[insertion_index].start + len(identity_copy),
        "insert_bytes": len(identity_copy) + len(copied) + len(relation_bytes) - 4 - relation_declared,
        "identity_insert_bytes": len(identity_copy),
        "identities_before": len(identities.records),
        "identities_after": len(identities.records) + len(owned_identities),
        "item_insert_bytes": len(copied),
        "relation_insert_bytes": len(relation_bytes) - 4 - relation_declared,
        "relations_before": len(relations),
        "relations_after": len(relations) + len(cloned_relations),
        "relation_children_before": relation_children,
        "relation_children_after": relation_children + relation_child_delta,
        "row_index": row_index,
        "row_name": f"{wrapper.name:#010x}",
        "inserted_row_name": f"{INSERTED_ROW_NAME:#010x}",
        "source_wrapper_index": first,
        "new_wrapper_index": insertion_index,
        "subtree_items": len(block),
        "owned_identities_copied": len(owned_identities),
        "relationship_action_identities": len(action_identities),
        "item_value_tokens_shared": False,
        "companion_records_copied": companion,
        "native_object_map": native_object_map,
        "native_object_ceiling_before": u32be(data, NATIVE_OBJECT_CEILING_OFFSET),
        "native_object_ceiling_after": u32be(patched, NATIVE_OBJECT_CEILING_OFFSET),
    }
    return bytes(patched), summary


def check_section_counts(data: bytes, section: Section) -> tuple[int, int, int]:
    """Verify the member header carries the section's parsed record counts."""
    counts = (section.elements, section.wrappers, section.properties)
    for offset, expected in (
        (ELEMENT_COUNT_OFFSET, counts[0]),
        (WRAPPER_COUNT_OFFSET, counts[1]),
        (PROPERTY_COUNT_OFFSET, counts[2]),
    ):
        found = u32be(data, offset)
        if found != expected:
            raise SceneInsertError(
                f"header word at {offset:#x} is {found}, expected the parsed "
                f"item count {expected}"
            )
    for offset, source in (
        (ELEMENT_COUNT_REPEAT_OFFSET, ELEMENT_COUNT_OFFSET),
        (WRAPPER_COUNT_REPEAT_OFFSET, WRAPPER_COUNT_OFFSET),
        (PROPERTY_COUNT_REPEAT_OFFSET, PROPERTY_COUNT_OFFSET),
    ):
        if u32be(data, offset) != u32be(data, source):
            raise SceneInsertError(
                f"header word at {offset:#x} does not mirror {source:#x}"
            )
    return counts


def bump_section_counts(patched: bytearray, data: bytes, elements: int,
                        wrappers: int, properties: int) -> None:
    """Raise the three record counts and their mirrors by the inserted records.

    The title allocates the document arena and the property storage from these
    words before it reads the item stream, so they must grow with the insert.
    """
    for offset, repeat, delta in (
        (ELEMENT_COUNT_OFFSET, ELEMENT_COUNT_REPEAT_OFFSET, elements),
        (WRAPPER_COUNT_OFFSET, WRAPPER_COUNT_REPEAT_OFFSET, wrappers),
        (PROPERTY_COUNT_OFFSET, PROPERTY_COUNT_REPEAT_OFFSET, properties),
    ):
        if delta:
            put_u32be(patched, offset, u32be(data, offset) + delta)
            put_u32be(patched, repeat, u32be(data, repeat) + delta)


def rebuild(section: Section, data: bytes, items: Iterable[Item], declared: int) -> bytes:
    """Re-serialize the section from its parsed item slices."""
    body = b"".join(data[item.start:item.end] for item in items)
    if len(body) != declared:
        raise SceneInsertError("rebuilt item body does not match its declaration")
    return data[:section.start] + struct.pack(">I", declared) + body + data[section.end:]


def encode(data: bytes, row_index: int) -> tuple[bytes, dict]:
    """Return the re-encoded member plus a summary of every change made."""
    section = find_pause_section(data)
    pairs = pause_row_pairs(section)
    if not 0 <= row_index < len(pairs):
        raise SceneInsertError(
            f"row index {row_index} is outside the seven authored rows"
        )

    if section.declared != sum(item.size for item in section.items):
        raise SceneInsertError("section length is not the sum of its items")
    counts = check_section_counts(data, section)

    # A no-change rebuild must be byte-identical to the input.
    roundtrip = rebuild(section, data, section.items, section.declared)
    if roundtrip != data:
        raise SceneInsertError("no-change roundtrip does not reproduce the input")

    _, wrapper, element = pairs[row_index]
    position = section.items.index(wrapper)
    new_wrapper_index = len(section.items)
    inserted = bytearray(data[wrapper.start:element.end])
    put_u32be(inserted, 0, INSERTED_ROW_NAME)
    element_offset = element.start - wrapper.start
    # The element's parent index is the created-record index of the wrapper that
    # owns it; the copy belongs to the appended wrapper, not the source row.
    put_u32be(inserted, element_offset + 4, new_wrapper_index)

    declared = section.declared + len(inserted)
    items = list(section.items)
    items.append(dataclasses.replace(wrapper, start=wrapper.start + len(inserted)))
    items.append(
        dataclasses.replace(
            element,
            start=element.start + len(inserted),
            parent=new_wrapper_index,
        )
    )
    body = (
        b"".join(data[item.start:item.end] for item in section.items)
        + bytes(inserted)
    )
    if len(body) != declared:
        raise SceneInsertError("patched item body does not match its declaration")
    patched = bytearray(
        data[:section.start]
        + struct.pack(">I", declared)
        + body
        + data[section.end:]
    )
    bump_section_counts(
        patched,
        data,
        1,
        1,
        len(wrapper.properties) + len(element.properties),
    )

    summary = {
        "input_bytes": len(data),
        "output_bytes": len(patched),
        "input_sha256": sha256(data),
        "output_sha256": sha256(bytes(patched)),
        "section_offset": section.start,
        "section_declared_before": section.declared,
        "section_declared_after": declared,
        "items_before": len(section.items),
        "items_after": len(section.items) + 2,
        "elements_before": counts[0],
        "wrappers_before": counts[1],
        "elements_after": counts[0] + 1,
        "wrappers_after": counts[1] + 1,
        "insert_offset": section.end,
        "insert_bytes": len(inserted),
        "row_index": row_index,
        "row_name": f"{wrapper.name:#010x}",
        "inserted_row_name": f"{INSERTED_ROW_NAME:#010x}",
        "source_wrapper_index": position,
        "new_wrapper_index": new_wrapper_index,
    }
    return bytes(patched), summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--row-index", type=int, default=6)
    parser.add_argument(
        "--clone",
        choices=("subtree", "pair"),
        default="subtree",
        help="subtree clones the whole row and owned identities; pair copies "
             "only the wrapper and element records",
    )
    parser.add_argument(
        "--check-roundtrip",
        action="store_true",
        help="parse, verify the no-change roundtrip and print the summary only",
    )
    parser.add_argument("--json", type=Path, help="write the summary as JSON")
    arguments = parser.parse_args(argv)

    data = arguments.input.read_bytes()
    try:
        if arguments.check_roundtrip:
            section = find_pause_section(data)
            pause_row_pairs(section)
            rebuilt = rebuild(section, data, section.items, section.declared)
            if rebuilt != data:
                raise SceneInsertError(
                    "no-change roundtrip does not reproduce the input"
                )
            summary = {
                "roundtrip": "identical",
                "input_bytes": len(data),
                "input_sha256": sha256(data),
                "section_offset": section.start,
                "section_declared": section.declared,
                "items": len(section.items),
                "elements": section.elements,
                "wrappers": section.wrappers,
                "rows": [
                    {"index": index, "name": f"{wrapper.name:#010x}"}
                    for index, wrapper, _ in pause_row_pairs(section)
                ],
            }
        else:
            if arguments.clone == "subtree":
                patched, summary = encode_subtree(data, arguments.row_index)
            else:
                patched, summary = encode(data, arguments.row_index)
            summary["clone"] = arguments.clone
            if arguments.output is None:
                raise SceneInsertError("--output is required to write the member")
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            arguments.output.write_bytes(patched)
            summary["output"] = str(arguments.output)
    except SceneInsertError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)
    if arguments.json is not None:
        arguments.json.parent.mkdir(parents=True, exist_ok=True)
        arguments.json.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
