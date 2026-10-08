# Odin 2 graphics and performance

Active goal, October 6, 2026: fix Android free-roam rendering and native menu
text, and improve sustained performance on the Odin 2 Portal (Adreno 740).
Preserve player progress and verify changes on the actual device.

## Ordered work

- [x] Capture a 30-second free-roam video, six extracted frames and six native
  free-roam/pause captures from an isolated clone of the Odin state.
- [x] Reproduce and fix stepped car-paint shading and bright foliage/horizon
  (pushed pixel textures, SDK `fa09596`; see the fix below).
- [x] Identify the source of temporal ghosting while driving: the same fault.
  Shadows, exposure and the passes after them read an empty shadow map.
- [x] Missing rear bodywork, black geometry, the missing gauge backing and the
  half-screen seam: gone with the same fix, in replays and live captures.
- [x] Pause menu, map, SETTINGS (host) and HUD text match desktop.
- [x] Compare 4x MSAA with MSAA off: 4x costs about 4-10 ms of GPU a frame.
- [x] GPU timing per phase, rendering and resolve without Snapdragon Profiler
  (`fh1_native_gpu_profile`, SDK `01aae09`); KGSL clock and busy sampling.
- [x] Fix the measured bottlenecks; see the performance section below.
- [x] Install without clearing app data; all 17 normal user files keep their
  hashes after every run of this work.

## Evidence and scope

The first installed-build run, `20261006T223212Z-p15108`, completes at frame
5100 with six captures and no route failures. All 17 files in the normal Odin
user tree retain their hashes. Evidence stays private under
`D:/horizon1-recomp-tests/odin-graphics-20261006/`: `free-roam.mp4`, extracted
frames, native output, session logs and `qualification.json`. This APK predates
the subsequent desktop issue-work commits; identify candidate build provenance
before comparing a newer APK. The MSAA-off run `20261006T223614Z-p16020`
completes at frame 1950 with four captures and unchanged normal-save hashes.
Ghosting persists with MSAA off; black elongated geometry is also visible.
Its nominal settings capture still shows pause, so settings-page coverage
remains pending. Different poses/route lengths and sampling prevent a matched
graphics or performance comparison.

The normal configuration explicitly enables 4x MSAA, uses 1x resolution and
caps guest/render presentation at 30 FPS. An unset MSAA default does not replace
this explicit choice. The visual run includes recording/tracing/capture work;
its whole-run FPS is not a controlled performance baseline or a fix result.

## Profiling alternatives

- The existing per-frame CSV and `tools/summarize-performance.py` provide
  frame distributions and available game/renderer counters. Separate loading,
  driving and menus; record instrumented GPU timers in separate runs.
