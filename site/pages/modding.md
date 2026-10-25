---
title: Modding
section: Technical
order: 4
description: Asset, archive, database, texture, Vulkan shader and native mods, and how they keep your save separate.
---

# Modding

Mods live in the state folder, never in the game files. They can replace files, patch single archive members, merge settings, patch the game database, replace textures or Vulkan shaders, or run native code through a C API. This page is a summary; the full contract is [docs/MODDING.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MODDING.md).

## Layout

```text
<state>/mods/<name>/
  mod.toml
  code/<name>.dll        a native mod (optional)
  game/...               whole files that replace the game's (optional)
  members/...            single members of the game's archives
  add/...                new members added to the game's archives
  merge/...              settings merged by key
  strings/<lang>/*.toml  new or changed text in the string tables
  db/*.sql               database patches
  textures/<hash>.dds    texture replacements
  shaders/shader_<guest>_<modification>_<translated>.spv  Vulkan replacements
```

`<state>` for an installed preview is `%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview`.

## Enabling

The built-in `hidden_cars` mod lists four hidden player-model variants.
Traffic entries such as the tour bus are excluded because driving support
does not establish garage or paint support. Existing purchases remain in
the isolated modded profile. To recover a blocked current selection, close
the game and run `python tools/fh1-profile.py recover-car --state-root "<state>"`.
It backs up the selected modded profile and settings before requesting the
title's starter-car fallback, preserving the trainer setting. Keep a
save-isolating mod enabled after recovery. Use the same title version and let it save
before restarting. Recovery/save/reload checks pass on private base and v4
fixtures with the trainer disabled, preserving original cars, parts and
credits. [Audit, limits and restore instructions](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/HIDDEN_CARS.md).

The intro Corrado's Garage and Design Creator entry routes pass on Windows
with the integrated livery resolve corrections. Paint editing, saving and
reloading, the other variants' full garage checks and v4 qualification remain
open; these entry checks do not establish complete model support.

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
| New archive members (`add/<archive>/<member>`) | Appended to the rebuilt archive, for example a new colour grading map in `dynamicpost.zip`. A name the archive already has is refused, as is a `members/` name it lacks |
| Strings (`strings/<language or ALL>/<Table>.toml`) | `IDS_` names with their text: existing names are changed, new ones added with their key, which the database refers to as `_&N` (`tools/fh1-strings.py`) |
| Merged settings (`merge/`) | `.ini` keys and `.xml` elements are merged into the file, so several mods can change one settings file |
| Title-update settings (`merge-update/`) | `.ini` and `.xml` member merges against the installed v4 update, such as `merge-update/media.zip/camera/cameraphysics.xml`. Built into the generated mod's `update/` overlay; inactive without the update. The verified update stays untouched |
| Database (`db/*.sql`) | SQL scripts run in load order on a copy of `media/db/gamedb.slt`, or of the database an enabled mod replaces it with |
| New cars (`tools/clone-fh1-car.py`) | A spec of cars that reuse an existing model with their own name, price, power and listed class becomes a `db/` script and `strings/` names. Once bought, the game rates a car from its physics, so a listed index should be the one the owned car shows. Clones upgrade and paint like any car; bought cars stay in the modded profile, which still loads if the mod is removed |
| Textures (`textures/<hash>.dds`) | Find a texture's hash with `--texture_dump_dir`. A replacement keeps the format and may be 2, 4 or 8 times larger. **SETTINGS > MODS > RELOAD TEXTURES** reloads them in game. On a GPU without BC formats (most Android GPUs) only 8_8_8_8 replacements apply |

For example, a merge that removes free-roam traffic:

```xml
<AIOpenWorld><Settings name="freeroam">
  <CarList numInitialTrafficCars="0" numInitialFestivalCars="0"/>
</Settings></AIOpenWorld>
```

Elements without a key attribute, such as the layers in `CameraPhysics.xml`, match by position; mark an element `pinyon-add="true"` to append it instead.

