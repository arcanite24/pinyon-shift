# What is still emulated: native replacement survey

Written 2026-11-15 at `dev` `72df0d76`. The question: which parts of Pinyon
Shift still run as translated guest code or through an Xbox 360 emulation
layer, and which of them could be replaced by host code for a measurable
gain on the Steam Deck LCD and the Odin 2 Portal (CPU ms a frame, GPU ms,
RSS, stutter)? Performance comes before parity.

Nothing was built or run for this page. Every number comes from the pages
linked below; a number marked *estimate* is arithmetic on those, not a
measurement. Where the repo has no data the row names the probe that would
size it. Compare CPU at the 60 fps cap, not uncapped (see
[FULL_FRAME_RENDERER.md](FULL_FRAME_RENDERER.md#fr-3-to-fr-6-the-cpu-ceiling-capped-2026-11-15)),
and judge in-run A/Bs against an A/A run.

## Summary

- **Most of what is emulated has been measured, and most of it is closed.**
  The GPU front end (PM4 decode, recording, submission), the D3D layer,
  scene submission, resolves and transfers, shader translation, the
  kernel's locks and XMA each have a measured ceiling in
  [lessons](../site/pages/lessons.md#what-didnt-pay-off-here) or the
  research pages. None is re-proposed here.
- **What is left is small pieces, not one pool.** On the Deck the guest
  threads use about 23 ms of CPU a frame: render 8, simulation outside
  physics 5.3, FMOD mixer 3.0, audio logic 2.1, physics 1.8, procedural
  geometry 0.9, presentation worker 0.9, crowd 0.3
  ([platforms](../site/pages/platforms.md#linux-and-the-steam-deck)). The GPU threads
  add about 24 ms. The Odin's GPU takes 15.3 of 16.7 ms. The levers that
  worked since October removed dead work or ran a system at a lower rate
  (voice chat tick, gamma ramp, HUD every other frame); native rewrites of
  live game code ran only 1.2-1.5 times faster than the translation.
- **The ranked list below follows that pattern.** It puts rate and dead-work
  items first, memory attribution second, and the large native replacements
  (FMOD mixer, whole-car physics) last.
- **Unmeasured pools that decide the order** are the Deck's kernel time (only
  the Odin has a kernel-sample profile), what the 200-350 MB of native heap
  holds on both devices, and how often each thread wakes on a
  power-limited Deck.

## Ranked candidates

Savings are CPU ms a frame at the 60 fps cap unless stated. Effort: S is
days, M a week or two, L a month or more. *Estimate* means arithmetic on
recorded numbers.

| # | Candidate | What is emulated now | Native replacement | Evidence, or the probe that would size it | Effort | Risk |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | **Audio logic at the console's rate** (NR-1). *Done 2026-11-16, on by default: `src/guest_native/audio_update.cpp` gates the four command-list thunks that hold 98 % of `CAudioThread` (records in [audio](../site/findings/audio.toml), "CAudioThread command lists"); audio thread -0.67 ± 0.09 ms on the Deck (one full-mix run), -0.44 ± 0.08 and -0.63 ± 0.05 ms on the Odin (two runs); captures unchanged in RMS and 30 Hz envelope share; skips only at 57 fps or more. The Odin race route left the car stuck at the guardrail, so its runs are a revving engine, not a drive* | `CAudioThread` runs the game's audio logic and the FMOD event system update once per *rendered* frame, so at 60 fps it runs twice as often as on the console's 30 fps | A host gate in front of the update slot, like [`ui_update.cpp`](../src/guest_native/ui_update.cpp): run it on one frame in two and pass the skipped time on | 2.1 ms on the Deck, 2.39 ms on the Odin ([threads](../site/findings/threads.toml), "other guest threads"). Half is 1.0-1.2 ms *estimate*. The same HUD change took 0.46-0.70 ms off the Deck's simulation thread and was noise on the Odin, so size both devices. Probe: add the cvar, in-run A/B on `fh1-race-sustained`, listen for engine-pitch and tyre-sound steps. Check that the 30 Hz console cadence is the real rate before trusting the premise | S | Low to medium: audio parameter steps; the HUD change had a hidden side effect (minimap submission) and this one may too |
| 2 | **Name the native heap, then trim it** (NR-2). *Trim rejected 2026-11-16: `malloc_trim`/`M_PURGE` every 60 s returned 1-11 MB on the Deck and 3-5 MB on the Odin ([lessons](../site/pages/lessons.md#what-didnt-pay-off-here)); the per-site census still needs `heaptrack` or `heapprofd`, not set up* | Nothing named: the Odin's scudo heap is 209 MB after the lazy XMA change (321.6 MB before), and the Deck has 158 MB of heap plus 188 MB of unnamed anonymous mappings ([NN-0.4](NEAR_NATIVE_RESEARCH.md#progress), [NN-4.1](NEAR_NATIVE_RESEARCH.md#progress)) | Per-site allocation census, then pooling, lazy allocation or smaller caches at the sites that dominate | RSS is half the yardstick and the Deck is already short of VRAM (873 of 1,024 MB used system-wide, 128 MB evicted). Probe: `heapprofd` on the Odin, `heaptrack` or an allocation hook on the Deck, grouped by call site, at race-sustained. No saving can be quoted before it | S probe, M fix | Low |
| 3 | **FMOD mixer, what stereo and ParamEQ left** (NR-3). *Not built 2026-11-16: no two or three leaves pass 60 % of the mixer; a reverb twin alone is about 0.15 ms estimate ([lessons](../site/pages/lessons.md#what-didnt-pay-off-here))* | Mixer thread 3.0 ms on the Deck (already stereo) and 4.86 ms on the Odin before the stereo change (3.0 after, about -1.0 ms); reverb is about a fifth of the Deck's mixer | Native twins of the next-largest units (reverb first: 12.3 % of the v4 mixer thread on the 8 Elite, 2.3 % of the Odin process), verified with the existing `tools/fmod-dsp-test` at the 60 dB bar | Switching the reverb off took 0.28-0.31 ms off the Deck, so a twin that costs half saves about 0.15 ms *estimate*; a twin of every unit would cap near 1 ms *estimate*. The channel-matrix twin read -0.03 ± 0.07 ms because it ran only 125 times a frame. Probe: per-function `perf` of the Deck's mixer thread on the current build; build a twin only if two or three leaves hold over 60 % of it | M per unit, L for all | Medium: audio fidelity; a whole-mixer replacement was dropped before for that reason ([considered and rejected](NEAR_NATIVE_RESEARCH.md#considered-and-rejected)) |
| 4 | **Dead-work census of the minor guest threads** (NR-4). *Rejected 2026-11-16: no unused output; `82E1C3E8` is a request worker, the cost is the wait path (NR-7); Deck 0.11/0.075/0.02 ms, Odin 0.18/0.10/0.08 ms ([threads](../site/findings/threads.toml))* | Threads with no known purpose or an unused output, still running in single player. Odin ms a frame: `82E1C3E8` 0.35 (91 % outside guest code, loops wait and release-mutex), `830C6918` (text formatting and allocation, about 1 % of a core), `829F6620` D3D tiling worker 0.23, presentation worker `82589AE8` 1.23, procedural geometry `82E217A0` 1.47 | Per thread: find what reads its output; skip, rate-limit or reuse as for the voice-chat tick (-0.114 ms) and the gamma ramp (17 % and 13 % of the render thread before the hook) | The first three total about 0.7 ms on the Odin *estimate*. The presentation worker and procedural geometry are live work (rate or caching, not removal); the latter already has native instance culling. Probe: call-graph by thread on the Deck, then for each hot function the readers of the buffer it fills (write-watch or a poisoned-output run, as in the LR slot check) | S per thread | Low if the output is shown unused; each needs its own route matrix |
| 5 | **Shader-load memo, re-checked under the keep-small-wins rule** (NR-5). *Already done (2026-11-16 check): its successor `gpu_d3d_shader_cache` has been on by default since 2026-10-15, decoder -0.50 ± 0.07 ms on the Odin ([D3D_RENDERER_RESEARCH.md](D3D_RENDERER_RESEARCH.md), DL-0.3 revisited); this row read the older rejected variant* | Each `IM_LOAD` rehashes the shader microcode with XXH3 (1.0 % of the Odin process; about 4,900 loads a frame) | Remember a load by its guest address, dropped by a write watch on the microcode | Exact (0 mismatches in 57 M checked loads, 99.8 % hits) and -0.32 ± 0.09 ms of decoder CPU on the Odin (four in-run A/Bs), rejected only at the old 0.5 ms bar ([lessons](../site/pages/lessons.md#what-didnt-pay-off-here), DL-0.3). Check whether the code survives; if so, repeat on the Deck and enable if it is a gain there too | S | Low |
| 6 | **Wake-rate and package-power census on the Deck** (NR-6) | The Deck is bound by a 15 W budget that CPU and GPU share, and 20+ host and guest threads wake on timers and events (a 100 Hz XHV2 timer was one) | Remove or batch timers and wakes the same way waits were fixed (-15 % CPU from the fence poll) | Unmeasured: the Odin's 1 W power samples cannot resolve a 1 W change ([NN-0.7](NEAR_NATIVE_RESEARCH.md#progress)) and no Deck wake count exists. Probe: `perf stat -e context-switches` per thread and `power1_average` over 60 s of race on the Deck, then A/B the top waker. The payoff shows as GPU clock, not frame time ([limits](../site/pages/limits.md#the-steam-decks-shared-power-budget)) | S probe | Low |
| 7 | **XAPI wait and signal wrappers served by a host fast path** (NR-7) | The title's wait, set-event and release-mutant wrappers go through the kernel export, the handle lookup and the host wait: 3.39 M waits, 2.25 M `NtSetEvent` and 2.09 M `NtReleaseMutant` in one desktop race, about 1 % of the Odin process | A hook at the wrapper that maps a guest handle straight to the host primitive (array index, no table or global-lock entry) | Kernel time is 9.1 % of the Odin process by first user frame, of which wakeups are 3 %; but the handle-lookup lock cost only 0.16 ms ([NN-3.10](NEAR_NATIVE_RESEARCH.md#progress)) and a no-waiter `notify_all` costs 1-2 ns (NN-3.3). So the ceiling is the call path, about 0.4 ms on the Odin *estimate*. The Deck has no kernel-sample profile. Probe: Deck `perf record -g` with kernel samples at race-sustained, split by first user frame as NN-0.1 did | M | Medium: object lifetime and waits are where past races came from |
| 8 | **Native inflate for loading** (NR-8) | A guest deflate loop is about 20 % of the asset worker while loading, one sample in 1,160 in a race; the LZX decoder is native already | A bit-exact native inflate, checked per call like LZX | Matters for load time and the first seconds of streaming, not the race. Probe: time to race-ready with the loop skipped on a fixed archive, plus the transition-frame stalls (75-350 texture reloads in 212-343 ms, [files](../site/findings/files.toml)) | S | Low |
| 9 | **Retire guest code without a crash on a stray read** (NR-9) | The 14.7 MB code section is resident but never read by generated code (258 jump tables aside) | Mode 3 of `pinyon_shift_retire_guest_code`: replace no-access with read-only zero pages that log the first read | 12-14 MB of RSS on the Odin; the current mode 2 is off by default because one read of retired code ends the game ([NN-6.7](NEAR_NATIVE_RESEARCH.md#progress)). A small win only if it can be made safe | S | Medium: a silent wrong read replaces a crash |
| 10 | **Whole-car physics step** (NR-10) | Physics is 1.8 ms on the Deck and 1.4 ms on the Odin, flat: no leaf over 13 % of itself; the tyre model is 0.01 % | One native step for the car body, verified against the translation | Only a whole-car step could reach #1071's 0.5 ms gate; at the measured 1.2-1.5 times, 1.8 ms gives 0.4-0.6 ms *estimate*. The AI-step-interval trick saved nothing. Not started | L | High: physics parity, replays, saves |

### What the order assumes

- Rows 1, 4, 5 and 6 are probes of days; each could move two to six small
  wins into the default set. Together they are about 1.5-3 ms on the Deck
  *estimate*, which is the same size as the whole of NN-1's code-generation
  gains.
- Row 2 is the only one that moves RSS by more than tens of MB, and it is
  the least sized. Do it before row 9.
- Row 3 is the largest single CPU pool left on the Deck that is guest code,
  but its ceiling is near 1 ms for a month of work; it follows the probes.

## Survey by area

For each area requested, what is emulated, what is known, and the verdict.

| Area | State | Verdict |
| --- | --- | --- |
| **Kernel and XAM exports** | 261 `xboxkrnl` and 181 `xam` exports implemented. The hot ones are sync wrappers (row 7), file and content calls (small, below), and a 100 Hz voice thread (fixed). Online and Kinect code (`0x82A90000`-`0x82B40000`) is entered 13.2 M calls in a race, but 0.23-0.25 % of the Odin process, and most calls go to two shared helper leaves | Row 7 only. Stubbing the online range was rejected (not dead code) |
| **Threading and sync primitives** | One global recursive mutex stands in for interrupts-off sections. 1,001 of 1,062 reservation-only sections now skip it (render thread -0.36 ms). Contentions fell from 132-160 to 22-25 a frame. Object lookups under their own lock measured +0.22 ± 0.59 ms. Poll loops became blocking waits; the render idle sleep and wake variants are bounded at 0.1 ms. Fibers use host fibers | Closed. Rows 4, 6, 7 cover what is left |
| **Memory** | 4.5 GB file-backed arena with three views of a 512 MB physical heap; the 0xE0000000 offset select is gone on Windows. Write watches by page protection cost 0.25-0.29 ms a frame on the Odin (36-42 protects), 0.7 % of samples. Sparse shared memory is on by default and saves 290 MB on the Adreno 740. `MADV_PAGEOUT`, host-pointer import of the mirror and 2 MiB pages for the arena were rejected | Rows 2 and 9. Odin RSS is 1.1-1.27 GB and the Deck's 1.2-1.4 GB, with PSS 850-970 MB on both ([NN-0.4](NEAR_NATIVE_RESEARCH.md#progress)) |
| **File I/O and STFS/content** | Host path devices, case-insensitive lookup, STFS DLC through a container device, overlay for mods. A play session read 189 MB in 4,538 reads (91 ms) and 1,203 opens took 108 ms; loading is guest work (asset decompression, texture reloads), not disk. Path lookups under the lock caused the Android hitches and were moved off it ([#416](../site/pages/runtime.md#threads)) | Not a pool in play. Row 8 for loading. Zero host path misses a frame (NN-3.8) |
| **Audio** | XMA decoded by FFmpeg on a worker with lazy contexts and direct output (-0.17 ms, -112 MB heap). FMOD stereo on Android and Linux (-45 % mixer instructions), native ParamEQ (-0.14 ms) and native XAudio2 output (-0.49 ms pass, -0.23 ms worker). FMOD XMA codec on the host, the channel-matrix twin and native MPEG for radio were measured and dropped | Rows 1 and 3. XMA and XAudio2 are done |
| **Input, networking, achievements** | SDL3 gamepads over XInput exports, DualSense, achievements UI and sounds are host code already. Networking is stubbed; the online code runs but is not a cost. Polling four voice users was the one input-side cost and is skipped | No CPU or memory payoff. Features (online play) were dropped by the user (NL-6) |
| **PM4 decoder and recording** | 28.0 % of the Odin process inclusive (decoder 8.9 ms a frame, Deck about 9 + recorder 10 + submission 5 ms). About 20 per-draw steps of 90-360 ns. Rejected: replaying repeated buffers (G0: -2.5 ms against 6), decoder-level untile skip, parallel decode and record, owned draw programs, templates, a D3D-level renderer (-0.9 ms best), the native draw slice, constant blocks, a larger shader memo, write-watch re-arm skips | Closed. Only fewer draws move these threads; row 5 is the one safe leftover |
| **Xenos state, EDRAM, resolves, textures** | EDRAM and render targets are replaced by the native executor. Resolves 1.66 ms, transfers 0.77, clears 0.32, reloads 0.22 ms of the Odin's 11.8 ms frame. Copy-free resolves (FR-1) saved 0.83-0.87 ms on the Deck and 0.65 ± 0.88 ms on the Odin, under the 1 ms gate; skipping every resolve dispatch 0.15-0.28 ms. Texture loads are compute untile already; texture requests are 7.6 % of the Deck recorder | Closed. The texture cache's key derivation is still Xenia-derived, and texture requests are about 0.75 ms of the Deck recorder (*estimate*, 7.6 % of 10 ms); a memo exists (usage generation), so no candidate |
| **Shader translation** | Shaders are translated to SPIR-V once and stored; packs and AOT pipelines remove the first-run stalls (Odin translation 0.52 to 0.07 s; 711 shaders). The heaviest shader is 10.5 % of a UHD 620 frame and rewrites would keep the rasterization | Closed (hand rewrites rejected, #1070 item 4) |
| **Guest D3D** | About 22 % of the Deck's render thread is D3D command-buffer code. Native constant uploads matched on 27 M calls but saved 20 ns a call; the draw slice, display-list compiler and constant dedupe were rejected | Closed |
| **Guest libraries** | Native already: `memcpy`/`memmove`/`memset`, `pow`, LZX, the scene and instance culling. Rejected or counted: more CRT functions (0.02 % each), a heap allocator (0.05 %), SQLite (0.04-0.08 ms, indexes added instead), zlib. `printf` is 12 % of a minor thread (about 1 % of a core) and sits in row 4 | Closed apart from rows 4, 8 and 10 |
| **Animation and game logic** | Simulation thread outside physics is 5.3 ms on the Deck, flat; the interface update (40 % of it) runs every other frame on Linux. Crowds step at 30 Hz of real time. No native animation candidate has a measured pool | Rate gates (row 1) are the lever that worked; no native rewrite is proposed |

## Already done

Each of these is recorded as kept on the [Internals](../site/pages/internals.md)
pages or in the Progress tables of the linked research pages.

- **Guest code:** host-local register saves (NN-1.2) and link register
  (NN-1.3), fixed FP mode (NN-1.1), specialised physics functions (NN-5.1),
  direct `vmsum` (NN-1.7), single-entry functions through host fibers,
  small code model and x86-64-v3 on Linux (NN-1.8, -5.5 % process CPU on the
  Deck), huge-page code, symbol ordering on Android.
- **Native twins:** `memcpy` family, `pow`, LZX, FMOD ParamEQ, scene and
  instance culling (`pinyon_shift_native_scene_cull`, on for Linux), the
  XAudio2 output path, the voice-chat tick skip, the interface update rate.
- **Runtime:** reservation-only critical regions without the global lock
  (NN-3.1), PCR-based critical-section thread lookup (NN-3.2), import trace
  off, XMA worker decode (NL-4.1), lazy XMA state, game database indexes,
  sparse shared memory on the Adreno 740 (NN-6.1), surface rows on demand.
- **GPU:** executor-owned render targets and EDRAM, single-pass scene,
  compute texture loads, specialised resolve and transfer pipelines, AOT
  pipelines and shader packs, early untile skip (NN-2.1, -0.73 ms).
- **Threads:** thread pinning on the Deck (NN-3.14, -6 % CPU).

## Already rejected

The full table is [lessons: what didn't pay off](../site/pages/lessons.md#what-didnt-pay-off-here).
The ones most likely to be proposed again:

- A retained, owned renderer for the scene, world, shadows or whole frame
  (B4, B5, FR-3 to FR-6): about 5 ms of capped CPU ceiling on both devices
  against a 6-15 ms gate ([FULL_FRAME_RENDERER.md](FULL_FRAME_RENDERER.md),
  [BEYOND_RECOMP_RESEARCH.md](BEYOND_RECOMP_RESEARCH.md)).
- Occlusion culling of hidden draws, from a late depth grid or in the
  game's own pass culling (FR-3a, FR-3b, #784): the walk keeps a mesh any
  pass keeps; safe removal saved 0.6-1.4 ms of GPU at best.
- Copy-free resolves and fewer resolves or transfers (FR-1, NN-2.7).
- A D3D-level renderer, display-list compiler, replay of repeated buffers,
  draw programs, native draw slice, parallel decode and record (DL-1 to
  DL-3, G0, #753, #754, #1070).
- Native constant uploads, shader constants without repeats, a native
  scene walk past the culling, a tyre-only physics rewrite, AI-step
  intervals (#1071).
- Synchronous GPU submission, async fence completion, session replay and
  serial-execution oracles (NN-2.8, CS-0.1, CS-0.4, CS-1).
- Locks: object lookups under their own lock, write-watch protects under
  their own lock, a no-waiter condition-variable skip, a page cache for
  range checks, wake instead of idle sleep (NN-3.10, NN-2.4, NN-3.3, NN-3.4,
  NN-3.9).
- Stubbing the online range, native SQLite, native zlib, native movie
  decode, FMOD stage B as a whole, FMOD's XMA codec on the host, the
  channel-matrix twin, native MPEG for the radio.
- Memory: host import or dma-buf of the GPU mirror, `MADV_PAGEOUT`, 2 MiB
  pages for the arena, retirement as the default.
- Codegen: PGO, one-target direct calls, more registers in host registers,
  pinned context registers, non-volatile registers as locals, ThinLTO,
  stack symbolization, speculative indirect-call contracts, probe-ordered
  symbols on x86-64, `-mtune=znver2`, streaming stores.

## What this survey did not check

- The SDK's source was read for layout and cvars, not profiled; sizes of
  `src/kernel` (19.9 k lines), `src/audio`, `src/input` and `src/filesystem`
  are not a measure of cost.
- The Deck has no kernel-sample profile and no wake count; the Odin's
  threads are base-image numbers from 2026-10-13 and may have moved with
  the later v4 changes.
- Rows 1 to 4 may overlap with each other on the audio thread and the
  procedural thread; size them one at a time against the same in-run A/A.
- Nothing here touches `site/pages`: no behaviour changed. A kept or
  rejected row goes on the site when it is measured (see
  [CLAUDE.md](../CLAUDE.md)).
