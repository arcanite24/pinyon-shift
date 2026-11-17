# Clean-slate Stage 0 evidence

These are probes of the premises in [CLEAN_SLATE_RESEARCH.md](CLEAN_SLATE_RESEARCH.md),
with experimental modes off by default. Default builds omit the probes.
Unestablished gates are not passes.
Local counts and device output are in `.local/codex-cs/`; they contain no
committed game code. No remote was pushed.

The first sections preserve Round 1 evidence. [Round 2](#round-2) supersedes
the replay and fence interpretations and records the still-unresolved exact
context gate. The original global-order capture failure and synchronous
drain alone did not decide their premises.

## Round 3

### Probe build isolation

The session pilot and both fence probes now require the SDK CMake flag
`-DREXGLUE_ENABLE_CS_PROBES=ON`. It defaults **OFF**, including Release.
Disabled builds omit the session implementation, cvars, PM4 capture state,
fence virtual methods, timeline worker and feature request. Session hooks
reduce to inline constants/no-ops; fence completion actions execute directly,
without the diagnostic callback wrapper or cvar query. The public runtime
definition also controls the application's audio and native hooks. An
experiment must rebuild the runtime, GPU plugin and host together.

On multivac (5800X/RTX 4080, NVIDIA 581.08), the default native Release
build's **785 active project/SDK objects have zero probe symbol definitions
or references**, checked with `llvm-nm --demangle` by
`tools/cs/check-probes-disabled.py` (configure with
`-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` first). The session source is absent
from the active compile commands; stale objects are not counted.

The short before/after desktop A/A uses
`tools/cs/routes/cs03-default-aa.fh1test`, private copies of the immutable
`appdata-2026-09-27-winwarm` seed, Vulkan/1x, vsync off and 60 fps. Both
60-second scripts stop normally, with free-roam captures at the pinned
position. No builds ran during either route. Retaining all frames in the
last 27..2 seconds (1,492 / 1,500 rows), mean frame time is
**16.755 → 16.666 ms (−0.53%)**, p99 **18.500 → 17.336 ms**. This shows no
observed frame-time regression in this short capped control. Process CPU
is 30.831 → 29.354 ms/frame while draws change 3,880 → 3,685; scene variation
prevents attributing that difference to the flag. Before source is parent
`571e8c09` / SDK `200bfdb`; after is that source plus the guarded probe patch.
Raw results, symbol check and binary fingerprints: `.local/codex-cs/round3/`.

### CS-0.2: caller demand and net publications

**Gate FAIL under the required conservative contracts; CS-2 is rejected at
this gate.** On the matched hot-thread instruction profile, net removable
context traffic is **0.850% render, 0.979% simulation and 0.753% mixer**;
pooled by retired-instruction samples, **0.903%**, against 15%.

| Thread / native TID | Load / store deletion samples | Total hot-thread instruction samples | Net fraction |
| --- | ---: | ---: | ---: |
| Render / 5178 | 419 / 219 | 75,042 | 0.850% |
| Simulation / 5168 | 792 / 140 | 95,174 | 0.979% |
| Hot mixer / 5189 | 157 / 8 | 21,916 | 0.753% |

The conditional-write charge retains no additional **sampled** store in
this profile; the synthetic control demonstrates that it retains one when
needed. This is not a claim that no such publication exists in all code.
Required stores are retained at their existing sites, with zero inserted
store sites. Unknown sampled instructions and unproved aliases receive no
deletion credit. The three small mixer threads remain separate in the raw
output and do not dilute the hot mixer. The percentages are the static
model weighted by a sampling profile, not an executed optimized build.

The final source artifact has 76,816 summaries (76,513 generated bodies,
267 opaque native override contracts and 36 reviewed native-entry aliases), 48,101
unresolved indirect sites, 49,929 opaque publication contracts and 267
native-to-original callback contracts. Return demand reaches ALL for
76,794 summaries after three iterations. The 23.7–29.6% ABI ceiling remains
historical: it deliberately granted narrower unknown-call and return
contracts. It is not the net count under read-everything handling. New
complete target/escape proofs would change the contracts and justify a
new census; this result is not a limit on every possible IR design.

Final evidence only: `.local/codex-cs/round3/ctx-net-{source,census,summary}.json`,
`ctx-imports.json`, extended `context-layout.json` and their build/self-check
logs. Earlier `ctx-source-*` / `ctx-census-*` variants in that directory are
exploratory. The full tool suite runs 540 tests: 534 pass, six skip; analysis
self-checks and native/Android ARM64 layout checks pass. The first test
invocation used an isolated Python without the repository import path;
the corrected full invocation uses the existing analysis environment.

The Round 3 census uses the **same** `r2-ctx-regs4` Odin instruction samples,
context layout and archived `libmain.so` as Round 2. No new timing run or
rebuilt library is substituted. `tools/cs/ctx-exact-census.py` computes
may-read-before-write, may-write and must-write sets, then propagates each
caller's continuation demand back to its callees until stable. Tail calls
propagate their caller's return demand. Unknown indirect calls read/change
all slots and their continuation demands reach every dispatch-table entry.
The resulting full return demand is derived from those continuations;
it is not an assumed ABI result mask. Opaque native replacement wrappers
also demand the complete result of their callable strong original bodies.

All 421 emitted switches are lowered into their recovered CFG edges.
Trap helpers, context snapshots/restores, CR/FPSCR methods, vector stores,
conditional writes and mutable atomic expected operands have explicit
effects. Partial writes preserve the rest of the slot. Reviewed native
CRT and critical-section contracts come from SDK bodies and the typed
marshal, including the void memory routines that preserve r3. ELF PLT/GOT
relocations resolve 11 reviewed import stubs among 869 imports. Other
opaque boundaries retain ALL read/write sets with no definite kill.
Every such publication contract is retained in the local source artifact.

The dispatch table gives a global target set, not a receiver-type proof
at a particular call site. The RE workspace's class/name index and the
historical observed targets provide no complete site-specific set. Literal
and straight-line copy propagation is also checked; no additional bounded
indirect target set is established. Unresolved sites therefore keep the
required read-everything contract, rather than using observed targets.

The matched AArch64 census separates local uses from memory observers.
Forward cache facts intersect at joins; backward demand retains the
original store when a call, escape or return can observe its value. A
conditional callee write also requires the old backing value when a later
reimport might need the unwritten path. These newly required publications
are charged before counting deletions. A pair survives if either component
is required. Required publications stay at original store sites, so the
count introduces no new store site. Unknown aliases/instructions are
retained. This counts context memory instructions under the stated
conservative contracts; it does not predict spills, instruction selection
or performance of a future IR backend.

Reproduce with the analysis-only Capstone environment used in Round 2:

```powershell
$py = '.local/codex-cs/round2/analysis-venv/Scripts/python.exe'
& $py tools/cs/ctx-exact-census.py --self-test
& $py tools/cs/ctx-exact-census.py --generated .local/generated/default `
  --binary .local/codex-cs/round2/cs02-measured-libs/libmain.so `
  --output .local/codex-cs/round3/ctx-net-source.json
& $py tools/cs/ctx-exact-census.py `
  --sets .local/codex-cs/round3/ctx-net-source.json `
  --android-dump .local/codex-cs/round2/cs02-odin-regs4-dump.txt `
  --runtime .local/codex-cs/odin/r2-ctx-regs4/logs/runtime.log `
  --binaries .local/codex-cs/round2/cs02-measured-libs `
  --layout .local/codex-cs/round3/context-layout.json `
  --output .local/codex-cs/round3/ctx-net-census.json
```

### CS-0.2: observed indirect targets as call contracts (#1070, 2026-11-12)

**Gate FAIL; CS-2 stays rejected.** Issue #1070 reopened CS-2 with a
speculative design: guard each indirect call with the targets a probe
build observed and send a guard miss, or a site the probe never saw, to a
conservative clone of the callee. `tools/cs/ctx-speculative-census.py`
models that. An observed site calls one of its observed targets. An
unobserved site calls an opaque fallback that reads and writes every slot
but feeds no return demand into the fast bodies. The 1,758 functions the
probe entered with no guest caller (thread entries, callbacks) keep full
return demand. Everything else is `ctx-exact-census.py`'s parser,
contracts and solver, unchanged.

The probe summary (`.local/re/probe/race-summary.json`, base race) gives
observed targets for 17,360 of the 48,101 unresolved call sites; the other
30,741 fall back. Return demand stays ALL for 2,095 summaries instead of
76,800. The Odin instruction profile and matched `libmain.so` that weighted
Round 3 are no longer on disk. So this reports a source-level proxy, with
each function's slot accesses weighted by its probe entry count:

| Contracts | Dead slot writes | Reads already available | Share of weighted lines |
| --- | ---: | ---: | ---: |
| Round 3 (conservative) | 7.32 G | 341.3 G | 1.23 % + 57.1 % |
| Speculative | 10.64 G | 342.4 G | 1.78 % + 57.3 % |

The host compiler already keeps most available reads in registers, which
is why Round 3 counted on the AArch64 binary. What matters is the
difference: the speculative contracts make 4.4 G more accesses removable,
0.73 % of the weighted lines. Scaling Round 3's measured 0.903 % by the
ratio of removable accesses (1.0125) gives about 0.91 %. Adding the whole
difference to it gives at most about 1.6 %, against the 15 % gate. Observed
targets narrow return demand, but the dead publications they expose are a
small part of the traffic. The proxy counts each line once per entry,
ignoring branches, in both modes. The 268 functions with native overrides
come from the desktop build's objects (`llvm-nm`), since the shipped
Android library is v4.

### CS-1 deterministic scheduling probe

The Round 3 desktop experiment serializes guest execution with one permit.
Guest entries have a 128-call budget, kernel boundaries share that budget,
waits yield explicitly, and 64 repeated timebase reads yield from polling
loops. The GPU decoder, audio pump, XMA worker, virtual timers and vblank
also acquire the permit before affecting guest state. Every grant advances
the logical clock by 10 microseconds; when every actor is delayed, it jumps
to the next deadline. Registered signals shorten waits; opaque native
completions have a one-logical-millisecond polling fallback. Host wall time
is used for profiling, presentation pacing and the watchdog, not the guest
clock. The timestamp bundle, timebase, uptime, system time and native guest
clock hooks use logical time. The initial host epoch is an external input.

Preflight found two native waits that needed explicit scheduler yields:
GPU WAIT_REG_MEM polling and the render hook's GPU-write notification wait.
The base XMediaFacade movie workers also self-suspend with NtSuspendThread
(the observed continuation is 881EC61C). These use cooperative suspension
in the probe; initial CREATE_SUSPENDED still uses the native startup gate.
The media observation extends the existing executable finding. No v4
mapping was inferred from this base run.

The recording contains the schedule and external controller, I/O and audio
pump inputs. PM4 hashes and word counts are comparisons, not substituted
guest state. Internal clocks, lock grants, allocations and guest-memory
loads are not replay values. In serialized traces the v2 record's host_ns
field contains logical nanoseconds. The render script's clock also uses
logical time. At its completed stop the private verification process flushes
the traces, schedule and perf CSV, then terminates without UI teardown.
That is a bounded diagnostic capture, not coverage of normal shutdown.
The mutex adapter retries an unset MSVC owner natively: owner publication
and SRW acquisition/release are separate operations. Treating that
transient state as a guest wait introduces uncontrolled host timing.
The earlier build disagrees at grant 139,779 (`schedule-race6-replay`,
logical 4.35063 s): a cooperative global-lock wait versus a call-budget
point. That trace establishes native lock arbitration, not a PM4 mismatch;
it does not identify the recorded owner. The revised adapter closes the
unset-owner gap and is used for subsequent attempts.

The prototype is Windows-only. Global-region contention against a parked
actor yields cooperatively; contention against a native backend worker waits
natively without advancing the guest clock. Distinguishing these uses the
pinned MSVC STL 14.44.35207 mutex-owner layout, checked for size and alignment.
This is an experimental portability limit, compiled out of default builds.
Host producers of the GPU work queue also enter the permit. The GPU idle
loop uses a fixed logical wait instead of its host spin-count heuristic.
The lock control varies a foreign worker's hold from 5 to 15 ms and replays
the same five grants / 50 microseconds, while separately checking an actor
that yields with the global lock held.

Fixed-delay attempts are retained as failed route qualification, not race
results. They include missed confirmations during loading, free-roam
captures, an unbounded movement wait and a car that drifted out of the
entry trigger. Brake input then drove the stopped car backwards; the final
route holds the handbrake after the fresh-vehicle startup anchor. It does
not teleport a car or change the seed. Movie opening and fresh free-roam
pose anchor startup; confirmations precede throttle, then a fresh movement
anchor precedes the race window. The driving and end HUD captures are the
qualification, not the script's exit status or game mode 3 (which includes
entry and results too). Script ticks pause at anchors; watchdogs count
output frames. No waits or confirmation inputs occur within the 60-second
window. Capture `logical_ns` bounds the PM4 interval; perf CSV times and
process CPU remain host measurements.

