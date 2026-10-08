# Android port backlog

Status: **open; created 2026-09-30** at `dev` checkpoint `542d2ae` (ShiftGlue
`4de586b`). This is the detailed plan for NP-14 of the
[native port backlog](NATIVE_PORT_BACKLOG.md#np-14-android), written as a
sibling of that document and of the
[performance backlog](PERFORMANCE_BACKLOG.md): same slice and row IDs
(`AP-n`, `AP-n.m`), sizes, dependency and gate conventions. It was written
from a read-only audit of the SDK runtime, the Vulkan renderer, the build
pipeline and the host layer; nothing here has been built or run on ARM64 or
Android. Every claim about the code cites the tree at the checkpoint above
(`sdk/` stands for `thirdparty/shiftglue-sdk/`). Claims about mobile GPUs,
devices and Android platform behaviour that the repository cannot show are
marked **guess** and have a row that verifies them before anything depends on
them. Raw notes are kept locally under `.local/backlog-research/` and are not
distributed.

## Progress (2026-10-01)

Execution started on 2026-10-01 with the target narrowed to high-end Android
handhelds and phones, **Snapdragon 8 Gen 2 or newer** (Adreno 740+, 12 GB,
Android 13+), which sets `minSdk` 33. No such device was available, so the
ARM64 work ran on an **Android 16 arm64 emulator on an Apple M4 Pro** (a real
weakly ordered AArch64 CPU; Vulkan 1.4 through gfxstream on MoltenVK, no
geometry shaders, 4 KiB pages), driven from the Windows PC through an adb
tunnel. Rows that need the reference device stay open.

| Row | State | Evidence |
| --- | --- | --- |
| AP-0.1 null GPU plugin | **Done** | `gpu_backend=null` in `rexgpu-fh1`; `run-fh1-render-test.py --null-gpu`; `fh1-opening-sync` and `fh1-buy-car` pass on Windows with the same save write sequence as Vulkan |
| AP-0.2 memory ordering | **Done** | `sync`/`eieio` lower to a full fence, `lwsync` to acquire-release, `isync` to acquire, through `REX_PPC_*` macros that are empty on x86-64 (70 + 230 + 20 sites in FH1) |
| AP-0.3 ARM64 build | **Done (Android)** | `android-arm64-*` presets; every target links with NDK r29; Linux ARM64 presets not added |
| AP-0.4 boot and opening route | **Done (Android)** | `fh1-opening-sync` completes on the emulator with `--null-gpu`, simulation-time ratio 1.037; fixes on the way: memfd shared memory, reserve-then-fix guest arena, module library names, fault-handler chaining, socket permission |
| AP-0.5 parity gates | **Mostly done** | On the emulator with `--gpu_backend=null`: `fh1-opening-sync`, `fh1-buy-car` (three consecutive runs), `fh1-race-sync`, `fh1-free-roam`, `fh1-pause` and `fh1-timing-straight` pass with simulation-time ratios 1.01-1.07; the vehicle state matches Windows to three decimals at `event-ready`. Found and fixed on the way: APCs never delivered (bionic `sigqueue` takes a process id), a second `pthread_join` aborting on bionic. The hour-long soak passes too: `fh1-long-drive` stretched to 216,000 frames ran 4,011 simulated seconds in 63.6 minutes (ratio 1.05, frame median 16.8 ms, p99 62 ms) without a hang or a failure; the car is parked after the drive, so it covers the threads and timers rather than the physics. Open: save payload hashes (they differ between any two runs, Windows included, so they need a deterministic route first) |
| AP-0.6, AP-3.5 16 KiB pages | **Partial (emulator)** | On Android 15's 16 KB-page arm64 emulator (`google_apis_ps16k`, host page 0x4000) the libraries load, the guest arena reserves and maps, the three XEX modules load and the guest threads start; the log reads `physical heap at E0000000 offset 0x1000`. Every packaged library has 16 KiB-aligned load segments. Open: the route matrix, which needs the 7.2 GB of game data on a 16 KB device (it did not fit the emulator host's free disk), and the write-watch fault count |
| AP-1.1 to AP-1.4 | **Done** | NDK presets, SDK CMake for Android, `main_android.h` glue, `libmain.so` with `SDL_main`, ANativeWindow surface, activity without Gradle |
| AP-1.5 title screen | **Done (emulator)** | The FH1 executor draws the title screen through Vulkan on the emulator |
| AP-2.0 capability report | **Done** | `VULKAN_CAPABILITY_REPORT` log line, on by default on Android; the emulator's report is in [docs/android/](android/capability-emulator-apple-m4-pro.json); the reference device's goes beside it. The report ends with `missing`: each feature or format the renderer would use that the device lacks, with what it does instead or that it cannot run; the emulator lacks D24S8 (depth kept in D32S8), geometry shaders, sparse binding and multisampled storage images (unchecked by the renderer) |
| AP-2.1 dynamic rendering bug | **Done** | Requested once; the feature is linked from the device's own flag |
| AP-2.2 geometry shaders | **Done** | Not required by default on Android. With every fallback forced on NVIDIA, `fh1-opening-sync` crashed the driver: the SPIR-V rectangle-list loop produced an invalid OpPhi, now fixed; all 444 translated modules pass `spirv-val`, menu captures within 1.5 MAE |
| AP-3.1, AP-3.2 lifecycle | **Mostly done** | SDL app events reach a lifecycle listener in the UI thread before SDL blocks; the window drops and recreates its surface; GPU commands, audio and guest time pause (the vblank thread sleeps meanwhile), so a minute away reaches the title as no time at all. Fifteen background and foreground cycles with Vulkan on the emulator, the same process throughout; the whole process uses about 6 % of one core in the background. Found on the way: with the recorder thread (Vulkan's default), pausing suspended the recorder while resuming woke the decoder, which would have frozen the game after the first return; the decoder now parks itself on a condition variable. The on-screen controls lay out inside the safe area SDL reports (the emulator's cutout and bars: 142, 137, 78 and 84 pixels). Open: rotation between the two landscape sides on a device |
| AP-3.4 low memory | **Partial** | Every `onTrimMemory` and `onLowMemory` logs the resident size and, for ten seconds, drops textures unused for a second down to a 256 MB floor; in the background the paused GPU thread wakes to do it without blocking the UI thread. The kill test under pressure needs the reference device |
| AP-3.3 storage | **Done** | `game/base` and `state` in the app's external files folder, set by the activity |
| AP-3.6 fonts, crash reports, logs | **Done** | Roboto fallback; crash reports with library and offset; logs to logcat and `state/logs`; `pull-logs` |
| AP-4.2 on-screen pad | **Done (emulator)** | Stick, triggers, A/B/X/Y, bumpers, Back and Start drawn by the host UI and read as a synthetic pad on user 0; shown on a touch, hidden 20 s after; SDL's touch-made mouse events no longer reach the mouse-and-keyboard driver. The feel of the layout waits for a player (AP-4.4's human test) |
| AP-4.6 hide the pad with a gamepad | Open | The overlay still shows on a touch while a pad is connected |
| AP-4.3 touch in the host UI | **Done** | A tap focuses and activates the row under it; Android Back steps back and, with no menu up, opens SETTINGS |
| AP-4.4 keyboard-only features | **Done** | SETTINGS (reachable from the pause menu with a pad, or with Back on a touch screen) gains TRAINER and SAVE PHOTO beside ACHIEVEMENTS |
| AP-5 audio | Partial | Silent fallback when no output opens; the stream is tagged with the game role; it opens SDL's default output, which SDL3 moves to headphones or a Bluetooth output when one connects; it stops in the background (AP-3.1) but does not request audio focus. Latency: Android reports 6 channels for the tablet's stereo speakers, and the 6-channel stream missed the low latency path, about 130 ms behind (AudioFlinger); the device now opens in stereo with 10 ms callbacks and plays through an MMAP playback thread (a 20 ms buffer). Not yet measured end to end |
| AP-4.5 haptics | Partial | The title's rumble reaches pads through `SDL_RumbleGamepad`; feeling it needs a pad on the reference device; no phone vibration for the on-screen pad |
| AP-6.1 tooling | **Done** | `pinyon.py android doctor/build/package/install/push-data/run/stop/pull-logs` |
| AP-6.2 boundary | **Done** | Policy, launcher payload and `.gitignore` refuse Android binaries; tests |
| AP-6.4 provenance | **Done** | `pinyon_shift_build.json` as an APK asset, read through `PINYON_SHIFT_BUILD_MANIFEST` |
| AP-6.5 documentation | **Done** | [ANDROID.md](ANDROID.md) |
| AP-7.2 thread placement | Partial | Guest priorities map to nice values on Android (no `SCHED_FIFO` for apps). With `latency_critical_thread_placement`, the main guest thread and the GPU commands, recorder and vblank threads are pinned to the cores whose `cpu_capacity` is at least half the largest (on an 8 Gen 2, the prime and four big cores, not the three A510s) and raised above normal. Off by default: on the emulator, whose cores are alike so only the priority changed, `fh1-opening-sync` failed in two runs of two with it (once stalled, once the `0x38` stop) and passed without it. AP-7.0 decides on the device |
| AP-2.5 memory at 1x | **Done (clamp)** | The draw resolution scale is clamped to 1x on Android (`android_allow_resolution_scale` overrides) and SETTINGS offers 1X only; budget logging waits for AP-7.0. `vulkan_memory_budget_log_seconds` (30 s on Android) logs each heap against its budget, the texture cache and the resident size with their peaks; the emulator has no `VK_EXT_memory_budget`, and the opening drive peaked near 1.1 GB resident there |
| AP-2.6 pipeline cache | **Done (driver cache)** | A `VkPipelineCache` per title, vendor, device and driver, saved 30 s after new pipelines and at shutdown; reloads on the emulator and on the 8 Elite (9 MB). The SPIR-V pack half is AP-6.3 |
| AP-2.8 graphical glitches | Open (candidate fix) | Flickering shadows, lighting and reflections, and screen-wide tile artifacts, reported on the 8 Elite. Two candidates fixed on 2026-10-02 (ANDROID_60FPS_BACKLOG A60-0): the barrier after a resolve did not make its writes available to the texture loads and draws that read them (shadows and reflections are resolve-sourced textures), and 2_10_10_10 targets were hosted at 8 bits. Scripted captures cannot show flicker; whether these were the cause needs the maintainer to look |
| AP-6.3 SPIR-V pack on the device | Open (measured) | The 8 Elite keeps the driver cache, `.xsh` and `.fbo.vk.xpso`, but every start logs `No FH1 precompiled SPIR-V shader pack (4D5309C9.fh1-native-v3.vulkan.E66826E.08.1x1.pnsp)`, so each start translates every guest shader on the CPU again. Over about 25 starts on 2026-10-01: 7,666 pipeline creations (about 300 a start) and 22 frames not presented because an async pipeline was still a placeholder (about one a start). A pack would shorten loading and remove first-use hitches and some CPU heat at load; it would not change the race frame rate, which is GPU-bound. Next: produce the Vulkan pack for the device's feature hash (`prepare-fh1-shaders.ps1` has the Vulkan backend), ship or push it, then record start-to-title time, pipeline creations and placeholder frames with and without |
| AP-8.1 routes from the PC | **Done** | `pinyon.py android run --route FILE --seed DIR --wait` isolates the state, pushes the seed, runs and judges the session (captures, failures, simulation time) |
| AP-8.2 CI | **Done** | A CI job cross-compiles the runtime, the GPU plugin and the host tests for android-arm64 with the pinned NDK and no game files |
| AP-7.5 presets | Partial | SETTINGS on Android offers QUALITY 30 (was BATTERY 30; 4x MSAA and shadows, the guest vblank at 60 Hz, bilinear) and SMOOTH 60 (no MSAA or shadows; both single-pass with quarter-rate reflections since 2026-10-08, see the Odin backlog), both 1x on Vulkan with the recorder thread, in place of the desktop's 120 and 2x presets; chosen by tapping on the emulator. Which holds its frame time after twenty minutes, and so the default, waits for the reference device |
| Reference device | **In use** | nubia NP05J (RedMagic tablet): Snapdragon 8 Elite (SM8750, Adreno 830, driver Vulkan 1.3.284), 6 x 3.53 GHz + 2 x 4.32 GHz Oryon cores, 11 GB, Android 15, 4 KiB pages; [capability report](android/capability-sm8750-adreno-830.json): geometry shaders, sparse binding, BC, D24S8 all present, only `shaderStorageImageMultisample` missing. An AYN Thor (Snapdragon 8 Gen 2) is also reachable |
| AP-2.7 on the 8 Elite | Partial | `fh1-opening-sync` passes with Vulkan (ratio 1.04-1.10). Found on the way: the Adreno 830 driver returns from `vkWaitForFences` at once for a `UINT64_MAX` timeout, which stopped the game at its first frame (black screen); waits are now a second at a time. The rest of the matrix is next |
| AP-7.0 first measurement | Partial | The opening drive at 1x: frame median 75 ms (13 fps), GPU 61 ms, recorder 48 ms for 1,830 draws, submission 28 ms; the FH1 executor opens about 268 renderings a frame, each a load and store of its attachments on a tiler, so AP-7.4 comes first. The CPU reaches 100-105 C and throttles to 2.4/2.84 GHz: the guest and GPU threads spin. RedMagic caps an app it does not know as a game at 960/1,017 MHz: the app now declares Android's PERFORMANCE and BATTERY game modes, and on RedMagic it has to be added to Game Space and started from there once |
| AP-7.0 the race on the 8 Elite | Partial (measured) | `fh1-race-start-wait` passes from the appdata seed: frame median 34 ms (29 fps) at about 4,760 draws in the race, 25 ms on the grid. Fixed on the way: a guest allocation read `/proc/self/maps` (12,000 lines) in `AllocFixed`, the fault handler, the treasure map and the cheats; the commands thread built and waited for pipelines; the presenter rebuilt its swapchain pipeline and waited for the GPU every present. Faster guest allocation exposed a title race that hung or crashed 7 runs of 7 about 30 s in: FH1's render job producer gives up after 1000 `NtYieldExecution`s, which return at once on the host, so a slow GPU frame let it queue hundreds of jobs, the job thread filled more than the render thread's 12 slots, and the render thread read a slot early or waited on a lost signal; a hook at 0x823F4F60 now waits in host time. Turnip (Gen8 V37) runs but is no faster than the stock driver. In the race the GPU limits: the submission thread spends 44 % of its time in `vkQueuePresentKHR`, where Android's BufferQueue waits for the previous frame's GPU work, and no thread is busy more than 61 % of a core. The GPU work to cut is about 265 renderings a frame (each a GMEM load and store on a tiler) and 86 resolve reloads moving 66 MB a frame, so AP-7.4 and PB-1.2 come next. By the executor's GPU timer the race spends 6.6-14.3 ms a frame on EDRAM ownership transfers (mostly one depth area alternating between 4x and 1x), 2-2.7 on resolves, 2.5-3.7 on texture reloads; transfers into depth now write depth and stencil in one pass with `VK_EXT_shader_stencil_export` instead of nine, read straight from the source rather than through a compute pass and a words buffer, which cut them to 3.5-5.2 ms and the race median to 25 ms (40 fps). Giving tiles back to an unchanged surface without a transfer was tried and dropped: the 1x depth is written between the two directions. Shrinking each rendering's area to what its draws and clears cover was tried and dropped too: it kept 20 % of the area across 940,000 renderings and changed no frame or GPU time, so the Adreno driver already spends nothing on untouched tiles. Resolve aliasing (PB-1.2) was measured and tried: skipping every repeat reload of a resolve-sourced texture (wrong output, an upper bound) took the race from 25.0 to 22.4 ms and the lighter scenes from 22.5 to 16.8 ms. Most reloads are 8_8_8_8 and 2_10_10_10 textures from 1x color resolves (a bloom chain from 1280x720 down to 64x32), plus shadow maps and a depth read; none is a plain copy (swapped red and blue, or float to unorm with an exponent bias). Drawing each resolve straight into the cached texture it covers whole (a fragment pass with the resolve's encoding) cut reloads from about 74 to 12 a frame but added about 31 fill passes, each about twice a reload's GPU time, and 50 renderings, so the frame stayed at 25 ms and it was not kept |
| AP-7.3 sustained frame rate | Partial (measured) | Twenty minutes of `fh1-long-drive` stretched to 48,000 frames on the 8 Elite with SMOOTH 60's settings (no MSAA, 60 fps cap): about 48 fps for the first four minutes with the CPU and GPU near 100 C, then the big cores capped at 2.4 GHz and about 39-40 fps sustained with peaks near 48; CPU and GPU settled near 78 and 75 C, skin 41 C, battery 39 C. Without MSAA the race's busiest part takes 17 ms cold (the 60 fps cap); with the game's 4x MSAA 25 ms, so BATTERY 30 keeps MSAA and SMOOTH 60 drops it (the MSAA row sets it alone). The same twenty minutes with BATTERY 30's settings (4x MSAA, 30 fps cap): a steady 29.5 fps for the first eight minutes, then the big cores capped at 2.4 GHz and about 27.5 fps sustained, back to 29.5 in lighter stretches; CPU and GPU settled near 76 and 73 C, skin 41 C, battery 40 C. So 4x MSAA does not hold 30 once the tablet is warm; MSAA OFF at the 30 fps cap leaves the headroom to hold it. On 2026-10-02, starting from a 36 C skin (the tablet on AC power could not cool further), the final build at the new SMOOTH 60 settings held 60 fps for a minute, 37-39 fps until the skin reached 44.5 C at about 14 minutes, then 26-28 fps; the details and why build-to-build soaks are not comparable are in [ANDROID_60FPS_BACKLOG.md](ANDROID_60FPS_BACKLOG.md) |
| AP-2.4 compressed textures | Partial (measured) | `vulkan_force_bc_decode` takes the no-BC path on any GPU. On `fh1-free-roam` (RTX 4080, Vulkan) the decoded textures need 261 MB where BC needs 105 MB (2.5 times, not the 4 to 8 guessed), device memory 1,314 MB instead of 1,040, under the 384 MB soft limit; the captures match the BC run within the run-to-run noise (MAE 1.8 to 4.0 against 1.0 to 3.0 between two BC runs). On `fh1-race-sync` the decoded textures need 437 MB where BC needs 148 MB (2.95 times; device memory 1,350 MB instead of 1,102), over the soft limit, so the race churns textures without BC; its captures match too apart from motion. A transcoder is therefore a Mali and PowerVR matter (AP-8.3) unless AP-2.0's report shows Adreno without BC |
| AP-2.3, AP-2.7, AP-3.4 (kill test), AP-4.1, AP-6.3, AP-7.0, AP-7.1, AP-7.3, AP-7.4, AP-7.6, AP-8.3 | Open | Need the reference device (formats, BC, memory and thermals, controllers, touch) or a second GPU vendor |

### Findings from the emulator runs

- **An attract-sequence resolve no backend packs.** Left idle on the title
  screen, the title resolves an RGBA16 float target (`c7`) into
  `k_16_16_16_16` (`t26`); the FH1 executor's resolve shader packs only
  8888, 2_10_10_10, 32_FLOAT and 16_16_16_16_FLOAT, so the copy is skipped
  (`resolve_dest_format`, now logged once per kind). The D3D12 path shares
  the shader; no Windows route idles long enough to reach it.
- **Thumbnail waits are timing-sensitive.** The scripted pad shows only the
  latest due step, so a press whose release falls due in the same output
  frame is lost; the Windows routes are calibrated with those losses (making
  every press visible sends `fh1-race-sync` down a menu path where the
  title reads guest address `0x38` and stops). Routes can therefore fail at
  their first file wait on a device whose frames arrive in different bursts;
  re-timing the routes is a separate task.
- **Gameplay renders on the emulator, with one texture fault.** Through
  Vulkan on the emulator's GPU (gfxstream over MoltenVK on an Apple M4; its
  [capability report](android/capability-emulator-apple-m4-pro.json): no
  geometry shaders, no sparse binding, no multisampled storage images, no
  D24S8, one 2 GB heap) the opening drive renders with its HUD, minimap and
  speedometer at about 6 fps, but the car's paint shows a fine grid and its
  stripes garbled texels where Windows draws them clean, and road markings
  are jagged. Not the no-geometry-shader paths: forced on NVIDIA, the same
  frame is clean. Candidates: the missing `shaderStorageImageMultisample`, or
  a tiling or format path the translation layer handles differently. To check
  on the Adreno reference device before anything else in AP-2.3.
