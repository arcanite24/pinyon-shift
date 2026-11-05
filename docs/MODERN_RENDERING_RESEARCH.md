# Modern rendering techniques

[Issue #981](https://github.com/arcanite24/pinyon-shift/issues/981) evaluates
replacing FH1's rendering techniques after identifying each pass's inputs,
outputs, readers and guest-visible side effects. Improving command submission
alone is the earlier [D3D renderer investigation](D3D_RENDERER_RESEARCH.md).

Qualification targets the current Vulkan ports, as confirmed by the maintainer
on 2026-11-02. Restoring the legacy D3D12 path is outside this investigation.

No replacement technique is enabled by this work. The first stage, MR-0, is
measurement and validation of the probes. A draw-target knock-out is not a
correct renderer and its saving is not a replacement's expected saving.

## Status and decision gates

| Item | Question still to answer | Status |
| --- | --- | --- |
| MR-0 | Per-pass cost on Mali, Deck, UHD 620, M4 Pro and RTX 4080 | Census complete for every row ([gates and decisions](#gates-and-decisions)); Mac MSAA replay timing stays unqualified |
| MR-1 | Remove both tiled scene work and the decoder's later-tile walk | Rejected: the decoder-level skip was built as NN-2.2 and saved -0.36 ± 0.40 ms of Odin decoder time; the GPU side is the existing untile option |
| MR-2 | Reduce MSAA and reconstruct edges without losing sample-dependent reads | No default change; 2X and FXAA stay player options |
| MR-3 | Reuse or cull sun-shadow casters | Rejected: atlas ceiling below the gate on every device |
| MR-4 | Reuse the second depth pass's result | Rejected: same-frame reuse breaks the depth → mask → scene order; SHADOWS off already removes the pass |
| MR-5 | Fuse bloom/luminance reductions and final composition | Rejected for this issue: the composite is already one fused draw, the reductions stay in any fusion, and the scene-colour pass before it (draw 5361) is required; fusing that needs a host-written replacement shader |
| MR-6 | Remove copies by rendering into sampled images | Rejected: resolves already write their textures; deferring the memory copy exactly saved 0.12 ± 0.16 ms on UHD 620 against a 2.41 ms ceiling |
| MR-7 | Change reflection update scheduling | Kept: the lower-rate option already ships at 0.25 on Android and ULTRA LOW and cuts Mali mip work from 2.46 to 0.49 ms |
| MR-8 | Batch sprites | Rejected: lamps, headlights and tyre smoke are under 100 draws a frame and their whole cost is below the gate |

A row's gate was set after its census, before any replacement work. Keep
prototypes behind default-off cvars. A default change requires image
comparisons and an actual saving on at least one target without regressing
the others.

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
Each draw also records the requested probe shader, exact rendering match,
hot-toggle state, actual draw shader and final command-suppression decision.
These fields distinguish a missing pass from a selector or toggle failure.

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
probe below supplements the draw groups. The further mip, night-light and
MSAA comparisons below still leave smoke/particles and qualified Mac MSAA
timings before the census supplies a gate for every MR row. The Mali post
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

### Reflection mip work

The base moving-race trace separates face rendering from mip generation:
one 256×256 base face is updated, then draws 1540–1587 execute six chains of
eight reductions. Pixel shader `21937679208E59A5` uses the
`0/2/1x/c3` rendering, reading 256×256 through 2×2 inputs and producing
128×128 through 1×1 outputs for each face. The earlier description that
only the updated face's mips run was too narrow. Those 48 mip draws and
48 resolves need their own cost bound, separate from reflection geometry.
They do not yet prove that other faces' mip chains can be omitted: CPU
writes, inherited state, clears and ownership changes still need checking.

On the tablet's v4 daytime route, mip-draw presence also depends on the
shadow setting. With full-rate reflections, the normal recorder and untile
enabled, a frame-3000 discovery has 1,644 draws and no instances of this
shader with shadows off. Changing only shadows to on produces 2,326 draws,
including all 48 mip draws. Each reports the requested shader, matching
rendering selector and active suppression; the later periodic skip count
is positive. A frozen off/on/off replay independently confirms selection.
This establishes a coupling in this route, not its guest-code cause or
whether resolves still update cube contents without those draws. The
default daytime shadow-off run cannot bound mip work in shadow-on scenes.

The shader-filtered live mip knock-out saves 0.50 ± 0.11 ms on M4 Pro and
1.43 ± 0.44 ms on UHD 620. Deck's 0.05 ± 0.12 ms is unresolved; RTX remains
source-paced (frame change below 0.01 ms). These are five-block marginal
GPU frame-span effects with resolves still executing, using the preceding
device settings. M4 uses `vulkan_pipeline_cache_persist=false`: an earlier
night batch reported `VK_INCOMPLETE` during cache writing and was excluded.
None of these measurements establishes the cost of an image-correct mip
replacement or rejects reflection scheduling as a whole.

On Mali with shadows enabled, 1x/MSAA off, untile on and the normal
recorder, the same five-block probe saves 0.49 ± 0.08 ms at the Android
quarter-rate reflection preset, or 2.46 ± 0.22 ms at full rate. Frame-time
savings are 0.50 ± 0.06 and 2.48 ± 0.21 ms respectively. Both routes finish
with positive selected-draw counters. This changes only mip draw commands;
face geometry, all mip resolves and their synchronization remain. The
shadow-off no-match run is excluded rather than reported as zero cost.

### Night lights and missing particle scope

The parked route at time-of-day 23 with shadows enabled selects lamp-glow
shader `E6A37477D3491A43` or headlight shader `36ADB4C3E44F265F` within the
main-scene rendering. The base night trace contains seven lamp draws and
76 headlight draws; their presence is verified independently from daytime
captures. The private run's cheat configuration sets the time, leaving the
installed save untouched. Original post effects and the normal recorder
remain enabled. These are five disjoint live A/B blocks, with positive
selection counters and no per-draw GPU profiling.

| Device | Lamp-draw suppression saving, ms | Headlight-draw suppression saving, ms | Night A/A shift, ms |
| --- | ---: | ---: | ---: |
| Mali-G720 | -0.17 ± 0.34 | 0.11 ± 0.13 | 0.04 ± 0.05 |
| Deck LCD | -0.11 ± 0.05 | 0.17 ± 0.11 | -0.05 ± 0.20 |
| M4 Pro | -0.06 ± 0.09 | 0.02 ± 0.12 | -0.11 ± 0.14 |
| UHD 620 | -0.24 ± 0.26 | -0.42 ± 0.73 | -0.81 ± 0.63 |
| RTX 4080 | Paced | Paced | -0.01 ± 0.01 |

Errors are standard errors; A/A is marker side 1 minus side 0, while the
two probe columns are control minus suppressed. They are not corrected by
subtracting A/A. UHD's night A/A frame-time shift is -2.54 ± 2.36 ms,
larger than these small effects. The measurements do not justify a lamp or
headlight batching prototype. This stationary view has no smoke or other
particles; [Tyre smoke](#tyre-smoke) budgets those. A tablet brake/throttle
route produced no visible smoke and is excluded from particle evidence.

Particle-route preparation can use the existing private-profile load hook
instead of editing the installed save. An archived decrypted 20,419-byte
profile contains `Main/TractionControl` and `Main/StabilityControl`, both
u8 fields with value 1. Their names and encoding are established by
`tools/fh1-profile.py`. In two Windows private-state runs, explicitly set
both fields to 1 versus both to 0 through the after-decrypt hook. Logs
confirm each field's applied value; both routes complete and capture
valid vehicle poses. Holding both triggers at 255 for five seconds
produces no visible tyre smoke in either run. This rules out that recipe
as particle evidence even with both fields zero; it does not establish
the settings' driving effects or the cause of the earlier result. These
diagnostic dumps require `gpu_record_thread=false`; the first recorder-on
attempt correctly logged that its dump request was ignored and is excluded
from command-stream evidence.

A follow-up with both fields zero, full throttle for 450 script ticks
(7.5 seconds), then the A-button handbrake and right steering produces
visible white tyre smoke in the later capture. The early capture shows
66 km/h; the later one shows the stopped car, skid marks and smoke. The
route captures a 76,239,148-byte frame dump just afterward. This supplies a
visible effect for shader identification, not a particle cost measurement
or a separate proof of either assist field's effect. The same pinned
profile's hash remains unchanged.

## MR-2: lower MSAA and existing scene-only FXAA

The maintainer agreed on 2026-11-02 to a 40 dB RGB8 PSNR floor plus visual
checks. Each accepted capture must meet that floor against its own original
4x reference. Motion, edges, HUD, lighting and temporal stability must also
show no visible defects before a default change. The measured sample-count
budgets justify a 1 ms net GPU frame-span saving gate on at least one
GPU-bound target, with no regression beyond interleaved control uncertainty
on the others. A static PSNR pass alone does not meet this gate.

### Fixed-command sample-count census

Use the same base moving-race dump for three disjoint 4x/off/4x blocks and
three 4x/2x/4x blocks. Each process replays 210 frames, discards the first
100 and requires at least 100 complete valid GPU samples. Host presentation,
per-pass profiling, untile and scaled-MSAA overrides are disabled. The
median decoded draw count remains 5,808 for every variant; this isolates
sample-count settings without removing decoder work. Each mode's control
front-buffer bytes must match every repeat on that device.

| Device and scale | 4x → off saving, ms | 4x → 2x saving, ms |
| --- | ---: | ---: |
| Mali-G720, 1x | 8.71 ± 0.41 | 3.67 ± 0.10 |
| Deck LCD, 1x | 1.08 ± 0.11 | 0.68 ± 0.02 |
| UHD 620, 1x | 18.68 ± 0.67 | 7.65 ± 0.36 |
| RTX 4080, 2x | 0.21 ± 0.19 | 0.13 ± 0.08 |
| M4 Pro, 2x | Unqualified controls | Unqualified controls |

Errors are standard errors over three blocks. All four reported devices
pass same-mode byte equality. Mac controls changed slightly even after
longer warmup and disabling asynchronous specialized passes; no qualified
Mac replay result is reported. These are serialized replay GPU frame spans,
including idle gaps, so the small Deck/RTX changes cannot establish their
isolated sample-shading cost. Live comparisons are needed for a net gain.
The tablet replays the base recorded commands on its v4 runtime; this is
not a claim about identical base/v4 gameplay frames or release binaries.

### Capture after the AA effect

The existing `swap_post_effect=fxaa` and `fxaa_extreme` can process the scene
before the HUD is composited (`swap_post_effect_scene_only=true`). Raw
replay front-buffer bytes precede this effect and cannot measure its image.
The default-empty Vulkan `fh1_frame_replay_output_path` now captures RGB8
PPM after the swap effect and gamma, before presenter upscaling and host UI.
It requires replay presentation and an existing parent directory. Capture
failure produces a nonzero process exit; the Python replay runner rejects
that exit even if the earlier native JSON reports successful readback, and
cannot publish a golden from it. Temporal presenter AA needs a presented
capture instead; this output is not a capture of FSR's result.

On RTX at 1x, the identical moving-race dump, 30 repeats, bilinear SDR
presentation and original guest post constants give the following RGB8
whole-image comparisons against original 4x. Two independent 4x captures
are byte-identical. FXAA leaves raw guest resolve bytes unchanged.

| Candidate | PSNR, dB | Mean absolute error, 8-bit levels |
| --- | ---: | ---: |
| Off | 39.46 | 0.68 |
| Off + FXAA | 39.16 | 0.78 |
| Off + extreme FXAA | 39.13 | 0.82 |
| 2x | 43.01 | 0.43 |
| 2x + FXAA | 40.98 | 0.60 |

FXAA smooths edges but scores worse against the 4x reference than 2x alone;
these numbers do not establish better quality. A check of 6,552 opaque
bright HUD pixels in three regions finds zero changes between off and
off+FXAA, not proof that every HUD edge is preserved. One static image does
not qualify temporal stability, particles, night lighting or other GPUs.
No default changes or image-quality acceptance follow from this test.

The same 1x, 30-repeat capture comparison on the other Vulkan ports gives:

| Device | 2x PSNR, dB | 2x + FXAA PSNR, dB |
| --- | ---: | ---: |
| Deck LCD | 43.20 | 40.98 |
| UHD 620 | 43.36 | 40.78 |
| M4 Pro | 43.26 | 41.01 |
| Mali-G720 | 43.24 | 40.97 |

Each pair uses that device's own original 4x reference. Repeated 4x RGB8
PPMs are byte-identical on these four devices, and enabling FXAA preserves
the off/2x raw guest resolve bytes respectively. Mac's successful 1x RGB8
control does not qualify the failed raw-byte 2x timing controls above.
These are still one scene, not a temporal-quality or 2x-scale validation.

**No MSAA plus existing FXAA is rejected for MR-2 under the agreed gate:**
it scores 39.10–39.24 dB on these four devices and 39.16 dB on RTX, below
40 dB in every case. Extreme FXAA also fails the RTX static gate at
39.13 dB. This rejects those combinations for a default replacement, not
the separate existing player options or a different temporal algorithm.
The 2x + FXAA combination passes this one static-image floor on all five
GPUs, but its motion and cross-device timing qualification remains open.
The original tablet APK was restored after each batch and its installed
profile retains SHA-256 `864dafc1…383644`.

### Live 4x versus 2x + FXAA

Use three disjoint original/candidate/original restart blocks at 120 Hz
source rate, original guest post effects, normal recorder, untile off,
explicit full 4x versus 2x and scene-only FXAA, SDR bilinear output and no
per-pass profiling. The pinned parked route captures the vehicle before
measurement; require a valid pose within 0.1 m across runs. Measure complete
CSV rows after the frame-1800 marker and 30 output frames of settling,
requiring at least 200 valid GPU samples. Runtime, module, seed and route
hashes accompany each local report.

| Device | GPU frame-span saving, ms | Frame-time saving, ms |
| --- | ---: | ---: |
| Deck LCD, 1x | 0.52 ± 0.05 | 0.54 ± 0.05 |
| Mali-G720, 1x | 3.95 ± 0.47 | 3.96 ± 0.47 |
| UHD 620, 1x | 1.96 ± 1.38 | 2.50 ± 0.95 |
| RTX 4080, 2x | -0.04 ± 0.01 | -0.001 ± 0.003 |

Errors are standard errors over three blocks. RTX remains source-paced;
Deck controls average 104 ± 20 more decoded draws than candidate runs, so
its gain includes scene variation. UHD has substantial between-block drift.
The first Mac series moved more than 8 m at the third capture and was
rejected before completing a block. A second series also fails position
equality; a handbraked follow-up adds an end capture and fails its within-run
0.1 m limit. No qualified Mac live result is reported. The cause of that
motion is unlocalized; holding the handbrake alone did not stabilize it.
Mali controls average 22 ± 19 fewer decoded draws than the candidate;
its control GPU span drifts from 27.48 to 31.08 ms across the series despite
the fixed pose, so retain interleaving and the between-block error. These
results do not yet satisfy a cross-device acceptance gate.

## Gates and decisions

Every row uses the gate already set for MR-2: a net saving of at least
1 ms of GPU frame span on one GPU-bound target **at the preset that ships
the work**, with no regression beyond control uncertainty on the others,
and the 40 dB RGB8 PSNR floor plus visual checks. On the Odin, where the
CPU front end dominates, the same 1 ms applies to CPU frame time and only
counts when draws or decoder work go away. Following the issue's method, a
row whose whole knocked-out cost is below the gate on every device is
dropped without design work. A knock-out supplies a wrong image, so a
ceiling that passes the gate only justifies a prototype; it is not that
prototype's saving.

| Row | Ceiling that decided it | Decision |
| --- | --- | --- |
| MR-1 | Main scene 1.6–28.6 ms of GPU span, of which `fh1_untile_predicated_tiling` already draws the tiles once (default on Android, macOS and ULTRA LOW). The decoder walk was prototyped before this issue as NN-2.2 (`fh1_untile_decoder_skip`): on the Odin race it dropped decoded draws from 3,702 to 1,919 a frame, yet moved the decoder by -0.36 ± 0.40 ms and process CPU by -0.13 ± 0.69 ms over 14 in-run pairs, and its exact-replay check diverged at half the resolve checkpoints | Rejected: below the gate on the CPU-bound device it targets, and not exact. The later-tile draws the early skip already drops (NN-2.1) were most of the cost |
| MR-2 | 4x → 2x + scene-only FXAA live: 3.95 ms Mali, 1.96 ± 1.38 ms UHD 620, 0.52 ms Deck, -0.04 ms RTX | No default change. See below |
| MR-3 | Shadow-atlas knock-out: 0.86 ms Mali, 0.22 Deck, 0.30 M4 Pro, 0.53 ± 0.53 UHD 620 | Rejected: below the gate everywhere. Caching casters on the host would not remove their decoding either, because the guest still issues them |
| MR-4 | Camera-depth knock-out: 1.52 ms Mali, 0.57 Deck, 0.61 M4 Pro, 4.22 UHD 620 | Rejected. The pass is already a depth-only prepass; main-scene depth arrives after the mask reads it, so reuse needs a reorder or last frame's depth. Low-end machines can already drop it with SHADOWS off, which removes both shadow passes |
| MR-5 | Small post group 1.79 ms Mali, 1.27 UHD 620; final composite 1.57 ms Mali, 6.37 UHD 620, 1.15 M4 Pro; draw 5361 3.29 ± 1.09 ms UHD 620 replay | Rejected for this issue. See below |
| MR-6 | Resolve-dispatch knock-out: 1.48 ms Mali, 1.35 Deck, 4.80 M4 Pro, 10.42 UHD 620; memory copies alone 2.41 ± 0.29 ms UHD 620 | Rejected. An exact deferred copy saved 0.12 ± 0.16 ms. See [Resolve memory copies](#resolve-memory-copies-mr-6) |
| MR-7 | Face rendering 0.07–0.11 ms except 2.09 ± 0.50 UHD 620; mip draws 0.49 ms Mali at the shipped quarter rate, 2.46 ms at full rate, 1.43 UHD 620, 0.50 M4 Pro | Kept, default on where it pays. See below |
| MR-8 | Lamp and headlight knock-outs within noise everywhere; tyre smoke below | Rejected. See below |

**MR-2.** 4x MSAA ships only in desktop QUALITY 60 (Windows and Linux)
and Android QUALITY 30. The Mac's QUALITY 60 and Android's SMOOTH 60
already store 4x surfaces with two samples, and every low-spec preset turns
MSAA off. Where 4x ships, the RTX 4080 gains nothing (-0.04 ms, source
paced), and Android QUALITY 30 is paced at 30 fps with room to spare. No
default changes. The 2X MSAA row and the FXAA row remain player options.
Motion and temporal checks for 2x + FXAA were not run, so it is not
qualified as a default anywhere.

**MR-7.** The row's candidate, updating faces at a lower rate, is the
existing `pinyon_shift_fh1_env_map_rate`. All six mip chains run only on
frames that update a face, so the rate cuts mip work as well: on Mali with
shadows on, mip draws cost 2.46 ± 0.22 ms at full rate and 0.49 ± 0.08 ms
at 0.25. Every Android preset and the desktop ULTRA LOW preset ship 0.25.
Rebuilding only the updated face's chain would remove at most five sixths
of the remaining mip draws: 0.41 ms on Mali at 0.25, and about 1.2 ± 0.4 ms
on UHD 620 at the desktop rate of 1, inside that device's ±0.6 ms A/A
spread. That refinement is not worth a prototype while ULTRA LOW already
gives such machines the quarter rate.

**MR-5.** The final composite (`614588022744BF6B`) is already a single
full-screen draw. It reads scene colour, the processed 320×192 image, the
640×360 mask, the 16³ grading LUT and the current 32×32 exposure. Its
knock-out is its own work, which any replacement keeps. The small post
group's reductions also stay in a fusion, which would only remove the
passes between them, so its 1.27 ms (UHD 620) and 1.79 ms (Mali) are upper
bounds above what fusion could save, and Mali was unavailable to qualify a
prototype.

The part above the gate is draw 5361 (`64AEAE9314A0118B`). It reads three
views of scene colour and resolves a full-size result back into scene
colour before the composite. Suppressing it in the race replay saves
3.29 ± 1.09 ms on UHD 620 (controls drift from 59 to 72 ms across the
series). It is not optional:

- It runs with the shipped post defaults (bloom contribution, motion blur
  and depth of field off) and with each of those effects on: the
  shader-filtered knock-out removed 2,255–2,337 draws in each live run.
- Without it the replayed frame falls to 11.8 dB RGB8 PSNR against the
  control at the defaults and 11.6 dB with the original coefficients, so
  it carries most of the image.

Folding it into the composite would replace two title shaders with one the
host writes, from math not yet established. The fusion would remove only
the intermediate's write, resolve and re-read, not its sampling. That is a
shader-replacement project of its own, so MR-5 is rejected for this issue
with that ceiling recorded.

### Resolve memory copies (MR-6)

The renderer already resolves into sampled images: with
`fh1_resolve_to_textures` (on by default), one compute dispatch writes the
EDRAM rectangle into the guest memory copy and into up to two current
textures over it. The copy into memory is the part that could go, since
the textures are already current.

**Ceiling.** `fh1_debug_resolve_textures_only` (diagnostic, default off)
skips the memory stores of every resolve over 4 KB that has such a texture.
It renders wrong where memory is read. Frozen race replay on UHD 620 (1x,
MSAA off, untile off, three off/on/off blocks of 210 repeats):
**2.41 ± 0.29 ms** of GPU frame span (blocks 2.74, 1.82 and 2.67). The image
changes little (75.6 dB against the control, no pixel off by more than 8),
because few later reads land in those ranges.

**Exact prototype.** `fh1_resolve_defer_memory` left each such resolve's
memory copy owed, tracked in 1 KB blocks, and wrote it from the texture
(one small compute pass sampling the texture's 32-bit words in place) only
when something requested that memory. Requests included texture loads,
vertex or index fetches, memory export, frame dumps and later resolves.
A 32-bit tiled resolve's 32×32 macro tile is a contiguous 4 KB, so a later
resolve that covers a whole tile makes the old bytes there unowed. A
partly covered tile is written first. Unscaled 32-bit resolves into
textures without a load conversion that hold the whole rectangle
qualified. On the RTX 4080 the race and night replays are byte-identical
to the controls under the validation layer with synchronization checks.

What the race frame does with that memory, per 30 replayed frames:

| Owed 1 KB blocks | Count |
| --- | ---: |
| Overwritten whole by a later resolve (no copy needed) | 564,448 |
| Written first, under a later resolve's partial tile | 27,144 |
| Read by texture loads, so written from the texture | 147,520 |

FH1 reuses resolve memory heavily: one 1280×720 allocation receives
1280×256 strips, and a 640×360 one receives a 520×520 resolve at another
pitch. Every texture-load reader is a texture the resolve could not write
directly. These are the reflection cube's 18 face resolves (six each at
256², 128² and 64², reloaded by the cube every frame) and a 1280×720 and
a 640×360 result read through another texture.

The same UHD replay A/B saved **0.12 ± 0.16 ms** (an earlier build, whose
texture read the validation layer rejected, saved -0.16 ± 0.37 ms).
Writing a quarter of the bytes from the textures, plus about 75 extra
dispatches and their barriers a frame, used up the rest of the ceiling.
On UHD 620 the on and off images also differed, a cause not investigated
since the row failed the gate.

**MR-6 is rejected.** Removing the remaining copies would need the cube
faces resolved straight into the cube texture and the other two readers
made direct targets. That is a resolve-target change, not deferral, and
its ceiling is the copies' share of the 2.41 ms. The prototype is ShiftGlue
commit `0ee82b25`, removed again in `101ad468`; the diagnostic switch
stays.

### Tyre smoke

The drive-and-handbrake dump in
[Night lights and missing particle scope](#night-lights-and-missing-particle-scope)
gives the smoke's draws. Suppressing one blended shader at a time in its
replay, pixel shader `8A911DCC4060CAE4` (vertex shader `D0B4ADE58BA22B62`)
removes all the visible smoke and nothing else. It accounts for **6 of
the 1,889 draws** in the untiled discovery frame, all inside the
main-scene rendering. Bound textures
are a DXT5 sprite sheet, the 1280×720 float camera depth and the
1024×1024 shadow atlas, which suggests soft depth-faded particles that
receive shadows. Bound slots do not prove every branch samples them.

The filter takes the hash as a decimal: `8A911DCC4060CAE4` is
`9984794611947719396`. A mistyped decimal selects nothing, and the
benchmark then fails with "selected draw count 0", which it did here.

Frozen replays of that dump use the benchmark's three disjoint
off/on/off blocks, untile on, presentation off and per-pass profiling off,
with the shader filter on the main-scene selectors
`1024/32/4x/d1+0/32/4x/c3,1024/32/1x/d1+0/32/1x/c3`:

| Device and settings | Selected draws per frame | GPU frame-span saving, ms |
| --- | ---: | ---: |
| UHD 620, 1x, MSAA off, 210 repeats / 100 warm-up | 6 | 0.21 ± 0.48 |
| M4 Pro, 2x, 4x MSAA, 610 / 300 | 6 | Unqualified |

Controls are byte-identical within each device. The UHD controls drift
from 59.6 to 66.6 ms across the series, so the result is "below the gate",
not a measured cost. On the M4 Pro the controls move between 20.8 and
24.8 ms from run to run and the blocks disagree in sign (-0.02 ± 1.3 ms),
the same replay drift as its MSAA controls. No Android device was attached
for this run, so Mali has no smoke figure.

**MR-8 is rejected.** Batching or instancing removes draw submissions,
not the pixels the sprites cover. The batchable families are 6 smoke,
7 lamp and 76 headlight draws in the measured frames, and suppressing each
family outright stays within noise on every device that resolved it. A
fill-bound GPU such as the Mali would gain nothing from batching even if
its smoke fill were expensive, because the blended pixels remain.
