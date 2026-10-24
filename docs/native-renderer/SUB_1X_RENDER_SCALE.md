# Rendering below 1x: feasibility and GPU prize

Research wave R02, 2026-10-24. Code inspected at Pinyon `34e2f00c`,
ShiftGlue `102fe952`. This is a design and an archival measurement analysis;
it adds no renderer setting or implementation. NP-4.8 and LS-1.8 remain open.

**Decision:** defer the prototype. A fixed 0.5x mode is substantially narrower
than arbitrary percentages, but it still crosses the executor, EDRAM
conversion shaders, shader-pack contract and presentation inputs. Budget
roughly 10–15 engineer-days for that implementation, then 3–5 days for the
image and device matrix. These are planning estimates, not measured build
times. The 25% Odin gate has not been tested.

The Odin was unavailable on October 24: `adb devices -l` and `adb mdns
services` were empty; the saved `192.168.1.198:41569` endpoint and port 5555
refused connections. The device lock was released without installing or
changing anything. The prize below comes from an existing October 13 Odin
capture, not a fresh run of the wave-R pin.

## Existing implementation and integer assumptions

Paths in this table are relative to the SDK unless prefixed with `Pinyon`.
Line numbers refer to the inspected pins. Sizes estimate work for a fixed
half-scale compatibility prototype; adjacent tasks overlap.

| Piece | Existing contract and work needed | Size |
| --- | --- | --- |
| Setting and lifecycle | `src/graphics/pipeline/texture/cache.cpp:341` clamps integer X/Y scales to at least 1, and Android to 1 unless explicitly overridden. `include/rex/graphics/pipeline/texture/cache.h:75` defines scaled as greater than 1. `src/graphics/vulkan/command_processor.cpp:2672` already switches integer scale between frames by rebuilding scaled components. Pinyon's settings and config tools expose integers. Add a separate, explicit half-scale mode; do not overload integer zero. | S, 0.5–1 day |
| Executor surfaces and rectangles | `src/graphics/vulkan/fh1_native_executor.cpp:448` stores an unsigned scale. `HostRect` at 695, image creation at 887, growth/copies at 1000 and target binding at 2415 multiply guest dimensions by it. `include/rex/graphics/fh1_edram_surfaces.h:76` divides the host limit by it. Keep surface keys, guest pitch, ownership and EDRAM periods in guest units; introduce a separate guest-to-host mapping for image extents, viewport, scissors, clears, copies and inspectors. | M, 2–3 days |
| EDRAM reinterpretation and resolves | `TransferFlags` at executor line 700 encodes `scale - 1` in two bits; resolve constants do so at 2818. `src/graphics/shaders/fh1_native_edram.hlsli:83` maps each guest pixel to an integer block of host pixels, including relocated color/depth/MSAA aliases. `fh1_native_resolve_memory.cs.hlsl:124` expands each guest 16-byte group into integer scale-squared groups. A fraction cannot be represented by changing a float at the call site. Both same-layout and relocated source lookups need a defined half-resolution sampling rule. | L, 3–5 days |
| Texture storage and aliasing | Executor line 3161 uses ordinary guest memory at 1x and the scaled resolve buffer above 1x. `src/graphics/vulkan/texture_cache.cpp:3397` maps an address range by multiplying its byte address and length by integer scale area; image creation at 1765 and swap dimensions at 1572 do likewise. Fractional compact storage needs new range/layout rules, texture identity, partial updates, validity tracking, direct-resolve views and reflection imports. The compatibility prototype below deliberately keeps these textures at guest size. | Included in resolve work for compatibility; L additional work for compact storage |
| CPU-visible outputs | Executor lines 3296–3329 preserve an unscaled copy for one-off readbacks and resolves of at most 4 KiB; small float readbacks use a deferred ring. At a fraction there are fewer source pixels, so “first host pixel of every guest pixel” no longer applies. Reconstruct the entire guest-sized destination with valid pitch, format, endianness, extent and padding before the existing readback queues see it. Qualify thumbnails and the 32×32 luminance output independently. | M, 1–2 days |
| Predicated tiling | `src/graphics/vulkan/command_processor.cpp:9388` adjusts viewport/window offsets and scissors using integer scale. Executor lines 783–815 handle the untiled surface's copy-down; resolve line 3281 carries its guest-row band. Preserve guest bin predicates and three bands; convert their endpoints once. Android's merged path and desktop's band path both need coverage. | M, 1–2 days |
| Guest shaders and offline packs | `src/graphics/pipeline/shader/spirv_translator.cpp:3473` and 3509 convert pixel-position parameters using reciprocals only above 1x; memexport handling at 3158/3360 also assumes integer expansion. `include/rex/graphics/fh1_shader_pack.h:43` and Pinyon `tools/native-shader-pack.py:138` store nonzero unsigned scales. A 1x pack does not make fragment coordinates correct at half scale. Add a distinct translation flag/cache identity and generate the half-mode pack offline, including pixel-center and memexport policy; retain the integer scale fields at 1 for the compatibility memory path. | M, 1–2 days |
| Presentation and upscalers | `RequestSwapTexture` reports integer-scaled dimensions today. `src/graphics/vulkan/fh1_camera.cpp:553` assembles depth bands with the same scale; row offsets and HUD snapshots also use it. The presenter's `DispatchTemporalUpscale` at `src/ui/vulkan/vulkan_presenter.cpp:580` already accepts actual source/output dimensions and resets history on size changes. Supply matching low-resolution color, HUD coverage, depth, motion-vector units and jitter; keep the 1280×720 guest video mode. FSR/DLSS do not repair mismatched input grids. | M, 1–2 days |
| Qualification | Race and driving routes, both tiling modes, all resolve kinds, exposure, HUD, bloom, shadows, reflections, thumbnails and reload; hot-switch cleanup and temporal-history reset. | L, 3–5 days after implementation |

