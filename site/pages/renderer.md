---
title: Native renderer
section: Internals
order: 4
description: How Pinyon Shift renders Forza Horizon's GPU commands on Vulkan with a renderer written for this one game, from the PM4 stream to EDRAM, resolves, textures, shaders and the present.
---

# Native renderer

The Xbox 360 GPU, Xenos, draws into 10 MB of EDRAM and copies results out to main memory with explicit resolves. A general emulator has to model that for every game. Pinyon Shift began that way, with ReXGlue's Xenia-derived Xenos renderer, and ran this game at about 28 fps. It now uses the **FH1 native executor**, which handles only what this game does and runs the opening drive at the display's refresh rate.

## Why a game-specific renderer

A standalone driver probe found that an extension name alone is not enough
to plan a GPU-driven front end. On the reference Deck's RADV 24.3-devel,
`VK_EXT_device_generated_commands` is available, but execution-set pipeline
binding supports compute only. The Odin's installed Turnip V37 exposes
neither EXT nor NV DGC. NVIDIA 581.08 supports graphics execution sets;
the M4 Pro accepts a native Metal render ICB with per-command pipelines,
but MoltenVK 1.4.1 exposes neither Vulkan DGC extension. This leaves the
proposed graphics front end blocked on the yardstick drivers. Per-pipeline
indirect draws remain unmeasured: the existing frame census aggregates
configurations and discards the order needed to count pipeline runs.
Comparing DGC with a tight recorder on one pass (#754) was dropped with
the pass's owned draw programs: that pass's whole CPU cost is
0.08-0.18 ms a frame (126-190 draws at 650-960 ns), below what an in-run
frame A/B resolves, and DGC would only move part of it. See the
[Stage 0 device table and method](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/CLEAN_SLATE_STAGE0.md#cs-03-driver-capabilities).

The separate placed-mapping probe succeeded on both yardsticks: a 512 MiB
coherent Vulkan allocation mapped at a reserved fixed address, and a
compute shader verified every CPU-written word with zero mismatches.
Turnip's type was device local; RADV's selected type was system/GTT memory.
This establishes placement support. Guest aliases remain untested, and the
completion-latency result below rejects the shared-arena proposal at its gate.
[CS-0.5 records the method and negative controls](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/CLEAN_SLATE_STAGE0.md#cs-05-placed-device-memory-mapping).

The asynchronous completion probe failed the latency gate too. An experimental
build (`REXGLUE_ENABLE_CS_PROBES=ON`, default OFF) provides the default-off
mode (`gpu_async_fence_probe` at startup, `gpu_async_fence_completion` hot). It
ends the submission at each guest fence and signals a timeline value behind
it. A completion thread waits and publishes the guest result; the producer
never waits on that semaphore. On the same pinned race/free-roam routes at
1x, Odin means rise 16.666→20.942 /16.692→21.885 ms; Deck
16.800→38.162 /16.875→37.462 ms. All p99s worsen. A/A mean shifts stay under
0.57%. This rejects CS-4 at its stated 3%/unchanged-p99 gate; placed mapping
support does not compensate for this cost. The earlier synchronous drain
is separate historical evidence. The mirror remains in use.
[Builds, timeline counts and controls](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/CLEAN_SLATE_STAGE0.md#cs-04-asynchronous-timeline-completion).

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

The decoder hands the recorder register runs (already byte-swapped), single registers, draws, shader loads, and callbacks for packets the CPU can observe. Ordering is the hard part: a race frame has about 280 event writes, 25–30 fence writes, 5 interrupts and one swap. By default, fence writes are recorded rather than waited for, so the game sees a fence only after the recorder has consumed everything before it. Memory writes, conditional writes, register-to-memory copies and occlusion queries wait for the recorder.

**Shader loads.** The decoder remembers each shader load by guest address and size while a write watch shows the microcode pages unwritten, so a repeated load skips rehashing the microcode and, where recording is inline (Android), the shader lookup too (`gpu_d3d_shader_cache`, on by default). On the Odin race 97 % of loads hit; six in-run A/Bs measured decoder CPU -0.50 ± 0.07 ms and process CPU -0.52 ± 0.27 ms a frame, with 0 mismatches against full hashing over 25.5 M loads.

Splitting decode from recording took the race from 17.67 ms to 16.46–16.75 ms a frame; the split left the decoder mostly idle, and the recorder became the limit at 1x. See [GPU optimizations](gpu-optimizations.md#the-recorder-thread).

## EDRAM and resolves

{{diagram:edram-resolves|Render targets reach textures through the guest-memory mirror, with a direct path into textures already in use.}}

**Surfaces.** A render target is a host image keyed by its EDRAM base tile, pitch, MSAA mode, depth or color, and format. Its address space runs to where EDRAM wraps (2,048 rows for a 1280-wide target), but the host image holds only the rows a draw, clear or resolve has reached: it starts at the first claim, rounded up to 128 rows, and grows by at least half when a later claim goes further, copying the old rows into the larger image. At 3x that took the race's 34 surfaces from 2.4 GB to 635 MB. A 2,048-tile owner map records which surface last wrote each tile and whether its stencil may be nonzero. When a draw claims tiles another surface owns, a **transfer** copies the old contents across: a pixel pass for color, and for depth a compute pass through a word buffer and back. Without `VK_EXT_shader_stencil_export`, which NVIDIA lacks, depth takes nine passes, one for depth and one per stencil bit. Transfers are limited by barriers, not pixels.

Some transfers can be proven unnecessary. For draws with depth test ALWAYS, or with no clipping, the executor runs the vertex shader on the CPU to bound what the draw covers. An unclipped stencil draw had claimed all 2,048 tiles.

**Resolves.** A resolve runs a compute shader that writes the **guest's tiled texture layout** into a host mirror of guest memory and marks that range as written by the GPU. Textures that overlap the range are invalidated, and the next fetch decodes them again in whatever format it asks for. That one mechanism covers partial resolves, several formats aliasing one address, and the CPU reusing the memory. Depth resolves reproduce the packed depth and stencil bits that later fetches read as `24_8` or `24_8_FLOAT`; the accepted differences are one LSB of D24S8 rounding and the low mantissa bits of float24.

Fast paths sit on top. A resolve also stores directly into textures that are already current, through raw-bits views, and reloads re-untile only the 32-row bands a resolve changed.

**CPU readbacks.** Resolves normally stay on the GPU. Traps on 117 and 154 resolved ranges originally found only car-thumbnail CPU reads in two routes: the game renders the car, resolves it and compresses it on the CPU. One-off resolves of 256 KiB or more, new or idle for seconds, are copied back to guest RAM before the next command the CPU can observe, with one GPU wait per batch. A later M1 Max trace also found CPU reads of the 4 KiB float luminance resolve used for exposure. Completed `32_FLOAT` resolves of at most 4 KiB are read back too (`fh1_readback_small_float_resolves`); above 1x they first need the unscaled GPU copy. They happen every frame, so they do not share the one-off queue and its GPU wait: each is copied into a small ring and written to guest RAM once its submission has completed, a frame or two late. Waiting for them cost 1.5–1.8 ms of fence waits a frame on the Windows desktop; the deferred copy measured no frame-time difference against no readback in an in-run A/B. This complements the 4 KiB validity tracking that keeps unrelated CPU writes from discarding the GPU copy.

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

**Avoiding compile stalls.** Translated shaders and pipeline descriptions are stored between runs, and the driver's `VkPipelineCache` is saved too. Setup plays a short preparation route hidden, about two minutes, so the first real launch finds both filled. With an empty driver cache that cut frame time over budget from 13.0 s to 5.7 s and the worst frame from 1.35 to 0.53 s. Measured again on the October 13 build, on the RTX 4080: 9.1 s over budget after preparation and 2.35 s with every pipeline of the route already stored. Every frame over 100 ms in the first case came with a burst of pipeline creations at the two moments new content appears, entering the world and loading the race: 233 pipelines that preparation hadn't reached, 137 with a shader no earlier pipeline used, 96 with known shaders but a new render pass or blend state. Pipelines are built on workers, never on the command threads. On the desktop a draw whose pipeline isn't ready is recorded anyway with a pending bind, and the submission's replay waits for the pipeline (up to 250 ms, then it leaves those draws out): every pipeline a frame needs is then requested at once and built in parallel. Waiting at each draw instead built them one at a time, 3-4 ms each on the RTX 4080, and a scene with 20 new pipelines held the frame for their sum. Android skips the draw.

A shader pack format (`.pnsp`, 112-byte header, 88-byte entries keyed by stage, guest hash and specialization, SHA-256 per entry) can carry translations ahead of time; on Vulkan it is optional. A corpus tool reads the game's own `.fxobj` files from the disc for 3,349 unique programs, 11,726 with vertex declaration variants. Packs are local files and never published.

## Present

**Reconfiguration.** VSYNC, fullscreen and HDR reuse one swapchain retirement path. It waits for submitted draws and drains the presentation queue under its host-access lock before releasing the old framebuffers and presentation semaphores. Draw fences alone do not cover presentation waits. Image acquisition uses a 50 ms timeout so a surface that stops progressing can return control to the UI or submission worker. Presenter submit device loss follows the GPU-loss reporting path, with the numeric Vulkan result in the log. The queue-idle fallback has the limitations described in the [qualification method](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DEVELOPMENT.md); the separate reporter failures still need their own hardware checks.

The swap resolve writes the front buffer into the mirror; the presenter applies the game's gamma ramp and optional FXAA, then scales the image with bilinear filtering, CAS or FSR 1. FXAA and the player's colour LUT run on the scene only: before the first HUD draw (a draw into the front buffer's `2_10_10_10_AS_10_10_10_10` view after the scene composite) the renderer copies the scene, and a compute pass changes only the pixels the HUD left equal to that copy. The same HUD boundary scales HUD draws for the HUD scale and safe zone, and keeps the player's anisotropy and LOD bias off HUD and depth-only (shadow) draws: on a free-roam route at 16x, 150,000 of 3.38 million draws were depth-only with textures and 49,000 HUD draws. On an RTX 4080 at 3x, uncapped, the scene-only pass cost nothing measurable: the median frame was 8.96 ms without AA and 9.10 ms with scene-only FXAA, toggled inside one free-roam route, within that route's noise.

**Temporal upscalers.** Upscalers are providers behind one interface: each reports its id, version, quality modes and the inputs it uses, and gets a per-frame input set (colour, depth, motion vectors, masks, jitter, frame delta, history reset). FSR 2 and FSR 3 run through the FidelityFX API from a library loaded at run time; one library (1.1.4) carries both FSR 3.1.4 and 2.3.3, and each provider pins its version. On Windows it is AMD's signed runtime. On Linux, Android and macOS the build compiles the same library from source (ShiftGlue `thirdparty/fidelityfx-vk`) and ships it beside the game or in the APK. The SDK generates its Vulkan shaders only with a Windows tool, so the build carries that tool's output for the pinned commit, checked by hash. Two of the SDK's Vulkan backend assumptions failed off Windows and are patched at configure time: an `alignas(32)` context placed at 4-byte offsets crashed under clang, and on unified-memory GPUs no memory type passed its device-local test. Static scene, 1280 × 720 to 1920 × 1080: on the Odin 2 Portal (Adreno 740) the upscale takes 4.7 ms of GPU time with FSR 2 and 5.8 ms with FSR 3 (median frame 17.7 and 18.6-19.2 ms against FSR 1's 16.7 ms); on the M4 Pro FSR 3 takes 5.0 ms at a 3840 × 2160 output; on a Steam Deck docked at 1080p it takes 10-14 ms and the frame grows to 26-28 ms, so FSR 1 stays the choice there. On the Deck's own screen at 1x the output is no larger than the render and the temporal path does not run ([UPSCALING_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/UPSCALING_BACKLOG.md) UP-2.1). They dispatch once per new game frame (a repaint shows the last upscale), with the measured frame delta, and drop their history only when the sizes or the output change. They never see the HUD: the swap also writes a copy of the frame without it, from the scene the executor snapshots before the first HUD draw (the one HDR uses) put through the same gamma ramp, with the HUD's coverage in its alpha. The upscaler gets that copy, and a compute pass then draws the frame with the HUD, upscaled bilinearly, wherever the coverage is set, so the HUD keeps sharp edges and leaves no trails in the upscaler's history. Under translucent HUD elements the scene is the bilinear one. `present_upscaler_hud=debug` shows the HUD-less input, `off` feeds the frame with the HUD as before. Screens without a scene snapshot, such as menus, are all HUD and go to the upscaler whole.

**Depth and camera motion for upscalers.** The game has no motion vectors, so they are built from its own draws. Scene vertex shaders read each object's world-view-projection matrix from four constant registers, and the static world shares one matrix, so the executor takes the largest group of draws with equal matrices as the world and matches its objects with the previous frame's. For geometry that did not move, the previous matrix times the inverse of the current one is the camera's motion; the same matrix gives the field of view and the near and far planes. A frame with nothing to match, or a jump, is a camera cut and drops the upscaler's history. The scene depth is copied band by band as each predicated tile is resolved, and a compute pass at the swap writes the depth and per-pixel camera motion beside the HUD-less copy. The scene turned out to be drawn turned 180 degrees with reversed depth, which the pass undoes ([rendering findings](game-rendering.md)). With these inputs FSR 3 keeps trees, road markings and rails sharp on a drive route that it otherwise smears (RTX 4080, 1280x720 to 3840x2160). Moving objects get their own motion: draws that write the scene's depth also write a per-object slot into a full-frame integer image, the nearest fragment winning through an atomic max, and the swap pass reprojects each pixel with its slot's previous-times-inverse-current matrix wherever the slot's depth is the pixel's. Cars needed their own rules, since they read their matrix from different constants than the world and draw to another colour target; they also had never been jittered, which had left their edges stair-stepped under FSR 3 ([rendering findings](game-rendering.md), [UPSCALING_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/UPSCALING_BACKLOG.md) UP-1.7). On the drive route the player's car now comes out still in the chase camera, with clean edges, at no change in median frame rate. The slot-writing shaders are variants, so their pipelines are new even when the player's pipeline cache is warm; a draw binds the base pipeline, with camera motion, until its variant is built, instead of waiting for it (waiting had stalled DLSS frames by up to a second in new areas); `present_upscaler_object_motion=false` turns it off. `present_upscaler_view=depth` or `motion` shows the inputs instead of the upscale; `present_upscaler_camera=false` turns them off.

**Jitter.** While a temporal upscaler runs, the scene is drawn with a different sub-pixel offset each frame, a Halton(2, 3) sequence of 8 samples per output pixel, added to the viewport of the scene draws placed by the camera matrix only, so shadows, post passes, screen-space passes inside the scene and the HUD stay still (a screen-space pass moved by half a pixel left a flickering column of stale colour at the screen edge). The offset goes to the upscaler with the frame. Against a native 3x render of a still scene, FSR 3 at 3x gained 2.2 to 5.2 dB of PSNR on static regions over the same upscale without jitter, and lost the grid pattern of an unjittered upscale. The game's MSAA is already off by default (`fh1_msaa_single_sample`). `present_upscaler_jitter=false` turns jitter off.

**DLSS.** Windows builds also have DLSS Super Resolution through NVIDIA's NGX on Vulkan, fed the same inputs, shipped with NVIDIA's approval. At configure time CMake downloads NGX's headers, its static loader and `nvngx_dlss.dll` from NVIDIA's pinned DLSS 310.9.16 commit, checks each by SHA-256, and stages the DLL with NVIDIA's licence in `upscalers/dlss/310.9.16/`; NGX loads the newest version folder there ([LEGAL.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/LEGAL.md)). The Windows FSR 2 and 3 runtime is AMD's signed `amd_fidelityfx_vk.dll` from the same pinned FidelityFX SDK 1.1.4 commit the other platforms build from, staged in `upscalers/fidelityfx/1.1.4/`. On the still scene at 3x on an RTX 4080, DLSS 310.9.16 came 0.1 to 0.6 dB closer to a native 3x render than FSR 3.1.4, with visibly finer foliage. `present_dlss_preset` hints a preset (J, K, L, M). The game's motion blur and depth of field, off by default, also stay off while a temporal upscaler runs even if turned on, because they smear what the upscaler accumulates. There are no reactive masks for particles or glass yet: the drive captures show no ghosting from them. On an RTX 4080, upscaling 1280x720 to 3840x2160 took 0.72 ms of GPU time with FSR 3.1.4 and 0.675 ms with FSR 2.3.3 (GPU timestamps around the dispatch, mean of 300 upscales on a free-roam route).

**HDR.** On Windows the swapchain is scRGB, `R16G16B16A16_SFLOAT` in extended sRGB linear. On Android it is HDR10: the last pass converts to BT.2020 and encodes with the PQ curve. Android treats scRGB 1.0 as SDR white and clips above it unless the app asks for headroom (Android 14 and later), so a 200-nit paper white pushed the whole image into that clip ([#500](https://github.com/arcanite24/pinyon-shift/issues/500)). On the Android 13 Odin 2 Portal, Vulkan offers no HDR10 color space, so the game takes a 10-bit swapchain and marks the window's buffers BT.2020 PQ itself, and sends HDR10 metadata with the levels `Display.getHdrCapabilities()` reports, to avoid assuming a brighter master. Those advertised levels and the metadata do not guarantee that every Android compositor preserves the PQ signal: Astra calibration is still unqualified ([#566](https://github.com/arcanite24/pinyon-shift/issues/566)). The HDR swapchain is also pre-rotated to the panel's orientation (the Odin 2 Portal's panel is portrait): the compositor's rotation only takes 8-bit buffers and tone-mapped HDR10 to SDR before it, which had washed the image out. Calibration clears the guest image and its HUD mask before drawing the host UI, and temporarily suspends the SDR/HDR comparison: either could otherwise cover the chart, even on a title-menu frame. On the Odin 2 Portal with SYSTEM and Turnip, the paper-white chart has identical captured pixels with compare on or off ([method and limits](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/ANDROID.md#hdr-calibration)). The SDR frame is decoded with gamma 2.2, 2.4 or sRGB and scaled to the chosen paper white (200 nits by default); scene highlights expand toward the display's peak. To keep the HUD at paper white, the executor snapshots the scene before the first HUD draw, and a compute pass marks changed pixels in the output's 2-bit alpha.

**Ultrawide.** A guest hook widens the main view's aspect by the window's aspect over 16:9, so the game's culling matches the wider view; scaling the projection on the host was abandoned because culling disagreed. Draws into the front buffer's HUD view are squeezed back to 16:9, and menus and the map are letterboxed.

**Pacing.** See [late swaps](gpu-optimizations.md#frame-pacing).

## Testing

Renderer changes are judged against scripted routes, not by playing:

- **Routes.** `tools/run-fh1-render-test.py` runs `.fh1test` scripts against a pinned save with a synthetic controller: waits on game state, key presses, setting changes, memory pokes, captures, and expectations on images (MAE, RMSE, changed-pixel ratio against a baseline) and performance. With `present_capture_readable`, each capture also saves the presented image, after the upscaler, which is what upscalers are compared on.
- **Frame dumps.** One frame's packets, starting registers, shaders and every guest range it reads can be dumped and replayed with the game suspended. Compare a replay with a saved replay golden for exact regression checks; matching the original live frame is not guaranteed. The [desktop inspector](modding.md#frame-inspector) reports that comparison and previews surfaces and resolve sources. The same dump can be replayed on other devices: comparing one free-roam frame on the Odin and the desktop, with every resolve dumped, found the first difference at resolve 9, which led to a Qualcomm push-descriptor bug.
- **Ordered frame census.** An optional Vulkan-only build (`REXGPU_FH1_ORDERED_CENSUS=ON`, default OFF) records the selected pipeline per emitted guest draw and host rendering instance. A Steam-launched 60-second Deck race contains 3,560 frames: 1,147.42 within-pass pipeline changes/frame and 2.5165 draws/run (median 1, p95 6). The stream has no overflow or missing output mappings. These counts do not establish batching legality or a saving. [Method and counts](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/CLEAN_SLATE_STAGE0.md#cs-03-ordered-pipeline-runs-on-the-deck).
- **Validation.** The Khronos validation layer, including synchronization validation, found the AMD device loss in 0.4.0: the recorder waited on fences the submission worker hadn't submitted yet. It also found a query ended inside a rendering, a shared present semaphore and a wrong storage view type.
- **Bisection switches.** Skip draws, null fetches, log draws, dump resolves, and label work for Nsight.

Rules that held: judge final frames, not intermediate targets; never run against the real save; and after two inconclusive trials on one gap, re-rank rather than try a third time.
