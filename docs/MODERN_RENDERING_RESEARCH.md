# Modern rendering techniques

[Issue #981](https://github.com/arcanite24/pinyon-shift/issues/981) evaluates
replacing FH1's rendering techniques after identifying each pass's inputs,
outputs, readers and guest-visible side effects. Improving command submission
alone is the earlier [D3D renderer investigation](D3D_RENDERER_RESEARCH.md).

No replacement technique is enabled by this work. The first stage, MR-0, is
measurement and validation of the probes. A draw-target knock-out is not a
correct renderer and its saving is not a replacement's expected saving.

## Status and decision gates

| Item | Question still to answer | Status |
| --- | --- | --- |
| MR-0 | Per-pass cost on Mali, Deck, UHD 620, M4 Pro and RTX 4080 | Live draw/resolve measurements below; night-sprite, reflection-mip and MSAA budgets remain |
| MR-1 | Remove both tiled scene work and the decoder's later-tile walk | Open; the existing untile option does not remove that walk |
| MR-2 | Reduce MSAA and reconstruct edges without losing sample-dependent reads | Open; existing off/2x/4x settings are controls, not a temporal replacement |
| MR-3 | Reuse or cull sun-shadow casters | Open; shadow-mask and headlight dependencies must remain |
| MR-4 | Reuse the second depth pass's result | Same-frame substitution is blocked by the depth → mask → scene dependency; a different prepass remains open |
| MR-5 | Fuse bloom/luminance reductions and final composition | Open; target reuse and CPU exposure readback prevent assuming the whole chain is one independent pass |
| MR-6 | Remove copies by rendering into sampled images | Open; preserve CPU-read resolves and ownership transitions |
| MR-7 | Change reflection update scheduling | Open; distinguish face updates, mip generation and their consumers |
| MR-8 | Batch sprites | Open; identify shaders, state, order and depth/stencil rules first |

Set a saving gate for each row after completing its census, before implementing
the replacement. Keep prototypes behind default-off cvars. A default change
requires image comparisons and an actual saving on at least one target without
regressing the others. None of the measurements below closes an MR row.

## MR-0: target-filtered draw knock-outs

`fh1_debug_skip_renderings` selects comma-separated **exact** rendering labels
from `fh1_native_gpu_profile`, such as
`1024/32/4x/d1+0/32/4x/c3,1024/32/4x/d1`. Set the selection at launch, then
toggle `fh1_debug_skip_rendering_draws` live. Both settings default to doing
nothing. Empty selection selects nothing; a partial label does not match.
`fh1_debug_skip_pixel_shader` additionally restricts that selection to one
guest pixel-shader hash, supplied as a **decimal** unsigned 64-bit integer
(zero means any shader). For example, `7009157937902174059` selects final
composite shader `614588022744BF6B` without removing HUD draws on the same
attachments. It requires a restart; the boolean remains the live toggle.

The probe suppresses only `vkCmdDraw` / `vkCmdDrawIndexed`. The decoder,
pipeline and binding work, renderings, ownership, clears, resolve dispatches,
fences and query commands still run. Draws inside an active guest occlusion
query and memory-export draws are preserved. Stats count selected commands as
`debug_rendering_draw_skipped` and protected commands as
`debug_rendering_draw_preserved`. The image and downstream sampled values are
deliberately wrong; do not use this as a player setting.

Labels describe attachments, not semantic pass identities. In particular, a
small float target may serve more than one group. Do not call its entire cost
"post processing" until shader and resolve traces establish the boundaries.

## Ordered post-chain inputs and outputs

The Vulkan one-frame shader discovery now records sampled bindings and
ordered resolves as well as shader identities. `draws.jsonl` has a zero-based
`index` and each used texture slot's fetch dimensions, format, physical base
and mip addresses, and padded guest allocation lengths. `resolves.jsonl`
records completed resolves: destination extent, format, sample selection,
packed destination info, untile band, source surface keys and rectangles.
`after_draw=N` places a resolve after N captured draws, before draw index N;
several resolves at the same boundary retain file order. Discovery remains
off by default and writes only into the requested local capture directory.

The lengths use the production texture upload layout, including guest
padding and packed mips. Host image bytes are unsuitable: the scene's
32-bit guest texture can have a 64-bit host view. Intersecting these ranges
finds **possible** producers, not exact dependencies. A resolve can write
only a rectangle of its allocation; a later partial write does not erase
all earlier producers. Bound slots also do not prove every shader branch
samples them. CPU readers and fences require separate traces.

A base-game moving-race frame (8991) replayed at native frame 2 contains
5,590 emitted draws and 92 completed resolves. All control front-buffer
bytes match with and without discovery. Its post-chain order is:

| Draw indices | Inputs and output established by bindings and resolves |
| --- | --- |
| 5334–5336 | Scene color to 320×192, then 64×32 and 32×32 reductions |
| 5337, `ED74D20BC7DFB0F7` | Current 32×32 reduction plus a prior 32×32 float texture; resolves the new float result back into that history allocation |
| 5338, `4D3934F366930540` | Prior 320×192 texture, current first reduction and the new float result; resolves into the 320×192 history allocation |
| 5339–5358 | Filtering, downsample and upsample chain, including logical 40×24 and 80×48 rectangles in padded 64×32 and 96×64 allocations; exact filter math remains open |
| 5359–5360 | Scene depth and a 640×360 RGBA8 intermediate produce the mask later bound by final composition |
| 5361, `64AEAE9314A0118B` | Three views of the scene color allocation; resolves full-size color back to it; exact purpose remains open |
| 5418–5419, `614588022744BF6B` | Scene color (slot 0), processed 320×192 (2), mask 640×360 (5), 16³ LUT (7), current 32×32 float (17) |
| 5420–5589 | 170 later HUD draws sharing the final composite's color target |

Both history inputs have no earlier overlapping resolve in this frame,
then receive their new result after the consuming draw. This establishes
read-before-write allocation use. Their cross-frame history role is an
inference; a one-frame GPU binding trace does not exclude CPU resets or
establish blend weights or the exposure adaptation formula. A replacement
must retain the old inputs until those reads finish.
The historical exposure CPU readback also remains a separate requirement.

Scene color and depth inputs span three band resolves, not merely the
resolve containing the first byte of the texture. The final front-buffer
resolve at physical `0x1C149000` has no sampled reader in this frame;
alternating front-buffer addresses alone do not establish temporal filtering.
Addresses and draw indices here identify this capture, not stable symbols.

The shader-restricted knock-out was checked independently with 210 replay
iterations: off/on/off suppressed 0/420/0 commands, exactly two per enabled
iteration. Decoded draw counts remained equal and control bytes matched.
This verifies selection; timings from that build-concurrent check are excluded.

### Depth before the shadow mask

The same ordered race trace corrects an earlier pass label. The 1040-pitch
D24S8 target at EDRAM tile 720 produces the 1024×1024 shadow atlases. It
precedes the 1280-pitch float-depth target at base 0. The latter's depth
resolve is bound at slot 0 by `93626E75D17576C5` and the following mask
draws, alongside a 1024×1024 atlas at slot 1. The mask resolves to a
1280×720 RGBA8 texture before scene lighting samples it at slot 13.

The early full-size depth dump and the final three-band scene depth show
the same camera-view road, car and barriers; the latter adds foliage.
The 1280-wide pass is camera depth for the screen-space mask, not the
light-space sun map. Skipping it removes shadows because it feeds their
mask. The older knock-out alone could not establish its projection.

This creates a same-frame ordering constraint for MR-4: camera depth feeds
the mask, and the mask feeds scene shading. Main-scene depth arrives after
those mask reads, so substituting that result would require changing the
render order and breaking this dependency cycle, or accepting older data.
It is not an independent duplicate that can simply be removed. A different
prepass remains a separate hypothesis requiring an image-correct prototype.
The 1,168 full-size depth draws, first mask reads at draw 1335, and main
band depth resolves at boundaries 2294, 4553 and 5333 establish that order
in this frame. Raw dumps remain local; their addresses are not symbols.

### Reproducible replay checks

Capture with the recorder split disabled (`gpu_record_thread=false`), using a
private run copied from a pinned seed. The committed
`config/render-tests/fh1-modern-rendering-census.fh1test` waits for
`pressstart.wmv` before sending startup input, then verifies free roam and
movement. The old output-paced race route can consume all startup inputs
before the title accepts input on a cold launch; that failed run is excluded.
For a race capture, add that boot wait and a 60 Hz wall clock to
`fh1-race-sync`, then arm `fh1_frame_dump_frame=-1` after its moving-race
capture. Dumps require 1x capture scale; scale the replay afterwards.

```powershell
python tools/benchmark-fh1-renderings.py PATH/TO/frame.fh1frame `
  --state-root .local/render-seeds/appdata-2026-09-27 `
  --build-directory out/build/win-amd64-release `
  --output .local/mr981/main-replay `
  --renderings=1024/32/4x/d1+0/32/4x/c3,1024/32/4x/d1 `
  --game-argument=--draw_resolution_scale_x=2 `
  --game-argument=--draw_resolution_scale_y=2 `
  --game-argument=--fh1_msaa_single_sample=false
```

The benchmark copies the dump and seed into its new evidence directory. It
refuses output inside the seed, never overwrites an evidence directory, and
retains every run's logs, performance CSV and front-buffer bytes. Three
disjoint off/on/off blocks each replay 610 times, discard the first 300 CSV
rows and require at least 100 valid whole-frame GPU timestamp samples. An
unmatched selector, missing samples, changing control image, changing GPU or
changing draw/resolve counts fails the comparison. Executable and GPU module
hashes, the selected GPU/driver, seed manifest and dump hashes accompany it.

Per-pass profiling is disabled during these timings. Separately collect a
profile to discover labels. `fh1_frame_replay_present=false` also suppresses
the replay's host presentation after closing its GPU frame; front-buffer
resolves and readback remain. This avoids swapchain acquisition imposing a
display-rate floor. The option defaults to true and affects only offline
replays; gameplay and the frame inspector retain presentation.

`--metric frame` explicitly measures replay latency when a driver cannot
return enough GPU samples. It includes CPU and idle time; an unavailable GPU
median is reported as null rather than zero. It is not a GPU-cost result.

### Initial main-scene replay measurements, 2026-11-02

All rows suppress the two main-scene target labels in the command above.
Positive saving is off minus on. Error bars are standard errors over three
disjoint blocks, not 95% intervals. They measure the whole GPU **frame span**,
including gaps in command supply, not isolated shader execution time.

| Device | Replay settings | Saving, ms |
| --- | --- | ---: |
| RTX 4080, Windows Vulkan | 2x, 4x MSAA | 0.08 ± 0.06 |
| M4 Pro, MoltenVK | 2x, 4x MSAA, existing untile default on | 8.19 ± 0.12 |
| Deck LCD, RADV | 1x, MSAA off | 0.44 ± 0.01 |
| UHD 620, Windows Vulkan | 1x, MSAA off | 28.06 ± 0.16 |
| 930MX, Windows Vulkan | 1x, MSAA off | 18.18 ± 0.07 |

Desktop, Mac and Deck use 610 repeats / 300 warm-up rows. UHD 620 uses
210 / 100 and 930MX 310 / 100; all retained at least 100 valid samples per
run. The dump is base-game moving-race frame 8991, 1,676,036 packet dwords,
with bloom, motion blur and depth of field enabled during capture. Windows
and Mac use SDK `10bc1704` plus the diagnostic patch; the Deck's existing
executable/runtime use `9b8e8473` with that patch applied to its GPU module.
These are within-device comparisons, not a cross-device benchmark of one
identical release. Raw evidence lives under `.local/mr981/`,
`~/pinyon-mac/mr981/`, `~/pinyon-shift-dev/mr981/` and
`C:\bench\mr981\`; no dumps or game images belong in the repository.

Every control in each block is byte-identical to the other controls. Disabling
replay presentation preserves those control bytes too. A deliberately
nonmatching `0/2/1x/c30` selector on the RTX 4080 selected zero draws and
matched the control exactly. Replay controls do differ from the original
live recording: they verify the probe and replay repeatability, not complete
live-renderer image parity.

### Live measurements are necessary

The offline replay runs decoding and recording on one thread. A small
frame-span saving can mean that thread is starving the GPU; it does not
establish that the selected pass is cheap. Keep the normal recorder split
for live measurements and use `make-ab-route.py --mark` to toggle the probe
and `perf_aa_toggle` together. Pair an A/A run with the same window cadence.

The initial live route parks the seeded Miata at the Gauntlet, takes its
reference capture before any knock-out, then alternates every 150 wall-clock
ticks at 60 Hz. Analysis starts at the first side-1 window, discards 15 output
frames after each change, excludes missing/dropped GPU timings and requires
30 retained frames per window. Fifteen windows give five disjoint BAB/ABA
blocks. Initial Mac measurements at 2x/4x with untile **off**, original post
effects and the normal recorder split save 8.43 ± 0.09 ms of GPU frame span;
the 95% Student-t half-width is 0.24 ms. Its A/A run shifts +0.42 ± 0.11 ms
and +130 ± 64 decoded draws per frame, showing scene variation in the parked
view. This supports prioritizing the main scene, not a final gate with a
0.24 ms error budget. Retain the A/A workload change rather than subtracting
it as a universal timing bias.

`pinyon_shift_fh1_render_fps_limit=0` means the display rate, not uncapped
output. The Deck's first live test stayed at 60 Hz and is excluded from pass
ranking. At an explicit 120 source limit, the live Deck knock-out saves
1.73 ± 0.12 ms of GPU frame span (95% half-width 0.33 ms) and
1.77 ± 0.10 ms of frame time. Its A/A GPU shift is -0.07 ± 0.13 ms, within
noise. A faster explicit source limit is required when a probe could take
the frame below the display interval. A timestamp span alone cannot expose
work hidden under that pacing floor.

### Mali daylight profile

The Galaxy Tab S10 Ultra (Mali-G720-Immortalis MC12, stock driver
184553472, v4 game build) uses a private state under
`files/qualification/mr981/` with the same pinned base save copied into it.
The v4 update is mounted in that private state. The installed user tree is
never used for these runs. Original post effects are enabled; the source
limit is explicitly 120, MSAA is off at 1x, and the platform's existing
untile, quarter-rate reflections and daylight shadows-off defaults remain.

Five disjoint live blocks save 1.64 ± 0.30 ms of GPU frame span and
1.56 ± 0.33 ms of frame time when the main-scene group is suppressed.
The A/A shifts are +0.02 ± 0.10 and +0.08 ± 0.11 ms respectively. These
are standard errors; the A/B GPU 95% half-width is 0.83 ms.

A separate instrumented profile covers 1,320 frames from native-frame
window 3000 onwards, with zero dropped profile frames. Its whole frame is
17.97 ms. These **instrumented label spans** are for locating work only:

| Draw-rendering label | ms/frame | Renderings/frame |
| --- | ---: | ---: |
| `1024/32/4x/d1+0/32/4x/c3` | 7.57 | 11.21 |
| `0/16/1x/c3` | 1.74 | 19.00 |
| `0/16/1x/c2` | 1.61 | 3.94 |
| `0/16/1x/c0` | 0.55 | 5.66 |
| `128/4/2x/d1+0/4/2x/c3` | 0.33 | 2.58 |

The discovery trace at native frame 3000 contains 1,503 emitted draws,
1,250 on the main-scene color/depth pair, and no depth-only shadow target.
Android's existing `pinyon_shift_fh1_shadows=false` removes both daylight
shadow passes. MR-3 and MR-4 need a night-time sample (when headlights force
them back) or an explicit shadows-on control before receiving a nonzero
budget. The missing daylight work is not a new optimization. The two full-
size 1x color groups need input/output tracing next; their labels alone do
not separate post composition from HUD work.

After testing, the tablet's original APK was restored. Its installed profile
hash and the pinned PC profile hashes are unchanged.

### Live draw-group census, 2026-11-02

These use the same parked route and five disjoint blocks as the live main
probe. Values are **off minus on GPU frame span**, in ms, with standard
errors over blocks. No per-pass timestamps run during the comparison.
They measure marginal effects of suppressing draws, including effects on
downstream work, while retaining clears, resolves and command decoding.
They are not additive totals or strict upper bounds on replacing a pass
and its copies. A paced or CPU-limited frame can hide removed GPU work.

| Device | Main scene | Camera depth | Shadow atlas | Small post group | Final composite | Reflection face |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mali-G720, v4, 1x/MSAA off | 1.64 ± 0.30 | 1.52 ± 0.16 | 0.86 ± 0.10 | 1.79 ± 0.24 | 1.57 ± 0.27 | 0.11 ± 0.12 |
| Deck LCD, 1x/MSAA off | 1.73 ± 0.12 | 0.57 ± 0.10 | 0.22 ± 0.18 | 0.18 ± 0.07 | 0.31 ± 0.11 | 0.08 ± 0.08 |
| M4 Pro, 2x/4x, untile off | 8.43 ± 0.09 | 0.61 ± 0.17 | 0.30 ± 0.18 | 0.27 ± 0.18 | 1.15 ± 0.12 | 0.07 ± 0.21 |
| UHD 620, 1x/MSAA off | 28.64 ± 0.58 | 4.22 ± 0.27 | 0.53 ± 0.53 | 1.27 ± 0.32 | 6.37 ± 0.44 | 2.09 ± 0.50 |
| RTX 4080, 2x/4x | Paced | Paced | Paced | Paced | Paced | Paced |

Selectors are exact guest attachment labels; the host's MSAA override does
not rename them:

| Group | Rendering selector | Extra shader filter |
| --- | --- | --- |
| Main scene | `1024/32/4x/d1+0/32/4x/c3,1024/32/4x/d1` | None |
| Camera depth | `0/16/1x/d1` | None |
| Shadow atlas | `720/13/1x/d0,720/13/4x/d0` | None |
| Small post group | `0/16/1x/c3` | None; establish any other use in each capture |
| Final composite | `0/16/1x/c2` | Decimal `7009157937902174059` |
| Reflection face | `128/4/2x/d1+0/4/2x/c3` | None; excludes the separate mip-chain draws |

Generate the measured route schedules from the committed parked base:

```powershell
python tools/make-ab-route.py config/render-tests/fh1-modern-rendering-parked.fh1test `
  --setting fh1_debug_skip_rendering_draws --values false true `
  --every 150 --from 1500 --mark --output .local/mr-draws-ab.fh1test
python tools/make-ab-route.py config/render-tests/fh1-modern-rendering-parked.fh1test `
  --setting perf_aa_toggle --values 0 1 `
  --every 150 --from 1500 --output .local/mr-draws-aa.fh1test
```

Run each in a new private output directory through `run-fh1-render-test.py`
with the pinned seed, `--hidden --no-performance-gate`, the selected labels,
`gpu_record_thread=true`, `fh1_native_gpu_profile=false`, `vsync=false`,
`host_present_fps_limit=0` and `pinyon_shift_fh1_render_fps_limit=120`.
Set `disable_bloom`, `disable_motion_blur` and `disable_depth_of_field` all
false, `present_effect=bilinear`, `present_hdr=false`, and the scale/MSAA
settings in the device table. Require successful route completion and a
positive `debug_rendering_draw_skipped` counter in an enabled window.
Analyze from the first side-1 marker, following the validity and settling
rules above; `summarize-inrun-ab.py` supplies the disjoint-block estimator.

The tablet's camera-depth and atlas rows explicitly enable shadows, giving
control spans about 25.7 ms rather than the daylight preset's 18.2 ms.
Other tablet rows retain daylight shadows off and quarter-rate reflections.
This is not a measurement of the entire shadow-setting trade. All devices
use original post coefficients and an explicit 120 source limit. The Mac
and Deck have the earlier A/A controls described above. UHD 620's A/A GPU
shift is -0.45 ± 0.60 ms (95% half-width 1.66 ms), so its smaller rows
need caution. Its approximately 70 ms frames leave fewer samples in a
2.5-second window: retain at least 10 after the same 15-frame settling
period, rather than the 30 required on the other devices.

The UHD small-post, depth and reflection follow-up uses native stats every
100 frames, because a 600-frame reporting interval could end before any
enabled probe window appeared in the log. Positive skip counters establish
selection; an absent periodic report was not treated as zero cost. Earlier
evidence file names `sun-depth` and `second-depth` mean the camera-depth
and atlas selectors respectively; the corrected semantic names above follow
the ordered dependency trace.

The RTX's completed post probes remain at the 120 Hz source floor:
8.35 ms frame time on control windows, with changes below 0.03 ms of frame
time. Its additional A/A GPU shift is -0.02 ± 0.08 ms and frame-time shift
+0.05 ± 0.06 ms. The evidence directory calls that A/A run
`desktop-census-resolves-ab2`: it uses marker changes only, with the resolve
probe off throughout, and is not a resolve-cost measurement.
This cannot establish the isolated GPU cost of those groups. The resolve
probe below supplements the draw groups. Reflection mips and night-only
sprites still need separate budgets, along with MSAA comparisons, before
the census supplies a gate for every MR row. The Mali post
groups, UHD final composite and UHD reflections warrant further study;
the small noisy reflection-face results on the other devices do not yet
reject MR-7's whole workload.

### Live resolve-dispatch probe

The existing default-false `fh1_debug_skip_resolve_dispatches` can now be
toggled live. It is read at each dispatch and changes no cached setup.
Use the same parked A/B schedule, changing that boolean instead of the draw
probe, so loading and the reference capture finish with normal copies.
`debug_resolve_dispatch_skipped` counts suppressed commands. Every tested
route completed and had positive counters; replay controls with the probe
off remain byte-identical after the metadata/counter change.

| Device and settings above | GPU frame-span saving, ms | Frame-time saving, ms |
| --- | ---: | ---: |
| Mali-G720 | 1.48 ± 0.08 | 1.42 ± 0.08 |
| Deck LCD | 1.35 ± 0.12 | 1.46 ± 0.09 |
| M4 Pro | 4.80 ± 0.40 | 4.14 ± 0.17 |
| UHD 620 | 10.42 ± 0.43 | 10.38 ± 0.48 |
| RTX 4080 | Paced (0.10 ± 0.04 span change) | -0.01 ± 0.01 |

Errors are standard errors over five disjoint blocks. Setup, descriptors,
barriers, clears, fences and readback paths still run, but the sampled
contents are wrong and can make downstream work cheaper. These are
marginal frame effects, not isolated dispatch times. Neither zeroing every
copy nor enabling this probe is a replacement: MR-6 must preserve the
current value for shader consumers and CPU readers, including exposure
and saved thumbnails. The nonpaced results justify investigating selective
direct sampling or aliasing; they do not establish how much an image-correct
implementation will save. Tablet testing again restored the original APK
and retained the installed profile hash.
