---
title: Modding
section: Technical
order: 4
description: Asset, archive, database, texture and native mods for Pinyon Shift, and how they keep your save separate.
---

# Modding

Mods live in the state folder, never in the game files. They can replace files, patch single archive members, merge settings, patch the game database, replace textures, or run native code through a C API. This page is a summary; the full contract is [docs/MODDING.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MODDING.md).

## Layout

```text
<state>/mods/<name>/
  mod.toml
  code/<name>.dll        a native mod (optional)
  game/...               whole files that replace the game's (optional)
  members/...            single members of the game's archives
  merge/...              settings merged by key
  db/*.sql               database patches
  textures/<hash>.dds    texture replacements
```

`<state>` for an installed preview is `%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview`.

## Enabling

List mods, in load order, in `<state>/config/pinyon_shift.toml`:

```toml
enabled_mods = "hello_telemetry,english_strings"
```

The in-game **SETTINGS** screen lists the mods it finds. Changes apply at the next start. Each load or rejection is logged as `mod.loaded` or `mod.rejected` with the reason.

## mod.toml

```toml
name = "hello_telemetry"              # must equal the folder name
version = "1.0.0"
abi = 1                               # PINYON_MOD_ABI_VERSION it was built for
game_version = "DB40DF605ADE49A6"     # optional: prefix of the default.xex SHA-256
library = "code/hello_telemetry.dll"  # omit for an asset-only mod
requires = []
load_after = []
conflicts = []
```

A mod with a missing requirement or a conflict isn't loaded. The v4 title update build identifies as `74B033805AB1BCAA`; a mod that uses only symbol and hook names can list both builds.

## Your save stays separate

With any mod enabled, the game plays a separate profile in `<state>/user-modded`, copied from yours the first time. Your own profile in `<state>/user` isn't opened while mods are on. Each modded save records the enabled mods and their hashes. Turn all mods off to get back to your unmodded profile, unchanged.

## Asset mods

| Kind | How it works |
| --- | --- |
| Whole files (`game/`) | Replace the file with the same path, case-insensitively. The earlier mod in the load order wins |
| Archive members (`members/<archive>/<member>`) | Before each start, the affected archives are rebuilt from your own copy with only those members replaced |
| Merged settings (`merge/`) | `.ini` keys and `.xml` elements are merged into the file, so several mods can change one settings file |
| Database (`db/*.sql`) | SQL scripts run in load order on a copy of `media/db/gamedb.slt` |
| Textures (`textures/<hash>.dds`) | Find a texture's hash with `--texture_dump_dir`. A replacement keeps the format and may be 2, 4 or 8 times larger. **SETTINGS > MODS > RELOAD TEXTURES** reloads them in game |

For example, a merge that removes free-roam traffic:

```xml
<AIOpenWorld><Settings name="freeroam">
  <CarList numInitialTrafficCars="0" numInitialFestivalCars="0"/>
</Settings></AIOpenWorld>
```

Nothing from the game disc may be distributed. A mod's install steps should build its files from the player's own copy, as `tools/install-sample-mod.py english_strings` does.

## Native mods

A native mod is a DLL built against [`include/pinyon_mod.h`](https://github.com/arcanite24/pinyon-shift/blob/dev/include/pinyon_mod.h). It exports two functions:

```c
PINYON_MOD_EXPORT uint32_t rex_mod_abi_version(void) { return PINYON_MOD_ABI_VERSION; }
PINYON_MOD_EXPORT int rex_mod_create(const PinyonModApi* api, PinyonMod* mod);
```

Through the API a mod can:

- Subscribe to hook points: frame tick, the player's vehicle pose, save encrypt and decrypt, file open, pause menu buttons.
- Read and write guest memory, and look up symbols and offsets by name. Mods never hard-code addresses.
- Call guest functions from a guest task on the game's main thread.
- Register settings and rebindable keys, show dialogs and write to the log.
- Draw HUD labels, add rows to **SETTINGS > MOD ACTIONS** and replace text in the game's string tables.

The ABI only grows: new members are appended to `PinyonModApi`, and its `size` tells a mod which exist. Recompiled code calls functions directly, so a mod can observe hook points and call functions, but can't replace a guest function.
