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
| FR-3 | Closed 2026-11-16: replays through the decoder and merging are bounded at about 1 ms each, and a replay of the model-asset lists that skips their decode and still records their draws (M2's floor) cost 1.57 µs a decoded draw on the Deck where its line allows 1.02 ("FR-3 M2: the retained path's ceiling") ("FR-3 M2: the retained path's ceiling") |
| FR-4 | Closed with FR-3: its passes would go through the same retained path, and the G0 runs that sized it replayed buffers from every pass |
| FR-5 | Closed with FR-3: the same path, the same ceiling |
| FR-6 | Closed: it needs FR-3 to FR-5, and on the Deck a replayed list's draws cost the recorder and submission more than the decode they saved left room for |

The full-frame renderer is not built, and none of its forms pass the
gates: replays through the decoder and merging were measured or sized at
about 1 ms each, and a retained path that skips the decode over its line (1.57 µs a decoded
draw left where 1.02 is allowed) ("FR-3 M2: the retained path's
ceiling"). The CPU the game's draws cost is spread over its guest code,
the decode, the state that decode leaves behind and the recording, and no
seam tried here removes enough of it while the draws still have to be
recorded.

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

**What merging alone would save.** The recorder's step model
(`gpu_draw_cost_model`, RR-0.1; Deck race at the cap, 3,800-4,600 draws a
frame, IssueDraw 1.5 µs a draw on `fr3p0`, 2.3 µs on `race-long`) splits a
draw's sampled time into steps. The ones only a merge removes (pipeline
bind, dynamic state, constants set, descriptor update and binds, the draw
command) are about 450-500 of 2,300 sampled ns, about 0.3 µs of real time
a draw. At 2.4x over the 1,189 host draws skip 7 removes, that is about
0.2 ms of recorder and at most about 1 ms of submission. The larger steps
(samplers, texture requests, targets, image infos, vertex residency) are
validation, which only a retained draw that skips its checks removes,
merged or not; DR-4.2 (+120 ns a draw) and NA-2.4 (even) found retained
draws that kept their checks no cheaper. So merging is worth about 1 ms;
what can carry the gate is retention: the render thread's and the
decoder's share of the owned draws, with the recorder and submission flat.

**Bindless textures don't help on the Deck.** ShiftGlue's bindless path
(PD-4, `vulkan_bindless_textures`, on by default only on Android), two
runs each on `fr3p0` at the cap: the texture steps halve (image infos 150
to 85 ns a draw, binds 72 to 37 ns), but IssueDraw stays at 1.5-1.6 µs a
draw, the recorder at 8.4-8.5 against 8.1-8.3 ms a frame, and the
submission thread rises from 3.2-3.3 to 4.5-5.6 ms (process CPU 55.9-58.0
against 52.7-55.5 ms). So any merging would plan on the 2.4x factor of
pipeline and textures, not the 4x of bindless.

**What a retained path needs.** The decoder's share goes only if the
recorder draws from captured records and the decoder never processes the
owned lists' register writes (90 % of its thread). Replaying the lists
through the decoder, as DL-2.1 and DL-3 did, keeps those writes, and that
is why they gained about 1 ms. G0 (NN-0.10, `gpu_replay_floor_probe`,
2026-10-13) is the one earlier probe that skipped the decode: it applied
the captured exit registers of any buffer whose bytes repeated and dropped
its draws, a wrong image, and on the Odin race saved 2.54 ms of process
CPU (decoder −1.68) against a 6 ms bar, with 42 % of drawn draws in
skippable buffers and 0.9 ms of its own hashing. M2 differs in its key
(the game's asset, so no hashing and the per-frame buffers covered) and
in drawing the records instead of dropping them. A retained path
therefore needs:

1. a game-side identity for the lists' draws, kept while the asset's list
   doesn't change (the command buffers carrying them are partly per frame);
2. insertion at the list's place in the stream, as DL-1.2's marker does;
3. records captured from a normal decode and handed to the recorder as
   they are, with the live parts (vertex fetch, which changes for about a
   tenth of the draws a frame, and memory-sourced constants) read again.

Slices, each behind a switch with the PM4 path as fallback:

| Slice | What | Kill line (Deck, in-run, capped) |
| --- | --- | --- |
| M2 | Model-asset lists retained at `824365B0` (main view, opaque): the guest writes a marker instead of running the list, and the decoder hands the recorder the list's captured records without decoding it | render thread and decoder −3.5 ms of skip 1's 5.0 with recorder and submission flat |
| M4 | The scene walk's other meshes and the cars (FR-3 complete), then shadows and reflections (FR-4) and sky, terrain, roads and HUD (FR-5) | FR-3's −6 ms, then FR-4 and FR-5 as their rows say |
| M1, M3 | Per-draw constant tables in translated shaders, then multi-draw batches by pipeline and textures | only if the last millisecond is needed: worth about 1 ms |

If M2 fails its line, FR-3 closes: merging can't add more than about
1.3 ms.

M2 failed its line before it was built: a replay of the same lists that
skips their decode and still records their draws (its floor) saves less
than the line on the Deck (next section).

## FR-3 M2: the retained path's ceiling on the Deck (2026-11-16)

M2 would replace the decode of the model-asset lists with records captured
from an earlier decode. G0's probe (`gpu_replay_floor_probe`) is the
cheapest form of that: it skips a buffer whose bytes repeat, applies the
captured exit registers and shaders, and drops the draws. Its result is a
ceiling for M2 once it is corrected for what differs: M2 would not hash
(add the probe's hashing back) and would still record its draws (take
their recording off).

All runs on the Deck, capped at 60, `pinyon_shift_native_scene_cull=true`,
single-pass scene on, `gpu_record_thread=false` on both sides (the probe
needs the decode and the recording on one thread, so the decoder column
holds both), 240-frame in-run windows from frame 4,600, 35 windows each.

**Coverage.** With the probe counting only (2 skips off) and `skip_world`
1 toggled in-run (`g0c`), skip 1 removed 500 host draws a frame and the
probe's skippable set fell from 747 to 218 drawn draws: the model-asset
draws M2 would own sit in buffers that repeat byte for byte and hold no
side effects, so G0 skips them, and a G0 ceiling covers M2.

**G0 toggled 0/2 in-run** (`g0-long`; `g0a` stopped at the title menu and
is left out). Host draws is the drop in `draw_calls` between the sides;
the decoder column holds decoding and recording:

| Run | Draws | Host draws | Process CPU | Render | Decoder | Submission | Hashing | Applying |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| g0b | 1,326 | −379 | −2.07 ± 2.21 ms | −0.52 ms | −0.55 ms | −0.64 ms | 0.76 ms | 0.87 ms |
| g0d | 2,841 | −1,147 | +0.09 ± 2.58 ms | −0.05 ms | −0.61 ms | −0.92 ms | 1.52 ms | 1.99 ms |
| g0e | 2,138 | −984 | −3.36 ± 3.54 ms | −0.21 ms | −1.82 ms | −0.95 ms | 1.01 ms | 1.41 ms |
| g0f | 1,952 | −816 | +0.01 ± 1.87 ms | −0.02 ms | −0.57 ms | −0.60 ms | 1.27 ms | 1.79 ms |
| g0g | 1,922 | −880 | −0.97 ± 1.77 ms | −0.12 ms | −0.85 ms | −0.76 ms | 1.20 ms | 1.87 ms |

**Skip 1 in the same layout** (`sw1-long`, record thread off): `g0c`
(with the probe counting, so less its hashing drop of 0.33 ms), `u1a` and
`u1b` took 1.71, 2.04 and 0.78 ms off the decoder thread for 500, 335 and
395 host draws. Recording a draw in this layout (`udc`, `race-long` with
`gpu_draw_cost_model`, gameplay band) costs 1.84-1.87 µs (IssueDraw).

**What this layout can't show.** With the record thread off, per host
draw: skip 1 removes 3.68 µs of decoding and recording (pooled, 1,230
draws), G0 without its hashing 2.42 µs (pooled, 4,206 draws), and
recording costs 1.84-1.87 µs (`udc`). That puts M2 at 25-31 % of skip 1's
decode share, but the shipping layout runs the recorder on its own thread,
where skip 1 takes 3.5-4.4 µs a host draw off the decoder alone, and M2
would hand that thread the decoder's entries instead of decoding again,
which G0 can't model. So the verdict comes from the same replay with the
record thread on.

**The replay in the shipping layout** (`gpu_replay_floor_probe` 3,
ShiftGlue): with the record thread on, a buffer that repeats byte for byte,
holds no side effects and records no calls has the record entries it
appended captured, with the decoder's exit registers and last shader
loads. A repeat appends the entries as they are and writes the exit state
to the decoder's shadow: its draws are recorded and drawn, the decode is
skipped. While a capture is open the decoder records every register write
and shader load and merges no constant runs, so the entries don't depend
on the state the buffer was entered in, as a retained list's can't.
Toggled 0/3 in-run on `m2p-long`; launches that stopped at the title menu
(`g0a`, `m2d`, `m2j`) are left out.

Earlier builds recorded the entries against the capture's entry state
(writes elided as unchanged, loads deduplicated, constant gaps filled with
the capture's values). Replayed into another state, those made the
recorder 0.3-2.8 ms slower and in two runs the frame missed the cap
(`m2a` to `m2i`, frame time up to +4 ms): the replay was drawing with
wrong state, so those runs size nothing. With complete entries the frame
held the cap in every run:

| Run | Draws | Replayed draws (decoded) | Process CPU | Decoder | Recorder | Submission | Hashing | Applying |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m2k | 2,104 | 1,900 | +0.80 ± 1.76 ms | −1.45 ms | +0.77 ms | +0.02 ms | 1.34 ms | 0.97 ms |
| m2l | 1,345 | 925 | +1.29 ± 2.76 ms | +0.29 ms | +0.60 ms | +0.17 ms | 0.83 ms | 0.44 ms |
| m2m | 1,336 | 847 | +1.35 ± 1.85 ms | +0.13 ms | +0.64 ms | +0.22 ms | 0.86 ms | 0.44 ms |
| m2n | 2,032 | 1,971 | +0.96 ± 1.88 ms | −0.84 ms | +1.05 ms | +0.17 ms | 1.34 ms | 0.92 ms |
| m2o | 1,301 | 850 | +0.41 ± 2.25 ms | +0.01 ms | +0.44 ms | +0.12 ms | 0.78 ms | 0.39 ms |

**Coverage.** With the replay on for a whole run and `skip_world` 1
toggled in-run (`r1a` to `r1c`, the earlier entry build), skip 1 removed
902-1,397 replayed decoded draws a frame: the model-asset lists M2 would
own are replayed.

Those runs replayed every repeating buffer, so their per-draw rates are
not the model-asset lists' rates. The deciding run measures skip 1 itself
with the replay off and on.

**The deciding run** (`f2s`, route `fact-long`): 240-frame windows from
frame 4,600 cycle skip 1 off and on, first with the replay off, then on,
so skip 1's effect is taken from adjacent windows under both. The capture
was stripped to what a retained list would record: it elides writes,
deduplicates shader loads and merges constant runs, but only against what
the same capture already wrote. A second launch (`f1s`) stopped at the
title menu. Skip 1's effect, 8-9 window pairs each:

| | Plain | With the replay |
| --- | --- | --- |
| Draws removed (decoded, host) | 440, 288 | 746, 460 |
| Decoder | −1.22 ms | −0.96 ms (hashing −0.32 ms) |
| Recorder | −0.98 ms | −1.39 ms |
| Submission | −0.47 ms | −0.54 ms |
| Process CPU | −2.61 ± 1.72 ms | −4.51 ± 1.93 ms |

With the replay on, what skip 1 still removes from the decoder (less the
hashing) is what the replay leaves of the lists: 0.85 µs a decoded draw
(1.37 µs a host draw) against plain decoding's 2.77 (4.22). The replayed
draws also cost the recorder and submission 0.72 µs a decoded draw (0.84 a
host draw) more than decoded ones. M2's line, at most 37 % of plain
decoding (the 63 % saving the kill line asks for, with recorder and
submission flat), is 1.02 µs a decoded draw (1.56 a host draw); the
replay's cost is 1.57 (2.21). The decoder alone would pass; the recorder
and submission excess, which this one run measures only roughly (about
±0.6 ms on those threads), takes it over the line by both measures. The
probe favours M2 on every other count: no hashing, no marker, no check
that the game hasn't rewritten a list, no live re-reads, and all of skip
1's render-thread share granted.

Why replayed draws cost the recorder more isn't established: the rise
was the same with entries recorded against the capture's state and with
complete ones (0.4-0.8 µs a replayed draw in the A/Bs above).

So a retained path that skips the decode can't reach FR-3's gate on the
Deck, and FR-3 closes with M1 and M3 (merging, about 1 ms). FR-4 and FR-5
close with it: their passes would use the same path, and the replay
skipped buffers from every pass of the frame. FR-6 closes because it
needs FR-3 to FR-5. The Odin wasn't re-run with a fixed v4 build; G0
failed there in October (NN-0.10). Runs: `g0b` to `g0g`, `u1a`, `u1b`,
`udc`, `f1b`, `f1c`, `r1a` to `r1c`, `m2a` to `m2o`, `f2s` under
`~/pinyon-qual/cg1071/runs` on the Deck.