The renderer already has integer 1x–4x scaling and scale switching, direct
resolve-to-texture writes, guest-sized readbacks, and spatial/temporal output
upscalers. None provides rendering below the console's resolution. The
[frame contract](NATIVE_FRAME_CONTRACT.md) remains the correctness boundary.
The existing [rendering records](../../site/findings/rendering.toml) describe
predicated tiling, depth-as-color resolves and luminance; the
[save records](../../site/findings/saves.toml) describe car thumbnails. This
study establishes no new guest addresses or function contracts.

## Cheapest fixed mode versus arbitrary percentages

Start with **0.5x**, or 640×360 for the 1280×720 scene. A two-state mapping
(native/half) makes coordinate conversion and shader variants bounded.
The ordinary band heights 256, 256, 208 become 128, 128, 104. Even then,
partial rectangles and small targets may have odd endpoints: derive image
extent and rectangle endpoints with one shared floor/ceil policy, clamp
nonempty images to at least one texel, and test adjoining coverage. Do not
scale the guest's EDRAM pitch or change its tiling predicates.

Two thirds is less convenient: 1280×2/3 is not an integer, and the 80×16
EDRAM sample tile does not map to integer host dimensions. A 0.75x mode
(960×540) has cleaner common extents, but less potential to meet the gate.
Any arbitrary-percent path needs a numerator/denominator or equivalent
mapping throughout, rounding of every partial range, per-texture physical
dimensions, pack/cache identities and policies for changing those dimensions.
Dynamic resolution adds resource reuse and temporal-history policy on top.

Two implementation choices should remain distinct:

1. **Compatibility prototype, recommended first.** Keep the public integer
   scale and texture/memory layout at 1x. Rasterize executor images at half
   size. Resolve each full guest destination by sampling the mapped
   low-resolution source, so existing untile, alias and CPU paths receive
   complete guest-sized data. Initially use an explicit nearest-sample rule
   for packed words/depth; bilinear filtering packed guest words is invalid.
   Reinterpretations still need conversion before packing. This preserves
   guest storage layout and dimensions, not the original image detail. Transfers,
   stencil and direct-to-texture paths must use the same rule. It saves
   attachment/raster work while retaining full-size resolve writes and
   texture storage. Check that the retained traffic and reconstruction cost
   do not consume the prize before designing compact fractional storage.
2. **Compact fractional renderer, follow-up only.** Keep render-derived
   textures physically small across post effects, reflections and resolves;
   expand only CPU-visible outputs. This could also save resolve/reload
   bandwidth, but needs a replacement for the current integer-group layout
   and consistent alias tracking. Estimate a further 2–4 engineer-weeks,
   with the same capture matrix. A fixed fraction reduces variants; it does
   not remove the layout problem.

For the first choice the final guest resolve is still 1280×720. Feed the
upscaler an actual 640×360 image by taking a half-size presentation copy of
that reconstructed output, with matched HUD/depth inputs, or by adding a
proven direct low-resolution front-buffer path. Count that copy in GPU time.
Passing a duplicated 720p image as “360p” metadata is incorrect. Downsampling
a normally rendered 720p frame alone saves no rendering work.

Expose one off-by-default, frame-boundary setting after the implementation
works. Reuse the existing rebuild path so route `cvar` steps can switch both
ways when packs are prepared; mark the transition and discard its warmup
window. A native-resolution HUD can follow only if captures show that the
globally softened HUD is unacceptable: selecting passes to keep at 1x adds
mixed-resolution ownership and compositing work.

The reference FH2 project uses pass-local image dimensions rather than our
EDRAM-to-guest-memory contract. Its `docs/renderizador_nativo.md` and the
pass sizing in `app/src/nativo/nfsmw_nativo_dibujos.cpp` were read only to
understand that difference. No source or translated implementation from the
GPL project is included here. Its performance figures are not used.

## Prize from the existing Odin profile

Input: October 13 `stage0/odin/gp6/runtime.log` from the near-native research
archive, Odin 2 Portal / Adreno 740 / Turnip gen8-v37, base Release, 1x,
`fh1-race-sustained`, `fh1_native_gpu_profile=true`. This extends the same
event-entry sequence as `fh1-race-start-wait`; it is not a fresh execution
of that route. The yardstick had sun shadows off, host single-sampling of
guest MSAA, and the untiled Android path. Post-effect values were disabled;
the post passes still ran. It cannot qualify shadows-on captures.