- **The `0x38` stop was a host query.** The treasure map and the
  trainer's collectible markers ask the title, from the frame hook, whether
  free roam's collectibles are live (sub_828BC9D8), which reads the world's
  game mode through sub_824878D0 without a check; while the title loads or
  leaves free roam that object is null, so the query read guest `0x38` and
  stopped the game whenever a check landed there (menu timing on the
  emulator, audio timing on the 8 Elite, at the same frame every run). The
  guest link register pointed at the frame loop because host guest calls
  run on a nested context; unhandled faults now log the host library,
  offset and symbol, which named the getter. Both queries now wait for the
  game mode object.
- **Files pushed with adb are closed to the app on Android 15.** What `adb push`
  creates in the app's folder belongs to the shell user; Android 16 lets the
  app read and write it, Android 15 does not even let it list it, so the
  game exited at once (creating `state/logs` failed, silently) and then
  could not see `game/base`. `push-data` and `run --seed` now open what the
  shell owns to the app (the app's folder stays closed to other apps), and
  the failure is logged. Handhelds on Android 13 to 15 would have hit it.
- **No socket permission, no single player.** The title opens system-link
  sockets at the single-player menu and dereferences null when `socket()`
  fails, so the package asks for `INTERNET`.

## Goal

A player who owns the supported disc builds Pinyon Shift on their PC, as
today, and additionally produces an Android package for their own ARM64
phone or tablet, sideloads it, copies their extracted game files to the
device, and plays *Forza Horizon* with a controller or on-screen controls at
the console's 1280x720 and at least the console's 30 fps, with saves,
settings, mods and the in-game host UI working as on Windows.

"Android port" is done when all of the following hold:

1. **Same legal model.** Nothing derived from the disc leaves the player's
   machines: the APK is built locally from their own ISO and is never
   published, and the extracted game data travels only PC to device
   ([legal](LEGAL.md)).
2. **Same code.** One generated translation, one SDK runtime, one FH1
   executor core and one Vulkan backend serve Windows, Linux, macOS and
   Android; Android differences live in the platform layer and in device
   capability fallbacks, not in forks.
3. **Correct.** The scripted routes that gate Windows changes (opening,
   free roam, race, buy-car, pause and settings) pass on the reference
   device with the same save payload hashes and simulation-time ratios as on
   Windows.
4. **Playable.** 1x internal resolution, output scaled to the display, a
   steady 30 fps in the race on the reference device without thermal
   collapse over a 20-minute session, audio in sync, controller and touch
   input, and clean pause, resume and surface loss.
5. **Operable.** The PC-side tooling produces, signs and installs the
   package, pushes the game data, collects logs and crash reports from the
   device, and runs the render-test routes on it.

### Non-goals

- Building on the device. The translation is 263 generated files, 306 MB of
  C++, built in 20-60 minutes with about 25 GB of disk on a desktop
  (`.local/generated/default`, `docs/BUILDING.md:5`); no phone compiles it.
- Internal scales above 1x (see AP-2.5: the Vulkan scaled-resolve buffer is
  `512 MB x scale^2` and the surfaces 2 GB at 2x).
- Publishing an APK, a Play Store listing, or an emulator-style "pick your
  game" app. One package, one title, built by its owner.
- A Metal or OpenGL ES backend. Vulkan 1.3-class drivers are the floor.
- x86-64 Android (Chromebooks, emulators): nothing forbids it, nothing
  schedules it.
- Rebuilding the launcher in Java or Kotlin. The PC remains the build and
  install host; the activity on the device is SDL's.

## How this backlog is organised

- **Slices** `AP-n` end with something a tester or player can run; rows are
  `AP-n.m`. Sizes are for one engineer (S <= 1 week, M 1-3 weeks, L 1-2
  months, XL > 2 months), estimated from the code, not committed.
- **Gates** reuse the rules in [development findings](DEVELOPMENT.md): the
  same seed and route for control (Windows) and candidate (device), save
  payload hash and `expect-simulation-time` where guest timing or numerics
  change, and captures compared against the Windows run of the same route.
  Never the AppData save; seeds from `tools/create-render-seed.py`
  ([AGENTS.md](../AGENTS.md)).
- **Trains.** `android-alpha`: boots and renders for developers (AP-0 to
  AP-2); `android-preview`: playable on the reference device with input,
  audio and lifecycle (AP-3 to AP-7); `android-1.x`: qualified on more
  than one GPU vendor and run from the tooling (AP-8). Trains can be re-cut;
  the dependency graph in the slice map is what matters.
- **Cross-references, not copies.** Rows that exist in the native port or
  performance backlog are referenced by ID (NP-12.x, NP-14.x, PB-x.y); their
  evidence stays there.

## Where the code stands

| Area | Finding | Android readiness | Evidence |
| --- | --- | --- | --- |
| Generated code | Clang-dialect C++ with `simde_mm_*` intrinsics (291 uses in one 38,363-line unit, led by `load_si128`, `store_si128`, `load_ps`, `shuffle_epi8`), `__builtin_bswap*` loads and stores on `volatile` pointers, `__attribute__((alias))` thunks off Apple, zero SEH scopes. The 0xE0 heap offset is read at run time on Linux and Android (NP-14.3). `std::fma` sites lower to one instruction on AArch64 without any baseline flag. | Portable in principle; **never compiled or run for AArch64** | `sdk/resources/templates/codegen/pch_h.inja:66-85, 140-158`; `.local/generated/default/pinyon_shift_recomp.254.cpp`; `cmake/PinyonShiftRexGlue.cmake:66-100` (x86-only baseline check) |
| Memory ordering | `sync`, `lwsync` and `eieio` are emitted as nothing with the comment that x86 has strong ordering; `lwarx` is a plain load; guest accesses are `volatile`, which orders nothing across addresses on AArch64. Every guest spinlock, fence poll and cross-thread flag relies on x86 TSO today. | **Correctness blocker on ARM64** | `sdk/src/codegen/builders/system.cpp:33-49`; PB-3.8 names the same `volatile` dependence |
| SIMD and FP state | `rex/ppc/intrinsics.h` includes simde SSE to AVX2 with an `arm_neon.h` branch; FPCR and FPSR replace MXCSR on ARM64; `vmsum3/4fp128` are scalar-double helpers (PB-3.7) and so arch-neutral. simde emulates `shuffle_epi8` (42,124 sites) with `tbl`, fine; lane-order, denormal and NaN parity are untested. | Compiles; parity unproven | `sdk/include/rex/ppc/intrinsics.h:22-28, 124-166`; `sdk/include/rex/platform/fpscr.h:53-83`; `sdk/src/core/memory.cpp:46` |
| Guest address space | One shared-memory object of `0x120000000` bytes (4.5 GB) backs a 4 GB virtual view and the 512 MB physical views; POSIX maps views with `MAP_FIXED` and no prior reservation (only macOS reserves first); the base is probed at powers of two. On Android the file-mapping path calls `ASharedMemory_create` through a pointer that `AndroidInitialize` sets, which nothing calls, and falls back to `/dev/ashmem`, blocked for apps since API 29. | Needs `memfd_create` and a reserve-then-fix mapping | `sdk/src/system/xmemory.cpp:139-151, 166-172, 320-360`; `sdk/src/core/memory_posix.cpp:87-110, 434-456, 506-513` |
| Page size and 16 KiB kernels | `rex_physical_host_offset_e0` is set from the allocation granularity at `PhysicalHeap::Initialize`; `BaseHeap` reconciles 4 KiB guest pages that share a larger host page; `page_size()` is `getpagesize()`. Built, never run on a large-page kernel (NP-14.3). | Designed for; untested | `sdk/src/system/xmemory.cpp:1918-1945, 2149-2192`; `sdk/include/rex/system/xmemory.h:30-60`; `sdk/src/core/memory_posix.cpp:114-118` |
| Write watches and faults | `sigaction` for SIGILL, SIGSEGV and SIGBUS with ARM64 register capture, ESR decoding (with a note that `esr_context` is missing on API 26 headers) and an AArch64 load/store decoder for MMIO. No `sigaltstack`; `QueryProtect` parses `/proc/self/maps` with an `ifstream` inside the fault path. | Exists; hardening needed | `sdk/src/core/exception_handler_posix.cpp:112-250, 424-438`; `sdk/src/system/mmio_handler.cpp:267-361` |
| Threads, fibers, waits | pthreads with Android branches (thread names through `dlsym`'d `pthread_getname_np`, `sched_setaffinity` by tid, no `pthread_cancel`); priorities through `SCHED_FIFO` (EPERM warns, EINVAL asserts); affinities map guest CPU i to host core i; multi-object waits poll at 1 ms. Fibers switch with the SDK's own AArch64 assembly (NP-14.2), harness-tested on x86-64 only. | Mostly there; scheduler policy wrong for big.LITTLE | `sdk/src/core/threading_posix.cpp:45-110, 345, 676-690, 826-875`; `sdk/src/core/fiber_posix.cpp:43-200`; `sdk/include/rex/thread/fiber.h:17-18` |
| Exceptions | Guest SEH on POSIX throws C++ exceptions from a signal handler without `-fnon-call-exceptions`, and its SIGSEGV handler is replaced when `MMIOHandler` installs its own. FH1's translation has no SEH scopes, so this is latent. | Latent; keep an eye on it | `sdk/src/core/seh_posix.cpp:34-117`; `sdk/src/system/xmemory.cpp:231` |
| Android glue in the SDK | Dead Xenia-era code: `threading_posix.cpp` includes a `rex/main_android.h` that does not exist; `GetAndroidApiLevel`, `InitializeAndroidSystemForApplicationContext`, `IsAndroidContentUri` and `OpenAndroidContentFileDescriptor` are declared and never defined; `vulkan_presenter.cpp` includes a missing `surface_android.h` while `Surface` already has `kTypeIndex_AndroidNativeWindow` and the presenter creates `VkAndroidSurfaceCreateInfoKHR`. | **Does not compile** | `sdk/src/core/threading_posix.cpp:48, 74`; `sdk/src/core/memory_posix.cpp:94`; `sdk/include/rex/filesystem.h:129-134`; `sdk/include/rex/system.h:22-24`; `sdk/src/ui/vulkan/vulkan_presenter.cpp:36, 426-428, 799-808`; `sdk/include/rex/ui/surface.h:30-42` |
| Build system | `platform.h` knows `REX_PLATFORM_ANDROID`, but CMake has no Android branch: an NDK build takes the `UNIX AND NOT APPLE` path, names itself `linux-arm64`, requires `x11-xcb` and `wayland-client` through pkg-config, compiles `surface_gnulinux.cpp`, links `pthread rt dl`, and forces SDL's X11, Wayland, ALSA, Pulse and PipeWire on. No Android preset in either `CMakePresets.json`; the project presets pass `-msse4.1` to every target; `build-preview.ps1` and `launch-preview.ps1` hard-code `win-amd64`. The host-side generator lookup already separates build host from target. | Blocked at configure | `sdk/include/rex/platform.h:35-37`; `sdk/CMakeLists.txt:161-169`; `sdk/src/ui/CMakeLists.txt:75-79, 154-168`; `sdk/src/core/CMakeLists.txt:105-106`; `sdk/thirdparty/CMakeLists.txt:293-302`; `CMakePresets.json:9-51`; `cmake/PinyonShiftRexGlue.cmake:110-126` |
| Entry point and modules | `main` on POSIX, `wWinMain` on Windows; Android's SDL needs `SDL_main` in a shared library. The game is an executable; the GPU plugin is `librexgpu-fh1.so` loaded from the executable's folder, which on Android resolves to `app_process64`; the two facade modules are shared libraries next to it. | Needs `libmain.so` and `nativeLibraryDir` lookup | `sdk/src/ui/windowed_app_main_sdl.cpp:107-131`; `sdk/src/system/gpu_plugin_loader.cpp:30-58`; `sdk/src/core/filesystem_posix.cpp:72-104`; `CMakeLists.txt:61-100`; `.local/generated/default/dll_targets.cmake` |
| Vulkan device requirements | No minimum API version is enforced, but the FH1 executor refuses to run without `dynamicRendering`, and `VK_KHR_dynamic_rendering` is requested twice into one map, so on a 1.1 or 1.2 driver that only exposes the extension the feature is never enabled. Hard: `independentBlend`, `fragmentStoresAndAtomics`, `vertexPipelineStoresAndAtomics`; `geometryShader` and `fillModeNonSolid` are required by default but have cvars and a vertex-shader expansion fallback for points, rectangles and quads. Render-target formats used without a query: RGBA16 SNORM/SFLOAT and UNORM, R16G16_UINT, RGBA16_UINT, R32_UINT and R32G32_UINT with multisampled integer sampling, D32_SFLOAT_S8_UINT. Sample-rate shading used by 26 executor modules without a check. No vendor branches. Not used: 64-bit integers or atomics, descriptor indexing, timeline semaphores. | Mostly satisfiable on 2023+ flagships (guess); several unchecked assumptions | `sdk/src/ui/vulkan/vulkan_device.cpp:100-145, 203, 237, 359-361, 685-689`; `sdk/src/graphics/vulkan/fh1_native_executor.cpp:298-301`; `sdk/src/graphics/vulkan/command_processor.cpp:985-996, 1943-1945`; `sdk/src/graphics/vulkan/primitive_processor.cpp:24-68`; `sdk/src/graphics/vulkan/pipeline_cache.cpp:1561-1598`; `sdk/src/graphics/vulkan/render_target_cache.cpp:300-415, 1642-1648` |
| Vulkan memory model | Shared memory is a 512 MB buffer, sparse when `sparseResidencyBuffer` holds and otherwise one dedicated 512 MB allocation; the scaled-resolve buffer is `kBufferSize x scale^2` on the same rule; 1x surfaces take 522-562 MB and textures peak at 265 MB under a 384 MB soft limit; 3x needs 4,448 MB of surfaces. No `VK_EXT_memory_budget`, no `VkPipelineCache` (387 pipelines recompiled at every start, 21 ms on NVIDIA). | 1x fits a 12 GB phone (guess); upscaling does not | `sdk/src/graphics/vulkan/shared_memory.cpp:50-110`; `sdk/src/graphics/vulkan/texture_cache.cpp:2157-2216`; `sdk/src/graphics/vulkan/pipeline_cache.cpp:3629`; [baselines](native-renderer/NATIVE_PERFORMANCE_BASELINES.md); PB-2.13 |
| Compressed textures | BC1, BC2, BC3, BC4 and BC5 are optional per format: when the format is unsupported the loader decompresses on the GPU to RGBA8, RG8 or R8 (4 to 8 times the memory). No ETC2 or ASTC path (`TODO` at the fallback). | Works; memory and bandwidth cost on Mali and PowerVR | `sdk/src/graphics/vulkan/texture_cache.cpp:60-65, 199-210, 321-370, 2539-2594` |
| Tiled-GPU behaviour | A race frame has about 300 renderings and 600 barriers (NP-12.4, PB-1.5), every attachment loads and stores (`LOAD/STORE` always, clears by `vkCmdClearAttachments` inside their own rendering), transfers and resolves run as full-image compute and draw passes. On a desktop GPU the barriers measured within noise (PB-1.5); on a tile-based GPU each rendering break is a tile store and reload. | Unmeasured; the likely GPU cost driver | PB-1.5, PB-1.6; `sdk/src/graphics/vulkan/fh1_native_executor.cpp:1558-1631` |
| Shader pipeline | Vulkan translates at run time with the vendored glslang builder and loads an optional pack keyed on the translator version, a device-feature hash, flags and scale; the executor's own 66 modules are prebuilt SPIR-V headers. The pack's feature hash omits `quad_operations_fragment`. No external compiler is needed on the device. | Works on device as-is; pack is an optimisation | [pack contract](native-renderer/SHADER_PACK_FORMAT.md); NP-12.5, NP-12.6; `sdk/src/graphics/vulkan/pipeline_cache.cpp:1258-1289` |
| Presenter and surface | Android surface creation exists; swapchain is R8G8B8A8 on Android; `OUT_OF_DATE` and `SURFACE_LOST` reconnect; only `IDENTITY` and `INHERIT` pre-transforms are accepted (no pre-rotation); `WindowSDL::CreateSurfaceImpl` has Win32, Wayland and X11 branches only. | Needs the `ANativeWindow` branch and rotation | `sdk/src/ui/vulkan/vulkan_presenter.cpp:1198-1205, 1232-1233, 1592-1593, 2265-2266`; `sdk/src/ui/window_sdl.cpp:410-457` |
| Lifecycle | `SDLWindowedAppContext::ProcessEvent` handles quit, keys, text, mouse and drop; nothing handles `DID_ENTER_BACKGROUND`, `WILL_ENTER_FOREGROUND`, `TERMINATING` or `LOW_MEMORY`; `GraphicsSystem::Pause/Resume` and `AudioSystem::Pause/Resume` exist and are never called; the surface is only (re)attached at window open and close. | Missing | `sdk/src/ui/windowed_app_context_sdl.cpp:126-180`; `sdk/src/graphics/graphics_system.cpp:501-508`; `sdk/src/audio/audio_system.cpp:370-391` |
| Audio | SDL3 is the only backend (plus `nop`); 48 kHz six-channel XMA through vendored FFmpeg with AArch64 NEON, downmixed to stereo; no WASAPI or platform code. SDL3 3.5.0 carries AAudio and OpenSL ES on Android. | Portable; latency untested | `sdk/src/audio/CMakeLists.txt:12-16, 38-41`; `sdk/thirdparty/CMakeLists.txt:245-304` |
| Input | SDL gamepads everywhere, XInput on Windows only, mouse-and-keyboard mode, `nop`; the SDL event watch stops before finger events and the context has no `SDL_EVENT_FINGER_*` case, though `ImGuiDrawer::OnTouchEvent` exists. The host UI takes pad, keyboard and mouse. Several player features are keyboard-only (F6 settings, F8 photo, F10 trainer, F11 fullscreen; F3, F4, F7 and backtick in the SDK); the pause menu's SETTINGS row is the one pad route into settings. | Controllers work; touch is new | `sdk/src/input/CMakeLists.txt:33-37`; `sdk/src/input/sdl/sdl_input_driver.cpp:77`; `sdk/src/ui/imgui_drawer.cpp:574-614`; `src/ui/hostui/host_ui.h:95-101`; `src/fh1_render_test.cpp:844` (`ScriptedInputDriver`, a virtual pad template) |
| Host UI and fonts | 1280x720 layout fitted into the painted output with a 90 % safe area (NP-1.3); fonts are looked up at Windows, macOS and Linux paths, the SDK font as fallback. No display-cutout handling. | Scales; needs touch and cutouts | `src/ui/host_style.cpp:6-19`; `src/ui/hostui/host_ui.cpp` |
| Host project Windows remnants | `pinyon_shift_app.cpp:385` calls `ExitProcess` unguarded; `crash_reporter_posix.cpp` uses `execinfo` (bionic API 33+); the live profile's `VirtualQuery` scan is a no-op off Windows; `cpu_baseline_guard.cpp` compiles to nothing off x86-64. 91 midasm hooks in `main-xex.toml` take guest registers, so they are architecture-neutral. | S to fix | `src/pinyon_shift_app.cpp:385`; `src/crash_reporter_posix.cpp`; `src/cpu_baseline_guard.cpp:5`; `config/rexglue/analysis/main-xex.toml` |
| Storage and paths | State root from `PINYON_SHIFT_STATE_ROOT`, game root from `PINYON_SHIFT_GAME_ROOT` (both set by `tools/pinyon.py launch`); `GetUserFolder` needs `XDG_DATA_HOME` or `HOME`; `HostPathDevice` resolves case-insensitively and walks the 2,400-file tree at start. Extracted game: 7.2 GB from an 8.74 GB ISO. | Works with app-private storage | `tools/pinyon.py:121-136`; `sdk/src/core/filesystem_posix.cpp:106-117`; `config/supported-dumps.json` |
| Tooling | Setup, build, shader preparation and launch are PowerShell plus a 1,315-line WPF launcher; `tools/pinyon.py` (194 lines) is the cross-platform launcher that already picks `out/build/<os>-<arch>-<config>`; render tests always spawn PowerShell. SDK CI builds `linux-arm64` natively on `ubuntu-24.04-arm` with clang 20; nothing builds Android. | PC-side orchestration exists to extend | `tools/build-preview.ps1:27, 32`; `tools/run-fh1-render-test.py:587-621`; `sdk/.github/workflows/_build-platform.yaml:30-83` |
| Boundary tooling | `config/repository-policy.json` forbids `.exe`, `.dll`, `.pnsp`, `.iso`, `.xex`, `MZ` and `XEX2` magic and `generated` paths; it does not know `.so`, `.apk`, `.aab` or ELF magic. | S to extend | `config/repository-policy.json`; `tools/check-repository-boundary.ps1:25-89`; `tools/package-launcher.ps1:120-122` |
| Null renderer | None: `rex_gpu_create` accepts `any`, `d3d12` or `vulkan` and a failed plugin load is fatal. The Rayman Origins recomp's Android work carried a null GPU plugin and a "leave the window to the activity" patch, both GPL-3.0 and not reusable as code. | Needed for the first vertical slice | `sdk/src/graphics/plugin_main.cpp:28-52`; `sdk/src/ui/rex_app.cpp:53-56`; [Rayman research](native-renderer/archive/RAYMAN_NATIVE_RENDERER_RESEARCH_2026-09-25.md) |

## Prerequisites from other backlogs

| Prerequisite | Why Android needs it | State (2026-09-30) |
| --- | --- | --- |
| NP-12.1, NP-12.2 | The Linux presets, the POSIX host sources and the crash reporter are the first time the project compiles off Windows; Android inherits every fix. | Written, unbuilt (needs the Linux toolchain) |
| NP-12.7 | Setup, build and launch in Python or shell; the Android flow is a target added to that core, not to the WPF launcher. | Launcher half done |
| NP-12.4, NP-12.6, NP-15.2 to NP-15.4 | The Vulkan executor, its pack and its higher-scale and texture fast paths are the only renderer Android can use. | Executor done at 1x to 4x; fast paths pending |
| NP-13.1, NP-13.2 | The first ARM64 build and guest-correctness pass; everything AP-1 finds on Android also holds on Apple Silicon, so whichever port runs first pays once. | Not started (needs a Mac) |
| NP-14.2, NP-14.3 | The ucontext-free fibers and the run-time 0xE0 offset. | Built, not run on AArch64 or a 16 KiB kernel |
| PB-1.5, PB-1.6, PB-2.13 | Fewer renderings and barriers, clears as `loadOp`, a persisted `VkPipelineCache`: measured as noise or unnecessary on NVIDIA, they are the first levers on a tiled GPU. | Deferred on desktop; revived here as AP-7 rows |
| PB-3 (locality, offset-free accesses, fused `vmaddfp`) | Guest CPU is 2 to 3 times more expensive per thread on a phone core (guess); items deferred on the 5800X become the only CPU levers. | Deferred; profiled flat on desktop |
| PB-4.2 | The host-measured, capped simulation delta keeps the game correct when a frame runs long under thermal throttling. | Done, opt-in |

## Slice map

| ID | Slice | Outcome | Size | Depends on | Train |
| --- | --- | --- | --- | --- | --- |
| AP-0 | ARM64 guest correctness on Linux | The recompiled title boots to the title screen and completes the opening route on an AArch64 Linux machine (16 KiB pages included) with a null renderer, matching Windows save hashes | M-L | NP-12.1, NP-12.2 | android-alpha |
| AP-1 | Android build and first frame | The SDK and the game build with the NDK into an SDL activity; the Vulkan clear and the title screen present on the reference device | L | AP-0, NP-12.7 | android-alpha |
| AP-2 | Mobile Vulkan | The FH1 executor runs the route matrix at 1x with zero skips on the reference GPU; capability fallbacks for formats, geometry shaders, BC textures and memory | L | AP-1, NP-15.3 | android-alpha |
| AP-3 | Lifecycle and storage | Pause, resume, surface loss, rotation, low memory and app-private storage behave like a native Android game | M | AP-1 | android-preview |
| AP-4 | Input for a phone | Controllers through SDL, an on-screen pad, touch in the host UI, every keyboard-only feature reachable by pad or touch | M | AP-1, NP-6 | android-preview |
| AP-5 | Audio | AAudio through SDL3 with acceptable latency, pause and resume, Bluetooth output | S | AP-3 | android-preview |
| AP-6 | Cross-build and sideload workflow | From the PC: codegen, NDK cross-compile, sign, install, push game data, pull logs; nothing derived distributed | M | AP-1, NP-12.7, NP-D | android-preview |
| AP-7 | Performance and thermals | 30 fps in the race at 1x on the reference device for 20 minutes; measured budget per stage | L (open-ended) | AP-2, AP-3, PB-1.5, PB-1.6, PB-3 | android-preview |
| AP-8 | Qualification and tooling | Routes run on the device from the PC; a second GPU vendor; CI builds the Android SDK targets without game code | M, ongoing | AP-6 | android-1.x |

Total: comfortably **XL** (NP-14's size), and the honest range is six months to a
year of one engineer's time with the hardware in hand, because AP-7 is
open-ended until AP-7.0 measures the device.

## Working order

**First vertical slice: AP-0.** The riskiest assumption in the whole port is
not Android, it is AArch64: the generated code has never run on anything
but x86-64, and the memory-ordering gap in the codegen (`sync`, `lwsync`,
`eieio` and `lwarx` lowered as nothing or as plain loads,
`sdk/src/codegen/builders/system.cpp:33-49`) is the kind of bug that shows
up as a rare hang in the race rather than a failed boot. Prove the CPU
side on an ARM64 Linux machine before touching the NDK: the SDK already
builds `linux-arm64` in CI, the Linux presets of NP-12.1 exist, and a
Raspberry Pi 5 running a 16 KiB-page kernel is both the cheapest ARM64
Linux box and the only easy way to run NP-14.3 for real. The GPU is
irrelevant to this slice, which is why AP-0.1 adds a null GPU plugin first
(it also gives NP-12 and NP-X a renderer-free boot for CI).

Then, in order:

1. **AP-0** entire: the null plugin, the ARM64 memory-ordering fix, the
   `linux-arm64` game build, the opening and free-roam routes with their
   save hashes and simulation-time gates equal to Windows.
2. **AP-1.1 to AP-1.4** (CMake, glue, activity, surface) so the device
   presents a cleared frame, then **AP-1.5** (title screen on the device).
3. **AP-2.0** (device capability report) before any renderer work, then
   AP-2.1 to AP-2.6 in the order the report dictates.
4. **AP-7.0** (the first measurement) as soon as the race route runs, so
   AP-3 to AP-6 are planned against the real budget rather than this
   document's guesses.
5. **AP-3, AP-4, AP-5** interleaved with **AP-7**; AP-6 last among them,
   because its shape depends on what the device needs (packs or not,
   how data gets there).
6. **AP-8** continuously once AP-6 exists.

## Needs a person or hardware

| Item | What is left | Needs |
| --- | --- | --- |
| AP-0 | Building and running the game on AArch64 Linux; the 16 KiB-kernel check | An ARM64 Linux machine with 16 GB or more of RAM (a Raspberry Pi 5 with 16 GB, or a Snapdragon X or Apple Silicon machine running Linux); a 16 KiB-page kernel on it |
| AP-1 | The NDK build, the activity and the first frame | Android Studio or the command-line SDK with NDK r27 or newer, JDK 17, and a reference device on Android 14 or 15 with a Vulkan 1.3 driver (a Snapdragon 8 Gen 2 or 8 Gen 3 phone is the working assumption; see AP-2.0) |
| AP-2.0, AP-8.3 | Capability reports and route runs on a second and third GPU vendor | A Mali (Dimensity 9300, Tensor G4) or Xclipse (Exynos 2400) device; a PowerVR device is optional |
| AP-3.5 | The 16 KiB-page run on Android itself | A device that boots a 16 KiB kernel (Pixel 8 or later with the developer option, or an Android 15 device shipping one) |
| AP-4.4 | Judging the on-screen controls | A player with the device; the route runner cannot judge feel |
| AP-7 | The thermal and sustained-performance runs, and the final playability call | The maintainer with the reference device and a power meter or `dumpsys` thermal logs |
| Legal decision | Whether an APK that holds the generated translation is a "locally linked preview executable" under [LEGAL.md](LEGAL.md) (the natural reading) and what the tooling must refuse to do with it (share, back up to a cloud, install on a second user's device) | The maintainer |

## AP-0 ARM64 guest correctness on Linux

**Why first.** Every later slice assumes the recompiled title is correct on
AArch64. Nothing in the repository has tested it: the fiber harness ran on
x86-64 under WSL (NP-14.2), the 16 KiB offset was never exercised
(NP-14.3), and simde's NEON lowering of 91 distinct intrinsics has no parity
test against the x86 build. This slice needs no GPU and no Android.

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| AP-0.1 | **Null GPU plugin.** A `rexgpu-null` (or a `null` backend inside `rexgpu-fh1`) that consumes the ring buffer, performs the CPU-visible packets the title waits on (`EVENT_WRITE_SHD` fence words, `MEM_WRITE`, `COND_WRITE`, `REG_TO_MEM`, `INTERRUPT`, `XE_SWAP`; PB-2.11 lists them), ticks vblanks and completes swaps without a device or a window. `rex_gpu_create` gains the backend name; `rex_app.cpp:53-56` keeps the fatal path for a missing plugin. Reuse the frame-dump recorder's packet understanding, not the Rayman patch (GPL). | `fh1-opening-sync` and `fh1-free-roam` complete on Windows with `--gpu_backend=null` and the same `save.file.write payload_hash` as the Vulkan run; frame log shows vblanks and swaps at the render limit | M |
| AP-0.2 | **Memory ordering on AArch64.** In the codegen, lower `sync` and `eieio` to `__atomic_thread_fence(__ATOMIC_SEQ_CST)`, `lwsync` to a release-acquire fence, `isync` to an acquire fence, and make `lwarx`/`stwcx` an acquire load and release compare-exchange, on every target (x86 emits nothing for the fences and keeps `lock cmpxchg`), so the generated code stays one tree. Audit the runtime's own cross-thread words the title polls (`WaitForGpuWrite`, the fence word at `0xFFCA4000`, vblank counters) for the same assumption. Count the sites and measure the AArch64 cost in AP-7.1. | `sdk/tests/ppc/asm` (167 fixtures) and `tests/unit/ppc` pass on AArch64; the x86-64 generated code is byte-identical before and after (the fences are no-ops there) | S-M |
| AP-0.3 | **`linux-arm64` game build.** Add `linux-arm64-{debug,relwithdebinfo,release}` project presets (no `-msse4.1`; `-march=armv8-a` or `armv8.2-a+fp16+dotprod`, a decision for AP-7.3), make the SSE baseline check and `PINYON_SHIFT_CPU_BASELINE` x86-only paths (`cmake/PinyonShiftRexGlue.cmake:66-100` already skips them off x86; the presets do not), fix `pinyon_shift_app.cpp:385`'s `ExitProcess`, build the SDK generator for the ARM64 host or run codegen on the PC and copy `.local/generated` (the generated tree is target-neutral), and link with `-mcmodel=small` as the SDK already chooses for AArch64. Decide `-fasync-exceptions`: Windows-only already. | `pinyon_shift`, `librexruntime.so`, `librexgpu-fh1.so` and the two facades link on the ARM64 Linux machine; `pinyon_shift_host_tests` pass there | S-M |
| AP-0.4 | **Boot to title with the null plugin.** Run `tools/pinyon.py launch --hidden` with `--gpu_backend=null`, fix what breaks: the shared-memory object (use `memfd_create` on Linux and Android instead of `shm_open`; `memory_posix.cpp:434-456`), `MAP_FIXED` without a reservation (`xmemory.cpp:166-172`: reserve the 4.5 GB range `PROT_NONE` first as `MapViewsMac` does, then `MAP_FIXED` into it; 39-bit VA kernels allow it), `sigaltstack` for the fault handler, `QueryProtect` out of the fault path, fibers (NP-14.2's AArch64 routine for real), FPCR rounding and flush modes. | The kernel log reaches the title's main loop; the opening route completes with `expect-simulation-time 0.95 1.08`; the thread list matches Windows (`Guest <start address>` names) | M |
| AP-0.5 | **Parity gates.** The opening, free-roam, race, buy-car and pause routes under the null plugin; save payload hashes equal to the Windows null-plugin run; a long free-roam soak (one hour) with no hang; `pinyon_shift_thread_sampler`'s POSIX equivalent or `perf` to confirm no thread spins. Hunt simde discrepancies with the save hash as the oracle and the `ppc_tests` fixtures as the bisection tool; record the findings for NP-13.2, which needs the same list. | Five routes pass three consecutive runs; hashes equal; no divergence or a documented, fixed cause for each | M |
| AP-0.6 | **16 KiB-page kernel.** The same routes on a 16 KiB kernel (Raspberry Pi 5 ships one; many ARM64 distributions offer one). Expect write-watch granularity to become 16 KiB (four guest pages per host page; `xmemory.cpp:2149-2192`) and count the extra watch faults per race frame against the 60-70 protection calls on Windows (NP-3.3). | Routes pass; `rex_physical_host_offset_e0 == 0x1000` logged; watch fault count recorded | S |

**Gates.** `ppc` and unit tests green on AArch64; five routes with Windows-equal
save hashes under the null plugin on 4 KiB and 16 KiB kernels; the memory
ordering change leaves the x86-64 generated code byte-identical; an
hour-long soak without a hang.

## AP-1 Android build and first frame

**Why now.** With the CPU side proven, the Android work is platform glue:
CMake, four missing files, the SDL activity and the surface.

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| AP-1.1 | **NDK toolchain and presets.** An `android-arm64-{debug,relwithdebinfo,release}` project preset using `$ANDROID_NDK/build/cmake/android.toolchain.cmake`, `ANDROID_ABI=arm64-v8a`, `ANDROID_PLATFORM=android-29` or later (see AP-3.3), `REXGLUE_USE_VULKAN=ON`, Ninja, and `-Wl,-z,max-page-size=16384` on every shared library (Android 15's 16 KiB kernels refuse unaligned ELF segments; **guess** about the exact platform rule, verified by AP-3.5). An SDK `android-arm64` preset for the standalone build. Codegen stays on the host (`PinyonShiftRexGlue.cmake:110-126` already resolves the host generator). Add the NDK, JDK and SDK build tools to a per-target toolchain manifest next to `config/release-toolchain.json`. | `cmake --preset android-arm64-release` configures | S |
| AP-1.2 | **SDK CMake for Android.** Gate `x11-xcb`, `wayland-client`, `surface_gnulinux.cpp`, the SDL X11/Wayland/ALSA/Pulse/PipeWire forcing and the `pthread rt` link behind `NOT ANDROID`; name the platform `android-arm64`; the GPU plugin, runtime and facades stay shared libraries; `rexcore` links `log` and `android`. Vulkan: the system `libvulkan.so` (`dynlib.h:56-60` already names it), no vendored loader. | The SDK's `rexruntime`, `rexgpu-fh1`, `rexui`, `rexaudio`, `rexinput` build with the NDK | S-M |
| AP-1.3 | **Missing glue.** Write `rex/main_android.h` and its `.cpp`: `GetAndroidApiLevel` (from `android_get_device_api_level`), `InitializeAndroidSystemForApplicationContext` (JNI context, `nativeLibraryDir`, files and cache dirs, `HOME`/`XDG_DATA_HOME` set for `GetUserFolder`), and call `rex::thread::AndroidInitialize`, `rex::memory::AndroidInitialize` and `rex::filesystem::AndroidInitialize` (declared, never called). Replace the `ASharedMemory`/ashmem path with `memfd_create` (AP-0.4). Define `IsAndroidContentUri`/`OpenAndroidContentFileDescriptor` or delete their users. Point the GPU plugin loader and the facade-module lookup at `nativeLibraryDir` instead of `GetExecutableFolder` (`/proc/self/exe` is `app_process64`). `crash_reporter_posix.cpp`: `execinfo` needs API 33, so use `_Unwind_Backtrace` or `libunwindstack`, and write the report into the app's files dir. | `libmain.so` links with every symbol resolved; `adb logcat` shows the kernel log's first lines when launched | M |
| AP-1.4 | **Activity, entry point and surface.** Build `pinyon_shift` as `libmain.so` with `SDL_main` (SDL3's `SDL_MAIN_HANDLED`/`SDL_main.h` in a small `main_android.cpp`), a Gradle project derived from `sdk/thirdparty/sdl3/android-project` (`SDLActivity`, `arm64-v8a` only, `android:extractNativeLibs` as needed for `dlopen` of the plugin, `largeHeap`, `screenOrientation="sensorLandscape"`, immersive sticky), and the `ANativeWindow` branch in `WindowSDL::CreateSurfaceImpl` (`SDL_PROP_WINDOW_ANDROID_WINDOW_POINTER`) producing an `AndroidNativeWindowSurface` for the presenter's existing `VkAndroidSurfaceCreateInfoKHR` path; add the `surface_android.h` the presenter includes. Pre-rotation: accept `currentTransform` and apply the rotation in the presenter's final blit, or request `sensorLandscape` only and treat 90/270 as identity (**guess**: Adreno composes rotation cheaply, Mali does not). | The activity starts, the presenter clears the swapchain, `vulkan_device` logs the device and the enabled features | M |
| AP-1.5 | **Title screen on device.** Push a game-data folder (AP-6.2's manual form: `adb push` to the app's external files dir), set `PINYON_SHIFT_GAME_ROOT` and `PINYON_SHIFT_STATE_ROOT` from the activity, run the opening route by script (`fh1-opening-sync` driven by `ScriptedInputDriver`, since the PowerShell runner cannot reach the device yet), fix what the Vulkan executor rejects on the device (AP-2 takes over from here). | The title screen renders; the opening route completes with the Windows save hash; a capture is pulled over adb | M |

**Gates.** A clean machine with the documented toolchain configures, builds
and installs the package; the title screen presents on the reference device
from an `adb push`ed game folder; the kernel log, frame log and crash report
land in the app's files directory and are pulled by `pinyon.py`.

## AP-2 Mobile Vulkan

**Why now.** The executor was written against one NVIDIA card. Phones differ
in features (geometry shaders, sparse binding, BC formats), in memory (one
pool shared with the CPU, enforced by `lmkd`) and in architecture (tile-based
deferred rendering, where the executor's EDRAM emulation is the worst case).
Capability first, then fallbacks, then the tiler-specific work in AP-7.

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| AP-2.0 | **Capability report.** A `--vulkan_capability_report` mode (or a small tool linked against `rexui`) that prints, for the device, every feature, extension, format property and limit the renderer reads or assumes: `dynamicRendering`, `independentBlend`, `fragmentStoresAndAtomics`, `vertexPipelineStoresAndAtomics`, `geometryShader`, `fillModeNonSolid`, `sampleRateShading`, `sparseResidencyBuffer`, `textureCompressionBC/ETC2/ASTC_LDR`, `maxStorageBufferRange`, `maxPushConstantsSize`, `maxPerStageDescriptorSampledImages`, push descriptors, fragment quad operations, the render-target formats of `render_target_cache.cpp:300-415` with multisampled integer sampling, `D32_SFLOAT_S8_UINT` and `D24_UNORM_S8_UINT`, A2B10G10R10 storage, swapchain formats and `supportedTransforms`, memory heaps and `VK_EXT_memory_budget`. Run it on the reference device and on every device the project can borrow; keep the reports under `docs/android/` (no personal data). Mobile expectations to check against (**guesses**): Adreno 7xx exposes BC and geometry shaders but not sparse residency; Mali G7xx exposes neither BC nor (on older drivers) geometry shaders; nobody exposes `fillModeNonSolid` reliably. | Reports for at least the reference device; every "unchecked assumption" in the readiness table has a measured answer | S |
| AP-2.1 | **Dynamic rendering request bug.** `VK_KHR_dynamic_rendering` is emplaced twice (`vulkan_device.cpp:203, 237`); the second `emplace` is dropped, so the promoted feature is enabled only when the device reports 1.3 (`:359-361, 685-689`) and the executor turns itself off on 1.1 and 1.2 drivers that expose the extension (`fh1_native_executor.cpp:298-301`). Fix, and make the executor's "dynamic rendering required" a start-up error with a message rather than a silent fallback to the render-target cache. Also fix the pack feature hash omission (`pipeline_cache.cpp:1258-1289`, `quad_operations_fragment`). | The executor runs on a 1.2 driver with the extension; a pack produced with and without quad operations has different names | S |
| AP-2.2 | **Geometry shaders and fill modes.** Default `vulkan_require_geometry_shader` and `vulkan_require_fill_mode_non_solid` to "if available", and qualify the vertex-shader expansion path for points, rectangle lists and quad lists (`primitive_processor.cpp:24-68`, `pipeline_cache.cpp:1561-1598`) against the goldens: NP-2.5 found 580-660 quad-list draws per 3D frame and 27-95 rectangle lists everywhere, and the quad split interpolates across a different diagonal, so the fallback is a visible difference to document rather than a bug. Wireframe is a debug view only. | Golden replays on a device without geometry shaders within a documented tolerance; no executor skips | S-M |
| AP-2.3 | **Formats without a query.** Query every render-target and depth format before use and choose fallbacks: `D24_UNORM_S8_UINT` where `D32_SFLOAT_S8_UINT` is absent (both executor transfer shaders then need the 24-bit path; D3D12 has one), RGBA16_SFLOAT for the UNORM gamma targets, `R32_UINT` pairs for `R32G32_UINT`, and a `sampleRateShading` check before the 26 MSAA executor modules load. Check A2B10G10R10 storage on the guest-output image (`presenter.h:71`) and pick RGBA8 or RGBA16F when absent. | The capability report's "missing" entries each have a tested fallback or an explicit refusal with a message | M |
| AP-2.4 | **Compressed textures.** On devices without BC: the existing GPU decode to RGBA8/RG8/R8 (`texture_cache.cpp:2539-2594`) costs 4 to 8 times the texture memory (the race's 265 MB becomes 1-2 GB) and the bandwidth of uncompressed sampling. Add a transcode path: BC1/BC3 to ASTC 4x4 or ETC2 (RGBA8 for alpha), BC4 to EAC R11, BC5 to EAC RG11, done once per texture hash and cached on device next to the shader pack (`cache/textures/<hash>.ktx2`), or produced on the PC from a texture dump (NP-10.3's `texture_dump_dir` already produces `<hash>.dds`) and pushed with the game data. Measure quality with the capture MAE on free roam. Mali and PowerVR need this; Adreno and Xclipse probably do not (**guess**, AP-2.0 decides). | Free roam on a no-BC device holds textures under the 384 MB soft limit; captures within tolerance | M |
| AP-2.5 | **Memory model at 1x.** Without sparse residency, shared memory is a dedicated 512 MB allocation and the scaled-resolve buffer another `512 MB x scale^2`, so Android is 1x-only and the scale setting is clamped and explained. Budget the rest: 1x surfaces 522-562 MB, textures 384 MB soft, transfer words 10 MB, the executable's 100 MB+ of code, the 512 MB guest physical heap, host caches; target under 3 GB of resident memory, which a 12 GB device tolerates and an 8 GB device may not (**guess**, measured in AP-7.0). Read `VK_EXT_memory_budget` where exposed and log heap usage per frame; lower the texture soft limit on small devices; handle `onTrimMemory` (AP-3.4). | Peak RSS and Vulkan heap usage logged on the race route; the 1x clamp shows in SETTINGS with a reason | S-M |
| AP-2.6 | **Pipeline cache and startup.** Persist a `VkPipelineCache` next to the pack (PB-2.13 found no need on NVIDIA; mobile drivers compile slowly and have no disk cache the app controls), create pipelines on a worker instead of the recorder on a first-seen pipeline, and produce a Vulkan pack on the device from the preparation route's capture (NP-15.2) keyed by the device feature hash, so play never translates. Record start time with and without. | Start-to-title time and first-race hitch count recorded with and without the cache; zero runtime translations on the route matrix with a pack | S-M |
| AP-2.7 | **Route matrix on the reference device.** `fh1-opening-sync`, `fh1-free-roam`, `fh1-race-sync`, `fh1-buy-car`, `fh1-pause`, `fh1-fmv` and `fh1-map` at 1x with zero executor skips and zero pack misses; captures compared against the Windows Vulkan run by MAE; frame dumps recorded on Windows replayed on the device (`test-fh1-frame-replays.py` with the device as a target through AP-8.1). | All routes pass three consecutive runs; the four goldens replay within the documented tolerance | M |
| AP-2.8 | **Graphical glitches on Adreno.** Reported by the maintainer playing on the 8 Elite: shadows, lighting and reflections flicker, and the whole screen shows tiled artifacts, as if it were rendered in quadrants. First check whether the Windows Vulkan run shows them: capture the same frames on both (AP-8.1 routes, `mae.py`), bisect by executor cvar (MSAA off, `fh1_native_stencil_export`, resolve paths, transfers), and check the tile-shaped artifact against the Adreno tile size and the render-pass boundaries: a missing barrier or load op between renderings, a stale attachment read by a later pass, or an EDRAM transfer reading a region before it is written. Shadows and reflections are rendered to textures by resolves, so start with resolve and transfer ordering. | No flicker in shadows, lighting or reflections and no tile artifacts in the race and free-roam routes; device captures within the Windows MAE tolerance | M |

**Gates.** Capability report checked in for the reference device; no
unchecked feature or format use remains in the Vulkan path; the route matrix
passes at 1x on the reference device with the Windows captures as control;
the texture, surface and shared-memory budget is logged and under the
agreed ceiling.

## AP-3 Lifecycle and storage

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| AP-3.1 | **Background and foreground.** Handle `SDL_EVENT_DID_ENTER_BACKGROUND`, `WILL_ENTER_FOREGROUND`, `TERMINATING` and `LOW_MEMORY` in `SDLWindowedAppContext::ProcessEvent` and route them to the app: on background, pause the GPU commands thread after the current frame (`GraphicsSystem::Pause`, `:501`), pause audio (`AudioSystem::Pause`, `:370`), and freeze guest time so the simulation does not integrate the pause as one step (PB-4.2's cap already bounds it; make the pause explicit); on foreground, resume in the reverse order. Guest threads keep running or are suspended as a whole (`XThread` suspend exists for the debugger); decide and measure battery drain in the background. | Background for one minute and resume: the game continues at the same simulation time, audio in sync, no device loss | S-M |
| AP-3.2 | **Surface loss and recreation.** Android destroys the `ANativeWindow` on background and gives a new one on foreground: the presenter today attaches a surface at open and close only, so add a window-surface-changed path that tears down the swapchain, waits for the device, and recreates from the new window (the `OUT_OF_DATE`/`SURFACE_LOST` reconnect exists for the first half). Rotation and fold/unfold change the extent; the presenter's letterbox follows. Also handle `SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED` and display cutouts (`SDL_GetWindowSafeArea`) for the host UI's safe area. | Ten background-foreground cycles and ten rotations during free roam without a device loss or a stale frame | M |
| AP-3.3 | **Storage.** Game data and state in app-specific external storage (`getExternalFilesDir`, no permission needed, visible over adb and MTP) with `PINYON_SHIFT_GAME_ROOT=<files>/game/base` and `PINYON_SHIFT_STATE_ROOT=<files>/state` set by the activity; the state layout stays `user/`, `config/`, `cache/`, `mods/`, `backups/` as `pinyon.py` defines it, so saves move between PC and device by copying. Optional: a one-time folder picker (SAF document tree) for players who keep the 7.2 GB on an SD card, which needs the content-URI file path (`MappedMemory::OpenForAndroidContentUri` exists for it); defer unless asked. Case-insensitive lookup and the 2,400-file start-up walk are measured on the device's flash. | A save written on the device loads on Windows and back; start-up file walk time recorded | S-M |
| AP-3.4 | **Low memory and `lmkd`.** On `LOW_MEMORY` and `onTrimMemory`, release the texture cache above a floor and drop the pipeline placeholder caches; log RSS, the Vulkan heaps and `/proc/self/status` at each frame-log sample so an `lmkd` kill is diagnosable after the fact. | A memory-pressure test (another app in the foreground, `am send-trim-memory`) does not kill the game at 1x on the reference device | S |
| AP-3.5 | **16 KiB-page device.** Run the route matrix on a 16 KiB kernel (NP-14.3's real test) and confirm the ELF alignment of every `.so` in the package. | Routes pass; `rex_physical_host_offset_e0 == 0x1000`; `zipalign -P 16` passes | S |
| AP-3.6 | **Fonts, crash reports, logs.** Host UI fonts come from the disc (NP-1.3), so only the system-font fallback needs an Android path (`/system/fonts/Roboto-Regular.ttf`); `host_style.cpp:6-19` gets the branch. The POSIX crash reporter writes into the files dir and the activity offers to share it (no network); the kernel and frame logs rotate so the files dir stays bounded. | A forced crash leaves a report that `pinyon.py android pull-logs` fetches | S |

**Gates.** The lifecycle test script (background, foreground, rotate, fold,
trim memory, in that order, in free roam and in a race) passes three times;
saves round-trip to Windows; crash reports and logs are retrievable.

## AP-4 Input for a phone

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| AP-4.1 | **Controllers.** SDL3's Android gamepad path already feeds the SDL input driver; qualify an Xbox controller over Bluetooth, a PlayStation controller and a clip-on (Backbone-class) USB-C controller against NP-6's mapping and the pause menu; make sure the `xinput` driver is excluded from the build (`sdk/src/input/CMakeLists.txt:33-37` does so) and that `SDL_HINT_JOYSTICK_*` hints are set for Android. | Three controllers drive the pause route and a race; the mapping screen shows the right glyphs | S |
| AP-4.2 | **On-screen pad.** A touch overlay drawn by the host UI (its glyph atlas and button art already come from the disc) that produces a virtual pad through the input system, following `ScriptedInputDriver` (`src/fh1_render_test.cpp:844`) as the template for a software pad: left stick for steering (or tilt steering through `SDL_SENSOR`, which the build forces off at `sdk/thirdparty/CMakeLists.txt:272`; decide), right-side throttle and brake, face buttons, Start. Fingers reach the context through new `SDL_EVENT_FINGER_*` cases (`windowed_app_context_sdl.cpp:126-180`) and the input watch's upper bound (`sdl_input_driver.cpp:77`). Hide the overlay when a controller is active. | The opening route and a race are completable by touch; the overlay's layout is saved in the host config | M |
| AP-4.3 | **Touch in the host UI.** `HostUi` takes mouse events already (`host_ui.h:98-101` with row hit rectangles); map finger down, move and up to them with a tap-versus-drag threshold and a wheel from vertical drags, and make the ImGui developer overlays respond through `ImGuiDrawer::OnTouchEvent`. | SETTINGS, the trainer and the achievements list are navigable by touch only | S |
| AP-4.4 | **Keyboard-only features.** F6 settings, F8 photo, F10 trainer, F11 fullscreen and the SDK's F3/F4/F7 and console have pad or touch routes: a long-press on Start (or the overlay's menu button) opens SETTINGS, photo export is a SETTINGS action, the trainer is a SETTINGS page, fullscreen is meaningless on Android. Keep the keyboard binds for connected keyboards. | Every player-facing feature reachable with a controller alone and with touch alone | S |
| AP-4.5 | **Haptics.** SDL haptics are off in the build (`SDL_HAPTIC OFF`); the title's rumble reaches controllers through SDL's rumble API, not the haptic subsystem, so check it works on Bluetooth pads and expose the NP-6 haptics options. Phone vibration for the on-screen pad is optional. | Rumble felt on a Bluetooth pad in a collision | S |
| AP-4.6 | **Hide the on-screen pad when a gamepad is connected.** Today the overlay shows on any touch and hides 20 s later, whether or not a pad is present. On `SDL_EVENT_GAMEPAD_ADDED` (or input from a physical pad) hide it and keep it hidden while one is connected, ignoring touches for the overlay; bring it back on `SDL_EVENT_GAMEPAD_REMOVED` when no pad is left. | With a Bluetooth pad connected the overlay never appears, touch or not; it returns when the pad disconnects | S |

**Gates.** A new player with only the phone finishes the opening drive and
one race with touch, then with a Bluetooth controller; `fh1-pause` driven by
the virtual pad passes.

## AP-5 Audio

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| AP-5.1 | **Backend and latency.** SDL3 picks AAudio on Android 8.1 and later (OpenSL ES before); measure output latency of the SDL audio driver's pull model with the title's 48 kHz six-channel frames downmixed to stereo, and set the SDL buffer size and `SDL_HINT_AUDIO_DEVICE_STREAM_ROLE` for games; confirm the XMA decoder's NEON path (vendored FFmpeg `config_android_aarch64.h`) keeps the audio thread (29 % of a desktop core, PB budget table) within a phone core. | Engine audio in sync with the frame in a capture; audio thread CPU recorded | S |
| AP-5.2 | **Pause, routing and focus.** Pause and resume with AP-3.1; handle Bluetooth connect and disconnect (`SDL_EVENT_AUDIO_DEVICE_*`) by reopening the stream; respect audio focus (another app's playback ducks or pauses the game's). | Headphones connected mid-race switch the output without a crash or a stall | S |

**Gates.** No audio underruns logged over a 20-minute race; a device switch
mid-session recovers.

## AP-6 Cross-build and sideload workflow

**Why the PC does everything.** The APK contains the generated translation,
so it is exactly as private as `pinyon_shift.exe` today: built on the
player's PC from their own ISO, installed on their own device, never
shared. The device never compiles, and no server is involved.

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| AP-6.1 | **`pinyon.py android` subcommands** on the NP-12.7 core: `provision` (NDK, JDK, platform tools, pinned and hashed in the toolchain manifest), `build` (host codegen if stale, the `android-arm64-release` preset, Gradle assemble, `apksigner` with a locally generated debug or player keystore), `install` (`adb install -r`), `push-data` (the extracted `game/base` to the app's external files dir with resume and a hash manifest; 7.2 GB over USB 3 is a few minutes, over Wi-Fi adb much longer), `pull-logs`, `run-route`. The WPF launcher gets one "Build for Android" button that calls these with the JSON event protocol, no more. | A clean PC with the manifest's tools goes from ISO to a running title screen on the device with four commands | M |
| AP-6.2 | **Boundary tooling.** Add `.so`, `.apk`, `.aab`, `.idsig`, `.keystore` and the ELF magic `\x7fELF` to `config/repository-policy.json` and to `package-launcher.ps1`'s forbidden list; write the APK only under `.local/android/` or `out/`; a `tools/tests` case asserts the Gradle project template contains no generated code or game data; the release workflow stays Windows-launcher-only. | `check-repository-boundary.ps1` rejects a staged `.apk` and a `.so`; CI green | S |
| AP-6.3 | **Packs and caches on the device.** Decide per AP-2.6: produce the Vulkan pack and the pipeline cache on the device on first run (a preparation route that runs hidden at first start, minutes long, with progress in the activity), or on the PC with the device's feature hash from the capability report (`pinyon.py android prepare-shaders --device`), and push them with the data. Record misses on the device and let `pull-logs` bring them back for the next production, as `cache/fh1-shader-misses` does on Windows. | First start to playable under five minutes after install on the reference device; zero runtime translations afterwards | S-M |
| AP-6.4 | **Updates and versions.** The package version follows `config/release.json`; `pinyon_shift_build.json` (commits, payload SHA, ABI, NDK version, `cpu_baseline = arm64`) ships inside the APK's assets and is shown in SETTINGS and in crash reports; a mismatched state root from an older build migrates as on Windows (config schema). | A rebuild installs over the old package and keeps the save; the build provenance is readable from the device | S |
| AP-6.5 | **Documentation.** `docs/ANDROID.md`: requirements (device tier, Android version, free space of about 8 GB), the four commands, what is and is not private, and the troubleshooting list (driver too old, no BC, out of memory). | Follows a reviewer from zero to playing | S |

**Gates.** Disc-to-play on the reference device from a clean PC with the
documented steps; the boundary check rejects every Android binary form; the
release pipeline is unchanged.

## AP-7 Performance and thermals

**Where it stands, by extrapolation (all guesses until AP-7.0).** On the
desktop (Ryzen 7 5800X, RTX 4080) a 1x race frame costs about 9.4 ms on the
GPU recorder thread for 5,100 draws, 6.5-7.8 ms on the title's render
thread, 4.6 ms per simulation step, about 6.4 ms of GPU, and 29 % of a core
for audio ([performance backlog](PERFORMANCE_BACKLOG.md#budget)). A
2023-2024 flagship core (Cortex-X3 or X4 at 3.2-3.4 GHz) runs this kind of
scalar, store-heavy code at perhaps a third to a half of the 5800X's
per-thread speed, so expect the render thread at 13-20 ms, the simulation
step at 9-14 ms, the recorder at 20-30 ms, and audio at most of a middle
core; the GPU (Adreno 740 or 750) has a tenth or less of the RTX 4080's
throughput, and the executor's 300 renderings and 600 barriers per frame
each flush tiles, so the GPU frame could be 40-80 ms before any tiler work.
That makes **30 fps at 1x the realistic target** and 60 fps a stretch goal
that needs AP-7.4's structural items. The frame-rate limit, the vblank
cadence and the simulation cap already exist as settings (NP-1.4, PB-4.2).

| Item | Work | Expected | Size |
| --- | --- | --- | --- |
| AP-7.0 | **Measure first.** The race route at 1x on the reference device with the frame log, `pinyon_shift_thread_sampler`'s POSIX equivalent (or `simpleperf` with the generated-line mapper of NP-3.0), per-frame GPU timestamps (PB-0.1 exists on Vulkan), Vulkan heap usage, RSS, CPU frequencies per cluster and the thermal status over a 20-minute run. Produce the same budget table as the performance backlog's for the device. | Decides everything below | S |
| AP-7.1 | **ARM64 codegen cost.** Measure AP-0.2's fences (every `lwsync` becomes a `dmb`), then the deferred PB-3 items on this CPU: offset-free accesses (PB-3.3), register locality (PB-3.2), fused `vmaddfp` (PB-3.4, on AArch64 `fmla` is natural), MXCSR-equivalent toggling of FPCR (PB-3.5), `-march=armv8.2-a+fp16+dotprod` versus `armv8-a`, and `-mcmodel=small` with LTO across the generated units (`PINYON_SHIFT_RECOMP_IPO`). Gate every numerics change with the save hash and `expect-simulation-time`. | The render thread and simulation step within 30 fps budgets (33 and 16 ms) with margin | M-L |
| AP-7.2 | **Thread placement on big.LITTLE.** Default `ignore_thread_affinities` on (the guest CPU i to core i mapping lands on little cores) and place the recorder, decoder, render and simulation threads on the big and prime cores from `/sys/devices/system/cpu/cpu*/cpu_capacity`; replace `SCHED_FIFO` (EPERM for apps) with `setpriority` on the thread's tid within what Android allows; keep audio on a middle core. Measure against no placement. | p95 frame time; fewer missed vblanks | S |
| AP-7.3 | **Recorder cost per draw on the device.** PB-2's memos were tuned against NVIDIA descriptor costs; re-profile `UpdateBindings`, push descriptors (`VK_KHR_push_descriptor` availability on Mali is driver-dependent, **guess**), dynamic uniform buffers and the decode-to-record split's queue depth on the device. | Recorder under 33 ms for a race frame; the split's benefit confirmed on a phone | M |
| AP-7.4 | **Tiler-friendly executor.** The items the desktop measured as noise are the mobile levers: batch renderings (PB-1.5: a rendering per change of bound surfaces, texture-load barriers per load not per dispatch, uploads before the rendering), clears as `loadOp = CLEAR` (PB-1.6), `storeOp = DONT_CARE` for depth surfaces a census proves unread before their next clear, single-sampled host surfaces for the 4x guest surfaces (PB-1.1 at 1x, an accepted fidelity trade), the sun shadow pass and its resolves as the largest transfer sources (PB-1.3's stencil copy, PB-1.10's rate ideas), and resolve aliasing (PB-1.2) to avoid the untile round trip through the 512 MB buffer. Measure each by knock-out on the device as PB did. | GPU frame under 33 ms at 1x | L |
| AP-7.5 | **Thermals and sustained performance.** A 20-minute race session logging thermal status, cluster frequencies and frame time; choose the shipped defaults (30 fps limit with vblank at 60, PB-4.2's capped delta, single-sampled surfaces) that hold the frame time flat after throttling sets in; expose a PERFORMANCE (30) and a QUALITY (30, MSAA) preset in SETTINGS as PB-5 did for the desktop. | Frame-time median within 10 % between minute 2 and minute 20 | S-M |
| AP-7.6 | **Memory under load.** Peak RSS and Vulkan heaps across the route matrix with AP-2.4's transcoded textures; a lower texture soft limit and a smaller shared-memory commit (only the pages the title maps, which the write-watch bitmap knows) if 8 GB devices are to be supported. | Peak resident memory recorded; the 8 GB verdict written down | S-M |

**Gates.** Race route at 1x on the reference device: frame median at or
under 33.3 ms and p95 at or under 50 ms over the last 600 frames, after 20
minutes of play; `expect-simulation-time 0.95 1.08`; save hash equal to
Windows; no `lmkd` kill under the memory-pressure test.

## AP-8 Qualification and tooling (ongoing)

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| AP-8.1 | **Routes on the device from the PC.** `run-fh1-render-test.py` gains a device target: it pushes the route and seed, launches the activity with the route arguments through `am start` extras, waits, and pulls the frame log, captures and the kernel log; the PowerShell dependency becomes a Windows-host detail. The seed stays read-only (the runner copies it into a private directory on the device). | The full route matrix runs from one command against a connected device | M |
| AP-8.2 | **CI without game code.** The SDK's `android-arm64` target built in the SDK's CI (an `ubuntu-latest` job with the NDK), and the project's `PINYON_SHIFT_HOST_TESTS_ONLY` configure for Android compiling the host sources and the Gradle template; no game data ever reaches CI. | Both jobs green on every push | S |
| AP-8.3 | **Second and third GPU vendor.** AP-2.0's report and AP-2.7's routes on a Mali device and an Xclipse device; vendor workarounds recorded as cvars with the driver version they apply to. | Route matrix at 1x with zero skips on two vendors | M (+hardware) |
| AP-8.4 | **Play test.** An unscripted session by a player on the reference device before each train, as NP-X asks for the desktop. | Findings filed as rows | — |

## Risks and open questions

| Risk or question | Why it matters | What resolves it |
| --- | --- | --- |
| **Memory ordering on AArch64** (`sdk/src/codegen/builders/system.cpp:33-49`) | Guest spinlocks, fence polling and cross-thread flags can race on a weakly ordered CPU; such bugs appear as rare hangs, not failed boots | AP-0.2 lowers the barriers; AP-0.5's hour-long soak and the race route on three runs |
| **Guest CPU cost on phone cores** (guess: 2-3x slower per thread) | If the render thread or a simulation step does not fit 33 ms, no renderer work helps | AP-7.0 measures; AP-7.1 applies PB-3's deferred items |
| **GPU cost of the EDRAM emulation on a tiler** (guess: 40-80 ms before tuning) | The executor's rendering breaks, full-surface transfers and `LOAD/STORE` policies were tuned on an immediate-mode GPU | AP-7.0's GPU timestamps and knock-outs; AP-7.4 |
| **Resident memory near 3 GB at 1x** (guess) | `lmkd` kills the process on 8 GB devices; 12 GB devices become the floor | AP-2.5 and AP-7.6 measure; the texture transcode of AP-2.4 and a smaller shared-memory commit are the levers |
| **No sparse residency on mobile** (guess) | Fixes Android at 1x; the scaled-resolve buffer is `512 MB x scale^2` | AP-2.0 confirms; AP-2.5 clamps and explains |
| **Feature gaps by vendor** (geometry shaders, BC, `fillModeNonSolid`, D32S8, push descriptors) | Each missing feature is a code path untested on desktop | AP-2.0's report per device; AP-2.2 to AP-2.4 fallbacks; AP-8.3 |
| **16 KiB-page kernels** | Wrong 0xE0 translation breaks every physical-heap access; ELF segments must be 16 KiB-aligned on Android 15 kernels | AP-0.6 on Linux, AP-3.5 on Android |
| **Driver quality** | Mobile Vulkan drivers vary by device vintage and OEM update policy; a 2023 device may carry a 2022 driver forever | Minimum: a Vulkan 1.3 driver, checked at start with a message; AP-2.0 reports collected per device |
| **Thermal throttling** | A 30 fps budget met for two minutes and missed at ten is not playable | AP-7.5's 20-minute protocol and flat-frame-time gate |
| **Pause and surface loss** | Android destroys the window on every background; the presenter was written for a window that lives as long as the app | AP-3.1, AP-3.2 with the cycle test |
| **Legal reading of the APK** | A package holding the translation must stay as private as the Windows executable; the tooling must not make sharing easy by accident | The maintainer's decision; AP-6.2's boundary rules; no "export APK" affordance beyond the install |
| **Data transfer** | 7.2 GB per device over adb is slow and fragile over Wi-Fi | AP-6.1's resumable push with a hash manifest; USB recommended |
| **Touch controls feel** | A racing game on a touch screen lives or dies on the overlay; no script can judge it | AP-4.4's human test; shipping tilt steering as an option |
| **Fiber routine on real AArch64** | NP-14.2's assembly was only run through a harness on x86-64 | AP-0.4 is its first real run; the harness ports to AArch64 in the same row |
| **Which device tier to call "supported"** | Determines the memory and GPU floors and the honest README line | AP-7.0 and AP-7.6 on the reference device; AP-8.3 on a second vendor |
| **Is a Linux ARM64 box available before a phone?** | AP-0 wants one; without it, AP-0 runs on the phone through the NDK build with the null plugin and `adb logcat`, slower to iterate but workable | The maintainer's hardware choice (see Needs a person) |

## Relation to the native port backlog

NP-14's six rows map as follows: NP-14.1 is AP-1 (plus AP-0.3 for the
presets), NP-14.2 and NP-14.3 are exercised by AP-0.4 and AP-0.6, NP-14.4
is AP-2 and AP-7.4, NP-14.5 is AP-6, and NP-14.6 is AP-3 to AP-5 and
AP-7. NP-14's dependency on NP-13 is kept in spirit (whichever ARM64 port
runs first does AP-0's correctness work once) but is not required: AP-0
needs only an ARM64 Linux machine. The native port backlog's slice map and
Needs-a-person table stay the index; this document holds the rows.
