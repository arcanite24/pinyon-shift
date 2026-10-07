# Modding Pinyon Shift

Pinyon Shift loads mods: native libraries that react to the title through
hook points and a C API, and asset mods that replace game files. This page
is the contract for mod authors. The design and its history are in the
[native port backlog](NATIVE_PORT_BACKLOG.md#np-7-mod-host-v1) (NP-7).

## Layout and enabling

A mod lives in the state directory, never in the game files:

```text
<state>/mods/<name>/
  mod.toml
  code/<name>.dll        optional: a native mod
  game/...               optional: files that replace the game's
```

`<state>` is the directory the launcher runs with (`--state-root`); for an
installed preview it is `%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview`.
Mods load when their names are listed, in order, in the `enabled_mods`
setting of `<state>/config/pinyon_shift.toml`:

```toml
enabled_mods = "hello_telemetry,english_strings"
```

The in-game SETTINGS screen lists the mods found under `mods/`. A change
takes effect at the next start. Every load and every rejection is logged as
a `mod.loaded` or `mod.rejected` event with the reason.

### mod.toml

```toml
name = "hello_telemetry"          # must equal the directory name
version = "1.0.0"
abi = 1                           # PINYON_MOD_ABI_VERSION the mod was built for
game_version = "DB40DF605ADE49A6" # optional: prefix of the default.xex SHA-256
library = "code/hello_telemetry.dll"  # omit for an asset-only mod
requires = []                     # mods that must be enabled and load first
load_after = []                   # mods to load after when they are enabled
conflicts = []                    # mods that must not be enabled with this one
```

A mod whose requirement is missing or failed, or that conflicts with an
enabled mod, is not loaded. Load order follows `requires` and `load_after`,
otherwise the `enabled_mods` order.

`game_version` may also be a list. The FH1 v4 title-update build identifies
itself as `74B033805AB1BCAA`, the SHA-256 prefix of its verified patched
image. It has its own symbol table, so a mod that uses only symbol and hook
names can list both builds:
`game_version = ["DB40DF605ADE49A6", "74B033805AB1BCAA"]`. A mod that relies
on raw guest addresses or field offsets must target one build: classes grew
in v4, so several offsets differ (see the
[title update v4 backlog](TITLE_UPDATE_V4_BACKLOG.md)).

## Your saves stay separate

With any mod enabled, the title plays a separate profile,
`<state>/user-modded`, which starts as a copy of the player's own the first
time. The unmodded profile in `<state>/user` is never opened while mods are
on. Every save of the modded profile writes `user-modded/pinyon_shift_mods.json`
with the enabled mods, a hash of the mod set and a hash of the plaintext save
body, so a save can always be traced to the mods that made it. Turning all
mods off returns to the unmodded profile unchanged.

Marketplace DLC installations and their entitlement headers are shared from
`<state>/user`: launcher enable/disable changes apply to both profiles. Creating
the modded profile copies save data without duplicating DLC assets. Existing
DLC copies under `user-modded` are left in place but are not enumerated.

## Asset mods

Files under `game/` replace the game's files with the same path
(case-insensitive) while the mod is enabled; an earlier mod in the load order
wins over a later one. New directories supplied by a mod are accessible;
existing disc directories retain their base files alongside replacements.
Replacement is whole files: the title reads its
archives (`media/*.zip`) through C streams, so an asset mod ships a complete
archive. Nothing from the game disc may be distributed; a mod's install
instructions should build its files from the player's own copy, as
`tools/install-sample-mod.py english_strings` does. Each replaced file the
title opens is logged as `mod.file.override`.

For an FH1 archive containing XMem members, use
[`patch-fh1-archive.py`](../tools/patch-fh1-archive.py) to replace selected
members in a new archive built from your own game files:

```powershell
python tools/patch-fh1-archive.py <original.zip> <new.zip> --replace member.xml=<edited.xml>
```

The tool retains other members' compressed bytes and updates both ZIP header
offsets and FH1's absolute payload offsets (extra field `0x1123`). Ordinary ZIP
repacking can leave those offsets pointing into unrelated data. The output
must be a new file; the original is never overwritten. A loose XML under
`game/media/GameModes` does not replace an existing member of `gamemodes.zip`.

The title checks some game files block by block against SHA-256 digests of
the originals and stops with a dirty-disc error on a mismatch. For a file a
loaded mod replaces, the host accepts the mismatch (logged once as
`mod.file.hash_accepted`); every other file is still checked.

### Single archive members

Most game data lives in zip archives listed in `media/zipmanifest.xml`. A
mod that changes one file inside an archive ships just that member:

```text
<state>/mods/<name>/members/<archive path>/<member path>
e.g. mods/my_mod/members/media/StringTables/EN.zip/PauseMenu.str
```

Before each start, `tools/build-mod-archives.py` (run by
`launch-preview.ps1`) rebuilds each affected archive from the player's own
copy: other members keep their compressed bytes, replaced ones are stored
uncompressed, and a matching `zipmanifest.xml` goes with it, all as the
generated mod `zz-archive-patches`. An earlier mod wins a member two mods
replace. Only existing members can be replaced, and archives whose end
record disagrees with the manifest (the largest track archive) must still be
replaced whole. `zz-archive-patches/archives.json` lists what was rebuilt.

### Settings merged by key

Several mods can change the same settings file when each ships only the
settings it changes, under `merge/` instead of `members/`:

```text
<state>/mods/<name>/merge/<archive path>/<member path>
e.g. mods/my_mod/merge/media/physics.zip/PhysicsSettings.ini
```

A merged `.ini` (such as `PhysicsSettings.ini` or `GameTunableSettings.ini`)
lists `Section\Key value` lines: those keys take the new values (keeping the
file's own `=` or space), other keys keep the player's, and unknown keys are
added. A merged `.xml` (such as `AIOpenWorld.xml`) mirrors the file's
structure with only the elements to change: an element matches the file's
element of the same tag with the same `id`, `name`, `model`, `key` or `type`
attribute, or, without one, the one at the same position among its tag; its
attributes and text replace the file's, unmatched elements are added, and
`pinyon-remove="true"` removes the matched one. For example, no free-roam
traffic:

```xml
<AIOpenWorld><Settings name="freeroam">
  <CarList numInitialTrafficCars="0" numInitialFestivalCars="0"/>
</Settings></AIOpenWorld>
```

Merges apply on top of a member another mod replaces (or the player's own,
decompressed with the build's `pinyon_shift_fh1_archive_extract`), and for a
key two mods set, the earlier mod in the load order wins. `archives.json`
lists the mods merged into each member.

### Textures

A mod may replace textures without touching the archives that hold them:

```text
<state>/mods/<name>/textures/<hash>.dds
```

`<hash>` is 16 hex digits naming the texture's content. To find it, run the
game with `--texture_dump_dir=<folder>`: every DXT1, DXT3, DXT5, DXT5A (BC4),
DXN (BC5) and 8_8_8_8 texture it loads is written there as `<hash>.dds`,
untiled and with its mip levels. 8_8_8_8 dumps use a DX10 header and keep the
channels as the game stores them (the game's swizzle picks them when it
draws), so edit them in place rather than reordering channels. Textures the
game renders itself (resolve output) are never dumped or replaced. Edit
a dump and ship it under the same name; the replacement must keep the format
and at least as many mip levels, otherwise it is logged and ignored. Earlier
mods win.

A replacement may also be 2, 4 or 8 times the dump's width and height (the
same factor both ways). It then needs at least the dump's level count; any
further levels, down to the dump's smallest size and below, are used too,
so ship a full chain: for a 2x replacement of a 512x512 dump with 10 levels,
1024x1024 with 11 levels. The game samples it like the original, only
sharper.

While the game runs, SETTINGS > MODS > RELOAD TEXTURES reads the texture
folders again and reloads every texture (`texture_replacement_reload`), so
edited, added or removed replacements show without a restart; the game
hitches once while its caches refill.

## Database patches

The game's data (cars, prices, events) is the SQLite database
`media/db/gamedb.slt`. A mod may ship SQL scripts in `db/*.sql`:

```sql
-- mods/cheap_jaguar/db/10-price.sql
update Data_Car set BaseCost = 1000 where Id = 1496;
```

Before each start, `tools/build-mod-patches.py` (run by
`launch-preview.ps1`) copies the player's own database, applies every
enabled mod's scripts in load order and file-name order, and serves the
result as the generated mod `zz-db-patches`, listed first so it wins. With no
scripts left the generated mod is removed and the stock database returns.
`zz-db-patches/patches.json` records the base and patched hashes and every
script applied.

## Native mods

A native mod is a DLL built against the C header
[`include/pinyon_mod.h`](../include/pinyon_mod.h). It exports two functions:

```c
PINYON_MOD_EXPORT uint32_t rex_mod_abi_version(void) { return PINYON_MOD_ABI_VERSION; }
PINYON_MOD_EXPORT int rex_mod_create(const PinyonModApi* api, PinyonMod* mod);
```

`rex_mod_create` keeps the `PinyonModApi` pointer, registers what it needs
and fills `PinyonMod` with its lifecycle callbacks: `on_create_dialogs`
(presentation is ready: add binds), `on_module_launched` (the title is about
to start) and `on_shutdown`. Mods are loaded before the title starts and are
never unloaded. The ABI only grows: members are appended to `PinyonModApi`,
whose `size` tells a mod which exist.

### Hook points

| Id | When | Event fields |
| --- | --- | --- |
| `PINYON_HOOK_FRAME_TICK` | once per title frame, main thread | none |
| `PINYON_HOOK_VEHICLE_POSE` | the player's vehicle pose is final | `floats[0..2]` position, `args[0]` its guest address |
| `PINYON_HOOK_SAVE_BEFORE_ENCRYPT` | the save body is about to be encrypted | `args[0]` body address, `args[1]` size |
| `PINYON_HOOK_FILE_OPEN` | the title opened a file | `text` lower-case guest path |
| `PINYON_HOOK_PAUSE_BUTTON_CONSTRUCTED` | the pause menu built a button | `args[0]` button address |
| `PINYON_HOOK_SAVE_AFTER_DECRYPT` | a saved file was decrypted, before the title reads it | `args[0]` body address, `args[1]` size |

Callbacks run on the guest thread that reached the hook, synchronously: keep
them short. `subscribe` returns a handle for `unsubscribe`.

### The profile body

The two save hooks see the plaintext of the title's secure files. The
profile (`ForzaProfile`) begins with a self-describing section: a
big-endian field count, then for each field `[u32 name length][name][u32
0x20][u32 0][u8 type][value]`. Types are 0x00 bool and 0x01 byte (1 byte),
0x03 UInt32, 0x07 Int32 and 0x09 float (4 bytes), 0x04 UInt64 (8 bytes), and
0x0F a struct, whose value is its own field count and fields. The player's
values are under `Main` (`Main/Credits`, `Main/XP`, `Main/Level`,
`Main/WristbandLevel`). Class-serialised challenge states and padding follow
the section. `tools/fh1-profile.py` decodes a body and edits a field. Edit a
save after it is decrypted, not before it is encrypted: the running title
keeps its own copy of the values, so a value written into an outgoing save
only lasts until the next save. To change the credits while the game runs,
call the title's accessors from a guest task instead (`profile.from_user`,
`profile.credits` and `profile.set_credits`).

### Guest memory, symbols and calls

Guest memory is big-endian, as the title sees it; `read_guest` and
`write_guest` copy bytes. Writing memory the GPU reads (textures, vertex
buffers) is not supported: the renderer would not see the change.

Mods never hard-code addresses. `find_symbol("frame.tick")` and
`find_offset("vehicle.slot.position")` look names up in the symbol table for
the supported executable: [`config/mod/fh1-symbols.toml`](../config/mod/fh1-symbols.toml),
plus every hook site as `hook.<name>`. Unknown names return 0 or -1. The
table is generated into the host by `tools/generate-fh1-symbols.py`, and a
test fails when it and the hook declarations disagree.

Guest functions are called only from a guest task: `enqueue_guest_task`
runs a callback on the title's main thread at the next frame tick, where
`call_guest(address, args, count)` calls a function with up to six integer
arguments and returns `r3`. Recompiled code calls other functions directly,
so a mod cannot replace a guest function; it can only observe hook points and
call functions.

### Settings, binds, dialogs and logging

- `register_cvar(name, default, description)` adds a text setting under
  "Mods", saved in `pinyon_shift.toml`; prefix the name with the mod's.
  `get_cvar` and `set_cvar` read and change any setting by name.
- `register_bind(name, "F9", description, callback, user)` adds a key bind the
  player can rebind; the callback runs on the UI thread.
- `show_dialog(title, text, buttons, count, callback, user)` shows a host
  message box over the title; the chosen index (or `UINT32_MAX` for cancel)
  arrives on the UI thread.
- `log(level, text)` writes the runtime log; `log_event(event, keys, values,
  count)` writes a `mod.<event>` diagnostics event.

### HUD labels and menu actions

The host draws a mod's UI over the title in the game's own fonts, without
touching guest addresses (NP-11):

- `set_hud_text(id, text, x, y, size)` shows, moves or (with empty text)
  removes a label. Positions are in the title's 1280x720 layout; keep to the
  90 % safe area, x 64 to 1216 and y 36 to 684, so the label stays on screen
  at every output size. Ids are shared by all mods: derive yours from your
  mod's name. It may be called from any thread, including hooks.
- `add_menu_action(label, callback, user)` adds a row to SETTINGS > MOD
  ACTIONS, reached from the pause menu's SETTINGS, and runs `callback` on the
  UI thread when the player picks it.

- `set_ui_string(table, key, text)` replaces the text of one entry of the
  title's string tables, such as a menu row's label, with UTF-8 text of any
  length; the title's own layout then fits it. It applies when the title
  next loads the table, so call it from `rex_mod_create`. `table` is the
  table's file name and `key` its 16-bit entry key, which
  `tools/fh1-strings.py` lists:

  ```text
  python tools/fh1-strings.py --archive <game>/media/StringTables/EN.zip --table PauseMenu.str --grep photo
  0xDED7  PHOTO MODE
  ```

  Each replacement is logged as `ui.string.override` (in place when it
  fits, otherwise appended to the table). The host renames the pause menu's
  offline MULTIPLAYER row (`0xDD6B`) to SETTINGS unless a mod sets it.

Adding rows to the title's own menus (native UI4 insertion) is still
research, tracked as NP-11.3 in the backlog.

## Samples

| Sample | Shows |
| --- | --- |
| [`hello_telemetry`](../mods_src/samples/hello_telemetry/hello_telemetry.c) | a setting, an F9 bind, `frame.tick` and vehicle-pose hooks, a guest call through the task queue (`kernel.get_av_pack`), a host dialog, a HUD label, a menu action, a longer pause-menu label and shutdown |
| [`english_strings`](../mods_src/samples/english_strings/mod.toml) | an asset-only mod replacing `media/StringTables/EN.zip` |

Build and install them into a private state copy (never the AppData save):

```text
cmake --build out/build/win-amd64-release --target pinyon_shift_mod_hello_telemetry
python tools/install-sample-mod.py <state> hello_telemetry
python tools/install-sample-mod.py <state> english_strings
```

`config/render-tests/fh1-mods.fh1test` runs both in a scripted route.
