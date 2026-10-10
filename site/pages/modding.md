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
hide_dlc = []                         # DLC package IDs the game must not see
profile = ""                          # play a new save in <state>/user-<profile>
shares_save = false                   # true: changes only looks, keeps the player's save
```

A mod with a missing requirement or a conflict isn't loaded. The v4 title update build identifies as `74B033805AB1BCAA`; a mod that uses only symbol and hook names can list both builds. `hide_dlc` hides marketplace packages, such as an expansion whose database the mod replaces, without changing them.

## Your save stays separate

With any mod enabled, the game plays a separate profile in `<state>/user-modded`, copied from yours the first time. Your own profile in `<state>/user` isn't opened while mods are on. Each modded save records the enabled mods and their hashes. Turn all mods off to get back to your unmodded profile, unchanged. A mod with a `profile` plays its own new save in `<state>/user-<profile>` instead.

A mod that only changes how the game looks or sounds, and never what it saves, can set `shares_save = true`. When every enabled mod does, the game keeps your own profile. The built-in immersive camera is one.

## Asset mods

| Kind | How it works |
| --- | --- |
| Whole files (`game/`) | Replace the file with the same path, case-insensitively. The earlier mod in the load order wins |
| Archive members (`members/<archive>/<member>`) | Before each start, the affected archives are rebuilt from your own copy with only those members replaced |
| Merged settings (`merge/`) | `.ini` keys and `.xml` elements are merged into the file, so several mods can change one settings file |
| Database (`db/*.sql`) | SQL scripts run in load order on a copy of `media/db/gamedb.slt`, or of the database an enabled mod replaces it with |
| Textures (`textures/<hash>.dds`) | Find a texture's hash with `--texture_dump_dir`. A replacement keeps the format and may be 2, 4 or 8 times larger. **SETTINGS > MODS > RELOAD TEXTURES** reloads them in game |

For example, a merge that removes free-roam traffic:

```xml
<AIOpenWorld><Settings name="freeroam">
  <CarList numInitialTrafficCars="0" numInitialFestivalCars="0"/>
</Settings></AIOpenWorld>
```

Elements without a key attribute, such as the layers in `CameraPhysics.xml`, match by position; mark an element `pinyon-add="true"` to append it instead.

Nothing from the game disc may be distributed. A mod's install steps should build its files from the player's own copy, as `tools/install-sample-mod.py english_strings` does.

## Custom radio stations

`tools/build-fh1-radio.py` builds a mod that adds a folder of music to Radio1, Radio2 or Radio3, or replaces a station's playlist with it. It needs [FFmpeg](https://ffmpeg.org/) and uses your own game files:

```text
python tools/build-fh1-radio.py D:\Music\Drive --state-root <state> --station Radio1 --replace --enable
```

The tracks play on the game's radio like its own; the DJ lines are unchanged. The mod holds a copy of the game's 680 MB music bank plus your tracks. To hear your music without touching the radio, use **YOUR MUSIC** on the AUDIO page instead.

## The XE mod

[Forza Horizon XE](https://www.moddb.com/mods/forza-horizon-xe-mod) adds about 170 cars and engine swaps. In the launcher (under DLC on Windows), **Download from ModDB** opens both XE downloads in your browser and installs them as soon as they finish in your Downloads folder. If you already have `Forza_Horizon_1_XE_Mod_v1.0.7z` and `FH1XE_v1.01_hotfix.7z`, choose **Install XE** instead, or run:

```text
python tools/pinyon.py xe install Forza_Horizon_1_XE_Mod_v1.0.7z FH1XE_v1.01_hotfix.7z
python tools/pinyon.py xe install --find --open-pages --wait 14400
```

Pinyon Shift never downloads XE itself: ModDB doesn't allow automated downloads, so your browser does it.

The archives are checked against ModDB's sizes and MD5s, and only the files that differ from your game are kept (2.4 GB; 7 GB free is needed while installing). XE runs on the base disc build, hides Horizon Rally and plays its own new save in `<state>/user-xe`, as its readme asks. Your own save isn't touched. `xe disable` turns it off and `xe remove` deletes its files but keeps its save.

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
