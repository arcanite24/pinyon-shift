# macOS

Pinyon Shift builds and runs natively on Apple silicon Macs. The game's
Vulkan renderer runs on Metal through MoltenVK, which the build includes. As
on Windows and Linux, you choose your own disc image, and the launcher
verifies it, builds the game on your Mac and starts it.

## Requirements

- An Apple silicon Mac (M1 or newer) with macOS 13.3 Ventura or newer. Intel
  Macs are not supported.
- Your ISO of the USA retail disc (`MS-2505`).
- About 20 GB free.
- Apple's Command Line Tools, which provide the compiler. The launcher
  offers to install them if they are missing; nothing else needs installing.

## Install and play

1. Download `PinyonShift-Launcher-macos-arm64.zip` from the
   [latest release](https://github.com/arcanite24/pinyon-shift/releases/latest),
   verify the SHA-256 listed there and open it. Move **Pinyon Shift** to
   **Applications** if you like.
2. The app is not notarized by Apple, so the first start needs your
   approval. Open it once, then go to **System Settings → Privacy & Security**
   and choose **Open Anyway** next to the message about Pinyon Shift. On macOS
   13 and 14 you can instead Control-click the app and choose **Open**.
3. If the launcher asks for the Command Line Tools, choose **Install the
   tools** and follow Apple's dialog, then **Check again**.
4. Choose **Choose disc image** and select your ISO, or drop it onto the
   launcher. Confirm ownership and choose **Verify and build**. The Mac stays
   awake until the build is done: about 20 minutes on an M4 Pro.
5. Choose **Play**. Press **F6** in game for settings.

On an M4 Pro, the 2026-10-18 free-roam qualification averaged 59.9 fps at
1x with MSAA off and a 60 fps limit. QUALITY 60 (2x, 4x MSAA) averaged
39.6 fps, so its name is a target, not a guarantee on this Mac. Start with
LOW-SPEC 60; see the renderer matrix below for the settings and limits.
The title starts at once; the stored pipelines
are compiled behind it, so the first seconds of a new scene can still hitch.

## From a terminal

The launcher runs these commands. In the install's source folder or a
repository checkout:

```bash
python3 tools/pinyon.py setup --iso ~/Downloads/forza-horizon.iso
python3 tools/pinyon.py launch
```

The `python3` that comes with the Command Line Tools is enough: `setup`
downloads a pinned Python for itself, and pinned CMake and Ninja, each
checked by SHA-256, into `.local/toolchain`.

## Where things live

```text
~/Library/Application Support/PinyonShift/source/<version>/   source, tools, game files, build
  .local/preview/user/                                       saves
  .local/preview/                                            settings, game logs, crash reports
  .local/logs/                                               setup logs
```

`PINYON_SHIFT_INSTALL_ROOT` moves the install elsewhere, for example to an
external drive.

## Troubleshooting

- **"Pinyon Shift" cannot be opened.** Approve it under Privacy & Security,
  step 2 above.
- **Setup failed.** The launcher names the step and the log. The same report
  is in `.local/logs/setup-error.json`; attach it together with the complete
  log named in the error when you file an issue. The JSON contains only a
  summary, not the compiler errors.
- **Building the translator fails in `cmake_pch.hxx`, with missing
  `std::bit_cast` or `std::byteswap`.** Keep the failed build directory and
  attach `.local/logs/rexglue-configure.log`, `rexglue-build.log` and
  `rexglue-pch-diagnostics.log` along with `setup-error.json`. Setup records
  the failed PCH's compiler version, include search, header trace and macros
  automatically. It preprocesses with the original compiler flags and
  environment without replacing build outputs; a diagnostic failure leaves
  the original build error intact. This distinguishes a different libc++ or
  a shadowed header/macro from missing compiler support. On the M4 Pro Mac
  mini, AppleClang 21.0.0 (`clang-2100.1.1.101`) with the CLT macOS 26.5 SDK
  exposes both APIs, and the filesystem PCH compiles. That does not reproduce
  or resolve the M1 Pro report in [#702](https://github.com/arcanite24/pinyon-shift/issues/702).
- **The window turns black or one colour after a resize or fullscreen change.**
  The presenter recreates the Vulkan surface on resize and keeps the Metal
  drawable at the swapchain's size before acquiring an image. Fullscreen
  defaults to a borderless window on the current desktop; it does not open a
  separate Space. `SDL_VIDEO_MAC_FULLSCREEN_SPACES=1` restores SDL's Space
  behavior for diagnosis, but that path has reported black output.
- **Free roam is too bright and flashes.** Two paths need correct luminance
  data. GPU memory tracks 4 KB guest pages so writes beside the exposure
  resolve do not discard it, even on a Mac with 16 KB host pages. Completed
  small float resolves are also copied to guest RAM for CPU exposure reads.
  Rebuild an older version; see the qualification results below. The M4 Pro
  route did not reproduce the reported bright pulses, so the original M1 Max
  exposure case still needs retesting. HDR brightness is a separate check.
- **The build cannot find a compiler.** Run `xcode-select --install` in
  Terminal, or reinstall the Command Line Tools from Apple's developer site.

## Uninstalling

Copy your saves out of `.local/preview/user` if you want to keep them, then
delete the app and `~/Library/Application Support/PinyonShift`.

## Status

| System | Status |
| --- | --- |
| Mac mini, M4 Pro, macOS 26 | Release app to a built game in 18 minutes, installed on an external drive; free roam route passes. Dev 04feee2 (2026-10-15): base and v4 builds, all 21 DLC packages imported from a ZIP and enabled, 1000 Club offline and the Horizon Rally entry on v4 |
| Other Apple silicon Macs | Not tested yet |

DLC, the title update, saves from another PC or from Xenia, crash reports,
the hardware check and the Android app use the same launcher panels and
commands as on Linux; see
[DLC, the title update and saves](LINUX.md#dlc-the-title-update-and-saves).
On a Mac, `portable.txt` goes in the folder that holds `Pinyon Shift.app`.
DLC import and the hardware check (through the MoltenVK the build ships)
were checked on the Mac mini. On 2026-10-15 the title update was imported from
its ZIP and `pinyon.py title-update build` made `macos-arm64-v4` in about 4.5
minutes after the base build; v4 started from `pinyon.py launch` with its
profile backup, shader preparation and offline 1000 Club.

## Renderer qualification

QUALITY 60 (2x scale, the game's 4x MSAA) needs a 16.67 ms budget. Qualify
each combination after a restart: scale 1x and 2x, each with MSAA off, 2x
and 4x. Use bilinear presentation, SDR, a 60 fps render limit, full shadows
and reflection rate, and `fh1_untile_predicated_tiling=false`, as the
QUALITY 60 preset sets them. Keep the same pinned seed and shader catalogs
on both platforms; never use a live save as a writable test state.

`config/render-tests/fh1-macos-quality.fh1test` waits for the title movie,
captures the parked car at script frame 1200, then drives from frame 1400
to 3600 without intermediate captures (23.33 to 60 seconds on the script
clock). The file wait can extend actual elapsed time. Align resource
samples to the capture events, rather than to process startup. Measure
frame time, process CPU, GPU time/utilization, resident
memory, device memory and surface allocations over that driving interval.
The performance CSV provides frame time, `process_cpu_ns`,
`guest_frame_gpu_time_ns`, `process_resident_mb`, `memory_device_usage_mb`
and `fh1_surface_mb`. CPU utilization is the sum of process CPU time divided
by elapsed time (100% is one core); macOS `ioreg -r -c AGXAccelerator -d 1`
provides device utilization. Record background load and memory pressure:
Apple's unified memory and clock changes can affect both readings.

For example, this is the QUALITY 60 cell in an already built checkout:

```bash
python3 tools/run-fh1-render-test.py \
  config/render-tests/fh1-macos-quality.fh1test \
  --state-root .local/render-seeds/<pinned-seed> \
  --build-directory out/build/macos-arm64-release \
  --output .local/macos-quality-2x-4x --hidden --no-performance-gate \
  --seed-vulkan-shader-storage --seed-pipeline-prewarm \
  --game-argument=--draw_resolution_scale_x=2 \
  --game-argument=--draw_resolution_scale_y=2 \
  --game-argument=--fh1_msaa_single_sample=false \
  --game-argument=--fh1_msaa_2x=false \
  --game-argument=--fh1_scaled_msaa_single_sample=false \
  --game-argument=--present_effect=bilinear \
  --game-argument=--present_hdr=false \
  --game-argument=--pinyon_shift_fh1_render_fps_limit=60 \
  --game-argument=--host_present_fps_limit=0 \
  --game-argument=--pinyon_shift_fh1_shadows=true \
  --game-argument=--pinyon_shift_fh1_env_map_rate=1 \
  --game-argument=--fh1_untile_predicated_tiling=false \
  --game-argument=--vulkan_texture_max_size=0
```

`--no-performance-gate` collects slow cells too; a route pass alone does
not certify 60 fps or correct geometry. Inspect both car captures and the
timing distribution. For exposure, repeat an interleaved pair with
`--game-argument=--fh1_readback_small_float_resolves=false` and `true`.
Both keep the existing 4 KB GPU tracking fix enabled. The readback and
fullscreen changes were proposed independently in
[ShiftGlue PR #6](https://github.com/arcanite24/shiftglue-sdk/pull/6).
The contributor's M1 Max results use an older SDK; they are not measurements
of the current M4 Pro build.

Also test fullscreen at launch, toggled by the cvar, and toggled from F6's
FULLSCREEN row while the menu paints. Inspect an OS window capture as well
as the guest capture: guest readback cannot detect a black or 1x1 Metal
drawable. Return to windowed mode and check the menu and picture again.

### M4 Pro results, 2026-10-18

Mac mini M4 Pro, 12 CPU cores, 24 GiB unified memory, macOS 26.3 (25D125),
Release ARM64, frozen base-game codegen from `45d1739`, SDK `927610f`
(the small-float readback, fullscreen and one-shot diagnostic changes). No title
update or DLC. The seed was `appdata-2026-09-27-macwarm`; the corresponding
Windows seed had the same profile SHA-256
`cc8951e814dbc750aac5c204772bef84094847273849f216b1df7462cdc314e4`.
Each cell restarted with a private copy of that seed and prewarmed shader
catalogs. The final pass used the route above, hidden, with split GPU
recording enabled and small-float readback on. These are single-run results
over 36.6–36.7 s of driving, with no captures inside the timed interval.

| Scale / MSAA | Mean fps | Median / p95 / p99 frame, ms | Mean GPU, ms | Process CPU % | GPU busy % |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1x / off | 59.85 | 16.73 / 19.61 / 20.48 | 15.36 | 142 | 51 |
| 1x / 2x | 59.95 | 16.72 / 19.55 / 20.36 | 15.34 | 146 | 57 |
| 1x / 4x | 59.55 | 16.67 / 19.86 / 20.73 | 15.83 | 137 | 61 |
| 2x / off | 59.84 | 16.57 / 19.69 / 20.58 | 15.87 | 150 | 79 |
| 2x / 2x | 53.65 | 17.94 / 22.08 / 34.61 | 17.28 | 141 | 85 |
| 2x / 4x | 39.55 | 23.16 / 34.53 / 38.69 | 24.01 | 105 | 90 |

Traffic and car pose can differ between restarts; these live-route cells
are a qualification sample, not an identical-workload A/B benchmark.
GPU time is the whole submitted guest frame, not a sum of per-pass Metal
timestamps. At the 60 fps limit it can include waits. CPU percentages use
one core as 100%; no other fleet workload used the Mac during these runs.
No forced GPU clock or power mode was applied. An earlier pass ranged from
55.2 to 59.4 fps at 1x and from
42.7 to 43.5 fps at 2x/4x with readback off/on. This variability does not
establish a readback speedup or regression. Both 2x/4x passes miss 60 fps.

| Scale / MSAA | Median Vulkan heap usage, MiB | Peak native surfaces, MiB | Median process RSS, MiB |
| --- | ---: | ---: | ---: |
| 1x / off | 895 | 62 | 451 |
| 1x / 2x | 935 | 87 | 904 |
| 1x / 4x | 960 | 117 | 916 |
| 2x / off | 3425 | 247 | 502 |
| 2x / 2x | 3571 | 347 | 464 |
| 2x / 4x | 3671 | 467 | 455 |

These columns overlap and must not be added. RSS excludes much of Metal's
memory: a separate 2x/4x drive's `vmmap -summary` snapshot reported a 4.6G
physical footprint (4.6G peak), with 837 MiB resident in its region table.
An earlier 2x/MSAA-off drive reported 4.4G. The quality snapshot also had
878 MiB swapped regions and about 6.8 GiB in the system-wide compressor
(`vm_stat`), so memory pressure is a possible contributor; background
desktop memory was not controlled. High GPU utilization is consistent
with the increased GPU cost, but does not exclude that pressure. Roughly
four times the Vulkan allocations of 1x is not evidence of a CPU leak.

An untiled-predicated-tiling control at 2x/4x returned 34.1 fps against the
earlier off run's 43.5 fps, median 28.29 against 22.24 ms, surfaces 848
against 467 MiB. These were unpaired live drives with varying car poses,
so they do not isolate a timing cost, but they do not qualify a gain.
QUALITY 60 keeps its existing off setting. A separate uncapped 1x/MSAA-off run with
it on reached 105.5 fps, median 9.30 ms, p95 11.65 ms. The older 8.35 ms,
120 Hz result on the site used a different 40 s drive and two-run medians;
it is historical, not a guarantee for every route or current build.

### Image and fullscreen gates

All six cells reached free roam (mode 17). The parked and driving captures
show filled car bodies; the reported 2 fps wireframe failure did not
reproduce on this M4 Pro. Some restarts produced a persistent gray/brown
sky and flatter reflections instead of a blue sky. This occurred with
readback both off and on, with split recording both off and on, with fast
pixel math both off and on, and with the legacy executor. Synchronous
pipeline compilation also showed it; the control logs recorded no draws
skipped for pipeline waits. None of those switches is established as a
cure, and their defaults are unchanged.

Five diagnostic runs captured 120 consecutive output frames each, at 1x
off (readback off/on), 2x/4x (off/on) and 1x/4x (on). No isolated bright
pulse exceeded both 12% over its brighter neighbor and 5 luma above the
neighbor average. Those instrumented windows do not prove the contributor's
exposure issue fixed. A current M4 Pro trace did confirm a guest CPU read
inside the luminance resolve with 4 KB tracking still enabled; see the
[resolve finding](https://arcanite24.github.io/pinyon-shift/game-rendering/#resolves).
The readback fixes that missing CPU copy without replacing the tracking fix.

`fh1-macos-fixed-frame.fh1test` arms a one-shot dump only after reaching
free roam. Use 1x, `gpu_record_thread=false`,
`spirv_fast_pixel_math=false` and an explicit `fh1_frame_dump_path`.
The route sets `fh1_frame_dump_frame=-1` to record the next complete
executor frame; its counter differs from the script clock and startup
captures can otherwise record the frontend. Split recording requests are
rejected with a warning, once, without writing a dump. See
[frame dump instructions](native-renderer/FH1_RENDER_TEST_AUTOMATION.md#frame-dumps-and-offline-replay).

The gameplay dump recorded executor frame 894 (mode 17 before and after
arming). Its two Mac replays were byte-identical to each other; each
differed from the live recording in 12,338 of 942,080 front-buffer words.
A replay golden is therefore the regression reference, rather than an
assumption that recording and replay are universally identical.

That same dump replayed on Windows/RTX 4080 at 1x/MSAA off, with fast pixel
math off on both platforms. The 1280x720 decoded images show the same car
and scene. Excluding the 16 padded rows, mean absolute RGB error was
1.165/1.120/0.830 on an 8-bit scale (RMS 3.114/2.844/2.173). In the native
10-bit channels, mean absolute error was 4.164/1023 and maximum local error
546/1023; 793,045 of 921,600 packed pixel words differed. This is a close
image comparison, not a bit-exact gate, and it does not qualify 2x/4x or HDR.
The Windows reference was the baseline SDK `b528422` build; the new CPU
readback default's Windows performance still needs a separate run.

`fh1-macos-fullscreen.fh1test` completed in windowed, initially fullscreen,
and explicit `SDL_VIDEO_MAC_FULLSCREEN_SPACES=1` runs, including menu and
cvar transitions and return to windowed mode. All 18 captures in the final
three runs were in free roam (mode 17). Guest and presented readbacks
were available. The SSH session's `CGPreflightScreenCaptureAccess()` was
false, so no OS window image was available: black output, a 1x1 drawable,
native Space transitions and HDR remain **unqualified visually**. No privacy
permissions or normal install settings were changed. Before closing #548,
check these transitions interactively and retest the original M1 Max scene
and save; QUALITY 60 still fails its performance budget on this M4 Pro.
