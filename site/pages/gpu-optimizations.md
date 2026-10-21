---
title: GPU optimizations
section: Internals
order: 5
description: What was slow in Pinyon Shift's renderer on the GPU and on the recorder thread, what changed, and what each change measured on desktop, Steam Deck, Mac and Android.
---

# GPU optimizations

Each entry names what was slow, what changed and what it measured. Figures are medians unless marked p95; "ns per draw" is recorder CPU time on frames with more than 3,000 draws. Where an idea was measured and dropped, it is listed too.

## How it was measured

Single runs mislead. The same build drifts about 4 % between batches on the desktop, and a handheld heats up over a run. The methods that held up:

| Method | Use |
| --- | --- |
| Interleaved A/B | last 600 frames of the scripted race, hidden window, pinned save, three interleaved pairs; median and p95 |
| ns per draw | recorder changes, judged on heavy frames only |
| In-run A/B | live settings flipped every 180-300 frames inside one run, for devices that heat up; the error bar comes from disjoint A B A blocks of windows |
| Frame replay | one dumped frame replayed 1,210 times; the median repeats within 0.02 ms, on any device |
| Knock-out | skip one phase, accept a wrong image, time the frame |
| Per-frame CSV | GPU time, draws, waits and per-thread CPU for every frame |
| Nsight GPU Trace, driver IR dumps, pipeline statistics | finding what the GPU is bound by |

GPU timestamps around each phase cost 2–5 ms a frame and overstate the phases several times, because each one waits for the queued draws. Knock-outs gave the true costs.

## The recorder thread

At 1x on the desktop the frame was bound by CPU work on the recorder thread, not by the GPU. An Nsight trace of a 3x frame showed the shader cores 20 % busy, memory 17 % and the front end waiting for idle 35 % of the time.