Use all complete GPU profile windows after the `race-moving` capture at
route frame 4560: executor frames 4800–5400, 5400–6000 and 6000–6600. These
are **three disjoint windows, 1,800 profiled frames, one archived run and
zero A/B pairs**. Values below are medians of window means, with min–max
spread; the logger reports 599/601/600 available frames and zero drops.

| Phase | Median ms/frame | Window range |
| --- | ---: | ---: |
| GPU frame timestamp span | 15.700 | 15.693–15.722 |
| Main scene draw-rendering label | 6.440 | 5.680–6.880 |
| Other reported draw-rendering labels | 2.030 | 1.980–2.210 |
| Resolves | 1.683 | 1.649–1.714 |
| Transfers | 0.779 | 0.774–0.786 |
| Clears | 0.334 | 0.334–0.336 |
| Resolve-sourced texture reloads | 0.193 | 0.125–0.193 |
| Other texture loads | 0.018 | 0.016–0.039 |
| Upload label | 0.080 | 0.080–0.110 |

The main-scene label is **41.0%** of the frame span (36.2–43.8%);
all reported draw labels sum to **53.9%** (48.8–57.9%). These are
*resolution-sensitive candidates*, not a measurement of the fraction that
actually scales with pixel count. Draw spans include geometry and pipeline
cost; frame spans include inter-submission gaps. The logger lists the 64
largest labels and rounds each to 0.01 ms. Timestamp profiling itself added
about 0.7 ms in the original control. Do not sum phase and label lines as
independent work, or treat their subtraction as pure fixed overhead.

For a pixel-sensitive fraction `f`, an ideal area model is
`T(s) = T(1) × (1 - f × (1 - s²)) + added reconstruction/upscale cost`.
Applying it separately to each selected window gives these **optimistic
scenarios**, before extra cost:

| Assumed pixel-sensitive work | 0.5x saving; resulting GPU ms | 0.75x saving; resulting GPU ms |
| --- | --- | --- |
| Entire main-scene draw span | 30.7% (27.1–32.9%); 10.892 (10.540–11.433) | 17.9% (15.8–19.2%); 12.904 (12.690–13.208) |
| All reported draw spans | 40.4% (36.6–43.4%); 9.370 (8.883–9.948) | 23.6% (21.4–25.3%); 12.016 (11.723–12.342) |

Thus half-scale is worth a dedicated follow-up; 0.75x has little margin
against the 25% gate even under generous assumptions. At 0.5x at least
33.3% of the original frame must truly scale with area to save 25%; at
0.75x it takes 57.1%, before any new work. If only the main-scene label
benefits, at least about 81% of its median share must scale for half-scale
to meet the gate with zero added cost. These profiles provide **no positive
guaranteed saving**. A one-resolution phase breakdown cannot establish the
scaling slope, and the current pin may differ from this archived baseline.

Reproducible local evidence is in `.local/codex-fleet/reports/R02/` in the
main checkout: `analyze-r02.py`, `profile-windows.csv` (including unselected
windows), `selected-labels.csv`, `prize-summary.json` and
`archived-gp6-runtime.log`. The input log SHA-256 is
`6924585bed576c34deb0648a059adb56801cc7a8e307413af13c5fb16c828a7b`.
The script asserts the selected frames, frame count and absence of dropped
profiles. Earlier [NN-0.11 analysis](../NEAR_NATIVE_RESEARCH.md) explains
the timestamp instrumentation and its overhead.

## Follow-up gate and cost

Before coding, obtain a current-pin Odin 1x race and free-roam profile with
the exact intended preset. Record draw counts and GPU labels, including a
shadows-on control. The archived race is enough to prioritize half-scale,
not to claim a current measurement or a passing gate.

Implement the compatibility path in a dedicated SDK branch and prepare its
distinct shader pack. First verify a still frame's resolve dimensions,
complete writes, alias formats, exposure and CPU readbacks on desktop;
then test live tiled and untiled routes. Replays alone do not exercise the
Android predicated-tiling behavior.

Measure half/off in one Odin run in both orders, with multiple disjoint
A/B/A blocks, transition warmup excluded and draw counts checked per side.
Use the project summarizer's disjoint estimator; do not count overlapping
adjacent pairs as independent. Include at least three runs, report the
number of pairs, median and spread, and compare source frame pacing/p95/p99
and slow-frame counts with an A/A control. Profile phases separately from
the unprofiled timing runs. Budget and identify the reconstruction and
upscaler costs rather than crediting all draw time as saved pixels.

Keep only if the **Odin race GPU frame drops at least 25%**, pacing stays
within the A/A spread, and side-by-side captures show intact HUD, bloom,
sun shadows, reflections and thumbnails, with stable exposure and a saved
thumbnail reload. Repeat the race and free-roam drive on RTX 4080; record
actual internal/display dimensions and GPU/input-history behavior for the
chosen upscaler. An altered-resolution image is intentionally different,
so pixel identity is not the criterion; inspect missing passes and seams.
No such A/B or image qualification was performed in R02.