- [Perfetto system tracing](https://perfetto.dev/docs/getting-started/system-tracing)
  normally correlates scheduling, frequencies and presentation. On the current
  Odin firmware, `traced_probes` repeatedly restarts after an ftrace field-format
  error for `f2fs_truncate_partial_nodes.nid`. The first trace contains 414
  FrameTimeline rows, zero scheduling/counter rows and three dropped negative
  timestamps. It is not a valid CPU trace. SDL uses a SurfaceView; app timeline
  coverage must be verified rather than assumed from compositor rows.
- Perfetto `linux.perf` is registered, but a ten-second targeted recording
  returns zero samples on this firmware. Registration alone is insufficient.
- [Simpleperf](https://developer.android.com/ndk/guides/simpleperf) is present
  and the application manifest permits shell profiling. Verify process/thread
  attribution and symbol coverage before treating a recording as usable.
  A ten-second 100 Hz native recording succeeds: 3,615 CPU samples, none lost,
  attributed to game PID 16020 with game/runtime function names resolved.
  Kernel function names remain unavailable; no device permissions changed.
  Initial CPU work includes GPU-command yielding; correlate with driving
  intervals before choosing an optimization. Native samples are CPU cost, not
  GPU duration or frame-time percentages.
  Native CPU counters/call stacks complement renderer GPU timings; they do
  not supply unavailable vendor GPU performance counters.

Use a new state under the device's `files/qualification` directory and the
`env.PINYON_SHIFT_STATE_ROOT` intent override. The current Android `run --seed`
helper replaces the normal state user/config tree, so do not use it for this
qualification. Copy source state read-only and never clear or replace the
player's save. Keep video runs separate from performance comparisons.


## Wait-policy candidate and desktop comparison

The first instrumented Odin recording resolves CPU symbols without Snapdragon
Profiler. With VSync off, the shared `WAIT_REG_MEM` path bypassed Android's
configured 100 microsecond sleep: the original visual run records 33,322 waits
and zero sleeps. The candidate honors a positive existing sleep setting even
without VSync; zero retains the original polling behavior. The actual policy
regression covers short sleeps, the initial yield period, and both VSync states.

A signed/aligned candidate APK with matching packaged libraries is installed
without clearing app data. Private session `20261006T224549Z-p16710` completes
all eight alternating 20-second windows at frame 6000, accepts each live setting
and records 9,452 slept waits. Commands-thread CPU falls from 93–98% of one core
to 13–19%, an 81–86% reduction across four pairs. This is thread CPU usage,
not overall frame-time savings. Three complete throughput pairs change by
-0.6%, -2.2% and +0.3%; no FPS improvement is claimed. Polling all thread stat
files adds device work: repeat with only the commands TID and an unpolled run
before relying on absolute performance. Driving and sustained thermal tests
remain pending. All 17 normal user files retain their hashes.

Desktop Vulkan control `20261006T224732Z-p22912` passes four captures from a
read-only Odin save/config clone with the supported desktop shader catalogs.
The stationary scene is clear on desktop while Android has strong ghosting,
washed-out sky/foliage and stepped paint shading. The pause-menu backing has
the same textured aesthetic on desktop; other affected text pages still need
capture. These controls narrow the graphics investigation but do not fix it.

Receipts remain beside the original video: `wait-ab-qualification.json`,
`candidate-verification.json`, native output and the desktop-control result.

The CPU comparison uses fixed held inputs. The car ultimately reverses into
the festival barriers, so these windows are not a stationary, pixel-matched
benchmark. The thread CPU reduction is reproducible across the four pairs;
driving frame times still require separate qualification.

## Graphics isolation results

Private stock-driver probes retain the player's normal state. Disabling direct
texture resolves does not remove the free-roam defects. Toggling folded clears
off introduces stronger ghosting which persists after restoring them; this
dynamic test does not isolate the cause. Disabling asynchronous pipeline
compilation in a fresh session also retains strong ghosting, clipped brightness
and stepped shading.

A private Turnip 26.0.0 R8 comparison verifies the custom driver loaded, but its
guest captures are black. It is not a qualified replacement driver. The normal
driver selection is unchanged.

Desktop run `20261006T225628Z-p52888` completes the control route with the
validation setting requested. Its enabled layers do not include Khronos
validation, so it cannot establish absence of Vulkan validation errors.
Per-probe receipts and frames are in `graphics-probes.json` and the corresponding
output directories beside the original video. Texture-upload differences,
actual affected menu pages and sustained driving performance remain open.

Fresh stock-driver session `20261006T225925Z-p25341` enables compute texture
upload and disables MSAA. It completes four captures at frame 1950; the same
ghosting, clipped sky/foliage and stepped paint remain. This upload-path setting
does not fix the defects. All 17 normal user files retain their original hashes
after the graphics probes.

## Device validation and intermittent ghosting

A diagnostic APK uses the same native libraries with debugging enabled. Official
Khronos 1.4.363.0 validation binaries load on the stock Odin driver. Core run
`20261006T230344Z-p26611` and a second run with the documented `validate_sync=1`
property complete four captures each without reported Vulkan errors or
synchronization hazards. Warnings concern unused shader outputs and a swapchain
transform mismatch. These checks do not cover every renderer defect or host
memory race. Validation runs are not performance comparisons. The release APK,
all original GPU-debug settings and the original synchronization property are
restored and verified (`validation-device-restored.json`).

Splitting every draw into its own rendering does not clear the defects. A
constant-upload preference comparison produces clearer stationary frames for
both settings, but both actually select cached memory type 6 on this driver.
No fix can be attributed to that setting; ghosting is intermittent. Sky/foliage
clipping and stepped paint remain. The next stronger control records and replays
identical GPU commands across devices, using the existing frame-dump tools.

## Frozen command-stream comparison

Odin session `20261006T231016Z-p28521` records swap 1000 as a 76 MB private frame
dump. The recorded frame exhibits ghosting. Replaying this exact command stream
on desktop draws a smooth car and clear scene; standalone Odin replay reproduces
ghosting and stepped shading, with missing HUD backing. Both execute 2,724 draws
and 91 resolves with no executor skips. The standalone fixture removes active
game simulation from this comparison; it does not prove which renderer stage is
wrong. Captured textures may include earlier frame history.

The first desktop replay executes zero draws because the seed enables the
decoder/recorder split. That comparison is rejected. `replay-fh1-frame.py` now
forces direct decoding, alongside synchronous compilation. The corrected helper
is verified against the captured stream with actual draws and front-buffer data.

On the same Odin replay, disabling stencil export and enabling compute texture
upload each produce a byte-identical front buffer to the baseline. These paths
do not explain the fixture's corruption. Receipts are in `replay-probes.json`;
decoded images are `odin-recorded.png`, `desktop-replayed.png` and
`odin-replayed.png` beside the original video. No graphics fix is claimed.

Device validation follows the [Android validation-layer workflow](https://developer.android.com/ndk/guides/graphics/validation-layer)
and [Khronos synchronization settings](https://github.com/KhronosGroup/Vulkan-ValidationLayers/blob/main/docs/syncval_usage.md).


## The fix: pushed pixel textures (2026-10-07)

A frame dump of free-roam swap 600 replayed on the Odin and on desktop, with
every resolve's output dumped (`fh1_resolve_dump_dir`), first diverges at
resolve 9, the screen-space shadow mask. Drawn alone, its first shadow draw
(pixel shader `93626E75`, four comparisons against the 1024x1024 `k_24_8`
shadow map) gives desktop's five levels; on the Odin its output equals a run
with that fetch nulled. The shadow map's guest bytes and its host `R32_SFLOAT`
image match desktop (dumped with the new `fh1_debug_dump_range`, SDK
`7f0d8fb`), so the draw reads nothing through a valid view: only
`vulkan_push_texture_descriptors=false` brings the frame back (front buffer
mean difference 49.7 to 12.8, the rest MSAA and rounding). One write per
binding, a push every draw and no null descriptors did not help. Qualcomm GPUs
now write pixel textures into sets (SDK `fa09596`). Every shadow is lit, so
the exposure overshoots: that was the white sky, the washed-out foliage, the
stepped paint and the noise; the ghosting and the seam followed from passes
reading the same textures.

Driving, menus, the map and the host SETTINGS now match the desktop captures.
Receipts: `D:/horizon1-recomp-tests/odin/` (`frame600.dump`, `rp-*` replays,
`fix-*` and `final-*` routes).

## Performance (2026-10-07)

GPU-bound throughout: the Adreno 740 holds its 680 MHz maximum at 90-99 %
busy while driving, so `android_gpu_turbo` has nothing to add, and the CPU
threads have room (recorder 8-9 ms, title thread 10-20 ms a frame).
Long free-roam drive, matched runs, frame cap off:

| Change | 1x GPU frame | 4x GPU frame |
| --- | --- | --- |
| Before (fixed renderer) | 36.2 ms | 42.5 ms |
| `vulkan_texture_load_compute_copy` on Android (resolves write their textures) | 31.9 ms | |
| `spirv_fast_pixel_math` on Android | 32.4 ms | |
| Both (SDK `180da5b`) | 28.0 ms | 38.7 ms |

A replay with both changes moves 2,641 of 921,600 pixels by more than
64/1023 (scattered foliage and shadow noise). Bindless textures (PD-4) are
now the Android default (SDK `b5e49a7`): the recorder's CPU falls from 9.25
and 9.05 to 7.67 and 7.81 ms a frame in two pairs, frame time unchanged.
`spirv_implicit_lod_2d` gains nothing (29.9 ms against 28.0).

Measured and not taken: copying CPU-written memory at the start of the
submission instead of where it is needed (about 18 copies a frame no longer
end the open rendering; GPU 38.7 to 38.1 ms, noise), and running draws that
write nothing inside the open rendering (only 11,500 of 84,000 had one).

Where the time goes now (1x, frame profile from opening to swap, 37 ms):
the main scene (`1024/32/4x/d1+0/32/4x/c3`, 16 renderings a frame) about
20 ms; the post chain (`0/16/1x/c2`, `0/16/1x/c3`, `0/2/1x/c3`, the 2x
`128/4` pass) about 8 ms; draws without attachments 2 ms; resolves 4.9;
transfers 2.6; texture reloads 2.8. The 4x/1x aliasing of the main depth
buffer (DR-2.1) is most of 4x's extra transfers. The busy free-roam drive
runs about 22 fps at 1x and 19 at 4x; the frame limit of 30 costs nothing
there (the limited and unlimited runs' driving windows match, 44.4 and
44.5 ms), only menus and loading run faster without it. Further GPU gains
need shader work on the main scene or the post chain.

### Shader specialization and further experiments (2026-10-08)

Every translated texture fetch read its signedness from a system constant
and switched on it. `spirv_specialize_texture_signs` (Android default, SDK
`efcbb82`) makes those words specialization constants set from the bound
textures, in pipelines kept beside the stored ones (the stored description
format and desktop prewarm catalogs are unchanged). 1x drive, two
interleaved pairs: frame 45.8 and 46.9 to 43.8 and 44.0 ms; the replay is
byte-identical. Draws that write nothing outside occlusion queries are now
skipped (SDK `9187b27`; 120 a frame, replay identical, gain within noise).

Measured and not taken:

| Experiment | Result |
| --- | --- |
| 7e3 targets as 32-bit B10G11R11 (half the main scene's color traffic) | GPU 45.4 to 45.8 ms at 4x: the scene is shader-bound, not bandwidth-bound; image drifts |
| Predicated forward jumps falling through (113 of 153 pixel shaders lose the program counter loop) | Replay identical; frame 42.8/41.7 to 42.7/41.2 ms, noise |
| Skipping the bloom chain (its scale is zeroed when bloom is off) | Every post group changes the frame: none is dead work |
| Adaptive frame limit | The limit costs nothing while driving (limited and unlimited windows 44.4 and 44.5 ms) |
| `spirv_implicit_lod_2d`, coordinate sanitizing, `android_gpu_turbo` | No gain; the GPU already holds 680 MHz |
| Transfers rendering only the rectangles they copy | 4x mean 49.5 and 49.1 ms off, 49.9 and 49.5 on: no gain |
| `RelaxedPrecision` on pixel math | No gain beyond noise |
| Skipping each 4x/1x depth transfer pair (`fh1_debug_skip_transfers`, SDK `12dda6e`) | Every pair is needed (the image breaks); each costs only about 0.7 ms |

### Turnip on the Odin (2026-10-08)

Mesa Turnip (`turnip-r8`, loaded with `android_gpu_driver` from
`files/state/drivers/turnip-r8`) is the largest remaining gain. It
advertises sparse residency buffers, but resolves written into sparse
shared memory read back as zeros, so the frame was black; the shared memory
now uses a plain buffer on Turnip (SDK `cd5c76c`). Long drive, frame cap
off, two interleaved pairs each:

| Driver | 1x frame median / p95 | 4x frame median / p95 |
| --- | --- | --- |
| Qualcomm (stock) | 41.5, 41.1 / 58.4, 58.3 ms | 48.6, 48.9 / 74.4, 78.3 ms |
| Turnip | 36.9, 37.2 / 45.2, 46.3 ms | 40.9, 41.0 / 50.1, 50.8 ms |

Turnip is 11 % faster at 1x and 16 % at 4x MSAA, and its p95 frame is a
third lower. Its replay of frame 600 matches the stock driver (front-buffer
mean difference 4.1 of 255, foliage noise) and its drive captures match.
The recommended Odin setup is Turnip with `android_gpu_driver = "turnip-r8"`;
the package does not ship a driver. Its own choice between tiled (GMEM)
and direct (sysmem) rendering is already the best: `TU_DEBUG=sysmem`
measures the same (4x mean 41.3 ms), and `TU_DEBUG=gmem` is slower (mean
56.4 ms, with a bimodal frame time) and leaves grainy edges.

GPU profile at 4x, stock against Turnip (ms a frame): frame 45.1 / 42.8,
transfers 5.4 / 3.2, resolves 5.7 / 4.7, texture reloads 3.2 / 2.6. The
main scene (`1024/32/4x/d1+0/32/4x/c3`, about 18 renderings) is 24.8 /
25.6 ms, 60 % of the frame, and it is the game's own shading at 4x MSAA:
bandwidth, precision, specialization and pass-structure changes above did
not move it.

### Turnip shader work (2026-10-08)

`vulkan_pipeline_statistics` (SDK `8d09b0d`) logs the driver's statistics
for every pipeline through `VK_KHR_pipeline_executable_properties`; Turnip
reports them, and nothing spills. `vulkan_debug_flat_pixel_shaders` (same
commit) bounds pixel shading: with every guest pixel shader writing a
constant, the 4x frame falls from 41.7 to 30.5 ms, so pixel shading is
about 11 ms of it.

Taken: 2D pixel shader fetches with implicit LOD on Turnip
(`spirv_implicit_lod_2d_turnip`, default on, SDK `a17fd5f`). 4x drive, two
interleaved pairs: 39.8 and 40.1 ms against 42.4 and 41.6; 1x median 35.5
ms (37.0 before). The frame 600 replay differs from explicit gradients by
a mean of 0.07, 0.01 % of pixels by more than 16 levels.

Measured and not taken:

| Experiment | Result |
| --- | --- |
| The once-through main loop left unrollable (Mesa honors `DontUnroll`) | Loops gone from 208 of 210 pixel shaders and 189 vertex shaders; instructions 457 to 446 and 1,196 to 1,172; frame unchanged (41.49 against 41.49 ms) |
| Shared memory loads (four 128 MB bindings) and endian swaps with selects instead of branches | Vertex shaders 1,196 to 749 instructions, load stalls 1,059 to 183 cycles; frame unchanged in two pairs (41.8/42.2, 51.9/51.9 ms): vertex work does not bound the frame |
| `TU_DEBUG=gmem` / `sysmem` | See above; the driver's choice is best |

DR-2.1's one host image for the main depth's 4x and 1x views does not
apply to MSAA on Vulkan: a 4x image cannot alias a single-sampled one of
twice the size, and supersampling it instead would shade the main scene
four times. The transfers it would remove cost 3.2 ms on Turnip, each
pair needed.

What remains is the game's own pixel shading and geometry in the main
scene (about 23.5 ms of a 40 ms 4x frame on Turnip), resolves (4.6 ms,
about 0.5 ms for each 1280x256 4x color resolve, which moves about 13 MB:
27 GB/s, near the memory's practical rate, so the shaders' 1,300-1,950
mostly untaken instructions are not what costs) and the post chain's 43
small renderings and 21 small resolves a frame (about 2 ms, each step
waiting on the last). The GPU is 91-93 % busy at 680 MHz throughout. At
1x the Odin now runs the busy drive at about 28 fps (35.5 ms) with Turnip,
against 24 fps (41.3 ms) on the stock driver before this round.

What remains is the game's own shading (main scene about 20 ms of a 1x
frame) and, at 4x MSAA, the main depth buffer's 4x/1x views copied back and
forth (about 15,000 tile-passes a frame, 5.3 ms): one host image for both
views is DR-2.1's deferred per-surface scale.

### Where the 4x Turnip frame goes (2026-10-08)

Bounds measured on the 4x drive (about 40 ms a frame), each a diagnostic
that breaks the image (SDK `8d09b0d`, `d604440`):

| Removed | Frame | So it costs |
| --- | --- | --- |
| Pixel shading (`vulkan_debug_flat_pixel_shaders`) | 30.5 ms | about 11 ms |
| All but each draw's first triangle (`fh1_debug_tiny_draws`) | 32.1 ms | about 8 ms with the pixels it keeps |
| Clears (`fh1_debug_skip_clears`) | 39.9 against 41.4 ms | about 1.5 ms |
| LRZ (`TU_DEBUG=nolrz`) | 40.1 against 39.8 ms | nothing: no hidden shading for it to save |

Per pixel shader (`fh1_native_gpu_profile_draws`), the cost is spread
across about 200 shaders: the heaviest takes 1.5 ms over 129 draws a frame
(298 instructions, one fetch), the next 0.9 ms; none spills, and the
translator changes above did not move them. The rest of the frame, with
shading and geometry gone, is about 30 ms: resolves 4.5, transfers 3,
texture reloads 2.5, clears 1.5, and the cost of about 3,000 draws and of
the renderings the game's own order breaks up (63 a frame by resolves, 14
by CPU-written memory uploads, 6.5 by texture loads), each a drain of the
GPU between render and compute work. Constants are about 2 KB a draw
(`gpu_constant_census`). Turnip has no performance counter extension to
split that remainder further.

### Fewer drains between renderings (2026-10-08)

With rendering spans ending at the rendering (SDK `3a45f5d`), the 4x
Turnip profile split into renderings 16.4 ms (the main scene 11.0),
resolves 4.4, transfers 2.7, texture reloads 2.5 and about 14.6 ms in no
span: the drains and flushes between about 300 barrier batches a frame
(`gpu_barrier_census`). Constant set rebinds cost nothing measurable
(`fh1_debug_keep_constant_binds`: 30.4 against 30.0 ms with tiny draws).

Taken:

| Change | Effect |
| --- | --- |
| Resolves write outdated textures they cover whole (`fh1_direct_resolve_outdated`, SDK `200c4c0`) | Direct writes from 58 to 73 % of resolves; 38.8 and 38.9 ms against 39.4 and 39.9 |
| Small 4-byte textures get the raw-bits view (`vulkan_small_texture_copy_views`, SDK `d003d06`) | The bloom and luminance chains (320x192 down to 2x2) are written by their resolves: resolve-sourced reloads from 67 to 17 a frame, barrier batches from about 300 to about 200; 38.5 and 38.3 ms against 39.1 and 39.0 |

| Resolve image stores skip texels outside the texture, so 4x4 and 2x2 textures under 8x8 resolves are written directly (`fh1_resolve_bounded_image_writes`, SDK `815af3c`) | Resolve-sourced reloads from 18 to 6 a frame; 38.2 and 38.6 ms against 38.7 and 38.9 |

All replays of frame 600 are identical to before and the drive captures
render correctly. Still reloading, about 6 a frame: the 1024x1024 depth
shadow atlas, whose memory a 1280x720 8888 resolve overwrites in part
each frame, so its own 520x520 resolve leaves it outdated (writing it
directly would need validity tracked per region of a texture), and
textures resolved in bands. Skipping every shared memory barrier after
resolves (unsafe, a bound) gained nothing (38.1 and 38.8 against 38.5 and
38.5 ms): the waits are the real dependencies, not the buffer barriers. Letting depth resolves also write
the 8_8_8_8 textures over their destination (the one sampled last)
changed no reload count (6 a frame) or frame time, so it was not kept.
The GPU's highest clock is 680 MHz, which it already holds. The remaining barriers are mostly the
pair around each of about 60 resolves a frame (rendering to the resolve's
compute and back), which the game's order of render, resolve and sample
makes necessary.

### The last reloads (2026-10-08)

Skipping every remaining resolve-sourced reload (`fh1_debug_skip_resolve_reloads`,
stale images, a bound) took the 4x frame from 38.4 and 39.4 to 36.0 and
36.7 ms, so the 5-6 reloads left (18 MB a frame) were worth 2.5 ms. Their
causes, from `fh1_texture_reload_probe` with the sampled textures' keys:

| Cause | Change | Effect |
| --- | --- | --- |
| The 1280x720 resolve targets fetched with and without packed mips made two textures over the same memory | Keys clear unused packed mips (`texture_key_unused_packed_mips`, SDK `4ea590d`) | Reload bytes 18.5 to 14.8 MB; 37.8 and 37.7 against 38.6 and 38.8 ms |
| The depth resolve is sampled as a depth texture and as 8_8_8_8 texels | Resolves write up to two textures (`fh1_resolve_two_textures`) | Reload bytes 14.4 to 10.9 MB; four pairs, mean 38.40 against 39.12 ms |

Left: the two 1024x1024 depth shadow atlases (memory overwritten in part
by a 1280x720 resolve each frame, then resolved only 520x520) and a few
textures resolved in bands; about 11 MB a frame. Skipping only the atlases' reloads
(`fh1_debug_skip_resolve_reloads_format=22`, stale images) measured 38.19
against 38.17 and 37.27 against 38.76 ms: at most about 0.7 ms, and a
correct fix would keep reloading the overwritten parts outside the 520x520
resolve, so it was not built.

### A newer Turnip (2026-10-08)

Turnip Gen8 V37 (Mesa, Vulkan 1.4.359, packaged for a8xx but running the
Adreno 740 as `Turnip Adreno (TM) 740`, API 1.4.363), already on the PC
from the 8 Elite work, against `turnip-r8` with the same build:

| Busy drive | turnip-r8 | Gen8 V37 |
| --- | --- | --- |
| 4x, two interleaved pairs | 38.7, 38.8 ms | 32.4, 32.4 ms (median 32.3, p95 38.6) |
| 1x | 34.3 ms (median 33.8) | 28.2 ms (median 27.9, p95 34.2) |

The frame 600 replay is identical to `turnip-r8`'s (front buffer mean
difference 0.0; 12.61 from the desktop reference for both) and the drive
capture renders correctly. Gen8 V37 is the recommended Odin driver: the
busy drive now runs about 31 fps at 4x and 36 fps at 1x.

Its GPU profile (4x) differs from `turnip-r8`'s mostly in what lies
between the work: the labeled spans cover 32.1 of a 34.1 ms profiled frame
(against about 14.6 ms in no span before), so barriers and switches
between rendering and compute cost it far less. The GPU is 99 % busy. Its
own choice of tiled or direct rendering stays best: default 32.0 ms,
`TU_DEBUG=sysmem` 32.9, `TU_DEBUG=gmem` 55.4.

### Balemuni Apex v2 (2026-10-08)

A community Turnip build (Mesa 26.3 development, b9a2bf3, "GCM" and other
tuning), reported to run other games better, against Gen8 V37 on the same
build, interleaved:

| Busy drive | Gen8 V37 | Balemuni Apex v2 |
| --- | --- | --- |
| 4x | 32.6, 32.4 ms | 35.1, 34.3 ms |
| 1x | 28.6 ms | 31.3 ms |

It also renders FH1 wrongly: lighting crushed toward black in the drive
capture and in the frame 600 replay (mean difference 112.7 from Gen8
V37's, 62 % of pixels by more than 16). Gen8 V37 stays the Odin driver;
the player state now loads it (`android_gpu_driver = "turnip-gen8-v37"`).

### What bounds the Gen8 V37 frame (2026-10-08)

The same bounds as before, on Gen8 V37 (4x drive): the frame 32.4 ms,
flat pixel shaders 25.7, each draw's first triangle only 24.6, the GPU 99
% busy in all three. So pixel shading is about 6.7 ms and all draw work
about 8 ms; the rest is resolves (6.3 ms), transfers (3.9), the full-screen
post passes and reloads, all real GPU work now that the waits between it
are gone. Skipping the per-sample divisions in resolves of the surface
that owns the tiles (the usual case) changed neither the resolves' 6.3 ms
nor the frame (32.3 against 32.4 ms): they are bound by memory traffic,
not arithmetic, so it was not kept. Keeping the 7e3 render targets as 32-bit
B10G11R11 instead of 64-bit float16 (which loses their alpha, so only a
bound) gave 31.4 and 31.7 against 32.1 and 32.2 ms: at most about 0.55 ms,
and a correct 32-bit 7e3 would need integer storage with shader packing,
which gives up hardware blending, so it was not built.

### Predicated tiling rendered once (2026-10-08)

FH1 draws its 720p scene in three predicated tiles (rows 0-256, 256-512
and 512-720, bin selects 3, C and 30), replaying the same command buffers
for each. Objects carry bin masks (8, A, 28, ...) and their own predicated
sub-buffers; packets predicated on a whole tile's mask (C, 30) set that
tile's window offset, window scissor and resolve destination. Skipping the
later tiles' draws outright (a wrong image) bounded the cost at 8.8 ms of
the 1x frame, and the game's own NonTiling scenario, selected through a
hook on its tiling-scenario load, drops the static world on both Vulkan and
D3D12, so the tiles are merged on the host instead
(`fh1_untile_predicated_tiling`, SDK `b4a9f72`, default on for Android):
the executor's surfaces are 720 rows tall, the first tile runs every bin's
packets except the whole-tile ones over the full height, the later tiles'
draws are skipped, and their resolves and resolve clears address their own
band's rows. The frame dump recorder flattens indirect buffers it ran, so
replays of a tiled recording lack the sub-buffers the first tile now runs;
only live runs test it.

| Busy drive, Gen8 V37 | Tiled | Untiled |
| --- | --- | --- |
| 4x | 32.0, 32.6 ms | 29.2, 29.5 ms |
| 1x | 28.3, 28.8 ms | 25.4, 25.5 ms |

The drive, race, map and photo mode captures match tiled ones (no seam at
the tile edges). The rest of the 8.8 ms bound was the later tiles' pixels,
which the untiled first tile still shades. Turnip already renders these
passes in system memory: `TU_DEBUG=sysmem` measured 28.6 ms against 28.9
ms by default, and forcing GMEM 50.4 ms, so the renderings broken by
resolves and uploads cost no extra tile loads and stores.

### Render scenario settings toward 60 fps (2026-10-08)

The render scenarios (`renderscenarios.zip`, `Horizon_Race.xml` for free
roam) were tried one setting at a time as asset mods in private states
(1x drive, untiled, stock about 25.0 ms):

| Setting | 1x drive |
| --- | --- |
| `EnvMapFrequencyScale` 0.25 | 22.7 ms, reflections look the same |
| `EnvMapFrequencyScale` 0 | 22.3 ms, reflections go dark |
| `CrowdDraw` 0; car LOD distances halved; `ParticleRateScale` 0.5 | no change |
| `CarDrawDriver`, `CollidableShadows`, `CrowdDrawShadows`, `SoftParticles`, `CarDamageTextures` 0, `HalfRateMirror`, `HalfRateBloom` | no change |
| `SkipShadowMapUnlessCockpit` 1 | 16.7 ms, the world in full shadow |

A mod switches the player to the modded profile, so both levers are host
hooks instead. After each DynamicRenderSettings control loads (0x82D81298,
r30 the control, r26 its scenario; controls are embedded in the scenario
at offsets from the table at 0x8321D848, index = id), the hook scales
`EnvMapFrequencyScale` (id 30) by `pinyon_shift_fh1_env_map_rate`, 0.25 on
Android (2.1 ms). `SkipShadowMapUnlessCockpit` (id 35, unused by the
game's own scenarios) drops the cascaded shadow maps, a screen depth
pre-pass and the screen-space shadow mask, about 6.4 ms; left alone, the
mask keeps its last contents, zeros on a fresh start, and the world is
fully shadowed. `pinyon_shift_fh1_shadows` (off by default on Android)
waits until the FH1 executor has seen the mask resolved once (1x 8888 at
EDRAM tile 720 into a 1280x720 texture, SDK `85625d3`), then sets the
skip in every gameplay scenario and keeps the mask texture white, so the
world is lit without shadows.

With both defaults (busy drive, Gen8 V37):

| | Frame | GPU |
| --- | --- | --- |
| 1x | 16.69 ms (the 60 fps cap), p95 16.9 | 15.5 ms |
| 4x | 19.2 ms, p95 23.2 | 18.6 ms |

The horizontal smear in some captures taken in turns is the game's
camera motion blur; captures with shadows on show it as well.

### In-game settings and desktop (2026-10-08)

The three settings apply while the game runs: the reflection rate and
shadows are rewritten in every recorded scenario at the next frame (the
game reads both each frame), and SINGLE-PASS SCENE rebuilds the Vulkan
renderer between frames like a resolution scale change (80 ms). A route
that switches them mid-drive on the Odin (GPU about 25 ms with shadows, 15.5
without, back to about 25) and on the desktop renders each phase
correctly. The Android presets are QUALITY 30 (4x, shadows) and SMOOTH 60
(1x, no shadows), both single-pass with quarter-rate reflections.

Desktop (Ryzen 7 5800X, RTX 4080, Vulkan, busy drive, hidden window):

| | Default | Single-pass | Single-pass, shadows off |
| --- | --- | --- | --- |
| 1x frame | 9.05, 8.86 ms | 8.91 ms | 8.81 ms |
| 3x GPU | 12.48, 11.36 ms | 11.89 ms | 8.38 ms |

1x is CPU-bound on the desktop, so neither changes its frame; at 3x
single-pass is within the noise and shadows off saves about 3.5 ms. The
desktop keeps both at the game's defaults.
