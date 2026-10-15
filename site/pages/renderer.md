---
title: Native renderer
section: Internals
order: 4
description: How Pinyon Shift renders Forza Horizon's GPU commands on Vulkan with a renderer written for this one game, from the PM4 stream to EDRAM, resolves, textures, shaders and the present.
---

# Native renderer

The Xbox 360 GPU, Xenos, draws into 10 MB of EDRAM and copies results out to main memory with explicit resolves. A general emulator has to model that for every game. Pinyon Shift began that way, with ReXGlue's Xenia-derived Xenos renderer, and ran this game at about 28 fps. It now uses the **FH1 native executor**, which handles only what this game does and runs the opening drive at the display's refresh rate.

## Why a game-specific renderer

The first step was a census of what the game actually sends the GPU, taken over 17,580 frames of scripted routes and later extended by 10,980 more ([NATIVE_FRAME_CONTRACT.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/NATIVE_FRAME_CONTRACT.md)):

| The game uses | Count |
| --- | --- |
| Render target configurations | 29, plus 11 from later routes |
| Resolve kinds | 20, plus 10 |
| Texture format and dimension pairs | 22 |
| Color targets per draw | one (no MRT) |
| Primitive types | strips, lists, quads, points, rectangles |
| Memory export draws | none |
| Front buffer | always 1280 × 720, 10:10:10:2 |

A bounded contract makes a renderer that handles exactly this set, and refuses anything else with a logged reason, a tractable project. A mode counts as covered only when its skip counters stay at zero over the routes.

The executor is specific to the game but not to its content: it has no shader hash lists, no checks on the game's own objects and no knowledge of particular scenes. An earlier attempt that rendered six draw "families" natively and left the rest to the emulated path was dropped. It ran at 91–95 ms a frame against 23.5 ms for the emulated path, and fell back on every frame of a race it hadn't seen.

Not everything was replaced. The per-draw translation of register state into pipelines, the constant buffer layout, the tiled texture cache and the shader translator are still Xenia-derived. The executor replaced render targets, EDRAM tiles, clears, resolves and the swap, and the emulated render target cache was deleted.

## Threads

{{diagram:renderer-threads|The command stream is decoded, recorded and submitted on three host threads.}}

Almost all of the game's draws arrive as `PM4_INDIRECT_BUFFER` packets that replay command buffers the game built in advance; 42 of about 5,000 draws a frame come from the game's immediate emitter, and 96 % of the indirect buffers are byte-identical from one frame to the next.

| Thread | Work |
| --- | --- |
| Guest render thread | the game's own D3D runtime writes PM4 packets |
| GPU Commands | decodes packets into a shadow register file, handles `WAIT_REG_MEM`, hashes microcode on load, and passes fixed-size records on |
| GPU Recorder | owns the real register state, the caches and the executor; derives pipelines and bindings for each draw and records a deferred command stream |
| GPU Submission | replays each stream into Vulkan (a submission every 1,024 draws) and calls `vkQueueSubmit`; also paints the present |
| GPU VSync | drives the guest vblank |
| Pipeline, shader and storage workers | build pipelines, translate shaders and write caches off the hot threads |

The decoder hands the recorder register runs (already byte-swapped), single registers, draws, shader loads, and callbacks for packets the CPU can observe. Ordering is the hard part: a race frame has about 280 event writes, 25–30 fence writes, 5 interrupts and one swap. Fence writes are recorded rather than waited for, so the game sees a fence only after the recorder has consumed everything before it. Memory writes, conditional writes, register-to-memory copies and occlusion queries wait for the recorder.

**Shader loads.** The decoder remembers each shader load by guest address and size while a write watch shows the microcode pages unwritten, so a repeated load skips rehashing the microcode and, where recording is inline (Android), the shader lookup too (`gpu_d3d_shader_cache`, on by default). On the Odin race 97 % of loads hit; six in-run A/Bs measured decoder CPU -0.50 ± 0.07 ms and process CPU -0.52 ± 0.27 ms a frame, with 0 mismatches against full hashing over 25.5 M loads.

