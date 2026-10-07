# Performance backlog: 4K at 120 fps on Vulkan

Status: **worked through on 2026-09-30; every item is taken, measured and
dropped, sized and deferred, or waiting on a person.** The long-term
follow-up, compiling FH1's display lists inside the executor, is
[DESKTOP_RENDERER_BACKLOG.md](DESKTOP_RENDERER_BACKLOG.md). Created 2026-09-30 at
`dev` checkpoint `58473da` (ShiftGlue `b9a5de0`).

**Outcome before the final pass.** The Vulkan race at 1x went from 20.8 ms
(48 fps) to a frame mean of 10.4-11.8 ms (about 90 fps): the GPU commands thread was split into
a decoder and a recorder, and the recorder's cost per draw fell from about
2.9 to 1.85 us through push descriptors, sampler, binding and lookup memos,
executor target skips, presenting from the submission worker and a register
state epoch. At 3x the GPU holds the frame at 22-24 ms (from 29.1) with
single-sampled MSAA surfaces. The GRAPHICS PRESET row sets PERFORMANCE 120
(1x on Vulkan with FSR 1 to the display) and QUALITY 60. The 120 fps target
is not met: the recorder needs about 7 ms against its 9.4, what remains of
it has no single item above 8 %, and PB-2.12's analysis shows a new draw
ABI would not close that; native 4K (3x) at 120 would need about three
times this GPU. What is left for a person is the GPU trace (PB-0.4) and the
visible-window check of the presets and fidelity trades (PB-5).

