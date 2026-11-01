# Ahead-of-time pipelines backlog

Created 2026-11-01 at `dev` `d19e7b8b`. Goal: build the Vulkan pipelines the
game will need from the player's own disc before play, so a first drive does
not stop for shader compiles, without depending on a scripted run.

Items are `AOT-*`. The Mac is the target (each cold Metal compile takes
100-190 ms); every Vulkan platform gains from the same catalog.

## Where it stands

- **First-time compiles are the free-roam spikes on the Mac.** Each new
  pipeline costs one 100-190 ms frame on an M4 Pro (docs/MACOS.md
  "First-time pipeline spikes"). Seen pipelines are stored
  (`.vk.xpso`, `.vk.signs.xpso`, `.xsh`) and rebuilt behind the title at the
  next start, so each one hitches once per machine. Skipping the draw
  instead glitches.
- **The preparation run covers only the opening.** `pinyon.py launch` plays
  `fh1-shader-preparation.fh1test` once (DR-1.3, LX-3.3); it presses through
  menus and never drives, so free roam starts cold.
- **The disc already gives every shader program.**
  `tools/extract-fh1-shader-corpus.py` finds 3,819 raw programs and 12,846
  with the vertex variants it derives (`site/findings/files.toml`, shader
  corpus).

## Measured structure (AOT-0)

Joined the stored pipelines to their microcode (`.xsh`) and the disc corpus
(SHA-256 of the microcode, source file of each program):

| Data | Pipelines | Shader pairs | Render/blend state blocks | Notes |
| --- | ---: | ---: | ---: | --- |
| Reference save on multivac, long play (Vulkan, no signs) | 2,831 | 639 | 26 render pass keys, 128 fixed+blend blocks | 1-4 states for most pairs, one pair 49 |
| Mac play copy after 6 min of free roam (signs) | 462 | 329 shader+modification combos | 91 | 41 texture-sign vectors, 169 state+signs |

- Pixel shaders are disc programs: 264 of the 266 the Mac drew.
- 89 of the 224 vertex shaders are not on the disc as stored: each differs
  from a disc program of the same size in 1-36 dwords, the vertex fetches
  patched for a vertex layout that is not among the 34 the corpus reads
  from shader files.
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
| AOT-0 | Structure census above; cold Metal throughput for a background build (pipelines a second on the M4 Pro) | decides whether over-generating is affordable | census done, throughput open |
| AOT-1 | Read the `.fxobj` technique table: which vertex and pixel programs a technique pairs, and any render state it carries | pairs found for the 138 observed same-file pairs | open |
| AOT-2 | Vertex layouts from model files, fed to the corpus's existing fetch patcher | reproduces the 89 runtime vertex shaders | open |
| AOT-3 | State per pair: map techniques and engine passes to the observed state blocks and render pass keys; texture signs from material texture formats, or build AOT pipelines without sign specialization | predicts the 462 Mac pipelines' keys exactly | open |
| AOT-4 | Generator at setup: writes a pipeline description list from the player's disc (nothing distributed, docs/LEGAL.md), built behind the title by the existing background prewarm | no change to frame time once built | open |
| AOT-5 | Fresh free-roam drive on the Mac with the generated list | first-time compiles fall by at least 80 % against 57 in 100 s / 91 in 250 s today | open |

The fallback, if AOT-1 to AOT-3 fail their gates: extend the preparation
route with a free-roam drive.