**Gate (a): FAIL, zero racing seconds replayed identically.** The qualified
`schedule-race14-record` stops successfully with both race-HUD captures:
4,846 PM4 frames including startup, 24,732,250 grants, final logical time
250.551870063 s. The 638-output-frame capture window spans 59.98244 logical
seconds / 91.187411 host seconds; the complete tape extends another five
logical seconds, so it covers more than 60 seconds after the first capture.
The visible race timer advances 13.461 to 73.780 s.

The **unobserved** replay fails at grant **850,145**, logical **11.67161 s**,
on guest thread 8: expected call-budget site **82C01D08**, actual
**824E5100**. This is guest control-flow drift, before racing, not an
observed PM4-hash mismatch. The helpers' static call edges are recorded in
the executable findings; they do not prove a changed XAM privilege result.
The upstream state change is not localized by this trace.

A separately sampled repeat fails earlier, at grant **8,461**, logical
**3.212016539 s**, waiting for host/main actor 8000000000000100 to attach.
All-thread native stacks identify a concrete uncontrolled dependency:
the UI is blocked in `GraphicsSystem::InitializeShaderStorage` on its
fence; the GPU actor is parked in `VulkanPipelineCache::InitializeShaderStorage`
waiting for native prewarm workers. Replay expects the UI's next scheduler
entry before granting the GPU another completion poll. Native backend
completion is not an input on this tape. This is an external-completion
coverage failure / scheduler deadlock; serializing guest and service actors
alone does not control it. It is separate from the unobserved guest-path
split. No full oracle is accepted, and the experiment does not refute a
scheduler that also controls those external completions.

**Cost (b): the serialized prototype is much slower, as expected for a
verification experiment.** `schedule-cost-serial2` uses mode 3, session
mode 0: no schedule file, external-input tape or PM4 hashing. Its same-input
normal control is `schedule-cost-normal2`, the default Release with probes
compiled out. Both use the pinned warm seed, Vulkan/1x, vsync off, a 60 fps
cap, `gpu_record_thread=false` and `vulkan_async_submission=false`. These
match the prototype's supported topology; this is not a comparison against
every shipping renderer configuration. No builds, tests or sampling run
during the timing windows.

| Desktop race control | Retained rows | Mean / p99 frame ms | Process CPU ms/output frame | Draws/output frame | Average process cores |
|---|---:|---:|---:|---:|---:|
| Default Release | 3,594 | 16.666 / 17.380 | 22.007 | 2,467.7 | 1.320 |
| Serialized, trace-free | 594 | 144.567 / 222.919 | 157.381 | 3,805.0 | 1.089 |

This is **8.67x mean frame time** and **7.15x raw CPU per output frame**.
Output cadence and trajectories differ; serialized draws/frame are 54.2%
higher, so the CPU ratio is not an isolated scheduler-overhead estimate or
an intrinsic bound on serialized execution. CPU rate actually falls from
1.320 to 1.089 cores. The retained windows consume 79.094 / 93.484 CPU
seconds over 59.899 / 85.873 host seconds. The full capture spans are
60.007668 host seconds normally and 60.03764 logical / 86.595386 host
seconds serialized. CPU is the CSV's process user+kernel time delta, summed
across threads. Frame and CPU means retain every row except two at each
capture boundary, excluding readback/PNG disturbance; there is no outlier
trim. Both runs stop successfully and their driving/end images show the
race HUD. `schedule-cost-comparison.json` retains values and frame bounds.

Timing uses a longer handbraked prelude and one late race-start press to
keep the fast control from starting earlier. The normal boot file anchor
is frame 20 rather than 370: the fast build had already passed the
file-wait lookback at 370. Racing inputs and measurement frames are
identical; the startup-anchor difference is outside the measured window.
Every run saves its scenario and binary fingerprints. The hash gate uses
its own frozen `schedule-race14-record-scenario.fh1test`, not a later edit.
The `max_active=1` log describes the single-permit invariant, not an
independent detector of every host access to guest state. This probe
establishes neither a correctness oracle nor a shipping performance mode.

Reproduction (frozen local generated trees; backups refuse overwrite):

