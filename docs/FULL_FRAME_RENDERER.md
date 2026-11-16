# Full-frame renderer (B5)

Started 2026-11-15, as step B5 of
[BEYOND_RECOMP_RESEARCH.md](BEYOND_RECOMP_RESEARCH.md). The goal is a
renderer that owns the whole frame: render targets, resolves, the main
scene, shadows, the post chain and the HUD. The game's PM4 stream would
stop being the source of the frame, one part at a time. Performance comes
before exactness, so the image may differ from the console's where it plays
the same.

This page is the plan and the progress record. Each stage ships behind a
switch that is off until its in-run A/B on the Steam Deck LCD and the Odin
2 Portal passes, and it falls back to today's path when it can't handle a
frame.

## Where the frame goes (census, 2026-11-15)

Odin 2 Portal, v4, `race-long` from a private state, uncapped, with
`--fh1_native_gpu_profile=true`. These are ms a frame over a 600-frame
window in the race. The labels are the executor's draw renderings (`base
tile/pitch/MSAA/format`, `+` joins depth and colour), `R` marks resolves
and `T` transfers:

| Part | Full frame | Scene walk and procedural models skipped (`pinyon_shift_debug_skip_world` 7) |
| --- | --- | --- |
| GPU frame | 11.8 | 7.8 |
| Main scene, 4x (`1024/32/4x/d1+0/32/4x/c3`) | 5.87 (17.2 renderings) | 1.98 (12.2) |
| Resolves | 1.66 | 1.65 |
| Transfers | 0.77 | 0.76 |
| Clears | 0.32 | 0.31 |
| Texture reloads (resolved data read back as textures) | 0.22 | 0.23 |
| Full-screen colour (`0/16/1x/c2`, 3 renderings) | 0.92 | 0.86 |
| Post chain renderings (`0/16/1x/c3`, 22, and `c0`, 7.7) | 0.99 | 0.98 |
| Biggest resolves | scene colour 1280×720 0.51 (×2), depth bands 0.42, colour bands 0.33, 320×192 0.12 (×6) | same |

What that says about the stages:

- **The main scene is half the GPU frame.** About two thirds of it is the
  scene walk's meshes (world, cars, props), and the rest is lists the walk
  doesn't send: the sky, terrain and roads.
- **The emulation structure is about 3 ms, a quarter of the frame.** That
  covers resolves, transfers, clears and reloads. None of it is game work;
  it's the cost of copying between EDRAM-shaped surfaces and guest memory.
- **The post chain is about 2 ms** across about 30 renderings and 21
  resolves.

The CPU side (Deck, from the B4 probe): the decoder, recorder and
submission threads are about 24 ms of the 46-50 ms of process CPU. They
can only go once every part of the frame stops coming through PM4.

## Stages

| Stage | What becomes ours | Pool it works on | Gate |
| --- | --- | --- | --- |
| FR-1 | **Frame structure.** Each render target and the texture that reads it are one host image, so a resolve is a layout change, not a copy. Resolves stop writing guest memory unless a CPU or memory reader needs it. Clears become attachment clears, and transfers go where the depth format is ours | resolves, transfers, clears and reloads: about 3 ms Odin GPU | Odin or Deck GPU −1 ms, no visible change |
| FR-2 | **Post chain.** Our own exposure, bloom, grade and composite passes from the scene colour, the 16³ grading LUT and the car mask. The game's ~86 post draws and 21 resolves are skipped | about 2 ms GPU, plus their decoder and recorder work | GPU −1 ms, image acceptable in play |
| FR-3 | **Main scene, retained.** The scene walk's draw records (the per-pass buckets) are drawn by our own renderer from cached per-mesh vertex and index buffers and pipelines, batched by material, using the translated shaders. That replaces the D3D calls and PM4 for those meshes | up to 3.4 ms GPU and 13.8 ms process CPU on the Deck (the B4 probe) | process CPU −6 ms on the Deck |
| FR-4 | **Shadows, camera depth and reflections** through the same retained path | the shadow and depth passes | as FR-3 |
| FR-5 | **Sky, terrain and road lists, and the HUD** | the rest of the main scene (about 2 ms on the Odin) and about 170 HUD draws | as FR-3 |
| FR-6 | **No PM4 for an owned frame.** Where FR-1 to FR-5 cover a frame, the game's command buffers are no longer decoded | the decoder, recorder and submission threads (about 24 ms of Deck CPU) | Deck process CPU −15 ms |

Order: FR-1 first, because it has no game-side unknowns, and its ceiling
(the MR-6 diagnostic) is already measured: 2.41 ms on the UHD 620. Then
FR-2, which is self-contained. FR-3 needs the bucket consumers found
(below).

**Where each stage stands (2026-11-16):**

| Stage | State |
| --- | --- |
| FR-1 | Closed: the copy-free class is under the gate on both devices |
| FR-2 | Closed: folded into FR-1 and FR-6 (the post chain's draws are cheap) |
| FR-3 | Unmerged forms closed; the merged form is sized and not started, a multi-week SDK project waiting for the maintainer's decision ("FR-3: can an owned path merge draws") |
| FR-4 | Waits on FR-3: it uses the same retained path for shadows, camera depth and reflections |
| FR-5 | Waits on FR-3: the sky, terrain and road lists go through the same path |
| FR-6 | Waits on FR-3 to FR-5: it needs every part of a frame owned |

The full-frame renderer is not built. What would pass its gates is the
merged form of FR-3 below; every form that keeps the game's draws one for
one has been measured under them.

## FR-1: frame structure

Known from MR-6
([MODERN_RENDERING_RESEARCH.md](MODERN_RENDERING_RESEARCH.md#resolve-memory-copies-mr-6)):

- `fh1_resolve_to_textures` already writes up to two current textures from
  the resolve's own dispatch. The memory copy is what's left.
- Skipping every memory copy over 4 KB (`fh1_debug_resolve_textures_only`)
  saved 2.41 ± 0.29 ms of GPU frame on the UHD 620, at 75.6 dB against the
  control.
- Deferring the copies until something reads them saved nothing. The
  readers are the reflection cube's 18 face resolves (reloaded by the cube
  each frame), and a 1280×720 and a 640×360 result read through another
  texture. Writing those from the textures used up the ceiling.

So FR-1 turns those readers into direct targets:

1. Resolve the cube faces straight into the cube texture's faces and mips.
2. Make the 1280×720 and 640×360 results' readers views of the resolved
   image.
3. Then drop the memory copy wherever every reader is direct. Keep it for
   CPU reads (resolves of 4 KB or less, the car-thumbnail readback) and
   memory export.

**Ceiling on the yardstick devices (2026-11-15).** These are in-run A/Bs on
`race-long`, uncapped, from the same builds as the B4 probe:

| Switch | Deck GPU | Deck process CPU | Odin GPU |
| --- | --- | --- | --- |
| `fh1_debug_resolve_textures_only` (no memory copy where a texture is current), two runs each | −0.10 ± 0.58, +0.06 ± 0.51 ms | +0.7, +0.3 ms (noise) | −0.24 ± 0.93, −0.23 ± 0.87 ms |
| `fh1_debug_skip_resolve_dispatches` (no resolve shader at all) | −1.55 ± 0.41 ms (−11 %) | −4.44 ± 2.30 ms | −1.36 ± 0.85 ms (−12 %) |

**The memory copies cost nothing on these GPUs**, unlike the UHD 620.
Steps 1-3 above therefore don't pay here, and FR-1 changes target:

- The pool is the resolve itself, 1.4-1.55 ms.
- The only way to reach it is to stop copying: render into the texture
  that reads the result. One way is to hand the render target's image to
  the texture when the next use of the target overwrites it whole, and
  give the target a fresh image. That is what The Simpsons Game recomp
  calls copy-free resolves.
- The biggest candidates are the 1280×720 scene-colour resolve (0.51 ms
  on the Odin, twice a frame) and the depth and colour band resolves of
  the main scene (0.75 ms together).

## FR-2: post chain ceiling

`fh1_debug_skip_rendering_draws` with `fh1_debug_skip_renderings=0/16/1x/c3`
drops the draws of the 22 small post renderings. Their state, clears and
resolves still run. Odin, two in-run A/Bs, uncapped: GPU −0.24 ± 0.89 and
−0.21 ± 0.90 ms, frame −0.28 and −0.25 ms, all noise. The side with the
skip drew 130-140 more scene draws, which hides about 0.1-0.2 ms. The
Deck runs didn't produce data: one stopped on the title menu, and the
other's capture didn't summarize.

The post chain's draws are cheap. Most of its 0.99 ms in the census is the
renderings and resolves themselves, which FR-1's copy-free resolves would
also reach. **FR-2 alone is not worth a native post chain.** It folds into
FR-1, then FR-6.

## What the pools say so far

On the GPU-bound devices, the frame's structure (resolves 1.4-1.55 ms) and
the post chain (about 0.2 ms of draws) are small. Most of the GPU frame is
the main scene's own content: the game's geometry through the game's
shaders. An owned renderer reaches that content only by drawing less of
it:

- culling hidden draws (#784 measured 48-70 % of the main scene's
  depth-writing draws passing no samples);
- coarser levels of detail;
- or cheaper shading.

So FR-3 moves ahead of FR-2, and it starts with occlusion culling that is
allowed to be a few frames late.

## FR-3a: occlusion culling a few frames late

The visibility census (`fh1_visibility_census=N`) already puts an
occlusion query around every draw every N frames, keyed by the draw's
command-buffer position and ordinal. `fh1_visibility_oracle_skip` drops,
in the frames between censuses, every draw that passed no samples at its
last census, before the draw is derived, so the recorder saves its CPU
work too. #784 rejected it as unsafe, because a draw that becomes visible
stays hidden until the next census. Under performance over correctness,
that is a pop-in of at most N frames.

**Measured 2026-11-15**, N = 4 (67 ms at 60 fps), with an in-run A/B of
the skip, uncapped, two runs per device:

| Device | Draws skipped a frame | GPU time | Process CPU | Frame, census on, skip off |
| --- | --- | --- | --- | --- |
| Deck | 835-885 (−38 %) | −0.25 ± 0.70, −0.26 ± 0.52 ms | −0.7 ms (noise) | 14.5-15.0 ms against 13.6 without the census |
| Odin | not counted in its capture | −1.30 ± 0.37, −1.40 ± 0.99 ms | −2.0, −1.8 ms | 12.75-13.1 ms against 11.5 without the census |

How to read it:

- The hidden draws are cheap on the Deck, because early depth rejects
  their pixels. On the Odin, a tiler, they're worth about 1.3 ms.
- The census queries cost about as much as the skip saves on both
  devices, so **query-driven culling is a wash**.
- A culler that pays has to get visibility for free. It also has to drop
  draws before the game builds them, so that guest D3D, the decoder and
  the recorder all skip them (about 4.2 µs of process CPU a draw on the
  Deck, from the B4 probe).

## FR-3b: occlusion culling in the game's own pass culling

Built and measured 2026-11-15 on the Deck (race-long, uncapped). Rejected;
the code stays in, off by default.

How it works:

- ShiftGlue (`fh1_occlusion_grid`, `src/graphics/vulkan/fh1_occlusion.cpp`)
  reduces the main scene's depth to 16-pixel tiles of their farthest depth
  (80 × 45 at 1280 × 720) with one compute pass at the scene's first
  resolve. Untiled, that is the one point where the depth is whole; by
  the HUD the last band has been copied over it. A four-slot ring is read
  back a few frames late and published through rexruntime
  (`rex/system/fh1_occlusion_grid.h`) with that frame's world-view-projection
  (c128-c131) and depth constants (stored depth = A + B / view z). A grid
  whose matrix drifted more than `fh1_occlusion_max_drift` from the current
  one is not published, and a grid older than four frames is cleared.
- The native pass culling (`pinyon_shift_occlusion_cull`,
  `src/guest_native/scene_cull.cpp`) projects an item's box with that
  matrix and drops it from the pass when every tile its rectangle covers is
  farther than its nearest corner. Items crossing the near plane, off
  screen, or covering more than 256 tiles are kept.

What it found:

- Open: on untiled platforms the camera depth copy is still taken when
  the HUD starts. While building the grid, a copy at that point read
  zeros. The copy feeds ambient occlusion and the upscalers, and whether
  they see zeros there was not checked.
- The grid fills (3,210-3,366 of 3,600 tiles hold depth) and is oriented
  right (`fh1_occlusion_dump_dir` writes it as PGM images). Captures with
  culling on showed nothing missing.
- Only passes 0-5 (cascades), 6, 9, 11 and 24 get items in a race. Pass 9
  is the main view's **terrain**: dropping all of it
  (`pinyon_shift_debug_drop_pass=9`) leaves grey ground and bare hills,
  while trees, props and cars stay. They come through the procedural-model
  culling and other lists, not this one.
- In-run A/B of culling pass 9: about 62 items a frame reach the test,
  46-49 % of them culled; frame +0.19 ± 0.32 ms, GPU +0.17 ± 0.41 ms, draws
  −56 ± 354: nothing.
- The view buckets do not decide what the main view draws. Dropping all
  four view passes (6, 9, 11, 24) still removes only the terrain. The walk
  draws a mesh whenever `824400B0` returns that some pass kept it. Trees
  and props come through the procedural-model culling, which the mask
  doesn't touch. Why the cars stay is open. With
  `pinyon_shift_debug_skip_world=4` (return 0, nothing pushed) the whole
  world goes, which is B4's −21 %.
- Ceilings, in-run A/Bs (`pinyon_shift_debug_drop_passes`, 35 windows):
  dropping pass 9 (the terrain) saved 0.59 ± 0.47 ms of frame and
  0.62 ± 0.55 ms of GPU (−238 draws). Dropping all view passes saved
  0.71 ± 0.41 ms of frame and 0.93 ± 0.49 ms of GPU (−374 draws). Culling
  only the hidden part of the terrain reached none of that.

- So the test moved to the whole item (`pinyon_shift_occlusion_whole`): a
  main-view item hidden in the grid returns 0 from every pass, shadows
  included. Captures showed nothing missing. In the A/B race about 490
  calls a frame list view 9, but most are kept before the grid is
  consulted: a box corner behind or at the camera (shadow casters around
  it, 67 %), off screen (15 %), or more than 256 tiles (3 %). About 48 items
  a frame were culled, some 2 % of the draws. The in-run A/B moved the
  frame by +0.17 ± 0.44 ms and draws by +22 ± 410: nothing. A second run
  stayed on the title menu and was discarded.

**FR-3b is closed.** Few of the items the walk tests are on screen and
in front of the camera, and the grid hides about 48 of them a frame. On
the Deck hidden draws are also cheap, because early depth rejects them.
The Odin was not run: with no gain on the Deck, it can't reach the gate.

## FR-1: which resolves hold the pool

`fh1_debug_skip_resolve_classes` skips resolve dispatches by class: bit 0
of the class is a multisampled host surface, bit 1 depth, bit 2 a current
texture written by the same dispatch, and bit 3 a rectangle spanning the
surface's width. It also counts resolved pixels per class. Bit 0 never
fired on the Deck, even for the guest's 4x and 2x surfaces, so it does not
tell their resolves apart. In-run A/Bs, `race-long`, uncapped, 35 windows:

| Skipped class | Frame | GPU | Process CPU |
| --- | --- | --- | --- |
| 12: colour, whole width, writes a texture (two runs) | −0.83 ± 0.49, −0.87 ± 0.42 ms | −0.87, −0.97 ms | −3.5, −3.2 ms |
| 14: depth, whole width, writes a texture | −0.25 ± 0.54 ms | −0.25 ms | −0.6 ms |

The GPU profile (`fh1_native_gpu_profile`, Deck, 3.1 ms of resolves with
the profile's own overhead) splits class 12 by surface:

- the four 1280 × 720 single-sampled colour resolves (two each from two
  surfaces) take 0.94 ms of profiled time;
- the 4x scene bands (1280 × 256 and 1280 × 208) take 0.43 ms;
- the 256 × 256 2x target, resolved six times, takes 0.17 ms;
- outside class 12, the 1280 × 720 depth resolve takes 0.32 ms.

So even all of class 12 is under the −1 ms gate, and the part an image
swap could take (the four 1280 × 720 resolves) is about half of it.

**Odin** (v4 APK, same route and switch, 35 windows): skipping class 12
gave frame −0.65 ± 0.88 ms and GPU −0.57 ± 1.06 ms, also under the gate.

**The cheapest replacement keeps most of the cost.** A test path replaced
the resolve shader with a plain `vkCmdCopyImage` from the surface into the
current texture, for whole single-sampled 32-bit colour resolves (about
seven a frame, guest memory not written). On the Deck the in-run A/B gave
frame −0.27 ± 0.74 ms, within noise. The copy was also wrong: the texture
holds the guest word's channel order and the render target doesn't, so
red and blue came out swapped and 2_10_10_10 washed out. A correct version
needs a swizzling shader or an image swap with swizzled views. A swap
removes even the copy; its bound is skipping those seven resolves alone,
about 0.5 ms by their profile share (not isolated in an A/B). The path was
removed.

**FR-1 is closed.** Skipping every resolve dispatch is worth −1.55 ms of
GPU on the Deck and −1.36 ms on the Odin, but most of that is resolves a
copy-free design can't take (depth, multisampled bands, small targets).
The class it can take is under the gate on both devices, and the swap
candidates within it are about half of that. `fh1_debug_skip_resolve_classes` stays as the probe.

## FR-3 to FR-6: the CPU ceiling, capped (2026-11-15)

**Correction (2026-11-16).** `skip_world` bit 1 (the model assets,
`824365B0`) never applied before commit 231b0482: the function was
missing from `host_overridden_functions`, so its only caller reached the
original directly and the probe never ran (no `scene.model_asset_skip_probe`
summary in any run). That voided the switch 1 rows below, not the switch 7
ones: with bit 4 on, `824365B0` is reached only 268-2,949 times in a whole
run (against about 1.4 million with bit 1 alone), so the model assets are
part of the scene walk's meshes, dropped before their lists are submitted,
not a separate path. The old and new switch 7 rows differ by the scene
instead: the old run skipped 1,182 draws a frame and the new ones 2,165-2,309,
at a similar 6-7 µs of process CPU a skipped draw (the light-scene pitfall of
B4). With the fix (Deck, same routes, capped, 35 windows each):

| Skipped | Device | Draws | Process CPU | Render | Decoder | Recorder | Submission |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 7: everything, fixed | Deck | −2,309 | −15.26 ± 2.60 ms | −3.23 ms | −5.43 ms | −4.26 ms | −1.79 ms |
| 1: model assets, fixed | Deck | −1,852 | −9.03 ± 2.69 ms | −1.02 ms | −3.98 ms | −3.13 ms | −1.44 ms |
| 7, fixed, second run | Deck | −2,165 | −12.53 ± 4.64 ms | −2.52 ms | −4.80 ms | −3.57 ms | −1.43 ms |

Skip 4 alone (s4) and skip 5 (s5) on the fixed build drew light scenes
again (−1,190 and −916 draws; −3.9 ± 4.6 and −5.5 ± 5.3 ms), so they don't
size anything. In full scenes, by the reasoning
below (an owned renderer removes the render thread's and the decoder's
share and keeps recording and submitting its own draws), the reachable pool
on the Deck is about 7.3-8.7 ms less the native culling it still runs,
about 7.0-8.4 ms over the two skip-7 runs: over FR-3's −6 ms gate either
way. The Odin's switch 7 rows stand; its switch 1 rows are void. The rest of
this section is the original text, measured in a lighter scene.


B4's process CPU saving (−13.8 ms on the Deck) came from uncapped runs, where
every millisecond of frame also costs CPU: the process keeps about three
cores busy. This round's uncapped A/Bs show the same ratio for work that
removes no CPU at all (skipping class-12 resolves: −0.85 ms frame, −3.3 ms
process CPU). So the ceiling was measured again at the 60 fps cap, where
both sides have the same frame time: `pinyon_shift_debug_skip_world` against
0, by submission path, 35 windows each.

| Skipped | Device | Draws | Process CPU | Decoder | Recorder | Submission |
| --- | --- | --- | --- | --- | --- | --- |
| 7: everything (B4's switch) | Deck | −1,182 | −8.68 ± 4.23 ms | −2.61 ms | −2.21 ms | −0.81 ms |
| 7 | Odin (v4) | −1,784 | −6.96 ± 1.62 ms | −3.51 ms | (inline) | −0.79 ms |
| 4: scene-walk meshes, run 1 | Deck | −1,108 | −4.81 ± 4.16 ms | −1.97 ms | −1.64 ms | −0.57 ms |
| 4, run 2 | Deck | −710 | −4.77 ± 4.28 ms | −1.52 ms | −1.15 ms | −0.51 ms |
| 4 | Odin | −1,260 | −5.34 ± 0.64 ms | −2.69 ms | (inline) | −0.95 ms |
| 2: procedural models | Deck | −856 | −2.53 ± 4.65 ms | −1.53 ms | −0.70 ms | −0.15 ms |
| 2 | Odin | −636 | −1.64 ± 0.89 ms | −0.83 ms | (inline) | 0.00 ms |
| 1: model assets | Deck | +25 | −0.41 ± 3.66 ms | | | |
| 1 | Odin | +80 | +0.20 ± 0.85 ms | | | |

(A first version of this section used switch 4 alone and concluded that
FR-3 failed on paper; switch 7 is B4's.)

With nothing drawn, the scene walk and the procedural models together are
worth 7-8.7 ms of process CPU, over FR-3's −6 ms gate. By thread on the
Deck (switch 7): render thread −1.94 ± 1.07 ms, decoder −2.61, recorder
−2.21, submission −0.83; the main thread and the workers don't move. (The
Odin build doesn't log per-thread slots.) An owned renderer in which the
guest stops submitting these meshes removes the render thread's and the
decoder's share, about 4.5 ms, less the native culling it still runs
(about 0.3 ms). It still records and submits its own draws, and DR-4.2's
buffer replay showed a replayed draw costs the recorder about what a full
one does. So the reachable pool is about 4.2 ms, under the gate, unless
the owned path also draws fewer, batched draws. **FR-3 was started anyway**
(user's call, 2026-11-15). Its next unknowns are who issues each path's
draws, and whether a draw's per-frame constants can be made without the
guest.

A run comparing cascade-only and view masks against `skip_world=4` stayed
on the title menu. Why the cars survive the view mask (perhaps calls the
native culling hands back to the original) is still open.

## FR-3: what is still unknown

- **Who reads the per-pass buckets.** The pass culling pushes 20-byte
  records onto five buckets per pass at `[r3+13844] + (pass × 5 + bucket) ×
  16` (`site/findings/rendering.toml`, "per-draw pass culling"). D3D's
  device code uses an offset 13844 of its own (the constant flushes
  `82408B70` and `8240DC70`, and the draw entries below, where it feeds
  the write pointer at +48); in a Deck race the renderer was at
  `413FFFC0` and its bucket headers at `4275DDB8`, in a virtual heap,
  where no command buffer the GPU reads can be, so the two fields are
  unrelated. Their readers are not found yet. Of the generated functions that load +13844, the ones on this
  object are the pass culling, the procedural culling (`8243EE58`), the
  walk (`82440CF8`) and the free-roam walk parent `82D65608`, which hands
  it to a 39-instruction per-frame list refresh (`82D5C9D0`). The others
  (`82461978`, and the draw entries `823FA0A8` and `824610C0`) are D3D
  device code whose own +13844 field sets the write pointer at +48. So the
  readers take the base from a register or a copy, and a static search
  doesn't reach them.
- **A page watch can't find them either.** A probe wrapped the walk and
  armed the SDK's guest access watch on the bucket pages after it
  returned. The bucket headers are at `4275DDB8`, in a virtual heap, and
  the watch only covers the physical heaps (0xA0000000 and up), so it
  never armed. Finding the readers this way would need a virtual-heap
  watch in the SDK. The probe was removed.
- **Who issues the draws (Deck race, 2026-11-15).** The guest stack's
  return-address slots are never written (the generated code keeps saved
  registers and the return address in host locals), so deep chains come
  from the frame-pointer race profile of 2026-11-13 through
  `tools/re/draw-chains.py`, and per-setting counts from the census's
  direct-caller histogram (`pinyon_shift_d3d_census_callers`, one race per
  `skip_world` value). Both are probable, one run each:
  - The procedural models draw immediately: entry 1 (`82415F68`) takes
    about 373 calls a frame, half into the ring and half into the tiled
    path, none recorded into a command buffer, from
    `82415CE0 < 82417418 < 824170D8 < 8243D2A0`. `skip_world` 2 takes it
    to 29 and removes that caller.
  - The scene-walk meshes reach the GPU as display-list runs: `skip_world`
    4 leaves the procedural caller and drops the runs from about 536 to
    331 a frame and the drawn draws from about 2,500 to 1,700. In the
    profile, about 30 % of the list executor's time (`82416A00`, run from
    `824167F8`) comes through `82437218 < 8243D340 < 82447490 < 82441718`:
    `82447490` is the car presentation (`CCarPresentation` slot 106), whose
    cloned lists these are (rendering findings, "display-list owners"). So
    cars are walk meshes drawn through their presentation; the bucket
    drain for the rest of the walk is still not named.
  - The model assets (`824365B0`) also run display lists, about 47 % of
    the executor's time, through `82417060 < 824365B0 < 82436468`.
  - `82439B70 < 8244CA98` is the common parent of the model-asset,
    procedural and `8243BD40` paths.
- What a record's object holds: mesh, vertex and index buffers, material,
  constants. Then how the game binds a material per draw: the
  `CD3D9GraphicsDevice` slots.


## FR-3: can an owned path merge draws (2026-11-16)

An owned path that keeps every draw still pays the recorder and submission
for it. In full Deck scenes at the cap a skipped draw is worth about 6-7 µs
of process CPU: the render thread about 1.1, the decoder about 2.3, the
recorder about 1.9 and submission about 0.7 µs (from the skip 7 rows
above). So an unmerged owned path has the render-thread and decoder share
to win, and only by drawing fewer, merged draws can it reach the rest.

**Unmerged forms are bounded by earlier work.** DL-3 compiled every display
list and replayed it without parsing (D3D_RENDERER_RESEARCH.md): on the
Deck the decoder fell 1.03 ± 0.10 ms and process CPU 0.91 ± 0.37 ms, and
NA-2.4's owned programs per list came out even. A replay of the model-asset
lists' decoded records at `824365B0` hands the recorder the same register
runs and draws, so it can't take the 3.5 ms of render and decoder time a
slice of the gate needs. It was not built. The Deck's decoder profile says
why (frame-pointer race profile, 2026-11-13): about 90 % of the decoder
thread is register writes (copying and swapping runs, comparing them with
the register file, recording them for the recorder), and deriving draws is
1.4 %; skipping the parse leaves the writes.

**Batch census.** ShiftGlue's ordered frame census
(`fh1_frame_census_ordered`, a build with `REXGPU_FH1_ORDERED_CENSUS`) now
writes, for every host draw, its rendering instance, pipeline, a hash of
the texture and vertex fetch constants its shaders read, the guest index
base, `RB_BLENDCONTROL0`, the innermost indirect buffer and a hash of the
dynamic state (viewport, scissors, window offset, depth bias, stencil
reference, face mode). `tools/re/batch-census.py` counts the batches a frame
would need if opaque draws were reordered within their rendering instance and
blended ones kept in order. Deck race at the cap, skip-off frames of the
in-run `sw1-long` and `sw7-long` routes, frame pairs every 30 frames:

| Draws merged by | Batches a frame (1,613-1,617 host draws) | Factor |
| --- | --- | --- |
| pipeline, textures, vertex fetch (only constants per draw) | 1,076-1,135 | 1.4-1.5 |
| pipeline and textures (vertex fetch per draw too) | 664-669 | 2.4 |
| pipeline only (bindless textures) | 383-408 | 4.0-4.2 |

Adding the dynamic state changes no count by more than 1 %. Two fixed-skip
runs (skip 0 against skip 7, different scenes, so a lower bound) put the
skipped set at 1,239 host draws, 97 % opaque: 870, 492 and 109 batches by
the three keys.

What else the census found:

- **The draws repeat; a third of their buffers are new each frame.**
  89-90 % of a frame's draws have a pipeline, textures, vertex fetch and
  index base that also occur in the previous frame (as a multiset; the order
  changes). Of the about 260-280 innermost indirect buffers a frame, 89 %
  recur at the same address a frame later, but those carry only 60-64 % of
  the draws: the rest, about 450-500 draws a frame, come through about 15
  buffers that are new every frame. A retained path keyed by buffer would
  miss them, so it has to be keyed on the game's side (the asset and its
  list).
- **Tagging draws by buffer doesn't find an owner's set.** Buffers that run
  on the skip-off side and never on the skip-on side carried about 500
  draws a frame, but the mirror count (skip-on draws in buffers never seen
  skip-off) was about 450: the test picks up the per-frame buffers.
- **Skip 1's draws.** Of the 1,852 decoded draws skip 1 removes in a full
  scene, 1,140 are host draws and 714 later-tile copies the untiling drops
  early (`fh1_untile_skipped_draws`), the same ratio as the whole frame.
- **Fixed-skip runs leave the race.** With skip 7 from frame 4,600 the car
  ended up spinning at 8 mph on bare ground instead of driving at 35, while
  everything still drawn (sky, ground, cars, HUD) drew correctly. Measure
  with in-run A/Bs, where both sides share the route.
- The census runs drew light scenes (2,669 decoded draws a frame on the
  skip-off side, where runs without it drew 2,793-4,142), and write 98-115
  MB a run.

**The merged form, sized.** By the census, merging the scene walk's draws
by pipeline and textures needs about 2.4 times fewer draws, and 4 times
with bindless textures. At the cap that could leave most of skip 7's
12.5-15.3 ms, but it needs, all of them new:

1. translated shaders that read float constants and fetch constants for
   each draw from a table indexed by the draw (multi-draw indirect, or an
   instance index), so draws with different constants can merge;
2. bindless textures, for the 4x factor;
3. per-mesh draw records captured on the game's side and kept while the
   asset's list doesn't change, with the vertex fetch supplied live (it
   changes from one frame to the next for about a tenth of the draws);
4. insertion at the list's place in the stream, as DL-1.2's marker does.

That is a multi-week ShiftGlue and game project. It is recorded here as
sized and not started, for the maintainer to decide; nothing short of it
reaches FR-3's gate.
