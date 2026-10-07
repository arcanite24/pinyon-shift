# Low-spec backlog: 60 fps at 1x on constrained hardware

Created 2026-10-04 at `dev` `512b0e6` (ShiftGlue `0038a40`) from a research
pass of 2026-10-04 (its report is not in the repository; its findings were
checked against the code and are summarised here, with corrections). Goal:
lower the hardware a player needs for the race at 1x (1280x720 internal) and
60 distinct source frames a second. This is a separate engineering target, not
a side effect of 120 fps work on the reference desktop. It follows
[DESKTOP_RENDERER_BACKLOG.md](DESKTOP_RENDERER_BACKLOG.md) (DR),
[PERFORMANCE_BACKLOG.md](PERFORMANCE_BACKLOG.md) (PB) and
[ANDROID_60FPS_BACKLOG.md](ANDROID_60FPS_BACKLOG.md) (A60). Items here name
the items they extend or re-scope, and nothing measured and dropped there is
proposed again without a new hypothesis.

## Requested defaults and feature trades

User direction, 2026-10-05. These items follow the higher-priority
[original Rally experience](DLC_BACKLOG.md#immediate-priority-the-original-rally-experience).
Items remain open until their implementation and qualification are complete.

- [ ] **Disable bloom and outdated VFX by default.** Inventory the legacy
  effects, including motion blur and depth of field, and provide explicit
  controls to restore them. Check gameplay, cutscenes, showroom and photo mode
  before changing defaults; measure which disabled passes actually save work.
  Bloom now defaults off with a live toggle, alongside the existing motion blur
  and depth-of-field defaults. The native hook zeros the frame-local bloom scale
  at `8246554C`, where the title's own debug adjustment already writes zero.
  Weather data, exposure and tone mapping remain intact. Desktop private-save
  free-roam driving and an on/off/restore run pass; 17 settings regressions pass.
  Captures have different vehicle poses and are not pixel-matched comparisons.
  Cutscene, showroom/photo-mode qualification and actual pass removal remain
  open. Zero contribution still executes the bloom filter; no performance gain
  is claimed. Evidence: ignored
  `D:/horizon1-recomp-tests/bloom-scale-20261006/`.
  The Odin's signed ARM64 build also completes the private on/off/restore
  route at frame 5400 with three free-roam captures and normal shutdown.
  All 17 normal-device user files are unchanged. Android paint shading and
  bright vegetation still need work; the switch is not a general graphics fix.
  Receipt: `D:/horizon1-recomp-tests/android-bloom-20261006/qualification.json`.
- [ ] **Disable MSAA by default on desktop and Android.** Extend LS-1.1/1.2
  to first-run defaults and presets, distinguish MSAA from post-process AA,
  and fix the restart notification through LS-1.3. Verify effective sample
  counts, image quality, memory and GPU time after restarting.
  First-run configuration and the Vulkan flag now default to OFF, preserving
  explicit saved choices. Odin private-state startup shows OFF when the flag
  is absent; settings preservation tests pass. Driving image quality, memory
  and GPU-time comparisons remain pending.
- [ ] **Optional reductions to game systems for weaker machines.** Investigate
  traffic density, ambient AI, crowds and other expensive simulation/render
  systems on Android and lower-end PCs. Profile each reduction separately,
  report sustained frame-time and power gains on real hardware, and expose
  useful reductions as optional settings with clear feature costs. Check race
  opponents, event completion, progression and save/reload; identify modes
  that cannot safely use a reduction. Keep these separate from normal gameplay.
- [ ] **Modern replacements for bloom, motion blur and depth of field.**
  Replace the legacy implementations with optional Vulkan effects, reusing the
  renderer's existing work where practical. Validate depth, motion vectors,
  HDR/exposure, HUD separation and temporal stability as each effect requires;
  avoid applying both the original and replacement pass. Measure desktop and
  mobile cost and retain an effects-off option for constrained hardware.

## The question

The old catastrophic renderer overhead is gone. On the reference machine the
1x race now runs at the 120 limit (DR's after-pass table). The question is
whether the remaining work fits weaker CPU cores, smaller memory budgets and
lower sustained power.

**Release gate (LS-0.2 revised the cadence rule on 2026-10-07).** On each
reference tier below, with the LOW-SPEC 60 preset (LS-1.1):
- **Frame cadence**: in the race (`fh1-race-sync`, plus the heavy race start
  of `fh1-race-start-wait`, 6,000-7,400 draws) at least 59 presents arrive a
  second and at most 1 % of source frames are over 25 ms. The first draft
  also asked for a p95 of at most 16.9 ms, but source frames jitter about
  +-1.5 ms around 16.67 ms on the reference machine itself (p95 17.8 ms)
  while every frame is presented on time on a 120 Hz display, so the p95 is
  reported, not gated. `tools/summarize-low-spec.py` computes the gate.
- **Memory**: peak device-local use is at most 90 % of the heap budget, and it
  stops growing after the first ten minutes of 30 minutes of `fh1-long-drive`
  plus three races and their menu transitions.
- **Sustained play** (handhelds and laptops): the same cadence between minutes
  20 and 30 at the device's default power profile.
- **First session**: shader preparation finishes, and after it no more than
  25 frames are over 100 ms on the first race (DR-1.3's empty-driver-cache
  method).

**Reference tiers** (proposed; LS-0.1 picks real machines):

| Tier | Class | Why |
| --- | --- | --- |
| T1 | Older desktop: 4 cores and 8 threads of the Zen 2 or Skylake generation, a 4 GB discrete GPU | Slower cores and a small VRAM heap, Windows |
| T2 | Steam Deck: Zen 2 with 4 cores and 8 threads, RDNA 2 with 8 CUs, 16 GB shared memory, 1280x800 panel | A top community request (README roadmap). 1x is nearly its native resolution. Needs the Linux build |
| T3 | Laptop with an integrated GPU (recent Radeon or Intel Xe/Arc) on Windows | Shared memory, power limits, a different driver stack |

The reference desktop (Ryzen 7 5800X, RTX 4080) gives sensitivity data only
(LS-0.5). Restricting its cores or clocks does not reproduce another
machine's cache, memory, driver or power behaviour.

## Where the cost is at 60 fps

Reference desktop, 1x, from DR's measurements:

| Work | Cost | Scales with |
| --- | --- | --- |
| GPU recorder thread | 1.11 us a draw on 5,000+ draw frames: about 6.7 ms for 6,000 draws | Draws times the source rate; not resolution |
| GPU decoder thread | 12 `WAIT_REG_MEM` a frame, 5.4-6.2 ms in all, spinning on desktop | Source rate. Spins burn a core |
| Title render thread | 6.5-7.8 ms a frame, 68 % of it waiting on the recorder's fences | Source rate |
| Simulation | 4.6-4.7 ms a step, one step a source frame | Source rate. It steps on the guest vblank callback, every second vblank (DR-5.2) |
| GPU, RTX 4080 | about 6.4 ms span. ROP 3 %, DRAM 17 % at 3x (DR-0.1): front end and barriers, not pixels | Resolution, MSAA |
| GPU, Adreno 830 (MSAA off, cold) | 16.8 ms; the executor's own phases at most 7.0 ms | The only non-desktop GPU measured |
| Busy host threads | 5, about 2.9 cores at 60 fps (PB-4.4) | Source rate |

What follows from it:
- **Resolution does not touch the CPU side.** 1x is the console's own
  resolution and the floor: the scale is an integer, and the translator bakes
  it into shaders.
- **The source rate drives every CPU cost.** The console ran FH1 at 30 fps.
  At 60 the port does twice the simulation steps and render work a second.
  At 120 it does four times as much.
- **Sensitivity, not prediction**: 6,000 draws at 1.11 us is 6.7 ms of
  recorder work. A core with half the throughput needs about 13.3 ms of the
  16.67 ms budget for the recorder alone. The simulation step would be about
  9.2 ms on another core. A 4-core part has little room for the decoder's
  spinning on top.
- **On integrated and handheld GPUs the GPU may bind first.** The Adreno 830
  needs 16.8 ms of GPU time at 1x without MSAA. A GPU in that class should be
  expected near it until measured, so T2 and T3 profile the GPU (LS-6.1)
  before any CPU work is ranked for them.

### Corrections and additions to the research

- **The default config does more than the research said.** A fresh config
  (`src/pinyon_shift_app.cpp`) sets `pinyon_shift_fh1_render_fps_limit = 0`,
  which follows the display:
  `guest_vblank_hz = (limit ? limit : display_refresh_hz) * 2`
  (`graphics_system.cpp`). It also forces `anisotropic_override = 3` (4x) and
  keeps the game's 4x MSAA. On a 144, 165 or 240 Hz display a new player's
  game renders and simulates at that rate.
- **Desktop has no MSAA control.** The desktop presets are PERFORMANCE 120
  (1x, FSR 1, limit 120) and QUALITY 60 (2x, bilinear, limit 60). Only
  Android has the MSAA row and a 1x/60/MSAA-off preset (SMOOTH 60).
  `fh1_msaa_single_sample` is not Android-only in the executor. Desktop
  ANTI-ALIASING selects `swap_post_effect` (FXAA) and does not touch MSAA.
- **A live bug in the restart handling.** The menu keeps its own restart list
  (`NeedsRestart` in `src/ui/settings_menu.cpp`). The SDK declares
  `fh1_msaa_single_sample` `kRequiresRestart`, but the menu's list does not
  include it. So the Android MSAA row sets the cvar live, the executor reads it
  only when it starts, and the menu shows no restart note.
- **Memory telemetry already exists, but only on Android.**
  `vulkan_memory_budget_log_seconds` logs heap usage against
  `VK_EXT_memory_budget`, the texture cache and resident size. Its default is
  30 on Android and 0 on desktop. It does not itemise executor surfaces.
- **Executor surfaces are never freed in a session.** `GetOrCreateSurface`
  creates a dedicated-allocation image per (EDRAM base, pitch, MSAA, format),
  and surfaces are destroyed only at shutdown. One Android session log went
  from 15 surfaces at frame 600 to 32 at frame 31,800.
  - Each surface spans the EDRAM addressing period (`Fh1SurfaceHeight`). A
    1280-wide single-sampled 32bpp surface is 2,048 rows tall for a 720-row
    image: 10 MiB as RGBA8, 20 MiB as RGBA16F (the 7e3 scene).
  - Rough estimate, to be measured by LS-0.4: 0.3-0.6 GiB at 1x,
    1.3-2.6 GiB at 2x, 3-6 GiB at 3x.
  - Single-sampled MSAA surfaces are a quarter of the size, so MSAA off saves
    memory as well as GPU time.
  - The texture cache limits are fixed at 1 GB soft and 2 GB hard (PB-8.3,
    chosen to leave 8 GB cards room at 3x). Scaled resolves add a
    512 MB x scale^2 buffer, sparse where the device supports it.
- **Linux and the Steam Deck inherit the desktop's spinning waits.** The
  `WAIT_REG_MEM` sleep defaults (100 us yield, 100 us sleeps; a third less
  CPU on the commands thread on the 8 Elite) are under `REX_PLATFORM_ANDROID`.
  Every other platform takes the Windows values (2 ms yield, then millisecond
  sleeps), although POSIX sleeps are fine-grained.
- **Stale numbers.** The README's performance section is from 2026-09-30
  (1x Vulkan 9.1 ms, 3x 28.7 ms). The race is now 8.29-8.31 ms at 1x and
  9.5 ms at 3x. The comment above the desktop presets in `settings_menu.cpp`
  still gives the old 2x and 3x costs.

## Verification rules

- **Seeds only.** Never the AppData save (AGENTS.md, CLAUDE.md).
- **A/B method.** Settings that apply live use the in-run A/B: the setting
  alternates every 300 frames in one route. Restart-only settings use
  interleaved pairs on the same route. Compare by draw band, and report
  cold-cache and warmed runs apart.
- **Measure total work, not one thread's.** A change that moves work between
  threads is judged on per-thread CPU (LS-0.3) and the whole frame. The
  executor's GPU frame span runs from the first to the last timestamp and
  includes idle gaps.
- **Benchmark without diagnostics.** Instrumentation proves a change works;
  the benchmark runs without it (`fh1_native_gpu_profile` costs 2-5 ms a
  frame).
- **Each device reports its own numbers.** Numbers from the reference machine
  are labelled as sensitivity data. A saving measured on one GPU is never
  quoted for another (the Android FSR and anisotropy savings are not desktop
  numbers).
- **Do not raise the minimum requirement.** A new GPU feature (descriptor
  indexing, buffer device address, local read) sits behind a capability check,
  with the current path as the fallback. No new CPU instruction-set baseline:
  the FMA build stays a runtime-guarded variant (NP-3.5).
- **Correctness gates.** Golden replays stay bit-exact for changes meant to
  be exact. Fidelity trades are judged by MAE plus one look by the maintainer.
  Guest codegen changes also pass pose drift, the save hash and `ppc_tests`.
- **Two inconclusive trials on one gap mean re-rank**, not a third trial (DR).

## Items

Effort: S under a week, M 1-3 weeks, L 1-2 months, XL longer. Gains are
estimates unless a measurement is cited.

### LS-0 Measure and define the target (1-2 weeks)

| ID | Item | Decides | Effort | Status |
| --- | --- | --- | --- | --- |
| LS-0.1 | **Reference hardware.** Pick or borrow a T1, T2 and T3 machine and record CPU, GPU, driver, RAM, VRAM, display and power profile. | Everything below that names a tier | S | Needs a person |
| LS-0.2 | **Constrained-hardware route matrix.** Runs `fh1-race-sync`, `fh1-race-start-wait` (heavy window), 30 minutes of `fh1-long-drive`, and a menu and scene-transition loop at LS-1.1's settings. It records source and presented cadence; p50, p95 and p99 frame readiness; missed 60 Hz deadlines; recorder and decoder busy time and CPU; wait counts and time; GPU span and executor phases; memory heaps and categories; and power and temperature where the device exposes them (MangoHud logs on T2). It also confirms the gate numbers. | The bottleneck on each tier | S-M | Not started |
| LS-0.3 | **Per-thread CPU on Windows.** `GetThreadTimes` counts in 15.6 ms ticks (DR-0.2), so `gpu_decoder_cpu_ns` and `gpu_recorder_cpu_ns` are POSIX only. Fill them from `QueryThreadCycleTime` (cycles, converted at the measured TSC rate), and add the simulation and render threads. | Whether LS-2 and LS-5 cut work or move it | S | Done (2026-10-07): `QueryThreadCycleTime` at the measured TSC rate; title frame thread in `fh1_title_thread_cpu_time_ns` |
| LS-0.4 | **Memory accounting by category.** Turn `vulkan_memory_budget_log_seconds` on in routes on every platform. Add executor surfaces (count and bytes by format and sample count), texture cache, committed scaled resolve, upload pools, pipelines, and retired allocations still in flight. Report logical bytes beside heap usage, with peaks, as perf CSV columns and a route summary. | Sizes LS-4; replaces the estimate above | S-M | Done for totals (2026-10-07): per-second gauges in every perf capture, log every 30 s on all platforms; pipelines and in-flight retirements not itemised |
| LS-0.5 | **Sensitivity runs on the reference machine.** Process affinity to 4 and 6 cores, with and without SMT siblings, and lower maximum processor state where the machine allows it. A **VRAM balloon** (a small tool that holds N GB of device-local memory in another process, so the game's heap budget shrinks to 4 or 6 GB) shows the low-memory behaviour. These results are labelled as sensitivity data. | Early ranking before LS-0.1's machines arrive | S | Done (2026-10-07): `host_cpu_simulation`, `--host-cpus`, `--sibling-load`, `pinyon_shift_vram_balloon`; results in Progress |
| LS-0.6 | **Commit-tagged benchmark results.** Each run writes a JSON file with commit, SDK, machine, effective settings (a dump of the cvars that matter), route, window and metrics. A script generates the README tables from these files. Then replace the stale README performance section and the stale preset comment. | Stops drift between prose and measurements | S | Done (2026-10-07): `tools/summarize-low-spec.py` records and tables; README section generated from them |
| LS-0.7 | **First session on a slow CPU.** Time shader preparation and count hitches with an empty driver cache (DR-1.3's method) on T1 and T2. The preparation route took 125 s on the reference machine. | Whether preparation or async pipeline work is needed for low-spec | S | Not started |

### LS-1 Choose a cheaper workload on purpose (1-2 weeks)

Gate: the effective settings match the selected preset, and the source rate
equals the selected limit on 60, 120, 144 and 240 Hz displays. No
restart-required setting reads as applied before the restart.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| LS-1.1 | **LOW-SPEC 60 desktop preset**: `gpu_backend = "vulkan"`, `gpu_record_thread = true`, scale 1x, `pinyon_shift_fh1_render_fps_limit = 60`, `host_present_fps_limit = 0`, `vsync = true`, `fh1_msaa_single_sample = true`, `present_effect = "bilinear"`, `anisotropic_override = -1`, `swap_post_effect = "none"`. Measure each choice on the reference GPU (in-run A/B; MSAA by interleaved restarts) and on T1-T3 once they exist. Then decide whether FXAA or CAS go back in. | Half the CPU work a second of the 120 preset. MSAA off cut the 8 Elite's busiest race frame from 25 to 17 ms, and also cuts MSAA surface memory to a quarter | S | Done (2026-10-07); image judged by the maintainer |
| LS-1.2 | **MSAA row on desktop**, labelled apart from post-process AA. Rename ANTI-ALIASING to POST-PROCESS AA (or FXAA) so OFF no longer reads as "no anti-aliasing at all". | Clarity | S | Done (2026-10-07) |
| LS-1.3 | **Restart handling from SDK metadata.** `NeedsRestart` now uses `GetFlagInfo` for both init-only and restart-required flags, plus project settings consumed when the title/profile loads. This covers Android MSAA and preset keys without maintaining a second renderer list. The Odin test shows the MSAA restart badge and pending note; a fresh process reads OFF and clears the pending note. The CRLF regression route also runs on Android. Effective surface sampling and performance remain separate checks. | Correctness | S | Done for lifecycle handling (2026-10-06) |
| LS-1.4 | **Frame-rate rows that say what they do.** GAME FRAME RATE LIMIT's OFF becomes DISPLAY (it follows the refresh rate). Presets set `host_present_fps_limit` too. The display page notes when the presentation limit is below the game limit, because the game then renders frames no one sees. | No accidental 120-240 Hz workloads | S | Done (2026-10-07) |
| LS-1.5 | **First-run defaults from the hardware.** On config creation only, probe the device type (integrated or discrete), the device-local heap size, logical cores and the display refresh. An integrated GPU, a heap under 6 GB or fewer than 6 cores starts at LOW-SPEC 60; other machines start at a 60 or 120 limit, never DISPLAY. Also stop forcing `anisotropic_override = 3` in the fresh config. A player's explicit settings are never migrated. | The right first impression on weak machines | S-M | Done (2026-10-07) |
| LS-1.6 | **A 40 fps step** in GAME FRAME RATE LIMIT, and a BALANCED 40 preset for handhelds and 120 Hz displays (an even third of 120; the Steam Deck's 40 Hz mode). Check the late-swap hook (DR-5.2) and the real-time steppers (DR-1.5) at 40. | Even pacing where 60 is out of reach | S | Done (2026-10-07); see Progress |
| LS-1.7 | **Launcher preflight and tested-hardware table** (README roadmap): show the GPU, VRAM, Vulkan version and core count with the recommended preset, and publish LS-0.2's results per tier. | Supported configurations players can check | S-M | Done (2026-10-07): the launcher's This PC row; per-tier results wait for LS-0.1 |

### LS-2 Waits and power (2-4 weeks)

Gate: the same delivered frame rate with less CPU time (LS-0.3), and lower
package power on T2 and T3.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| LS-2.1 | **POSIX sleep defaults.** Apply the Android `WAIT_REG_MEM` defaults (100 us yield, 100 us sleeps) to Linux too: change the `REX_PLATFORM_ANDROID` guard in `command_processor.cpp` to not-Windows, then measure on Linux and T2. | A third less decoder CPU, as on the 8 Elite (A60-5.1) | S | Done in code (2026-10-07); measuring on Linux and T2 needs the hardware |
| LS-2.2 | **Windows short sleeps for CPU time.** Try a shorter yield phase followed by high-resolution waitable-timer sleeps (`CREATE_WAITABLE_TIMER_HIGH_RESOLUTION`, already in `threading_win.cpp`), judged by cycles (LS-0.3). PB-4.1 measured only working time, behind a 2 ms yield phase that covered nearly every wait. Also apply it to `gpu_idle_spin_count` (500 yields on desktop) and the ring-idle wait. | Frees a core on 4-core parts | S | Done (2026-10-07); see Progress |
| LS-2.3 | **Complete release notification.** DR-1.1 failed because 4 of 12 waits a frame still ended on the timeout, from an unsignalled release. Find every writer of `0x1FCA4000`/`0x1FCA4004` with `gpu_trace_wait_reg_mem_writers`. Then use a race-safe sequence: publish, wake, recheck after waking, with a bounded spin first. `WaitOnAddress` or a futex only once every writer wakes. Never release guest fences earlier than the resources they protect allow. | CPU and power at an unchanged frame rate | M | Not started |
| LS-2.4 | **Thread placement on 4-core and 8-thread parts.** Keep the recorder, decoder, simulation and render threads off each other's SMT siblings (`latency_critical_thread_placement`). Measure on T1 and T2; PB-4.4 measured nothing on 8 cores. | p95 on small CPUs | S | Measured on simulated tiers (2026-10-07): no gain; see Progress |
| LS-2.5 | **Lower CPU power, higher GPU clocks?** On T2 and T3 the CPU and GPU share one power limit. Test whether LS-2.1-2.3 raise sustained GPU throughput. | A hypothesis to measure | S | Not started |

### LS-3 Reuse instead of rebuild on the recorder (re-scopes DR-3.1, DR-4.1, DR-4.2; months)

The phased plan for LS-3 is the [recorder replay backlog](RECORDER_REPLAY_BACKLOG.md)
(RR-0 to RR-6).

Gate: fewer recorder cycles a draw over 5,000+ draw frames, with no
regression in GPU time or memory, and zero verify mismatches over the route
matrix. On T1, the heavy race start meets 16.67 ms.

What is already measured (DR's Progress rows):

| Experiment | Result |
| --- | --- |
| Per-draw templates | 1,205 against 1,115 ns a draw: slower |
| Recorder-side buffer replay | 1,571 against 1,472 ns a draw: slower |
| Persistent constant blocks | Equal to the upload pool; replay still 120 ns a draw slower than none |
| Ceiling probe (skip wholly matching buffers) | Recorder 10.4 to 3.7 ms on the heavy race start |
| Census | 86-91 % of draws match their previous execution, 85-89 % in wholly matching buffers, about 3.6 draws a buffer, 1,200 buffers a frame. Only 4-15 % also match in constants |
| Constant sources | About 90 % of constant dwords are register writes inside the buffers, and about 10 % one 16-dword `LOAD_ALU_CONSTANT` matrix a draw |

The lesson: swapping the allocation or upload mechanism is not enough. The
gather itself and the per-draw validation are the cost. Moving the gather to
the decoder thread spreads that work over threads; it does not remove it.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| LS-3.1 | **Immutable and dynamic constants apart.** Compile the constants a buffer's own register writes set once per buffer identity. Keep the per-draw matrix as a compact dynamic input, snapshotted at decode time, because the title may rewrite the source before the GPU reads it. Shaders read the immutable block and a dynamic slot. Every register a draw reads must be written inside its buffer, checked at capture (DR-4.1's condition). | Most of the 1,130-1,170 binding cycles of a matching draw | L | Not started |
| LS-3.2 | **Stable resource identities.** A descriptor-indexed texture and sampler table (DR-4.1), so a binding becomes an index. Devices without the features keep the current per-draw descriptor path. | Descriptor writes and texture-request work | L | Not started |
| LS-3.3 | **Dependency granularity as a gate, before any replay.** Add per-subsystem generations: texture bindings, watched vertex and index ranges, and tile ownership (its generation exists; DR-3 disposition). Measure how often each would invalidate a segment over the route matrix. A generation that changes on every draw invalidates everything and recreates today's cost. A camera matrix update changes dynamic inputs only. | Whether LS-3.4 can hit | M | Measured (2026-10-07): the gate passes; see Progress |
| LS-3.4 | **Coalesced, order-preserving segments.** With about 3.6 draws a buffer, one secondary command buffer per indirect buffer is questionable: Khronos warns against many small secondaries, and AMD notes that they can cost GPU time. Segments span adjacent compatible buffers and split at target changes, transfers, resolves and CPU-visible packets. They reproduce the exit state for what follows. This is command reuse, not reordering or batching. | Recorder toward DR-4's 3 ms gate | L-XL | Not started |
| LS-3.5 | **A narrow first prototype** on one frequent, well-understood segment family. Success means total CPU, GPU time, memory and p95 readiness, not a high replay count. | Go or no-go for LS-3.4 at scale | L | Not started |
| LS-3.6 | **AMD and Intel GPU-time check** of re-executed segments before they become a default anywhere (DR-4.2's risk). | No GPU regression on T1-T3 | S | Not started |

### LS-4 Bounded memory (3-6 weeks)

Gate: LS-0's memory gate on a 4 GB GPU at 1x (T1, or the VRAM balloon on the
reference machine), with no new hitches from eviction.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| LS-4.1 | **Retire idle executor surfaces.** A surface can go when it has no live tile ownership, no GPU work in flight and no use for N frames, in least-recently-used order. Never retire one that holds authoritative EDRAM contents. Count recreations. | A bounded surface set instead of monotonic growth | M | Not started |
| LS-4.2 | **Texture cache limits from the budget.** Derive the soft and hard limits from `heapBudget` (`VK_EXT_memory_budget`), re-read periodically because other applications change it, instead of a fixed 1 and 2 GB. | Fits 4 GB cards and shared-memory GPUs | S-M | Done (2026-10-07): `texture_cache_memory_budget_limits` |
| LS-4.3 | **Pooled surface allocations.** Suballocate surfaces from pooled memory through the existing allocator (`vulkan_mem_alloc.cpp`). Keep dedicated allocations where the driver requires or prefers them. Measure the working set, not just the allocation count. | Less fragmentation and fewer allocations | M | Not started |
| LS-4.4 | **Tighter surface extents.** Allocate the rows actually claimed, with an expansion path (recreate and copy) when a draw, transfer or resolve reaches further. The full-period height preserves guest addressing, so this needs a bounds proof first. | About 2.8x less for a 720-row surface | L (high risk) | Not started |
| LS-4.5 | **One host image for the 1x and 4x depth alias** (DR-2.1's per-surface scale). This removes a surface and about a third of transfer tile-passes. | Memory and GPU on every tier | L | Deferred with DR-2.1 |
| LS-4.6 | **Behaviour under pressure.** Detect when usage passes the budget (on Windows the OS demotes allocations, which shows as stutter) and log it. Cover it with a balloon route. | Diagnosable low-memory reports | S | Done for detection (2026-10-07): a warning when device-local use crosses the budget; balloon route in Progress |

### LS-5 Guest CPU for slower cores (re-scopes PB-3 and DR-5.1; 1-3 months)

PB-3 and DR-5.1 were deferred because guest threads are not the limit on the
5800X. That ranking does not carry over: a function hidden behind the
recorder's waits there may be the limit on T1 or T2.

Gate: differential correctness (pose drift, save hash, `ppc_tests`) and a
repeatable CPU reduction measured on T1 or T2, not on the reference machine
alone.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| LS-5.1 | **Guest profile on the constrained CPU.** The thread sampler with `--lines 1` and `tools/map-generated-lines.py`, per guest thread (simulation, render, others). | The hot set for LS-5.2-5.4 | S | Not started |
| LS-5.2 | **Profile-guided register locality.** `non_volatile_as_local`, `cr_as_local` and `non_argument_as_local` per function for the hot set, rather than a global switch. State syncs back to the guest context at calls, hooks, exceptional exits, fiber boundaries and interior resume points. Functions that must share register state (exception funclets) stay excluded, as the SDK's config already handles. | 15-30 % of guest CPU (PB-3.2's estimate) on the hot set | L | Not started |
| LS-5.3 | **Offset-free stack and TLS accesses** (PB-3.3). | 4-10 % | M | Not started |
| LS-5.4 | **Runtime overheads on guest threads** (PB-3.11, PB-4.5). Count write-watch faults (60-70 `VirtualProtect` a race frame) and global-lock contention (149 a frame, 0.34 ms) on T1, where each costs more. | Unknown until counted | S to count, M to fix | Not started |
| LS-5.5 | **Numerics apart from locality.** Fused `vmaddfp` (PB-3.4), MXCSR propagation (PB-3.5) and SIMD `vmsum` (PB-3.7), each as its own change with differential tests for rounding, special values and resume. | Small each | S-M | Not started |

Already done or measured, not to redo: native CRT `memcpy`/`memmove`/`memset`
(PB-8.1), `stwcx.` as a compare-exchange (PB-8.2), PGO and AVX2 plugin builds
(PB-3.9).

### LS-6 GPU cost by device class (per device, ongoing)

Already retained, not new work: compute texture loads (DR-2.0), band reloads
and resolves into textures (DR-2.2), CPU extents for unclipped draws (DR-2.1),
folded clears (A60-1).

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| LS-6.1 | **Per-pass GPU profile on T1-T3.** Executor phases (`fh1_native_gpu_profile`) plus the vendor tool (Radeon GPU Profiler, Intel GPA, Nsight). It decides whether MSAA, transfers, resolves, reloads, scene draws or the present chain lead. DR-0.1's low ROP and DRAM shares were measured on a 4080 before the transfer fixes; they say nothing about a small GPU. | The order of LS-6.2-6.5 per device | S | Not started |
| LS-6.2 | **Present chain at low output.** Bilinear against CAS against FSR 1 to 1080p and 800p on each tier (on the 8 Elite FSR 1 cost 1.4 ms). | Preset choice | S | Not started |
| LS-6.3 | **Renderings on integrated GPUs.** Measure the cost per rendering with A60-E1's `fh1_debug_rendering_split_draws` on RDNA 2 and Xe. If it is high, prove local-read candidates one by one (A60-11; `VK_KHR_dynamic_rendering_local_read` reads pixel-local attachments only, so it cannot replace arbitrary sampling or EDRAM alias conversion), each with a fallback. | Sizes A60-11 off Android | S to measure, L to build | Not started |
| LS-6.4 | **Formats and mixed resolution** only where LS-6.1 shows bandwidth leading. 7e3 as `B10G11R11` only after a census proves its alpha unread (DR-2.4 had nothing to gain on the 4080). | Bandwidth on shared-memory GPUs | S-M | Not started |
| LS-6.5 | **Temporal upscaling** (DR-5.4's staged plan) comes after real low-cost source frames. It helps a GPU-bound tier but removes no recorder or simulation work, and the dormant FSR 3.1 path's inputs are wrong today. | GPU margin on T2 and T3 | L-XL | Not started |

## Not to build

- **Another renderer rewrite.** The title's per-draw D3D seam carries 42 of
  about 5,000 draws, and the semantic capture (SNR) did not generalise. The
  display-list boundary (DR-0.4, `82416A00`) is the supported seam.
- **More threads as a way to lower requirements.** A 4-core target gains more
  from removing instructions and synchronisation than from moving the same
  work to more workers.
- **Generic batching or multi-draw indirect.** The draw census found only
  single-draw runs. LS-3 reuses commands; it does not reduce draws.
- **Internal resolution below 1x.** The scale is an integer and baked into the
  translated shaders, and 1x is the console's resolution.
- **A simulation slower than the source rate with interpolated frames.** Frame
  interpolation was rejected (its setting is removed by config migration).
- **Repeating measured knobs without a new hypothesis.** PGO and AVX2 builds,
  priority boosts and MMCSS, broad sleep changes on Windows, constant
  coalescing and compare-before-upload, speculative shader shortcuts (fast
  pixel math, implicit LOD, robustness off), shadows every other frame,
  submission splits. A new device can justify a retest. "Perhaps this time"
  cannot.
- **Optimising a timer instead of the workload.** Every change is checked on
  the whole frame and on total CPU.

## Risks and open questions

| Risk | Settled by |
| --- | --- |
| No constrained hardware in the project | LS-0.1 (a person); LS-0.5's sensitivity runs meanwhile, labelled as such |
| T2 needs the Linux build | README roadmap (Linux in progress); T1 and T3 do not wait for it |
| AMD and Intel are unqualified (README), and the AMD Vulkan fixes await hardware confirmation | LS-0.1's machines; the interpreted, current binding path stays the default where unmeasured |
| Integrated GPUs may be GPU-bound whatever the CPU work | LS-6.1 before ranking LS-3 or LS-5 for T2 and T3 |
| Surface retirement drops authoritative EDRAM contents | Retire only without tile ownership; goldens and route captures; count recreations |
| A new binding ABI raises the minimum GPU | Capability checks and the current path as fallback (verification rules) |
| Heat and power make single runs on handhelds and laptops drift | In-run A/B for live settings; interleaved pairs from the same cooled start for the rest (A60's method) |
| LOW-SPEC 60 drops MSAA: harder edges | The maintainer's look; FXAA or CAS back in if LS-1.1 shows room |

## Working order

1. **P0, now:** LS-1.1 to LS-1.5 (settings, the restart fix and first-run
   defaults), LS-0.3, LS-0.4, LS-0.6 and LS-2.1 (cheap and testable on hand),
   LS-0.5's sensitivity runs. LS-0.1 for the maintainer.
2. **P0 once hardware exists:** LS-0.2 and LS-0.7 on each tier, then LS-6.1.
   Re-rank LS-2 to LS-6 from what binds.
3. **P1:** LS-4.1 and LS-4.2 (memory), LS-3.3 (measure invalidation first),
   then LS-3.1, LS-3.2 and the LS-3.5 prototype.
4. **P2:** LS-5 on the constrained CPU's profile, LS-2.2 to LS-2.4.
5. **P3:** LS-6.2 to LS-6.5 per device, LS-4.3 to LS-4.5, LS-3.4 at scale.

## Needs a person

| Item | What | Who |
| --- | --- | --- |
| LS-0.1 | Picking, buying or borrowing T1, T2 and T3 machines | The maintainer |
| LS-1.1 | Judging LOW-SPEC 60's image (MSAA off, bilinear) at the machine | The maintainer |
| LS-6.1 | Vendor profilers on hardware the project does not have | Whoever holds the machine |

## Progress

Rows are added here as items are measured or done. Records of the
2026-10-07 runs (commit, SDK, settings, simulation, bands, memory) are in
[benchmarks/low-spec/2026-10-07](../benchmarks/low-spec/2026-10-07); the
captures stay in the ignored `D:/horizon1-recomp-tests/lowspec-20261007/`.
All numbers below are from the reference machine (Ryzen 7 5800X, RTX 4080,
120 Hz display) and, where simulated, are sensitivity data.

| Item | Status | Evidence |
| --- | --- | --- |
| LS-1.1 to LS-1.6 | Done (2026-10-07) | Desktop presets LOW-SPEC 60, BALANCED 40, PERFORMANCE 120 and QUALITY 60, each setting `host_present_fps_limit = 0` and MSAA; a desktop MSAA row; POST-PROCESS AA; GAME FRAME RATE LIMIT reads DISPLAY and gains 40; the display page notes a presentation limit below the game's. A new config starts at LOW-SPEC 60 (no 4x anisotropy, a 60 limit); a discrete GPU with 6 GB or more, 6 or more logical processors and a 120 Hz display moves to PERFORMANCE 120 on that first launch (`config.first_run.preset`). The launcher's reset writes the same defaults |
| LS-1.1 | Measured on the reference GPU | Two interleaved pairs with `fh1_native_gpu_profile` on `fh1-race-start-wait` at 60 fps: the game's 4x MSAA adds 0.2-0.35 ms of EDRAM transfers a race frame on the RTX 4080 (0.93-0.98 against 1.10-1.29 ms); resolves (0.5-0.75 ms), texture reloads (0.26-0.49 ms) and clears are unchanged, and the 34 surfaces take 501 against 265 MB (1.37 against 1.12 GB device-local). Frame cadence is the same either way on this GPU. The profile's frame span (about 16 ms at 60 fps) includes idle time, so the scene draws cannot be ranked here; on the Snapdragon 8 Elite MSAA was 25 against 17 ms. Small desktop GPUs need LS-6.1 |
| LS-1.7 | Done | The launcher's graphics panel probes Vulkan through `vulkan-1.dll` (the discrete GPU first, else the one with the most memory: name, device-local memory, Vulkan version), counts physical cores and threads, reads the game monitor's refresh rate, and recommends PERFORMANCE 120 by the game's own first-run rule, BALANCED 40 under 4 physical cores and LOW-SPEC 60 otherwise; it warns below Vulkan 1.3. "Use ..." applies the preset through `set-graphics-experiment.ps1 -GamePreset`, which also reports the in-game preset a config matches. On the reference machine: RTX 4080, 15.7 GB, Vulkan 1.4, 8 cores and 16 threads, 120 Hz, PERFORMANCE 120. `test_hardware_check.py` keeps the thresholds equal to the game's |
| LS-1.6 | Measured | `fh1-race-start-wait` at a 40 limit: 39.97 presents a second on 16 threads and 39.9 on four slow cores, median 25.0 ms, 0.2-0.4 % of frames over 1.5 intervals, and the route's race (late-swap hook and steppers) completes as at 60 |
| LS-0.3 | Done | `gpu_decoder_cpu_ns` and `gpu_recorder_cpu_ns` are cycle-exact on Windows; the title's frame thread fills `fh1_title_thread_cpu_time_ns` (4.3 ms a heavy race frame at 60 fps on 16 threads) |
| LS-0.4 | Done for totals | Perf captures carry `memory_device_usage_mb`, `memory_device_budget_mb`, `fh1_surface_count`, `fh1_surface_mb`, `texture_cache_mb` and `process_resident_mb`. LOW-SPEC 60 race: 1.12-1.13 GB device-local, 34 surfaces of 265 MB, textures 150 MB, 2.0 GB resident. The long drive stays at 34 surfaces and 1.12 GB: no growth at 1x without MSAA. 2x with the game's MSAA: 3.3 GB; 3x without: 4.3 GB. The estimate above (0.3-0.6 GiB of surfaces at 1x) held |
| LS-0.5 | Done | Simulated tiers on `fh1-race-start-wait`, LOW-SPEC 60, heavy band (6,000+ draws): 4 cores/8 threads 59.7 presents a second, recorder 8.9 ms a frame; 4 cores/4 threads 59.7, recorder 7.4 ms (SMT siblings slow the recorder more than they help); 4 cores with busy siblings (slow-core proxy) 58.9-59.3 over eight runs, at the gate, recorder 10.6-10.8 ms, p99 21-24 ms; 2 cores/4 threads on `fh1-race-sync` 59.0-59.3 with 0.8-1.0 % long frames, the edge. All others pass the cadence gate; BALANCED 40 passes on the slow-core proxy with a wide margin. With the balloon holding 11 and 13.5 GB of the 16 GB card (3.5 and about 1 GB free), cadence is unchanged. GPU speed is not simulated |
| LS-2.2 | Done | WAIT_REG_MEM: 100 us high-resolution sleeps after a 200 us yield against the 2 ms yield, at 60 fps, heavy band: decoder CPU 12.4 to 8.9 ms (4C/8T), 10.0 to 7.4 (4C/4T), 12.9 to 11.1 (slow cores), 9.8 to 7.5 (16 threads); p95 0.8-1.1 ms lower everywhere; presents unchanged. At 120 fps the 2 ms yield beat the sleeps in all four interleaved pairs, by 2.4-4.5 presents a second (105.1-112.5 against 100.6-110.1), so the default (-1) chooses by game rate: sleeps at 60 and below, the 2 ms yield above. Verified on the final build: 0-0.1 sleeps a frame at 120 and 3.3 at 60. A first check of the automatic policy ran a stale GPU DLL (see the build row) and was discarded. Windows `Sleep` rounded a sub-millisecond sleep to a yield, which is why PB-4.1's sleeps never cut CPU. Measured and dropped: a 50 us yield (0.4-0.5 ms less decoder CPU, within run spread), no yield (53 presents a second on slow cores), and doubling each further sleep of a wait up to 400 or 800 us to arm the high-resolution timer less often (`ZwSetTimerEx` was 13 % of the decoder's samples): decoder CPU 9.03 against 9.03 ms on 4C/8T, and 55.5 presents a second on slow cores at 800 us. The decoder's remaining 7-9 ms a frame is decoding, not waiting (7.9 ms with every wait asleep) |
| Build | Fixed (2026-10-07) | The SDK copied runtime-loaded GPU plugins (and `rexruntime.dll`) next to the game only when the game relinked. A change inside `rexgpu-fh1.dll` alone did not relink it, so the game kept loading the previous DLL from the build root: three runs here measured stale code before it was caught by timestamps. `rexglue_stage_on_change` now re-copies a plugin or the runtime whenever its file changes |
| LS-2.1 | Done in code | POSIX platforms take the short sleeps; Linux and Steam Deck numbers need the hardware |
| LS-4.2 | Done | `texture_cache_memory_budget_limits` lowers the soft and hard limits to what the budget leaves (90 % of it minus everything else, at least 256 MB), re-read every second. At 1x the race uses 150 MB of textures, so the limit binds only on small budgets |
| LS-4.6 | Done for detection | A warning when device-local use passes the budget. The 13.5 GB balloon left the game about 1 GB free without crossing the driver's reported budget (11.9 GB) or changing cadence |
| LS-2.4 | Measured, no gain | On the simulated 4 cores/8 threads and 4 slow cores, `latency_critical_thread_placement` (above-normal priority for the decoder, recorder and vsync threads) and `ignore_thread_affinities` (guest threads unpinned) stayed within run-to-run spread: 59.43-59.56 against 59.58-59.72 presents a second for three plain 4C/8T runs, and 59.02-59.32 against 58.95-59.19 on slow cores. Retest on T1 and T2, whose schedulers and caches differ |
| LS-3.3 | Measured, gate passes | `gpu_template_stats` now also records, per draw, the host image views and samplers bound and whether the draw needed an EDRAM ownership transfer or a shared memory upload. `fh1-race-start-wait` at 60 fps, 600-frame windows: in the heaviest (5,591 draws a frame) 71.4 % of draws match their previous execution's state and 71.3 % also match in bound views with no transfer (69.6 % in wholly replayable buffers); in the 4,595-draw window 86.7 %, 86.5 % and 84.2 %. Transfers touch 0.4-0.9 % of draws and uploads 0.3-0.8 %, so host bindings and tile ownership cost replay almost nothing; constants differ in 85-95 % of draws, so a replay must re-gather them (LS-3.1). Sizing from a symbol-resolved recorder profile (4 cores, 8 threads, race): the per-draw path is 48 % of the recorder thread; a replayed draw would still gather constants (about 8 %), validate textures and memory (about 7 %) and apply register writes (about 6 %), so about 46 % of the recorder's busy time a replayed draw is skippable, about 32-39 % of the recorder at 70-85 % replayable draws (8.9 to about 5.7 ms a frame), against the ceiling probe's 64 %. That share is only reachable if validity is proved per buffer, not per draw: the DR-4.2 replay (SDK branch `dr42-buffer-replay`) matched each draw's signature before replaying it and a replayed draw still cost about 3,200 against 3,300 cycles, 1,000 of them constant uploads. The design LS-3.4 needs from this: (1) a buffer is valid when its bytes hash equal (the decoder already hashes them for the census) and its entry register state equals the recording's, tracked as a running hash of the register writes applied, not per draw; (2) texture, memory and tile validity from generation counters checked once per segment (this census shows they almost never change); (3) constants re-gathered per draw until LS-3.1 splits the register-written 90 % (fixed when the bytes are) from the per-draw matrices loaded from memory, so the first prototype saves the derivation (state, pipeline, dynamic state, targets) and keeps the uploads |
| LS-4.1 | Deferred | Surfaces do not grow at 1x without MSAA (34 over a long drive and a race), so retirement has nothing to win at LOW-SPEC 60. Reopen for 2x and 3x on 8 GB cards |
| LS-0.6 | Done | `tools/summarize-low-spec.py record` writes a commit-tagged record per run (the runner stores the source revision at launch); `table --compact` generated the README's low-end table. The README race table is from the same records |