```powershell
cmake -S . -B out/build/win-amd64-release -DREXGLUE_ENABLE_CS_PROBES=ON
# Run instrument-schedule-budget.py for default, xmedia and speech, with
# separate --backup directories, before building. It journals originals.
cmake --build out/build/win-amd64-release --target pinyon_shift pinyon_shift_stage_rexruntime
# Run cs01-serialized-race.fh1test from the pinned warm seed, privately copied.
# Record: cs_schedule_mode=1, cs_session_mode=1, exclusive schedule/trace paths.
# Replay: the same binary, cs_schedule_mode=2, cs_session_mode=2, those paths.
# Timing: cs_schedule_mode=3, cs_session_mode=0 (no tape or PM4 hashing).
# Both builds: Vulkan, vsync off, 60 fps cap, gpu_record_thread=false,
# vulkan_async_submission=false. Never build during timing runs.
```

Budget instrumentation covers **86,245** non-reference generated bodies in
326 partitions across all three modules; reference execution counters are
zero. Use `--restore` on each instrumentation backup before returning to a
default build. `read-schedule.py` validates grant identities, monotone time,
record count and truncation. The scheduler controls cover reversed native
arrival order, ordinary shared-memory updates, self-suspension, parked-actor
and native-worker lock contention, and rejection of changed points,
truncation and overwrite. A GPU-stream end comparison prevents accepting a
replay that leaves trailing PM4 frames unread.

### CS-0.3: ordered pipeline runs on the Deck

The optional Vulkan census (`REXGPU_FH1_ORDERED_CENSUS=ON`, default OFF;
`fh1_frame_census_ordered=true` and an exclusive
`fh1_frame_census_ordered_path`) retains selected pipeline-cache-entry
identity per emitted guest draw and actual host rendering instance.
`REXGLUE_ENABLE_CS_PROBES` stays OFF; the options are independent. Pipeline
IDs are process-local, auxiliary draws are excluded, the first pipeline
in a rendering is not a switch, and pass/frame boundaries close a run.
The native LLVM 20.1.8 / x86-64-v3 build runs `cs01-race.fh1test` through
Steam on the reference Deck LCD, using the read-only Stage 0 `warm-seed`,
Vulkan/1x and a 60 fps cap. Both endpoint HUD images qualify; race-window
GPU samples are 990–1,476 MHz, not the SSH-only 200 MHz state. Over
**59.999757 s / 3,560 frames**, there are **11,756,744 draws** and 273
selected pipeline identities: **1,147.42 switches/frame** (median 1,039,
p95 1,786) and **2.5165 draws/run** (median **1**, p95 **6**, maximum 242).
**72.43%** of the 4,671,838 runs contain one draw. All output mappings are
present and unique, with zero overflow. `tools/cs/analyze-frame-order.py`
checks those properties; local evidence is `round3/deck-order-race2/`
(including the compressed raw stream and hashes). The first attempt
stopped before game launch because the older seed lacked Vulkan storage;
it contributes no census data. These are adjacency counts, not literal
Vulkan bind-call counts or proof of legal batching or a performance gain.
No batching was implemented; CS-3 graphics DGC remains on hold.

## CS-0.2: observable context state

**Gate not established, 2026-10-17.** The multivac analysis ran on the base
generated tree at project `ebbf959`, SDK `79d3e6f`. The tree was last
generated 2026-10-16; its concatenated partition SHA-256 is
`f73cb4edadf3461d014c18601b66bb28b1ef0b2c6f15aa155fe46628465c4613`.
`tools/cs/ctx-publish-sets.py` excludes reference copies and analyzes 76,257
`sub_` bodies, 209 context slots, 3,701,893 source load expressions and
2,725,935 source store expressions. These are source expressions, not host
instructions and not deletions.

The script builds a CFG from the emitted labels and branches and solves
may-read-before-full-write sets to a fixed point over direct calls. Partial
slot writes preserve the old slot. Native/context escapes, resume switches
and all 48,100 unresolved indirect call sites read everything. Callees are
not assumed to kill caller state, so the summaries are conservative, not
exact publish sets. The historical `.local/re/probe/race-summary.json`
contains observations at 18,017 indirect sites; observed targets are not a
proof of the possible vtable targets. No sound call-site vtable resolution
artifact was found. The script reports this as unknown, not zero targets.

For a compiled-code cross-check, it streams NDK r29 `llvm-objdump -d
--no-show-raw-insn` over `out/build/android-arm64-release/libmain.so`
(2026-10-16), retaining only counts. It recognizes AArch64 context-base
copies, counts pair loads/stores as one instruction, and clears speculative
state at branches. Only full GPR/LR/CTR stores are publication candidates.
A candidate is a store before a direct call to a callee that cannot observe
that slot. It can be **deferred**: a later observer may still require it.
It is not a net deletion, and host register pressure has not been modeled.

| Root (base address) | Direct closure, functions | Identified ctx loads / stores, static | Publication deferral candidates / host instructions, static | Same ratio, weighted by historical global race calls (estimate) |
| --- | ---: | ---: | ---: | ---: |
| Render `825A6320` | 1,369 | 24,272 / 38,327 | 2,139 / 245,359 (0.87%) | 0.48% |
| Simulation `8255AE10` | 6,210 | 116,581 / 188,289 | 12,662 / 1,089,757 (1.16%) | 0.55% |
| Audio `82FB4AF8` | 14 | 64 / 104 | 8 / 524 (1.53%) | 2.82% |

These closures overlap and omit indirect reachability. Global function call
counts cannot attribute a shared callee to a particular thread; the audio
closure is especially incomplete. The binary and historical call probe
are not a matched build. Accordingly none of these ratios is a hot-thread
instruction saving or evidence against the 15% gate. Missing evidence:
matched per-thread/per-edge call counts, sound indirect target sets, callee
must-write summaries, return demands and an instruction census after exact
publishing. **Do not authorize CS-2 from this census.**

Reproduction (PowerShell, repository root):

```powershell
.local/toolchain/python-3.13.15/python.exe tools/cs/ctx-publish-sets.py --self-test
.local/toolchain/python-3.13.15/python.exe tools/cs/ctx-publish-sets.py `
  --generated .local/generated/default --calls .local/re/probe/race-summary.json `
  --binary out/build/android-arm64-release/libmain.so `
  --objdump-executable C:/Users/neri/AppData/Local/Android/Sdk/ndk/29.0.14206865/toolchains/llvm/prebuilt/windows-x86_64/bin/llvm-objdump.exe `
  --output .local/codex-cs/ctx.json
```

The self-check covers a callee reading a caller's volatile `r6`, a write
before a call, a conditional write, a partial write, recursion and an
unresolved indirect call. No generated code is changed.

## CS-0.3: driver capabilities

**Extension gate passes literally on the Deck; graphics pipeline switching
does not, 2026-10-17.** Standalone `tools/cs/vulkan-probe.cpp`, built from
project `ef46d6c4` plus the probe, using SDK `79d3e6f`'s Vulkan headers.
It queries advertised extensions and their complete feature/property
structures with `vkGetPhysicalDeviceFeatures2` and `Properties2`. It does
not execute generated commands. Zero fields for an absent extension mean
not queried, not a driver-returned limit. Full JSON: `vulkan-{multivac,deck,odin,mac}.json`
in `.local/codex-cs/`.

| Device / actual driver | EXT DGC / feature | Pipeline execution-set limit / pipeline-binding stages | NV DGC / shader groups | Placed map: placed / range / reserve; alignment |
| --- | --- | --- | --- | --- |
| Multivac, RTX 4080, NVIDIA 581.08 | yes / yes; dynamic layout yes | 16,384 / `0xFF` (graphics and compute) | yes / 16,384 | absent |
| Steam Deck LCD, RADV Mesa 24.3.0-devel `aef01ebd12` | yes / yes; dynamic layout yes | 4,096 / `0x20` (**compute only**) | absent | yes / no / yes; 4,096 bytes |
| Odin 2 Portal, Adreno 740, Turnip Mesa 26.3.0-devel `a995eaeda4` (installed V37) | absent | unavailable | absent | yes / no / yes; 4,096 bytes |
| Minivac, M4 Pro, MoltenVK 1.4.1 used by the game | absent | unavailable | absent | absent |
| Astra | not measured: no Astra in `adb devices` or the reachable mDNS endpoints (those identify as RG Rotate and Shield TV) | unknown | unknown | unknown |

The EXT maximum sequence counts are 4,194,303 on NVIDIA and 1,048,576 on
RADV; token limits 32 and 128; token offsets/strides `UINT32_MAX` on NVIDIA
and 2,047/2,048 on RADV. Both report input modes `3`, transform feedback
and multidraw-count support. RADV's general stages mask is `0x3FFF`, but
the **pipeline-binding** mask is only `0x20`, and shader-binding mask zero.
NVIDIA reports `0xFF` for all three stage masks. General DGC support is
therefore insufficient to authorize the proposed graphics execution sets
on the Deck. The Odin needs the existing recorder fallback. Do not assume
a newer Mesa's features from its extension name on an installed driver.

