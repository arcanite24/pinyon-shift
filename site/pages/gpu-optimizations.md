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
| In-run A/B | live settings flipped every 300 frames for 16 windows inside one run, for devices that heat up |
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

On 2026-10-13 (RTX 4080, `fh1-race-sync`, last 600 frames, three runs) the frames with more than 5,000 draws, about half of them at about 6,500 draws, have a median of 8.5-9.0 ms. In them the decoder does 6.4-7.1 ms of work besides 1.6 ms of waiting for the title, and the recorder 7.6-8.0 ms, so both threads sit at the 8.33 ms budget: making either one alone faster leaves the frame where it is. A sampled profile of the decoder with a PDB: 22-27 % waiting, about 25 % applying register runs, 18 % packet dispatch, 2 % hashing shader microcode on load.

**Tried and dropped.**

- **Bindless textures** were within ±1.5 % on desktop, because NVIDIA's push descriptors were already cheap. On Android they cut the recorder from about 9.2 to 7.7 ms and are the default there; the frame didn't change because the GPU is the limit.
- **Replaying recorded draws** instead of deriving them again: an upper-bound probe that skipped every matching buffer took the recorder from 10.4 to 3.7 ms. Real replay of per-draw templates, buffers and whole segments was slower or −0.3 % against a −15 % goal. Proving a recorded draw is still valid cost as much as deriving it. The O(1) tests in the table above now make that proof cheap, and they show what is left: after them a draw still costs about 980 ns, spread over about 20 steps of which none is above 135 ns (constant uploads), so skipping derivation per draw cannot reach the replay probe's numbers. Reading float constants by address, which re-executing whole buffers would need, measured slower too: the title writes new constant values nearly every draw, so a heap of pages copies more than packing does ([Lessons](lessons.md#what-didnt-pay-off-here)).
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
| macOS: stored pipelines created behind the running title (`vulkan_pipeline_prewarm_background`) | MoltenVK still compiles each through Metal: 732 pipelines took 21.6 s on an M4 Pro, a black screen at every start; the title now starts at once, and a draw that needs a pipeline not yet built builds it or waits for that one |
| No pipeline builds on the command threads | 8 Elite menus about 95 s to 10 s |
| Specialized passes and translation moved to workers | cold worst frame 252–348 to 63–69 ms |
| Desktop waits up to 250 ms for a missing pipeline instead of skipping the draw | frames without a present 84 to 2 |

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

The M4 Pro is shading-bound in free roam, so the shader switches the Adreno GPUs use pay off there too. The table gives medians of a 40 s scripted drive at 1x, two runs each, with pipelines prewarmed and untiled predicated tiling on (its own saving was measured by toggling it inside one run):

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
| Sun shadows off, through the game's own unused `SkipShadowMapUnlessCockpit` setting | about 6.4 ms of a 23 ms Odin frame; at the 60 limit 58.3 fps with 4.4 % slow frames, against 58.1 fps and 8–11 % with shadows; desktop 3x about 3.5 ms (kept on) |
| Reflection cube map at a quarter rate | Odin 25.4 to 23.2 ms, same look |
| Bilinear output instead of FSR 1 | 1.4 ms on the 8 Elite |
| The game's anisotropy instead of forced 4x | 0.43 ms on the 8 Elite |
| Bloom, motion blur, depth of field off | nothing measurable; every post-processing group still changes the frame |

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
