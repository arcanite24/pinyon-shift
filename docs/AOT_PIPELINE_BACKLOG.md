# Ahead-of-time pipelines backlog

Created 2026-11-01 at `dev` `d19e7b8b`. Goal: build the Vulkan pipelines the
game will need from the player's own disc before play, so a first drive does
not stop for shader compiles, without depending on a scripted run.

Items are `AOT-*`. The Mac is the target (each cold Metal compile takes
100-190 ms); every Vulkan platform gains from the same catalog.

## Where it stands

- **Done 2026-11-01, gate met with the shipped list.** In two 100 s drives
  to far roads on the M4 Pro (method below), the
  draws that waited for a first-time compile fell from 51 to 0 and 3 (two
  runs) and from 46 to 4: 91-100 % fewer, against the 80 % gate. The list
  holds earlier Mac free roam too, so part of that is in-sample; a list from
  the Windows reference save alone cut them to 16 and 21 (69 % and 54 %).
- **Windows Vulkan and Android.** `prepare-fh1-shaders.ps1` writes the
  list before its preparation route (`pinyon.py prepare-shaders
  --pipelines-only`), and the route builds it. Android gets the PC's list:
  the launcher's Wi-Fi share offers it as the "free-roam pipelines" group
  and `pinyon.py android push-data --state-root` copies it over USB. On the
  RTX 4080 the east probe first needed 322 pipelines without a list
  (`appdata-2026-09-27-winwarm` seed), 15 with the shipped list (in-sample: most of it is this PC's play) and 32
  with a list from Mac play alone (764 pipelines). The background build
  took 30 s for 5,215 pipelines. Where the stored pipelines are built
  before the title (Windows, Linux, Android) the list is still built behind
  it, on 2 threads on Android (`vulkan_aot_prewarm_threads`). Android is
  not measured yet: no test device was free.
- **First-time compiles are the free-roam spikes on the Mac.** Each new
  pipeline costs one 100-190 ms frame on an M4 Pro (docs/MACOS.md
  "First-time pipeline spikes"). Seen pipelines are stored
  (`.vk.xpso`, `.vk.signs.xpso`, `.xsh`) and rebuilt behind the title at the
  next start, so each one hitches once per machine. Skipping the draw
  instead glitches.
- **The preparation run covers only the opening.** `pinyon.py launch` plays
  `fh1-shader-preparation.fh1test` once (DR-1.3, LX-3.3); it presses through
  menus and never drives, so free roam started cold.
- **What ships.** `config/fh1-aot-pipelines.json`: 2,916 pipeline
  descriptions from long play (the Windows reference save and the Mac play
  copy) and, for their 1,159 shaders, the disc program each comes from (by
  SHA-256) with the edits that make it the shader the title draws with. No
  microcode. `pinyon.py prepare-shaders` extracts the player's disc and DLC
  programs (8.5 s), applies the edits, pairs each shader pair with every
  state seen with either of its shaders, and writes
  `cache/shaders/shareable/4D5309C9.fbo.aot.xpso` (about 5,200 pipelines).
  It is rewritten when the catalog or the installed DLC change. ShiftGlue
  (`vulkan_aot_pipelines`) builds the list behind the title with the stored
  pipelines; the preparation route builds it too, so the driver cache has
  it before the first real start.
- **Texture signs.** On the Mac and Android the pipelines a draw uses are
  specialized for the signs of the bound textures, which a list made ahead
  of play cannot know. ShiftGlue now draws with the unspecialized pipeline,
  whose shaders read the same signs from the system constants, while the
  variant builds (`vulkan_signs_generic_fallback`, on). So the list holds
  unspecialized pipelines only.

## Measured structure (AOT-0)

Joined the stored pipelines to their microcode (`.xsh`) and the disc corpus
(SHA-256 of the microcode, source file of each program):

| Data | Pipelines | Shader pairs | Render/blend state blocks | Notes |
| --- | ---: | ---: | ---: | --- |
| Reference save on multivac, long play (Vulkan, no signs) | 2,831 | 639 | 26 render pass keys, 128 fixed+blend blocks | 1-4 states for most pairs, one pair 49 |
| Mac play copy after 6 min of free roam (signs) | 462 | 329 shader+modification combos | 91 | 41 texture-sign vectors, 169 state+signs |

- Pixel shaders are disc programs: 264 of the 266 the Mac drew.
- 89 of the 224 vertex shaders are not on the disc as stored. Most are a
  same-size disc program with exports turned into no-ops or moved to
  another output register, as a link step fitting a vertex shader's outputs
  to its pixel shader's inputs would; some also have fetches reformatted
  for a vertex layout the corpus does not read from shader files, a few
  have inserted instructions (AOT-2).
- Every pair whose two shaders are on the disc (138) comes from one source
  file (an `.fxobj` or `default.xex`).
- Of the 148 pipelines first seen in free roam after the benchmark route,
  103 reused a state block and 137 a sign vector the route had already
  produced; only 77 shared a pixel shader with it. New roads bring new
  shader pairs drawn in known states.
- By the pixel shader's source, those 148 free-roam pipelines are 64 track
  materials, 48 `default.xex` programs, 24 car shader files and 12 without
  a pixel shader. Track material files hold at most 4 vertex and 4 pixel
  programs, so pairing every program in one file is close to exact; the car
  files (about 257 x 240 programs) and `default.xex` (176 x 294) need the
  technique table, 371,710 pairs in all otherwise.
- The effect description precedes the program containers in an `.fxobj`'s
  shader block. In `Cars/DropShadow.fxobj` (3 vertex programs, 1 pixel)
  three 16-byte records near its end each hold a distinct pointer and two
  shared ones, likely the three techniques; the pointers do not equal the
  containers' file offsets, so the block's in-memory layout comes first.

## Items

| Item | What | Gate / measure | Status |
| --- | --- | --- | --- |
| AOT-0 | Structure census above; cold Metal throughput for a background build | decides whether over-generating is affordable | done: 4,937 pipelines behind the title in 66 s on 9 threads with an empty Metal cache, 2.0-2.3 s for 5,393 once Metal has them |
| AOT-1 | Read the `.fxobj` technique table: which vertex and pixel programs a technique pairs | pairs found for the 138 observed same-file pairs | dropped: pairs come from play instead (the catalog); the table is not needed for the gate |
| AOT-2 | Where the runtime-only vertex shaders come from | reproduces them from the disc | done: of 1,594 stored shaders, 925 are disc programs and 636 edits of a same-size one (exports turned into no-ops or moved to another output register, fetches reformatted); 33 are neither and their pipelines are left out |
| AOT-3 | State per pair | predicts the Mac pipelines' keys | done without prediction rules beyond play: states come from the catalog, each pair also gets the states of pairs sharing a shader (from the Windows save and the route alone, 115 of the 148 Mac free-roam pipelines instead of 95); texture signs replaced by the unspecialized fallback |
| AOT-4 | Generator at setup, nothing distributed | no change to frame time once built | done: `tools/fh1_aot_pipelines.py`, `pinyon.py prepare-shaders` |
| AOT-5 | Fresh free-roam drive on the Mac with the generated list | first-time compiles fall by at least 80 % | met: 91-100 % fewer blocking compiles (above) |

Method for AOT-5: the M4 Pro, hidden runs of
`config/render-tests/fh1-aot-drive.fh1test`, which opens the map,
fast-travels to a far road (`cheat_fast_travel_anywhere`) and drives 100 s
with alternating steering (the west drive moves the map cursor the other
way, `-16000 -12000`), on the `appdata-2026-09-27-macwarm` seed (the
benchmark route's 314 pipelines stored), with and without the list in the
seed's storage. ShiftGlue logs `First draw with pipeline` for each pipeline
a draw needs that is not stored, and whether it drew with a built
unspecialized pipeline meanwhile. Frame times cannot show the gain on this
Mac: its Metal cache already held every pipeline from earlier play and runs, so no
run had a frame over 50 ms; the count of draws that had to wait is the
measure.

| Run | Drive | List | First needed | Waited (nothing built) | Drew unspecialized |
| --- | --- | --- | ---: | ---: | ---: |
| aot-a1 | east | none | 51 | 51 | 0 |
| aot-b1 | east | Windows only, Metal cache cold | 43 | 27 | 16 |
| aot-b2 | east | Windows only | 46 | 16 | 30 |
| aot-c1 | east | shipped | 48 | 0 | 48 |
| aot-c2 | east | shipped | 53 | 3 | 50 |
| aot-wa | west | none | 46 | 46 | 0 |
| aot-wb | west | Windows only | 61 | 21 | 40 |
| aot-wc | west | shipped | 55 | 4 | 51 |

In aot-b1 every wait came before the 66 s background build had finished; 16
of them were in the list. The preparation route now builds the list, so a
new player's first start finds Metal's cache filled.

To rebuild the catalog after more play (any platform's
`cache/shaders/shareable`), extract a corpus with the DLC
(`extract-fh1-shader-corpus.py --content-root` for each package) and run
`tools/fh1_aot_pipelines.py catalog --corpus <corpus dir> --storage <dir>
... --output config/fh1-aot-pipelines.json`.

The fallback, if AOT-1 to AOT-3 failed their gates, was to extend the
preparation route with a free-roam drive; not needed.
