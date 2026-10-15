# Next-level research: code generation, reverse engineering and runtime

Researched 2026-10-12 at `dev` `d4ba71a` (ShiftGlue `c5a124c`). This page
answers three questions:

1. Which big projects would take Pinyon Shift furthest from here?
2. Can more reverse engineering make the recompiled code more specialized
   and much faster?
3. How would we build a XenonRecomp/XenosRecomp-style toolchain without
   ReXGlue's costs, and lower resource use?

It extends [RECOMP_OPTIMIZATION_SURVEY.md](RECOMP_OPTIMIZATION_SURVEY.md)
(#456) and the [performance backlog](PERFORMANCE_BACKLOG.md) without
repeating them. Nothing was built or run for this page. The numbers come
from four places:

- counts over the generated tree (`.local/generated/default`) and the
  Release objects (`out/build/win-amd64-release`);
- the repository's recorded benchmarks and perf CSVs;
- the SDK source;
- primary sources for other projects.

Every estimate is marked as one. The full research notes are kept locally
in `.local/backlog-research/next-level-2026-10-12/`, which is not
committed.

Licences limit what we take:

- XenonRecomp, XenosRecomp and plume (MIT), and Xenia, Canary and Edge
  (BSD-3): code with attribution.
- UnleashedRecomp and Rayman Origins Recomp (GPL-3): ideas only.
- Projects without a licence: ideas only.
- TiP-Recomp: its author does not consent to AI use of the work, so it
  was not analysed.

## Summary

- **Don't start over with a hedge-dev-style stack. Rebuild ShiftGlue's
  code generator around XenonRecomp's one good idea.**
  - **That idea:** every function has a single entry, so guest
    registers can live in host registers.
  - **What blocks it here:** ShiftGlue gave 56,860 of FH1's 76,499
    functions a resume `switch` (342,683 interior entry points). That
    switch is our addition, not upstream ReXGlue's. It exists only
    because the runtime abandons the host call chain when a guest fiber
    switches stacks (`KeSetCurrentStackPointers` calls `XThread::Reenter`
    only when the thread has a guest fiber).
  - **The way out is already half built:** the SDK has host-fiber
    versions of the XAPI fiber functions, but FH1 maps none of them.
  - **Why not a hand-written runtime:** FH1 needs exactly what
    UnleashedRecomp's lean runtime lacks (fibers, MSVC exceptions, two
    DLL modules, XMA, STFS DLC, the v4 title update). Our GPU path is
    already native.
- **About 43-46 % of the host instructions in the generated code are
  bookkeeping, not the game's work:**
  - 24 % plain moves to and from the `ctx` register file;
  - about 14 % the `0xE0000000` physical-view select;
  - 4.7 % byte swaps.

  This is a static count over a sample of 12,021 functions. The two
  hottest audio routines are 54-57 % bookkeeping.
- **The cheapest large win is the physical-view select.**
  - **Why it exists:** on Windows, desktop builds map guest views with
    `MapViewOfFileEx`, which needs 64 KB alignment, so the `0xE0000000`
    view can't start at its 4 KB offset and every access adds `0x1000`
    back.
  - **The fix:** placeholder views (`MapViewOfFile3`, Windows 10 1803+)
    accept 4 KB offsets, and the SDK already calls them in its
    non-desktop branch. On 4 KB-page Linux and Android kernels the offset
    is always 0.
  - **Evidence:** removing the select only for r1-based accesses already
    cut Odin guest instructions 17-18 % (#431).
- **The two largest wins sit in different places:**
  - **Low-end devices:** register locals behind single-entry functions,
    plus the select removal, are the largest lever on guest CPU time.
    (Since measured: correct non-volatile locals make the code 42-66 %
    larger and the desktop guest code 20-27 % slower; NL-1.4 in Progress.)
    That matters on the Odin, the Deck, low-spec PCs, and for heat and
    battery.
  - **Desktop 1x:** the limit is not guest code. Three host threads
    re-read and re-derive command lists that are 96 % identical every
    frame: about 18 ms of CPU per 8.4 ms frame, about 2.2 cores.
    Compiling the title's display lists once (DR-5.3, then DR-3.1, DR-4.1
    and DR-4.2) is the lever there. XenosRecomp's register-file, bindless
    shader interface is the piece of it worth taking.
- **For speed, the useful reverse engineering is not function names.**
  It is four kinds of fact the generator can apply everywhere:
  - register signatures and ABI conformance;
  - memory classes (private, shared, polled, GPU-visible);
  - indirect-call targets;
  - which code can be on a stack at a fiber switch.

  Get them from an "RE build" of the game itself, with probes in the
  generator's macros, and from a local Ghidra workspace. Feed them to the
  generator through a versioned knowledge base. Dynamic data may choose
  what to specialize; only static proof or an exact guard may permit it.

## Where the cost is today

### Generated code (static, `win-amd64-release`)

| Measure | Value |
| --- | --- |
| Functions, guest instructions | 76,499; 3,651,030 |
| Partition source | 261 MiB, of which 24.5 % is per-instruction comments |
| Host `.text` | 75 MB, about 20 host bytes per 4-byte guest instruction |
| `ctx` memory operands | 26.8 % of host instructions (24.4 % plain moves; 60 % of them stores) |
| Physical-view select | about 13.9 % of host instructions, on 70.3 % of guest accesses (725,461 sites) |
| `bswap` | 4.7 % of host instructions (964,062 swaps in source) |
| Resume switches | 56,860 functions, 342,683 cases; `dispatch_address` cleared on entry in all 76,499 |
| Calls | 296,172 direct, 48,100 indirect, 31,828 tail calls; 342,942 `ctx.lr` stores; 49,841 save/restore helper calls |
| Flush-mode toggles left | 38,248 |
| Weak aliases | 76,499: no guest function can be inlined |
| Dispatch tables | about 35 MiB committed and zeroed (main table 11.3 % used); `PPCFuncMappings` 6.7 MB of writable `.data` |
| Recomp compile | 28-52 CPU-minutes; the critical path is one 27,503-instruction function (`sub_8241A370`, 54-112 s) |

An ABI liveness model over 12,018 of the sampled functions shows what
register locals could remove. The model keeps today's semantics except
for calls, which follow the PowerPC convention.

| Model | `ctx` traffic vs today | Host instructions saved |
| --- | --- | --- |
| Perfect forwarding, today's call semantics | -21 % | 5.4 % |
| ABI at calls, resume switch kept | -33 % | 8.2 % |
| ABI at calls, no resume switch | -47 % | 11.8 % |
| No resume switch, and no `ctx.lr` store where re-entry is impossible | -55 % | 13.9 % |

Only 1.2 % of register writes are dead. The waste is writing every
result to memory and reading it back. The resume switch is what blocks
the load side: removing it halves the reloads after calls, from 177 k to
82 k.

These are static shares. They don't weigh instructions by how often they
run. Dynamic counters (top-down analysis on the Deck, `simpleperf` on the
Odin) are item NL-0.3.

### Host threads (1x race, 120 fps limit, RTX 4080)

Frames with at least 5,000 draws, from the 2026-10-07 low-spec CSV:

| Thread | CPU a frame |
| --- | --- |
| GPU Commands (PM4 decoder) | 8.38 ms, including up to 2 ms of `WAIT_REG_MEM` yield-spinning |
| GPU Recorder | 6.82 ms, about 1.3 µs a draw |
| GPU Submission | 2.97 ms |
| Title render thread | 2.36 ms, plus a 3.72 ms fence wait |
| Audio | about 28-29 % of a core |

The frame median is 8.43 ms.

### Memory

| Item | Size |
| --- | --- |
| Process resident | 2.0-2.1 GB at every scale, so render targets don't drive it; no breakdown by region exists |
| VRAM | 0.9-1.13 GB at 1x, 3.3 GB at 2x with MSAA, 4.3 GB at 3x |
| Executor surfaces | 265 MB at 1x, 2.0-2.4 GB at 2x/3x; sized to the EDRAM period and never freed (635 MB at 3x since NL-3.5) |
| Physical heap | 512 MB committed at start, mapped three times |
| GPU shared-memory mirror | 512 MB; real RAM on Turnip, which can't make it sparse |
| Textures | stored twice: the tiled guest copy and the untiled host copy (146-602 MB) |

## The ReXGlue inheritances, and what replaces each