`tools/cs/metal-probe.mm` separately allocated a two-command render ICB
on the M4 Pro with `inheritPipelineState=NO`, built a pipeline with
`supportIndirectCommandBuffers=YES`, and bound it in both commands.
Allocation and binding succeeded (`metal-mac.json`); GPU execution and a
compute-generated sequence were not tested. MoltenVK's extension result
must not be inferred from native Metal support. The Vulkan loader initially
returned `VK_ERROR_INCOMPATIBLE_DRIVER` without its ICD manifest; querying
the exact game's `rexglue-artifacts/libMoltenVK.dylib` directly succeeded.

On the Odin, the standalone binary uses the game's adrenotools namespace
hooks with a read-only copy of the **installed** driver, SHA-256
`b6d445f512d15bb94be3d46bb2e2d27f604f161bf7400f32ed6008de59844c7f`.
It runs in `/data/local/tmp/cs-stage0`, not in the player's state. The
hooks need `libc++_shared.so` beside them; the first attempt without that
dependency failed to load, then passed after copying it into that private
directory. No driver or player configuration was changed.

Build with C++20 and `-O2`, including
`thirdparty/shiftglue-sdk/thirdparty/vulkan-headers/include`:
Clang 20.1.8 on Windows; WSL clang with `-ldl -static-libstdc++
-static-libgcc` for the native Deck executable; NDK r29 clang with
`--target=aarch64-linux-android33 -static-libstdc++ -ldl -llog` plus the
existing `libadrenotools.a` and `liblinkernsbypass.a` and adrenotools include
directory for Android. Desktop/Deck take an optional loader path. Android
takes `driver-directory/ hook-directory/ library-name` for the custom
driver. Metal builds with `clang++ -fobjc-arc -framework Metal -framework
Foundation`. All probes exit nonzero on API/load failure.

