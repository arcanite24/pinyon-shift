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

| Part | Full frame | Scene walk skipped (`pinyon_shift_debug_skip_world` 7) |
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

**Next design (FR-3b):** test each item's box in the game's own per-pass
culling (`824400B0`, which our native version runs on Linux) against a
small max-depth grid of an earlier frame's main view:

- The executor reduces the scene depth to tiles in one compute pass after
  the main scene and copies the grid into a host-visible ring, 2-3 frames
  deep.
- The native culling projects the box with that frame's view-projection
  and drops the item from the view passes when every tile it covers is
  nearer than the box.
- The shadow passes are left alone.
- Still needed: the view's projection matrix on the guest side, the guest
  depth convention, and which views count as the main scene.

## FR-3: what is still unknown

- **Who reads the per-pass buckets.** The pass culling pushes 20-byte
  records onto five buckets per pass at `[r3+13844] + (pass × 5 + bucket) ×
  16` (`site/findings/rendering.toml`, "per-draw pass culling"). Offset
  13844 is also stored by D3D's constant flush (`82408B70`, `8240DC70`), so
  `r3` there is the device-side renderer object. Its bucket readers are not
  found yet: no generated function loads 13844 other than the culling, the
  walk and a setter (`82461978`). The readers likely take the bucket base
  from a register or a copy.
- What a record's object holds: mesh, vertex and index buffers, material,
  constants. Then how the game binds a material per draw: the
  `CD3D9GraphicsDevice` slots.