| Inheritance | Why it exists | Cost here | Replacement | Item |
| --- | --- | --- | --- | --- |
| Registers written through to `ctx` | interior re-entry, hooks and imports read `ctx` | 26.8 % of host instructions | locals synced by the PowerPC ABI, as #467 did for CR | NL-1.4 |
| Interior resume switch (ShiftGlue's addition) | guest fibers abandon the host call chain | irreducible loops; doubled reloads; 342,683 table entries | guest fibers on host fibers, so functions are single-entry | NL-1.2 |
| Physical-view select | 64 KB view alignment on Windows; 16 KB-page kernels elsewhere | about 14 % of host instructions | exact 4 KB mapping; compile-time 0 on 4 KB kernels | NL-1.1 |
| Weak alias + `noinline` on every function | host code overrides by defining the symbol | no inlining, even with LTO; 7.5 MB of dynamic symbol tables on Android | strong symbols except a declared override list | NL-1.5 |
| `volatile` + `bswap` on every access | MMIO, cross-thread flags, one exact model | blocks forwarding; 4.7 % `bswap` | plain stack accesses, then stack slots as locals; MOVBE | NL-1.6, NL-1.8 |
| One host pointer per guest instruction | O(1) lookup of every resume address | 35 MiB committed, 11 % used | entries for function starts only, 4-byte entries, const mappings | NL-1.9 |
| PM4 decode and per-draw derivation every frame | Xenia's general GPU model | about 2.2 cores at 1x | compile display lists once, with a register-file, bindless ABI | NL-3 |
| XMA as MMIO hardware | Xenia models the audio chip | the trap is about 7 points of the audio thread | call the decoder at the guest XMA API | NL-4.1 |
| Kernel objects behind the global lock and a handle table | Xenia's object model | #416 stalls on Android | atomics in guest dispatcher headers with `WaitOnAddress`/futex | NL-4.3 |
| Physical heap committed up front; surfaces never freed | inherited | 512 MB commit; 2 GB of VRAM at 2x/3x | commit on demand; surfaces sized by role and evicted | NL-4.4, NL-3.5 |

## What to take from XenonRecomp and XenosRecomp

**Lineage.** ReXGlue is not a git fork of XenonRecomp. It is a rewrite
that keeps:

- XenonRecomp's disassembler tables and configuration schema;
- `PPCContext`, the first VMX helpers and the flush-mode emitter;
- the jump-table classes and the function-table formula.

It wraps them in a phased analysis and Xenia's runtime. ShiftGlue's
analysis is ahead of XenonRecomp in several ways:

- MSVC exception tables, RTTI vtables and DLL modules;
- guaranteed tail calls and AArch64 fences;
- exact FP corner cases, which FH1's collision code depends on.

| Take | Why |
| --- | --- |
| Single-entry functions and all register-local options (XenonRecomp, MIT) | XenonRecomp's README credits removing the save/restore helpers as its largest single gain, and reports about 20 MB smaller code and "several ms" faster frames, with no method. Our CR-only version measured -11/-12 %. |
| Mid-asm hooks that pass registers by reference (XenonRecomp) | Lets hooks coexist with register locals without a full sync |
| A register-file, bindless shader interface with one specialization mask (XenosRecomp, MIT) | The runtime half of XenosRecomp. It removes the per-draw constant gather, about 1,130 of 5,800 recorder cycles a draw, but only pays together with compiled display lists (NL-3) |
| One embedded, compressed, hash-indexed shader blob built at install | Vulkan translates every shader again at each start, and setup plays a 125 s route to warm caches. An offline pack from the 3,349-program disc corpus shortens setup and start. Driver pipeline compiles remain. |
| Pipelines built when the work is created (UnleashedRecomp idea, GPL) | FH1's analogue of asset loads is display-list creation: build pipelines then, not on first draw |

| Don't take | Why |
| --- | --- |
| UnleashedRecomp's hand-written kernel, o1heap, flat 4 GiB | FH1 needs fibers, exceptions, DLL modules, XMA, STFS DLC and the title update; the guest allocator is 0.05 % of a race (#468) |
| D3D-call hooking over plume | Only 42 of about 5,000 draws a frame go through the title's emitter; the rest are prebuilt lists |
| XenosRecomp itself | It ignores `CondExec` conditions, vertex-fetch formats, LOD and bias, and 1D textures, all of which FH1 uses; it failed to compile FH1's shaders (PB-10) |
| XenonRecomp's FP shortcuts | No FMA, `dp_ps` dot products: FH1 compares `vmsum` results |
| `skip_msr` | Guest code masks interrupts to guard per-CPU data |
| A direct LLVM-IR backend, for now | Everything ranked here can be expressed in C++ under Clang 20. Revisit only if `-ftime-trace` shows the front end dominating the build (NL-0.3) |

## Proposed projects

Effort: S is days, M a week or two, L longer. Every codegen item keeps
the project's gates:

- the save hash, `expect-simulation-time`, route images and frame
  replays from pinned seeds;
- Odin per-thread guest instructions at the 30 fps limit, four or more
  runs per build;
- cycles, not only instructions, for front-end work: `perf stat` on the
  Deck, `simpleperf` on the Odin.

Each item that is kept or rejected goes on the docs site in the same
change.

### NL-0 Safety net and baseline (do first)

| ID | Work | Why | Effort |
| --- | --- | --- | --- |
| NL-0.1 | **ABI poison build.** After every call returns, overwrite the dead volatile `ctx` fields with poison and assert that the non-volatile fields are unchanged. Run the route corpus. | Proves the calling convention on FH1 before NL-1.4 relies on it. It runs with today's codegen and names any function that breaks the ABI. No published translator does this check. | S |
| NL-0.2 | **Lockstep codegen verify.** Generalize `guest_native` verify: build the reference codegen of sampled functions into the same binary, run both on cloned state every Nth call, and compare live registers and written memory. | The gate for NL-1.1, NL-1.4 and NL-1.6 | S-M |
| NL-0.3 | **Missing measurements:** resident memory and commit by region (VMMap, `/proc/<pid>/smaps`); time to the first guest instruction, including table zeroing and 419 k registrations; `-ftime-trace` on a few partitions; dynamic instruction mix and front-end stalls (top-down analysis on the Deck, `simpleperf` i-cache and iTLB on the Odin) | Ranks NL-1.8, NL-1.9 and NL-4.4, and settles the C++-vs-IR question | S |
| NL-0.4 | **Import the Canary/Edge PPC test corpus** (571-581 tests against our 167) and triage it. Known gaps: `vcmpbfp` with a NaN (Edge `e4b13738c3`), `vmaxfp`/`vminfp` with a QNaN, and `vmaddfp`, which rounds twice. | Codegen semantics coverage before large codegen changes | S-M |
| NL-0.5 | **Decide the generated-unit flags.** The SDK's `-ffp-model=strict` and `-fno-strict-aliasing` apply only to its own sources, not to Pinyon's recomp units. Without strict FP, LLVM may move FP operations across MXCSR writes. `-fasync-exceptions` is on although no SEH scope is emitted. | Correctness first. Measure each flag's cost. | S |

### NL-1 Code generation v2 in ShiftGlue

The expected gains for this track are estimates, except where marked as
measured.

| ID | Work | Evidence and expected value | Effort | Risk |
| --- | --- | --- | --- | --- |
| NL-1.1 | **Remove the physical-view select.**<br>• Windows: reserve with `VirtualAlloc2(MEM_RESERVE_PLACEHOLDER)`, map each view with `MapViewOfFile3(MEM_REPLACE_PLACEHOLDER)` at its exact 4 KB offset, and make `REX_PHYS_HOST_OFFSET` `0u`.<br>• Linux and Android: a build option that emits `0u` and refuses to start on a kernel with pages above 4 KB. The APK and the Deck build are made per device, so the option can follow the target.<br>• macOS arm64 (16 KB pages): keep the offset, but as an unlikely branch, which costs two instructions on x86-64 against four or five today; check the AArch64 output, where Clang may turn it back into a select.<br>• Check the write-watch and protection arithmetic, which uses `host_address_offset`, and the GPU's physical views. | The select is about 14 % of host instructions and 17 % in the hottest functions. Removing it for r1 accesses alone measured -17/-18 % Odin guest instructions. Estimate: -10 to -25 % on Windows and 4 KB Android. | S-M | Low-medium |
| NL-1.2 | **Guest fibers on host fibers, then single-entry functions.**<br>• Map FH1's XAPI fiber functions to the SDK's existing `[rexcrt]` fiber group (`src/kernel/crt/threading.cpp`). The only two callers of `KeSetCurrentStackPointers` are `sub_830ED900` and `sub_830ED910`, the fiber switch (recorded on the site's Executable page, `site/findings/executable.toml`).<br>• Confirm with the `stack.reentry` trace that `Reenter` no longer fires on the route matrix.<br>• Find any other interior entries: host `Execute` at a registered interior address, exception continuations.<br>• Emit resume labels only for that proven set, possibly none. | Removes 56,860 switches, 342,683 cases, 76,499 dispatch clears and most table registrations. Loops become reducible, so LICM, unrolling and vectorization see them. It makes `skip_lr` legal outside the remaining set. Enabler for NL-1.4: halves the post-call reloads in the model. | M-L | Medium-high |
| NL-1.3 | **CTR and XER as locals.** Both are dead across calls. `xer.so` is never set (0 overflow-form instructions, one `mtxer`, a context restore), so the SO copy in 192,632 compares folds to 0. | Removes the `ctx.ctr` store in 4,666 `bdnz` loops and dead carry stores. A cheap slice of NL-1.4. | S | Low |
| NL-1.4 | **GPR, FPR and VR locals synchronized by the PowerPC ABI for the non-volatile set, and by callee live-in and clobber sets for the volatile set**, generalizing #467. NL-0.1 showed the title reads callee-left volatile registers (see Progress), so "dead after a call" needs the callee's own code, which the generator has.<br>• Before a call: store the registers the callee (transitively, for direct calls; every volatile register for indirect ones) reads before writing, and the dirty non-volatile locals.<br>• After a call: reload the return registers and every volatile register the callee may have written; the rest stay valid in locals.<br>• Full sync only at hooks that take `ctx`, `setjmp`/`longjmp`, SEH and functions NL-0.1 flags.<br>• The save/restore helpers become no-ops. | Static model: -47 to -55 % of `ctx` traffic, 12-14 % of host instructions. XenonRecomp and every PPC JIT surveyed (Cemu, RPCS3, Xenia, Dolphin) keep registers out of memory. Estimate: -15 to -30 % guest instructions. Needs NL-0.1 and NL-1.2. | L | High |
| NL-1.5 | **Strong symbols except a declared override list**, so Clang and ThinLTO can inline. Hidden visibility on Android. A host definition missing from the list fails the link, so the list can't be silently incomplete. Then measure ThinLTO again: #464 measured it while LLVM still refused every guest-function inline (`InlineCost.cpp`, "interposable"). | 12,736 functions have 8 or fewer guest instructions. 7.5 MB of Android dynamic symbol tables. Estimate: 3-6 % (PB-3.6), more after NL-1.4. | M | Low-medium |
| NL-1.6 | **Stack.** First, the r1 fast path for the FP, update, sign-extend and vector forms (58,444 sites, about 10 % of the six-channel biquad). Then plain (non-`volatile`) r1 accesses. Then non-escaping frame slots as host locals in host byte order. | Literature: SecondWrite 1 → 6.5 % on optimized inputs; WYTIWYG shows promotion can also lose, so keep a per-function switch. | S, S-M, then L | Medium |
| NL-1.7 | **Ship PGO keyed by guest address.** Emit `#line` equal to the guest instruction offset and use sample PGO (`llvm-profgen`), so a profile survives codegen changes. CI builds one profile per release; generation is deterministic for the one accepted XEX. | Measured: -1.4 to -5.5 % per guest thread (#464). It stayed opt-in only because profiles broke on codegen changes. | S-M | Low |
| NL-1.8 | **Use the player's CPU.** The build already runs on the player's machine. On CPUs that have them, compile for x86-64-v3 (MOVBE fuses load and byte swap; BMI2, AVX2) behind the existing start-up guard. | `bswap` is 4.7 % of host instructions. Unmeasured: measure cycles on the Deck (Zen 2) and the 5800X. | S | Low |
| NL-1.9 | **Smaller and faster to build.**<br>• Optional disassembly comments: 24.5 % of the source.<br>• `sub_8241A370` split or built at `-O1`.<br>• `cold` or `-O1` for functions no route executes.<br>• Dispatch entries for function starts only, 4 bytes each.<br>• `PPCFuncMappings` const in `.rdata`. | Shorter first builds (20-60 min today) and about 35 MiB less committed memory | S each | Low |
| NL-1.10 | **Fold read-only image data.** At least 19,900 float-constant loads become literals, with a start-up hash of the folded ranges as the guard. | Small-medium | S-M | Low-medium |

Below the line until earlier items are measured:

- **Guest registers as host arguments** (`preserve_none`). Instrew measured
  1.96 → 1.69 of native, but those conventions have no callee-saved
  registers, which suits guest non-volatiles poorly. Measure after NL-1.4.
- **Plain heap accesses.** High risk: a guest data race becomes a C++ data
  race. Do it only with NL-2.3 memory classes and a chaos-timing build.
- **Guarded devirtualization.** No hot `bctrl` site is known yet; NL-2.3
  counts them.

### NL-2 Reverse engineering that feeds the generator

| ID | Work | Why | Effort |
| --- | --- | --- | --- |
| NL-2.1 | **A versioned knowledge base in `config/re/`** (TOML, keyed by base address) for functions, types, globals, memory classes, call sites and libraries. Each entry carries a confidence, its evidence and a v4 address resolved by `map-fh1-v4-addresses.py`.<br>• Import the RE record's 104 rows, the 73 mod entries and the 467 guest addresses that sit only in backlogs.<br>• A legal lint rejects instruction runs and hex blobs.<br>• The generator emits a name table, so profiles and crash logs read `sub_82438EA8 crt.pow`. | Today 606 guest addresses are scattered across docs and config, 139 of them in the record. No signatures, no types, nothing the generator can read. | S |
| NL-2.2 | **A local Ghidra workspace**, rebuilt headlessly from the player's own dump. It uses Ghidra 12.1 with the Xenon360 loader (Apache-2.0, VMX128) and applies ShiftGlue's function boundaries, switch tables and vtables plus the knowledge base. It lives in `.local/re/` and is never committed. LLM bridges (GhidraMCP) can draft names, which stay at "guess" until a route or hook confirms them. | Every finding is re-derived from generated C++ today | S |
| NL-2.3 | **An RE build** (`PINYON_SHIFT_RECOMP_PROBE`). Probes in `REX_FUNC_PROLOGUE`, `REX_CALL_INDIRECT_FUNC` and the memory macros record:<br>• per-thread call counts;<br>• per-site indirect-call targets;<br>• stack offsets touched;<br>• memory region classes and cross-thread sharing per cache line;<br>• field offsets typed by the RTTI vtable at an object's base;<br>• argument values;<br>• the LR of each MMIO store.<br>`harvest.py` merges route output into the knowledge base. | Turns the recompiled game into the RE instrument. It produces the facts NL-1.4, NL-1.6 and the plain-heap item need. | M |
| NL-2.4 | **Library identification.**<br>• Read the XEX static-library header: the SDK parses it, nothing uses it.<br>• Cross-match titles the player owns (Forza Motorsport 3 and 4) with BSim or BinDiff, in local databases only.<br>• No legal XDK signature set exists. | Native replacements of whole library families need identity and contracts | M |
| NL-2.5 | **The class hierarchy.** Extend `vtable_scanner` to read the RTTI hierarchy descriptor, which it reads but ignores today. | Devirtualization candidates; a type for each object in the field census | S-M |

**Gating rule.**

- Dynamic facts may choose what to specialize.
- Indirect targets, argument values and library replacements may be used
  behind an exact guard or a code hash with verify mode.
- Facts that can't be guarded need static proof plus a checking build that
  passes the route corpus: register signatures, memory privacy and resume
  pruning.

**First RE targets, in order:**

1. The ABI and stack-switch census (enables NL-1.2 and NL-1.4).
2. Memory sharing and polling (enables NL-1.6).
3. Indirect calls and classes on the hot threads: the scene walk and the
   job dispatcher.
4. The audio path:
   - the XMA register-write sites;
   - whether the reverb and biquad output reaches anything but the
     speakers. If not, an exact SIMD port is the wrong bar: a port checked
     by `audiocapture` signal-to-noise with the save hash unchanged
     becomes acceptable.
5. The simulation and job-worker call trees.

The allocator and the CRT string helpers are not targets (#465, #468).

### NL-3 GPU: compile the display lists once

These items are already deferred in the
[desktop renderer backlog](DESKTOP_RENDERER_BACKLOG.md). This research
confirms they are the desktop lever and adds the shader-interface piece.

| ID | Work | Why | Effort |
| --- | --- | --- | --- |
| NL-3.1 | **DR-5.3: compile each `IDirect3DCommandBuffer` once.** Hook the runner `82416A00` and compile at creation or close, so the decoder scales with lists (about 1,200 a frame), not dwords (1-1.8 M). | The decoder is 7.4-8.4 ms a heavy frame | L |
| NL-3.2 | **DR-3.1: an O(1) "unchanged since last frame" test** per subsystem: texture bindings, vertex and index ranges, tile ownership | Every replay attempt so far was slower because validating a draw cost as much as deriving it | L |
| NL-3.3 | **A shader interface in the XenosRecomp style.** The guest register file per stage, read by address; bindless textures; one specialization mask. Emitted as an offline SPIR-V pack built at install from the disc corpus. | The constant gather is about 1,130 cycles a draw. The pack also ends start-up re-translation and shortens the 125 s preparation route. Bindless alone measured ±1.5 % on NVIDIA, so it pays only with NL-3.1/3.2 | M-L |
| NL-3.4 | **DR-4.1 and DR-4.2: constants by address, then GPU re-execution** of compiled lists (secondary command buffers or descriptor buffers) | Ceiling probe: recorder 10.4 → 3.7 ms on the heavy race start | L |
| NL-3.5 | **Surfaces sized by role and evicted when idle (LS-4.3); VMA blocks of 64 MB** (skate3 `f7d808a`, BSD-3) | 2.0-2.4 GB of VRAM at 2x/3x; returns freed memory to the OS | M |
| NL-3.6 | **Pipelines built when a display list is created or rewritten**, decoded off the hot threads | First-launch stutter: 5.7 s over budget after the warm-up route | M-L |

### NL-4 Lean runtime pieces

| ID | Work | Why | Effort |
| --- | --- | --- | --- |
| NL-4.1 | **XMA at the API.** Hook the guest XMA register-write sites, found from the MMIO handler's LR log, and call the decoder directly. Decode off the guest audio thread with read-ahead. | `MMIOHandler::CheckStore` is 22 % of the Odin audio thread inclusive; the trap and dispatch part is about 7 points | M |
| NL-4.2 | **Audio fixes from Edge and Canary.**<br>• Pump the audio off the global lock (Edge `12e3b4223d`, #416).<br>• NEON `ConvertFrame` with x64 rounding parity: Android and macOS truncate today.<br>• The XMA packet-boundary and loop-start fixes. | Android stutters and audio-thread CPU; bit parity across platforms | S each |
| NL-4.3 | **Kernel objects in the guest dispatcher headers**: atomics plus `WaitOnAddress`/futex, as UnleashedRecomp does (idea). The interrupt callback runs outside the global lock. | Android only: restructuring the lock measured 0.34 ms a frame on desktop | M-L |
| NL-4.4 | **Commit the physical heap on demand; trim idle pipeline workers** | Part of the 2 GB resident; measure with NL-0.3 first | S-M |
| NL-4.5 | **Async file reads** (Edge `c6cc761676` and its follow-ups) | Only if NL-0.3 shows per-read stalls on the Deck SD card or Android storage; desktop reads total 91 ms a run | M |

### NL-5 Quick ports from Xenia forks

All are BSD-3; keep the Xenia headers on any ported file. Each was checked
against the SDK.

| Port | Source | Why |
| --- | --- | --- |
| Primitive-conversion cache invalidation compares against the wrong bound (`primitive_processor.cpp:1513`) | Edge `1b0e9d00ea` | A rewritten index buffer can draw with stale converted indices; FH1's quad and rectangle lists are converted |
| Invalidate unwatched pages on protect, decommit and release (`xmemory.cpp` `TriggerCallbacks`) | Edge `5ddf045a83` | Page state persists across frames since schema 26 |
| SPIR-V main-loop switch fall-through (`spirv_translator.cpp:1485-1505`) | Edge `f145711a4a` | An NVIDIA device loss; relevant to #388 |
| Scalar ALU swizzle with three-source vector ops (`translator.cpp:1336`) | Canary `92ada8ebc0` | Scan the shaders for the encoding first; bump the shader cache version. **Scanned: no FH1 shader has it, dropped (Progress).** |
| XInput subtype per device, with a per-slot wheel override | Canary `103257c5aa` | FB-2.1: the game sees a wheel. **Built, on by default since FB-2 was checked on a T248 (Progress).** |
| Deferred-overlapped delay 100 → 25 ms | Canary `8d2d80dfde` | About 0.1 s once at boot. **Ported.** |

A free-running `V_COUNTER` (Edge `9d93773228`) is worth a log check: if
FH1 reads it, it may relate to #381. **Checked: FH1 never reads it
(Progress).**

### NL-6 Player-facing: online play

[Dyotson/RecompiledForzaHorizon](https://github.com/Dyotson/RecompiledForzaHorizon)
(MIT, ReXGlue-based, created 2026-10-10) is the first known working FH1
online implementation. It reports matchmaking, Rivals, car clubs and
shared free roam, using:

- a UDP tunnel for the game's ports 1000 and 1001;
- virtual `0.77.0.N` peer addresses;
- a rendezvous and relay server;
- a "Turn10.Horizon" title-services endpoint.

It targets the base executable, so every address has to be re-derived for
v4, and its addresses are someone else's analysis: leads only
(docs/LEGAL.md). It also needs a server that we or the players would
host. Effort L. Whether to pursue it is a product decision, not a
technical one.

## Progress

Dispositions of the items started so far, with the evidence. Static counts
are over the 260 generated x86-64 objects of the Windows Release build
(FMA3 baseline), before and after the change, with the pinned Clang 20.1.8
and `llvm-objdump`.

| Item | Outcome | Evidence |
| --- | --- | --- |
| NL-1.1 Windows | **Done.** The runtime maps every guest view through a placeholder (`VirtualAlloc2`, `MapViewOfFile3`) at its exact file offset, so the `0xE0000000` view sits where it belongs and `REX_PHYS_HOST_OFFSET` is `0` on Windows. A Windows older than 10 version 1803 is refused at start with a message. | All 625,228 select compares are gone from the generated objects. Together with NL-1.3 (the two were generated together): host instructions 17,733,702 to 13,717,318 (−22.6 %), generated `.text` 74.97 to 59.68 MB (−20.4 %); byte swaps, flush-mode writes and vector reversals unchanged. The select's share by the four-instruction estimate was 14.1 %, so about 8 % of the saving is NL-1.3's. |
| NL-1.1 Linux, Android | **Done and measured on the Odin.** `PINYON_SHIFT_PHYSICAL_HEAP_4K_PAGES` (default on) compiles the offset to 0; `Memory::Initialize` refuses a kernel with larger pages. Every device in the lab uses 4 KB pages (Odin 2 Portal, Android 13; the Snapdragon 8 Elite tablets, Android 16; the Deck). | `getconf PAGESIZE` on the three Android devices: 4096. Per-thread instructions per second over the race window of `fh1-race-sustained` (`simpleperf stat --app studio.deimos.pinyonshift --per-thread -e instructions --interval 1000`, which works because the app is profileable; per-thread CPU time is not usable, since threads migrate between core types), both runs at the 60 fps limit (6,975 and 6,974 frames), one run each, medians: render thread 0.933 to 0.727 G/s (−22 %), simulation 1.532 to 1.168 (−24 %), audio 1.679 to 1.095 (−35 %, which includes NL-4.2's NEON frame conversion), whole process 7.36 to 6.13 (−17 %). The host-side decoder thread was unchanged within its spread (1.68 to 1.86 median, q3 5.5 both). The baseline APK (before all of this research) is `.local/android/pinyon-shift-odin-before-20261012.apk`; the new one carries NL-1.1, NL-1.3 and NL-4.2 but not yet NL-1.2. |
| NL-1.3 | **Done.** `ctr_as_local` and `xer_as_local` in both analysis files. | Counts above. Hooks that take `ctx` and `guest_native` verify read neither register. |
| NL-5.1 | **Ported** (xenia-edge `1b0e9d00ea`): a cached primitive conversion is dropped when any part of its index range is written, and a conversion in progress over a written range is not stored. | Correctness; the test compared against the range's end. |
| NL-5.2 | **Ported** (xenia-edge `5ddf045a83`): a guest protect-to-writable, decommit or release raises the GPU invalidation callbacks even with no watch armed, since page validity persists across frames. | Correctness. |
| NL-5.3 | **Ported** (xenia-edge `f145711a4a`): a translated shader's main-loop switch case jumps through the loop's continue block instead of falling into the next case, the pattern that lost NVIDIA devices. | Changes shader output; the Vulkan translation cache keys on the translator version. |
| NL-4.2 | **Ported.** The audio pump reads its client table under a mutex of its own instead of the global critical region, and the heap is never touched while it is held (xenia-edge `12e3b4223d`); ARM64 converts XMA frames and folds 5.1 to stereo with NEON, rounding and saturating as x64 does (`b899a97a7e`, `32177527fa`); a frame whose header crosses a packet boundary is counted (`adf56b76c4`), a loop start one bit short of a frame boundary is resolved to it (`5dd1cdbbf5`), and the work loop drains a partly delivered frame (xenia-canary `6bef1fbed1`). | Correctness and bit parity; the Android audio thread's cost is for the Odin to measure. |
| NL-2.1 | **Done differently.** The knowledge base is `site/findings/*.toml` (430 records with confidence and evidence, rendered by the site with an address index and `symbols.json`), which the repository already had. Added on top: `tools/re/kb.py` (`symbols` writes one address table with a names map; `check` verifies every `sub_X` a record names is a generated function start, base and v4; `lint` refuses disassembly listings and hex dumps), `tools/summarize-thread-samples.py --symbols` labels profiles with the recorded names, and `tools/tests/test_re_kb.py` runs the lint and the check. The two findings this research made (the fiber switch, XER and CTR) are recorded on the Executable page. | `check` found one record whose v4 field paired base and v4 addresses with an arrow, handled; the lint found none. |
| NL-0.1 | **Built and run; the ABI hypothesis failed.** `PINYON_SHIFT_RECOMP_ABI_POISON` generates the game with a check around every guest call (`rex/ppc/abi_poison.h`): the non-volatile registers are snapshotted before and compared after, and the volatile registers the ABI leaves dead at a return are overwritten with a value that names the register and the call site; an argument register still holding one at the next call is logged. | On `fh1-race-sustained` the non-volatile checks never fired (0 mismatches, two runs), but the build crashed on the simulation thread within two seconds: `sub_823F3048` calls `sub_823F2ED8` in a loop and sets r3-r5 but not r6, so the callee stores through whatever r6 its previous call left. The title does rely on callee-left volatile registers. **Consequence for NL-1.4:** non-volatile registers may live in locals synchronized by the ABI, but a call may not treat a volatile register as dead unless the callee's own code never reads it before writing it. The generator has the callee bodies, so it can compute each callee's live-in and clobber sets (transitively for direct calls, conservatively for indirect ones) and synchronize exactly those registers; the poison build, told the same sets, then checks the analysis instead of the ABI. The "argument still poisoned" log is noisy because it does not know each callee's arity (stale r5-r10 are reported at every call); the same sets fix that. |
| NL-0.5 | **Decided.** The generated units now compile with `-fno-strict-aliasing` (on) and without `-fasync-exceptions` (off, `PINYON_SHIFT_RECOMP_SEH` brings it back); `-ffp-model=strict` stays an option (`PINYON_SHIFT_RECOMP_FP_STRICT`). | Three hot partitions (the audio reverb's, the six-channel biquad's and the 27,503-instruction kernel's) compiled with each flag, no precompiled header: `-fno-strict-aliasing` produced byte-identical objects; `-ffp-model=strict` added 2.1 %, 1.5 % and 0.9 % host instructions; `-fasync-exceptions` added 0.3 %, 0.3 % and removed 0.8 %. No generated unit contains an SEH scope. |
| NL-1.8 | **Built as an opt-in variant**, not the default. `PINYON_SHIFT_CPU_BASELINE=v3` (preset `win-amd64-v3`, `build-preview.ps1 -CpuBaseline v3`) compiles for x86-64-v3 with a start-up guard for AVX2, BMI1/2, LZCNT, MOVBE and F16C. | Same three partitions: MOVBE replaced 20 % of the byte swaps in the two audio routines (677 and 714 `movbe` for 619 and 676 fewer `bswap`) and 0.6 % in the float kernel, for 0.8 %, 1.0 % and 0.1 % fewer host instructions. Too small statically to change the default; a cycle measurement on the Deck or the 5800X decides it. |
| NL-1.2 | **Done.** The five XAPI fiber functions (`ConvertThreadToFiber` `0x830EBC70`, `ConvertFiberToThread` `0x830EBD00`, `CreateFiber` `0x830EBD50`, `DeleteFiber` `0x830EBE30`, `SwitchToFiber` `0x830EBE90`; in v4 they sit 0xC1E80 higher, `0x831ADAF0` to `0x831ADD10`) are mapped to the SDK's host fibers through `[rexcrt]`, and the new generator option `interior_resume = false` emits no resume switch, no resume labels and no resume aliases (`RecompilerConfig::interiorResume`, on by default for other titles). The family is recorded on the site's Executable page. | Race route with `PINYON_SHIFT_REENTRY_TRACE=1`: all five hooks hit, no `reentry.transfer`, no `KeSetCurrentStackPointers` or `MmCreateKernelStack` import call, route passed at 119.1 fps median (116.0 before, run noise). Static, over the generated objects: host instructions 13,717,318 to 12,699,751 (−7.4 %), `.text` 59.68 to 54.15 MB (−9.3 %), 260 to 234 units; byte swaps and vector reversals unchanged. Cumulative with NL-1.1 and NL-1.3: 17.73 M to 12.70 M (−28.4 %). **Odin:** three alternating runs of the APK before and after (after also carries NL-1.5, NL-1.10 and the vector fixes), race window at the 60 fps limit: simulation thread 1.168/1.160/1.155 to 1.097/1.107/1.096 G instructions/s (−5.6 %, every run after below every run before); the render thread cannot be read from these runs, because the scene itself varied (953 to 1,503 draws a frame between runs of the same build, with the decoder thread following it), and per draw the render thread's medians were 10.5 K before against 11.1 K after, inside that spread. A render-thread comparison needs a scene-fixed route (replay) or many more runs. Other interior entries looked for: none found (exception continuations and host `Execute` always start at function entries). **Regression found by the v4 session:** `tools/port-fh1-v4-analysis.py` accepted the five base addresses for v4 (small thunks whose normalized bytes matched code at the same address), so 9488cb7's v4 build mapped five unrelated functions, the guest fiber switch still ran and, with no resume entries, the title screen failed to load; the fix (the v4 addresses above) is on `dev` since 2026-10-13. Lesson: verify a v4 mapping of a small function by its cross-references, not by its bytes. `skip_lr` is now legal everywhere; measured separately under NL-1.4. |
| NL-1.6 step 1 | **Done in the generator; no change on the platforms that map the view exactly.** `lfs`, `stfs`, `lfd`, `stfd`, `lwa` and `lha` with r1 as the base now take the stack path (58,310 of the 58,444 sites; the X-form stragglers stay). | Static count identical before and after on Windows (12,699,751 host instructions): since NL-1.1 the stack path and the general path compile to the same code wherever `REX_PHYS_HOST_OFFSET` is 0. The change matters only where the offset survives (macOS arm64 and other 16 KB-page kernels), to measure there. **Step 2 measured and not kept:** `PINYON_SHIFT_RECOMP_PLAIN_STACK` (off) compiles the stack accesses without `volatile`. Statically it removed 1.5 % of the host instructions (12,699,751 to 12,514,891) and 15,658 byte swaps (forwarded spills), but the race route ran slower on the 4080 desktop: 108 and 110 fps median against 117, 117 and 119 for the volatile build, with a worse p99 (21.5 ms against 13.8-19.3). The likely cause is Clang merging adjacent spill stores into wider ones that the guest's narrower reloads cannot forward from; not pursued. Step 3 (frame slots as host locals) stays open. |
| NL-1.9 | **Done, with two parts measured and dropped.** `PPCFuncMappings` is `const` (read-only data). With the resume aliases gone (NL-1.2) the mapping table holds 76,885 entries instead of 419,524, so the start-up registration loop is 82 % shorter. `disassembly_comments = false` drops the `// mnemonic operands` line before each instruction: the generated source shrinks from 253.4 to 186.6 MB (−26 %), but Clang's lexer is not where the build spends its time (timings below), so the comments stay on for readability (three matching partitions, with and without comments: 4.6/4.4, 4.3/4.4 and 4.5/4.3 s). **4-byte dispatch entries, dropped:** the table holds a host pointer per guest instruction (8 bytes) and is indexed directly by an indirect call; a 4-byte entry would be an index into a host-pointer array, one dependent load more on every `bctrl`, to save 14 of the 28 MB resident, so it is not worth the hot-path cost. **A cold tier, dropped for now:** functions no route executes could compile at `-O1`, but "no route executes" needs the probe build's call counts (NL-2.3) to be trustworthy, and the first-build time is dominated by the 234 units' optimization, which the per-unit timings show is not the comments. | `tools/summarize-startup.py`: "function table" to "xex loaded" (where the registrations happen) 0.239 s on the build before, 0.160 and 0.136 s on two runs after; the 28 MB dispatch table is unchanged. |
| NL-2.4 (first bullet) | **Done.** `tools/re/xex-libraries.py` reads the XEX2 static-library header; the result is a finding on the site's Executable page (25 libraries, XDK 2.0.21119, LIBCMT 2.0.11886, two compiler builds; XFFB and XINP2 present, which bounds FB-2.1's contract). | Three XEX files read; no code of the game needed. **Cross-match: dropped by the maintainer (2026-10-13); no dump will be supplied.** It needs Xbox 360 dumps of Forza Motorsport 3 or 4 that the player owns; on 2026-10-13 none was found on multivac's C:, D:, E: or J: or in the Mac mini's home folder (blindvac was offline). The only Forza image present is an original-Xbox Forza Motorsport ISO, an x86 binary from another compiler, which cannot cross-match PowerPC code. The tooling is ready: the Ghidra workspace (NL-2.2) runs BSim on local databases once a dump is supplied. |
| NL-5.4 (scalar swizzle) | **Dropped, measured.** Canary `92ada8ebc0` changes the scalar `b` component only when a two-component scalar operation is co-issued with a three-operand vector operation. | A decoder over the 12,846 disc shaders (`.local/native-renderer/fh1-disc-shader-corpus`): 478,372 ALU instructions, 54,659 two-component scalar operations, 143,939 three-operand vector operations, zero co-issued (the only scalar opcode ever paired with `mad`, `cnd*` or `dp2add` is `retain_prev`), so the port cannot change any FH1 shader. Recorded in the site's lessons table. |
| NL-5.5 (wheel subtype) | **Built, on by default.** `input_report_wheel_subtype` (SDL driver) reports `XINPUT_DEVSUBTYPE_WHEEL` with the force feedback flag for a detected wheel, and 900 degrees in the capabilities so the title picks its 900-degree mapping. F6 shows it as WHEEL MODE. | The title's wheel path is traced (FEATURE_BACKLOG FB-2.1) and was checked on a Thrustmaster T248: the subtype gives the title's wheel steering and button layouts. Only wheels see the change; gamepads still report subtype 1. |
| NL-5.6 (deferred delay) | **Ported** (Canary `8d2d80dfde`): the deferred-overlapped completion delay is 25 ms instead of 100. | Every route of this work ran with it; boot is a one-time saving too small to measure against run noise. |
| NL-5 `V_COUNTER` | **Dropped, measured.** FH1 never reads `V_COUNTER`. | New `gpu_log_register_reads` cvar logs the first guest read of each GPU register; a full race read only `CP_PROG_COUNTER` (0x044B) and `D1MODE_VBLANK_VLINE_STATUS` (0x1951). Edge `9d93773228` cannot matter here, and it is not the #381 lead. |
| NL-0.4 | **Done for the hand-written corpus; the generated corpus is staged.** xenia-canary `2372a54105` (2026-10-11): 254 new and 22 updated test files imported into the SDK's `tests/ppc/asm` (167 to 421 files, 1,480 to 2,541 cases); its 151 `instr__gen_*.s` files (167,636 hardware-recorded cases, 66 MB) stay out of the repository at `.local/ppc-tests/xenia-canary-gen` with Canary's own 28,713-case skip list, for a build that points the suite at them. Generator changes to take them: xenia's memory and float spellings, plain comments skipped, one translation unit per file, labels resolved per file, a skip list with reasons (Catch2 `SKIP`), the host FP environment reset per test. Five mnemonics the bundled binutils lacks are hand-encoded. Fifteen instructions the generator had never implemented (`vrlb`, `vaddcuw`, `vsubcuw`, `vavguw`, `vmaxuw`, `vpkpx`, `lvsl128`, `lvsr128`, `ldbrx`, `stdbrx`, `lmw`, `rotld`, `icbi`, `mcrxr`, `mtmsr`) now are; `vmaddfp` and `vnmsubfp` fuse the multiply-add. | Final run: 2,541 cases, 0 failures, 108 skipped (12,379 assertions) with a reason each (`tests/ppc/skip.txt`): 94 Canary cases whose expectations contradict their inputs (the whole load family, `fcmpo`/`fcmpu`, `fadd`/`fsub` cases, `lvx`, `lmw`, `ldbrx`), 10 reciprocal-estimate cases (`frsqrte`, `vrsqrtefp`: exact against 12-bit), `stwcx.`/`stdcx.` without a reservation (succeeds here), `mfmsr` (0x9030 on the console), `mffs` of the exception-enable bits, and `mcrfs`, `mfvscr`, `mtvscr` (unimplemented, unused by FH1). No wrong result was found in an instruction FH1 uses. **Generated corpus, first run** (a 1.37 GB `ppc_tests.exe`, 572 files, 2 min to run): 167,636 cases, 28,283 failed; 27,399 of those are in Canary's own skip list, so Canary fails them too, and 884 are ours alone. The 884: `vpkpx` 650 (unimplemented), `vminfp`/`vmaxfp` 166 (a NaN operand must be the result and `min(-0, +0)` is `-0`, where SSE returns the second operand), `vsl` 32 (the count is read from the wrong byte when the bytes disagree), `vrsqrtefp`/`frsqrte` 29 (negative inputs give a negative NaN here, the positive QNaN there; `frsqrte` rounded through `float` and overflowed for inputs below 2^-256) and `vexptefp` 7 (no clamp beyond the float exponent range). All, `vpkpx` included, are fixed in the SDK; `vsr` lost the carry between the two 64-bit halves and is fixed too. **Second run after the fixes:** 26,773 failed, 26,650 of them in Canary's list and 123 ours: `vminfp`/`vmaxfp` 100 (a denormal input must be flushed to a signed zero before the compare and a NaN result quieted; fixed next), `vrsqrtefp`/`frsqrte` 23 (the 12-bit estimate, not reproduced). `vcmpbfp` went from 891 to 330 (the rest are the `_cr_` forms: CR6 held the "all out of bounds" bit too; fixed next). **Final run** (after the vmaxfp/vminfp flush and the vcmpbfp. CR6 fix): 26,205 failed, 26,182 of them in Canary's list and 23 ours (the `frsqrte`/`vrsqrtefp` 12-bit estimates); 2,531 of the cases Canary skips pass here. The shared remainder is the `_cr_` record forms of the floating-point arithmetic (CR1 from FPSCR's exception bits, not modelled), `vnmsubfp`/`vmaddfp` (1,012 and 11,520, NaN sign and denormal cases of the fused form), and `vsl`/`vsr` with count bytes that disagree (hardware shifts per byte; the spec calls the result undefined). The 27,399 shared failures are dominated by the `_cr_` record forms of the floating-point arithmetic (CR1 copies FPSCR's exception summary bits, which neither implementation models), `vnmsubfp` and `vcmpbfp` with NaN operands (both bound bits set; fixed here) and `vpkpx`. The first triage also showed that FPSCR-writing tests leaked round-toward-zero into the tests after them, so the earlier passing count hid nothing but the later failures were partly the harness. |
| NL-0.2 | **Done.** The generator emits every function in `reference_functions`, and every Nth leaf function with `reference_sample_every`, a second time as `ref_sub_X`: the reference options (every register in `ctx`, no folding, calls through the thunk) with every store routed through a log (`rex/ppc/reference.h`, `push_macro`/`pop_macro` over the store macros). Functions a log cannot roll back are skipped (vector stores through raw addresses, atomics, `dcbz`, calls, the global lock). `pinyon_shift_reference.h` names them; `src/guest_native/reference_verify.cpp` defines the strong `sub_X` for each (the generator lists them as host-overridden so direct calls go through the thunk) and with `pinyon_shift_reference_verify=N` runs the reference copy on a copy of the registers every Nth call, rolls its stores back, runs the optimized function for real and compares the three return registers, the non-volatile set and the logged bytes (`reference.mismatch` events with the inputs, a `reference.summary` at route end). The game keeps the optimized results. | `reference_sample_every = 40` gives 192 reference copies (of about 7,700 eligible leaf functions). Race route with verify on every call: **31,105,675 calls verified, 0 mismatches** across the optimized code's CR, CTR and XER locals, folded constants and thunk bypass. The first run reported 19,323 mismatches in two functions: the comparison looked at every logged store, and a function that writes a word twice had its first value compared against the final memory; only the last store per address counts now. Verifying every call slowed the simulation enough to fail the runner's time-ratio gate (1.09 against 1.08), so a verify run uses `--no-performance-gate`; `=100` or more keeps a gate-passing run. |
| NL-1.4 | **Built for the non-volatile set; measured slower, dropped.** ShiftGlue `6eb062a` makes `non_volatile_as_local` correct: r14-r31, f14-f31, v14-v31 and v64-v127 load from `ctx` on entry, the save/restore helpers are inlined on the locals, and the locals a function writes are published to `ctx` before every call, tail call and return (`non_volatile_fprs_as_local`, `non_volatile_vectors_as_local` and `non_volatile_reload_after_call` select the variants). The first version, which dropped the helper calls and started locals at zero, crashed: functions read a caller's register through `ctx` before writing it, and 13 such functions are reached through indirect calls in a race, so a hand list (`share_registers`) can't cover them. A boot hang with every class localized came from folded rodata constants written to `ctx.fN` while the function read its local; the fold now names registers through the accessors. Every correct variant finishes `fh1-race-sustained` at the same frame count as the baseline, and every one costs more: guest code on the render and simulation threads takes 20-27 % more cycles (sampler, self cycles outside ntdll), and `.text` grows from 55.6 to 92.3 MB, since each function now carries its save and restore sequences and a publish at every call. The volatile half (callee live-in and clobber sets) builds on the same locals and would add publishes, not remove them, so it is dropped with it. The option stays off; with it off the generator's output is identical, function for function. | Same desktop, same flags, one build directory per variant, 60 s window of the race (render / simulation thread, Gcycles/s): baseline 1.96 / 1.87 (earlier runs 1.94-2.02 / 1.76-1.80); GPR locals only 2.12 / 1.92; all classes with a reload after each call 2.17 / 1.98; all classes, publish only 2.17 / 2.03. Output frames in the 30 s after `race-moving`: 3463-3508 for all. The early unsafe build counted 4.3 % fewer host instructions statically, so even its ceiling was small next to the code growth correctness needs. The growth is not an x86 effect: the main module's generated code compiled with the Android arm64 release flags is 11,569,931 instructions with the option off and 16,396,271 with it on (+41.7 %), so the Odin was not run. |
| NL-1.5 | **Step 1 done: direct calls bypass the weak thunk.** `direct_calls_bypass_thunk = true` makes every `bl` and tail `b` to a generated function name the strong `__imp__sub_` body instead of the weak `sub_` thunk (one `jmp` less per call); `host_overridden_functions` lists the three functions `src/guest_native` replaces with a strong `sub_` of its own, which keep the thunk. `[rexcrt]` hooks and the save/restore helpers are named directly as before; indirect calls still go through the dispatch table and the thunk. | Static host instructions unchanged (12,699,751 to 12,704,801): the partitions are 234 units and a callee is almost never in its caller's unit, so nothing inlines without link-time optimization. Race route: pass, 120.0 fps median, 1 % low 80.8, p99 12.4 ms (the best of the eleven routes of this work; one run, so within noise for the median but the low end improved). **ThinLTO measured, not made the default:** with `PINYON_SHIFT_RECOMP_IPO` the bypass does let Clang inline across units: the executable's `.text` grew from 55.6 to 60.2 MB (+8 %) and its instruction count from 13.06 M to 14.62 M (+12 %), while the race route ran at the same 120.0 fps median (1 % low 82.0 against 80.8, p99 12.2 against 12.4 ms): at the desktop's frame-rate cap the two are indistinguishable, so the decision belongs to the Odin, where #464's earlier ThinLTO measurement (neutral) was taken while the thunks still blocked every inline. The link takes about 15 minutes. A missing override entry does not fail the link yet: the strong `sub_` and the `__imp__sub_` body both link, and direct calls silently skip the override, which is the remaining risk of this option. |
| NL-1.7 | **Done: the generator keys debug lines by guest address.** `guest_line_directives = true` emits `#line <guest byte offset + 1> "<project>.guest"` before every instruction's code, so the line table (CodeView on Windows, DWARF elsewhere) names the guest address instead of the generated file's line; a sample profile (`llvm-profgen` from `perf`/`simpleperf`) and a sampler's symbolization then survive any change to the generated C++. The build's `PINYON_SHIFT_RECOMP_PGO=GENERATE/USE` instrumentation flow is unchanged; the option is off by default because the directives grow the source (253 to 317 MB) and change the partitioning (234 to 605 units). What remains for shipping a profile per release is CI work: a training run per platform and `llvm-profgen` on the Deck or the Odin, where sample profiling exists. | One generated unit compiled to assembly: 12,662 of its 14,807 `.cv_loc` entries point at `pinyon_shift.guest` with lines such as 4,089,681 (`0x82000000 + 0x3E6750`), the rest at the runtime's headers; compile time of the same-index partition 4.6 s against 5.1 s. Instructions are 4 apart, so an instruction whose code spans more than four lines bleeds into the next instruction's numbers. |
| NL-1.10 | **Done.** `fold_rodata_loads = true`: a D-form `lfs`, `lfd`, `lwz`, `ld`, `lwa`, `lhz` or `lbz` whose base register holds a value known from `lis`/`li`/`addi`/`addis`/`ori` on the straight-line path (cleared at labels, calls, hooks and every other write) and whose address lies in `.rdata` becomes the literal it would load. The generator writes the folded ranges with their FNV-1a 64 hash into `pinyon_shift_folds.cpp`; `Runtime::LoadXexImage` hashes the same bytes of the loaded image and refuses the image when they differ, so a patched or different executable cannot run with stale constants. | FH1 base image: 19,350 load sites folded over 2,275 distinct `.rdata` addresses (16,859 `lfs`, 1,648 `lfd`, 843 integer loads), as the census predicted (19,900 estimated). Generated host instructions 12,704,801 to 12,579,563 (−1.0 %), byte swaps 829,353 to 810,001 (one per folded site), flush-mode writes 38,139 to 37,148, `.text` 54.19 to 53.80 MB. Race route: pass at 119.7 fps median (the cap), the folded bytes verified at load (2,275 ranges). |
| NL-2.2 | **Done.** `tools/re/ghidra-workspace.py` builds the workspace in `.local/re/ghidra` (never committed) from the player's own `default.xex`: it writes a table of ShiftGlue's 76,885 function starts, the knowledge base's names and address records (`kb.py symbols`, with confidence) and `classes.json`'s 7,636 vtables, imports the executable headlessly with `tools/re/ghidra/ApplyPinyonKnowledge.java` applied before analysis, and applies the table again after analysis, because auto-analysis turns about 11,450 of the starts into data. A name whose confidence is "guess" stays a plate comment; the others become the function name. Tools, under `.local/re/tools`: Ghidra 12.1.3 (NSA's GitHub release), Eclipse Temurin JDK 21.0.12.1+1 (Adoptium) and XEXLoaderWV 12.1.3 (zeroKilo's GitHub release, the established XEX loader); the Xenon360 loader the item named was not used, since it had one star and two weeks of history. XEXLoaderWV's PowerPC language does not decode VMX128, so vector-heavy functions show undefined instructions; the generated C++ stays the reference for them. Ghidra refuses a project path with a `.`-prefixed element, so the tool passes the 8.3 short path on Windows. | Rebuilt from scratch: import and analysis about 6 minutes, then the reapply; a check script found 76,890 functions, all 76,885 ShiftGlue starts at a function start, 0 missing, and `0x823E22C8` named `viewport_aspect_and_culling_frustum` from its finding. |
| NL-2.3 | **Done for the first two probes.** `PINYON_SHIFT_RECOMP_PROBE` (generator option `call_probes`, `rexglue codegen --probes`, its own tree `.local/generated-probe`) counts every function entry in a per-instruction-slot table and records every indirect call site's target per thread (`rex/ppc/probe.h`); the runtime writes `<state>/logs/probe.json` at shutdown and `tools/re/probe-summary.py` reads one or more of them with the generated function list and the knowledge base's names: functions by calls, functions no route entered (the cold-tier list), indirect sites by distinct target count (one target is a guarded-devirtualization candidate). Stack offsets, memory classes, field census and argument values are the next probes; they need the same hooks (`REX_FUNC_PROLOGUE`, the memory macros) and a harvest format, not a new mechanism. | Race route on the probe build (its overhead pushed the simulation-time ratio to 1.083, so the runner's gate is skipped with the new `--no-performance-gate`): 6.15 G calls to 38,770 of the 76,257 generated functions; **37,588 functions never entered** (the cold-tier list, `.local/re/probe/race-never-called.txt`, one route so far). The most-called functions are the register save and restore helpers: `__savegprlr_29` and `__restgprlr_29` 232 M calls each, the `_26`, `_27`, `_20` and `__savefpr_28` pairs behind them, about 1.9 G calls (31 %) in all, which is what NL-1.4's non-volatile locals turn into nothing. Indirect calls: 1.02 G through 18,017 sites; **17,144 sites (95 %) saw a single target** in the route (guarded-devirtualization candidates), 496 two, and the vtable dispatches fan out to up to 97 and 264 targets. The two hottest sites are in the render frame function (`0x8259F4AC` and `0x8259F4C4`, 30.4 M calls each, one target each). Recorded on the site's Executable and Threads pages. |
| NL-2.5 | **Done.** The vtable scanner reads each locator's class hierarchy descriptor (base classes in order, the vtable's offset in the complete object) and the generator writes `classes.json` beside the generated code: vtable, class, offset, bases, slots. The file is derived from the game's RTTI, so it stays in `.local` like the generated code; the knowledge base can cite it. | FH1 base image: 7,636 vtables for 6,389 classes, 7,236 of them with base classes (1 to 12 deep; 3,836 with one), 1,246 secondary vtables (offset > 0), 74,385 slots. Generated code unchanged. |
| NL-3.5 | **Done for sizing; eviction and VMA blocks not needed.** ShiftGlue `a34793b`: an executor surface's host image holds only the rows a draw, clear or resolve has claimed (rounded up to 128, at least the untile height), not the whole EDRAM addressing period (2,048 rows for a 1280-wide target). A later claim past the image grows it by at least 1.5x: the old rows are copied into the new image, the new rows cleared, and the old image released once its submission completes. `fh1_surface_rows_on_demand=false` restores full-height images. Eviction of idle surfaces is not taken: all 34 surfaces of a 3x race now total 635 MB and each is used every frame or every few. The 64 MB VMA blocks do not apply: surfaces are dedicated allocations, not VMA suballocations. | RTX 4080, `fh1-race-sustained` at 3x: surfaces 2,388 to 635 MB (34 either way; an instrumented estimate of the claimed rows predicted 605 MB), device memory 4,479 to 2,747 MB; two surfaces grew in the route; captures within run-to-run noise and inspected; the Khronos validation layer reports the same two pre-existing messages with the option on and off. |
| NL-3.6 | **Measured, dropped.** The stutter left after preparation is pipelines first needed when new content appears, and building them when a display list is created cannot know their state: a pipeline needs the render target formats and the blend and depth state the list inherits from its caller (DR-0.4: lists mark inherited state; nothing patches them). Stored pipelines persist, so the cost is once per install. | RTX 4080, 1x, an empty NVIDIA driver cache per case (`__GL_SHADER_DISK_CACHE_PATH`), `fh1-race-start-wait` from the appdata seed. After the preparation route (fresh state with the player's settings, as setup runs it; 287 pipelines stored): 9.07 s of frame time over 16.7 ms, 16 frames over 100 ms, worst 1.19 s; 233 pipelines created during play, 137 with a shader no earlier pipeline used and 96 with known shaders in a new combination of state. Every frame over 100 ms falls within a burst of 4-65 creations, at entering the world (5.25 s) and at loading the race (3.82 s). With every pipeline of that run stored (414) and its driver cache: 2.35 s, one 1.6 s frame at the race load with 40 creations of content that varies run to run. So 6.7 s is the ceiling of any earlier build. |
| NL-3.1 | **A decoder step done; compiling each list once not taken, measured.** A sampled profile of the decoder thread (Release plugin with a PDB, `REXGPU_FH1_DEBUG_INFO`, 1x `fh1-race-sync`, the heavy window) found it 22-27 % waiting (WAIT_REG_MEM yields), about 25 % applying register runs, 18 % packet dispatch and 2 % hashing shader microcode on load; one line, the per-register "unchanged, and not a register whose write always matters" test, was 11 %. ShiftGlue `e00387b` (`gpu_decode_compare_runs_wide`, on) compares a run that holds none of those registers four registers at a time (SSSE3, NEON) and stops zero-filling the batch before each run is copied in. Compiling lists once would remove the parse and dispatch, not the register application the recorder needs, and the heavy frames are bound by the recorder as much as by the decoder, so a free decoder would leave the frame time where it is; the item's 7.4-8.4 ms included the waits. | 1x `fh1-race-sync`, last 600 frames, frames above 5,000 draws (290 of 600, about 6,500 draws), three alternating runs each: decoder work (CPU minus WAIT_REG_MEM time) 7.20, 7.25, 7.28 ms off against 6.38, 7.06, 6.63 on (median −0.6 ms, −8.6 %); frame median 9.05, 8.82, 8.98 against 8.52, 9.64, 8.81 (noise); recorder 7.6-8.7 ms in all six; captures on against off within the off-against-off spread. The arm64 file compiles with the Android build's flags. |
| NL-3.2 | **Done for the per-draw tests (ShiftGlue `a361e38`, `gpu_draw_unchanged_inputs`, on).** Started at the maintainer's request on 2026-10-13. Each stage that a draw usually repeats now checks in O(1) whether its inputs changed since the last draw and keeps the last result if not: the samplers (same shaders, submission and filtering, and none of the fetch constants they read written since, which the texture cache's in-sync bits already track), the texture request (the bindings in sync, and each texture already marked used and transitioned for sampling in this submission, tracked by a usage generation that `SetUsage` bumps), the texture descriptor sets or push (same shaders, layout, frame, and a generation bumped whenever samplers or textures are derived in full), and target preparation, memoized per register state hash in 16 slots instead of the last state only. `BeginDrawRendering` reuses the rendering id `BindTargets` computed. Vertex and index ranges already had their O(1) test (`SharedMemory::RequestRange`'s valid-page bitmap, the vertex buffer in-sync bits) and tile ownership its generation, so they needed nothing new. `gpu_draw_unchanged_inputs_verify` derives every stage anyway and counts differences: none over 12.5 million draws; the validation layer reports the same messages with the tests on and off. | 1x `fh1-race-sync`, RTX 4080. Hits: samplers 44 %, texture requests 56 %, texture descriptors 41 % of draws, target preparation memo 53 → 73 %. Draw cost model (heavy band): IssueDraw 1,066 → 981 ns a draw, 5.47 → 5.03 ms a heavy frame. Four alternating runs each: heavy-frame median 8.66 → 8.51 ms (−1.7 %), all frames 8.57 → 8.43 ms, recorder 7.76 → 7.68 ms. After the tests a draw is about 980 ns over about 20 steps, the largest the constant uploads (about 130 ns), so per-draw reuse has reached its floor. |
| NL-3.3 stage 1 | **Measured, not adopted (ShiftGlue branch `nl33-paged-float-constants`, `94212bd`, `vulkan_paged_float_constants`, off).** Started at the maintainer's request on 2026-10-13 as the first stage of constants by address. Shaders read float constants by register number: a 64-byte page table in push constants maps each 16-register page (vertex pages 0-15, pixel 16-31) into a storage-buffer heap, and a draw copies only the pages written since their last copy, a run of consecutive pages in one request, reusing a rewritten page whose values did not change. It renders the race unchanged and adds no validation messages. It halves the constants set work (constants set 31 → 11 ns, descriptor update 19 → 9 ns a draw) but the title writes new values nearly every draw: 1.9 page runs a draw are dirty and only 0.03 come back unchanged, so a draw copies about 650 bytes against 490 for the packed gather, and the upload step grows by what the set saves. The heavy race recorder took 7.85-8.49 ms against 7.47-7.72 ms with packing, heavy frames 8.79 against 8.54 ms (medians of 3 rounds). Kept on a branch, not on main. | 2026-10-13, RTX 4080, 1x `fh1-race-sync`, alternating rounds, the cost model and constant census in separate runs; Khronos validation on `fh1-race-sustained`; Android arm64 compile. |
| NL-3.3 and NL-3.4 | **Measured, dropped; they stay the renderer project in [DESKTOP_RENDERER_BACKLOG.md](DESKTOP_RENDERER_BACKLOG.md) DR-4.1 → DR-4.2.** NL-3.3 stage 1 (row above) failed its gate, which removes the reason to build NL-3.4 on it: reading constants by address does not remove the copy, because the title writes new constant values nearly every draw, and a re-executed buffer would still copy them each frame (DR-4.1: about a tenth of the constant dwords arrive by a per-draw load with new contents, and only 4-15 % of draws match their constants of the previous frame). Earlier record, still current:  they stay the renderer project in [DESKTOP_RENDERER_BACKLOG.md](DESKTOP_RENDERER_BACKLOG.md) DR-4.1 → DR-4.2.** The recorder half of the heavy frame (7.6-8.0 ms of 8.33) is what they would cut. Every per-draw form of reuse was measured slower: DR-4.2 stage 2 templates 1,205 against 1,115 ns a draw, stage 3a buffer replay 1,571 against 1,472, because proving a draw still valid cost as much as deriving it. Only the whole-buffer ceiling (recorder 10.4 → 3.7 ms on the heavy race start) pays. NL-3.2 now gives each subsystem an O(1) test against the last draw, and its result (−8 % of a draw) bounds what per-draw reuse can do; re-execution still needs the buffer's identity and write watch (DR-3.1) and constants and textures by address (DR-4.1) so that recorded GPU work stays valid across frames. NL-3.3's parts measured nothing alone: bindless ±1.5 % on the desktop (Android keeps it, recorder 9.2 → 7.7 ms); an offline SPIR-V pack has no consumer on Vulkan (DR-5.5) and would not carry pipelines, which NL-3.6 shows are the remaining first-launch cost. | 2026-10-13, RTX 4080, 1x `fh1-race-sync`: heavy frames 8.5-9.6 ms median, recorder 7.6-8.7 ms, decoder work 6.4-7.3 ms, the title waiting on GPU fences 4.25 ms a heavy frame. DR-4.2's stage numbers are from 2026-10-02 on the same machine and route. |
| NL-4.1 | **Re-diagnosed and the cheap part measured; the API hook is not needed.** The premise was wrong: the recompiled build never traps on an XMA register store. The generator recognises the register window when the address is built (`lis 0x7FEA`) or when `eieio` follows, and emits the store as a direct call into the decoder's register handler (`REX_MM_STORE_*`), so there is no fault, no decode of the faulting instruction and nothing for an API hook to save. All XMA traffic goes through nine XAUDIO2 helpers (about 1.0 million writes and 0.5 million reads a race; recorded on the Audio page with the GPU register sites on the Rendering page). What the audio thread paid for was the handler's work: a kick decodes the context on the calling thread, by the SDK's design, to avoid waiting on the worker's sweep. The new SDK cvar `xma_decode_kicks_inline` (default on) leaves kicked contexts to the decoder thread instead, which is the "decode off the guest audio thread" half of the item without touching guest code. | Desktop, `fh1-race-sustained` at the 120 fps limit, thread sampler on the guest threads, 60 s race window, two runs each: guest audio thread 0.801 and 0.837 Gcycles/s with the inline decode, 0.678 and 0.715 with the worker decoding (−15 %); simulation and render threads unchanged within run noise; the worker decoded 145,524 and 177,663 frames instead of about 570; no XMA stall of either kind and the same output queue depth (6.7) in all four runs. **Odin**, two alternating pairs at the 60 fps limit (`simpleperf stat --per-thread`, race window): guest audio thread 1.263 and 1.298 G instructions/s inline, 0.977 and 1.049 with the worker decoding (−21 %); the XMA worker rose from 0.045 to 0.092-0.116, so the process saves about 0.2 G/s net; simulation thread unchanged (1.07-1.10), no stall, queue depth 8.0, 0 frames above 25 ms in the worker runs against 1 in each inline run. The default stays inline until someone listens to a race on Android with it off: the SDK added the inline path against 50-100 ms stalls on the worker sweep, and no counter here hears a dropout. What remains of the item is that decision and, if wanted, read-ahead in the decoder, both runtime work. |
| NL-4.3 | **Dropped for now, bounded on the Odin.** After NL-4.2 moved the audio pump off the global critical region, the lock's whole cost in a race is about 1 ms a frame summed over every thread and it produces no spike frames, so a redesign of the kernel objects (M-L, Android only) could win at most that; #416's spikes are not in this route any more. Reopen if a route shows the lock on the critical path again. | Ten complete `fh1-race-sustained` runs on the Odin at the 60 fps limit (the NL-1.2 A/B runs, 6,960-6,989 frames each), last 800 frames: 126-207 critical-region contentions a frame, blocked time summed over threads 0.55-1.28 ms a frame (3.3-7.7 % of the 16.7 ms frame), p99 1.9-3.6 ms, worst frame 3.5-14.3 ms, 0 or 1 frame above 25 ms per run. |
| NL-4.4 | **Dropped with NL-0.3's numbers.** The guest heaps that an on-demand commit could trim are 113 MB resident (the 64 KB heap 78, the 4 KB heap 35) of a 2.0 GB working set; the pipeline workers are idle threads with small stacks. | NL-0.3's measurement. |
| NL-4.5 | **Dropped for the desktop, open for the Deck and Android.** Desktop reads total 91 ms a run; the per-read stall data for the other platforms is not collected yet. | — |
| NL-6 | **Dropped for now by the maintainer (2026-10-13).** Online play would need a rendezvous and relay server and every address of the base-executable implementation re-derived for v4 (effort L); the maintainer chose not to pursue it. Reopen with a hosting decision. | — |
| NL-0.3 | **Measured.** New tools: `tools/measure-process-memory.py` (resident, committed and reserved bytes by region: guest views, dispatch table, each image, private, mapped) and `tools/summarize-startup.py` (time to each startup milestone from a runtime log). | **Resident memory in the race** (Windows, 1x, RTX 4080, working set 2,009 MB, private commit 1,868 MB, 101 threads): anonymous private memory 697 MB (host heaps and the driver), other mapped files 621 MB resident of 2,093 MB committed (the driver's and the content archives' mappings), the guest arena 577 MB (physical heap 248 MB through the A0 view plus 142 through the raw view and 12 through C0, the 64 KB virtual heap 78, the 4 KB heap 35, the XEX 34, the dispatch table all 28 MB), images 115 MB (the executable 52 MB). **Startup** (new build, from the first log line): arena mapped 0.87 s, function table 0.94 s, executables loaded 1.18 s, first guest instruction 1.19 s, first movie frame 2.6 s; the same within 0.1 s on the build before this work. The front-end stall and instruction-mix counters on the Deck and the Odin are still to do. |

## Order

1. **Now (S items, parallel):**
   - NL-0.1, NL-0.3, NL-0.5;
   - NL-1.1 (the select), NL-1.3, NL-1.8;
   - NL-5's first three ports and NL-4.2;
   - NL-2.1.
2. **Next:** NL-1.2 (fibers, then single entry), with NL-2.3 probes and
   NL-0.2. Then NL-1.5 and NL-1.7.
3. **Then:** NL-1.4, full register locals (built and dropped: slower, see Progress). Then NL-1.6.
4. **In parallel, a separate track:** NL-3.1 → NL-3.2 → NL-3.3 →
   NL-3.4, the desktop 1x lever, and NL-4.1. (NL-3.1's decoder step
   and NL-3.2's per-draw tests done; NL-3.3's paged constants measured
   slower and NL-3.4 dropped with them; the recorder chain stays DR-4.1 →
   DR-4.2, see Progress.)

A rough bound, as an estimate: NL-1.1 plus NL-1.4 would cut guest-thread
instructions on the Odin by between a quarter and a half, if their ranges
above hold. For scale, #431's r1 change (-17/-18 %) and #467's CR locals
(-11/-12 %) compound to about -27 % on the render and simulation threads.

## Corrections and other findings

- **Survey corrections** ([RECOMP_OPTIMIZATION_SURVEY.md](RECOMP_OPTIMIZATION_SURVEY.md)):
  - The `-ffp-model=strict` / `-fno-strict-aliasing` row says "Same", but
    the flags reach only the SDK's sources, not the generated units
    (NL-0.5).
  - The setjmp row says no addresses are set; `main-xex.toml` sets them.
  - The conditional flush-mode skip predates #466; only carrying the mode
    across labels is ours.
  - The three Canary options marked *unverified* exist:
    - `x64_extension_mask` fuses `vmaddfp`;
    - host/guest stack sync is JIT-only;
    - MMIO store recording is what our static `REX_MM_*` already does.
  - Xenia Edge's "guest fibers" are a full guest-thread scheduler on six
    host threads, not fiber parallelism. Still not applicable.
- **`docs/LINUX_PORT_BACKLOG.md`** says the large-code-model link has
  never run, while a 195 MB Linux binary is on record. The Linux x86-64
  build also still uses `-mcmodel=large`, although 75 MB of text fits the
  small model; that is worth a measurement.
- **Licence notices:**
  - ShiftGlue's source carries XenonRecomp-derived code (disassembler
    tables, config schema, `PPCContext`, VMX helpers), but no XenonRecomp
    MIT notice ships, and `THIRD_PARTY_NOTICES.md` lists only ReXGlue.
  - Comments in `include/rex/ppc/context.h`, `function.h`,
    `intrinsics.h`, `src/codegen/config.cpp` and
    `src/ui/vulkan/vulkan_presenter.cpp` credit UnleashedRecomp, which is
    GPL-3.0.

  Both need a check under [LEGAL.md](LEGAL.md).
- **Security:** `github.com/conventional-elanoides4623/pinyon-shift` is
  not a fork. It copies this project's commit subjects, and on 2026-10-12
  its README pointed a download button at a zip inside the repository.
  That is a common malware-lure pattern; nothing was downloaded.

## Sources

Research notes with full citations:
`.local/backlog-research/next-level-2026-10-12/` (codegen audit, runtime
and GPU audit, XenonRecomp/XenosRecomp lineage, translation literature,
RE and specialization, Xenia forks). Primary sources cited there include:

- [XenonRecomp](https://github.com/hedge-dev/XenonRecomp),
  [XenosRecomp](https://github.com/hedge-dev/XenosRecomp) and
  [UnleashedRecomp](https://github.com/hedge-dev/UnleashedRecomp);
- [Xenia Canary](https://github.com/xenia-canary/xenia-canary) and
  [Xenia Edge](https://github.com/has207/xenia-edge);
- Instrew ([VEE 2021](https://home.cit.tum.de/~engelke/pubs/2104-vee.pdf)),
  SecondWrite ([EuroSys 2013](https://terpconnect.umd.edu/~barua/anand-EUROSYS-2013.pdf)),
  WYTIWYG ([ASPLOS 2024](https://doi.org/10.1145/3620665.3640371));
- [`MapViewOfFile3`](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-mapviewoffile3)
  and LLVM's inliner
  ([`InlineCost.cpp`](https://github.com/llvm/llvm-project/blob/llvmorg-20.1.8/llvm/lib/Analysis/InlineCost.cpp#L3070)).