The distinction between general DGC and pipeline binding follows the
[Khronos DGC specification](https://docs.vulkan.org/spec/latest/chapters/device_generated_commands/generatedcommands.html).

## CS-0.5: placed device-memory mapping

**Pass on both yardsticks, 2026-10-17.** The extended standalone probe
(`bc124685` plus `tools/cs/placed-map.h` and `placed-check.comp`; same
drivers and SDK headers as CS-0.3) allocated 536,870,912 bytes of
host-visible, host-coherent `VkDeviceMemory` and bound a storage buffer.
It first reserved `[0x200000000, 0x220000000)` with `PROT_NONE` and
`MAP_FIXED_NOREPLACE`, verified that it owned that exact range, then called
`vkMapMemory2KHR` with `VK_MEMORY_MAP_PLACED_BIT_EXT` and the reserved
address. The returned address matched. This is a whole-allocation map,
requiring no `memoryMapRangePlaced` feature.

The CPU wrote all 134,217,728 words with an index-dependent pattern. The
compute shader read **every word** in sixteen 32 MiB descriptor ranges
(respecting `maxStorageBufferRange` and dispatch limits), accumulating
mismatches in a separate coherent result buffer. HOST-to-COMPUTE and
COMPUTE-to-HOST barriers plus a host fence wait guard the result. Each
device returned zero mismatches. The probe unmapped with
`VK_MEMORY_UNMAP_RESERVE_BIT_EXT`, released the reservation and destroyed
its allocations. These tests never attach to the game or its save.

| Device | Allocation / checked bytes | Memory type / flags | Result | Evidence in `.local/codex-cs/` |
| --- | ---: | --- | --- | --- |
| Deck LCD / RADV `aef01ebd12` | 536,870,912 / 536,870,912 | 2 / `0x6` (visible, coherent; **not device local**) | 0 mismatches | `placed-deck.json` |
| Odin / installed Turnip `a995eaeda4` | 536,870,912 / 536,870,912 | 0 / `0x7` (device local, visible, coherent) | 0 mismatches | `placed-odin.json` |
| Multivac / NVIDIA 581.08 | not attempted: extension absent | unavailable | unsupported | `placed-multivac.json` |
| M4 Pro / MoltenVK 1.4.1 | not attempted: extension absent | unavailable | unsupported | `vulkan-mac.json` |
| Astra | not reachable | unknown | untested | CS-0.3 |

A negative-control shader deliberately reports the first word as wrong
while checking the same entire range. Both devices reported exactly one
mismatch and exit status 2 (`placed-{deck,odin}-negative.json`). Thus the
zero counts are not from an unexecuted dispatch or an unread result buffer.
No latency or bandwidth claim is made from these single functional tests.
RADV's first matching type is system/GTT memory, so this does not prove
that a particular device-local heap can replace the mirror without a
bandwidth or residency cost. Guest aliases, page permissions, write watches
and CPU/GPU lifetime synchronization remain untested. CS-0.4 is still
required before CS-4.

Compile `placed-check.comp` with the existing glslang tool:

```powershell
out/build/glslang-tool/StandAlone/glslangValidator.exe -V --target-env vulkan1.1 tools/cs/placed-check.comp -o .local/codex-cs/placed-check.spv
```

Add `--placed <shader-path>` to the CS-0.3 executable's arguments. The
placement/reservation code is implemented for Linux/Android; unsupported
devices are only queried. The reservation uses no overwriting fixed map
until the probe has successfully reserved and checked its own range.
See the [Khronos placement contract](https://docs.vulkan.org/refpages/latest/refpages/source/VkMemoryMapPlacedInfoEXT.html).

On multivac (Windows 11 Pro `10.0.26200`), a placeholder plus
[`MapViewOfFile3(MEM_REPLACE_PLACEHOLDER)`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3)
exists for a data/pagefile section handle. That does **not** establish a
route for an arbitrary D3D12 allocation: a D3D12 shared-heap handle is not
documented as such a mappable section, and `ID3D12Resource::Map` does not
take a requested host address. Microsoft's
[`OpenExistingHeapFromFileMapping`](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device3-openexistingheapfromfilemapping)
provides a special diagnostic system-memory heap from a section, with
resource/flag restrictions; it is not a general export-and-remap guarantee
for the game's GPU allocation. No D3D12 code was run. The plan's placeholder
route remains a platform-specific hypothesis, not a pass from this Vulkan
test.

## CS-0.4: true guest completion latency

The SDK's default-off, hot `gpu_true_fence_completion` probe submits and
waits for host GPU work on the recorder thread before `EVENT_WRITE_SHD`
fence stores, enabled scratch-register writebacks, command-stream
interrupts and `WAIT_FOR_IDLE`. Vulkan uses its existing submission-fence
wait, which first waits for the submission worker to have submitted the
fence; D3D12 uses its existing queue completion wait. Failure refuses the
guest signal. The existing `FlushCpuVisibleResults` only flushes resolve
readbacks, so it was not a general GPU completion wait. The ring read
pointer still describes decoding progress; it is not changed into a GPU
completion marker. This is a synchronous latency probe, not an asynchronous
completion scheduler or a shared guest/GPU arena.

**Gate failed, 2026-10-17.** The SDK implementation is commit `4d78764` on
`main`, on project source `e8bbbb81` (no subsequent application-source
change). Native Release builds use the existing base generated tree with
frozen codegen. Routes
`tools/cs/routes/cs04-{race,free}-ab.fh1test` toggle only this cvar and the
perf A/B marker. The race uses 300-frame windows from route frame 6000;
free roam uses 300-frame windows from frame 1800. Both use the pinned
`appdata-2026-09-27` seed (profile SHA-256
`CC8951E814DBC750AAC5C204772BEF84094847273849F216B1DF7462CDC314E4`),
copied into a private state for each run. Free roam remains parked; the
race drives. The race uses `fh1-gauntlet-entry-sync`'s longer button presses;
free roam holds the handbrake after entry. No builds ran during routes.

All measurements below are Vulkan, 1x, vsync off, with the same build on
both sides: Odin 2 Portal/installed Turnip V37 and Steam-launched Deck
LCD/RADV at the 60 limit; Ryzen 7 5800X/RTX 4080/NVIDIA 581.08 desktop at
the 120 limit. Deck ancestry proves a Steam launch, its power profile was
`auto` and gameplay clocks were 1,040-1,600 MHz. The SDK's D3D12 path was
compiled on Windows but not measured. Source, build logs and binary
fingerprints are `cs04-build-*-final.log`, `cs04-local-binaries.json` and
`cs04-deck-binaries.sha256` in `.local/codex-cs/`. The build directories'
older sidecar JSON files were stale after direct CMake rebuilds; their
October 15/16 revision/hash fields are **not** the provenance of these
runs. The fingerprint files and build logs are. The exact Android APK is
retained as `cs04-probe.apk`.

`tools/cs/summarize-fence-ab.py` uses the NN in-run method: drop the first
boot/loading window, discard the first 30 frames of each remaining window,
require 60 retained samples, then pair adjacent opposite windows. No
frame-time outliers are removed. Race results have five pairs, free roam
six; the side aggregates also include the final unpaired window. Means
and p99 use `frame_time_us`; slow frames here means over **20 ms** on all
devices. Counts, draw rates and every window are in
`cs04-{odin,deck,win}-{race-ab5,free-ab1}-summary.json`.

| Device / route / run | Mean ms, off → on | Change | p99 ms, off → on | Frames over 20 ms, off → on |
| --- | --- | ---: | --- | --- |
| Odin race / `race-ab5` | 16.68 → 20.27 | +21.49% | 17.29 → 24.42 | 0.30% → 53.61% |
| Odin free roam / `free-ab1` | 16.68 → 23.08 | +38.37% | 17.26 → 27.56 | 0.19% → 98.69% |
| Deck race / `race-ab5` | 16.77 → 48.21 | +187.52% | 20.77 → 57.33 | 1.64% → 99.54% |
| Deck free roam / `free-ab1` | 16.84 → 48.69 | +189.20% | 21.41 → 59.97 | 1.52% → 99.60% |
| Multivac race / `race-ab5` | 8.39 → 12.91 | +53.82% | 9.98 → 17.07 | 0.04% → 0.23% |
| Multivac free roam / `free-ab1` | 8.45 → 13.17 | +55.93% | 11.01 → 16.73 | 0.03% → 0.08% |

Paired frame-time costs (mean ± SE, ms): Odin race `3.59 ± 0.19`, free
`6.33 ± 0.12`; Deck race `31.68 ± 0.93`, free `32.02 ± 0.65`; desktop
race `4.70 ± 0.20`, free `4.76 ± 0.24`. The GPU-thread fence-wait counter
increased on the Odin race from 0.049 to 14.48 ms per frame and on the
Deck from 0.108 to 33.11 ms, confirming that the treatment awaited actual
host submissions. Draw counts on the race differed by +1.2% on Odin and
-3.2% on Deck, much smaller than the measured frame loss.

Controls `race-aa1` and `free-aa1` run the corresponding `*-aa` routes with
completion **off on both sides**, preserving the marker schedule. A/A
paired differences, ms ± SE: Odin `0.00023 ± 0.00017` race,
`0.00051 ± 0.00037` free; Deck `0.048 ± 0.050` race,
`-0.0048 ± 0.0125` free; desktop `-0.0025 ± 0.123` race,
`-0.0093 ± 0.096` free. All aggregate mean differences were under 1%.
The largest absolute A/A p99 shift was 2.32 ms on the Deck race, against
the treatment's 36.56 ms. Each device's raw A/A summary is retained too.

All twelve qualified A/B and A/A routes reached their scripted stop with
no hang or device loss. The existing race-HUD checker passes all six race
captures (`cs04-hud-checks.json`), and inspection of pre-treatment and late
race/free-roam captures found no new corruption. The fixture's car-select
thumbnails already show noise before treatment; that is not attributed to
true completion. The old free-roam
fixture's generic 55 Hz presentation / 80 Hz simulation floors reject
some runs, including controls capped at 60; those post-run failures are
retained, not called passes. They are not the CS-0.4 gate. Early `race-ab1`
to `race-ab4` attempts are excluded: incompatible output waits in a
wall-time script, a precreated Android output directory, missing Deck
shader storage, a short-press route that stayed in free roam, and an
unsuccessful brake setup that selected reverse. Only the later race-HUD
qualified route supplies race numbers.

This synchronous **whole-prefix** host-fence wait is conservative: it
also stops recording while the queue completes. The results reject this
implementation against the unchanged 3%/p99 gate; they do not prove that
asynchronous or stage-specific retirement must cost as much. They do
not authorize a shared arena. The diagnostic cvar remains off by default,
and CS-4 is held pending a different completion design and a new probe.

## CS-0.1: ordered session pilot

The default-off SDK pilot (`cs_session_mode=1` record, `2` replay,
`cs_session_path` filename, both restart-only) records a total order of
boundary observations. Mode 1 refuses an existing file. Mode 2 feeds back
recorded guest timebase, system-time, uptime and controller-state values;
it validates identities, kernel results, I/O results/digests and each PM4
hash. The first mismatch exits with status 86 and an expected/actual
boundary tuple. It does not continue with unrelated values. The same
binary is used for record and replay.

The log covers XThread starts, single/multiple/signal-and-wait requests
and results, event/semaphore/mutant signaling, timer APC firings, XFile
read/write status, size, offset and content digests, GPU fence writes and
interrupts. XThread-backed workers get their kernel thread ID; other host
threads use tag zero. I/O is reissued against the same immutable game and
pinned initial save, with results checked, rather than copying game
content into the recording. This is narrower than replaying arbitrary
external I/O. Directory queries, network results, host vblank scheduling,
host thread-pool arbitration, inline guest atomics and fast critical
sections are not fully intercepted. Wait logging **observes** ordering;
it does not force the host scheduler to reproduce it. Initial clock
epochs and the timer queue's host deadlines are not virtualized. These
are explicit limits of the cheap pilot, not claims that nondeterminism
outside the hooks is absent.

Every decoded PM4 header and payload, including IB links, nested buffers
and zero padding, contributes to a 64-bit FNV-1a hash, closed at `XE_SWAP`.
A separate count records the dwords in the same frame. This hashes packet
memory at decode entry, rather than merely counting draws or final
registers; concurrent mutation after that snapshot is not modeled.
The log flushes at every frame. `tools/cs/read-session.py` emits
counts and hashes, never input or I/O contents. Full guest-memory hashes
at every kernel synchronization were not added to this pilot; a dirty-page
snapshot design remains part of CS-1.

`tools/cs/session-self-test.cpp` links the real runtime without a game.
It records then replays a clock value and a 16-byte input state despite
different live values; boundary-order and PM4-hash negative controls exit
86; recording over the same file exits 86 and preserves it. The reader's
self-check rejects malformed/truncated records and oversize payloads.
This separates a broken log format from a real session-order divergence.

The game route `tools/cs/routes/cs01-race.fh1test` uses the qualified
Gauntlet entry and records from boot, with 60 wall seconds between the
`gauntlet-driving` and `gauntlet-end` captures. GPU true-completion stays
off. The recording and replay each start from a new private copy of the
same seed as CS-0.4.

**Gate failed, 2026-10-17.** Project source `c6333e00` (application C++
unchanged from `0f8f20b2`), SDK main `40666b3`, frozen base codegen, native
Release Windows and Android builds. Both use Vulkan, 1x, vsync off and a
60 fps game cap. Device/driver identities are those above. Builds finished
before routes started. Exact binary hashes are in `cs01-detail-binaries.json`;
APK SHA-256 `80253c185dd182358d19f22e6307ba81adb283e4cf458986140bae937dceab88`.
Build logs `cs01-build-{win,android}-detail.log` and
`cs01-build-linux-detail-retry.log` record the rebuild. The old generated
build sidecars still have stale metadata; they are not revision evidence.

Each device's `cs01-record2` completed the route. Both start/end capture
pairs show the race HUD and a 60-second race-clock interval
(`cs01-record2-captures.png`, `cs01-record2-hud.json`). These are recordings
from boot through the race, so the totals below include startup. Two
independent replays, `cs01-replay2` and `cs01-replay3`, each use a fresh
private seed copy and the **same binary and record2 reference** on that
device. They fail closed at the first identity/order mismatch:

| Device | Recorded bytes / boundaries | Recorded duration / PM4 frames | Replay2 first mismatch, zero-based | Replay3 first mismatch | Verified equal PM4 |
| --- | ---: | ---: | --- | --- | --- |
| Multivac / RTX 4080 | 1,082,406,224 / 27,056,475 | 161.179 s / 9,614 | 18: uptime expected, system-time actual | 5: uptime expected, system-time actual | 0 frames, 0 s |
| Odin / Turnip V37 | 985,542,720 / 24,634,907 | 164.159 s / 9,555 | 1: uptime expected, system-time actual | 3: uptime expected, system-time actual | 0 frames, 0 s |

All four actual/expected tuples have host-thread tag zero, key zero and
zero payload size. The mismatch is **event order**, not an observed PM4
hash mismatch or a differing returned time value: replay substitutes clock
values only after the boundary identity matches. On Windows the wrapper
reports intentional exit 86; Android's flushed runtime log records the
same fail-closed path. Expected/actual tuples and boundary indices are in
`desktop/cs01-replay{2,3}.state/logs/runtime.log` and
`odin/cs01-replay{2,3}/logs/runtime.log`. Trace summaries and per-frame
hashes are `cs01-{win,odin}-record2-summary.json`; raw references have the
same prefix and `.bin` suffix. Raw traces are local only.

Source inspection explains why scalar playback is insufficient: the kernel
updates its guest timestamp bundle from a 1 ms **host** repeating timer
(`xboxkrnl_module.cpp`), while guest system time is also queried during
XThread construction (`xthread.cpp`). Their startup interleaving is not
controlled. The log does not retain query call sites, so these particular
call paths are an inference from the startup context, not a captured call
stack. The observed class is the differing order of clock-boundary types.
The broad global clock hook also includes host work tagged zero; a future
oracle must distinguish that work from guest queries.

Initial `record1/replay1` attempts had the same early order failure
(Windows boundary 4, Odin 26), but detailed tuples went only to stderr,
which Android did not retain. The logger was fixed and both recordings
repeated before using the table above. No record/replay pair crosses a
binary change. Real-runtime positive playback, order/hash negative controls,
exclusive-create protection and disabled-mode no-file checks pass with the
final runtime (`cs01-self-test-detail.txt`); release-contract tests: 40 pass.
The full tools suite before the logging-only correction: 534 pass, 6 skip,
111 subtests. No performance gate is inferred from recording overhead.

This is a first-divergence census, **not an exhaustive discovery of every
source in the race**. Replay never reaches its first PM4 comparison, so
later scheduling, input, I/O, memory and GPU equality remain untested. No
memory hashes were collected. Do not claim a 60-second deterministic
session or authorize CPU/GPU rewrites against this pilot as an oracle.


A full CS-1 design needs the following before PM4 equality can serve as an
oracle. These are coverage gaps identified from the implementation, not
additional experimentally observed mismatches after the first failure:

| Source | Pilot coverage and required design |
| --- | --- |
| Host scheduling | Log order only; deterministic execution grants must arbitrate thread starts, wait returns and signaling. A log mutex orders observations, not the guest instructions between them. |
| Time | Returned scalar values only; use a virtual epoch and shared logical clock for timer deadlines, sleeps, vblank, GPU interrupts and their delivery order. Host polling must not consume guest clock records. |
| Identity | Kernel thread IDs and numeric boundary keys; use stable logical thread/object IDs and query-site identities, including host workers currently tagged zero. |
| Guest shared memory | No interception of inline atomics/fast critical sections or arbitrary races; deterministic scheduling plus dirty-page snapshots at synchronization points is needed. No memory-equality claim was tested here. |
| I/O | XFile operations and content digests observed, actual I/O reissued; capture external results, directory/metadata queries, network and entropy inputs, and isolate writes. Identical pinned files do not cover arbitrary I/O. |
| Input | Controller values replayed at intercepted calls; wall-time route/UI events still need a logical schedule and call identity. |
| GPU | Decoder packet snapshots, fence writes and interrupts observed; virtualize completion/vblank order and retain the memory each packet consumes. A 64-bit PM4 hash alone is not a guest-state proof. |
| Timers | APC firing observed but host deadlines and dispatch not controlled. Neither trace recorded a `timer_fire` event; that path has no device replay coverage. |

Stage 0 does not implement that scheduler, memory oracle or reference
interpreter. Failing this pilot rejects the cheap ordered-value replay
premise, not the feasibility of a deliberately deterministic runtime.


## Round 2

### CS-0.2: optimistic traffic ceiling

The broader all-context ceiling does **not** reject the 15% gate. On the
Odin, `r2-ctx-regs4`, a pinned-seed 60 fps Vulkan/1x race, the optimistic
ABI ceiling estimates are **23.72% render, 25.44% simulation, 29.59% hot
FMOD mixer**. Their sampling-only one-sided 99.95% upper limits are
24.24%, 25.90%, 30.62%. These are deliberately generous deletion ceilings,
not achieved savings or permission to start CS-2. The exact census remains
to be completed; the lower round-one deferral numbers cannot reject it.

The recording has 592,415 retired `instructions:u` samples, period 500,000,
zero reported losses, over 55.0011 s beginning after `gauntlet-driving`.
Per-thread hot samples: render TID 5178 75,042; simulation 5168 95,174;
mixer 5189 21,916. Three other `82FB4AF8` threads have 178, 9 and 5 samples
and are retained separately, not averaged into the mixer. Start/end captures
show the race HUD. Total identified ctx traffic plus unknown instructions
is about 31–33%; the ABI model removes part of that ceiling.

The profile's source is parent `2aa969a4`, SDK `39a5bcf` (full source SHA in
`round2/cs02-measured-source.json`). The final SDK `430a065` only corrects
the diagnostic's explicit native TID: Android's `Thread::system_id()` was
a pthread value, so this recording is attributed by the correct native TID
already present in the runtime log prefix. No behavior or codegen changed.
Use the archived `cs02-debug-probe.apk` and its extracted libraries under
`round2/cs02-measured-libs`, not a later rebuilt shared library. The matched
`libmain.so` SHA-256 is
`3c3777d890fe644a9a751fd91867e890632adcd528e2e7c3dea15ffc98ff0da0`.

`tools/cs/ctx-traffic-ceiling.py` decodes each sampled instruction with its
captured user registers and tests effective memory addresses against all
logged `PPCContext` ranges. Android top-byte tags are removed. Unknown
binaries/operands, literal loads and adjacent 64-byte accesses are all
granted as removable. `context-layout.cpp`, compiled on Windows and Odin,
agrees on size 2688, f0 offset 344 and v0 offset 608. No game memory or
instruction listings are emitted by the analysis.

`ctx-abi-model.py` solves transitive read-before-write sets for 76,764
emitted functions including named save/restore helpers. Unresolved calls
read r1–r10, r13, f1–f13 and v1–v13. Known bodies supply their own reads;
the existing ABI-poison r6 dependency is included, with r6 also treated as
an output of `823F2ED8`. Returns demand r3/r4, f1–f4, v1–v3 and preserved
GPR/FPR/VR/CR/FPSCR state. This ceiling additionally grants full kills for
partial assignments, volatile kills at unresolved calls, and non-register
state elision. A may-cache CFG analysis grants ambiguous branch/loop cases
as deleted; only proven required imports/publications are retained. Pairs
count as one host instruction and retain that instruction if a demanded
component survives. There is no spill charge. These relaxations can enlarge
the ceiling, never establish an achieved saving. Sampling uncertainty does
not cover skid, model error or platform transfer.

The desktop `desktop-ctx-regs-route` also completed the same race with
per-thread register/PC snapshots (`thread_sampler --ips 1`). Its EXE hash
matches the recorded build. However, SuspendThread PCs repeatedly land in
blocked waits while cycle deltas describe earlier work. The apparent
4.77/6.94/9.21% cycle-weighted ctx shares (mixer/simulation/render) are **not
retired-instruction ceilings** and are excluded from the gate. Native WPR
capture requires an elevated process, unavailable to this session. Raw
samples and the failed attribution are kept rather than presented as proof.

Evidence: `.local/codex-cs/round2/cs02-odin-abi-cfg.json`, raw perf data and
dump, matched library hashes, HUD checks and `cs02-model-debug.json`.
Earlier `*-abi-*` outputs without the CFG/opaque-call corrections and outputs
using rebuilt libraries are exploratory and not gate evidence. The reader
and ABI-model self-tests cover r6, partial writes, an escape after an earlier
store, TBI, repeated imports and a paired store with one demanded component.
Android's profiling wrapper rejected `--no-unwind`; the accepted run uses
`run-as` with a debuggable APK and an 8-byte stack capture. A realtime-clock
attempt failed; the accepted instruction recording uses the default
monotonic clock. Both failures are retained. No live save was used.



### CS-0.2: strict follow-up and unresolved exact census

After the ceiling cleared 15%, `ctx-strict-model.py` continued the analysis
with transitive may-write and must-write summaries, fixed-point CFG
read-before-write, and a matched AArch64 import/publication census. It
keeps partial writes, unknown memory operands, unknown calls and all return
state; opaque register-reference helpers retain all state. Forward cache
facts intersect at joins, and backward demand follows every known CFG
successor. This avoids the optimistic model's may-cache joins, partial
kills and branch elision. No replacement code is emitted.

On the same `r2-ctx-regs4` samples and matched `libmain.so`, the analyzed
subset is **0.468% render (268 load + 83 store samples /75,042), 0.319%
simulation (270 + 34 /95,174), 0.680% mixer (148 + 1 /21,916)**. These are
model census estimates, **not an exact net host-instruction count or a
certified performance lower bound**. The strict source scan covers 76,764
bodies including named helpers, 48,101 indirect sites and 58,299 opaque
sites. No sound call-site vtable resolution is available; dynamically seen
targets are not a proof that other targets cannot occur. Source SHA-256 is
`f73cb4edadf3461d014c18601b66bb28b1ef0b2c6f15aa155fe46628465c4613`.

**Blocked / gate unestablished, CS-2 HOLD.** The remaining gap is material:
the 23.72/25.44/29.59% ceiling clears the gate, while the strict subset
cannot decide it. Restricting return demand to ABI state or assuming all
writes occur would shrink this gap without proving it. An exact net count
still requires call-site return demand and read/write proofs for opaque
escapes, plus charging the imports/publications introduced by moving a
store across a call. The machine census retains ambiguous aliases and does
not emit that transformed variant or its register allocation. Neither this
number nor round one's deferrals may reject CS-2. No exact deletion result
has been established; this part of Round 2 remains incomplete. The desktop
retired-instruction profile also remains unavailable without an elevated
PMU capture; its suspend-PC snapshots are excluded, as described above.

Evidence: `round2/cs02-strict-source-v2.json`, `cs02-strict-census.json` and
self-tests for partial writes, conditional must-writes and repeated imports.
The earlier `cs02-strict-source.json` predates opaque-reference handling
and is exploratory only. Keep the accepted optimistic ceiling separate
from this stricter, incomplete attempt. Completing a compiler or a session
scheduler to validate these assumptions would be Stage 1 and was not begun.

### CS-0.3: optional pipeline-run census

The existing frame census does not preserve draw order: it aggregates
configurations and their counts into windows. Pipeline-switch count and
draw-run length are therefore **unavailable from that census**. No Deck
per-pipeline batching saving is inferred from the extension query or from
distinct shader pairs. An ordered stream of final pipeline IDs at each
draw would answer the optional question; no new census run was added.
See [native frame contract](native-renderer/NATIVE_FRAME_CONTRACT.md#gaps-and-unknowns).


### CS-0.1: per-thread replay and shared-memory order

**Round 2 result: external-event capture does not decide shared-memory
ordering. CS-1 needs execution scheduling.** This replaces the round-one
capture failure as the design evidence. No Stage 1 scheduler was built.
The final full race replay verifies **zero PM4 frames / zero seconds**;
earlier iterations `r2-boot9` and `r2-boot13` verified one frame each, not a
race. Odin replay was conditional on desktop success and was not retried.

All runs use multivac, RTX 4080/NVIDIA 581.08, native Windows Release,
Vulkan, 1x, vsync off, 60 fps, the immutable `appdata-2026-09-27-winwarm`
seed and a new private state per run. `r2-race1-record` completed the
160-second route: the HUD clock advances 00:18.510 to 01:18.526 between
`gauntlet-driving` and `gauntlet-end`, 60.016 seconds. The trace contains
**3,387,155,130 bytes, 60,832,197 events, 71 streams and 9,525 PM4 frames**
(overall duration 161.3749725 s, including startup). These are counts of
that capture, not replay equality. `r2-race1-summary.json` holds the census.

Measured source: root `9d7d9d07`, SDK `67bb7fb`, plus the exact dirty diffs
saved by `run-session.py` under each run name. `r2-race1-binaries/` and
`r2-boot21-binaries/` retain the exact EXE/runtime/GPU DLL and SHA-256
manifests. Every record/replay pair uses the same binary. The final SDK
capture checkpoint is `4ed1cc7`; it incorporates these fixes. Local
GetTickCount/read/store instrumentation was backed up with hashes, applied
only to native definitions, and restored after the captures. Those
instrumented binaries remain archived. Rebuilding the ordinary tree does
not reproduce their observations without explicitly applying the tools.

The V2 format has one file per stable guest thread ID, with tagged host
roles for timestamp, vblank, GPU, recorder and audio workers. Each event
contains kind, thread, sequence, site/key, value, payload length and host
relative time. Replay consumes each stream independently; it does not
impose one global event order. Returned inputs are fed back; observed
PM4 hashes/word counts and diagnostic memory loads are compared, never
substituted. Callback delivery is paced by recorded host time. This pacing
cannot determine how many guest instructions execute before a delivery.

Capture and replay were expanded until the first failure was an observed
shared-memory value, rather than a missing boundary. The classes found:

| Class | Correction or disposition |
| --- | --- |
| Global inter-thread event order | Replaced by per-thread sequence streams; a two-thread unit replay deliberately reverses host arrival order. |
| Time sources and call identity | Uptime, system time, performance counter/frequency and PPC timebase reads captured at stable module-relative sites. The guest GetTickCount helper reads the shared timestamp bundle directly, so it also needs the local generated hook. |
| Timer/vblank/APC/IRQ delivery | Tagged delivery, callback address/argument, registration and GPU MMIO reads captured. Timestamp writes and vblank are separate roles. No timer-fire or APC event occurred in the final full race; those paths have no route coverage. |
| Kernel wait outcomes | Capture result and wait request separately, replay timeout/success choice and alertable delay result; unfinished waits at the recording boundary are allowed. Semaphore release has its own event kind. |
| Kernel identities | Replay published slots, thread IDs, virtual CPU selection, allocation addresses and TLS layout/data. Lazy guest-memory objects use their guest address as identity; private handles do not consume published slots. |
| Contended lock implementation | Per-object acquisition grants replace a global ticket that deadlocked. Probe-only Rtl critical sections use a CAS wait and preserve ownership/recursion while avoiding private waiter-event allocation differences. This changes enabled-probe bookkeeping; it is not a performance result or an unchanged scheduler. |
| Files and input | Feed file read bytes, status/count/position, query/directory metadata and controller state/capabilities/keystrokes. Check write payloads and feed write status/count. File-open side effects, arbitrary devices, network and entropy are not claimed exhaustively captured. |
| Host hooks and audio | Capture camera/crowd scaling, render-job throttle result, step-backpressure decisions, native voice state, audio pump/callback selection and built PCM. Other optional host-clock features are off in the seed. XMA direct-memory completion remains a coverage limitation. |
| Other observed startup boundary drift | Some iterations reach a vblank signal where replay reaches the next timebase read (for example `r2-boot20`); the precise shared queue/capture cause was not established. Do not label these all fixed or proven races. `session-iterations.json` retains each first failure. |
| Ordinary shared job-state poll | **Scheduling required.** The final first value mismatch is a guest load, with matching prior per-thread boundaries. Read/write evidence below identifies the completion transition crossing the poll. |

The first value divergence in `r2-race1-replay` is render thread `0x13`,
sequence **8,588**, site `82412688:+40`, object `0x2E094000`: capture reads
**3**, replay reads **4**. `sub_82412688` polls job state bytes +40/+41
outside the job critical section. `sub_8243CB38` takes the lock at +4 and
rechecks only after the polling helper reports readiness. Worker helper
`sub_82E43EA8` publishes byte +40 under that lock.

`r2-boot21` adds observed stores, retaining a last-writer diagnostic. Its
first mismatch is the inverse: render `0x13`, sequence **8,595**, captured
**4**, actual **3** at `0x2E094028`. The reference worker `0x10` writes 3 at
sequence **19**, time **949,111,100 ns**, then 4 at sequence **92**, time
**950,273,500 ns**. The reference reader sees 4 at **950,274,600 ns**.
Replay's last matching store is still worker `0x10` sequence 19, value 3,
actual time **953,093,500 ns**. Both writer values are ordinary guest
stores; the reader does not acquire their lock. The diagnostic does not
force either value. Independent per-object grants therefore leave this
poll on opposite sides of completion. The byte is internal shared state,
not a missing external I/O or clock return that can simply be fed back.
Replacing the load's value would be memory-order replay and must also
order its dependent accesses; it would no longer test external-event
capture alone. This does not establish what the original console scheduler
did, nor prove that every possible later divergence is known. The observer
stops at the differing load before a PM4 comparison: it does not prove
that tolerating this polling drift would necessarily change PM4. It does
show that strict per-thread event streams do not determine that poll or
the subsequent clock-call count without shared-memory/execution ordering.

A final repeat removes **every memory observation**, keeping only the
GetTickCount shim. `r2-race-no-watch`, parent `ce7580fb`/SDK `200bfdb`, uses
the same route and seed and the same binary for record/replay. Its HUD
checks pass at both ends of the 60-second race. The recording contains
3,125,594,685 bytes, 55,407,669 events, 71 streams and 9,546 PM4 frames over
161.2399935 s including startup; **zero `guest_memory` events**. Replay
still stops before its first PM4 frame, render `0x13` sequence **8,511**:
expected per-object lock grant `0x12E094004`, ticket **7**; actual timebase
read in `sub_82462030`, called through `82462050`, `82462098`, `82E4A030`,
`82E4B240`, `82412688`. The lock is again at job `0x2E094000 +4`.
The polling/work-selection path therefore also diverges in the external
event stream without an observer stopping on a memory value. It is not
merely the earlier observation assertion. No PM4 equality is inferred
beyond the successfully compared prefix (zero here); an oracle that
intentionally tolerates polling drift would require a different clock/log
contract and separate validation. Exact binaries/hashes, trace summary,
HUD checks and stack-to-function metadata remain under this run name.
The clock shim was restored and the normal Windows build rebuilt afterward.

CS-1 must choose deterministic guest execution quanta (instruction/basic
block or a reference interpreter), or record and enforce shared-memory
read-from/happens-before order, including inline atomics, fast lock paths
and polling loops. Stable object identities, virtual time and interrupt
injection must share that execution schedule. Validate dirty memory at
synchronization points as well as PM4. Kernel-call grants alone are too
coarse. The prototype did not collect a complete memory oracle or classify
unreached later races; those remain explicit design work.

Validation: the real-runtime two-thread positive replay, disabled no-file,
order/hash negative controls and existing-path protection pass
(`session-unit-final.json`, exits 0/0/0/86/86/86). Reader and instrumentation
self-tests pass. Seven locally patched generated partitions were restored
byte-for-byte using their guarded backups before performance builds.

### CS-0.4: asynchronous timeline completion

The Round 2 probe is separate from the synchronous drain. Arm it at start
with `gpu_async_fence_probe=true`; hot-toggle
`gpu_async_fence_completion`. Both default false. Vulkan timeline support
is enabled before device creation only when armed. At a guest fence or
scratch write and command interrupt, the command processor ends the current
submission without waiting and enqueues a timeline signal after that work
in the submission worker FIFO. A dedicated host thread waits on the
semaphore, then performs the guest write or interrupt. It has guest thread
TLS for interrupt dispatch. The producer never waits on that semaphore.
Off transitions preserve callback FIFO order until older delayed writes
retire. Existing resolve-readback synchronization is retained on both sides.
A backend without the armed timeline worker refuses hot mode rather than
silently reporting early completion. This is a diagnostic, not a shared
arena implementation.

SDK `200bfdb`, parent checkpoint accompanying this text. Native Windows
Release builds pass. The earlier 12-second pinned desktop smoke route
completes with the worker armed and completion enabled
(`round2/async-smoke1`, root `9d7d9d07`/SDK `67bb7fb` plus the archived
working changes; this predates the mode-counter log added in `200bfdb`). This is
only a smoke check, not the latency gate. Handheld race/free-roam A/B and
A/A measurements follow with the separate `cs04a-*` routes. The synchronous
Round 1 drain results above remain historical and cannot decide this mode.


**Round 2 timing verdict: FAIL; CS-4 rejected at its Stage 0 gate.** The
asynchronous mode also exceeds +3% mean frame time and worsens p99 on both
yardsticks. No gate, cutoff, outlier rule or route input was changed to
obtain this outcome. The probe remains off.

Matched source: parent `e98117f4`, SDK main `200bfdb`, frozen base generated
tree (local diagnostic patches restored), native Release Android and
Linux-amd64-v3. Odin uses the installed Turnip V37/Adreno 740 driver (SHA
`b6d445f512d15bb94be3d46bb2e2d27f604f161bf7400f32ed6008de59844c7f`);
Deck uses RADV 24.3-devel under Steam/game mode at its normal power settings.
Both use Vulkan, 1x, vsync off, a 60 fps cap, the same pinned
`appdata-2026-09-27` profile and private warm states as Round 1. The Deck
uses its prior private warm derivative of that seed. No measured route
ran during a build. Exact APK `round2/cs04a-probe.apk` SHA-256
`0811b0e55682b2f6684ff00123822463889d7f4164eab1aa5f2cdf148ceac12b`;
its library hashes are in `cs04a-probe.json`. The Linux executable is
`37bdfd278d4fbd20218dee3087e03715dffa935d7f284e8d60fecafda1044b43`,
retained with corrected source/hash sidecar in `round2/async-linux-build`.
Windows secondary coverage is the smoke route described above, not a
latency measurement.

Runs: `.local/codex-cs/{odin,deck}/r2-async-{race,free}-{ab,aa}1`.
A = immediate completion; B = asynchronous timeline retirement. Each
process is armed at startup, so both sides share worker/feature setup.
Hot windows alternate every five wall seconds after race/free-roam entry.
The unchanged NN summarizer drops the first window, discards 30 settling
frames per window, requires 60 retained rows, and retains every subsequent
frame, including hitches. Five paired race windows and six free-roam pairs;
pooled means/p99 also retain the final eligible unpaired window. Frame
counts differ because B runs slower. Counts are actual perf rows, not
60 Hz route ticks. These are within-process comparisons, with same-binary
A/A marker controls; no cross-build improvement is claimed.

| Device / route | Mean A → B (ms) | Change | p99 A → B (ms) | Frames >18 ms A → B | Samples A / B |
| --- | ---: | ---: | ---: | ---: | ---: |
| odin / race | 16.666 → 20.942 | +25.66% | 17.046 → 28.296 | 0.148% → 92.754% | 1349 / 1242 |
| odin / free | 16.692 → 21.885 | +31.11% | 17.068 → 27.421 | 0.494% → 99.639% | 1618 / 1385 |
| deck / race | 16.800 → 38.162 | +127.16% | 21.830 → 47.591 | 3.723% → 100.000% | 1343 / 605 |
| deck / free | 16.875 → 37.462 | +122.00% | 21.542 → 50.118 | 5.587% → 99.861% | 1593 / 720 |

Paired per-window B−A mean ± standard error (ms): Odin race
**4.511 ± 0.892**, free **5.238 ± 0.190**; Deck race **21.505 ± 0.429**,
free **20.438 ± 0.276**. A/A pooled mean changes, race/free: Odin
**−0.00087% / −0.01109%**, Deck **+0.56121% / +0.03889%**. A/A p99 changes
are +0.477/−0.267 ms and +1.745/−0.323 ms respectively; p99 has ordinary
scene noise, far below the B increases. Draw counts also vary with the
scene: race A→B averages 2524→2736 on Odin and 3227→3376 on Deck;
free 3592→3522 and 3745→3667. These differences are retained, not normalized
away to change the frame-time gate.

Runtime logs confirm actual asynchronous work. At a Deck race transition,
8,464 timeline signals were issued and retired over one B interval, with
zero pending callbacks at the off switch. `CS_ASYNC` mode-transition lines
retain issued/retired/pending counts for the other windows. The B mean
`gpu_thread_fence_wait_ns` counter is zero in all four routes; the new
completion path has no producer wait on its timeline. Existing resource
reuse/readback synchronization is not redefined by that observation.
The submitted signals and additional submission splits are part of this
specified design's cost; this is not a measurement of a hypothetical
zero-overhead completion mechanism.

Every timing script reaches its stop and the game exits normally; all
race HUD assertions checked separately on Odin and by the Deck runner.
The Deck free A/B outer runner correctly fails its generic present floor
(48.476 Hz <55); free A/A instead fails its legacy simulation floor
(58.088 Hz outside 80..500), despite near-60 fps rendering. Those failures
are retained and are not called generic QA passes. Android's direct app
runner does not apply the Python cadence validator. The measured 3%/p99
gate above fails independently of those generic checks. Extra enabled
correctness runs are excluded from this timing table.

Detailed rows, >20 ms shares, pairs and frame counts:
`round2/cs04a-summary.json` and `cs04a-{odin,deck}-{race,free}-{ab,aa}.json`.


Correctness-only repeats `r2-async-{race,free}-on1` on both devices enable
the mode after world entry and leave it on. All four reach the script stop.
Their final race/free-roam captures were inspected with completion still
enabled: no new corruption observed. All six race runs' driving and end
captures pass the race-HUD check (12 images), and all 12 app scripts report
completion (`round2/cs04a-correctness.json`). The enabled free Deck repeat
also fails the outer cadence validator; it is not a generic QA pass.
No hangs or corruption were seen on these routes; this is bounded route
coverage, not a proof about every game mode. These extra runs are excluded
from the A/B table.

Validation/restoration: native Windows, Android and Linux Release builds
pass; tools tests **534 pass, 6 skip, 111 subtests**; runtime replay positive
and negative controls and analysis self-tests pass. The original Odin APK
is restored by exact SHA-256, all 17 player-user files have identical
hashes, both pinned seed profile hashes are unchanged, and all seven local
generated patches match their original backups. Hash lists are compared
by filename (their raw traversal orders differ). The Deck's normal
PinyonShift entry has the SDK `200bfdb` build; only the owned CSStage0
shortcut/link/metadata were removed. Private evidence states remain.
`round2/restoration.json` and `restoration-deck.txt` retain the checks.
AppData was never used as a writable run root. No pushes; no Stage 1 work.

Round 2 recommendations: **CS-1 redesign** around execution/shared-memory
order before claiming an oracle; **CS-2 HOLD** because its exact 15% count
is still unestablished (the ceiling does not reject it); **CS-3 HOLD** its
graphics DGC architecture on these drivers, with per-pipeline batching
unmeasured; **CS-4 reject** at the asynchronous completion latency gate,
despite accepted placed-mapping support. CS-0.3 and CS-0.5 stand as accepted.