{{diagram:recorder-cost|Recorder CPU per draw. Most of the gain came from not redoing work whose inputs hadn't changed.}}

**Threads first.**

| Change | Measured |
| --- | --- |
| Split decoding from recording; fence writes recorded instead of synchronized (about 30 a frame had left the decoder waiting half its time) | race 17.67 to 16.46–16.75 ms |
| A submission worker replays streams into the driver (it had been a third of the command thread) | worker busy 11.9 ms a frame |
| Present from the worker, so the swap doesn't wait for it | 2,076–2,151 to 1,924–1,971 ns per draw; frame 12.49 to 11.78 ms |

**Then per draw.** A census found that 58 % of draws change only shader constants. Most of the work below caches what a draw derives and reuses it while the inputs hold:

| Change | Measured |
| --- | --- |
| Draws to the same targets stay in one rendering, instead of a barrier and a new rendering per draw (4,850 renderings and 5,200 barriers a frame to 297 and about 600) | race 31.9 to 19.6 ms |
| Bulk register writes | 1x race 20.79 to 19.49 ms |
| Sampler reuse | 19.49 to 18.36 ms |
| Push descriptors for pixel textures | 2,178–2,223 to 2,157 ns per draw |
| A register-state epoch: pipeline, viewport and target preparation reused while non-constant state holds | about 1,967 to 1,900 ns |
| Uniform memory host-cached instead of write-combined | 1,800 to 1,755 ns |
| The decoder drops register writes that change nothing | 1,725–1,849 to 1,649–1,697 ns |
| Sampler parameters memo | 1,685–1,789 to 1,622–1,721 ns |
| Float constant ranges merged across small gaps (12 to 5.5 runs a draw) | heavy frame 10.16 to 9.71 ms |
| System constants memo, hit on 58–73 % of draws; a verify mode found no difference over about 38 million draws | 88–103 to 68–78 ns per draw for that step |
| Draw registers fused into the draw record, shader loads as typed entries, cheaper batch handoff (record entries 92,100 to 56,800 a heavy frame) | recorder CPU −7 to −14 % |
| A constants descriptor set key included 4 bytes of uninitialized padding, so 43 % of draws wrote a new set | about 1.1 ms of recorder time |
| The decoder compares a register run with its register file four registers at a time when the run holds no register whose write always matters (the per-register loop was 11 % of the decoder thread) | heavy race frames: decoder work 7.2 to 6.6 ms; frame time unchanged, because the recorder bounds those frames too |
| Stages kept when their inputs are unchanged since the last draw, each by an O(1) test (`gpu_draw_unchanged_inputs`): the samplers (same shaders, submission and filtering, no sampled fetch constant written: 44 % of draws), the texture request (bindings in sync, textures already used and sampled in this submission: 56 %), the texture descriptor sets or push (41 %); target preparation remembered per register state hash in 16 slots (hits 53 to 73 %). A verify mode found no difference over 12.5 million draws | 1,066 to 981 ns a draw; heavy frames 8.66 to 8.51 ms (four alternating runs each) |

Together with the binding memo table and ThinLTO for the GPU code, the 1x race went from 20.79 ms (48 fps) on 2026-09-30 to an 8.3 ms median, the 120 fps limit.

The binding memo remembers texture objects as well as fetch constants. Above
1x, an invalidated entry must choose its texture object again: resolving into
an allocation makes it scaled, while a CPU write can reuse it for an ordinary
texture with exactly the same fetch constants. Reusing the old object reads
the wrong memory copy. Only outdated memo entries are re-derived; other
textures retain their bindings and contents. A backend-independent regression
test covers both ownership transitions and an unrelated texture. See the
[ownership analysis and gameplay checks](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/LIVERY_TEXTURE_OWNERSHIP.md).

Compressed textures need every stored base and mip page to belong to resolves
before selecting the scaled buffer. After the livery editor reuses an
allocation, an old resolved mip or padding page can coexist with CPU asset
data; selecting the whole scaled buffer then decodes unrelated render output
as compressed blocks. A private three-layer MX5 route on multivac (RTX 4080,
Windows Vulkan, 2x) reproduced noisy festival signs and black road surfaces.
Requiring complete ownership restores those textures while retaining fully
resolved compressed textures and the partial-resolve path for uncompressed
render targets. The regression fails three of 27 assertions before the fix
and passes all 27 after it.

On 2026-10-13 (RTX 4080, `fh1-race-sync`, last 600 frames, three runs) the frames with more than 5,000 draws, about half of them at about 6,500 draws, have a median of 8.5-9.0 ms. In them the decoder does 6.4-7.1 ms of work besides 1.6 ms of waiting for the title, and the recorder 7.6-8.0 ms, so both threads sit at the 8.33 ms budget: making either one alone faster leaves the frame where it is. A sampled profile of the decoder with a PDB: 22-27 % waiting, about 25 % applying register runs, 18 % packet dispatch, 2 % hashing shader microcode on load.

**Tried and dropped.**

- **Bindless textures** were within ±1.5 % on desktop, because NVIDIA's push descriptors were already cheap. On Android they cut the recorder from about 9.2 to 7.7 ms and are the default there; the frame didn't change because the GPU is the limit.
- **Replaying recorded draws** instead of deriving them again: an upper-bound probe that skipped every matching buffer took the recorder from 10.4 to 3.7 ms. Real replay of per-draw templates, buffers and whole segments was slower or −0.3 % against a −15 % goal. Proving a recorded draw is still valid cost as much as deriving it. The O(1) tests in the table above now make that proof cheap, and they show what is left: after them a draw still costs about 980 ns, spread over about 20 steps of which none is above 135 ns (constant uploads), so skipping derivation per draw cannot reach the replay probe's numbers. Reading float constants by address, which re-executing whole buffers would need, measured slower too: the title writes new constant values nearly every draw, so a heap of pages copies more than packing does ([Lessons](lessons.md#what-didnt-pay-off-here)).
- **Owned draw programs for one pass** (`gpu_d3d_program`, off; #752, #753): the game marks the buffers of the procedural-model lists (trees and other vegetation, 126-190 draws a frame), and the backend records each run's derived draw state once: shader analysis, primitive processing, translations, the pipeline and the viewport. Later runs take it from the program while the state hash, shaders, draw words, settings and index range are unchanged. The recorded index range is copied into a device-local arena and retired when the game or a resolve writes it; retired copies are freed once the GPU is past their last use (about 3 submissions, 5-14 ms), with no fence on the whole arena. Shadow mode derived every draw anyway and compared: 4.6 million draws on the desktop race, no difference. In performance mode 99-100 % of those draws came from a program and none of them was derived again, which saved 70-160 ns a draw against recording only. The complete cost tells otherwise: against the same lists bracketed and timed with no program (mode 4), the program path cost 925 against 962 and 865 against 860 ns a program draw on multivac, and 762 against 670 and 743 against 646 ns on the Odin, where 5 of 6 windows that ran both modes were slower by 5-58 ns. Matching a draw against its record (state hash, shaders, draw words, settings, index version) costs about what the cached derivation costs, as with replay above. Looking the program up only at a run's first drawn draw was needed for even that: many runs draw nothing (later tiles), and a lookup at every run had cost the Odin 90 ns a draw. Rejected; the code stays, off. Checking the settings once a run instead of at every draw, and prefetching the next record, left the Odin 85-100 ns a program draw slower than mode 4 (743 against 641, 752 against 660, prefetched 738 against 655 and 732 against 645 ns). The pass's GPU side is small too (#755). A probe (`gpu_d3d_program_probe` 2) skips only these draws' draw commands; alternated every 60 frames on the Odin and compared window by window with its neighbours, it saved 0.37 ± 0.22 and 0.22 ± 0.23 ms of 11.3-11.9 ms of timed GPU work a frame in two runs. Native vertex layouts or typed fetch from host buffers could remove only part of that, so they were not built. The pass has no resolves or copies, so logical resolve targets have nothing to replace in it.
- **Culling hidden draws** (#784): an occlusion query around every draw of one frame in eight (`fh1_visibility_census`, off) found that 54-60 % of the main scene's draws on the Odin drive pass no samples, after the game's own culling. A deliberately wrong probe that drops each draw that passed no samples at its last census (`fh1_visibility_oracle_skip`) cut the main pass from about 8.3 ms by 2.2 and 3.2 ms in two runs. Most of that is vertex and binning work for occluded draws, not shading: the draws with early depth carried 1.6-1.7 ms of it. The draws that also pass no samples with the depth test off (`fh1_visibility_census_no_depth`), roughly what a frustum test against bounds could remove without popping, saved 0.64 ± 0.77 and 1.44 ± 0.52 ms. Culling the occluded rest would need depth from earlier frames, which can drop an object for a frame when it comes into view, so neither was built.
- **PGO** of the GPU code, an AVX2 build, Windows MMCSS scheduling and thread placement: no consistent gain.

## Renderings and clears

Tile-based mobile GPUs pay for each rendering: on the Adreno 830 one costs 24–28 µs.

| Change | Device | Measured |
| --- | --- | --- |
| EDRAM clears folded into the next rendering's load | 8 Elite | renderings about 280 to 210; frame −1.6 to −2.6 ms, GPU −0.5 ms |
| The three predicated scene bands drawn once ("single-pass scene") | Odin | 4x 32.0 to 29.2 ms; 1x 28.3 to 25.4 ms; no seam in captures |
| | Desktop 3x | within noise |
| Draws that write nothing skipped (about 120 a frame) | Desktop | within noise |

Dropped: store-op tuning (only about 8 depth stores a frame qualified); trimming render areas (the Adreno driver already skips untouched tiles); forcing Turnip's on-chip GMEM path (50–56 ms against 29–32); skipping attachment barriers at 3x (noise).

## Resolves and texture loads

| Change | Measured |
| --- | --- |
| Texture loads by compute, writing untiled texels through a storage view, instead of buffer-to-image copies that NVIDIA serialized on its copy engine | texture loads at 3x 13.1 to 3.9 ms; 3x race 39.9 to 24.7 ms; Odin 36.2 to 31.9 ms |
| Resolve straight into the current texture, color and depth | −0.96 ms GPU at 3x |
| Reload only the 32-row bands GPU writes touched | −0.64 ms GPU at 3x |
| CPU bounds for unclipped draws, so they stop claiming all 2,048 tiles | −1.27 ms GPU at 3x; transfers 3.1–3.3 to 1.7–2.4 ms |
| Partial resolves into outdated textures | Odin reloads 1.29 to 0.23 ms, GPU 20.9 to 19.3 ms; Deck −3 %, identical image; no gain on RTX 4080 or M4 Pro, so on for Linux and Android only |
| Resolve and transfer pipelines specialized per case; the generic ones compiled to about 400 instructions a pixel on Turnip, the specialized ones 100–300 | Odin resolves 4.83 to 3.59 ms, GPU 23.7 to 20.4–21.3 ms; RTX 4080 at 2x −0.4 ms; Deck 11.71 to 11.19 ms |
| 16 × 16 resolve workgroups | Odin 15.02 to 14.18 ms at 1x |
| Stencil export in depth transfers, one pass instead of nine | 8 Elite transfers 6.6–14.3 to 3.5–5.2 ms; race 35 to 25 ms |
| Reload fixes on the Odin: whole outdated textures covered, raw-bits views for small textures, bounded image writes, only changed cube faces | reloads 67 to 17 a frame; cube reloads 0.20 to 0.04 ms; each byte-identical in replay |

Partial resolves leave texels outside the resolved area with their older contents, which is why they are measured per platform before being turned on.

## Shaders

| Change | Measured |
| --- | --- |
| Shared memory read through one texel buffer instead of a storage buffer (the Adreno 740 limits those to 128 MB) | typical vertex shader 548 to 252 instructions; Odin replay 16.65 to 15.01 ms; no desktop gain |
| Texture sign specialization | Odin 45.8 to 43.8 ms |
| Implicit LOD on Turnip | Odin 42.4 to 39.8 ms |
| Turnip without shader preambles | 13.88 to 13.65 ms |
| Hot shaders hand-edited to drop per-operation NaN guards, matched by guest hash and SPIR-V hash | 17.73 to 17.52 ms; identical images |
| Fast pixel math | desktop noise; Odin 36.2 to 32.4 ms |

Fast math has a trap: Direct3D 9 shaders rely on 0 × ∞ = 0. Dropping that rule smeared motion blur on Adreno ([#403](https://github.com/arcanite24/pinyon-shift/issues/403)), and it was restored.

**Compile stalls.**

| Change | Measured |
| --- | --- |
| Shaders prepared during setup | first launch, frame time over budget 13.0 to 5.7 s |
| `VkPipelineCache` saved between runs | NVIDIA: 387 stored pipelines created in about 21 ms at start; Odin 1.7 s to 86 ms |
| The running save of that cache (every 30 s while new pipelines appear) moved from the GPU commands thread to the storage write thread | reading and writing the driver's cache held the thread 30–40 ms, a hitch every 30 s on the Odin 2 Portal; free-roam frames over 25 ms on the Odin went to 1, and the Deck LCD's 70 ms free-roam frame went away |
| macOS: stored pipelines created behind the running title (`vulkan_pipeline_prewarm_background`) | MoltenVK still compiles each through Metal: 732 pipelines took 21.6 s on an M4 Pro, a black screen at every start; the title now starts at once, and a draw that needs a pipeline not yet built builds it or waits for that one |
| No pipeline builds on the command threads | 8 Elite menus about 95 s to 10 s |
| Specialized passes and translation moved to workers | cold worst frame 252–348 to 63–69 ms |
| Desktop waits up to 250 ms for a missing pipeline instead of skipping the draw | frames without a present 84 to 2 |
| The wait moved from each draw to the submission's replay (`vulkan_async_pipeline_bind_on_replay`), so a frame's new pipelines build in parallel | RTX 4080, drive route with no stored pipelines: title fence waits 1.17-1.37 s to 0.52 s, worst frame 305-416 to 145-166 ms |

## Three switches across four GPUs

The same frame replayed on every device. The results differ enough that no saving measured on one GPU was assumed for another:

| Switch | RTX 4080, 2x | M4 Pro, 1x / 2x | Steam Deck, 1x | Image |
| --- | ---: | ---: | ---: | --- |
| Default | 6.24 ms | 12.67 / 29.9 ms | 11.19 ms | |
| Quads as triangle lists | −3 % | — / −5 % | about −1 % | mean difference 0.02/255 |
| Coarse 2 × 2 shading | about −3 % | not in MoltenVK | −7 % (−9 % with alpha-tested draws) | slightly softer |
| TEXTURE GAMMA FAST | none | −8 % / — | −2 % | darker midtones |

- **Quads.** Quad lists were expanded in a geometry shader, which Adreno runs slowly; 77 of 220 driving pipelines had one. Converting them to triangle lists saved about 1.2 ms on the Odin and is the default everywhere.
- **Coarse shading** uses the fragment shading rate extension: the Odin scene went 8.67 to 7.71 ms at 4x. Draws using alpha to coverage stay at full rate because Turnip turned them into dithered ghosts. It is a player option, SCENE SHADING, off by default.
- **Texture gamma.** Sampling gamma textures through sRGB views skips the console's piecewise curve in every shader. The sRGB curve is darker in the midtones (half the pixels change), so the default stays accurate.

## Apple silicon

The M4 Pro is shading-bound in free roam, so the shader switches the Adreno GPUs use pay off there too. The table gives medians of a 40 s scripted drive at 1x with MSAA off, two runs each, with pipelines prewarmed and untiled predicated tiling on (its own saving was measured by toggling it inside one run). QUALITY 60 instead selects 2x, 4x MSAA and untiled predicated tiling off; these 1x numbers do not qualify that preset:

| Switch, M4 Pro | Median frame |
| --- | ---: |
| Base | 10.9 ms |
| Fast pixel math (`spirv_fast_pixel_math`) | 8.6 ms |
| Texture signs as specialization constants | 9.8 ms |
| MoltenVK without Metal argument buffers | 10.3 ms |
| Untiled predicated tiling | about −0.8 ms |
| All four, the macOS default | 8.35 ms (the 120 Hz cap) |
| IEEE vertex math | 11.0 ms, no gain |
| Bindless textures | 11.1 ms, no gain |

With all four on, the GPU frame is 5.6–5.7 ms against 12.3–12.7 ms, and the title waits on GPU fences 6 times a frame instead of 26. Mean luma over the drive is 114.6 against 114.7 on Windows.

The window is hidden in these runs, but Core Animation still hands out drawables at the display rate. MoltenVK takes the drawable while it encodes the present, on the thread that submits everything else, so no run goes past 120 fps on a 120 Hz display. MoltenVK also stamps timestamps at Metal encoder boundaries, so per-pass GPU timing doesn't work there; whole frames do.

These are historical optimization measurements. On 2026-10-18, the current
base-game qualification on the M4 Pro (24 GiB, macOS 26.3), with a pinned
Miata seed and a 60 fps limit, averaged 59.6–59.9 fps at 1x across off/2x/4x
MSAA. At 2x it averaged 59.8/53.6/39.6 fps respectively. QUALITY 60's
2x/4x cell had median/p95/p99 23.16/34.53/38.69 ms and mean whole-frame
GPU time 24.01 ms. Its heap usage was 3671 MiB and peak native surfaces
467 MiB; RSS is not total Metal memory. These are single runs over 36.6–36.7 s,
not an A/B speedup claim ([method and all resource columns](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS.md#renderer-qualification)).

The 1x untiled-predicated-tiling saving did not qualify a quality-mode gain:
an unpaired 2x/4x live control returned 34.1 fps against 43.5 with it off,
and surfaces 848 against 467 MiB. Varying car poses limit the timing
comparison. QUALITY 60 keeps its existing off setting. A separate uncapped
1x/MSAA-off run with it on reached 105.5 fps, median 9.30 ms, on this seed.
The small-float exposure readback complements 4 KiB GPU tracking; no
measured gain justifies removing that tracking or changing fast math or
pipeline waiting to address the remaining restart-dependent sky tint.

## MSAA, scale and memory

| Change | Measured |
| --- | --- |
| Above 1x, the game's 4x MSAA surfaces had 36 host samples per guest pixel at 3x; one sample per pixel | 3x race 29.1 to 22.3 ms; transfers 10.3 to 4.4 ms |
| MSAA off at any scale, the desktop default | 8 Elite race 25 to 17 ms; RTX 4080 only 0.2–0.35 ms, but surfaces 501 to 265 MB |
| Two host samples for the game's 4x | Odin GPU 18.69 (4x), 16.19 (2x), 15.19 ms (off); 2x now holds 60 and is the SMOOTH 60 preset |
| Surfaces allocated for the rows they use, not the whole EDRAM period (`fh1_surface_rows_on_demand`) | RTX 4080, 3x race: 34 surfaces 2,388 to 635 MB, device memory 4,479 to 2,747 MB; two surfaces grew during the route; captures unchanged |

| Desktop race | Median | p95 | Graphics memory |
| --- | ---: | ---: | ---: |
| 1x | 8.41 ms | 10.75 ms | 0.9 GB |
| 2x with the game's 4x MSAA | 8.43 ms | 11.71 ms | 3.3 GB |
| 3x | 9.82 ms | 13.58 ms | 4.3 GB (2.7 GB with surfaces sized by rows) |

## Quality cuts

| Cut | Measured |
| --- | --- |
| Sun shadows off, through the game's own unused `SkipShadowMapUnlessCockpit` setting | about 6.4 ms of a 23 ms Odin frame; at the 60 limit 58.3 fps with 4.4 % slow frames, against 58.1 fps and 8–11 % with shadows; desktop 3x about 3.5 ms (kept on). Applies only while the cars' lights are off (08:02 to 18:50 game time), since the setting also removes the headlights' light on the road ([#532](https://github.com/arcanite24/pinyon-shift/issues/532)) |
| Reflection cube map at a quarter rate | Odin 25.4 to 23.2 ms, same look |
| Bilinear output instead of FSR 1 | 1.4 ms on the 8 Elite |
| The game's anisotropy instead of forced 4x | 0.43 ms on the 8 Elite |
| Bloom, motion blur, depth of field off | nothing measurable; every post-processing group still changes the frame |

Oncoming headlight flicker remains under investigation in
[#531](https://github.com/arcanite24/pinyon-shift/issues/531), including with
HDR off. Restoring the projected headlight pool with shadows off does not
qualify that separate behavior. The [night-traffic route and recording
method](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/HEADLIGHT_FLICKER.md) preserve a two-minute observation
window at each output limit; its sparse captures and successful exit alone
cannot establish that the lights stayed stable.

## Frame pacing

{{diagram:frame-pacing|A frame that misses its vblank by a little used to wait for the next one.}}

At a 120 limit the guest vblank ticks every 4.17 ms and the game steps every second one, so frames quantize to 4.17 ms steps. A frame that missed 8.33 ms by a little waited until 12.5 ms. A hook now lets a late frame flip as soon as it is ready:

| | Before | After |
| --- | ---: | ---: |
| Median | 9.10 ms | 8.89 ms |
| p95 | 13.07 ms | 10.48 ms |
| p99 | 16.5 ms | 13.1 ms |

The cost is uneven spacing after a late frame (9.0 then 7.7 ms). `VK_KHR_present_wait` was measured and left off: spacing deviation 1.36 ms with it, 1.08 ms without.

The decoder's waits for GPU writes choose by rate. At 60 fps and below it sleeps in 100 µs steps after a 200 µs yield, which cut decoder CPU from 12.4 to 8.9 ms on a simulated 4-core PC. At 120 a 2 ms yield wins by 2.4–4.5 presents a second.

## Driver problems found on the way

These were correctness fixes, not speed, but each cost days to find:

- **AMD device loss.** With asynchronous submission the recorder could wait on a fence the worker hadn't submitted yet; AMD's driver fails on that. The worker now publishes its last submission and waits stop there.
- **Adreno 830** returns at once from `vkWaitForFences` with an infinite timeout; waits go a second at a time.
- **Qualcomm push descriptors** read as null in some draws, which broke shadows. Qualcomm devices use descriptor sets.
- **Barriers and formats.** A resolve's writes were declared as reads, and 10-bit targets were stored at 8 bits.
- **Validation.** A query ended inside a rendering, one present semaphore was shared between swapchain images, and a storage view had the wrong type. One query warning at startup is still open.

The livery editor also resolves RGBA8 EDRAM into single-channel 8-bit masks,
including MSAA averages. The native path packs these as individual bytes and
preserves neighbouring texels with atomic masked writes. The same tiled and
scaled layouts apply; this format uses texture reloads rather than direct
32-bit image writes. See the [livery investigation](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/LIVERY_TEXTURE_OWNERSHIP.md)
for the trace and remaining gameplay checks.