Splitting decode from recording took the race from 17.67 ms to 16.46–16.75 ms a frame; the split left the decoder mostly idle, and the recorder became the limit at 1x. See [GPU optimizations](gpu-optimizations.md#the-recorder-thread).

## EDRAM and resolves

{{diagram:edram-resolves|Render targets reach textures through the guest-memory mirror, with a direct path into textures already in use.}}

**Surfaces.** A render target is a host image keyed by its EDRAM base tile, pitch, MSAA mode, depth or color, and format. Its address space runs to where EDRAM wraps (2,048 rows for a 1280-wide target), but the host image holds only the rows a draw, clear or resolve has reached: it starts at the first claim, rounded up to 128 rows, and grows by at least half when a later claim goes further, copying the old rows into the larger image. At 3x that took the race's 34 surfaces from 2.4 GB to 635 MB. A 2,048-tile owner map records which surface last wrote each tile and whether its stencil may be nonzero. When a draw claims tiles another surface owns, a **transfer** copies the old contents across: a pixel pass for color, and for depth a compute pass through a word buffer and back. Without `VK_EXT_shader_stencil_export`, which NVIDIA lacks, depth takes nine passes, one for depth and one per stencil bit. Transfers are limited by barriers, not pixels.

Some transfers can be proven unnecessary. For draws with depth test ALWAYS, or with no clipping, the executor runs the vertex shader on the CPU to bound what the draw covers. An unclipped stencil draw had claimed all 2,048 tiles.

**Resolves.** A resolve runs a compute shader that writes the **guest's tiled texture layout** into a host mirror of guest memory and marks that range as written by the GPU. Textures that overlap the range are invalidated, and the next fetch decodes them again in whatever format it asks for. That one mechanism covers partial resolves, several formats aliasing one address, and the CPU reusing the memory. Depth resolves reproduce the packed depth and stencil bits that later fetches read as `24_8` or `24_8_FLOAT`; the accepted differences are one LSB of D24S8 rounding and the low mantissa bits of float24.

Fast paths sit on top. A resolve also stores directly into textures that are already current, through raw-bits views, and reloads re-untile only the 32-row bands a resolve changed.

**CPU readbacks.** Resolves normally stay on the GPU. Traps on 117 and 154 resolved ranges found no CPU reads in two routes, with one exception: the car thumbnails. The game renders the car, resolves it and compresses it on the CPU. One-off resolves of 256 KiB or more, new or idle for seconds, are therefore copied back to guest RAM before the next command the CPU can observe, with one GPU wait per batch.

**Scaling.** Rendering runs at 1x to 4x the console's resolution, as whole multiples because the shader translator bakes the scale in. Surfaces hold scale × scale host pixels per guest pixel; transfers and resolves scale guest rectangles; and everything the guest can see keeps guest sizes. Resolves of 4 KB or less also write an unscaled copy, because the game reads its 32 × 32 luminance image at guest size for auto-exposure ([#444](https://github.com/arcanite24/pinyon-shift/issues/444)).

**Predicated tiling.** The game draws its 720p scene as three bands of 256, 256 and 208 rows, the Xbox 360 technique for fitting a frame into EDRAM. Merging them was rejected for the desktop because the game culls per band. An option draws the scene once and resolves the bands; it is on by default only on Android. The later bands' draws are then skipped; the command processor checks for that right after the draw's copy dispatch, before it derives the rest of the draw: on the Odin race that took the decoder's time per decoded draw down 7-8 % (about 0.7 ms a frame, in-run A/B).

**MSAA.** The game's 2x and 4x surfaces can be stored with fewer host samples: one per pixel (the desktop default) or two for the game's 4x. Resolves average samples 0–3 or take sample 0, as the guest asks.

## Textures

The texture cache reuses the Xenia-derived core over the executor's mirror. A texture's key comes from its fetch constant: base, format, size, pitch, tiling, mip range, endian mode and swizzle. Decoding runs in compute shaders that untile and byte-swap per format, covering DXT1/3/5, DXN, CTX1, DXT3A/5A, 10:11:11 and the 16-bit normalized and depth formats; a setting forces the BC decode path for devices without BC support.

**Invalidation.** CPU writes are found with page write-watches; GPU writes are marked by resolves. Ranges are told apart by a write generation per allocation, not by address. One setting mattered: clearing every touched page's state each frame re-uploaded memory that hadn't changed, and keeping it cut vertex uploads over a route from 41.6 GB to 0.42 GB.

**Size cap.** TEXTURE SIZE (`vulkan_texture_max_size`) gives a mipmapped texture larger than the cap a host image that starts at the first level that fits, so the larger levels are never untiled, uploaded or stored. Shaders address textures in normalized coordinates and the translator divides unnormalized fetches by the guest size, so a smaller image samples correctly, as texture replacements of another size already do. Resolve targets have no mips and keep their size. On a free-roam drive (RTX 4080, 1x) a cap of 256 took the texture cache from 110 to 85 MB and the device memory the renderer allocates from 882 to 756 MB, with no change in frame time.

**Gamma.** The console converts gamma textures with a piecewise-linear curve. The default reproduces it in the shader. TEXTURE GAMMA FAST samples through sRGB views instead, which is cheaper and slightly darker in the midtones.

## Shaders

The game's Xenos microcode is translated to SPIR-V by ShiftGlue's translator, which needed three fixes for this game: the texture exponent bias was read from the wrong fetch word, which darkened HDR fetches; a predicated forward jump is taken only when the whole pixel quad takes it, because derivatives inside one deadlocked an NVIDIA GPU; and cube fetches with derivatives use implicit LOD with a bias, because explicit gradients picked different cube mips and gave cars a green glow.

| Binding set | Contents |
| --- | --- |
| 0 | shared memory and EDRAM |
| 1 | five uniform buffers with dynamic offsets: system, vertex float, pixel float, bool and loop, fetch constants |
| 2 | vertex textures |
| 3 | pixel textures, as push descriptors, or bindless on Android |

**Avoiding compile stalls.** Translated shaders and pipeline descriptions are stored between runs, and the driver's `VkPipelineCache` is saved too. Setup plays a short preparation route hidden, about two minutes, so the first real launch finds both filled. With an empty driver cache that cut frame time over budget from 13.0 s to 5.7 s and the worst frame from 1.35 to 0.53 s. Measured again on the October 13 build, on the RTX 4080: 9.1 s over budget after preparation and 2.35 s with every pipeline of the route already stored. Every frame over 100 ms in the first case came with a burst of pipeline creations at the two moments new content appears, entering the world and loading the race: 233 pipelines that preparation hadn't reached, 137 with a shader no earlier pipeline used, 96 with known shaders but a new render pass or blend state. Pipelines are built on workers, never on the command threads. On the desktop a draw whose pipeline isn't ready waits up to 250 ms for it; Android skips the draw.

A shader pack format (`.pnsp`, 112-byte header, 88-byte entries keyed by stage, guest hash and specialization, SHA-256 per entry) can carry translations ahead of time; on Vulkan it is optional. A corpus tool reads the game's own `.fxobj` files from the disc for 3,349 unique programs, 11,726 with vertex declaration variants. Packs are local files and never published.

## Present

The swap resolve writes the front buffer into the mirror; the presenter applies the game's gamma ramp and optional FXAA, then scales the image with bilinear filtering, CAS or FSR 1. FXAA and the player's colour LUT run on the scene only: before the first HUD draw (a draw into the front buffer's `2_10_10_10_AS_10_10_10_10` view after the scene composite) the renderer copies the scene, and a compute pass changes only the pixels the HUD left equal to that copy. The same HUD boundary scales HUD draws for the HUD scale and safe zone, and keeps the player's anisotropy and LOD bias off HUD and depth-only (shadow) draws: on a free-roam route at 16x, 150,000 of 3.38 million draws were depth-only with textures and 49,000 HUD draws. On an RTX 4080 at 3x, uncapped, the scene-only pass cost nothing measurable: the median frame was 8.96 ms without AA and 9.10 ms with scene-only FXAA, toggled inside one free-roam route, within that route's noise.

**HDR.** On Windows the swapchain is scRGB, `R16G16B16A16_SFLOAT` in extended sRGB linear. On Android it is HDR10: the last pass converts to BT.2020 and encodes with the PQ curve. Android treats scRGB 1.0 as SDR white and clips above it unless the app asks for headroom (Android 14 and later), so a 200-nit paper white pushed the whole image into that clip ([#500](https://github.com/arcanite24/pinyon-shift/issues/500)). Android 13 offers Vulkan no HDR10 color space at all, so the game takes a 10-bit swapchain and marks the window's buffers BT.2020 PQ itself, and sends HDR10 metadata with the levels `Display.getHdrCapabilities()` reports, so the panel shows the image as is and clips at its own peak instead of tone-mapping it from an assumed brighter master. The HDR swapchain is also pre-rotated to the panel's orientation (the Odin 2 Portal's panel is portrait): the compositor's rotation only takes 8-bit buffers and tone-mapped HDR10 to SDR before it, which had washed the image out. The SDR frame is decoded with gamma 2.2, 2.4 or sRGB and scaled to the chosen paper white (200 nits by default); scene highlights expand toward the display's peak. To keep the HUD at paper white, the executor snapshots the scene before the first HUD draw, and a compute pass marks changed pixels in the output's 2-bit alpha.

**Ultrawide.** A guest hook widens the main view's aspect by the window's aspect over 16:9, so the game's culling matches the wider view; scaling the projection on the host was abandoned because culling disagreed. Draws into the front buffer's HUD view are squeezed back to 16:9, and menus and the map are letterboxed.

**Pacing.** See [late swaps](gpu-optimizations.md#frame-pacing).

## Testing

Renderer changes are judged against scripted routes, not by playing:

- **Routes.** `tools/run-fh1-render-test.py` runs `.fh1test` scripts against a pinned save with a synthetic controller: waits on game state, key presses, setting changes, memory pokes, captures, and expectations on images (MAE, RMSE, changed-pixel ratio against a baseline) and performance.
- **Frame dumps.** One frame's packets, starting registers, shaders and every guest range it reads can be dumped and replayed with the game suspended. Vulkan replays are bit-exact, and the same dump replays on any device. Replaying one free-roam frame on the Odin and the desktop, with every resolve dumped, found the first difference at resolve 9, which led to a Qualcomm push-descriptor bug.
- **Validation.** The Khronos validation layer, including synchronization validation, found the AMD device loss in 0.4.0: the recorder waited on fences the submission worker hadn't submitted yet. It also found a query ended inside a rendering, a shared present semaphore and a wrong storage view type.
- **Bisection switches.** Skip draws, null fetches, log draws, dump resolves, and label work for Nsight.

Rules that held: judge final frames, not intermediate targets; never run against the real save; and after two inconclusive trials on one gap, re-rank rather than try a third time.