The built-in immersive camera supplies separate disc and v4 merges because
the update has more chase-camera layers. Regenerate both with
`python tools/build-immersive-camera.py`. Live chase height, distance, FOV
and spring stiffness are in [CAMERA EDITOR](playing.md#camera-editor);
their defaults preserve the loaded tuning and per-car camera overrides.
See [Camera editor](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MODDING.md#camera-editor) for the
data and runtime boundary.
Update member merges also preserve the winning whole-archive override
under a mod's `update/` directory.

Nothing from the game disc may be distributed. A mod's install steps should build its files from the player's own copy, as `tools/install-sample-mod.py english_strings` does.

## Shader mods

Enabled mods can provide Vulkan SPIR-V in `shaders/`. The earlier loaded
mod with a valid exact match wins; separate shaders compose, while two
replacements of one shader do not merge. Names include the guest hash,
specialization and XXH3 hash of the original translation, so changed
translator output cannot silently select stale bytecode. Invalid files
are logged and skipped. Changes require a restart.

Capture one GPU frame with `vulkan_shader_discovery_dir` and
`vulkan_shader_discovery_frame`, then run
`python tools/discover-fh1-shaders.py <capture>`. It lists exact identities,
draws, the HUD boundary and bound color/depth surfaces without disassembly.
`--check-mod <mod>/shaders` compares a mod against that frame. Surfaces do
not identify materials or objects. Keep capture files in `.local/`.

Overrides can change existing inputs' use; preserve the renderer's bindings
and stage interface. They cannot add game inputs. Rebuild and test after
translator or graphics-setting changes, and test driver compilation cost
on the target GPU. Only independently authored code may be distributed;
translated guest bytecode stays local.
[Authoring contract and capture commands](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MODDING.md#shader-replacements).

## Frame inspector

On desktop Vulkan, **Ctrl+F8** opens a frame inspector. **Capture next frame**
freezes surface sizes, formats, draw counts and previews, resolve source
rectangles, and texture identities. Hover a texture row for its base-level
XXH3 hash, which uses the texture replacement filename's byte domain.
GPU-written or unavailable payloads have no CPU hash. The inspector is off
by default and captures only on request; capturing waits for the GPU.

To open a local `.fh1frame` dump, restart with
`--fh1_frame_inspector_replay=true`, paste its path and choose **Open dump**.
The title stays suspended in this workspace. **Color** reports the replay's
front-buffer comparison; **Wireframe** needs `fillModeNonSolid`, and
**Overdraw** adds red per fragment on blend-capable attachments while keeping
render-pass clears. Diagnostic views are restricted to replay.

Previews are at most 256 pixels along their longest side. Resolve previews
show the source before destination packing and sample selection; depth is
grayscale. The [inspector contract and limits](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/FRAME_INSPECTOR.md)
describe image lifetimes and how to record and compare a dump. Dumps contain
game data: keep them local.

Windows verification on an RTX 4080 covered live capture, dump recovery and
diagnostic views. Inspected Color output matched plain replay byte for byte;
the tested recording still differed from its live frame. Disabled frame-time
measurements varied too much to establish a no-regression result. The linked
contract records the method, numbers and remaining qualification work.

## Rally world probe

For Rally-world experiments, `tools/create-rally-freeroam-seed.py` builds a
private base-disc seed from verified owned Rally and a pinned save. It uses a
separate test profile and always places the car at an owned stage start.
It cannot qualify save/resume or travel back to Colorado, and is not installed
as a built-in mod. See the [probe and remaining gates](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/RALLY_FREEROAM.md).

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

The archives are extracted with [7-Zip](https://www.7-zip.org) when it is installed, otherwise with the system `tar`. Some Windows `tar.exe` builds can't read XE's LZMA archives; the install then stops before extracting and asks you to install 7-Zip and choose **Install XE** again.

## The UDLC pack

[UDLC v1.2](https://www.moddb.com/mods/forza-horizon-udlc-pack/downloads/udlcv12)
by Warshack4874 installs as a community DLC package. Download it yourself,
then use the launcher's DLC panel or `python tools/pinyon.py dlc udlc --find`.
The optional Traffic Car Unlocker needs UDLC. See
[installation and qualification](dlc.md#community-udlc) for the verified
versions and known paint-shop hangs. Pinyon Shift does not redistribute
these downloads.

["Open" UDLC](https://www.moddb.com/mods/forza-horizon-udlc-pack/downloads/open-udlc)
replaces the game's database files for editing the DLC cars. It is not a
DLC package and is not supported by the importer or the UDLC command.

## Native mods

A native mod is a DLL built against [`include/pinyon_mod.h`](https://github.com/arcanite24/pinyon-shift/blob/dev/include/pinyon_mod.h). It exports two functions:

```c
PINYON_MOD_EXPORT uint32_t rex_mod_abi_version(void) { return PINYON_MOD_ABI_VERSION; }
PINYON_MOD_EXPORT int rex_mod_create(const PinyonModApi* api, PinyonMod* mod);
```

Through the API a mod can:

- Subscribe to hook points: frame tick, the player's vehicle pose, save encrypt and decrypt, file open, pause menu buttons.
- Read and write guest memory, and look up functions, hook sites and offsets by name instead of hard-coding them. The table does not name data globals yet, so the [Game objects](game-objects.md) examples give the two they need for both executables.
- Call guest functions from a guest task on the game's main thread.
- Register settings and rebindable keys, show dialogs and write to the log.
- Draw HUD labels, add rows to **SETTINGS > MOD ACTIONS** and replace text in the game's string tables.

The ABI only grows: new members are appended to `PinyonModApi`, and its `size` tells a mod which exist. Recompiled code calls functions directly, so a mod can observe hook points and call functions, but can't replace a guest function.
