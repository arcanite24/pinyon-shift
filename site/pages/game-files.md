---
title: Files and formats
section: Reverse engineering
order: 9
description: The layout of Forza Horizon's media folder and the formats inside it: XMem LZX ZIP archives and their payload-offset field, LSB2 string tables, XDS textures, the SQLite game database and its merge files, UI scene files and FMOD banks, with code to read them.
---

# Files and formats

The disc's `media/` folder is 7.18 GB in 2,385 files. Most of it is 524 ZIP archives holding 258,936 members, nearly all compressed with the Xbox's XMem LZX codec, which ordinary ZIP tools list but cannot extract. The rest is loose FMOD sound banks, XML, compiled shaders and one SQLite database.

| Folder | Size | What is in it |
| --- | ---: | --- |
| `tracks/` | 2.9 GB | Colorado's scenery archive (230,057 members) and the UI studio tracks ([World and tracks](game-world.md)) |
| `cars/` | 1.5 GB | one archive per car: `.carbin` models, `.xds` textures, livery masks, physics XML |
| `audio/` | 1.4 GB | 984 FMOD `.fsb` banks and 34 `.fev` event files, the radio ([Audio and radio](game-audio.md)) |
| `ui/` | 0.7 GB | textures, fonts and UI scene archives ([UI, HUD and input](game-ui.md)) |
| `wheels/` | 135 MB | rim models |
| `stringtables/` | 7 MB | one archive of `.str` tables per language |
| `db/` | 3 MB | `gamedb.slt`, the game database |
| top level | | `gamemodes.zip` (flow scripts), `renderscenarios.zip`, `camera.zip`, `physics.zip`, `Livery.zip`, `UI.zip` and loose XML |

The v4 title update adds one `media.zip` whose members the game prefers over the disc's ([Title update v4](game-title-update.md)).

## Media layout and file access

{{findings:files/Media layout and file access}}

## Archives

{{diagram:game-archive-format|An FH1 archive. The game finds each member's data through extra field 0x1123 in the central directory, not through the local header, so a repacked archive must rewrite that field.}}

The extra field is easy to read with Python's `zipfile`, which lists method-21 members even though it cannot decompress them:

```python
import struct, zipfile

def payload_offsets(path):
    """(name, method, size, payload offset) for each member of an FH1 archive."""
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            extra, pos = info.extra, 0
            while pos + 4 <= len(extra):
                tag, size = struct.unpack_from("<HH", extra, pos)
                if tag == 0x1123:  # little-endian u32: absolute payload offset
                    yield (info.filename, info.compress_type, info.file_size,
                           struct.unpack_from("<I", extra, pos + 4)[0])
                pos += 4 + size

for name, method, size, offset in payload_offsets("media/gamemodes.zip"):
    print(f"{offset:#010x} method {method:2} {size:8} {name}")
```

Where a local header exists, the offset equals the header's position plus its 30 bytes, name and extra field; a method-21 payload then starts with a frame header (`0xFF` and two big-endian sizes for a short frame). To decompress, use `pinyon_shift_fh1_archive_extract` ([Methods and tools](game-methods.md#data-files)) or an LZX decoder with a 64 KiB window over the joined frame bodies.

{{findings:files/Archives}}

## String tables

All UI text is in `.str` tables, one archive per language under `media/stringtables/`. A string is found by a 16-bit key; the game database refers to strings as `_&N`, where N combines a table hash and the key ([Cars, events and DLC](game-content.md#game-database)). This reads a table's directory:

```python
import struct

def read_str_table(data: bytes) -> dict[int, str]:
    """Key -> text for one extracted .str (LSB2) table."""
    assert data[:4] == b"LSB2"
    chunk = struct.unpack_from(">I", data, 12)[0]          # offset of the string chunk
    count = struct.unpack_from(">I", data, chunk + 4)[0]
    entries = [struct.unpack_from(">HI", data, chunk + 8 + 6 * i) for i in range(count + 1)]
    pool = chunk + 8 + 6 * (count + 1)                      # NUL-terminated UTF-16BE strings
    strings = {}
    for key, offset in entries[:-1]:                        # the last entry is the 0xFFFF sentinel
        start = pool + 2 * offset
        end = start
        while data[end:end + 2] != b"\0\0":
            end += 2
        strings[key] = data[start:end].decode("utf-16-be")
    return strings
```

`tools/fh1-strings.py` does the same with extraction included, and mods replace an entry with `set_ui_string`.

{{findings:files/String tables}}

## Textures and models

A car's models are `.carbin` files in its archive: one for LOD1-5, one for LOD0, the cockpit, and a caliper and a rotor per wheel. Each is a list of named parts (body, hood, bumpers, glass, lights). A part has a box, a pool of 28-byte vertices and one index buffer per material and LOD. A vertex stores its position relative to the box's offset as a direction and a length: a unit vector in three 16-bit values, and a fourth value giving the length as a fraction of the length of the box's half-extent vector. The game passes the offset and that length to its vertex shader as one constant per part, so the boxes are tight:

```text
position = (x, y, z) / 32767 * w / 32767 * |half_extent| + offset
```

`tools/fh1_carbin.py` reads every base car's models and writes them back byte for byte (`roundtrip`), and `dump` lists the parts. It is the first step of the car importer ([#496](https://github.com/arcanite24/pinyon-shift/issues/496)). `set_positions` refits a part's box to new positions and re-encodes them; an XKR-S rewritten 1.2 times wider this way is clean in game. Decoding each axis with its own half-extent looks right for an unchanged model but breaks as soon as a box changes, which is what an Autoshow frame dump sorted out.

{{findings:files/Textures and models}}

## Game database

`gamedb.slt` is an ordinary SQLite 3 file, so any SQLite tool reads it (open it read-only). What its tables mean for cars and events is on [Cars, events and DLC](game-content.md).

```sh
sqlite3 "file:media/db/gamedb.slt?mode=ro" "select name from sqlite_master where type='table' order by name"
```

{{findings:files/Game database}}

## UI scene files

UI scenes are described with the rest of the interface on [UI, HUD and input](game-ui.md#scene-files).

## Other formats

{{findings:files/Other formats}}