**Final pass (2026-09-30).** A comparison with UnleashedRecomp,
XenosRecomp, skate3recomp and other recomps, plus a census of FH1's command
stream, produced PB-6 to PB-10 in
[Final pass](#final-pass-lessons-from-other-recomps-pb-6-to-pb-10). Working
through it:

- The guest CRT's `memcpy`, `memmove` and `memset` now run as host code, and
  the atomics use `std::atomic` (PB-8.1, PB-8.2).
- The per-draw memos are keyed by a register content hash (PB-6.1, PB-6.3).
- A recorder profile found PB-8.8 to PB-8.11: cached uniform memory, fixed
  per-draw overheads, a sampler parameters memo, and the decoder dropping
  register writes that change nothing.

The recorder went from 1.85 to 1.55-1.65 us per draw. The 1x race now runs
at 120 fps (8.33 ms median) from 5 to 40 s, and its heavy last stretch at a
median of 9.1-9.2 ms, where the title's render thread and the recorder's
fence latency share the limit. The census ruled out the two-level constant
ABI (PB-7.2). Compiled display lists (PB-6.4) and bindless textures (PB-7.3)
are deferred with sizes and reasons. The high-frame-rate crowd (PB-9) stays
a reverse-engineering session. The maintainer's visible-window check now
includes pacing (PB-8.6). This backlog replaces the performance items of the
[native port backlog](NATIVE_PORT_BACKLOG.md) (NP-2, NP-3, NP-9 and the
speed half of NP-15) with one target and one plan. It was written from a
read-only audit of the renderer, the command processor, the recompiled guest
code and the frame loop, plus the measurements in
[Where the frame stands](#where-the-frame-stands). Paths use `sdk/` for
`thirdparty/shiftglue-sdk/`. Raw run output is kept locally under
`.local/perf4k/` and is not distributed.

## Target

The moving race at a **3x internal scale (3840x2160) at a steady 120 fps**
on the maintainer's machine (Ryzen 7 5800X, RTX 4080, 4K display at
120 Hz), on the **Vulkan** backend. Direct3D 12 became legacy and unsupported
on 2026-10-05; its measurements below are historical comparisons.
A frame is 8.33 ms, and FH1 ends its frames on guest vblanks, so a frame
that misses the budget costs a whole vblank (4.17 ms at the 240 Hz vblank
the render limit of 120 gives): the measured race frames take 8.4, 12.5,
16.7, 20.8 or 25.0 ms and nothing in between. The budget below therefore
leaves margin for jitter.

The maintainer has accepted, for this target, results that are not 100 %
faithful to the console and optimizations that carry risk, as long as the
gates in [PB-5](#pb-5-gates-and-protocol) hold. The trades this plan makes
are listed in [Fidelity trades](#fidelity-trades-this-plan-allows).

## Budget

Every stage runs concurrently with the others, so each must fit the frame
on its own.

| Stage | Today (1x unless noted) | Budget per frame | Margin note |
| --- | ---: | ---: | --- |
| GPU, one race frame at 3x | 29 ms on Vulkan, 18.5 ms on D3D12 | **≤ 7.0 ms** | includes the presenter's passes |
| GPU commands thread (PM4 decode, state derivation, executor, tape) | about 18 ms busy on Vulkan (the 1x frame; 5,800-6,400 draws) | **≤ 6.0 ms** | measured with `pinyon_shift_thread_sampler` |
| Submission worker (tape replay, `vkQueueSubmit`) | ~3 ms | ≤ 5.0 ms | grows with descriptor work moved onto it |
| Title render thread (`Guest 825A6320`, the loop in `sub_8259F3E8`) | 6.5-7.8 ms (39 % busy at 60 fps; 27 % of a 29 ms frame at 3x) | **≤ 6.0 ms** | per frame; recompiled code |
| Title simulation thread (`Guest 8255AE10`, `sub_823ED888`) | 4.6-4.7 ms per step (55 % busy at 120 steps/s) | ≤ 6.0 ms per step | one step per frame at 120 fps; steps follow vblanks, not frames |
| Audio (`Guest 82FB4AF8`) and the rest | 29 % of a core | no change | |
| Present | one 4K blit | ≤ 0.3 ms GPU | no scaling at 3x on a 4K display |

## Where the frame stands

Measured 2026-09-30 on `fh1-race-sync` (seed `appdata-2026-09-27`,
`RelWithDebInfo`, hidden window, `--pinyon_shift_fh1_render_fps_limit=120`
so the guest vblank runs at 240 Hz, car-card repair off), race window =
last 600 frames less the final 30, D3D12 packs `fh1-native-v3` at 1x and
3x. GPU utilization is `nvidia-smi` sampled every 500 ms over the race.

| Run | Frame median / p95 ms | fps | GPU span median ms | GPU busy | Draws/frame | Sim steps/frame |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D3D12 1x | 18.10 / 26.0 | 55 | 16.5 | 35 % (p10 23 %) | 6,357 | 2.3 |
| D3D12 1x, render limit 60 (vblank 120 Hz) | 16.70 / 25.4 | 60, capped | 15.0 | 33 % | 5,925 | 1.1 |
| D3D12 3x | 19.22 / 25.0 | 52 | 18.5 | **89 % (p10 75 %)** | 6,135 | 2.3 |
| D3D12 3x, `--fh1_native_gpu_profile=true` | 24.78 / 30.8 | 40 | 24.1 | 71 % | 5,904 | 3.0 |
| D3D12 1x, `--fh1_native_gpu_profile=true` | 20.00 / 25.5 | 50 | 17.6 | 37 % | 6,195 | 2.4 |
| Vulkan 1x | 20.79 / 25.9 | 48 | not written on Vulkan (PB-0.1) | 36 % (p10 30 %) | not counted on Vulkan | 2.5 |
| Vulkan 3x | **29.13 / 33.6** | 34 | not written | **98 % (p10 99 %)** | not counted | 3.5 |
| Vulkan 1x, `--fh1_native_gpu_profile=true` | 20.83 / 28.2 | 48 | executor span 18.8 | | | 2.6 |
| Vulkan 3x, `--fh1_native_gpu_profile=true` | 30.70 / 36.9 | 33 | executor span 30.3 | | | 3.7 |

What the numbers say:

- **At 1x the race is CPU-bound at about 18 ms on D3D12 and 21 ms on
  Vulkan** with the GPU a third busy; at 3x the GPU becomes the limit at
  18.5 ms on D3D12 and **29 ms on Vulkan** (99 % busy) with the CPU side
  unchanged. The CPU side needs 2.2-2.5x, the Vulkan GPU at 3x about 4x.
- **Vulkan's GPU frame is 57 % longer than D3D12's for the same draws** at
  3x (29.1 against 18.5 ms) and its transfers alone are 10.3 against
  7.7 ms profiled, so part of the Vulkan gap is backend overhead rather than
  emulation cost (PB-1.9).
- **The old "60 fps cap" was the vblank.** With the render limit at 60 the
  guest vblank runs at 120 Hz and FH1, which waits two vblanks per frame,
  lands on 16.70 ms every frame; with it at 120 the cap moves to 8.33 ms
  and the race runs unpaced at 55 fps. The hidden window reports 60 Hz, so
  every earlier hidden baseline was capped.
- **Frames are quantized to vblanks.** In the unpaced 1x run, 14 frames
  took 2 vblanks (8.37 ms), 291 took 4 (16.70), 203 took 5 (20.79) and 71
  took 6 (25.00); a frame that misses 8.33 ms by a little costs 4.17 ms.
- **Simulation steps follow vblanks, not frames.** FH1 steps its
  simulation once per two vblanks: 120 steps/s here regardless of the
  frame rate, 2.3 steps per 18 ms frame. Frames with 3 steps take 21.5 ms
  median against 17.1 ms with 2, so the simulation thread is on the
  critical path when a frame spans more vblanks, which is the "catch-up"
  behaviour reported at 4x (NP-4.10).
- **The GPU profile flag costs 2-5 ms per frame** (timestamp queries and
  per-draw timers: 18.1 vs 20.0 ms at 1x, 19.2 vs 24.8 ms at 3x), so its
  phase times are upper bounds; the frame numbers above come from runs
  without it.
- **Thread map.** `Guest 8255AE10`'s start routine calls `sub_823ED888`,
  the simulation loop; `Guest 825A6320` runs `sub_825A6208`, which calls
  the render loop `sub_8259F3E8`; `Guest 82FB4AF8` is audio.
- **Thread sample at 3x on Vulkan** (`pinyon_shift_thread_sampler`,
  4 ms interval, race window of a 29.0 ms frame, `.local/perf4k/vk3x-sampled`):
  GPU commands thread 70 % busy (about 20 ms per frame; its 30 % of waits
  are GPU fences and the worker, since the GPU is the limit), submission
  worker 23 % (mostly `vkQueueSubmit` blocking behind the saturated GPU),
  simulation thread 55 % (3.4 steps per frame, 4.7 ms per step), render
  thread 27 % (7.8 ms per frame; 68 % of its time in the fence wait
  `sub_829F04A8` -> `sub_823E91F0`), audio 28 %, and about 0.5 core across
  fourteen other guest threads. On the GPU commands thread the largest
  exclusive items are the NVIDIA driver (6.3 %, about 1.8 ms, no public
  symbols: descriptor writes), `UpdateBindings` self 4.8 %,
  `IssueDrawImpl` self 3.5 %, the type-0 register path (`WriteRegister`
  4.7 %, `WriteRegistersFromMem` 2.3 %, `copy_and_swap_32_unaligned`
  1.6 %) and `LoadShader` 1.5 %.

Executor GPU phases with the profile on, ms per frame over the race
window (upper bounds, see above):

| Phase | D3D12 1x | D3D12 3x | Vulkan 1x | Vulkan 3x | Scaling |
| --- | ---: | ---: | ---: | ---: | --- |
| Ownership transfers | 1.39 | 7.70 | 1.43 | 10.27 | pixels x samples x passes (9 for depth with stencil) |
| Resolves | 0.63 | 2.08 | 0.66 | 2.30 | pixels x samples |
| Texture reloads a resolve invalidated (untile) | 0.73 | 2.61 | not timed on Vulkan | not timed | pixels |
| Clears | 0.21 | 0.26 | 0.20 | 0.28 | pixels x samples |
| Sum | 2.96 | 12.65 | 2.29 + reloads | 12.85 + reloads | of a 17.6 / 24.1 / 18.8 / 30.3 ms profiled span |

At 3x the executor's own passes are about half the profiled GPU frame and
the draws the other half on both backends. Memory at 3x: surfaces
4,448 MB, scaled resolve range 464 MB, textures 558 MB, transfer words
90 MB.

Transfer census at 3x over the 4,800-frame run (`transfer tile-passes`
log line; `base/pitch/msaa/kind`): depth 4x to 1x at base 0 11.66 M tile
passes, depth 2x to 4x at base 128 10.37 M, depth 1x to 4x at base 0
7.78 M, depth 128/4x to 1024/4x 5.53 M, colour (720) to depth (128, 2x)
3.89 M, colour (720) to depth (0, 4x) 3.89 M. Totals: 871,462 transfers
(181 per frame) in 96,511 batches, 253 M tile passes (53,000 per frame),
stencil passes skipped on 68 % of transfers.

## Progress

Race medians on `fh1-race-sync` (PB-0.6 protocol, render limit 120).
Frames land on 4.17 ms vblank steps, so medians move in steps; means are
given where they tell more.

| Date | Change | Vulkan 1x | Vulkan 3x |
| --- | --- | ---: | ---: |
| 2026-09-30 | Baseline (SDK `b9a5de0`) | 20.79 | 29.13 |
| 2026-09-30 | PB-1.1 single-sampled MSAA surfaces (opt-in) | — | 22.3-23.8 |
| 2026-09-30 | PB-2.2 bulk register writes | 19.49 | |
| 2026-09-30 | PB-2.3 sampler reuse | 18.36 | |
| 2026-09-30 | PB-2.1 texture set reuse | 18.23 | |
| 2026-09-30 | Float constant runs, lock-free page scan (PB-2.4) | 17.04-17.28 | |
| 2026-09-30 | Translation memo, dynamic constants (PB-2.1) | 16.74-16.86 (mean 17.9-18.3) | |
| 2026-09-30 | Constants set memo | mean 17.4-17.9 | |
| 2026-09-30 | PB-2.11 decode/record split (opt-in), draw records, early shader hashing | mean 16.46-16.75 (unsplit 17.67) | 22.4-23.8 with single-sampled surfaces |
| 2026-09-30 | PB-2.5 fetch-word fast path, PB-2.1 push descriptors | mean 12.6-13.3; recorder 2090-2190 ns/draw | |
| 2026-09-30 | PB-2.9 executor target skips, PB-2.8 present on the submission worker | mean 11.7-11.8; recorder 1920-1970 ns/draw | |
| 2026-09-30 | PB-2.5 binding memo, texture view cache, PB-2.7 shader lookup front | mean 11.2-11.8; recorder 1840-1940 ns/draw | |
| 2026-09-30 | PB-2.6 register state epoch: pipeline, translation, viewport and target memos | mean 10.4-11.5; recorder 1820-1900 ns/draw | 24.2 median (GPU-bound) |
| 2026-09-30 | PB-8.1 guest CRT on the host, PB-8.2 atomics, PB-6.3 content-hashed memos | mean 10.0-11.4; recorder 1750-1900 ns/draw | |
| 2026-09-30 | PB-8.8 cached uniform memory, PB-8.10 fixed per-draw costs, PB-8.9 unchanged register writes dropped | mean 9.4-9.6; recorder 1650-1700 ns/draw | 24.3 median (GPU-bound) |
| 2026-09-30 | PB-8.11 sampler parameters memo | median 9.1-9.2, mean 9.0-9.5; recorder 1550-1650 ns/draw; 8.33 ms (120 fps) median from 5 to 40 s | |

From the push descriptors on, runs are compared by the recorder's busy time
per draw over the race frames (frames with more than 3,000 draws), since the
600-frame window of the medians covers different parts of the route from run
to run. The same build drifts about 4 % between batches, so only
interleaved pairs within a batch are compared.

**True costs by knock-out** (3x, single-sampled, each skipped alone with
a temporary switch, image wrong but frame timed): skipping resolve-sourced
texture reloads, all transfers or all resolves each takes the frame from
22.3 ms to 20.8 ms, the CPU floor at the time, so each costs at least
1.5 ms of GPU and reloads about 2.6 ms (GPU span 22.7 to 20.1 ms). The
executor's GPU profile overstates its phases several times over (reloads
11.6 ms profiled): each timestamp waits for the draws queued before it.
At 3x single-sampled the GPU is 97 % busy for about 22.5 ms, so the draws
themselves are about 16 ms: the pixel cost of the draws, not the
executor passes, is now the GPU's largest item.

**Where the 3x GPU frame goes** (2026-09-30, split and single-sampled
surfaces, GPU busy from `nvidia-smi` utilization times the frame): 6.4 ms
at 1x, 11.9 ms at 2x, about 22.5 ms at 3x, which fits a fixed 4.6 ms (the
per-draw front end of about 6,000 draws with pipeline, descriptor and state
changes, plus the executor's small passes) and 1.9 ms per 1x frame area of
pixel work. Every cheap lever tried on the pixel side moved the 3x GPU span
by 1 % or less, within run-to-run noise: fast pixel math (PB-1.8b), implicit
LOD for 2D fetches (PB-1.8a, 22.86 against 23.06 ms), robust buffer access
off (PB-1.8e), and skipping the 164 color and 134 depth attachment
write-after-write barriers per frame (22.64 against 22.80 ms). Skipping the
shadow-map draws (the 1040-pitch depth surface) saved about 0.5 ms. So the
3x GPU frame is raw draw work on the scene and post-processing surfaces:
what remains needs a GPU profiler to split it (PB-0.4) or a structural
change: rendering only the main scene at the full scale (PB-1.10), fewer
draws, or a lower internal scale with an upscaler (the fallback tier).

**Barrier census** (3x, per frame, from a temporary count by kind):
164 color and 134 depth same-layout attachment barriers between renderings,
about 90 texture-load scratch-buffer and 89 image layout transitions, 85
resolve attachment/sampled transitions each way, 76 compute-to-compute
buffer barriers each way (resolve writes and texture loads of the scaled
resolve buffer), and 47 shared-memory upload barriers each way.

## Gap analysis

| Stage | Today | Budget | Factor | Where the time is |
| --- | ---: | ---: | ---: | --- |
| GPU at 3x | 29 ms Vulkan (18.5 ms D3D12) | 7.0 ms | 4.2x (2.6x) | half in the executor's emulation passes (transfers, resolve, untile, clears), half in the draws on 4x-MSAA 4K surfaces; Vulkan adds backend overhead on both halves |
| GPU commands thread (Vulkan) | ~17 ms | 6.0 ms | 2.8x | per-draw descriptor sets and `vkUpdateDescriptorSets`, register writes, shared-memory range checks, texture and sampler re-derivation, pipeline lookup, swap wait |
| Title render thread | 6.5-7.8 ms | 6.0 ms | 1.1-1.3x | recompiled code: register file in memory, volatile guest accesses, MXCSR toggles; waits on the GPU thread's fence words |
| Simulation step | ~4.6 ms | 6.0 ms | fits | must stay one step per frame (PB-4) |
| Frame pipeline | 4-6 vblanks per frame | 2 | — | the title runs one frame ahead of the GPU commands thread and both end on vblank ticks; the GPU thread's sleep quanta cost 1-2 ms; the simulation's millisecond delta jitters and has no step cap |

**Where it stands after this backlog's work (2026-09-30)**, hidden race on
Vulkan with the split: at 1x the frame mean is 10.4-11.8 ms (about 90 fps)
from 20.8 ms, with the GPU recorder busy about 9.4 ms per 5,100-draw frame
(about 1.85 us per draw from 2.9) and the GPU about 6.4 ms; at 3x the GPU
holds the frame at 22-24 ms (from 29.1). The PERFORMANCE 120 preset (1x on Vulkan with FSR
1 to a 4K display) is therefore the path to 120, and it needs the recorder
near 7 ms: every Tier 1 and Tier 2 item is taken or measured, the remaining
per-draw cost has no item above 8 % of the thread (texture binding,
constant uploads, dynamic vertex data, register apply and executor
bookkeeping), and a guest frame's fences tie the title to the recorder, so
the last quarter needs a different renderer rather than more caching (see
PB-2.12). Native 4K (3x) at 120 is out of reach on this GPU: the draws'
pixel work alone is about 17 ms there.

## Fidelity trades this plan allows

Accepted by the maintainer on 2026-09-30 for the 4K target; each is a
setting with the faithful behaviour available, and each is checked by eye
on captures rather than by byte-identical replays.

1. **Single-sampled host surfaces at scale 2x and above.** The guest's 4x
   and 2x MSAA surfaces become 1-sample (or 2-sample) images. At 3x each
   guest pixel is still 9 host pixels, but 4K edges lose MSAA and
   alpha-to-coverage foliage and fences go hard-edged; `swap_post_effect
   = fxaa` is the cheap cover.
2. **Stencil dropped from ownership transfers** where no draw tests stencil
   on the destination before its next clear, and transfers skipped where a
   golden replay at 1x proves the destination is fully overwritten before
   it is read.
3. **Resolves that bypass the guest memory mirror** except for the resolves
   the CPU reads (thumbnails, one-off captures).
4. **Guest numerics changes** (codegen register locality, vector lowerings,
   an AVX2 baseline) gated by the pose-drift and save-payload-hash checks,
   not by bit-identical traces.
5. **Frame-loop hooks** that cap the simulation steps a frame may run and
   pin per-frame animations to real time.
6. **Pass refresh rates** (measured 2026-09-30, not taken): the race's
   1280-wide 1x depth-only pass is the sun shadow map (skipping it removes
   every shadow) and holds 18 % of the draws, the 1040-pitch depth pass
   another 11 %. Refreshing them every other frame would cut up to about a
   tenth of the recorder's work on average, but the shadows would trail
   the scene by a frame (about half a metre at race speed); a skip placed
   after target binding saved nothing, so it would have to drop the draws
   before their register and texture work. Measured that way too (the sun
   shadow pass and its resolves skipped on odd frames at the top of the
   draw path, 2026-09-30): 6.5 % fewer draws per frame but only about 2.5 %
   less recorder time (9.47-9.59 against 9.71-9.78 ms), since the depth-only
   draws are the cheap ones, so not worth stale shadows. On the GPU at 3x
   the same pass costs about 2.2 ms (24.2 ms median with it, 22.0 without;
   the 1040-pitch pass 0.2 ms), which is PB-1.10's case for rendering it at
   1x, the console's own shadow resolution.

## PB-0 Measure and instrument

Everything below is a prerequisite for judging the items after it; each is
small.

| Item | Work | Size |
| --- | --- | --- |
| PB-0.1 | **Done** (SDK `7a00843`; `gpu_recorder_busy_ns` added with the split, SDK `41ae267`): Vulkan writes `guest_frame_gpu_time_ns` (frame-open and swap timestamps), `draw_calls`, and the fence and submission-worker waits in `gpu_thread_fence_wait_ns`. The GPU span is first submission to swap and includes idle gaps when the CPU limits; GPU busy still comes from `nvidia-smi`. Vulkan per-frame GPU timing: the Vulkan command processor fills neither `guest_frame_gpu_time_ns` nor `draw_calls` in the performance CSV (both zero in every Vulkan run) and charges no fence or worker wait to `gpu_thread_fence_wait_ns` (`sdk/src/graphics/d3d12/command_processor.cpp:2932, 3488` only). Add frame-open and swap timestamps, the draw counter and the wait counters on Vulkan. | S |
| PB-0.2 | **Done** (SDK `0ecd9a2`): the Vulkan GPU profile times `texture_reloads` and `texture_loads`, logs transfer tile-passes per surface pair, and reports renderings and barrier batches per frame (3x: 336 and 686). Its phase times overstate (see the knock-outs in [Progress](#progress)). Vulkan executor phase parity: `texture_reloads`/`texture_loads` GPU phases (D3D12 `fh1_native_executor.cpp:2113-2119`) and the transfer top-pairs log (`transfer_volume_`, D3D12 `:776-780, 2121-2129`) exist only on D3D12; add both to the Vulkan executor, plus per-frame counts of renderings begun and barriers submitted. | S |
| PB-0.3 | **Also sampled at 1x with the split (2026-09-30, `.local/perf4k/vk1x-guest`)**: GPU recorder 79 % busy, simulation thread 46 %, render thread 42 % (its waits are mostly the GPU fences the recorder signals), decoder about 50-60 % with most of the rest in `WAIT_REG_MEM` yields: at 1x the recorder is the only thread near the frame budget. Thread attribution at the target rate. **Sampled 2026-09-30** (the busy shares above): `pinyon_shift_thread_sampler` over `GPU Commands`, `GPU Submission` and `Guest ` at 3x on Vulkan with the render limit at 120 (`.local/perf4k/vk3x-sampled`). Still to do: the same sample with `--lines 1` mapped to guest instructions for the render and simulation threads (PB-3.1), and count the CPU-visible PM4 packets per frame (`EVENT_WRITE_SHD`, `MEM_WRITE`, `COND_WRITE`, `REG_TO_MEM`, `XE_SWAP`; the packet recorder at `sdk/src/graphics/command_processor.cpp:722-747`), which bound the decode-to-record pipeline depth of PB-2.11. | S |
| PB-0.4 | **Needs a person**: Nsight Systems is installed, but its Vulkan trace needs registry writes and its GPU metrics need the GPU performance counter permission (`ERR_NVGPUCTRPERM`), both of which need an administrator; knock-out A/Bs stand in for it. One Nsight Graphics GPU trace of a 3x race frame on Vulkan to split the draws' GPU time between rasterizer/ROP, shading and front-end, and to time the transfer passes and the words compute individually. Decides how much PB-1.1 (fewer samples) against PB-1.8 (faster shaders) is worth. | S (tool install) |
| PB-0.5 | **In use (2026-09-30)**: the render-test routes capture at any scale, and 3x captures of `fh1-race-sync` compared by MAE against the faithful setting stand in for replays; every change above at 1x was checked the same way. Captures at 3x for fidelity checks: frame dumps and replays are gated to 1x (`command_processor.cpp:1078-1083`), so the aggressive items are judged by 3x route captures (`fh1-race-sync`, `fh1-free-roam`) compared by MAE against the faithful setting, with the 1x golden replays kept for bit-exact changes. Add a `fh1_debug_skip_transfers=<n>-<m>` cvar next to `fh1_debug_skip_draws` (`command_processor.cpp:54-63`) so transfer classes can be skipped in a replay and diffed. | S |
| PB-0.6 | **Refined (2026-09-30)**: from push descriptors on, recorder changes are judged by the recorder's busy nanoseconds per draw over frames with more than 3,000 draws, three interleaved pairs per change, since the 600-frame window of the medians moves along the route from run to run and batches drift by about 4 %. Frame medians stay on vblank steps (4.17 ms at the 120 limit); limits of 180 and 240 would give finer steps, but the frame-counted route scripts cannot run the race at those rates, and the simulation would tick faster. The protocol for every number in this backlog: hidden, seed `appdata-2026-09-27`, `fh1-race-sync` last 600 frames less 30, render limit 120, GPU profile off, three interleaved pairs for an A/B, `nvidia-smi` sampled alongside, reported as frame median and p95, GPU span, GPU busy, draws, vblanks and simulation steps per frame (`.local/perf4k/measure4k.ps1` is the reference script). | S |

## PB-1 GPU at 3x

Goal: a 3x race frame at or under 7 ms of GPU time on Vulkan. The
executor's passes are the first half, the draws on 4x-MSAA 4K surfaces the
second.

| Item | Work | Expected | Size |
| --- | --- | --- | --- |
| PB-1.1 | **Done, opt-in** (SDK `d5d3f07`, `fh1_scaled_msaa_single_sample`): Vulkan 3x race 29.1 to 22.3 ms, profiled transfers 10.3 to 4.4 ms; captures render correctly. **Single-sampled host surfaces at scale.** `GetOrCreateSurface` makes a `width*scale x height*scale` image with `samples = 1 << key.msaa` (`sdk/src/graphics/vulkan/fh1_native_executor.cpp:546, 571-575`) and `BindTargets` puts `msaa_samples` in the pipeline key (`:1449`; pipeline `sdk/src/graphics/vulkan/pipeline_cache.cpp:3419-3437`), so at 3x the scene's 4x surfaces are 3840x1536 images with 4 samples: 36 samples per guest pixel for ROP, depth, clears, transfers and resolves. Add a host sample mode for scale >= 2 (`fh1_host_msaa_mode`: native, 2, 1): image samples 1 or 2, `msaa_samples = k1X` in the render-pass key, `LayoutConstant`/`HostSample`/`GuestSample` remapped (`fh1_native_edram.hlsli:225-245, 262-330`), the non-multisampled transfer and resolve variants selected (`:640-647, 1680-1689`), `EnsureTransferWords` at 1 sample. Guest shaders need no retranslation: `kSysFlag_MsaaSamples` matters only to the FSI and sample-rate paths (`spirv_translator.cpp:3094, 3184-3195`). The 2-sample mode is the inverse of today's 2x-as-4x mapping. | ROP, depth and every executor pass on the 4x surfaces (12.5 M of 19 M draws) at a quarter of the sample traffic; the largest single GPU lever | M |
| PB-1.2 | **Deferred, off the 120 path (2026-09-30)**: at 1x the GPU has headroom (6.4 ms); at 3x the reloads it targets are about 13 full-frame (1280x720 at 3x, 33 MB) and 5 shadow-sized (1024 square R32F) textures per frame, 2.6 ms by knock-out, and aliasing saves bandwidth only where the mirror write can be dropped too (a resolve plus reload and a resolve plus direct write move the same bytes otherwise). **Resolve aliasing on Vulkan** (NP-9.1, deferred at 1x for 0.5 ms; worth 3-5 ms at 3x). Resolve into a storage-image view of the destination `VulkanTexture` (A2B10G10R10, R8G8B8A8, R32F, RGBA16F are storage-capable on NVIDIA) and mark its payload generation loaded so `FindOrCreateTexture`/`LoadTextureData` skips the untile (`:1832-1960`, `MarkRangeAsResolved` at `:1947`; `pipeline/texture/cache.cpp:347-375, 476-515`). Keep the mirror write for one-off resolves the CPU reads, `vulkan_readback_resolve` and frame dumps, and fall back to the mirror when a later fetch reads the range through a different key. First step, cheap on its own: port D3D12's direct reflection-cube import (`d3d12/texture_cache.cpp:2250-2300`). | removes the 88 resolve-sourced reloads per frame (2.6 ms profiled at 3x) and most of the resolve pass; removes the front buffer's 33 MB round trip | L |
| PB-1.3 | **Deferred, off the 120 path (2026-09-30)**: single-sampled surfaces already took the profiled transfers from 10.3 to 4.4 ms at 3x, and the rest costs at least 1.5 ms by knock-out; worth taking with the 3x quality tier. **Transfers without nine passes.** NVIDIA exposes neither `PSSpecifiedStencilRef` on D3D12 nor `VK_EXT_shader_stencil_export` on Vulkan (checked with `vulkaninfo`, driver 581.8), so the one-pass stencil export of NP-2.4 is AMD- and Intel-only. On single-sampled destinations (PB-1.1) the stencil byte can instead be copied from the transfer words buffer into the image's stencil aspect with `vkCmdCopyBufferToImage` (D3D12: `CopyTextureRegion` to plane 1), so a depth transfer becomes one depth draw and one copy instead of the loop at `:1155-1194`; multisampled destinations keep the bit passes. Then: skip the stencil passes for destinations no draw stencil-tests before their next clear (per-surface stencil-read census in the executor), and skip whole transfers a 1x golden replay proves unread (PB-0.5), starting with the two biggest pairs, the 4x/1x depth reinterpretation at base 0 and the 2x/4x one at base 128. Fewer transfers also remove their words dispatches, barriers and rendering restarts. | transfers from 7.7 ms profiled at 3x to about 1 ms | M |
| PB-1.4 | **Deferred, off the 120 path (2026-09-30)**: 0.3-0.6 ms at 3x; the swap's CPU side was taken by PB-2.8. **Present chain.** Today: HUD surface -> resolve to the mirror (33 MB at 3x) -> untile reload of the 2_10_10_10 swap texture -> `apply_gamma_pwl` into the presenter's guest-output image -> bilinear quad into the swapchain (`vulkan/command_processor.cpp:2497-2622, 2827-2846`; `vulkan_presenter.cpp:1723-1990`). Sample the executor surface that owns the front buffer's tiles (or the PB-1.2 texture) in the gamma pass, and write the swapchain directly when no scaling or CAS/FSR is selected. | four full-frame 4K passes removed, about 0.3-0.6 ms | S-M |
| PB-1.5 | **Measured 2026-09-30: attachment barriers are not the limiter.** Skipping the same-layout attachment write barriers (298 per 3x frame) moved the GPU span within noise (22.64 against 22.80 ms); the census is in [Progress](#progress). **Renderings and barriers.** One dynamic-rendering scope per change of bound surfaces or per pending barrier, LOAD/STORE always; texture loads call `SubmitBarriers(true)` per dispatch (`vulkan/texture_cache.cpp:1652`), shared-memory uploads end the rendering (`vulkan/shared_memory.cpp:283`), executor transitions are full-image barriers (`:469-533`). NP-12.4 counted about 300 renderings and 600 barriers per race frame; each drains a 4K pipeline. Batch the texture-load barriers per load, upload shared memory before the rendering starts, count both per frame (PB-0.2). | 0.5-2 ms | S-M |
| PB-1.6 | **Deferred (2026-09-30)**: clears are about 0.2-0.3 ms at any scale. **Clears** through `loadOp = CLEAR` where a resolve-clear or a full-surface clear precedes the next rendering, instead of `vkCmdClearAttachments` inside its own rendering (`:1558-1631`). | small; free once PB-1.1 lands | S |
| PB-1.7 | **Needs PB-0.4 (a person)**. **Draw-side GPU cost.** After PB-0.4: if ROP-bound, PB-1.1 covers it; if shading-bound, PB-1.8; if front-end-bound (about 6,000 draws with pipeline, descriptor and dynamic-state changes each), nothing short of merging draws helps and the floor is measured. | decides the order of the rest | — |
| PB-1.8 | **(b) done opt-in** (SDK `c8dc02c`, `spirv_fast_pixel_math`): 22.35 ms against 22.3-23.8 ms, within noise, no NaN pixels. **(a) measured, not adopted**: implicit LOD with bias for 2D fetches gave a GPU span of 22.85-22.87 against 22.99-23.12 ms. **(e) measured, not adopted**: `robustBufferAccess` off gave 23.87 against 23.76 ms. **Translated shader efficiency**, from an audit of the SPIR-V translator and the disc corpus (12,846 programs: 10,818 vertex, 2,028 pixel). The pixel shaders average 4.1 texture fetches and 47.6 ALU instructions, half of them `mul`/`mad`; everything below scales with pixels and applies to the DXBC path too where noted. (a) **Texture fetches** (`spirv_translator_fetch.cpp`): every computed-LOD fetch samples with explicit gradients (`OpDPdx/DPdy` scaled by `exp2(lod)`, `:1467-1636`) only to fold the fetch constant's LOD bias in, a rounding epsilon is always applied (size decode from the fetch constant, an `FDiv` and `FAdd` per axis, `:694-707, 847-941, 1088-1094`), signedness is resolved at run time with a second sample under `if (is_any_signed)` and a per-component `OpSwitch` (`:1382-1409, 1966-2043, 2207-2246`), then an exponent-bias `Ldexp` and `FMul` per component. Extend the cube change (SDK `9e34a49`) to 1D/2D/3D: implicit LOD with `Bias`; apply the epsilon only to point-filtered fetches; specialize signedness and bias per (shader, fetch constant) with a runtime fast path first and a mismatch counter before removing the fallback. (b) **ALU** (`spirv_translator_alu.cpp:190-278`, `spirv_builder.cpp:42-53`): every float op carries `NoContraction`, so the driver never forms an FMA, and every `mul`/`mad` adds the SM3 zero check (`NMin(|a|,|b|) == 0 ? 0 : a*b`), about five ops instead of one FFMA on half the pixel ALU. Drop both for pixel-shader colour math behind a cvar (keep them for vertex position math and anything feeding depth); the same change applies to DXBC (`dxbc_translator_alu.cpp:85-100`, `dxbc_translator.cpp:3125-3131`). Risk: shaders relying on `0 x Inf = 0` masking (the HDR paint and glass shaders were exactly this sensitive); validate with the goldens at tolerance, the free-roam frame 1800 glow count and register captures on `BDA312E0D00025E9` / `410E568A69EC236A`. (c) **Control flow** (`spirv_translator.cpp:593-705, 1299-1324, 1425-1616`): programs with jump targets become one `OpLoopMerge DontUnroll` loop with a per-lane program counter and an `OpSwitch` (`DontFlatten`) over the labels, so every temporary is loop-carried and the driver cannot propagate or eliminate across cases. 372 of 2,028 pixel shaders have jumps (511 forward, 2 backward, 10 loops), all reducible to nested `if`/`if-else`; vertex shaders are 99.2 % label-free. Emit forward jumps as `OpSelectionMerge` regions (bool-constant jumps uniform, predicated ones keeping the quad-uniform AND from SDK `dfed4c8`), loops as real loops, and keep the PC loop as the fallback for the two backward-jump shaders; drop `DontFlatten` on short exec conditionals. (d) **Resolution scale as specialization constants** (`fetch.cpp:993-1004`, `spirv_translator.cpp:3150-3171, 3262-3301`; `pSpecializationInfo` is null at `pipeline_cache.cpp:3213-3267`): identical code after folding, one pack for every scale, which is NP-4.9 for shaders. (e) **Vertex fetch**: endianness is two runtime branches per dword (`:3997-4064`) and `robustBufferAccess` is on (`vulkan_device.cpp:647`), which NVIDIA implements with per-access bounds checks; make the endianness a specialization constant, bind shared memory as an `R32_UINT` texel buffer (NVIDIA's 2^27-texel limit is exactly 512 MB; verify) and turn robust access off. (f) Never enable `depth_float24_convert_in_pixel_shader` (`flags.cpp:20`): it forces sample-rate shading, four pixel-shader invocations per pixel at 4x. | (a) and (b) high at 3x: a large share of pixel time; (c) medium-high on the expensive material shaders; (d) packaging; (e) low-medium | (a) S-M, (b) S, (c) M, (d) S, (e) S |
| PB-1.10 | **Tried a shortcut, not adopted (2026-09-30)**: depth-only draws on 1x-MSAA depth surfaces rendered into a 1x copy of the surface, blitted down before and back up after (whole surface, then only the draws' scissor rectangles). The shadow pass interleaves with its resolves, so every frame paid about 4.7 down-and-up blit pairs plus the rendering breaks around them: the 3x race went from 24.0 to 25.0 ms. It needs the resolves to read the 1x image, or a real per-surface scale. **Sized (2026-09-30)**: the sun shadow map is the 1280-wide 1x depth surface at EDRAM base 0 (skipping it removes every shadow); at 3x it costs about 2.2 ms of GPU, so rendering it at 1x would recover about 1.9 ms at 3x and 0.7 ms at 2x. Not implemented: the executor's surfaces, transfers and resolves all assume one scale. **Mixed resolution: only the main scene at the full scale.** At 3x every surface is scaled, including shadow maps, reflection cube faces and the half- and quarter-resolution post-processing chain. The texture cache already tracks per texture whether its memory came from a scaled resolve (`scaled_resolve_pages_`) and translated shaders un-scale per texture (`textures_resolution_scaled`), so the missing parts are a per-surface scale in the executor (surfaces, viewports, transfers and resolves between surfaces of different scales) and a policy (full scale for the 1280-wide scene and composite surfaces, 1x for the rest). Draws into 1x surfaces then pay a ninth of today's pixel cost at 3x. Pixel-position (`param_gen`) and memexport shaders bake the scale in, so those draws must stay on full-scale surfaces or get 1x variants. | depends on the scene/post split of the 17-19 ms of pixel work; needs PB-0.4 to size | L |
| PB-1.9 | **Needs PB-0.4 (a person)**: the gap at 3x is now 24.0 ms Vulkan against 19.2 ms D3D12 median. **Vulkan is slower than D3D12 on the same GPU work** (3x profiled: executor frame 30.3 ms against D3D12's 24.1 ms, transfers 10.3 against 7.7 ms). Candidates, in order: the rendering restarts and full-image barriers around transfers and texture loads (PB-1.5), `robustBufferAccess` (PB-1.8e), and the per-draw dynamic state; PB-0.4's trace settles it. | closes the backend gap before the levers above | S to find |

## PB-2 GPU commands thread on Vulkan

Goal: under 6 ms busy for a 6,000-draw frame. Today about 17 ms: draws
59 % (2.0 us per draw), of which `UpdateBindings` 16 % with the driver's
descriptor allocation and writes 40 % of that; register writes, dispatch,
texture and sampler re-derivation, shared-memory range checks and the swap
wait make up the rest. Three tiers; the first is low-risk single-thread
work, the second moves decode off the recording thread, the third is the
native draw ABI.

**Tier 1, single-thread (estimated 17 to about 10 ms):**

| Item | Work | Removes | Size |
| --- | --- | --- | --- |
| PB-2.1 | **Done** (push descriptors, SDK `40844ef`): pixel texture sets with at most 32 bindings use a push descriptor layout, recorded into the tape so the driver writes them on the submission worker; a push is recorded only when the contents or layout change. Five interleaved pairs: 2157 against 2178-2223 ns per draw, frame mean 12.80 against 13.25 ms. It also applies the pipeline-layout compatibility rule that was computed but never used (a set bound under an incompatible layout was taken as bound). **Partly done**: unchanged texture sets reused within a frame (SDK `5288701`, 29 % of requests), constants bound as dynamic uniform buffers from sets cached per frame by buffers and ranges (SDK `32469bb`). Push descriptors remain. Descriptors: every draw rebuilds both texture sets (`vulkan/command_processor.cpp:7038-7041`), allocates a new constants set with five writes whenever any constant buffer changed (`:7115-7149`) and issues one `vkUpdateDescriptorSets` (`:7196`). Use `VK_KHR_push_descriptor` (exposed by the driver) for the texture and sampler sets, recorded into the tape so the driver work lands on the submission worker, and make the constants set `UNIFORM_BUFFER_DYNAMIC` with one set per 2 MiB upload page and five dynamic offsets per draw (`CmdVkBindDescriptorSets` already carries offsets, `deferred_command_buffer.h:63-90`). No SPIR-V change. `VK_EXT_descriptor_buffer` (also exposed) is the follow-up if the worker becomes the limit. | about 1.5 ms on this thread | M |
| PB-2.2 | **Done** (SDK `05f449c`): plain runs stored with one swap-copy, Vulkan splits runs by constant class; 1x 20.79 to 19.49 ms. Register writes: bulk paths exist only for float, bool and fetch constants (`:2260-2308`); every other type-0 range goes through the virtual `WriteRegister` per register with `load_and_swap` (`sdk/src/graphics/command_processor.cpp:380-537`). SIMD `copy_and_swap` for every range, then side effects only for the few special registers (scratch, `COHER_STATUS_HOST`, `DC_LUT_*`, `VGT_EVENT_INITIATOR`) that intersect it. | 1.8-2.2 ms | S |
| PB-2.3 | **Done** (SDK `640349b`): 1x 19.49 to 18.36 ms. Samplers: `GetSamplerParameters` and the `samplers_` lookup run for every sampler of every draw (`:3970-4013`, `vulkan/texture_cache.cpp:674-789`); D3D12 gates on the six fetch dwords plus the binding word (`d3d12/command_processor.cpp:4047-4060`). Port the gate. | 0.5-1.0 ms | S |
| PB-2.4 | **Rest measured (2026-09-30)**: keeping vertex buffers resident when a fetch constant is rewritten with the same words measured 1965 against 1888 ns per draw (rewritten fetch constants nearly always change); what `RequestRanges` still costs is mostly real uploads of the title's dynamic vertex data and their write-watch re-arming. **Lock part done** (SDK `36c24fc`): the page-valid scan no longer takes the global critical region (half of `RequestRanges` was waiting for it); the range front cache remains. Shared memory: `RequestRanges` per vertex and index buffer per draw takes the recursive global lock and scans page bitmaps (`shared_memory.cpp:423-568`), re-triggered because fetch-constant writes clear `vertex_buffers_in_sync_` (`:2223, 2306, 4221-4268`). A front cache of ranges validated this frame with an invalidation epoch bumped by `MemoryInvalidationCallback` and `RangeWrittenByGpu`, and vertex-buffer states kept when a fetch constant is rewritten with the same value. | about 0.8 ms | S-M |
| PB-2.5 | **Binding memo done** (SDK `77a9338`): each fetch constant slot keeps its last four derivations (key, swizzle, signs, textures) by the six fetch words, valid until bindings are reset (a texture destroyed or outdated); 1925 against 1985 ns per draw, D3D12 replays 4/4. The Vulkan side keeps a texture's last view per signedness (SDK `a41ba75`). **Done** (SDK `b2b0d78`): a binding rewritten with the same six fetch words is only marked in sync; recorder busy 14.18/13.88 against 14.51/14.19 ms. Compare-before-upload of the fetch and bool/loop constant blocks was measured and dropped (the extra copy cost what it saved). Texture bindings: every rewritten fetch constant re-derives its binding (`pipeline/texture/cache.cpp:559-655`) and then `MarkAsUsed`/`SetUsage` and a linear pending-barrier scan (`:3089-3129`). Keep the raw six dwords per binding and compare before deriving; touch usage only when the binding changed within the submission. | 0.5-0.7 ms | S |
| PB-2.6 | **Done as a register state epoch (SDK `f456d2a`, `da6b017`, `368a1dd`)**: an epoch bumped whenever a register other than the shader constants and the per-draw ones (index buffer, draw and event initiators, scratch, coherency) changes value; a census found 58 % of race draws change only constants, fetch constants and those per-draw registers. While the epoch holds, the last draw's pipeline (with the shaders, primitive, controls and render pass; 1900 against 1967 ns per draw), shader modifications and translations, host viewport and executor target preparation are reused (1904 against 1975, all three pairs better); D3D12 replays 4/4. Measured and dropped on the same basis: a system-constants skip (the guest index base is written into the constants for every guest-DMA indexed draw, so they change almost every draw; 1891 against 1841) and a direct-mapped front on the executor's surface map (1853 against 1876, inconclusive). **More measured, not adopted (2026-09-30)**: skipping draws that can write no depth, stencil or color (about 4 % of draws) before their texture and binding work: 10.56 against 10.33 ms recorder busy per frame. Coalescing shader constant writes on the decoder (recording each written range once per draw with its final values; the title writes about 17 register runs per draw: 167 float, 25 fetch and 35 other words) made the recorder's register path heavier (8.6 % against 7.5 % of its time) and the decoder busier. The plugin built with AVX2, BMI2 and `-O3` measured 1901 against 1885 ns per draw (shipped builds are Release, already `-O3`). **Measured alongside, not adopted**: two ways to cut float constant uploads. Gathering into host memory and reusing the last upload when the bytes match hit 32 % of uploads but made `UpdateBindings` heavier (SDK `4a5ef52`, dropped in `ba4d0d4`); comparing constants as the recorder writes them and keeping the upload valid on an unchanged rewrite measured 2054 against 2029 ns per draw. The upload copy itself (about 7 % of the recorder, into write-combined memory) stays for PB-2.12. State derivation: `UpdateSystemConstantValues` (`:6338-6836`), `GetHostViewportInfo` and `GetCurrentStateDescription` (`pipeline_cache.cpp:1502-1709`, which repeats the polygonal and rasterization tests of `IssueDrawImpl`) recompute every field each draw. A dirty bitset over the ~40 registers they read, set in `WriteRegister`, skips each when clean; the pipeline lookup's XXH3 (`:1102-1165`) follows the same mask. | about 0.7 ms | S |
| PB-2.7 | **Done** (SDK `efd57a9`): the decoder hashes the microcode (PB-2.11) and the recorder answers repeated loads from a 64-entry direct-mapped table by hash before the map; with the view cache 1909 against 1934 ns per draw. `LoadShader` hashes the ucode with XXH3 and looks it up on every `IM_LOAD` (`pipeline_cache.cpp:899-921`). Memoize by guest address and dword count, invalidated by a memory watch on the ucode pages. | about 0.5 ms | S |
| PB-2.8 | **Done** (SDK `960d853`, `vulkan_present_on_submission_worker`): the presenter's step after the refresher (ready image, paint, the refresher fence) runs as a submission-worker job after the swap's submission, so the swap no longer waits for the worker; three pairs: 1924-1971 against 2076-2151 ns per draw, frame mean 11.78 against 12.49 ms. Splitting submissions every 256 draws instead of 1024 was measured first and changed nothing (2126 against 2124 ns per draw). Found on the way (SDK `a331d91`): the plugin compiled `Presenter` without `REX_HAS_FIDELITYFX_SDK`, a smaller class than the runtime's, so any inline member access after those fields read the wrong offset. Swap: the thread waits for the submission worker at every swap (`:5683-5687`) and then refreshes the guest output itself (`:2481-3019`). Queue the presenter refresh as a worker job and split submissions every 256 draws so the last job is short. | 0.5-1.0 ms | M |
| PB-2.9 | **Rest folded into PB-2.6's epoch memos (2026-09-30).** **Executor part done** (SDK `e36210d`): target preparation is skipped when one of the last four preparations of the same targets in the same tile generation claimed at least as many tiles (without the draw's extent estimate when it covered the surface), marking stencil bumps the generation only on a change, and a draw continuing the open rendering skips the attachment infos; 2066-2104 against 2125-2157 ns per draw. With the skip off entirely the recorder costs 2583-2679 ns per draw, so preparation hit rate is worth watching. Also done alongside: float constants gathered in runs (SDK `dc99251`) and a shader's last translation lookup remembered (SDK `f9dd4f1`). Executor per draw: `EstimateMaxY` runs before the signature test, a `std::vector` of bases is allocated per miss, `FindSurface` walks a `std::map` twice and `DrawRenderingId` is computed twice (`fh1_native_executor.cpp:1374-1408, 1447-1456, 1499-1521`). | about 0.2 ms | S |
| PB-2.10 | **Not pursued**: the submission worker is 25-30 % busy at 1x and the fence handling is a small part of it; nothing on the frame's critical path. Fences: `vkResetFences` and fence vectors per submission (`:5636-5680`) against one timeline semaphore. | small | S |
| PB-2.13 | **Measured, not needed on this hardware (2026-09-30)**: the 387 stored pipelines are created in about 21 ms at start (the NVIDIA driver keeps its own pipeline disk cache) and the race has no pipeline cache misses, so a persisted `VkPipelineCache` and extended dynamic state would change neither start time nor frame time here; they remain for drivers without a disk cache. Pipelines: no `VkPipelineCache` exists (`vkCreateGraphicsPipelines(device, VK_NULL_HANDLE, ...)`, `pipeline_cache.cpp:3623`), so every start recompiles the 397 stored pipelines, and a first-seen pipeline creates its placeholder synchronously on this thread (`:1176-1194`). Persist a `VkPipelineCache` next to the `.xpso` storage, and use extended dynamic state (exposed by the driver) for cull, topology, depth-stencil and blend so the 397 descriptions collapse towards the 306 shader pairs. Stutter and start time, not steady frame time. | start time; no hitch on a new pipeline | S-M |

**Tier 2, decode-to-record split (PB-2.11, L). Done, opt-in** (SDK
`9362a07`, `7440c33`, `gpu_record_thread`; Vulkan): the GPU commands thread
decodes against a shadow register file and records register runs and
backend work in batches; a "GPU Recorder" thread applies them in order. Fence
writes and interrupts are recorded rather than waited for, so the title sees
a fence only once the recorder has consumed the draws before it; MEM_WRITE,
COND_WRITE, REG_TO_MEM and occlusion queries wait for the recorder. Draws
are fixed records (a closure per draw cost a heap allocation), and IM_LOAD
hashes microcode on the decoder. Race mean 16.46-16.75 ms against 17.67 ms
unsplit; `fh1-buy-car` saves a rendered card and `fh1-modes-sync` passes.
The recorder is now about 83 % busy and the decoder 40 %, so the recorder's
per-draw cost is what the frame waits on (after PB-2.1, PB-2.8 and PB-2.9:
about 1.95 us per draw, 10 ms for a 5,100-draw race frame, 80 % busy; after
the binding memo and caches about 1.9 us). A race frame's draws by target
set: the 4x-MSAA main scene 61 % (about 4,050), a 1280-wide 1x depth-only
pass 18 % (1,200), the 1040-pitch shadow depth 11 % (714), the rest small
passes; halving the depth passes' rate would cut a fifth of the recorder's
draws but leave shadows a frame stale (about half a metre at race speed),
so it is listed as a fidelity trade rather than taken. Before recording fences, syncing
at each of the ~30 fence writes per frame left the decoder waiting half its
time. Per race frame the stream has about 4,500 draws, 280
`EVENT_WRITE_EXT` (constant screen extents, no sync needed), 25-30
`EVENT_WRITE_SHD` fences, 5 interrupts and one swap. Design notes: A decoder thread keeps
PM4 dispatch, register writes into a shadow `RegisterFile`, `WAIT_REG_MEM`
and `LoadShader` hashing, and emits (register run, draw, copy, swap,
CPU-visible packet) records over an SPSC queue; the recorder owns the real
register file, the caches, the tape and submissions. Ordering the code
requires: `EVENT_WRITE_SHD` stores its fence word at decode time
(`command_processor.cpp:1307-1328`) and wakes the title
(`PinyonShiftGpuFenceWait`), after which the title reuses dynamic vertex
and index memory, so either the recorder executes every CPU-visible packet
in order (`EVENT_WRITE_SHD`, `MEM_WRITE`, `COND_WRITE`, `REG_TO_MEM`,
`INTERRUPT`, `XE_SWAP`) or the decoder stalls at each until the recorder
has consumed everything before it; PB-0.3's packet count bounds the depth.
`FlushCpuVisibleResults` must drain the GPU when one-off readbacks are
pending, so the recorder publishes that state. Register side effects
(scratch writeback, `DC_LUT`, `COHER` dirty bit, the fetch/float/bool
invalidations at `vulkan/command_processor.cpp:2190-2308`) replay on the
recorder. Expected: decoder about 2.4 ms plus the `WAIT_REG_MEM` sleeps
that finally overlap recording; recorder about 7 ms after Tier 1.

**Tier 3, native draw ABI (PB-2.12, XL; NP-9.5 revived). Assessed, not
pursued (2026-09-30)**: measured against today's recorder, its parts do not
add up to the 5 ms it promised. Shaders reading the raw 256-entry float
arrays would upload 4 KB per stage per change where the gather uploads
about 680 bytes per draw; texture descriptors already cost little after push
descriptors and the binding memo; and the system constants change almost
every draw anyway (the guest index base is in them). The recorder's
remaining cost is spread across texture binding (about 8 % of the thread),
constant uploads (7 %), register apply (7 %), dynamic vertex uploads (4 %),
primitive processing (3 %) and executor bookkeeping, so a quarter less
needs a renderer that consumes the title's command stream natively rather
than a new draw ABI for this one. The original analysis: what Tier 1
cannot remove is the per-draw float-constant gather (about 1 ms), the
image-info building for texture sets and the per-draw system constants.
A pack format v4 whose shaders read the raw 256-entry float register array
(one memcpy or delta upload per stage), take texture and sampler indices
from a small per-draw record (bindless; the SPIR-V translator has no
non-uniform-indexed array mode today) and split system constants into
pass-level and per-draw blocks brings the recorder to about 5 ms. This is
the boundary between "Xenia backend with native surfaces" and a native
renderer, and it is what makes 120 fps safe rather than marginal.

## PB-3 Guest CPU

Goal: the render thread's frame and the simulation step each 30 % faster,
so both hold 120 Hz with margin. The audit of the generated code
(76,502 functions, 599,974 load and 431,380 store sites, built with
`-O3 -msse4.1 -mfma -ffp-contract=off -fasync-exceptions`, no LTO or PGO)
finds the register file in memory: every guest register write is a store
to `ctx`, every guest access a `volatile` load or store preceded by a
four-instruction select for the physical-heap skew
(`REX_PHYS_HOST_OFFSET`, `pch_h.inja:140-164`: `stw r12,-8(r1)` is eight
host instructions), every compare writes four condition bytes (227,708
sites, six instructions each), `__savegprlr`/`__restgprlr` are real calls
storing 18 byte-swapped words, 56,860 functions open with a
`switch (ctx.dispatch_address)` of interior-resume aliases (342,683 in
all), MXCSR is toggled with 44,598 conditional checks and 6,090
`ldmxcsr` sites, VMX vectors are byte-reversed with `pshufb` at 42,124
sites and stored back to `ctx` after every op, `vmaddfp` is a separate
multiply and add even on the FMA baseline, and `vmsum3/4fp128` are
35-instruction scalar-double helpers. In a leaf `bdnz` loop
(`sub_82AF85F8`) one store per guest instruction, not the ALU work, limits
throughput. Calls target weak aliases (`sub_X -> __imp__sub_X`) so Clang
cannot inline guest calls even under LTO.

**Why the locality options are off, and how to turn them on.** The
runtime resumes guest code at an interior PC: `XThread::Execute` runs a
`setjmp` loop, and the title's stack switch (`KeSetCurrentStackPointers`
-> `Reenter`) `longjmp`s back to it and re-dispatches at `ctx->lr` with
`dispatch_address` set, so the owning function enters through its resume
`switch` expecting every register in `ctx` (`sdk/src/system/xthread.cpp:776-839`,
`xboxkrnl_threading.cpp:294-299`, `function_dispatcher.cpp:85-87`); guest
`setjmp`/`longjmp` copy the whole `ctx`; two mid-asm hooks take `ctx`
itself. The protocol that makes locals safe: reload localized registers
from `ctx` on the resume path only; spill before `ppc_setjmp`/`ppc_longjmp`
and reload after; spill and reload around the imports that switch context
and the two `ctx` hooks; mark the functions that restore r14-r31 before the
stack switch as `share_registers` (the mechanism exists; find them from the
`stack.reentry.first lr=` trace); keep `skip_lr` off because the runtime
reads `ctx->lr` to re-enter.

| Item | Work | Expected | Size |
| --- | --- | --- | --- |
| PB-3.1 | **Profiled 2026-09-30 at 1x (split, render limit 120)**: both guest threads are flat, no function above 3 % (`sub_82526248` 2.9 % on the simulation thread, `sub_824168B0` 2.0 % on the render thread), and they are 46 % and 42 % busy against the recorder's 79 %, so PB-3.2 to PB-3.11 are off the 120 fps path while the recorder is the limit; they stay listed for when it is not. **Instruction-level profile first.** `pinyon_shift_thread_sampler --lines 1` on `Guest 825A6320` and `Guest 8255AE10` (no elevation needed) mapped with `tools/map-generated-lines.py`, or the WPR capture (`tools/capture-cpu-profile.ps1`, elevated) through `tools/summarize-cpu-hotspots.py`: which guest functions and instruction classes the render thread's 6.5 ms and the simulation step's 4.6 ms are made of. Sizes PB-3.5 and PB-3.7. | decides the order below | S |
| PB-3.2 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Register locality**: `non_volatile_as_local`, `non_argument_as_local`, `cr_as_local` (then `ctr`/`xer`) with the resume protocol above (`sdk/src/codegen/function_graph.cpp:539-552`, `builders/context.cpp:47-112, 201-232`). Removes the write-through store on most register writes and all 50,077 save/restore calls, and lets Clang forward and eliminate across blocks. Bit-identical. | 15-30 % of guest CPU; the only lever large enough alone | L |
| PB-3.3 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Offset-free accesses where the address is provably virtual**: stack (r1), TLS (r13), `lis`-derived constants below 0xE000 and image addresses take macro variants without the physical-heap select, tracked per GPR like the existing `mmio_base_regs` (`builder_context.h:41-54`, `context.cpp:544-622`). Guest stacks live at 0x70000000, so the select is dead there. | 4-10 %; mechanical and safe | M |
| PB-3.4 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Fused `vmaddfp`/`vnmsubfp`/`vmaddcfp128`** on the FMA baseline (`simde_mm_fmadd_ps`, `builders/vector.cpp:93-113`, 8,128 sites): one rounding as VMX defines it, so likely closer to the console than today, but a numerics change gated by pose drift and the save hash; the SSE4.1 baseline keeps the two-op form. | small overall, halves the FP ops of vector loops | S |
| PB-3.5 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **MXCSR toggling**: propagate the flush-mode state across labels and calls (`function_graph.cpp:571`, `context.cpp:379-388`) instead of forgetting it, and measure FTZ/DAZ permanently on as the aggressive variant (changes only double-denormal results). | unmeasured; each `ldmxcsr` serializes | S-M |
| PB-3.6 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Call overhead**: codegen inlining of tiny leaf callees (no calls, hooks or resume aliases; a TOML denylist keeps hookable functions out) and a cheap out-of-line `if (dispatch_address) goto resume` instead of the full `switch` on entry. | 3-6 % | M |
| PB-3.7 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Bit-identical SIMD `vmsum3/4fp128`**: `cvtps2pd`, `mulpd`, ordered adds and branchless fix-ups replace the 35-instruction helper (`sdk/include/rex/ppc/intrinsics.h:124-166`), preserving the reduction order; the `ppc_tests` fixtures cover it. | 1-3 %, more in collision code | S |
| PB-3.8 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Non-`volatile` guest accesses** with compiler barriers at labels, calls and the (currently empty) `sync`/`lwsync`/`eieio`/`isync` lowerings (`builders/system.cpp:40-50`), so spill and reload pairs fold. Risky: polled words and cross-thread flags depend on `volatile` today. | 2-6 % | M |
| PB-3.9 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Plugin side measured (2026-09-30)**: profile-guided optimization of the GPU plugin (instrumented race run, `llvm-profdata`, `-fprofile-use`) measured 1765/1701 against 1711/1724 ns per draw over two clean pairs, and an AVX2, BMI2, `-O3` plugin 1901 against 1885: neither pays on the recorder, so neither is kept. **Build flags**: drop `-fasync-exceptions` (no SEH scopes are generated), re-measure PGO (`PINYON_SHIFT_RECOMP_PGO`) against guest-thread CPU rather than frame time, AVX2 only for the variable shifts. | small each; free | S |
| PB-3.10 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Vector lowerings**: `stvlx`/`stvrx`/`stvebx` byte loops and the per-lane `vpkd3d128`/`vupkd3d128`/`vsrw` become mask and blend sequences (`builders/memory.cpp:599-644`, `vector.cpp:997-1010, 1171, 1388`). | minor | S |
| PB-3.11 | **Deferred with PB-3.1's finding**: off the 120 path while the recorder is the limit. **Runtime overheads on guest threads**: count write-watch faults per guest thread (60-70 `VirtualProtect` calls per race frame, each a VEH fault, the global lock and a TLB shootdown), the global-lock contentions (about 260 per frame, every event and wait) and `RtlEnterCriticalSection` spins on the render and simulation threads, then take the direct object pointer in the dispatch header and 64 KiB watch granularity if they show on the critical path. | unknown until counted | S to count, M to fix |

## PB-4 Frame pipeline, pacing and HFR

**How the frame is paced today** (from the generated code and the SDK).
The guest vblank runs on the host `GPU VSync` thread at twice the render
limit or the display refresh (`sdk/src/graphics/graphics_system.cpp:54-58,
189-201`; the limit is hot); each vblank runs the guest's interrupt
callback under the global lock (`:391-426`), whose D3D handler
(`sub_829EEC48`) bumps the vblank counter, completes the queued swaps whose
target vblank has arrived and sets an event. The simulation loop
(`sub_823ED888` on `Guest 8255AE10`) ticks once per two vblanks
independently of rendering: 2.38 ticks per 19.9 ms frame, 1.00 per 8.33 ms
frame in the CSVs. The render thread (`Guest 825A6320`, loop
`sub_8259F3E8`) presents through `sub_829EFB30`: fence insert and ring
kick, `VdSwap`, then `sub_823E91F0` waits for the **previous** present's
fence, so the title runs at most one frame ahead of the GPU commands
thread, with a swap-queue throttle at 15 pending swaps; the fence predicate
`sub_829F04A8` is hooked to spin 20 us then block up to 1 ms on
`WaitForGpuWrite` (`src/native_renderer/graphics_hooks.cpp:105-147`). On
the GPU commands thread the ring-empty wait is 500 `SwitchToThread` calls
then a 5 ms event wait (`sdk/src/graphics/command_processor.cpp:246-266`),
and `WAIT_REG_MEM` yields up to 2 ms then `Sleep`s at least 1 ms
(`:1137-1145`). A race frame's draws take the thread about 14.6 ms at 1x
and it then waits 1.5-1.8 ms in `WAIT_REG_MEM` for the tick, which is why
frames land on 4, 5 or 6 vblanks and never between.

**The frame-rate ceiling is therefore the GPU commands thread and the
GPU, not the title.** The simulation costs 4.6-5.1 ms per tick (45 %
headroom at 120 Hz) and the render thread 6.5-7.8 ms per frame (6-22 %,
which is why PB-3 is not optional). No
pacing change is needed: the vblank stays at twice the target; on a 60 Hz
display `pinyon_shift_fh1_render_fps_limit = 120` with `host_present_fps_limit
= 60` shows every other source frame.

**The variable delta** (`sub_823ED888`, `.local/generated/default/pinyon_shift_recomp.254.cpp:458-712`):
elapsed time is read from a millisecond clock as an integer; 16 or 17 ms
snaps to 1/59.94 s with a residual accumulator; the only clamp is
`elapsed > 4000 ms -> 16`, and `f31 = max(f31, 0.0001)`. So a long frame
or a long fence wait is integrated as one big step (NP-4.10's "catching
up" at 4x), and at 120 fps the delta alternates 8 and 9 ms, a 6 % jitter
between ticks. The value is stored at `owner+448` (`0x823EDB84`), where
`PinyonShiftObserveSimulationDelta` already rewrites `f31` for the trainer.

| Item | Work | Expected | Size |
| --- | --- | --- | --- |
| PB-4.1 | **Measured, not adopted (2026-09-30)**: a 200 us high-resolution sleep after the yield phase instead of the millisecond `Sleep` changed nothing (GPU commands thread working time 15.35-15.81 against 15.57-15.74 ms), because the 2 ms yield phase already covers nearly every wait. **Deadline waits on the GPU commands thread**: the `Sleep(>= 1 ms)` in `WAIT_REG_MEM` and the 5 ms idle wait overshoot by 1-2 ms, 12-24 % of an 8.33 ms frame. The vblank deadline is known (`last_frame_time + interval_ticks`, `graphics_system.cpp:224`): wait on it with `SleepUntil`, or signal a host event from `MarkVblank` as `WaitForGpuWrite` does for fence words. | up to 2 ms of a 120 fps frame | S |
| PB-4.2 | **Done, opt-in** (project `7ff6b5e`, `pinyon_shift_host_simulation_delta`, `pinyon_shift_max_simulation_step_ms`): the race passes at 1x and 3x with simulation-to-wall ratios equal to the title's own delta (1.000, 0.958). **Host-measured simulation delta with a cap** in `PinyonShiftObserveSimulationDelta`: `steady_clock` between ticks at microsecond resolution, clamped to `[0.0001, pinyon_shift_max_simulation_step]` (default two target ticks, 0.0334 s), time scale applied after. Removes the millisecond jitter at 120 Hz and the catch-up burst in one place; the game slows under load instead of jumping. Gates: `expect-simulation-time 0.95 1.08`, the pose baseline and the save payload hash (the 16/17 ms snap disappears at a 60 fps limit). Optional deterministic mode: quantize to k x 1/120 with an accumulator. | correctness at 120 Hz and under load | S |
| PB-4.3 | **Deferred to a reverse-engineering session (2026-09-30)**: `sub_82AE8AE0` turned out to fill the 92-byte presentation parameters at start, not an animation stepper. Procedure: take `snapshot` steps on `fh1-race-sync` in the crowd section at render limits 30 and 120 with the route clocked by wall time (`clock_hz`), run `tools/scan-guest-snapshots.py` on each, and keep the floats whose step per second scales with the frame rate (4x at 120); those are the per-frame steppers to trace to their writer and hook to real time. First pass run (2026-09-30, `.local/pb43/race-snap.fh1test`, snapshots 10 frames apart in the race at limits 30 and 120): about 1,600 steady floats per run, but the heaps differ between runs so addresses do not line up, and the step census is dominated by unit-step counters present at both rates; the crowd's phases likely derive from one clock, so the next step is poking the candidate clocks one at a time with the route's `poke` and watching the crowd in the captures. **Per-frame animation steppers (NP-3.7)**: the crowd and the purchase animation run fast at high rates; `sub_82AE8AE0` multiplies the video mode's refresh rate by a constant into `obj+68` and is the first candidate for a refresh-derived step; once an updater is found, scale its increment by `delta / (1/30)` at the constant load. Reproducible by route (crowd) at 30 fps against unlocked, synchronized by game time. | correctness | M |
| PB-4.4 | **Measured, not adopted (2026-09-30)**: `latency_critical_thread_placement` (above-normal priority for the main guest, GPU and vblank threads; the 5800X has no hybrid cores) gave 1926/2002/1890 against 1875/1891/1870 ns per draw. **Thread placement for the measurement and the preset**: the busy host threads in a race are GPU Commands, the simulation loop, the render thread, one more guest thread and GPU Submission (2.9 cores at 60 fps); on the 8-core part the only risk is SMT-sibling pairing of GPU Commands with the simulation or render thread. Pin the three to distinct physical cores when measuring 120 fps (`latency_critical_thread_placement` exists, off by default) and adopt it in the preset if it holds p95. | p95 | S |
| PB-4.5 | **Measured, not pursued (2026-09-30)**: a new `critical_region_blocked_ns` column (SDK `f9c9e00`) shows 149 contentions and 0.34 ms blocked per race frame summed over all threads (p95 0.86 ms), so restructuring the lock would recover at most a fraction of a millisecond, most of it off the recorder. **Global lock on the frame path**: the vblank interrupt runs guest code under the process-wide recursive mutex 7 times per 8.33 ms frame (2 vblanks plus 5 `INTERRUPT` packets), every guest event and wait takes it for a handle lookup (`sdk/src/system/xobject.cpp:370-449`), and `mtmsrd` takes it once per simulation tick. Measure the blocked time on the three critical threads (the `critical_region_contentions` column is a running total); then cache the object pointer in the dispatch header, stop holding the lock across the guest interrupt callback, and give `mtmsrd` a per-thread interrupt-mask flag where the title only masks interrupts. | unknown, likely 0.1-0.5 ms spread over threads | S to measure, M to fix |
| PB-4.6 | **Setting chosen**: Vulkan presents with IMMEDIATE when allowed, then MAILBOX; for a 120 Hz display at 120 fps without VRR, `vulkan_allow_present_mode_immediate = false` gives MAILBOX (each source frame shown once, no tearing). Verifying the delivery needs the visible-window run of PB-5. **Present**: neither backend uses host vsync (D3D12 `Present(0, ALLOW_TEARING)`, Vulkan immediate then mailbox); `host_present_fps_limit` paces presentation only and `pinyon_shift_fh1_source_presentation` presents each source frame once. At 120 fps on a 120 Hz display use mailbox (or the VRR path of NP-4.5) so every source frame reaches the display once; verify with `present_delta_ns` and `duplicate_present_count`. | delivery, not speed | S |

## PB-5 Gates and protocol

**Preset added (2026-09-30)**: the GRAPHICS page's GRAPHICS PRESET row
sets PERFORMANCE 120 (Vulkan, the split GPU commands thread, 1x internal
with FSR 1 to the display, game frame rate limit 120) or QUALITY 60 (3x,
default backend, limit 60); any other combination reads CUSTOM, and a
change applies at the next start. **Gate status on the hidden race at
1x**: frame mean 11.2-11.8 ms (85-89 fps) with the recorder 9.6 ms busy per
frame; 3x on Vulkan is GPU-bound at about 22 ms. The speed gate is not met
yet: the recorder needs about 7 ms (PB-2.12 or a pass-rate trade).

- **Speed.** Race window (PB-0.6 protocol, display at 120 Hz, window
  visible for the final check) median at or under 8.4 ms and p95 at or
  under 12.5 ms (three vblanks) at 3x on Vulkan; distinct presents at or
  above 110 per second on `fh1-race-sustained`; the same route at 1x and
  2x no slower than today.
- **Fidelity, bit-exact items** (transfers by copy, aliasing, descriptor
  and register-path work, codegen options that must be bit-identical):
  golden frame replays at 1x byte-identical or within the documented
  tolerance (`tools/test-fh1-frame-replays.py`).
- **Fidelity, accepted trades** (PB-1.1, stencil and transfer skipping):
  3x captures of `fh1-race-sync`, `fh1-free-roam`, `fh1-buy-car` and
  `fh1-map` compared by MAE against the faithful setting, and one look by
  the maintainer before the trade becomes a default.
- **Guest numerics** (PB-3): `expect-simulation-time 0.95 1.08`, the
  pose-drift gate on `fh1-timing-straight`, and `M5_TRACE save.file.write
  payload_hash` equality against control.
- **Never** the AppData save; seeds only.

## Final pass: lessons from other recomps (PB-6 to PB-10)

Researched 2026-09-30 against local checkouts: UnleashedRecomp `cf829a9`
with XenosRecomp `990d03b` (hedge-dev), skate3recomp `f6e0ae8` with its SDK
submodule, Rayman Origins, Kameo, Nocturne, TiP, reNut, SVR07, the Yukes SDK
fork and upstream ReXGlue `development`. Measured on FH1 the same day with a
temporary decoder census (reverted).

**What the fast ones do.**

- **UnleashedRecomp** has no GPU emulation. It replaces the statically
  linked Xbox D3D runtime function by function (`CreateDevice`,
  `SetTexture`, `DrawIndexedPrimitive`, `StretchRect`...). It reads the
  device struct's own dirty bits for constants, and a lock-free queue feeds
  one render thread over plume (D3D12/Vulkan).
- **XenosRecomp**, its offline shader recompiler (MIT), emits a D3D9-like
  ABI:
  - the whole float register file per stage in one buffer, indexed by
    register number (4 KB vertex, 3.5 KB pixel), uploaded whole when dirty;
  - bindless textures and samplers, with indices in a 272-byte shared
    block;
  - no fetch-constant interpretation in the shader;
  - one specialization mask.
- **Unleashed's other techniques:**
  - lazy resolves: a resolved texture sampled before its source is redrawn
    binds the source surface directly;
  - a shipped pipeline list plus pipelines predicted from asset loads;
  - 191 mid-assembly hooks for high frame rates.
- **skate3recomp's** 2x comes from a hand-ported native scene renderer.
  - It hooks the engine's RenderMesh and sorted draw list and ports the
    material shaders by hand; the SDK still parses PM4 but skips suppressed
    draws and resolves.
  - That is months of game-specific work. Its SDK's emulation fast paths are
    behind ours, so there is nothing to port there beyond small settings.
- **Rayman Origins** hooks D3D draws like Unleashed.
- The other ReXGlue projects keep emulation. They contribute small things:
  - `[rexcrt]` routing of guest `memcpy`/`memset` to host code;
  - an FP-exception guard;
  - present-interval hooks for frame-rate unlocks.
- **Upstream ReXGlue** has one performance commit the fork lacks: `7f7c92e`,
  `stwcx.` as a `std::atomic` compare-and-swap.

**Why FH1 cannot take the D3D-hook route, and what it can take instead.**
The census of the race:

| Measure (per race frame) | Value |
| --- | --- |
| Draws through the title's runtime indexed emitter (`0x8240F4D8`) | **42**, 70 us of guest time |
| Draws arriving in indirect buffers (IBs) | all of the ~3,400-6,700 |
| IB executions | 1,000-1,740, carrying 0.96-1.85 M PM4 dwords |
| IBs byte-identical to the previous frame at the same address | **96 %** (none changed in place; the rest are new addresses) |
| Draws inside those identical IBs | 66-85 % |
| `LOAD_ALU_CONSTANT` packets | 3,300-6,000, all float constants, ~16 dwords (4 vec4) each |
| ...whose source data is identical to the previous frame | **99.9 %** |
| Draws in identical IBs whose context registers and fetch/bool/loop constants equal the same draw's last frame | 55-67 % (36-54 % of all draws) |
| ...whose full float register file also equals last frame's | 0 % (the camera globals change every frame) |

So FH1 renders from prebuilt display lists, with static per-object constants
loaded by pointer. A D3D-level hook would see almost none of it. The same
lists are decoded and every draw re-derived each frame, though, and that
repetition is the lever.

Licenses:
- UnleashedRecomp is **GPL-3.0**: ideas only, no code.
- XenosRecomp and plume are MIT, as the research reports them (re-check
  before vendoring).
- moodycamel concurrentqueue is BSD/Boost.

### PB-6 Static display lists

| Item | Work | Expected | Size |
| --- | --- | --- | --- |
| PB-6.1 | **State hash done (SDK `940f03c`)**: the recorder keeps a Zobrist-style hash of exactly the registers the PB-2.6 state epoch covers, updated per changed register where the epoch is bumped; it keys PB-6.3's memos. The IB identity half was not built: only PB-6.2 and PB-6.4 would use it. **IB identity and a running state hash on the decoder.**<br>• Identify each IB by (physical address, dword count) and keep it valid through a write watch on its pages, instead of hashing 1-1.8 M dwords a frame. The shared-memory watch machinery exists.<br>• Keep a Zobrist-style hash of the draw-relevant register state that updates per write in O(1): `H ^= mix(i, old) ^ mix(i, new)`. It covers context registers `0x2000-0x23FF` less the per-draw ones (`VGT_DMA_*`, `VGT_DRAW_INITIATOR`, `VGT_EVENT_INITIATOR`) and fetch/bool/loop constants, from the shadow register file.<br>• Put `draw_identity = (IB key, ordinal)` and `state_hash` in each `DrawRecord`.<br>• The decoder has about 40 % slack. | enabler; the census numbers above become live counters | M |
| PB-6.2 | **Not taken (2026-09-30)**: the decoder is not a limit. It waits 35 % of the race, mostly in `WAIT_REG_MEM` on words the title's CPU writes (see PB-6.4), and it now spends part of its slack on PB-8.9's compares. **Decoded record-stream cache.** For an IB still valid under its watch, replay last frame's record words (register runs, draw records, calls) instead of parsing PM4 again. `LOAD_ALU_CONSTANT` payloads are re-read from memory (they are pointers), and calls that sample live memory stay live. | decoder time (about 5 MB of PM4 a frame); frees decoder capacity for PB-6.1 and PB-6.4 | M |
| PB-6.3 | **Done as content-hashed memos (SDK `940f03c`, `gpu_state_hash_memos`)**: the translation, pipeline and viewport memos became 4096-entry direct-mapped tables keyed by the state hash and their inputs, so a draw finds the entry of any earlier draw in the same state, last frame's included. Six interleaved pairs: 1873 against 1892 ns per draw on average (four better), within noise; kept because it costs nothing and is the state key PB-6.4 needs. Samplers and texture bindings already have per-slot memos by their fetch words, and target preparation depends on tile ownership rather than register state, so they were not templated. **Cross-frame draw templates on the recorder.** Per `draw_identity`, keep the last frame's derived state together with its `state_hash`:<br>• shader pair, modifications and translations;<br>• pipeline, layout and handle;<br>• viewport and scissor;<br>• sampler parameters and handles;<br>• the texture binding infos, validated by the texture cache's binding version and outdated flag;<br>• the executor's target keys.<br>On a hash match, use them instead of the per-draw derivations. This generalizes PB-2.6's epoch memos ("same as the previous draw") to "same as this draw last frame". | the derivation share of the recorder (about 20 %) times the extra hit rate; measure first with PB-6.1's counters | M |
| PB-6.4 | **Deferred, XL (2026-09-30)**: after PB-8.8 to PB-8.11 the recorder costs 1.55-1.65 us per draw, and its profile is flat: bindings and constants 15 %, register writes 8 %, textures 7.5 %, shared-memory ranges 5 %, target preparation 4 %, primitive processing 3.6 %, system constants 3 %. A compiled IB can only skip what an O(1) "unchanged since last frame" test proves, and those tests are today the costs themselves: texture binding validity, vertex and index range validity under the write watch, and executor tile ownership. Each subsystem needs such a test first. The race's heavy stretch also has a latency component: the decoder waits (35-70 % of its time there) on words at physical `0x1FCA4000`-`0x1FCA4017` that only the title's CPU writes, the chunk releases of its render thread, and that thread waits on `EVENT_WRITE_SHD` fences at `0x1FCA5002`/`0x1FCA5006`, which the recorder writes only when it reaches them. So the heavy frames follow the recorder's latency as well as its throughput. A longer decoder yield before sleeping (50 ms against 2 ms) measured worse: the spinning decoder slows the recorder. **Compiled display lists.** For an IB that is valid, has the same entry `state_hash` as last frame, and whose resources are all unchanged (no texture outdated, no shared-memory page of its vertex/index data invalidated, and the same executor tile ownership over its targets at entry):<br>• replay last frame's tape segment for the IB with patched constant bindings;<br>• apply its register writes from the PB-6.2 cache;<br>• per draw, only gather and upload the float constants (the camera globals change) and rewrite the dynamic offsets.<br>Everything else is skipped: textures, samplers, descriptors, pipeline, executor preparation and binding, primitive processing, shared-memory checks. An invalidation inside the IB falls back to the full path. | per templated draw about 0.4 us against 1.85; with about 45 % of draws eligible, **roughly a third of the recorder (9.4 to about 6.3 ms)**, the gap to 7 ms | XL |
| PB-6.5 | **Deferred with PB-6.4.** **GPU-side reuse** (research after PB-6.4): Vulkan secondary command buffers per compiled IB, or `VK_EXT_descriptor_buffer` with constant addresses read per draw from a small table, so a compiled IB is re-executed rather than re-recorded. | submission worker time; the recorder's tape copy | L |

Order: PB-6.1, then PB-6.3 (cheap and measurable), then PB-6.2 and PB-6.4.
Gate each with the 1x replay goldens (bit-exact) and the race captures.

### PB-7 Constant and binding ABI (XenosRecomp's lessons, on our translator)

| Item | Work | Expected | Size |
| --- | --- | --- | --- |
| PB-7.1 | **Census done (2026-09-30)**: a race frame makes about 10,400 float-constant uploads (vertex and pixel) carrying 224K vec4 (3.6 MB), of which 35K (16 %) changed since their last upload. About 120 registers change at most four times a frame (the frame globals, about 230 changes) and about 200 carry the other 35K changes (per object). **Census first.** Per draw, record which 4-register float blocks changed since the previous draw, and whether they came from `LOAD_ALU_CONSTANT` (per object, about 4 vec4 a draw) or from writes outside static IBs (frame globals). The design depends on it. | decides PB-7.2 | S |
| PB-7.2 | **Not taken (census, 2026-09-30)**: a per-draw block would still carry the ~15 per-object registers of the ~21 a draw reads, about 2 % of the recorder for an L-sized translator change. What forced most uploads was the title rewriting unchanged constants, which PB-8.9 now drops on the decoder. **Two-level register-indexed constants.** The SPIR-V translator reads float constants by register number, as XenosRecomp does, from two buffers:<br>• a per-frame global register file, uploaded whole (4 KB + 3.5 KB) only when a global block changes, a few times a frame;<br>• a small per-draw block holding the ranges the draw's IB loads, addressed through a per-draw offset.<br>The per-draw gather and the used-constant bitmap scans disappear. Unleashed's "upload the whole file when dirty" would cost 37 MB a frame at FH1's 5,000 draws, hence the split. | the float-constant gather and upload, about 7 % of the recorder | L |
| PB-7.3 | **Deferred, L (2026-09-30)**: the texture half of `UpdateBindings` (image infos, view lookups, push descriptor records) is about 3 % of the recorder, and a descriptor-indexing translator change touches every shader and pipeline; not worth it against the items above. **Bindless textures and samplers** (descriptor indexing, as in both Unleashed and skate3). Each texture view gets a heap index at creation, and samplers are heap entries by hash. Per draw only indices go into a small block (or push constants), replacing the push-descriptor image-info building. Translator change: non-uniform indexing into the descriptor arrays. | about 3-4 % of the recorder, plus the submission worker's push descriptors | L |

### PB-8 Quick wins seen in other projects

| Item | Work | Source | Size |
| --- | --- | --- | --- |
| PB-8.1 | **Done (project `[rexcrt]`, SDK `8497c62`)**: `memcpy` `0x82A7D730`, `memmove` `0x82A7DCA0` (its forward path branches into `memcpy`'s entry) and `memset` `0x82A7F140` run as host code. The SDK's natives returned the host pointer, which the hook turned back into a guest address without the physical views' host offset, so they now leave `r3` as the guest passed it. With PB-8.2 the simulation thread (`Guest 8255AE10`) used 11-14 % fewer cycles per second over the race at an equal frame rate (1.37 to 1.22 and 2.63 to 2.27 Gcycles/s in two sections); `memcpy` alone had been 1 % of it. Race captures match. Route FH1's guest CRT `memcpy`/`memmove`/`memset` (and `XMemCpy` if linked) to host code with the SDK's `[rexcrt]` table (supported by our codegen, unused by our config). `sub_82A7F140` is a `memset` candidate (called with `(dst, 0, 92)`). Measure the guest threads' busy share. | Kameo, Nocturne | S |
| PB-8.2 | **Done (SDK `f882e05`)**: the compare-exchange works on a same-width copy of the reservation, and the sequentially consistent fences around `mfmsr`/`mtmsrd` are gone as upstream. D3D12 replays 4/4. Port upstream `7f7c92e`: `stwcx.`/`stdcx.` as `std::atomic` compare-exchange without the full-barrier `__sync` builtin, dropping the CR0.so copy. | upstream ReXGlue | S |
| PB-8.3 | **Done (SDK `d28bfd5`)**: at 1x the cache holds about 161 MB and never evicts, but on the 3x long drive it sat at the scaled 576 MB soft limit and evicted 204 textures. The defaults are now 1 GB soft and 2 GB hard (not 2 and 4, to leave 8 GB cards room for the 3x surfaces). Raise the texture cache's limits (soft 384 MB to 2 GB, hard 768 MB to 4 GB, lifetime 30 s to 300 s) and measure reloads and evictions over a free-roam route. | skate3 | S |
| PB-8.4 | **Measured, not adopted (2026-09-30)**: MMCSS "Games" registration of the command, recorder, submission and vblank threads plus a 1 ms timer request measured worse in all three pairs (1947/1830/1792 against 1797/1807/1735 ns per draw). MMCSS "Games" registration and 1 ms timer resolution for the decoder, recorder, submission and vblank threads (distinct from the priority boost measured in PB-4.4). | skate3, Nocturne | S |
| PB-8.5 | An NVIDIA application profile preferring maximum performance (NVAPI), against P-state parking under a CPU-bound load. It changes a driver profile, so it is an opt-in setting for the maintainer to approve. | skate3 | S |
| PB-8.6 | **Needs the visible check (2026-09-30)**: most of the race now runs at 120 fps, so pacing shows. Over seconds 12-38 of two hidden runs, frames average 8.62-8.65 ms with a median of 8.33 but a spread of 2.5-2.6 ms (p1 5.8-5.9 ms, p99 13.6-13.8 ms), and presents follow the same pattern. Whether a present wait evens this out on the 120 Hz VRR display can only be judged with the window visible. Present at 120 Hz: frame latency 2 and a present wait at the start of the guest frame (Vulkan `presentWait`), as Unleashed does, for even pacing once the frame fits. | UnleashedRecomp | S |
| PB-8.8 | **Done (SDK `2659acc`, `vulkan_cached_uniform_memory`)**, found by the final-pass recorder profile: the uniform pool took write-combined system memory, and each draw's float constants are gathered there in runs of a few vec4 (vcruntime `memcpy` was 5 % of the recorder). Host-cached memory instead: 1755 against 1800 ns per draw over six pairs (five better); the 3x frame (GPU-bound) is unchanged within noise. | profile | S |
| PB-8.9 | **Done (SDK `9bf779f`, `gpu_record_elide_unchanged_registers`)**: the decoder compares each register write with its shadow register file and records only the sub-runs that change a value; scratch, coherency, gamma-ramp and initiator registers are always recorded. Every elided rewrite would have cost the recorder a swap-copy and an invalidation of constant buffers, texture bindings or vertex buffer residency. 1649/1697/1668 against 1741/1725/1849 ns per draw; captures match within run-to-run variance. | profile, PB-7.1 | S |
| PB-8.11 | **Done (SDK `467583c`)**: sampler parameters, a pure function of the six fetch words, the binding's filter overrides and the filtering cvars, are kept in a 1024-entry direct-mapped memo behind each slot's last derivation, so a slot whose sampler changed finds a state seen before (the derivation was 3 % of the recorder). 1634/1721/1622 against 1717/1789/1685 ns per draw. **Measured, not adopted**: the same for texture bindings (a 2048-entry memo shared by all fetch slots behind their four ways) was better in three of six pairs (1580 against 1597 on average, carried by one slow base run). | profile | S |
| PB-8.10 | **Done (SDK `f774bf0`)**: fixed per-draw overheads from the profile: the Vulkan device pointer cached (a virtual `provider()` call several times a draw), the draw counter added once per swap instead of a cross-module thread-local update per draw, executor counters keyed by literal address instead of building a `std::string` per count, and a 16-entry front on the executor's surface map. 1755/1776/1846 against 1825/1847/1891 ns per draw. | profile | S |
| PB-8.7 | **Deferred with PB-1.2 (2026-09-30)**: at 3x the GPU holds the frame at about 24 ms, and 3x at 120 needs about three times this GPU, so the reload bandwidth this saves (about 2.6 ms at 3x by knock-out) does not change the 3x outcome; at 1x the GPU is about half busy. Lazy resolve aliasing for the scaled modes (PB-1.2's simpler form). When a resolve destination is sampled before its source surface is drawn again, and the formats, size and single-sampling match, bind the executor's surface directly and skip the untile reload. The copy happens only if the source is about to be overwritten while the texture is still referenced. | UnleashedRecomp `StretchRect` | M |

### PB-9 High-frame-rate correctness (PB-4.3) with Unleashed's toolkit

Unleashed's 191 hooks follow a few patterns:
- clamp a site's delta time;
- rescale exponential lerps with `1 - pow(1 - t, (30 + bias) / (fps + bias))`;
- grow an object's allocation to hold a per-object accumulator and step it at the original rate;
- integrate at 30 Hz and extrapolate the visual position.

TiP and reNut unlock by hooking the title's present-interval setter and re-locking the scenes that break.

| Item | Work | Size |
| --- | --- | --- |
| PB-9.1 | **Not started in this pass (2026-09-30)**: a correctness item rather than a speed one, and a reverse-engineering session of its own. Each candidate clock takes a route run and a look at the captures, and PB-4.3 left about 1,600 of them. The snapshot tooling and the route's `poke` are ready. Find the crowd's stepper. Continue PB-4.3's snapshot pass by poking the candidate clocks one at a time with the route's `poke` and watching the spectators in the captures; then trace the writer of the one that freezes them. | M |
| PB-9.2 | **Waits on PB-9.1.** Apply the matching pattern (delta clamp or per-object accumulator) as a mid-assembly hook in `config/rexglue/analysis/`, gated by a cvar, and extend `expect-simulation-time` routes with a crowd capture at 30 and 120 fps. | S-M |
| PB-9.3 | **Waits on PB-9.1's method.** Audit the purchase animation (NP-3.7's first report) the same way. | M |

### PB-10 Long-term options (not scheduled)

- **A native FH1 scene renderer**, skate3 2.0 style: hook the engine where it
  builds its display lists and draws per mesh, port the material shaders,
  and let the SDK skip suppressed draws and resolves. It is the only route
  past about 2x beyond PB-6, and it costs months. Revisit only if PB-6.4
  falls short.
- **Adopting XenosRecomp itself**: it expects D3DX shader containers with
  constant tables and D3D-level state, and leaves integer/loop constants,
  vertex formats and memexport unimplemented. PB-7 takes its ABI ideas onto
  our translator instead.

**Final-pass working order.**
1. PB-8.1 to PB-8.4, cheap and independent.
2. PB-6.1, then PB-6.3, measuring the template hit rate.
3. PB-7.1's census.
4. PB-6.2 and PB-6.4, the main lever for 120 fps at 1x.
5. PB-7.3, then PB-7.2 if PB-6.4 leaves the constant upload on top.
6. PB-9 in parallel.
7. PB-8.5 to PB-8.7 last.

## Working order

1. **PB-0** in full (about a week): Vulkan timing and counters, the 3x
   thread sample, the Nsight trace, the transfer-skip cvar, and the Vulkan
   baseline rows above.
2. **PB-1.1 first, with PB-1.8a and PB-1.8b right after** (small changes
   with a large share of pixel time), then **PB-1.3, PB-1.2, PB-1.4,
   PB-1.5 and PB-1.8c**: the GPU at 3x is the only stage that has no
   CPU-side workaround, and PB-1.1 is the largest single lever. Re-measure
   after each; expect the 3x GPU frame near 8 ms after these, with PB-1.7
   and PB-1.9 deciding the rest.
3. **PB-2 Tier 1** (PB-2.1 to PB-2.10) in parallel with step 2, since they
   touch different files: the GPU commands thread to about 10 ms, the race
   at 1x to about 90-100 fps.
4. **PB-4** pacing hooks and **PB-3** codegen, so the title's threads hold
   one simulation step per frame and the render thread keeps margin.
5. **PB-2.11** (decode-to-record), then **PB-2.12** if the recorder still
   misses 6 ms.
6. **PB-5** gates, then the 4K/120 preset in SETTINGS (3x, Vulkan, host
   MSAA mode 1 with FXAA, render limit 120).

Fallback tier if the GPU at 3x stays over budget after step 2: 2x with
FSR 1 or CAS to 4K, or the 2-sample host mode, both already settings.

## Needs a person

| Item | What is left | Needs |
| --- | --- | --- |
| PB-0.4 | A GPU trace of a 3x race frame (Nsight Systems' Vulkan trace and GPU metrics, or Nsight Graphics) to split the draws' GPU time | An elevated session, or the NVIDIA setting that allows GPU performance counters for all users |
| PB-8.5 | Approving an NVIDIA application profile that prefers maximum performance (a driver setting) | The maintainer |
| PB-8.6 | Judging frame pacing at 120 fps with the window visible (a present wait or not) | The maintainer at the machine |
| PB-5 | The final check with the window visible on the 120 Hz display, and one look at the accepted fidelity trades before they become defaults | The maintainer at the machine |

## Relation to the native port backlog

NP-2 and NP-3's measured-and-deferred items, NP-9.1 to NP-9.5 and NP-15.1
are superseded by this backlog; their evidence stays where it is and each
row there now points here. NP-15.2 to NP-15.6 (Vulkan preparation, texture
fast paths, higher scales, the default switch, vendor qualification) stay
in the native port backlog and gate the switch of the default renderer, not
the frame rate.
