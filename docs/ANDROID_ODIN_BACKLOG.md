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
about 0.5 ms for each 1280x256 4x color resolve) and the post chain's 43
small renderings and 21 small resolves a frame (about 2 ms, each step
waiting on the last). The GPU is 91-93 % busy at 680 MHz throughout. At
1x the Odin now runs the busy drive at about 28 fps (35.5 ms) with Turnip,
against 24 fps (41.3 ms) on the stock driver before this round.

What remains is the game's own shading (main scene about 20 ms of a 1x
frame) and, at 4x MSAA, the main depth buffer's 4x/1x views copied back and
forth (about 15,000 tile-passes a frame, 5.3 ms): one host image for both
views is DR-2.1's deferred per-surface scale.