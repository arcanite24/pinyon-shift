# Near-native research: CPU and memory on the handhelds

Researched 2026-10-13 at `dev` `d79f98c` (ShiftGlue `a361e38`). This page
answers one question: how close can Pinyon Shift get to the CPU and memory
cost of a native port, and which projects get it there?

It follows [NEXT_LEVEL_RESEARCH.md](NEXT_LEVEL_RESEARCH.md) (NL) and the
[performance backlog](PERFORMANCE_BACKLOG.md) without repeating them.
Nothing was built or run for this page. The numbers come from:

- the repository's recorded runs and perf CSVs, mostly the Odin NL runs of
  2026-10-12 and 2026-10-13;
- the probe build's call counts (`.local/re/probe/`), the generated tree
  and the Release objects;
- the SDK and Pinyon source;
- primary sources for other projects.

Every estimate is marked as one. Each proposal was checked by a premise
review and a feasibility review. Refuted proposals are in
[Considered and rejected](#considered-and-rejected); the corrections from
the others are folded into the estimates and gates below. Every
proposal and both reviews of it, with their arithmetic, are in
`10-proposals-and-verdicts.md` beside the research notes, and the
scripts and raw outputs behind them are under `scratch/`. The full
research notes are kept locally in
`.local/backlog-research/near-native-2026-10-13/`, which is not
committed.

The maintainer set the terms:

1. **Yardstick.** The Odin 2 Portal (Android) and the Steam Deck LCD
   (Linux): total CPU milliseconds per frame over all threads, plus
   resident memory (defined under the Odin memory table). The desktop is
   secondary.
2. **Fidelity.** Not bit-exact: a good-enough, playable experience,
   checked by frame and audio comparisons with the thresholds in
   [Verification](#verification) rather than by identical bytes.
3. **Scope.** Versions and platforms: "whatever is best". This page
   recommends one (see [Scope](#scope)).
4. **Size.** Large projects are in scope for this step.

Licences limit what we take:

- XenonRecomp, XenosRecomp, plume, N64Recomp, RT64, libultraship, Aurora
  and the Perfect Dark port (MIT), Xenia and its forks and Project8Recomp
  (BSD-3), OpenGOAL (ISC), FAudio (zlib), minimp3 (CC0): code with
  attribution.
- UnleashedRecomp, MarathonRecomp, Rayman Origins Recomp, PS2Recomp,
  N64ModernRuntime and Zelda64Recomp (GPL-3): ideas only.
- Projects without a licence (Ship of Harkinian, re3/reVC): ideas only.
- TiP-Recomp: its author does not consent to AI use of the work, so it
  was not analysed. Zelda64Recomp and Dusk (CC0) refuse generative-AI
  contributions; both were read at README level only and are used as
  ideas only.

## Why NEXT_LEVEL_RESEARCH was not enough

NL measured what it could count: guest-thread instructions on the Odin and
desktop frame time at the 120 limit. Its codegen items that deleted an
emulation structure held (NL-1.1 to NL-1.3: -22.6 % static instructions,
-22 to -35 % Odin guest-thread instructions), but the guest threads are
only about 60 % of the process. The rest is mostly the GPU and audio
hardware emulation (the PM4 decoder, recording, submission, the XMA
worker), which no codegen item touches. Its larger bets rested on
premises nobody had counted first: NL-1.4's static liveness model
predicted 13.9 % and every correct build was 20-27 % slower, because the
title is not ABI-clean (NL-0.1); NL-3.3's paged constants assumed
repeating constants that the census later showed churn. Several
"frame unchanged" verdicts were also read at the cap or on one stage of a
pipelined path, where a CPU saving does not show. This page uses the
maintainer's unit (CPU ms per frame on the handhelds), counts each premise
before ranking the item, and gates every large project on a cheap probe.

## Summary

- **Stage 0 is done (2026-10-13; [Progress](#progress)), NL-4.1 included:** no dropouts in either XMA mode, worker mode sounded right in play on the Odin, so NN-4.1 is built on worker mode, the SDK default since 2026-10-13 (`xma_decode_kicks_inline=false`). G0 failed:
  replaying repeating command buffers saved 2.5 ms of Odin process CPU
  against the 6 ms bar, and only 42-45 % of drawn draws sit in buffers a
  compiler could skip, so the display-list compiler (NN-2.3) is dropped
  and the decoder skip (NN-2.2) and the constant ABI (NN-2.6) go ahead.
  The Deck is GPU- and power-bound at 1x (GPU 17.2-17.9 ms, the APU at
  its 15 W limit). FP-mode writes are 65-70 % of the physics routine's
  cycles on all three devices, which makes NN-1.1 the first codegen item.
  Odin kernel time is 9 % of the process and the HLE sync syscalls stay
  under NN-3.13's bar. Emulation structure is about 3 ms of the Odin's
  15.7 ms GPU frame, and shared-memory uploads split the main scene into
  17-23 render passes. Resident memory counted once: about 1.93 GB on the
  Odin, 1.71 GB on the Deck. The rest of this page is the plan as
  written before Stage 0; the decisions below the Order list apply it.
- **About half of the Odin's CPU is overhead.** Of 38.8 ms of process CPU
  per frame in a 60 fps race (run `xa2`), 15.4-23.1 ms (40-60 %) is
  translation and emulation overhead (estimate). A native build would
  spend about 16-23 ms (estimate). The desktop share is higher, 51-71 %
  (estimate), because the decoder and recorder scale with its larger draw
  count. The Deck has no valid CPU measurement yet. Every baseline on this
  page is the base image, while new native work targets v4 (NN-0.6).
- **The biggest single pool is the GPU front end.** The Odin decoder
  (with inline recording) is 8.9 ms a frame, and about 1,400 of the draws
  it decodes each frame are then skipped by predicated tiling. Skipping
  them earlier, first in `IssueDrawImpl` and then in the decoder, saves
  2-3.5 ms on the Odin (estimate). A display-list compiler at the
  game's command-buffer seam is the only route to the rest (4.5-8 ms with
  the untile work, estimate). Its cheap gate (G0, a replay-floor probe and
  a draw-weighted census) now runs first, in Stage 0, before any M effort
  on the decoder skip that the compiler would make unnecessary.
- **Audio is the cheapest large pool.** FMOD mixes 5.1 and folds to
  stereo; its effects spend nearly all their time in six-channel loops.
  Forcing stereo, removing the XMA re-arm and decoding XMA frames
  directly save 1.5-2.2 ms (estimate) with small changes; native twins of
  the parametric EQ and matrix units add 0.95-1.9 ms (estimate), and
  replacing FMOD's XMA codec at its API boundary about 0.5 ms more
  (estimate).
- **Codegen has smaller, safer wins left.** Deleting save/restore helper
  calls with host-local saves, a fixed IEEE FP mode instead of per-site
  toggles, LR-slot deletion and shipped PGO add up to about 2-4.7 ms
  (estimate). They are build-level changes of 1-4 % each, so they are
  judged by per-thread instruction counts against a cross-build A/A, not
  by CPU time. Whole-program register promotion (IPA) nets only
  0.15-0.5 ms after spills and goes last.
- **The runtime has about ten small items** (lock-free single-reservation
  sections, TLS-free critical sections, symbol binding, trace flags,
  path and validation caches, futex wakes): 1.5-3 ms together
  (estimate), each a few days. Odin kernel time is unattributed today, so
  the syscall-heavy items wait for a profile with kernel samples.
- **Memory.** Retesting sparse binding on Turnip Gen8 V37 would return
  330-410 MB of KGSL device memory (estimate; it assumes a touched-page
  volume for the mirror that nobody has measured); lazy XMA contexts about
  148 MB of process heap (estimate). Retiring the 512 MB mirror by host
  import was refuted (no `external_memory_host` on Turnip).
- **The Odin's GPU is the next limit.** It takes 15.3 of the 16.7 ms
  frame, so on the Odin the CPU work buys power and heat headroom before
  frame rate. The last attribution left about 11.4 ms of GPU time with no
  geometry (resolves 3.6, transfers 1.3, the rest unnamed) and predates
  the latest renderer work; NN-0.11 measures it again, and decides whether
  the GPU gets a research pass of its own.
- **Scope: v4 first, Vulkan as the default everywhere, Odin and Deck
  first.** New native hooks target the v4 executable; base keeps the
  recompiled path and is not retired. The Deck needs its v4 build path
  (LX-3.4) and a first CPU measurement (LX-7.0) before anything is ranked
  for it. The Mac is out of scope for this step. The Astra and the Fold6
  are validation devices.
- **End state (estimate).** If the ranges hold and overlap as expected,
  the three stages remove about 10-20 ms of the Odin's 38.8 ms, leaving
  19-29 ms a frame against an estimated native 16-23 ms. RAM (unified
  memory on the handhelds) falls by about 0.45-0.55 GB: 0.33-0.41 GB of
  KGSL device memory and about 0.15 GB of process heap, counted
  separately because their overlap is unknown.
- **Measure first.** Stage 0 replaces the noisy single-run comparisons:
  an Odin call graph in the race with kernel time, a Deck LX-7.0 run, an
  in-run A/A harness and a cross-build A/A with known noise floors, a
  memory ledger, power samples, a v4 address map, and G0.

## Where the overhead is

### Odin 2 Portal (yardstick, 60 fps limit)

Snapdragon 8 Gen 2, Turnip V37, SMOOTH-60 cuts (1x, MSAA off, shadows off,
environment maps at a quarter rate, tiling once). Run `xa2`, 2026-10-13
(XMA decoded inline, the default), `simpleperf stat --per-thread` over the
race window, base image. `xa2` logged game mode 3 at race-ready,
race-moving and race-sustained. `xa1` (same configuration), which earlier
drafts used, logged game mode 17 at all three markers: it ran in free
roam, as did `b1`; every other NL run reached the race. Same-build runs
vary from 808 to 1,855 draws a frame.

| Thread or role | CPU ms per frame | Measured or estimate |
| --- | ---: | --- |
| Process | 38.80 (NL runs 33.2-41.3; fit 28.7 + 6.97 µs per draw, pooled over builds with different codegen) | measured |
| Decoder with inline recording | 8.92 (fit 1.73 + 5.17 µs per draw, pooled likewise) | measured |
| Submission | 3.08 CPU, 7.79 busy wall | measured |
| Guest render | 5.33 | measured |
| Guest simulation | 5.76 | measured |
| FMOD threads | 4.86 (mixer 4.46) | measured |
| Other guest threads | 6.73 | measured |
| Guest jobs | 1.33 | measured |
| XMA worker | 0.45 | measured |
| Host audio (Audio Worker 0.32, AudioTrack 0.24, SDLAudio 0.15) | 0.71 | measured |
| Pipeline compiles | 0.51 | measured |
| Other host threads | 1.15 | measured |
| GPU frame | 15.28 ms of 16.7 (NL runs 14.7-15.7) | measured |
| Draws | 1,396 a frame; drawn / skipped by untile about 1,450 / 1,400 in `race-1x` (2026-10-08 `runtime.log`) | measured |
| Global lock | 126-207 contentions, 0.55-1.28 ms blocked | measured (NL-4.3 runs) |

"Other guest threads" by thread (per-thread medians, so they do not add
to the role median): `82BAF5C8` CAudioThread, the game audio logic and
FMOD Event System, 2.39; `82E217A0` procedural geometry 1.47; `82589AE8`
presentation worker 1.23; `830C68B8` XAudio2 pass 0.59; `82E1C3E8` (role
unknown) 0.35; `829F6620` D3D tiling worker 0.23; `82463D60` XHV2 0.16.
This is the largest bucket without an item of its own; NN-4.4 and NN-4.5
touch two of its threads (the XAudio2 pass and XHV2).

"Decoder with inline recording" is decode plus record on one thread. The
decode/record split is off on Android: `SupportsRecordThread()` returns
whether texture descriptors are pushed (`vulkan/command_processor.h:408`),
and the Vulkan backend never pushes them on the Qualcomm vendor ID, which
Turnip reports too, because the Adreno driver left pushed textures
unreadable (`vulkan/command_processor.cpp:1343`). Every Android preset
still sets `gpu_record_thread = true`. No Turnip split A/B exists (device
ledger §10 #12).

| Memory | Size |
| --- | --- |
| Process resident (`process_resident_mb`) | 1,264 MB (NL runs 1,231-1,335) |
| Device memory (KGSL) | 1,200 MB (NL runs 1,180-1,204) |
| Executor surfaces | 247 MB |
| Texture cache | 167 MB |
| GPU shared-memory mirror | 512 MB, real RAM (not sparse on Turnip); derived from `shared_memory.cpp`, not measured |

**Memory yardstick.** The Odin and the Deck share one pool of RAM between
CPU and GPU, so the yardstick is RAM used, counted once: the process's PSS
(`smaps_rollup`), split into anonymous pages and clean file-backed pages
(which the kernel can drop and reload), plus KGSL device memory that is
not already mapped into the process. How much of the 1.2 GB of KGSL memory
the resident figure already counts is unknown (device ledger §10 #10);
NN-0.4 establishes it. Until then, KGSL and resident savings are reported
separately and never added.

| Overhead bucket | Arithmetic | ms per frame (estimate) |
| --- | --- | ---: |
| GPU front end | decoder 8.92 minus native recording at 0.6-1.0 µs a draw | 7.5-8.1 |
| Submission excess | 3.08 minus 0.5-1.0 | 2.1-2.6 |
| Guest bookkeeping | 24.01 ms of guest threads x 18-35 % | 4.3-8.4 |
| Polling, HLE sync, write-watch | low-density threads, lock contention | 1.5-4.0 |
| **Total** | | **15.4-23.1 (40-60 %)** |

The bookkeeping share comes from static counts (context traffic about
24 % of instructions, `bswap` 4.7 %, save/restore helpers 36 % of all
dynamic guest calls: 2.19 G of 6.15 G in the race probe; NL-2.3's 31 %
counted only the named save/restore pairs, about 1.9 G) weighted by
0.7-1.0, since those loads and stores hit L1. Native ports of `pow` and
LZX ran 1.8-2.2x faster than their translations, which agrees with
published PowerPC translators (half to two-thirds of native).

Measurement gaps: per-thread CPU time on the Odin is noisy from core
migration; `xa1`'s `simpleperf` missed nine late threads, and `xa2` was not
checked for the same; raw same-build spread is up to 23 %, 0.3-3.7 % after
normalizing by draws (draw normalization applies to the GPU threads, not
to guest threads). Every Odin call graph on record (cg2, cgsig, race5) was
taken pre-NL, mostly at the 30 fps limit, and with `simpleperf record
--in-app`, which records no kernel samples: syscall-heavy costs are
unattributed (cg2 shows `process_vm_readv` at 0.00 %, while on the desktop
the same validation through `VirtualQuery` was 13-30 % of the simulation
thread's busy samples). Track 01's `a3`/`b1` runs ran at 10 fps and are
invalid, and `nl-xma-b4` (the source of the desktop's 15.5 % runtime-layer
share) never reached the race.

### Steam Deck LCD (yardstick, Linux)

No valid CPU data exists. The CSVs on record were taken with the GPU
pinned at 200 MHz over SSH, and LX-7.0 has not run. What is known:

| Item | Value |
| --- | --- |
| Frame rate | holds 60 at 15 W with desktop defaults (tiled, shadows on), documented |
| GPU frame replay | 11.19 ms |
| Process CPU | about 50 ms a frame (estimate from an unsourced "about 38 % CPU" line in a session transcript, read as 3 of 8 logical CPUs) |
| Overhead share | 50-70 % (estimate, from the desktop split) |
| Resident | 1,211-1,437 MB (2026-10-09 CSVs and notes) |
| Device memory / surfaces | 804-812 MB / 256 MB |
| v4 build | none yet (LX-3.4) |
| Prior art | Project8Recomp (BSD-3, ReXGlue 0.10), Deck LCD: 48.9 ms of CPU a frame at about 2,665 draws, uncapped (derived from its CHANGELOG v0.3.0: 21.94 ms mean frame, 223.1 % process CPU); the only external Deck yardstick. FH1's race has 4,500-7,400 draws on the desktop path |

### Desktop (secondary: Ryzen 7 5800X, RTX 4080, race at the 120 limit)

Run `nl-base-1`: draws median 3,702 a frame (mean 3,931). The route
failed its simulation-time check (ratio 1.0817 against 0.95-1.08); its
frame data is still usable.

| Thread | CPU ms per frame |
| --- | ---: |
| Decoder | 7.49-7.76 |
| Recorder | 5.57-6.01 |
| Submission | 2.75 (busy, taken as CPU) |
| Guest threads | 15.7 (derived from sampler cycles at an effective 4.0 GHz) |
| Process | 32.5-33.5 (derived; no whole-process measurement exists) |

Resident 2.0-2.1 GB, VRAM 1.1 GB. The `WAIT_REG_MEM` yield spin
(1.9-2.0 ms) appears only on Windows above 61 fps. Overhead: 17-23 ms,
51-71 % (estimate).

### Validation devices (scale)

- **RedMagic Astra (8 Elite).** Thermally bound: 60 fps for about a
  minute, 37-39 fps at 40-44 °C skin, 26-28 fps above 44.5 °C. At the
  30 fps limit (v4) the process spends 62 ms of CPU per 33.3 ms frame,
  7.0 ms of it on submission. CPU and GPU share the SoC's power budget,
  so CPU milliseconds saved should buy GPU clock here; no power split is
  measured (NN-0.7). It holds the only v4 CPU data on record.
- **Z Fold6 (8 Gen 3).** The player's real v4 device (v4 APK, all DLC,
  the AppData save). No data of any kind.

## What native means, layer by layer

| Layer | Today | Native | Distance (Odin, estimate) |
| --- | --- | --- | --- |
| CPU code | Translated C++: registers written through to `ctx`, save/restore helper calls, `volatile` byte-swapped accesses, indirect dispatch, per-site FP mode toggles | The game's own code compiled with inlining and native vector code | guest code at about 1.5-2x native instructions; 4.3-8.4 ms of bookkeeping |
| GPU | The guest D3D runtime writes PM4; the host decodes it, re-derives every draw, records Vulkan, emulates EDRAM resolves and transfers, untiles predicated bins | The engine records Vulkan directly at 0.6-1.0 µs a draw; render targets live where the tiler wants them | 7.5-8.1 ms decoder, 2.1-2.6 ms submission; part of the 11.4 ms no-geometry GPU skeleton |
| Runtime, kernel, memory | HLE kernel objects behind one global lock, `mtmsrd` sections, guest polling, a 512 MB GPU mirror, write-watch page protection | OS events and atomics, memory sized to use | 1.5-4.0 ms; 512 MB mirror (derived); 148 MB of XMA contexts (estimate) |
| Audio and media | FMOD Ex runs translated at 5.1 and folds to stereo; XMA decoded through FFmpeg's API with per-packet re-arm; output hops through an emulated XAudio2 | Native stereo mixer and effects, direct decode, one output path | 4.86 ms FMOD + 0.45 XMA + 0.71 host audio + 0.59 XAudio2 pass; about 2.5-4 ms removable (estimate) |
| Libraries and game systems | Physics, SQLite, online code run translated; already native: `memcpy`/`memset`, `pow`, LZX | Native libraries | physics, collision and AI car simulation are about 11.5 % of process cycles (cg2, 30 fps, pre-NL; 86 % of the job workers; 19 functions make half of the workers' time), a large but unnamed pool; a pilot port gains 0.2-0.65 ms on top of NN-1.x. SQLite 0.04-0.08 ms |

The pattern from prior ports holds here: every large measured win in the
field came from replacing a platform seam (the graphics API, the audio
library), not from the CPU translator. FH1 is on the "recompilation plus
emulated platform" rung, with native pieces; every project on the next
rung (UnleashedRecomp, MarathonRecomp, Zelda64Recomp with RT64) got there
by replacing an SDK library family at its API.

## Proposed projects

Effort: S is days, M a week or two, L a month, XL a quarter or more.
Every saving is Odin CPU ms per frame and is an estimate unless marked
measured. A gate is the measured result a first prototype must reach to
continue. Every item keeps the project's correctness gates (save hash,
`expect-simulation-time`, route images, replays from pinned seeds) plus
the fidelity checks in [Verification](#verification). Each item that is
kept or rejected goes on the docs site in the same change.

How gates are read. Items behind a cvar are toggled inside one run and
judged against the in-run A/A (NN-0.3). Build-level items (NN-1.x,
NN-3.6) cannot be toggled in a run, and their effects (1-4 % of CPU) are
far below the 23 % raw spread between runs, so they are judged by
per-thread `simpleperf stat -e instructions` (cycles where the item
changes latency rather than instructions), with the simulation thread as
the scene-independent reference (one step a frame, the method that gave
NL-1.2 a clean verdict) and the cross-build A/A (NN-0.3) as the noise
band. Draw normalization applies only to the GPU threads. Where an
instruction gate is given, the CPU equivalent uses the measured
instruction-to-CPU elasticity of 0.52-0.6 (#467).

### NN-0 Measurement (do first)

| ID | Work | Why | Gate | Effort |
| --- | --- | --- | --- | --- |
| NN-0.1 | **Odin call graph at 60 in the race with kernel time**: current v4 build, game mode 3 confirmed in the log, `simpleperf record -g` on all threads from start. Kernel samples need `simpleperf` run outside `--in-app` with `perf_event_paranoid` lowered (`security.perf_harden 0`, root on some builds); if neither works, attribute syscalls with `--trace-offcpu`, per-thread schedstat and the syscall counters of NN-0.5 | Every Odin call graph on record is pre-NL, at 30 fps and without kernel samples; NN-2.4, NN-3.3, NN-3.4 and the HLE event sets are syscall costs nobody has seen on the Odin | per-thread totals within 5 % of `simpleperf stat`; kernel or off-CPU time attributed per thread | S |
| NN-0.2 | **Deck LX-7.0** launched from Steam (not over SSH), with the GPU clock checked during the run; per-thread `perf`, hwmon package power | No valid Deck CPU data exists | GPU clock unpinned, race reached | S |
| NN-0.3 | **Two A/A harnesses.** In-run: toggle a no-op cvar every 300 frames, normalize the GPU threads by draws, report a confidence interval, then a detector-power test with a known injected cost. Cross-build: install the same build twice under different package builds and run them alternately (at least three pairs), per-thread instructions and cycles | Raw spread is up to 23 %; most items below are 0.1-1 ms; build-level items cannot be toggled in a run | in-run interval within ±2 % and a 0.3 ms injected cost detected; cross-build band per thread known (target ±1 % instructions on the simulation thread) | S-M |
| NN-0.4 | **Memory ledger**: PSS by mapping (`/proc/<pid>/smaps_rollup` and `smaps`), anonymous vs clean file-backed, plus KGSL device memory by type, and which KGSL allocations the process also maps; Odin and Deck | Resident memory is half of the yardstick and has no breakdown on Android; the KGSL/RSS overlap is unknown; the 148 MB XMA-context and 512 MB mirror figures are not measured | every MB attributed to a region, overlap counted once | S |
| NN-0.5 | **Counter builds**: per-item event counters (lock sections taken, XMA `Set()` calls, untile-skipped draws, helper calls, futex wakes with no waiter, `process_vm_readv` calls, `SleepEx(0)` calls per site, write-watch faults) behind a cvar | Lets each item report its own count before and after | counts match the probe build | S |
| NN-0.6 | **v4 baseline and address map**: a v4 probe build, v4 NL-style Odin runs, and v4 addresses for every address cited in NN-2, NN-4 and NN-5 | Every baseline here is base (the NL runs' audio thread is `82FB4AF8`, v4 `83075D18`; the probe, the IPA analysis and cg2 are base); only the reverb (`830CE6C0`) and the biquad (`83087D70`) have v4 addresses | every cited address mapped or marked absent; v4 per-role CPU within the base runs' spread or explained | S-M |
| NN-0.7 | **Power samples**: battery current or a power rail on the Odin and the Astra during the race, with CPU and GPU clocks | The Astra shows CPU ms buy GPU clock under a shared power limit; nobody has measured how much | CPU/GPU power split per route | S |
| NN-0.8 | **Native twins as a calibration bench** (track 09 O1): for `pow`, LZX and three or four hot guest functions (a VMX audio routine, a physics routine, a scene walk), compare instructions, IPC and cycles native vs translated on the Deck and the Odin, then remove one overhead at a time in the translated twin (locals, no `volatile`, no swap, inlined helpers, no FP-mode writes) | Ranks the NN-1 items by measured cycles instead of static counts | each overhead's cycle share on both devices | S |
| NN-0.9 | **Hygiene: rename `rex::thread::TimerQueue`** to 15 characters or fewer | `pthread_setname_np` fails on the long name, so the thread inherits `SDLThread` and its CPU is unattributed on the Odin (dropped NN-3.7 guessed it at 0.45-0.56 %) | the timer thread named in `istat` | S |
| NN-0.10 | **NN-2.3's G0** (defined under NN-2.3): the replay-floor probe and the draw-weighted census, plus two probes: how `IDirect3DCommandBuffer` contents come to exist (write-watch the +116 chain at creation and log the writer's caller; track 02 unknown 1), and the constant-source conflict between `rendering.toml` lines 44 and 492 (one census says about 10 % of constants arrive as one 16-dword `LOAD_ALU_CONSTANT` matrix per draw, the other that the only `LOAD_ALU_CONSTANT` emitter loads static tables) | The GPU front end (7.5-8.1 ms plus 2.1-2.6 ms of submission excess) is the largest pool on the page; G0 is S-sized while NN-2.3 is 3-6 months, and NN-2.3 would make NN-2.2 unnecessary | G0 as defined under NN-2.3; both probes answered | S |
| NN-0.11 | **Odin GPU frame attribution** at the yardstick preset, live in the race on current `dev` (not the frame-600 replay, which runs tiled): split the GPU frame into the title's own passes and the emulation structure (resolves, transfers, EDRAM layout copies, Turnip drains between graphics and compute, untile duplicates), and re-measure the no-geometry skeleton | The Odin GPU is at 15.3 of 16.7 ms, so CPU saved there buys power and heat before frame rate; the last attribution (frame-600: about 11.4 ms with no geometry, of which resolves 3.6 and transfers 1.3) predates NL-3.2, NL-3.5 and untile on Android, and the rest of the skeleton is unnamed | every GPU ms a frame assigned to a pass family or to emulation structure, within 5 % of the frame's GPU time | S |

### NN-1 CPU code generation

| ID | Work | Why (overhead) | Estimate | Gate | Effort |
| --- | --- | --- | ---: | --- | --- |
| NN-1.1 | **Fixed IEEE FP mode.** Run guest code with FZ=0 (the host default) and drop the per-site toggles; separately, remove exactly the toggles triggered by pure moves (about 30 % of sites). Not FTZ/DAZ: 26,288 single-precision copy sites (`lfs` then `stfs`) risk integer punning under flush. A vector-only FTZ fallback is impossible. IEEE mode everywhere also stops VMX code from flushing denormals as the console does: on Zen 2 denormal operands can take microcode assists in reverb and IIR tails and in VMX physics (track 01 notes reverb denormal stalls). FP changes can make scripted routes diverge, which breaks between-build A/B on route position as well as image checks. | After #466 the residual toggle cost is about 5 % of render and simulation, about 0 of audio | 0.35-1.5 (central 0.8) | render and simulation instructions -3.5 % (about -2 % CPU) against the cross-build A/A; Deck audio and physics thread cycles not higher (`perf stat`); route images and SNR within the Verification thresholds | S |
| NN-1.2 | **Delete save/restore helper calls** with host-local saves under today's write-through `ctx` (helper classes G-H, M; no interprocedural analysis). This also deletes the guest-stack copies of saved registers, which hooks read (`r1+84`) and which the 13 entered intrinsic non-volatile readers or an unwinder may read. | 2.19 G helper calls at about 36 arm64 instructions each (78 G); cycle share render 6.1-13.3 %, simulation 5.7 %, jobs 9.7 %, other guest 6.1 %, audio 2.2 % | 1.2-1.6 | first: a census of host and hook readers of saved-register slots, each kept or given a host-side copy; then guest-thread instructions -7 % (about -4 % CPU) | M |
| NN-1.3 | **LR slot and back-chain store deletion** with `skip_lr` and a keep-LR list. Host readers of `ctx.lr` must stay correct: `title_waits.cpp` line 46, the ViewportAspect hook (#363), `Reenter` paths, `stall_dump`, M5 traces. 84 epilogues read the back chain and 86 functions reload r1. | Two stores per call on the hot path | 0.25-0.7 | poison build clean; guest-thread instructions -2 % | S-M |
| NN-1.4 | **Ship PGO** (instrumented, measured -2.2 % process instructions on the Odin). Shipping is a per-release device step: CI has no game, the profile is 21.7 MB against a 5 MB policy, and `llvm-profgen` needs branch records the Odin lacks. | Instruction-to-CPU elasticity measured 0.52-0.6 (#467) | 0.3-0.9 | process instructions -2 % against the cross-build A/A | M |
| NN-1.5 | **Guarded devirtualization** of monomorphic indirect sites, excluding targets that runtime `SetFunction` hooks replace (`CAudioEngine::Update` `0x82BB5918`, hooked as `UpdateRallyPace`; the input event `0x8269BCF8`). | Indirect dispatch cost on hot virtual calls | 0.05-0.3 | premise: probe counts confirm the sites are monomorphic; result: instructions -0.5 % on the threads that own the sites | M |
| NN-1.6 | **Dead dispatch stores**: two stores per call on the hot path that nothing reads | small, free | 0.05-0.25 | static count of stores removed (`llvm-objdump` over the Release `libmain`; a counter build cannot count stores that no longer exist); then guest instructions -0.5 % | S |
| NN-1.7 | **Exact SIMD `vmsum`** (PB-3.7), keeping FH1's comparison results | 1-5 % of simulation, workers and render | 0.1-0.6 | `reference_verify` exact | S-M |
| NN-1.8 | **Deck code model and ISA**: the Linux preset uses `-mcmodel=large` plus `--no-relax`, which makes every call register-indirect; 75 MB of text fits the small model. Also x86-64-v3 (the Linux preset is SSE4.1, so `fma` is a libm call). | Every call on the Deck pays an indirect branch | unknown until NN-0.2 | Deck per-thread cycles -3 % against the cross-build A/A | S-M |
| NN-1.9 | **Symbol ordering file** from the probe build (hot together, never-entered last; 52.6 % of statements are never entered). ThinLTO on arm64 stays unmeasured; BOLT is absent from the toolchain and the NDK. | i-cache and iTLB on a 53.8 MB `.text`; the cheap layout lever | 0-0.3; RSS -10 to -25 MB | PSS -10 MB on the Odin | S |
| NN-1.10 | **IPA register model** (last). Net `ctx` gain after spills is small: spill clawback 40-68 % on arm64, 60-75 % on Win64, 85 % or a net loss on Deck SysV. Fixed sets give 16,671-50,892 functions with non-volatile live-in; the class file is unsound (1,273 sites outside the slot union) and 862 functions need clobber-everything. Register passing (stage B) fits only 11.7-16.8 % of entries and is dropped. | NL-1.4 lost 20-27 % for lack of exactly this precision | 0.15-0.5 | compile census of the top 200 functions with spills shows 3 % or more beyond NN-1.2 | XL |
| NN-1.11 | **armv8.2-a guest code on the handhelds**, the arm64 counterpart of NN-1.8. The Android and macOS presets set `PINYON_SHIFT_CPU_BASELINE=armv8-a`, and the SDK compiles every target, `libmain` included, with `-march=armv8-a` (`rexglue_helpers.cmake:55`): `stwcx.` becomes an LL/SC loop or an outline-atomic call, and acquire loads cannot use RCpc. The Odin, the 8 Elite and the Fold6 are all ARMv8.2 or later; the APK is built per device. NN-3.6 covers LSE for the runtime libraries only. | LL/SC loops and outline-atomic calls on guest reservation code | unknown until counted | first: static count of LL/SC loops and `__aarch64_*` outline-atomic calls in `libmain`; then per-thread cycles -1 % against the cross-build A/A | S-M |
| NN-1.12 | **Fixed host registers for `ctx` and `base` on AArch64** (`-ffixed-xN` with named register variables; x19-x28 are callee-saved, so foreign code preserves them). Feasibility unknown: every entry from host code into guest code must set them. | ctx/base argument copies are 6.5-7.1 % of static and 1.1-3.5 % of executed instructions (track 01) | 0.15-0.5 (estimate) | first: a twin in NN-0.8 with the registers pinned; then guest instructions -1 % | M |

### NN-2 GPU front end

| ID | Work | Why (overhead) | Estimate | Gate | Effort |
| --- | --- | --- | ---: | --- | --- |
| NN-2.1 | **Early untile skip in `IssueDrawImpl`**, right after the `kCopy` dispatch, carrying the tiling pass in the draw record | About 1,400 draws a frame are derived in full and then skipped | 0.8-1.8 | decoder -0.8 ms per frame, draw-normalized, in-run | S |
| NN-2.2 | **Decoder-level skip** of the later tiles' bin-predicated object packets. Only if G0 fails: NN-2.3 removes the decode it would skip. | Removes parsing as well as derivation for skipped bins | Odin 2-3.5 in total with NN-2.1; Deck 2.5-4.5; desktop/Deck 15-20 % of decoder+recorder when tiled | live same-frame capture identical in all bins | M |
| NN-2.3 | **Display-list compiler** at the game's `IDirect3DCommandBuffer` seam (`82416A00`): compile each list once, re-execute with constants read by address. List identity comes from a host tag in the guest's own command language, a PM4 type-3 NOP naming the list object and its recording count (the RT64, libultraship and Aurora pattern, track 08 T2), not from hashing dwords. Must cover the other draw emitters (`82416380` and `82415F68`, about 540 draws a frame against 35 through `8240F4D8`; also `82460998`, `82408B70`, `8240DC70`), the second producer thread `82589AE8` and the second IB producer `8246FB98`. `824168B0` is the generic constant flush and stays guest. Use a mid-asm hook at `0x82416EFC`, not a native body. Only 49-58 % (DR-0.3) to 70-89 % of draws are in repeating buffers, and the constant-source conflict (NN-0.10) is unresolved. | The decoder and recording are the largest single overhead; DR-4.2's replay was about 3,200 against 3,300 cycles a draw, so per-draw replay is not the shape; Turnip submission measured 2.26 µs a draw | own share 1.5-5 (central 3-3.5); with NN-2.1/2.2 4.5-8; desktop 8-11 | **G0** (Stage 0, NN-0.10). Probe: re-run each IB range whose bytes match the previous frame from its cached host command buffer (re-executed secondaries), with no decode and no validity checks; a wrong image is allowed. It is the Odin, CPU-total version of DR-4.2's desktop ceiling probe (recorder 10.4 to 3.7 ms). Metric: Odin decoder + submission CPU ms per frame, counting drawn draws only. Configuration: untiled Odin preset (SMOOTH-60 cuts, tiling once, 1x), `fh1-race-sustained` from a pinned seed. Baseline: the same build with the probe cvar off, toggled every 300 frames (NN-0.3). Pass: at least 6 ms below the baseline (3 ms beyond NN-2.1/2.2's estimated 2-3.5 ms), and the draw-weighted census puts at least 80-85 % of drawn draws in repeating lists | XL (3-6 months) |
| NN-2.4 | **Watch flags under their own lock** | 6-12 ms `mprotect` hitches under the global lock; the `mprotect` cost itself is kernel time the Odin profiles cannot see (NN-0.1) | hitch removal, not ms/frame | frames over 25 ms -50 % and p99 frame time not worse, in-run | S |
| NN-2.5 | **Shader pack** (AP-6.3) through the existing `Fh1ShaderPack` loader. `VkPipelineCache` and SPIR-V packs cannot be shipped. | Warm start | -0.34 s Odin warm start | measured start time | S |
| NN-2.6 | **Constant ABI**: delta-refresh persistent constant blocks. Only if G0 fails; a new register-file ABI only with NN-2.3. Persistent blocks were measured +16 ns a draw before (DR-4.2), so this needs the delta form. | Per-draw constant gather | 0.05-0.5 | Odin decoder µs per drawn draw -5 % in-run; desktop recorder -50 ns a draw | M |
| NN-2.7 | **Role images** for render targets (the base-0 depth 1x/4x alias is live; transfers come from shadows). Yardstick effect: executor surfaces 247 MB to an estimated 40-80 MB at 1x (track 02), and the recorder's transfer work (57 transfers and about 11,300 tile passes a frame in `race-1x`). Track 02 estimated 3-4 ms of Odin GPU from removing transfers (1.3-1.7 ms) and most compute resolves (3.1-3.6 ms); the reviews cut that to 0.4-1.0 ms: Odin transfers are about 1 ms and mostly the live depth alias copy, transfers come from sun shadows (which the yardstick preset turns off), and the resolve bounds are measured (about 2.4 ms of dispatches, 0.4 ms of it fixed). Confirm it with a GPU profile at the yardstick preset before ranking. | GPU time and surfaces memory; CPU only through transfers | 0.4-1.0 GPU ms; surfaces -170 to -200 MB (estimate) | frame replay GPU -0.4 ms and surfaces 120 MB or less | XL |
| NN-2.8 | **Synchronous submission on Android, re-tested on CPU total.** Recording is already inline on the decoder there, yet submission costs 3.08 ms of CPU (2.1-2.6 ms above native, estimate). NP-9.2 rejected synchronous submission on desktop frame time (21.05-21.19 against 19.25-20.32 ms overlapped) when recording was on the same thread; the yardstick is now CPU total, and on Android there is no tape to replay. | Thread hand-off, wakeups and per-submit work | 0.3-1.0 (estimate) | process CPU -0.5 ms in-run with p99 frame time not worse | S |

### NN-3 Runtime and kernel

| ID | Work | Why (overhead) | Estimate | Gate | Effort |
| --- | --- | --- | ---: | --- | --- |
| NN-3.1 | **Lock-free single-reservation sections**: 1,061 of the 1,062 `mtmsrd` sections are one `lwarx`/`stwcx.` pair; emit them without the global lock, keeping `guest_depth_`. `sub_8314D1F0` stays locked. Check ABA against the interrupt callback's plain stores. | 126-207 lock contentions a frame | 0.44-0.85 | contentions -50 %; chaos-timing route clean | S-M |
| NN-3.2 | **RTL critical sections read the current thread from the PCR `host_stash`**, not TLS | TLS lookup on every enter | 0.15-0.32 | TLS lookups per frame -90 % (counter); render and simulation instructions -0.5 % | S |
| NN-3.3 | **Skip the futex broadcast with no waiter** (Android) | syscall per release; kernel time unattributed on the Odin today | 0.09-0.32 | futex syscalls per frame -50 % (counter); off-CPU or kernel time on the releasing threads lower (NN-0.1 method) | S |
| NN-3.4 | **Hook validation page cache**: geometry validators call `PinyonShiftGuestRangeReadable` per access (`pinyon_shift_runtime_hooks.cpp`, around lines 7504 and 8738), one `process_vm_readv` syscall a page on Android; use a thread-local page cache as `dlc_treasure_map.cpp` does | desktop race 0.5-1.3 ms measured (`VirtualQuery` 13-30 % of the simulation thread's busy samples); Odin invisible in `--in-app` profiles | Odin unmeasured | first: `process_vm_readv` calls per frame on the Odin (counter); desktop -0.5 ms | S |
| NN-3.5 | **Import trace flag off in release**: `REX_TRACE_IMPORT_REACH` does a `test_and_set` on every hooked import because `PINYON_SHIFT_TRACE_IMPORTS` defaults on | 0.35-0.42 % of process | about 0.13 | flag off, count 0 | S |
| NN-3.6 | **Symbol binding and atomics**: `-Bsymbolic-functions` on `librexruntime`/`librexgpu` (5,273 of 5,747 jump slots are self-defined), `armv8.2-a+lse` behind a HWCAP check, inline `tzcnt` and atomics. Precedent: the same flag took `libmain`'s PLT stubs from 1.6 % to 0.1 % of process cycles (`CMakeLists.txt:99`, PB-3.12, `site/pages/recompiler.md`). The new premise is the runtime libraries' PLT, still 0.5-2.5 % per thread (`scratch/challenge-staticlink-premise/perthread.txt`). | PLT indirection and LL/SC loops | 0.25-0.55 | PLT stubs below 0.2 % of the GPU Commands and Submission threads' samples; their instructions -1 % against the cross-build A/A | S |
| NN-3.7 | ~~`KeTimeStampBundle` 1 kHz timer~~ **Dropped 2026-10-13: the premise failed.** The title reads the bundle through its `GetTickCount` (`sub_823F18B8`): about 1.03 M calls in a desktop race, FMOD's among them, so refreshing it less often would change what they see (`site/findings/threads.toml`, "GetTickCount reads KeTimeStampBundle"). | — | — | — | — |
| NN-3.8 | **Negative lookup cache** in `HostPathDevice::ResolvePath` | repeated failed opens | 0.07-0.12 | failed lookups per frame -90 % (counter) | S |
| NN-3.9 | **Render-idle producer wake** | wake latency spins | 0.1-0.27 | decoder + render thread CPU -0.1 ms in-run, p99 not worse | S |
| NN-3.10 | **User-space headers for L-size objects** | beyond NN-3.1 | 0.07-0.15 | after NN-3.1: global-lock acquisitions from object headers -50 % (counter), contentions not above NN-3.1's level | M |
| NN-3.11 | ~~The five remaining `SleepEx(0, TRUE)` spinners~~ **Dropped 2026-10-13: counted, too small.** With the render thread's idle path replaced, the guest `SleepEx` runs 234 times a second in all in a desktop race, `sub_82D18588` never runs, and none of the five spinners takes more than 0.01 % of the Odin process (`site/findings/threads.toml`, "SleepEx wrapper and its spinners"). | — | — | — | — |
| NN-3.12 | **Explicit dirty marking for upload paths** the title uses every frame, from a hook instead of a write-watch fault; faults stay as the fallback (track 03 #3) | 7 faults and 23 `mprotect` calls a frame at 5-10 µs each, serialised under the global lock | 0.2-0.4 | write-watch faults per frame -50 % (counter); route images within thresholds | M |
| NN-3.13 | **User-space kernel objects, full version** (track 03 #1; reopens NL-4.3 on running cost): event, semaphore and mutant state as atomics in the guest dispatcher header, wake only with a registered waiter, cached host object pointer so `KeSetEvent` skips `ObjectTable::LookupObject` and the global lock. NN-3.3 and NN-3.10 are its cheap subsets. | `NtSetEvent` was about 4.9 % of desktop guest running time; unmeasured on the Odin | 0.7-1.5 including NN-3.3/3.10 (estimate) | only if NN-0.1 shows HLE sync syscalls at 0.5 ms a frame or more; then guest-thread CPU -2 % in-run | M-L |
| NN-3.14 | **Deck thread placement** (LX-7.3): simulation, render, audio, decoder and submission on distinct physical cores, jobs on the SMT siblings | 4 cores and 8 threads under a shared 15 W limit | unknown (guess 0-8 % of CPU-bound frames) | after NN-0.2: Deck process CPU -3 % and p99 not worse | S-M |

### NN-4 Audio and media

| ID | Work | Why (overhead) | Estimate | Gate | Effort |
| --- | --- | --- | ---: | --- | --- |
| NN-4.1 | **XMA**: no `Set()` in inline mode (`Work()` clears `is_enabled` and only a kick re-enables it); decode XMA frames directly, bypassing the FFmpeg API wrapper (about 40 % of decode); reuse decoders through a flush patch or initialize only XMA's MDCT sizes; allocate the 320 contexts lazily (about 461 KB each from the field sizes, zero-filled; derived, not measured, NN-0.4 measures it). Baseline: inline mode, the default until 2026-10-13 and the mode of `xa2`. Worker mode is measured on the same routes: `xb1` against `xa1` audio -1.05 ms and XMA +0.32; `xb2` against `xa2` audio -0.80 and XMA +0.60, so audio plus XMA net -0.2 to -0.73 ms; NL-4.1 measured about -0.2 G instructions a second for the process. NL-4.1 chose worker mode, and the SDK made it the default on 2026-10-13, so the `Set()` removal does not apply; the rest does. | XMA register handling and decode were 22 % of the audio thread | 0.85-0.9 against inline; memory about -148 MB of process heap | per-call SNR within thresholds; XMA `Set()` calls per frame -90 % (counter); PSS -100 MB | S |
| NN-4.2 | **FMOD stereo**: override `sub_82F86498` to call `setSpeakerMode(2)` through `sub_82F86298`/`sub_82F904E8` first. The constructor `sub_82F90A00` defaults to 5.1 (six channels); ParamEQ, echo and HP/LP spend 98 % of their time in the six-channel loops. The stereo fold must become a passthrough. | About two-thirds of the effect work is for channels that are folded away (estimate) | 0.6-1.3 (central 1.0-1.2) | restart pairs (an init-only change), FMOD threads -12 %; listening test | S |
| NN-4.3 | **Native DSP twins**, ParamEQ (`sub_82FC6CC0`) and the matrix units (`sub_82FAE0B8`, `sub_82FAB740`) first; not the reverb (partly VMX and delay-line bound). Units go in `host_overridden_functions`. Gate on time, not instructions: NL-1.1 cut FMOD-thread instructions 35 % for 5 % CPU. Allowed by [LEGAL.md](LEGAL.md#native-replacements-of-game-and-library-code) as written: each unit implements the contract of FMOD Ex's documented parameters (ParamEQ: centre, bandwidth, gain) with a published filter design (a peaking-EQ biquad) and standard matrix mixing; coefficients come from the parameters, never from the executable, and differences from the translated unit are accepted within the audio thresholds. | ParamEQ and matrix are the concentrated part of the mixer | 0.95-1.9 | guest_native tolerance verify; per-call SNR within thresholds; FMOD thread -10 % CPU per unit | M |
| NN-4.4 | **Output hop**: emulate FMOD's XAudio2 source voice natively and idle the pump in gameplay, after a census of other engine users: XHV2 (thread `82463D60`, 18 voice creates), four unattributed creates, and the movie glue `sub_82E5DB08` | The XAudio2 pass (0.59 ms) and the audio worker (0.32 ms) run every frame | 0.45-0.9 if nothing else needs the engine, else 0.1-0.15 | census first; then XAudio2 pass and Audio Worker CPU -80 % in-run | M |
| NN-4.5 | **Stub the XHV2 100 Hz thread** (voice chat, unused offline) | wakeups; the thread measured 0.16 ms a frame in `xa2` | 0.06-0.16 | thread wakeups and CPU to about 0 | S |
| NN-4.6 | **Radio MP3 at FMOD's codec read** (`sub_82FD4890`, descriptor `sub_82FD5850`) through the FFmpeg `mp3float` decoder already linked | translated MP3 decode; its cost with a station playing is unmeasured (with the radio off, the probe's race still entered the codec read 1,963 times, most likely for voice-over; the Odin race profile has no samples in it) | 0.1-0.5 with the radio on (guess) | first: a radio-on Odin measurement from a seed with a station on; continue if MPEG decode is 0.2 ms a frame or more; then per-call SNR | M |
| NN-4.7 | **Press Start render-thread loop** (about 980 ms of CPU a second) | battery and heat at the title screen | not on the yardstick | first: a call-graph sample at Press Start names the loop; then render-thread CPU there below 250 ms a second | S |
| NN-4.8 | **FMOD's XMA codec at its API boundary** (around `sub_83002C20`/`sub_82FFB3F8`): a host XMA decoder writes into FMOD's buffer, with no contexts, registers, worker or ring (track 04 #4) | the rest of the XMA emulation, 3-5 % of process cycles on the cg2 basis (about 2 % more once NN-4.1 is in) | about 0.5-0.6 beyond NN-4.1 (estimate) | XMA worker CPU about 0; audio thread -5 % in-run; per-call SNR within thresholds | M |

### NN-5 Game systems and libraries

| ID | Work | Why (overhead) | Estimate | Gate | Effort |
| --- | --- | --- | ---: | --- | --- |
| NN-5.1 | **Physics specialised at build time**, pilot `sub_82D2F348` and `sub_82D21DB0`. [LEGAL.md](LEGAL.md#native-replacements-of-game-and-library-code) rules out committing hand translations of game logic, so the native form is generated from the player's executable: per-function generator options for the family (register locals inside the function, host-order temporaries for non-escaping data, single-precision and vector lowering where the guest code is single precision), compared with today's translation by tolerance verify. A hand-written native version is allowed only for a function whose contract can be specified from our own analysis (a standard integrator or collision primitive), not for unnamed logic. The family is 131 functions, 117 unnamed; the expected MLP kernel does not exist; the RacingAI job runs in bursts. | The pool is about 11.5 % of process cycles (cg2, 30 fps, pre-NL; about 6.5 ms per 30 fps frame, estimate), 86 % of the job workers; native leaves ran 1.8-2.2x | 0.2-0.65 steady for the pilot, on top of NN-1.x (not the pool's size) | pilot gains at least 0.1 ms; determinism checks in Verification | XL |
| NN-5.2 | **SpeechFacade idle**: keep the library (8.1 MB packaged, 16.8 MB unstripped in the build tree) from loading or running in gameplay; guest thread `82ADA220` requests the load and no samples fall in its code | memory | RSS only | PSS -8 MB (smaps) | S |

### NN-6 Memory

These run alongside the stages in [Order](#order). Each reports KGSL
device memory and process PSS separately (see the memory yardstick).

| ID | Work | Estimate | Gate | Effort |
| --- | --- | --- | --- | --- |
| NN-6.1 | **Turnip sparse retest on Gen8 V37.** Sparse binding was disabled in `cd5c76c` on `turnip-r8` because resolves written into the sparse shared memory read back as zeros (`vulkan/shared_memory.cpp`); never root-caused. Turnip's sparse support depends on the KGSL backend, so the kernel matters as much as the driver. | KGSL device memory -330 to -410 MB (estimate: assumes the mirror's touched-page volume, which nobody has measured, track 02 unknown 8) | first: a minimal sparse bind, resolve-write and readback test on the Odin's Gen8 V37 and kernel; only then route images through it; result: KGSL -300 MB measured, validation clean, route images within thresholds | S-M |
| NN-6.2 | Lazy XMA contexts (part of NN-4.1) | about -148 MB process heap (estimate) | PSS | S |
| NN-6.3 | Hot/cold ordering (NN-1.9) and SpeechFacade idle (NN-5.2) | -10 to -40 MB PSS | smaps | S |
| NN-6.4 | **Executor surfaces on the Odin**: measure `fh1_surface_rows_on_demand` (NL-3.5) on and off; never measured on Android, and the Odin's 247 MB has not moved across the NL runs | unknown | surfaces MB on vs off | S |
| NN-6.5 | **Textures held once**: guest physical copies of GPU resources plus host Vulkan copies of the same data, in the same RAM on the handhelds (track 03, 150-300 MB, estimate). Pairs with NN-2.3 (textures at creation). | -150 to -300 MB (estimate) | PSS + KGSL -100 MB | L |
| NN-6.6 | **`MADV_COLD` on guest pages backing GPU resources** that are never rewritten, so Android's zram can take them (track 03 #10) | 100-250 MB of RSS (guess) | PSS -100 MB with no refault stalls (frames over 25 ms not higher) | S-M |
| NN-6.7 | **Release the 14.7 MB of dead guest `.text`** after a no-access trial survives the route matrix (track 03 #12) | up to -14.7 MB | the trial runs clean; PSS -14 MB | S |

### Considered and rejected

| Proposal | Why rejected |
| --- | --- |
| Stack symbolization (P2) as an L project | Only 29-39 % of slots are promotable against its own 60 % gate; the 83 % figure came from one function; hooks read `r1+84` |
| Retiring the GPU mirror by host import, UMA dma-buf or zero-copy | Turnip and Qualcomm have no `external_memory_host`; fences are written at decode and record time with three frames in flight, so sharing tears; an import pins all 512 MB; RADV `userptr` rejects `memfd` |
| Hooks on polling loops | E1 already fixed `CTransferManager`; the remaining waits are `INFINITE`; the fence spin measured no difference; `82DBB740` is absent from the Odin profile. The five `SleepEx(0, TRUE)` spinners were counted separately and are too small (NN-3.11) |
| Restructuring the tiler's passes | 93-102 renderings a frame, about 31.5 ended by resolves; the upload hoist gave no gain on replay; the depth alias view cannot be built; compute cube mips were tried before |
| Desktop untile as is | Decoder and recorder neutral on the desktop: decoder 7.73 to 7.83 ms, recorder 4.68-4.80 to 4.67 ms, submission 2.42-2.50 to 2.10 ms (one run each at the 120 limit, 2026-10-08, `D:/horizon1-recomp-tests/desktop/ab-1-*`, Pinyon `3f8cd4c`, SDK `9187b27`); on the Odin `ut-1x`/`ut-4x` cost 0.5-1.6 ms more CPU for GPU 27.1-27.5 → 24.1 ms |
| Stubbing the online range `82A90000`-`82B40000` | Not dead: 310 functions entered, 13.2 M calls |
| Native movie (WMV) decode for the yardstick | 164-195 ms of CPU a second at Press Start only; 60 fps holds there; 0 in the race |
| Native zlib; native SQLite | zlib already rejected; SQLite 0.04-0.08 ms |
| BOLT on Android | absent from the toolchain and the NDK |
| `-Os` cold tier | only -2.4 to -4.9 MB of `.text` |
| Interrupts outside the global lock | risky for about 0 CPU |
| FMOD stage B (whole-mixer replacement) | the concentrated units are covered by NN-4.2/4.3/4.8 at far lower risk |
| IPA stage B (register passing) | fits 11.7-16.8 % of entries |
| Retiring the base executable | players must supply the title update themselves (LEGAL.md forbids distributing it), base stays the default by the maintainer's TU-5 decision ([TITLE_UPDATE_V4_BACKLOG.md](TITLE_UPDATE_V4_BACKLOG.md)), and the v4 media ID (`4000D145`) differs from the USA disc (`2DC7007B`) |
| Frame-rate decoupling with interpolated frames (RT64, Ship of Harkinian) | the LOW_SPEC_BACKLOG "Not to build" decision (no simulation below the source rate with interpolated frames; frame generation is planned as an opt-in on a steady base rate, #523-#526). Reopen only if the maintainer agrees |
| Byte-swapped or reversed guest memory | every host component that touches guest memory (GPU texture and vertex paths, XMA, file I/O, kernel structures, CRT overrides) would have to address it reversed, and word swizzling breaks unaligned word accesses; endian overhead is bounded at about 5-14 % by the Bi-Endian Compiler data and is about 5 % statically here (tracks 01, 08, 09) |
| Engine-level scene renderer (skate3recomp's route) | the Xenos-era six-family pilot needed 153 guest hooks, broke on a different event and ran 91-95 ms frames against 23.5 ms; the list compiler gets most of the CPU gain with generic code (track 02 §8) |
| D3D draw-call HLE only (UnleashedRecomp's route) | sees 42 draws a frame unless lists are recorded through D3D at run time; if they are, it becomes NN-2.3 done at list creation (track 02 §8, decided by NN-0.10's provenance probe) |

## Scope

- **Versions: v4 first for new native hooks.** The reference save,
  Rally and the 1000 Club run on v4, and every native replacement needs
  its addresses per executable; the v4 fiber regression showed the cost of
  byte-matched addresses. Choosing v4 saves about 10-25 % per
  function-level unit, about 50 % only for struct-heavy work, and nothing
  for codegen items, which apply to both (estimate). Base keeps the
  recompiled path and is not retired (see the rejected table). Every
  measurement on this page is from base runs, so NN-0.6 re-bases them.
- **Renderer: Vulkan is the default everywhere.** The D3D12 backend is
  still in the SDK (`src/graphics/d3d12`; only the configuration was
  migrated away from it). Nothing here targets it, and every NN-2 item
  would otherwise need a second backend, so retire it once NN-2.3 lands.
- **Platforms: Android arm64 (Odin) and Linux (Deck) first.** The desktop
  is secondary and usually gains more from the same GPU front-end work.
- **The Mac is out of scope for this step.** It does not follow for free:
  macOS arm64 has 16 KB pages, so the physical-view offset survives there,
  the NL-1.1 select is still generated, and NL-1.6 step 1 matters only
  there (NEXT_LEVEL_RESEARCH, NL-1.6 row). It needs its own measurement
  and items after the yardstick work.
- **Validation devices:** the Astra (8 Elite, thermally bound, the only v4
  CPU data) and the Fold6 (the player's real v4 device, no data yet) check
  each stage's result after the Odin.
- **Deck prerequisites:** a v4 build path (LX-3.4) and LX-7.0 (NN-0.2)
  before any Deck-specific item is ranked.

## Order

1. **Stage 0, measurement and decisions (S, parallel): NN-0.1 to
   NN-0.11, and the NL-4.1 listening test (decides NN-4.1's mode).**
   Go/no-go: the in-run A/A reaches ±2 % and detects a 0.3 ms injected
   cost, and the cross-build A/A band is known; otherwise items under
   0.5 ms are judged by counters only. G0 decides between NN-2.3 and the
   NN-2.2/NN-2.6 path. NN-0.11 decides whether a GPU research pass (this
   page's method, with Odin GPU ms a frame as the unit) runs before
   Stage 2: it does if emulation structure is 2 ms or more of the GPU
   frame.
   **Stage 0 decisions (2026-10-13).** The in-run A/A reaches ±1.8 % of
   process CPU but does not detect a 0.3 ms cost in one run (+0.22 ±
   0.43 ms), so items under 0.5 ms are judged by their counters, by
   about eight pooled runs, or by per-thread instructions. G0 failed:
   NN-2.2 and NN-2.6 go ahead in Stage 2, and NN-2.3 and NN-6.5 (which
   depends on it) are dropped. Emulation structure is about 3 ms of the
   Odin GPU frame, over the 2 ms bar, so the GPU research pass runs
   before Stage 2; the upload-split main scene is its first question.
   NN-0.1 found the HLE sync syscalls under 0.5 ms a frame, so NN-3.13
   is not pursued. NN-0.8 puts NN-1.1 (FP mode) first among the codegen
   items and shows register locals losing on call-heavy functions, which
   NN-1.10 must model. The Deck is GPU-bound at 1x, so Deck CPU items
   (NN-1.8, NN-3.14) are judged by power and frame-time tails there, not
   by frame rate.
2. **Stage 1, S items (parallel), about 4-8 ms on the Odin (estimate,
   not simply additive):** NN-4.1, NN-3.5, NN-3.6, NN-4.2, NN-3.1, NN-3.2,
   NN-3.3, NN-3.4, NN-3.8, NN-3.9, NN-1.1, NN-2.1,
   NN-2.4, NN-2.8, NN-6.1, NN-2.5, NN-1.6, NN-1.9, NN-1.11, NN-4.5,
   NN-4.7, NN-5.2, NN-6.4, NN-6.7. Each is kept only if it clears its A/A
   band.
3. **Stage 2, M items, about 4-8 ms more (estimate; about 1-2 ms less if
   G0 passes and NN-2.2 is skipped, since NN-2.3 then covers it):**
   NN-2.2 and NN-2.6 (only if G0 fails), NN-1.2, NN-1.3, NN-4.3, NN-4.4 (after its census), NN-4.8, NN-1.4,
   NN-1.5, NN-1.7, NN-1.12, NN-1.8 and NN-3.14 (after NN-0.2), NN-4.6
   (after its radio-on measurement), NN-3.10, NN-3.12, NN-6.6.
4. **Stage 3, XL items behind gates, about 1.9-6 ms more (estimate: NN-2.3
   1.5-5, NN-1.10 0.15-0.5, NN-5.1 0.2-0.65; NN-2.7 is GPU-only and
   NN-3.13 overlaps NN-3.3/3.10):**
   - NN-2.3 display-list compiler: only if G0 passes in Stage 0.
   - NN-1.10 IPA register model: only if the top-200 compile census shows
     3 % or more beyond NN-1.2.
   - NN-2.7 role images and the D3D-level HLE they need.
   - NN-6.5 textures held once, with NN-2.3.
   - NN-3.13 user-space kernel objects: only if NN-0.1 shows the syscalls.
   - NN-5.1 physics specialised at build time: after NN-1.2 and the
     NN-0.8 twins show which overheads the family pays.

   **Stage 2 and 3 outcome (2026-10-14).** Kept: NN-1.2, NN-1.3, NN-1.7,
   NN-1.8, NN-3.14, NN-4.3 (ParamEQ only), NN-4.4 and NN-5.1. The Odin gains are about
   0.6 ms of audio-thread CPU a frame from NN-4.4, 0.14 ms from NN-4.3
   and about 0.35 ms from NN-5.1, plus the per-thread instruction cuts of
   NN-1.2 and NN-1.3. NN-2.2 and the PGO build (NN-1.4) measured inside
   noise and were rejected. NN-2.6, NN-4.8, NN-6.6, NN-1.5, NN-1.10,
   NN-1.12, NN-3.10, NN-3.12, NN-4.6 and NN-2.7 were dropped or rejected
   on their premise or measurement. NN-1.8 (Linux code model and
   x86-64-v3) and NN-3.14 (Deck thread placement) were measured once the
   Deck was back and kept: simulation -10.5 % and process -5.5 % cycles,
   and process -6 to -7 %, on the Deck. Each
   item has a Progress row.

A rough bound, as an estimate: stages 1-3 remove about 10-20 ms of the
Odin's 38.8 ms, leaving 19-29 ms a frame, against an estimated native
16-23 ms.

## Verification

- **guest_native tolerance verify** for every native twin: compare
  outputs within a tolerance, including the volatile registers the caller
  reads afterwards (NL-0.1 showed the title reads them).
- **Lockstep verify** covers leaf functions only (NL-0.2); non-leaf
  replacements need route-level checks.
- **Poison build** for any change to call-boundary state (NN-1.2, NN-1.3,
  NN-1.10).
- **Live same-frame captures** (pause or photo mode) for NN-2.1, NN-2.2
  and NN-2.3: frame replays cannot test untile or a native front end.
- **Shadow mode for NN-2.3**: run the compiled list beside the decoded
  path on sampled frames and compare captures before switching over (the
  Rayman Origins port's method; GPL, idea only).
- **Image thresholds** (proposed; calibrate against two runs of the
  reference build first, since the scene varies): per route capture,
  mean absolute error at most 1.0 of 255 levels and at most 0.1 % of
  pixels off by more than 16 levels, or twice the reference A/A, whichever
  is larger. A capture over either limit is reviewed by eye before the
  item is kept.
- **Audio thresholds** (proposed): per-call SNR at the replaced unit's
  input and output of at least 60 dB for float DSP twins (NN-4.3) and at
  least 40 dB for codec replacements (NN-4.1, NN-4.6, NN-4.8). NN-4.2
  changes the mix by design, so it takes a listening test plus
  per-category `audiocapture` levels within 1 dB. The per-category
  `audiocapture` differs run to run, and whole-mix RMS is noise.
- **Determinism-changing items** (NN-1.1, NN-5.1): physics may diverge,
  so route position and image checks stop being comparable between
  builds. These items must pass `expect-simulation-time`; replays and
  ghosts recorded on the reference build must play back on the new one
  without visible desync over a full race; rewind must be tested at three
  points of a race; and their performance gates use per-thread
  instruction rates over a time window, not route positions.
- **A deterministic route** for the save check: the save hash is not
  deterministic today (AP-0.5).
- **The A/A noise floors** (NN-0.3) for every A/B; restart pairs for
  init-only changes such as NN-4.2.
- **Reverse-engineering records** go in `site/findings` in the same
  change that identifies them (CLAUDE.md), not later with the change that
  uses them. This research identified several, listed under
  [Before committing this page](#before-committing-this-page).

## Risks and open questions

- **Deck numbers are estimates.** Everything Deck-specific waits for
  NN-0.2; its split may differ from the desktop's.
- **Base baselines.** Every measured number here is from the base image;
  v4 hook call counts may differ (NN-0.6).
- **Odin noise.** Most stage 1 items are 0.1-1 ms against a raw same-build
  spread of up to 23 %. Without NN-0.3 they cannot be told apart from
  noise.
- **Legal policy.** [LEGAL.md](LEGAL.md#native-replacements-of-game-and-library-code)
  now sets the rules for native replacements (2026-10-13): contract-based,
  independently written code with published or licensed algorithms may be
  committed; hand translations, copied data and middleware's own
  algorithms may not. NN-4.3 and NN-5.1 are scoped to fit it. The native
  versions of `pow` and LZX already fit it (published algorithms).
- **NN-2.3's constant source** is unresolved, and its repeat share ranges
  from 49 % to 89 % depending on the census. The only public precedent,
  Dolphin's display-list cache, was removed (4.0-758) after it gave a
  small gain in some games and broke many others on validity. The
  display-list compiler is worth 3-6 months only if G0 passes.
- **Fixed IEEE mode (NN-1.1)** changes denormal results; collision code
  depends on exact FP corner cases, and on the Deck unflushed denormals
  can cost microcode assists. Route images and simulation-time checks must
  pass.
- **Save/restore deletion (NN-1.2)** removes the guest-stack copies of
  saved registers that hooks and intrinsic readers may read.
- **Lock-free sections (NN-3.1)** depend on no plain store racing a
  reservation; the interrupt callback is the known case.
- **Open:** what the guest render thread spends building PM4 inside the
  guest D3D runtime; Odin i-cache and iTLB behaviour; thermal headroom
  gained per watt saved (NN-0.7); the role of `82E1C3E8`.

Lessons carried over from NL:

- Count the premise in the yardstick's own unit (CPU ms per frame, not
  instructions) before building.
- Check for existing A/B runs before measuring again.
- Run a wrong-image ceiling probe (skip the work entirely) to bound an
  item before making it correct.
- Prototype one unit before a whole-program build.

## Progress

Dispositions of the items as they are executed, with the evidence, in the
form of NEXT_LEVEL_RESEARCH's Progress table. A kept or rejected result
also goes on the docs site in the same change (CLAUDE.md).

| Item | Outcome | Evidence |
| --- | --- | --- |
| Research | **Done 2026-10-13.** This page; the reverse-engineering facts it found are recorded in `site/findings` (audio, threads, rendering, executable, systems, world), the native-replacement policy is in [LEGAL.md](LEGAL.md#native-replacements-of-game-and-library-code), and the goal is on the [roadmap](ROADMAP.md). | Notes and every proposal with both reviews in `.local/backlog-research/near-native-2026-10-13/`. The run's local disassembly copies were deleted; only counts are kept. |
| NN-0.1 | **Done 2026-10-13.** Odin race at 60, base Release, `simpleperf record -g` (DWARF) for 30 s with kernel samples (`perf_event_paranoid` is 1 on the Odin, so `--app` records them; kernel symbols are restricted, so kernel time is attributed by its first user frame). By library: guest code 48.0 %, GPU backend 19.3 %, kernel 9.1 %, runtime 8.2 %, libc 6.7 %, Turnip 4.5 %, vDSO 2.0 %. By thread: GPU commands 28.3 %, guest `8255AE10` 14.3 %, `825A6320` 14.1 %, `82FB4AF8` 12.2 %, submission 7.1 %. Inclusive: packet decode 28.0 %, `IssueDrawImpl` 13.0 %, MMIO store checks 3.2 %, XMA 2.8 %, texture requests 2.4 %, `LoadShader` 1.5 % (1.0 % rehashing microcode with XXH3 on `IM_LOAD`), uploads 1.2 %. Kernel time by first user frame: `condition_variable::notify_all` 3.0 % (pipeline-cache `EndSubmission` 1.0 %, guest `PosixEvent::Set` 1.2 %), `recursive_mutex::unlock` 0.8 %, `mprotect` 0.7 % (write watches), `MaybeYield` 0.6 %; HLE sync syscalls stay under NN-3.13's 0.5 ms bar. **Open lead:** 12.0 % of the render thread `825A6320` (1.7 % of the process) is in vDSO `clock_gettime` with no caller: neither DWARF nor frame-pointer unwinding leaves the vDSO, and the guest's 51 timebase reads sit in 35 functions, none of them hot (the frame function reads it six times). | `rec1` (DWARF) and `rec2` (frame pointers) in `.local/backlog-research/near-native-2026-10-13/stage0/``odin/`; NDK 29 simpleperf with `--symdir` on the unstripped libraries. |
| NN-0.2 | **Done 2026-10-13.** LX-7.0 on the Deck LCD, launched from Steam (a devkit shortcut through `steam://rungameid`; `reaper` is the parent, `SteamLaunch` in the command line), GPU clock on auto (1,040-1,581 MHz). Race at 1x: frame median 16.7-17.9 ms, p95 21.5-22.3 ms (53.6-55.5 fps); GPU 17.2-17.9 ms. Per frame: recorder 11.8-15.7 ms, GPU commands 12-12.9, render 9-9.6, submission 8.6-9.6, simulation 8.2-8.8, FMOD 7.1-7.2; process 59-74 ms; 3,400-4,500 draws. APU 13.2-14.5 W against the 15 W limit, battery 22-23 W, 70-79 °C. The Deck is GPU- and power-bound at 1x. Free roam did not run (the scratch route stuck). | `.local/backlog-research/near-native-2026-10-13/stage0/``deck/`. |
| NN-0.3 | **Done 2026-10-13; estimator revised 2026-10-19 (#747).** The SE values in this table came from overlapping adjacent pairs, which understate it (about 1.45x in simulation); `tools/summarize-inrun-ab.py` now uses disjoint A B A blocks with a t interval, and the recheck of every archived capture is in `site/pages/lessons.md`. In-run: `fh1-race-sustained-aa` toggles `perf_aa_toggle` every 180 frames (14 pairs from frame 4260; `tools/make-ab-route.py --mark`, `tools/summarize-inrun-ab.py`). Odin A/A: process CPU difference 0.02 ms, SE 0.37 ms, so the 95 % interval is ±1.8 % of 39.6 ms (meets ±2 %); decoder per decoded draw ±2.55 % (misses ±2 %; a draw-adjusted regression did worse than pairing). Detector power: 0.3 ms spun on the GPU commands thread was invisible, because that thread busy-yields while idle and the spin only replaced spinning; on a worker thread of its own (`perf_inject_cpu_thread`, the default) it read +0.22 ± 0.43 ms. One run resolves about ±0.9 ms (2 SE); a 0.3 ms item needs about eight runs pooled or a per-thread metric. Cross-build, four reinstalls of the same APK (`xr1`-`xr4`): process CPU 36.7-41.3 ms (SD 6.4 %), because the scene split the runs in two (1,730-1,776 against 1,382-1,390 draws a frame); whole-process CPU across runs is therefore unusable without normalizing by draws. Per thread, instructions a frame vary by 1.1 % on `82589AE8`, 1.6 % on the main (simulation) thread `8255AE10` and 4.9 % on the audio thread `82FB4AF8` (CV over the four runs); the GPU commands thread follows the scene (CV 15.9 %) but per decoded draw it is 34.8-36.6 k instructions (CV about 2.5 %). So build-level items are judged on the simulation threads' instructions (about ±1.5 %) and on GPU-thread instructions per draw. | `aa1`, `inj1`, `inj2`, `xr1`-`xr4` in `.local/backlog-research/near-native-2026-10-13/stage0/``odin/`. |
| NN-0.4 | **Done 2026-10-13.** Odin race (`tools/summarize-memory-ledger.py` over `smaps` and KGSL): PSS 971 MB = guest arena 457.6, scudo heap 321.6, GPU driver mappings 104.1, game code 62.9, other code 17.0, Java 3.2, stacks 2.0, other 2.3; RSS 1,269 MB, swap 13 MB. KGSL holds 1,057 MB: 126 MB mapped (94 MB of it already in PSS through `/dev/kgsl-3d0`), 931 MB unmapped; 72 MB imported. Counted once, about 1.93 GB plus the 72 MB imported. Deck race: PSS 967 MB (guest arena 470, anonymous mappings 188, heap 158, executable 60.5, RADV/LLVM 37, runtime libraries 32.6), RSS 1,242 MB, no swap; amdgpu VRAM 490 MB and GTT 257 MB (fdinfo, no overlap with `smaps`), about 1.71 GB in all; 873 of 1,024 MB VRAM used system-wide, 128 MB evicted. | `ledger-race-sustained.json` in `.local/backlog-research/near-native-2026-10-13/stage0/``odin/aa1/`; `.local/backlog-research/near-native-2026-10-13/stage0/``deck/20261013T175652/`. |
| NN-0.5 | **Done 2026-10-13.** Counters appended to the perf CSV, on in Release builds (`PINYON_SHIFT_CAPTURE_PERFORMANCE` defaults on): injected CPU, process CPU, XMA work-event sets, untile-skipped draws, kernel-object notifies with and without a waiter, guest-range readable checks, critical-section thread lookups, host-path lookup misses, decoded draws, and the replay probe's and `LOAD_ALU_CONSTANT` census's counters. | ShiftGlue `include/rex/perf/counter.h`. |
| NN-0.6 | **Address map done 2026-10-13.** All 27 addresses cited in NN-2, NN-4 and NN-5 map (`tools/map-fh1-v4-addresses.py`), for example `82416A00`→`824469B0`, `0x82416EFC`→`0x82446EAC`, `8246FB98`→`8249F310`, `82589AE8`→`826000A0` (context match), `82FC6CC0`→`83087D70` (the known v4 biquad), `82D21DB0`→`82DE3D10`, `82ADA220`→`82B98AA8`; the `site/findings` records that cite them carry `v4` fields. v4 runs on the Odin (v4 Release, private state with the verified title update; `XEX patch applied` to 0.0.4.12 and the race reached, `v4r1`, `v4r2`), against the base runs with a similar scene (`xr1`, `xr2`: 1,730-1,776 draws, v4 1,640-1,887): process CPU 40.6-42.4 against 40.9-41.3 ms; per role, instructions a frame are within the base spread for the audio thread (v4 `83075D18`: 19.2-22.3 against 20.2-21.2 M), `8261E318` (base `825A6320`), `82C6DD70` (`82BAF5C8`), `82EE37A0` (`82E217A0`) and the GPU commands thread per draw (35.3-35.8 k against 36.2-36.6 k); the main (simulation) thread `825CEC88` (base `8255AE10`) is about 4 % higher (18.3-18.7 against 17.6-17.8 M), unexplained. Base baselines on this page hold for v4 within run spread. | `.local/backlog-research/near-native-2026-10-13/stage0/``cited-v4.json`. |
| NN-0.7 | **Done on the Odin 2026-10-13; the Astra was not connected.** USB input power with the battery full (no battery current), sampled about twice a second: race 7.5-8.7 W across eight runs (mean of the last 46 s; per-sample SD 2.4-3.2 W), 0.7-0.9 W with the game closed and the screen on. The sampler cannot split CPU from GPU, and the in-run A/B windows (6 s, about 10 samples) are too short to resolve a 1 W change. | `*.power` in `.local/backlog-research/near-native-2026-10-13/stage0/``odin/`. |
| NN-0.8 | **Done 2026-10-13** (`tools/nn08-bench`; desktop, Deck, Odin prime core). Twins for `pow` (`82438EA8`), LZX (`830F2210`), the biquad (`82FC6CC0`), the constant walk (`824168B0`) and physics (`82D21DB0`, no native twin). Share of cycles removed on the Odin: FP-mode writes 69.8 % of physics (Deck 65-69 %, desktop 65-71 %); native twins 47-74 % (Deck 35-68 %); no `volatile` 6.9 % of `pow` and 12.7 % of LZX (Deck about 10 % of LZX); register locals a loss on `pow` (-36 %), the walk (-15 %) and the biquad (-8 %), a gain only on physics (26 %); no link-register stores and inlinable helpers under 6 %. On the Deck, x86-64-v3 halves the biquad (27.1k against 57.1k cycles; `fma` is a libm call on SSE4.1). Ranks NN-1: FP-mode write elision first, then `volatile`; locals only with a call-aware model. | `.local/nn08-bench/results/`. |
| NN-0.9 | **Done 2026-10-13.** The timer thread shows as `rex TimerQueue` in the Odin `istat` (about 12 M instructions in a one-second interval). | `aa1.istat`. |
| NN-0.10 | **G0 failed 2026-10-13.** The probe (`gpu_replay_floor_probe`; 2 skips) replays any indirect buffer, at any depth, whose bytes and nested buffers repeat its capture, from the captured exit registers, bins and shaders. Odin race, 14 in-run pairs: process CPU 38.66 → 36.04 ms (-2.54 ± 0.58 SE), decoder 9.26 → 7.50 ms (-1.68 ± 0.31), against the 6 ms bar. Census over the race: about 1,080 buffers a frame, 96 % repeating; 1,890 drawn draws, 74 % in repeating buffers and 42 % in skippable ones (copies, events and other side effects make the rest unskippable), against the 80-85 % bar; 3,900 decoded draws, 52 % untile-skipped. The probe's own hashing and applying cost 0.9 and 1.0 ms. Provenance: of 256 watched lists, 190 were written again after running, 121 writes inside their executed bytes, by `8247B438` (from `8247B4D0`) and `memcpy` in `8247B3B0`, `829EB0B8` and `82C76A90` (`site/findings/rendering.toml`, "display-list writers"). Constant source: about 5,130 `LOAD_ALU_CONSTANT` a frame load 83,570 dwords from about 290 sources, none changed between loads, so they are static tables; this settles the conflict in favour of "engine side of the display lists". NN-2.3 is not pursued; NN-2.2 and NN-2.6 apply. | `g0-ab1`, `g0-ab2`, `wr1` in `.local/backlog-research/near-native-2026-10-13/stage0/``odin/`; route `fh1-race-sustained-replay-probe-ab`. |
| NN-0.11 | **Done 2026-10-13.** The FH1 GPU profile now covers every race frame. It used to end each frame after the presenter had closed the submission, so the frame's last two timestamps were never submitted and 597 of 600 frames were dropped; ShiftGlue now ends the frame before the swap. Odin race, 600-frame windows, base Release, `--fh1_native_gpu_profile=true`: GPU frame 15.7 ms (the profile adds about 0.7 ms: guest GPU time 15.6 against 14.9 ms unprofiled). The main 4x scene is 6.4-6.9 ms in 17-23 renderings a frame, broken mostly by shared-memory uploads (which end 13-19 of them a frame); the title's other renderings about 2.2 ms. Emulation structure: resolves 1.5-1.7 ms, transfers 0.6-0.8 ms, clears 0.3 ms, texture reloads and loads under 0.25 ms, uploads under 0.1 ms, so about 2.9-3.1 ms (19-20 %) plus whatever the main scene's splits cost on a tiler. The upload-split render passes are the first target of a GPU research pass. | `gp6` in `.local/backlog-research/near-native-2026-10-13/stage0/``odin/`. |
| NL-4.1 listening test | **Done 2026-10-13: worker mode chosen.** The maintainer played the game on the Odin in worker mode (`--xma_decode_kicks_inline=false`) and reported it working and sounding great, perhaps with better frame pacing. Frame pacing in the four runs below agrees in direction: frames over 20 ms 39 and 7 inline, 18 and 5 worker; p99 20.70 and 17.55 ms inline, 19.78 and 17.46 worker (medians 16.67 ms in all four; the run-to-run spread is larger than the mode difference). Objective test: The worry was that worker mode (`--xma_decode_kicks_inline=false`) brings back the 50-100 ms stalls the inline path was added against. Odin race, four alternating runs (inline, worker, inline, worker), 40 s of the native 6-channel mix captured from frame 4300 with each frame's submit time (`fh1-race-sustained-audio`, `PINYON_SHIFT_AUDIO_PROBE_SECONDS=40`). In both modes, all 7,500 frames arrived, the largest gap between submits was 14.2-16.7 ms (a frame is 5.33 ms and the host queue holds 8), there were no gaps over 20 ms, no 256-sample block 30 dB under its surrounding half second, no XMA stall of either kind, and the queue stayed at 7-8. Worker mode was active (the decoder thread decoded 26-28 XMA frames per video frame, against 0.1 inline). CPU: guest audio thread 20.3-21.4 M instructions a frame inline, 18.0-19.1 worker (-11 %); XMA decoder thread +1.9 M; net about -0.4 M instructions a frame (about 0.1 ms). The worker captures were about 3 % lower in RMS in both pairs (0.0570-0.0571 against 0.0588-0.0590, 0.3 dB), unexplained. No counter finds a dropout in either mode. NN-4.1 is built on worker mode, which the SDK made the default the same day, and the `Set()` removal (inline only) drops out of NN-4.1 while the direct XMA decode, decoder reuse and lazy contexts stay. Stereo folds of the four captures are in `.local/nl41-listening/`. | `xma-in1`, `xma-wk1`, `xma-in2`, `xma-wk2` in `.local/backlog-research/near-native-2026-10-13/stage0/odin/` (`route/rally-audio-probe.wav`). |
| NN-3.5 | **Kept 2026-10-13.** The import first-use trace is a build option again, `PINYON_SHIFT_TRACE_IMPORT_REACH`, off by default (renamed from `PINYON_SHIFT_TRACE_IMPORTS` so cached build trees pick up the new default). Every hooked import had paid an atomic test-and-set for it. Release Odin runs logged 175 `import.first` lines before and 0 after. | `xr1` (Stage 0) against every Stage 1 run in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-3.2 | **Kept 2026-10-13 (counters).** `RtlEnterCriticalSection` and `RtlTryEnterCriticalSection` take the current thread from the guest PCR instead of a TLS lookup (`rtl_critical_section_pcr_thread`, on). Odin race, in-run: thread lookups 2,718 → 19 a frame (-99 %, gate -90 %); instructions on the render thread -2.5 ± 2.5 % and on the main thread -1.7 ± 1.5 % (gate -0.5 %, both within their noise); process CPU +0.62 ± 0.61 ms, with 343 more draws a frame on the B side. | `nn32-ab1` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-3.3 | **Rejected 2026-10-13.** The premise was a futex call on every release with no waiter. A microbenchmark on the Odin (Android 13 bionic) found no such call: `notify_all` with no waiter costs 1-2 ns over the lock and unlock (21.4 against 19.9 ns; 16.9 against 15.1; after a waiter has left, 21.5 against 20.4). At about 360 releases a frame that is about 1 µs. In-run, the skip read -0.67 ± 0.79 ms of process CPU, which is noise. The code was removed. | `nn33-ab1` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`; `condbench` in the session notes (`stage1/NOTES.md`). |
| NN-2.1 | **Kept 2026-10-13, below its gate.** `IssueDrawImpl` checks the tiled-pass skip right after the copy dispatch, before deriving the draw (`fh1_untile_early_skip`, on). Odin race, in-run: decoder µs per decoded draw -7.2 ± 3.3 % and -8.0 ± 4.6 % in two runs, against +0.8 % (SD 3.6) for the same ratio in five runs that toggled other settings. At about 3,450 decoded draws and 2.80 µs a draw that is about -0.73 ms a frame, against the -0.8 ms gate; it is kept because both runs agree and the change only removes work. | `nn21-ab1`, `nn21-ab2`; controls `nn33-ab1`, `nn32-ab1`, `idle2`, `nn11-ab1`, `nn45-ab1`; `ratio_ab.py` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-2.4 | **Dropped 2026-10-13 (premise).** The 6-12 ms `mprotect` hitches under the global lock no longer happen. Timing every write-watch protect in three Odin races found none over 2 ms: 36-42 protects a frame, 0.25-0.29 ms a frame in all, and 1-2 frames over 25 ms in about 2,680. There is nothing for a separate lock to remove. | `write_watch_protect_ns` and `write_watch_slow_protects` in three race runs in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-3.4 | **Dropped 2026-10-13 (counted).** Guest-range readable checks run 5.2 times a frame on the Odin race (median 0), so a page cache would save microseconds. The desktop's 0.5-1.3 ms came from `VirtualQuery`, which Android does not use. | `guest_range_readable_checks` in the Stage 1 runs in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-3.8 | **Dropped 2026-10-13 (counted).** `HostPathDevice` lookup misses are 0 a frame in the Odin race. | `host_path_lookup_misses` in the Stage 1 runs in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-3.9 | **Dropped 2026-10-13 (bound).** A producer wake can remove at most what fewer idle polls remove. Taking the render thread's idle sleep from 200 to 2,000 µs (ten times fewer polls) saved -0.10 ± 0.09 ms of render-thread CPU in-run and made the tail worse (p99 17.26 → 17.42 ms, frames over 20 ms 0 → 4), so a wake would save under 0.1 ms. | `idle2` (route `idle-ab.fh1test`) in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-6.4 | **Done 2026-10-13 (measured).** Executor surface rows on demand (`fh1_surface_rows_on_demand`, already the default) on the Odin race: surfaces 94 MB on against 247 MB off, KGSL device memory 1,040-1,042 against 1,194 MB (-152 MB), process CPU 38.4 against 38.5 ms. The default stays on. | `surf-off1` against the Stage 1 runs with the default in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-1.1 | **Kept 2026-10-14.** A thread whose guest code has never changed the FPSCR rounding or non-IEEE bits skips the per-instruction mode checks (`ppc_fixed_fp_mode`, on; one flag, defined in the runtime, so libmain and the runtime share it). Odin race, in-run, three runs pooled: render thread -0.15 ± 0.05 ms, main -0.13 ± 0.05, one job worker -0.14 ± 0.05, CAudio about -0.11, XMA -0.15 to -0.25 ms of CPU a frame (about 3 % of the render and main threads); instructions -0.5 to -4 % (jobs -5.8 %). Route captures differ from the A side no more than two A/A runs differ from each other (MAE 30-77; the Odin runs are not frame-identical). | `nn11-ab1`, `nn11-ab2`, `nn11-ab3` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-1.6 | **Kept 2026-10-14 (static).** Indirect calls through the generated dispatch no longer store the target into the context's dispatch-address field first (ShiftGlue `_indirect_call.inja`): those stores fell from 94,714 to 12 in `libmain.so`, its instructions by 124,853 (-1.05 %) and `.text` by 499 KB. Two runs each of the builds without and with it: the four big guest threads went from 56.0 to 55.2 M instructions a frame (-1.4 %), inside the cross-build spread, so the run-time effect is below what the Odin resolves. | `a-1`, `a-2`, `b-1`, `b-2` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`; `llvm-objdump` counts of the two `libmain.so`. |
| NN-4.1 | **Kept 2026-10-14 (two parts), one part dropped.** XMA contexts allocate their decoder state when first used (`xma_lazy_decoder_state`, on): restart pairs, RSS 1,109-1,140 against 1,235-1,252 MB, native heap PSS 209.7 against 321.6 MB (-112 MB). Decoding straight into the output instead of through the staging copy (`xma_direct_decode`, on): XMA thread -0.137 ± 0.066 and -0.210 ± 0.050 ms in-run (pooled -0.17 ± 0.04), instructions -21 % and -41 %. Reusing decoders across contexts was dropped (counted): 0.32 decoder opens a frame. | `c-on1`, `c-on2`, `c-x41`, `c-x41b`, `nn41d-ab1`, `nn41d-ab2` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-4.5 | **Kept 2026-10-14.** The XHV2 voice-chat thread's tick (`sub_8245DBE0`, v4 `sub_8248D438`) is skipped while no voice session exists and the thread waits 50 ms instead (`pinyon_shift_voice_chat_idle`, on; `src/guest_native/voice_chat.cpp`). Odin race, in-run: XHV2 thread 0.121 → 0.013 ms of CPU a frame (-0.114 ± 0.009), instructions -92 %, cycles -91 %. | `nn45-ab1`, `nn45-ab2` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`; `site/findings/threads.toml`. |
| NN-5.2 | **Dropped 2026-10-14 (counted).** The speech module's library is 3.3-3.6 MB of PSS in an Odin race, under the 8 MB bar, so loading it lazily is not worth its risk. | `h-led1` memory ledger in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`, `solib_pss.py`. |
| NN-2.8 | **Rejected 2026-10-14.** Synchronous submission (`vulkan_async_submission=false`) removes the 2.7 ms GPU Submission thread and saves 1-3 ms of process CPU a frame, but the render thread then waits on each submit: Odin race restart pairs, p99 frame time 21.4-21.6 against 17.2 ms and frames over 18 ms 5.9-7.2 % against 0.1-0.3 %, at the same 16.7 ms mean. Async submission stays the default. | `h-as1`, `h-as2` (off), `h-on1`, `h-on2` (on) in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-1.9 | **Kept 2026-10-14.** Android `libmain.so` links with an lld symbol ordering file (`config/performance/symbol-order-base.txt`, the default for base builds; `tools/make-symbol-order.py` writes it from a probe build's boot-to-race call counts, most-called first), so the functions a race runs share as few pages as possible. Odin race, memory ledger at race-moving, two runs per build: `libmain.so` PSS 52.0 and 52.0 MB without it, 34.2 and 35.8 MB with it (-17 MB, -33 %); total PSS 868-874 against 850-851 MB. Process CPU 33.6-34.4 against 32.5-32.9 ms a frame, the same direction in both pairs but within the cross-build band. v4 builds have no order file yet. | `e-led1`, `e-led2` (without), `h-led1`, `h-led2` (with) in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`, `solib_pss.py`. |
| NN-3.1 | **Kept 2026-10-14.** An interrupts-off guest section that holds only one load-reserve/store-conditional pair (no other store, no nested section, every branch staying inside) runs without the global critical region, since its store-conditional is already a host compare-exchange: 1,001 of the 1,062 such sections in the image (`guest_reservation_sections_unlocked`, on; the generator marks them). Odin race, in-run, three runs on build I: about 5,000 sections a frame skip the lock, contentions on it fall from 132-160 to 22-25 a frame (-86 %), and CPU per frame falls on the render thread by 0.42 ± 0.09, 0.33 ± 0.09 and 0.34 ± 0.07 ms (pooled -0.36 ± 0.05), the main thread -0.12 ± 0.05, the job worker -0.11 ± 0.06 and the XMA thread -0.11 ± 0.04 ms. The first run (build H) was void: the switch was a header `static inline` member, which Android gives each shared library its own copy of, so the cvar never reached the generated code (`site/pages/lessons.md`, "One variable, two copies"). | `nn31-ab3`, `nn31-ab4`, `nn31-ab5` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-6.1 | **Kept 2026-10-14, Adreno 740 only.** Sparse shared memory was off on Turnip because resolves into the sparse buffer read back as zeros on the Adreno 740 with an older Turnip. With the bundled Turnip gen8-v37 it renders correctly on the Odin 2 (Adreno 740): race captures differ from the dense buffer's no more than two dense runs differ from each other. Device memory 770-780 against 1,062-1,066 MB (-290 MB; KGSL mapped and unmapped 1,120 → 829 MB on build H), process CPU and frame-time tails unchanged. `vulkan_sparse_shared_memory_turnip` is now 1 by default, sparse on the Adreno 740 only; 2 allows every Adreno, 0 none. Not checked: other Adrenos (the Fold6 holds the player's v4 save and the Astra was not connected) and the Vulkan validation layer, which has no Android build in the repository. | `h-sp1`, `j-sp2`, `j-sp3` against `h-led1`, `j-led1`, `j-led2` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`. |
| NN-1.11 | **Kept 2026-10-14 (static).** Android builds compile every target, `libmain` included, for ARMv8.2-A (`PINYON_SHIFT_ANDROID_MARCH`, `REXGLUE_ARM64_MARCH`): `stwcx.` and the runtime's atomics are inline LSE instructions instead of LL/SC loops or outline-atomic calls (outline-atomic calls 1,976 → 0 in `libmain`, 594 → 0 in the runtime, 71 → 0 in the GPU library). Cross-build runs (three without, two with) show no per-thread difference outside the run spread, so the run-time effect is below what the Odin resolves. The app now refuses to start, with a message, on a CPU without LSE atomics or RDM (ARMv8.0 cores), before any native library loads. | `c-on1`, `c-on2`, `c-on3`, `d-1`, `d-2` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/`; `llvm-objdump` counts. |
| NN-3.6 | **Partly done 2026-10-14.** `-Bsymbolic-functions` on `librexruntime` and `librexgpu-fh1` cut their jump slots from 5,747 to 474 and from 1,124 to 340, and LSE atomics come with NN-1.11. The PLT share did not follow: the GPU commands thread spends 1.29 % of its samples in PLT stubs on build J (runtime libraries 1.00 %) against 1.35 % (1.09 %) at Stage 0, far from the gate (< 0.2 %), because the hot stubs are calls between libraries, which the flag does not bind: `rex::tzcnt` and `bit_scan_forward` (out of line in `math_gcc.cpp`), `RingBuffer::BeginRead`/`EndRead`/`AdvanceRead`, `copy_and_swap_32_aligned`, `FormatInfo::Get`, the upload pool's `Request` and `memcpy`. Next: inline the bit helpers in `math.h` (with the Stage 2 rebuild). | `j-rec1` in `.local/backlog-research/near-native-2026-10-13/stage1/``odin/` (`plt.sh`), Stage 0 `rec2`. |
| NN-6.7 | **Kept as an option 2026-10-14, default off.** `pinyon_shift_retire_guest_code=2` makes the 14.7 MB guest code section no-access (keeping the 258 jump tables found inside it, 14,344 bytes) and punches its pages out of the guest memory file: 14.4 MB released, guest arena 434-437 against 447-449 MB. Seven routes (free roam, photo mode, map, buy car, pause, movie, collectibles) run with no access violation in mode 1, and races in mode 2 run clean (`k-rr1`, `k-rr2`, `l-ret2`: 1-5 slow frames at the race start). The race-start slowdown first seen (44-102 slow frames) needs mode 2 and the memory ledger together (`l-ret2l` 100, `l-base` 5, `l-ret2` 2): the ledger's `smaps` copy after the punch-hole, a measurement artefact. Off by default because a read of retired code ends the game and the routes cannot cover every guest path; 12 MB does not yet justify that risk. | `.local/backlog-research/near-native-2026-10-13/stage1/NOTES.md` (NN-6.7 sections); `src/guest_native/retire_code.cpp`; `site/findings/executable.toml` "switch jump tables inside the code section" |
| NN-4.7 | **Dropped 2026-10-14 (cause narrowed, off the yardstick).** The delay loop on renderer field `+3244` is not the Press Start spin: its timer thunk runs only 270-370 times a second there, and sleeping 200 µs before each read changed nothing (`l-ps1`, `l-ps2`: render thread 16.37 ms of CPU a frame on both sides; `l-race1` no change). In the `ps-rec1` profile the time is in the frame function's own code (29 %, one tight host range) and its drawing callees. `ps-recm` on build M maps that range to the frame function's 16-pass loop at `0x8259F498` (two virtual calls a pass): with so little work per pass, the frame function itself must be running back to back many times per displayed frame at Press Start. Throttling it is a frame-pacing change for the title screen only, which the yardstick does not cover; the timer replacement is removed. | `.local/backlog-research/near-native-2026-10-13/stage1/NOTES.md`; `site/findings/threads.toml` "render thread idle path" |
| GPU pass P1 | **Rejected 2026-10-14.** Hoisting a render pass's vertex and index uploads ahead of the pass (`vulkan_hoist_scene_uploads`) removed nearly every upload split and 7-16 % of render passes, but three in-run A/B races on the Odin measured +0.36 ± 0.16, +0.21 ± 0.27 and +0.43 ± 0.21 ms of GPU time with frame time, slow frames and KGSL busy unchanged: on the Adreno 740 these passes render in system memory, so a split costs a pipeline drain and the upfront copy cost more. Code removed; the split and render-pass counters stay. | `.local/backlog-research/near-native-2026-10-13/stage1/NOTES.md` (GPU pass P1); `.local/backlog-research/near-native-2026-10-13/gpu-pass/NOTES.md`; `site/pages/lessons.md` |
| GPU pass P3 | **No gain 2026-10-14, default kept.** Turning `vulkan_submit_on_primary_buffer_end` off shortened the GPU timestamp span by 0.49 ± 0.21 ms over three in-run A/B races, but KGSL busy, frame time, slow frames and CPU did not move: the span includes the gaps between submissions. Next GPU questions from the pass: resolves (0.2-0.5 ms) and dead transfers (0.1-0.4 ms). | `.local/backlog-research/near-native-2026-10-13/stage1/NOTES.md` (GPU pass P3); `site/pages/lessons.md` |
| NN-1.2 | **Done 2026-10-14.** `host_local_register_saves` (on for the base image) replaces the `__savegprlr_N`/`__restgprlr_N` pair with copies between `ctx` and C++ locals in 22,060 of 22,968 functions; a per-function scan keeps the helpers where the save slots could be visible (exception data 246, unknown r1-indexed access 304, r1 in arithmetic 198, mid-asm hooks 60, and smaller groups). Save call sites 22,969 to 909; Android `.text` +2.2 % (47.0 to 48.1 MB). Odin race, cross-build (two L against three M, simpleperf per-thread instructions, rows 4300-6900): simulation thread -5.9 % (-4.0 % without the light-scene run), audio thread `82BAF5C8` -6.0 %, render thread per decoded draw -7 %; process CPU and frame time within run spread. Race and six routes complete, no access violation, still captures within A/A. The LR slot and the FPR/VMX helpers are unchanged (NN-1.3). | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-1.2); `site/pages/recompiler.md` |
| NN-1.7 | **Done 2026-10-14, below its estimate.** `vmsum3fp128` (1,845 sites) and `vmsum4fp128` (893) are exact SIMD in the SDK header (AVX/SSE2/NEON), matching the old helper bit for bit on 320 M differential cases per path (special values, all rounding modes, flush on and off). clang already vectorized the old helper, so a site went from 37 to 31 (vmsum3) and 34 to 31 (vmsum4) AArch64 instructions and lost its three branches: well under 1 % of any thread, against the 1-5 % estimated. No separate in-game `reference_verify` run: the differential test checks the instruction itself bit for bit, and the Odin lockstep race on build X, which carries it, found 0 mismatches in 41.6 M calls (NN-5.1). | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-1.7); `tests/unit/ppc/vmsum_differential.h` in the SDK |
| NN-2.5 | **Done 2026-10-14.** Packs never loaded before: the Vulkan translation observer reported the bindless flag where the loader expects none (pack flags 09 against 08); fixed in the SDK's `pipeline_cache.cpp`. Packs cannot ship, so `pinyon.py android shader-pack` makes one per device: it starts the game to the title over adb with `PINYON_SHIFT_NATIVE_SHADER_CAPTURE_DIR` (route `fh1-shader-capture.fh1test`), builds the pack with `tools/native-shader-pack.py` and pushes it into the state's shader cache. Odin, Press Start with and without the pack (build M): 711 SPIR-V shaders loaded, 0 misses, translation 0.521 to 0.071 s, start to title 2.987 to 2.659 s (-0.33 s, the -0.34 s estimated). | `.local/backlog-research/near-native-2026-10-13/stage1/NOTES.md` (NN-2.5); `site/pages/android.md` |
| NN-4.2 | **Kept 2026-10-14, on by default on Android and Linux; listening test passed.** `pinyon_shift_fmod_stereo` sets FMOD's speaker mode to stereo before its init (`fmod.init_stereo` replacement of `sub_82F86498`, v4 `0x83047550`; it then declines so the original init runs) and the runtime's stereo fold passes the two channels through at unity. Odin restart pairs: FMOD mixer instructions 10.62/9.30 against 18.11/17.58 M a frame (-45 %), its CPU 3.04/2.47 against 3.75/3.80 ms (about -1.0 ms), `CAudioThread` 1.86/1.84 against 2.11/1.99 ms. A 5.1 speaker setup loses its surround channels, so it is off on Windows and macOS. Listening test 2026-10-14: the maintainer played on the Steam Deck with the stereo mix and reported it sounding great, so it is on by default on Linux too (the Deck has stereo outputs only, unless it drives a surround receiver over HDMI); Windows and macOS keep the 5.1 mix. | `.local/backlog-research/near-native-2026-10-13/stage1/NOTES.md` (NN-4.2); `src/guest_native/fmod_stereo.cpp` |
| NN-5.1 | **Kept 2026-10-14.** Three per-function generator lists (`register_locals_functions`, `fixed_fp_mode_functions`, `single_precision_functions`, `config/rexglue/analysis/main-xex.toml`): every register in locals with a dataflow publish at calls and returns; a function with flush toggles runs only in fixed FP mode and tail calls an unspecialised `ieee_` copy otherwise (with values in locals Clang moves FP arithmetic across the host FP control write); one single-precision fma for fmadds-family ops on single operands. Host-order temporaries not built (NN-0.8: no swap 1.5 %, no volatile 0.3 % of physics). Of 81 family functions tried, 19 kept (arm64 at least 3 % shorter, no more memory accesses; NDK 29, release flags, each function alone): 12,742 to 9,206 instructions (-28 %), `ctx` accesses 3,149 to 1,289, FPCR writes 246 to 19, stack accesses 256 to 737; `sub_82D21DB0` 3,835 to 1,737. The pilot `sub_82D2F348` +1 % with more memory accesses, not kept; the FP options alone on 61 functions +3.9 % instructions and no desktop gain, rejected. Offline tolerance verify (old against new translation, synthetic registers and memory, every register, call argument and written byte, both FP modes): 8,000 runs per function, all within a few single ulps or NaN sign/payload (four `sub_82D2F070` runs traced to a NaN sign re-read through overlapping synthetic pointers); it found two generator bugs, both fixed. Desktop cycles on those inputs: -4 % time-weighted, `sub_82D21DB0` -29 %. 12 of the 19 get lockstep reference copies. Odin lockstep race (build X, `pinyon_shift_reference_verify=1`, 4 ulps): 41,560,196 calls in 251 functions, 0 mismatched, 0 within tolerance, after two verifier fixes (save-area and LR slots the optimized body skips are now unchecked stores, and each byte is compared against its newest store). Odin cost, cross-build (four races on build S without the lists against six on build X, simpleperf per-thread instructions, rows 4300-6900): job worker 2.58 to 2.02 M instructions a frame (-22 %, about 4 SE; the ranges do not overlap), simulation thread 16.08 to 15.54 M (-3.4 %, about 2.4 SE), about 1.1 M instructions or 0.35 ms of CPU a frame, against the 0.1 ms gate. | `.local/backlog-research/near-native-2026-10-13/stage3/nn51.md`; `site/pages/recompiler.md`, `site/pages/lessons.md` |
| NN-1.3 | **Kept 2026-10-14.** `host_local_lr` (base image, with `host_local_lr_keep = [0x82BC5870]` for the vehicle-pose trace that reads its own slot) keeps the saved link register in a C++ local: 55,074 of the 56,799 functions that store LR converted, 1,725 kept by the scan (shared registers 566, unknown r1-indexed access 344, exception data 331, r1 arithmetic 214, mid-asm hooks 81 and smaller groups); `libmain` `.text` -0.99 MB (-2.1 %). No guest code walks the back chain to an LR slot, and no tail-call target reads its caller's slot. Desktop poison build (slot poisoned and checked at each reload): race, 855.6 M checked calls, `lr_slot_mismatches=0`, no access violation. Odin race against build N: simulation thread instructions -2 to -3 %, inside the cross-build spread. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-1.3); `tests/unit/codegen/host_local_lr_test.cpp` in the SDK; `site/pages/recompiler.md` |
| NN-4.4 | **Kept 2026-10-14, on by default.** `pinyon_shift_native_audio_output`: while FMOD's output voice is the only started XAudio2 voice and no other XAudio2 call came in the last second, the host answers FMOD's `GetState` with its own sample count and copies each 256-frame block from FMOD's ring, and the guest XAudio2 pass stops; another voice starting (a movie) or an FMOD voice call hands back at a ring boundary. Shadow mode (both paths): max difference 0, lag 0, phase errors 0. Odin in-run A/B: XAudio2 pass 0.488 to 0 ms, Audio Worker 0.349 to 0.123 ms (-85 %, gate -80 %). Route matrix (fmv, free roam, photo mode, map, buy car, pause, collectibles) 7 of 7 complete, no access violation; with movies on, native output stays off as designed. The hooks are reached only through vtables, so no codegen change. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-4.4); `site/pages/runtime.md`, `site/findings/audio.toml` |
| NN-4.3 | **Kept in part 2026-10-14.** The native ParamEQ (`pinyon_shift_fmod_native_parameq`, default on): build S verify 335,872 calls, none below 60 dB; FMOD mixer thread -0.141 ± 0.047 ms a frame (-5.7 %) in-run. The channel matrix twin matched on 1.29 M calls (after a verify fix for level writes from the game thread) but measured -0.031 ± 0.071 ms, so it and its three host overrides were removed. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-4.3); `tools/fmod-dsp-test`; `site/pages/runtime.md`, `site/pages/lessons.md` |
| NN-4.8 | **Dropped 2026-10-14 (measured).** FMOD's XMA codec decoded on the host at its read, seek and close: the verify never became exact (build S: 2,205 of 25,092 calls below 60 dB, seek alignment), and the in-run A/B moved only the XMA Decoder thread (-0.11 ± 0.08 ms; process -0.05 ± 0.60). With worker decoding (NL-4.1) the emulation left is about 0.1 ms. Code removed; the findings stay. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-4.8), `stage2/nn48-design.md`; `site/pages/lessons.md`, `site/findings/audio.toml` |
| NN-2.2 | **Rejected 2026-10-14.** The decoder-level skip (`fh1_untile_decoder_skip`) dropped a later tile's object buffer when tile 0 ran the same buffer that frame and it only set state and drew, replaying bin masks, window offsets, tile packets and COHER/SCRATCH writes. Five revisions on the Odin race (builds R to W) removed each refusal class (window offset, tile state, registers, tile 0's mask-3 packets, COHER polls). The build W census still put the skippable decode at 1.45-1.51 ms a frame with 56 % of later-pass buffers refused (every-tile masks), and the exact-replay verify still diverged at 2,400 of 4,800 resolve checkpoints and 3,600 CPU-visible writes (registers `0x481E`-`0x4829`). In-run A/B (`nn22-ab5`, skip 0/2, 14 pairs): decoded draws 3,702 to 1,919, but decoder -0.36 ± 0.40 ms, submission -0.23 ± 0.26 ms, process -0.13 ± 0.69 ms. The parse it skips is cheap next to the draws NN-2.1 already drops. Code removed. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-2.2, revisions 1-4), `stage2/nn22-nn26-design.md`, `stage2/nn22-sdk.patch`, `stage1/odin/w-cen`, `stage1/odin/nn22-ab5`; `site/pages/lessons.md` |
| NN-2.6 | **Dropped 2026-10-14 (premise).** Constant uploads cost about 1.4 ms a frame on the Odin (cost model scaled to IssueDraw), but the float share is borderline (51 % of uploads, 45 % of bytes), and the earlier results (RR-2.2: the cost is pool requests, not copies; DR-4.2: persistent blocks +16 ns a draw) leave no way for a delta form to save the 250 ns a draw it needed. NN-2.2 was rejected, so the draw count it was to be re-measured on is unchanged. Not built. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-2.6 premise); `site/pages/lessons.md` |
| NN-6.6 | **Dropped 2026-10-14 (measured).** `MADV_PAGEOUT` reclaims a 64 MB memfd mapped once (RSS 68 to 3 MB) and nothing when it is mapped twice, as the guest arena is; the GPU-backed pages are exactly the double-mapped ones. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-6.6), `stage2/madv/`; `site/pages/lessons.md` |
| NN-1.5 | **Dropped 2026-10-14 (counted).** Three quarters of executed indirect calls are at single-target sites, but calling them directly saves about 0.035 ms a frame (0.3-0.7 % of the owning threads' instructions), below the -0.5 % gate on every thread but render and below what a cross-build A/B resolves. | `.local/backlog-research/near-native-2026-10-13/stage2/nn15-nn110-census.md`; `site/pages/lessons.md` |
| NN-1.10 | **Dropped 2026-10-14 (census, below the 3 % gate).** Realistic bound for more guest registers in host registers over the top 200 functions: 1.4-2.0 % of their instructions beyond NN-1.2, about 0.05-0.07 ms a frame. So Stage 3 does not run it. | `.local/backlog-research/near-native-2026-10-13/stage2/nn15-nn110-census.md`; `site/pages/lessons.md` |
| NN-1.12 | **Dropped 2026-10-14 (measured).** Pinned context and base registers, Odin prime core (`tools/nn08-bench` variants): pow +1 %, LZX -2 to -3 %, biquad -9 %, physics -4 to -14 %, against "at least 1 % better on pow and walk, within 1 % elsewhere": pinning loses the context's no-alias benefit in FP code. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-1.12), `stage2/nn112-design.md`; `site/pages/lessons.md` |
| NN-3.10 | **Rejected 2026-10-14.** Kernel object lookups under the object table's reader lock: 84 % of the global lock's contentions but only about 0.16 ms blocked a frame; in-run A/B process +0.22 ± 0.59 ms, render -0.06 ± 0.10. Code removed; the lock census (`critical_region_census`, off) and the RemoveHandle ordering fix are kept. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-3.10/3.12); `site/pages/lessons.md`, `site/findings/threads.toml` |
| NN-3.12 | **Rejected 2026-10-14.** Explicit dirtying of the CPU-refilled vertex ranges: write-watch faults fell from about 6.8 to 5.4-6.2 a frame, while about 370 pages a frame were invalidated at kicks and all re-uploaded; in-run A/B process +0.02 ± 0.61 ms. Code removed; `write_watch_fault_trace` (off) is kept. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-3.10/3.12); `site/pages/lessons.md`, `site/findings/rendering.toml` |
| NN-4.6 | **Dropped 2026-10-14 (measured).** With the radio on, the FMOD threads ran 0.44-0.67 M more instructions a frame (two alternating pairs), about 0.15-0.2 ms for decode, streaming and mixing together, under the 0.2 ms gate set for the decode alone. | `.local/backlog-research/near-native-2026-10-13/stage2/NOTES.md` (NN-4.6), `stage2/fh1-race-sustained-radio.fh1test`; `site/pages/lessons.md` |
| NN-2.7 | **Dropped 2026-10-14 (measured).** Profiled resolves 1.75 ms and transfers 0.78 ms a frame, but the in-run ceilings (debug patch, every dispatch skipped) saved 0.15-0.28 ms for resolves and nothing for transfers (+0.08 to +0.30 ms): unprofiled, the copies overlap other GPU work. Both are under the 0.4 ms gate, and surfaces have met the memory gate since NN-6.4. Patch reverted. | `.local/backlog-research/near-native-2026-10-13/stage3/NOTES.md`, `stage3/nn27.md`; `site/pages/lessons.md` |
| NN-1.4 | **Rejected 2026-10-14.** Instrumented PGO of the generated code, trained on four routes with a profile keyed to the generated code's content hash, measured on the race (three runs each against four of the same build without it): process instructions after a linear fit on draws -0.72 % (profile applied automatically) and -0.13 % (applied by hand), against the -2 % gate; the build's own runs differ by 20 % raw with the draw count. Profile 13.4 MB (1.9 MB compressed). Tooling not committed. | `.local/backlog-research/near-native-2026-10-13/stage2/nn14-pgo.md`; `site/pages/recompiler.md`, `site/pages/lessons.md` |
| NN-1.8 | **Kept 2026-10-14.** Linux x86-64 builds use the small code model with linker relaxation (88 % of calls direct instead of register-indirect, 93 % fewer `movabs`, code 10 % smaller) and the x86-64-v3 baseline (FMA3 instead of a libm `fma` call, MOVBE). Deck LCD, Steam launches on auto clocks, six interleaved races (A, B, A, B, A, B), per-thread `perf stat` for 40 s from race-ready, against the A/A spread of the three A runs: simulation thread cycles a frame -10.5 ± 1.2 % (A/A 1.5 %), render -7.1 ± 3.0 % (4.5 %), audio -26.4 ± 2.2 % (0.7 %), job threads -14.3 ± 2.8 % (2.0 %), GPU Commands per decoded draw -2.9 ± 0.6 % (0.9 %), process -5.5 ± 0.5 % adjusted for draws; p99 -6.6 %, fps +2.8 %, APU power unchanged at the 15 W limit. Captures differ only by race timing. | `.local/backlog-research/near-native-2026-10-13/stage2/deck/` (RESULTS.md, runs, scripts); `docs/LINUX.md`, `site/pages/platforms.md` |
| NN-3.14 | **Kept 2026-10-14, automatic on the Deck.** `linux_thread_cores` (the Linux form of `android_thread_cores`) pins by thread name; on a Steam Deck the default layout puts the simulation and audio threads on core 0's two SMT siblings, render and GPU submission on core 1's, GPU Commands and the recorder on cores 2 and 3, and everything else on the remaining siblings. In-run A/B on the race (build A, five runs in two toggle orders, because the toggles fall on fixed route frames): process CPU -6.1 ± 1.3 % and -6.8 ± 1.5 % adjusted for draws, from GPU Commands (-7 to -10 %) and the recorder (-6 to -8 %); p99 +0.08 ms with both orders weighted equally (23.45 against 23.56 ms without capture frames), p95 about 1 ms better; frames over 25 ms 4.8 against 3.3 a run, too few to call. Tail follow-up 2026-10-14 on the shipped v3 build, Steam launches at 15 W: eight in-run runs with a randomised, balanced order of on/off in 180-frame window pairs, and four interleaved launch pairs. In-run, auto minus off: p95 -0.83 ± 0.14 ms, p99 +0.09 ± 0.51 ms (p = 0.44 under random window swaps), frames over 25 ms +1.9 ± 2.1 a run (p = 0.21), over 33 ms -0.1. Launch pairs: p99 -0.14 ± 0.88 ms, p95 -1.7 ms, process CPU -6.0 ms, over 25 ms +2.3 ± 4.3 a run. p99 is not worse; every set leans towards a few more 25-33 ms frames under auto, mostly at the race start, none significant (the `*=5,7` entry, which puts the job, XMA and driver threads on two logical CPUs, is the suspect if it is followed up). Two earlier single smoke runs (p99 24.5 ms) fall inside the auto range here. Closed. Data: `stage2/deck/tails/`. | `.local/backlog-research/near-native-2026-10-13/stage2/deck/` (RESULTS.md, runs, scripts); `site/pages/platforms.md` || NN-3.7 | **Dropped at review (2026-10-13).** The title reads `KeTimeStampBundle` through its `GetTickCount`, so the 1 kHz timer stays. | `site/findings/threads.toml`, "GetTickCount reads KeTimeStampBundle": 287 callers, about 1.03 M calls in a desktop race (probe build). |
| NN-3.11 | **Dropped at review (2026-10-13).** The spinners hardly run since the render thread's idle path was replaced. | 234 guest `SleepEx` calls a second in a desktop race; none of the five over 0.01 % of the Odin process (`site/findings/threads.toml`). |

## Sources

Research notes with full citations:
`.local/backlog-research/near-native-2026-10-13/` (CPU codegen, GPU
pipeline, runtime and memory, audio and media, game work and libraries,
device ledger, history of what was tried, prior-art ports, prior-art
translation), plus `10-proposals-and-verdicts.md` (every proposal and
both reviews, with their arithmetic). The corrections this page took
from the reviews trace to these files:

| Correction | Source |
| --- | --- |
| Odin baseline `xa2` and game modes | `odin/*/*.jsonl` and `*.istat` of the NL runs in the session scratchpad named in the device ledger §2.1; `scratch/06-device-ledger/odin_nl_results.json`, `window_threads.py` |
| Desktop untile is CPU-neutral | `D:/horizon1-recomp-tests/desktop/ab-1-*` perf CSVs through `scratch/challenge-untile-premise/ab.py` |
| 26,288 `lfs`/`stfs` copy sites | `scratch/challenge-p3-relaxedfp-feasibility/fpcensus.json` |
| Audio FP-toggle cost about 0 | `scratch/challenge-p3fp-premise/togglemix.json` |
| Runtime-library PLT 0.5-2.5 % per thread | `scratch/challenge-staticlink-premise/perthread.txt` |
| `process_vm_readv` at 0.00 % in cg2 | `scratch/challenge-media-premise/cg2_all_self.txt` |
| 461 KB per XMA context, 148 MB in all | derived from the context's field sizes (8 channels of 12,288-float output buffers, 32 KB of frame data, 32 KB of scratch), not measured; `10-proposals-and-verdicts.md`, audio reviews; NN-0.4 measures it |
| NN-2.7's 0.4-1.0 GPU ms | `10-proposals-and-verdicts.md`, the premise review of the one-band proposal: Odin transfers are about 1 ms and mostly a needed alias copy, resolve dispatches about 2.4 ms with 0.4 ms fixed, and the mirror-write skip saved at most 0.22 ms at 4x |

Repository sources:

- [NEXT_LEVEL_RESEARCH.md](NEXT_LEVEL_RESEARCH.md),
  [PERFORMANCE_BACKLOG.md](PERFORMANCE_BACKLOG.md),
  [RECOMP_OPTIMIZATION_SURVEY.md](RECOMP_OPTIMIZATION_SURVEY.md);
- [ANDROID_ODIN_BACKLOG.md](ANDROID_ODIN_BACKLOG.md),
  [ANDROID_PORT_BACKLOG.md](ANDROID_PORT_BACKLOG.md),
  [LINUX_PORT_BACKLOG.md](LINUX_PORT_BACKLOG.md),
  [LOW_SPEC_BACKLOG.md](LOW_SPEC_BACKLOG.md);
- [DESKTOP_RENDERER_BACKLOG.md](DESKTOP_RENDERER_BACKLOG.md),
  [RECORDER_REPLAY_BACKLOG.md](RECORDER_REPLAY_BACKLOG.md),
  [RECORDER_PER_DRAW_BACKLOG.md](RECORDER_PER_DRAW_BACKLOG.md),
  [NATIVE_PORT_BACKLOG.md](NATIVE_PORT_BACKLOG.md),
  [native-renderer/RESEARCH.md](native-renderer/RESEARCH.md);
- [TITLE_UPDATE_V4_BACKLOG.md](TITLE_UPDATE_V4_BACKLOG.md),
  [LEGAL.md](LEGAL.md);
- `CMakePresets.json`, `CMakeLists.txt`, SDK
  `cmake/rexglue_helpers.cmake`, `include/rex/graphics/vulkan/command_processor.h`,
  `src/graphics/vulkan/command_processor.cpp`,
  `src/graphics/vulkan/shared_memory.cpp`;
- `site/findings/audio.toml`, `site/findings/rendering.toml`,
  `site/findings/threads.toml`, `site/pages/lessons.md`.

External sources (licence in brackets):

- [XenonRecomp](https://github.com/hedge-dev/XenonRecomp) and
  [XenosRecomp](https://github.com/hedge-dev/XenosRecomp) (MIT),
  [UnleashedRecomp](https://github.com/hedge-dev/UnleashedRecomp)
  (GPL-3, ideas only);
- [Xenia Canary](https://github.com/xenia-canary/xenia-canary) (BSD-3);
  Project8Recomp CHANGELOG v0.3.0 (BSD-3);
- [N64Recomp](https://github.com/N64Recomp/N64Recomp) and
  [RT64](https://github.com/rt64/rt64) (MIT);
- [FAudio](https://github.com/FNA-XNA/FAudio) (zlib), a complete XAudio2
  reference;
- Dolphin's display-list cache removal
  ([issue 7000](https://bugs.dolphin-emu.org/issues/7000));
- WYTIWYG ([ASPLOS 2024](https://doi.org/10.1145/3620665.3640371)),
  Instrew ([VEE 2021](https://home.cit.tum.de/~engelke/pubs/2104-vee.pdf)).
