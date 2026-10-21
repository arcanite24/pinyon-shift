---
title: Recompiler
section: Internals
order: 2
description: How ShiftGlue turns Forza Horizon's default.xex into C++, finds every function, and matches the Xenon CPU's floating-point and vector behaviour.
---

# Recompiler

[ShiftGlue](https://github.com/arcanite24/shiftglue-sdk) is a fork of ReXGlue 0.10.0. Its generator, `rexglue`, reads the game's executables and writes one C++ function per guest function. Setup runs it on the player's machine, so no translated code is ever distributed.

## Inputs

`config/rexglue/pinyon_shift_manifest.toml` names three images: `default.xex` and the two facade modules `SpeechFacade_default.xex` and `XMediaFacade_default.xex`, included because traces showed the game loading them and calling into them. Each image has an analysis file in `config/rexglue/analysis/`. Only one retail executable is accepted, identified by its SHA-256.

The generator boots the runtime in a tool mode and loads each XEX through the same loader the game uses (derived from Xenia's): it decrypts the session key and the image with AES, decompresses the basic and LZX formats, and can apply `.xexp` title update deltas.

## Finding the functions

A static recompiler has to know where every function starts and ends before it writes a line of output. ShiftGlue's analysis runs in phases, and the build fails rather than guess.

{{diagram:recompiler-phases|The analysis phases. Configuration supplies what the binary doesn't make discoverable.}}

| Phase | What it finds |
| --- | --- |
| Register | Imports; the compiler's register save and restore helpers, found by byte signature; every `.pdata` entry; MSVC exception tables (unwind maps, try blocks, IP-to-state maps); functions declared in configuration |
| Scan | Code and data regions in each section |
| Discover | Walks each function: `bl` targets become functions, plain `b` targets don't; jump tables; MSVC RTTI vtables, through Complete Object Locators and the slots after them |
| Gap fill | Code nothing reached is split at `blr` and tail calls; fragments a stronger source already covers are dropped |
| Merge | Resolves jumps and seals function bounds |
| Validate | Any call that lands on no function is an error |

A scan for `lis`/`addi` function-pointer pairs exists but is off: it found too many false positives.

**Jump tables.** Four MSVC patterns are recognized: absolute 32-bit entries (`lwzx`), and byte, shifted-byte and halfword offsets from a base (`lbzx`, `lhzx`). The table size comes from the `cmplwi` bounds check found by scanning backwards, at most 64 instructions and 512 entries. When the pattern is broken, the table is declared by hand: in the title update an `lfd` between the bound check and the branch made the scan read too far and merge the next function, which one `[[switch_tables]]` entry fixed.

**Declared boundaries.** The base analysis declares 113 function sizes. Most are adjustor and tail thunks and vtable targets that have no `.pdata` entry, or regions that gap fill had merged into one function. Each carries a comment with its evidence, such as a vtable target proven at run time. Discovery that disagrees with a declared size is a warning; any new codegen warning fails the build, and `config/rexglue/accepted-codegen-warnings.json` accepts exactly three known ones.

## What the generator emits

Every guest function becomes:

```cpp
void sub_82XXXXXX(PPCContext& __restrict ctx, uint8_t* base);
```

`ctx` holds the guest registers: r0–r31, f0–f31, the 128 VMX128 vector registers, `lr`, `ctr`, `xer` (as separate so/ov/ca bytes), each `cr` field as four bytes (lt, gt, eq, so), `fpscr`, the reservation and a dispatch address. `base` is the host address of guest address 0.

| Guest construct | Generated code |
| --- | --- |
| `bl` to a known function | a direct C++ call |
| `b` into another function | `[[clang::musttail]]` call, so loops that cross functions don't grow the host stack |
| `bctrl`, `bctr` through a pointer | lookup in a dispatch table of host pointers, one slot per guest instruction, placed after the image in guest memory; misses fall back to a search of all loaded modules |
| Jump table | a C++ `switch` on a 32-bit index |
| Guest fiber calls (`CreateFiber`, `SwitchToFiber`, ...) | the runtime's host fibers, so no function is ever resumed in the middle (see below) |
| `lwarx` / `stwcx.` | `std::atomic` compare-exchange on a same-width copy of the reservation |
| `mtmsrd` (interrupts off) | enter the runtime's global critical region |
| `sync`, `lwsync`, `eieio`, `isync` | nothing on x86-64; seq_cst, acq_rel, seq_cst and acquire fences on AArch64 |
| `mftb` | the runtime's guest tick count |
| Guest `setjmp` / `longjmp` | a host `jmp_buf` per guest buffer, held in a thread-local map |

**Single-entry functions.** Until October 2026, 56,860 functions started with a `switch` on `ctx.dispatch_address` (342,683 cases) so the runtime could resume them at a return address: when the game called `KeSetCurrentStackPointers`, the runtime `longjmp`ed to the thread's base and dispatched again at `ctx.lr`. Tracing the only two callers of that kernel function showed they were XAPI's `SwitchToFiber`: the game's job system runs on fibers. Mapping the five XAPI fiber functions to the runtime's host fibers (`[rexcrt]` in the analysis file) keeps the host call chain intact across a guest fiber switch, so no interior entry is needed and the generator emits none (`interior_resume = false`). Indirect calls stopped storing their target in `ctx.dispatch_address` as well, since nothing reads it any more: 94,714 stores and 499 KB of Android code went, with no run-time change the Odin can resolve. Every function now has one entry and its loops are reducible to Clang. Statically: host instructions 13.72 M to 12.70 M (−7.4 %), code 59.7 to 54.1 MB (−9.3 %). The race route completed with the runtime's re-entry trace on and recorded no stack switch; the frame rate was unchanged within run noise (116–119 fps median).

**Condition registers in locals.** Generated code keeps guest registers in `ctx`, so every compare stores its CR bits to memory that a guest store might alias, and Clang can't drop or forward them. With `cr_as_local`, a function keeps the CR fields it uses in C++ locals, loaded from `ctx` on entry. Writing them all back and reloading them around every call cost what it saved: binaries grew 13–26 % for no change in instructions. What made it pay is the PowerPC calling convention:

- cr2–cr4 are preserved across calls, and the other fields are dead at a call and at a return.
- So a call, return or tail call writes back only the cr2–cr4 locals and reloads nothing.
- Hooks that read `ctx`, the `setjmp` copy, `longjmp` and exceptions keep a full write-back and reload.
- A function always loads its locals from `ctx` on entry; while functions could still be resumed mid-body this was correct because only preserved fields are live at a return address.

On the Odin this cut guest instructions per second by 11 % on the render thread and 12 % on the simulation thread, and the executable shrank 9 %. The other registers stay in `ctx`.

Each function is defined as a weak thunk over a strong `__imp__` body, so host code can replace a guest function by defining the same symbol (Mach-O has no overridable alias; on macOS it is a weak thunk too). Since October 2026 direct calls and tail calls name the strong body (`direct_calls_bypass_thunk`), one `jmp` less per call and inlinable under link-time optimization; the three functions the host replaces are listed (`host_overridden_functions`) and keep the thunk, as do indirect calls through the dispatch table. On the race route the change was 120.0 fps median with the best p99 of the series (12.4 ms); without LTO the static instruction count does not move, because a callee is almost never in its caller's compilation unit. With ThinLTO (`PINYON_SHIFT_RECOMP_IPO`, off by default) Clang does inline across units: 8 % more code, 12 % more instructions, and the same 120 fps at the desktop's cap, so that build waits for a measurement on the Odin.

## Memory access

Guest memory stays big-endian. Every load and store is a `volatile` access through `__builtin_bswap16/32/64` at `base + address`. Until October 2026 an address at or above `0xE0000000` also added `0x1000`, because Windows mapped that view 4 KB short of its place in the physical heap ([why](runtime.md#guest-memory)); the select behind that add was a compare, a conditional set and a shift on 70 % of all guest accesses. Skipping it for accesses through `r1`, the stack pointer, had already made the binaries 5.4–5.7 % smaller and cut the Odin's guest instructions per second by 17–18 % on the simulation and render threads. Mapping the view exactly removed the remaining 625,000 selects: with the count register and XER kept in locals (below), the generated x86-64 code went from 17.7 M to 13.7 M host instructions (−22.6 %) and from 75.0 to 59.7 MB of code (−20.4 %). Only Apple silicon, with 16 KB pages, still adds the offset. On the Odin 2 Portal (Android, 4 KB pages) the same change, with the count register and XER in locals and the NEON audio conversion, cut instructions per second in a race at the 60 fps limit by 22 % on the render thread, 24 % on the simulation thread and 35 % on the audio thread (`simpleperf stat --per-thread`, one run each way). Addresses in `0x7F000000`–`0x7FFFFFFF` go to the MMIO handler.

**Read-only data folded into literals.** The compiler builds a constant's address with `lis` and `addi` and loads it; when that address lies in `.rdata` the generator emits the value instead (`fold_rodata_loads`): 19,350 load sites over 2,275 addresses in FH1, almost all of them `lfs` and `lfd` float constants, for 1.0 % fewer host instructions and one byte swap less per site. The generated code carries the folded ranges and their hash, and the runtime refuses an executable whose bytes differ, so a patched image cannot run with stale constants.

**Count register and XER in locals.** Both are volatile in the PowerPC ABI and dead at every return address, so a function keeps them in zero-initialized locals that never touch `ctx` (`ctr_as_local`, `xer_as_local`). FH1 has no overflow-enabled integer instruction and its one `mtxer` is a context restore, so XER's summary-overflow bit is never set and the copy of it into every compare's condition field folds to zero.

**The other registers stay in `ctx`.** The generator can keep the non-volatile GPRs, FPRs and vector registers in locals too (`non_volatile_as_local`), and FH1 runs correctly with it, but it is off because it is slower. The game reads registers its caller left live through `ctx`, also from functions reached through indirect calls, so a function has to inline its register save and restore sequences on the locals and publish every local it writes before each call and return. On the desktop race route that made `.text` 66 % larger (55.6 to 92.3 MB; the same code for Android arm64 has 42 % more instructions) and the guest code on the render and simulation threads 20-27 % slower at the same frame rate. The likely reason, not measured separately: on x86-64 a `ctx` field is an L1 hit the compiler addresses directly, and with 16 host registers most localized values spill to the stack anyway, so the added copies outweigh the saved accesses. Details are in [NEXT_LEVEL_RESEARCH.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/NEXT_LEVEL_RESEARCH.md) (NL-1.4).

**Register saves to host locals.** Most FH1 functions start by calling the compiler's helper that stores the non-volatile GPRs they use into their stack frame, and end by calling the matching restore helper. No other code reads those stack slots, so with `host_local_register_saves` the generator replaces the pair with copies of `ctx.r14`-`ctx.r31` into C++ locals and back, and keeps the link-register slot the caller can read. A scan of each function keeps the helpers where the slots could be visible: a function with exception data or a mid-function hook, a frame allocated dynamically, the stack pointer stored or used in other arithmetic, or any load, store or pointer that can reach the save area. In the base image 22,060 of the 22,968 functions that call the save helper are converted (save calls 22,969 to 909); the Android `.text` grows 2.2 % (47.0 to 48.1 MB) because the copies are inline. On the Odin race the simulation thread ran 4-6 % fewer instructions a frame, the audio thread 6 % fewer and the render thread 7 % fewer per draw (three races against two), with frame time and process CPU within run-to-run spread; seven routes ran to completion with identical still captures. Unlike `non_volatile_as_local` above, the registers stay in `ctx`; only the copies through memory and the helper calls go.

**Return address in a local.** With `host_local_lr`, a function that saves the link register to its caller's frame keeps it in a C++ local instead: the slot store becomes an assignment and every reload reads the local, so `r12` and `ctx.lr` get the same value they got from memory. The register-save scan decides, and it also keeps the slot when the function shares registers with another, tail-branches to code that could read the slot first, or has a label reached with a different stack pointer; `host_local_lr_keep` lists functions whose slot a hook reads. In the base image 55,074 of the 56,799 functions that store LR are converted (1,725 kept), and `libmain` loses 0.99 MB of `.text` (2.1 %). A build that writes a poison value into each converted slot and checks it at every reload ran the race for 855 million checked calls with no mismatch. On the Odin the simulation thread ran 2-3 % fewer instructions, inside the cross-build spread. The stack back chain stays in memory, because the stall dump and `alloca` code walk it.

**Per-function specialisation.** For a list of functions in the analysis config, the generator goes further than the options above, so the native form still comes from the player's executable rather than from committed code ([LEGAL.md](legal.md)). `register_locals_functions` keeps every guest register of the function in C++ locals, volatile ones included. The locals start from `ctx`; before each call, tail call and return the function stores the registers it has changed since they were last stored, and after a call it reloads the volatile ones, because callers in FH1 read registers a callee left behind. A dataflow pass over the function's labels decides which registers are dirty at each of those points, and the save and restore helpers are inlined onto the locals. Such a function runs only in fixed FP mode (the default on arm64): with the guest's values in locals, Clang moves arithmetic across a host FP control write, so a scalar operation could run with flush-to-zero on. In the other mode it tail calls an unspecialised copy of itself, emitted beside it. `fixed_fp_mode_functions` reads the fixed-mode switch once on entry instead of at every flush-mode toggle, and `single_precision_functions` computes a multiply-add whose operands are all single precision as one single-precision fused multiply-add, the guest's own rounding, instead of a double one rounded to single.

The list is chosen by measurement. Of the 131 functions that make 80 % of the physics time, 81 with at most three calls and real FP work were tried. 19 were kept: their arm64 code (NDK clang, release flags, each function compiled alone) got at least 3 % shorter with no more memory accesses. Together they went from 12,742 to 9,206 instructions (−28 %), from 3,149 to 1,289 `ctx` accesses, from 611 to 306 FP conversions and from 246 to 19 FPCR writes, while stack accesses rose from 256 to 737. The largest, `sub_82D21DB0`, went from 3,835 to 1,737 instructions. The tyre model `sub_82D2F348` and most functions with several calls or many live vector registers got longer, because the locals spill, so they stay as they were. An offline check runs each function's old and new translations from the same synthetic registers and guest memory and compares every register, every argument at a call and every byte written. Over 8,000 runs per function, half of them with denormals, infinities and NaNs, every difference was a NaN sign or payload, or within a few single-precision ulps from the single-rounded multiply-adds. On the desktop with those inputs the 19 took 4 % fewer cycles, weighted by their share of physics time, and `sub_82D21DB0` 29 % fewer. In the game on the Odin, a lockstep run that executes both translations on every call found no difference beyond 4 ulps in 41.6 million calls. Across four races without the lists and six with them, the job worker ran 22 % fewer instructions a frame and the simulation thread 3.4 % fewer: about 1.1 million instructions, roughly 0.35 ms of CPU a frame. Details are in [NEAR_NATIVE_RESEARCH.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/NEAR_NATIVE_RESEARCH.md) (NN-5.1).

## Floating point and vectors

Generated code runs FPU instructions with denormals and VMX instructions with flush-to-zero, as the Xenon does. It switches the host's MXCSR (FPCR on ARM) only when the mode changes. The tracked mode used to be forgotten at every label, so the first float instruction after a label tested the register and often rewrote it. A pass over each generated function now computes the mode at every label from all the paths into it, and drops a toggle where every path has already set that mode. That removed 29 % of the conditional toggles and 6 % of the Odin audio thread's instructions. Calls still reset the tracked mode, because the callee may leave either. The guest rounding mode maps to host rounding, and `mtfsf` honours its field mask. FH1's threads never change the FPSCR's rounding or non-IEEE bits, so until a thread does, its float instructions skip the mode checks entirely (`ppc_fixed_fp_mode`): on the Odin race, in-run over three runs, that cut 0.13–0.15 ms of CPU a frame from each of the render, main and job threads (about 3 %), with route captures no further from the original than two runs of one build are from each other.

| Behaviour | How it's matched |
| --- | --- |
| `fmadd` family | `std::fma`, single-precision forms rounded through `float`; one instruction with the FMA3 build, bit-identical either way |
| `vmsum3fp128`, `vmsum4fp128` | products summed in double in the console's order; a finite dot product that overflows single precision returns the canonical QNaN, as the hardware does, where SSE's `dp_ps` gives infinity. The game's collision code compares those results. |
| Saturating packs and adds | `vpkuhus`, `vpkd3d128` (16-bit normalized packs clamp to ±32767), `vaddsws` (overflow detection), `vctuxs` (NaN to 0) |
| `fctid`, `fctidz`, `fctiwz` | NaN inputs give the console's results |
| `vmaxfp`, `vminfp` | a NaN operand is the result, the maximum of `-0` and `+0` is `+0` and the minimum `-0`, where SSE's min/max return the second operand |
| `vcmpbfp` | a NaN operand sets both bound bits |
| `vsl`, `vsr` | the whole 128-bit shift, with the count from the last byte of the count register as the hardware reads it |
| `vexptefp` | `+inf` from 128 up and `0` below −126, where the exponent arithmetic would wrap |
| `frsqrte`, `vrsqrtefp` | computed exactly rather than as the hardware's 12-bit estimate; negative inputs give the positive QNaN; `frsqrte` of a denormal does not overflow |
| Floating-point compares | set the `un` bit for NaN |
| `stvlx`, `stvrx` partial stores | tested at offsets 0, 1, 4, 8, 12 and 15, aliasing cases and 512 seeded random cases |
| VMX128 decoding | decoded ahead of the ppc405 opcodes it overlaps |

Vector code is lowered through SIMDe, which maps the SSE intrinsics to NEON on ARM. `vmaddfp` and `vnmsubfp` fuse the multiply and the add as the hardware does (one FMA instruction on x86 FMA3 and ARM64; hosts without FMA round the product first).

**Instruction tests.** The SDK's PPC suite (`tests/ppc`) grew from 1,480 to 2,785 cases in October 2026 by taking xenia-canary's tests (BSD-3); each file becomes its own translation unit, and a skip list names 147 cases with the reason for each: 126 whose expected value contradicts the test's own inputs, 16 for the estimate instructions (the hardware returns 12-bit estimates, the generated code the exact value), and 5 for a store-conditional without a reservation, `mfmsr`, the FPSCR exception-enable bits, a hand-encoded `stvx128` that is not one, and three instructions FH1 does not use (`mcrfs`, `mfvscr`, `mtvscr`). Until October 2026 the case parser stopped at the first plain comment among a case's directives, so 244 cases never ran, every `vpkuhus` and `vpkuwus` case among them; once they ran, they and new cases showed that both instructions wrote the destination lane by lane while still reading it, wrong whenever the destination is also a source. FH1's one such site (`vpkuwus128 v63,v63,v63`) only uses a word computed before the overwrite, so its result did not change. The import found no wrong result in an instruction FH1 uses; it did find fifteen instructions the generator had never met (none in FH1), now implemented, and xenia-canary's hardware-recorded corpus then found the NaN, signed-zero and range cases in the table above. xenia-canary's 167,636 hardware-recorded `_gen_` cases are not in the repository; the suite accepts an extra directory of them (`REXGLUE_PPC_TEST_EXTRA_ASM_DIRS`, a 1.4 GB executable). On that corpus 26,205 cases fail, 26,182 of which xenia-canary itself skips (the record forms that copy FPSCR's exception bits into CR1, `vnmsubfp` and `vmaddfp` with NaN or denormal operands, `vsl`/`vsr` with count bytes that disagree, which the architecture leaves undefined); the 23 that fail here alone are the reciprocal square-root estimates, computed exactly instead of to the hardware's 12 bits. 2,531 cases that xenia-canary skips pass here.

## Checking the generator against itself

Every optimization above changes what the generated C++ looks like without changing what it must compute, and the PowerPC test suite (2,785 hand-written cases, plus 167,636 hardware-recorded ones kept outside the repository) only covers one instruction at a time. The lockstep verifier covers whole functions in the running game. With `reference_sample_every = 40`, the generator emits every 40th leaf function a second time as `ref_sub_X` with the reference settings: every register in `ctx`, no folded constants, no fast paths, and every store routed through a log (`rex/ppc/reference.h`). Functions whose effects a log cannot undo are skipped: calls, atomics, `dcbz`, the global lock. Aligned 128-bit vector stores go through the log too, and `reference_functions` names functions to copy besides the sample: the call-free specialised physics functions (12 of the 19 above get a copy). `src/guest_native/reference_verify.cpp` then takes over the `sub_X` entry of each sampled function; with `pinyon_shift_reference_verify=N`, every Nth call runs the reference copy on a copy of the registers, rolls its stores back, runs the optimized function for real and compares the return registers, the non-volatile registers and every byte the copy wrote against the last value it wrote there (a vector store over an older scalar one owns the bytes it covers). A difference is logged as a `reference.mismatch` event with the inputs that produced it, the largest floating-point distance in single-precision ulps and the value pair. With `pinyon_shift_reference_verify_ulps=N`, floating-point registers and stored floats that differ by at most N ulps (or are NaNs of either sign) are counted as within tolerance instead, for functions whose rounding is changed on purpose (`single_precision_functions`). A function that keeps the link register or its saved GPRs in locals (`host_local_lr`, `host_local_register_saves`, `register_locals_functions`) never writes those frame slots, so the generator marks each save-area store of the copy that the optimized body does not contain (the inlined save helper's stores, the LR slot store) as unchecked: rolled back but not compared. Every other store, the FPR and vector saves included, is still compared.

On the race route with every call verified, 192 sampled functions were run 31,105,675 times with no mismatch, with the folded constants, the stack fast paths, the CR, CTR and XER locals and the direct calls all on. The check is off unless the cvar is set, and the reference copies cost nothing when it is off beyond their size in the binary.

### Region oracle

The lockstep verifier compares the generator with itself, one call-free function at a time. The region oracle (#749) checks whole call trees against an implementation that shares no code with the generator: a slow PowerPC interpreter (`rex/ppc/interpreter.h`). The interpreter reads the guest's own instruction words. On the instruction corpus, the hand-written cases plus the 167,636 recorded on hardware, it passes all 63,714 cases it can run. It refuses the others as outside its scope, and a region that reaches such an instruction is reported, not compared. The one difference it keeps on purpose: like the generator, it returns exact values for the reciprocal estimates.

`oracle_regions` names root functions. The generator follows each root's direct calls and tail calls and emits every function it reaches twice more, with every store logged:

- `orr_sub_X` with the reference settings;
- `orc_sub_X` with the build's own settings and specialisations, the candidate that a hand-written native version would replace.

Calls between region functions stay inside the copies. Any other call is an opaque boundary: the copy records the callee, the call site and the whole context there, and stops. That covers an import, an indirect call, a function outside the region or a host replacement. The host CRT's `memcpy`, `memmove` and `memset` are the exception: they only move bytes and change no register, so the copies call logged versions and the interpreter does the same. Without that, the first physics root stopped at its first `memcpy` on every call.

`src/guest_native/region_oracle.cpp` takes over the root. With `pinyon_shift_region_oracle=N`, every Nth call runs the interpreter, the reference copy and the candidate copy from the same registers and memory, rolls back each one's stores, then runs the root for real. It compares:

- the interpreter with the reference copy, strictly: every register, every store outside the root's stack frame in order (address, size, value), and the exit, either a return or a stop at the same boundary with the same context;
- the candidate with the reference copy in the same way, except the registers the generator keeps in locals and never publishes because nothing reads them across a call or a return: CTR, XER, the volatile CR fields and LR (`host_local_lr`). Those are counted as dead volatiles;
- the candidate's stores with memory after the real run, so the logged copy is shown to be the code that runs.

Differences are logged as `oracle.mismatch` events with the inputs. Route summaries add an `oracle.region` event per root.

On multivac, the v4 race route with every call checked gave no difference at 0 ulps:

| Root | Calls checked | How each check ended | Compared | Interpreter vs reference | Candidate vs reference |
| --- | ---: | --- | --- | --- | --- |
| `sub_82DE3058` (specialised physics function, 7 functions with copies) | 567,488 | Returned | 10.5 million visible stores | No difference | No difference |
| `sub_82DFC570` (parent of six specialised physics functions, 77 functions with copies) | 117,480 | Stopped at a boundary after one visible store | Context at the boundary | No difference | No difference |

On the x86 default, which is not fixed-FP mode, the candidate runs its IEEE versions.

`pinyon_shift_region_oracle_fault` seeds a fault into the candidate's run to prove the check works. On `sub_82DE3058` it caught every one:

| Fault | Caught |
| --- | --- |
| Dropped store | 548,452 of 548,452 |
| Two stores swapped | 600,224 of 600,224 |
| A volatile register (r10) changed after the return | 542,080 of 542,080 |

On `sub_82DFC570` it caught every dropped store and changed register. A swap needs two visible stores, so the oracle counted those runs as not applicable rather than as passes. The check is off unless the cvar is set. It catches a wrong result, not a slow one; the speed of a native replacement is measured separately.

### Native regions

A native region (#750) compiles one oracle root and the functions it calls into a single host function, `nr_sub_X`, with the guest registers in host values instead of `PPCContext` fields. `native_regions` in the analysis TOML names the root; it must already be an oracle root, must not recurse and must not reach `setjmp`/`longjmp`. The generator emits each member as an always-inline copy on a host-local context. Calls between members stay inline. Any other call publishes the local registers to the real context, calls the generated function and reloads; indirect calls run the same way, with no devirtualisation. The generic `PPCContext` entry and the generated body stay: `pinyon_shift_native_region` picks the generated root (0, the default), the native region (1), or alternates the two call by call and times each side (2).

What the local context costs decides the result:

- Copying the whole `PPCContext` in and out, and around every outside call, made the region 36 % slower on the Odin (about 1 KB each way, the vector file included), while the desktop was 6-8 % faster.
- The generator now copies in only the fields the region names, about 60 of them, and publishes only the fields it writes. The host `memcpy`, `memmove` and `memset` calls publish r3-r5 and reload r3.
- FPR loads, stores and folded constants go through `std::bit_cast` on the double view, so the compiler keeps the FPRs as doubles. This did not change the arm64 code measurably: most of its `fmov`s are the big-endian single-precision loads and stores the generated code has too.
- Guest memory accesses inside the region are not `volatile`. The region is one host function, so the compiler may keep an inlined member's register saves and spills in host registers and drop a load another member repeats; outside calls take `base` and still see memory. With only the stack accesses plain the Odin gained 1.6-2.1 %; with every access plain it gained 4-6 %.

The oracle checks the region's logged copy against the reference and, with the region selected, its real run: 520,256 calls on the v4 race with no difference. Per call, measured with the in-run A/B on the v4 race route (calls alternate between the two sides, timed with the TSC or the arm64 virtual counter, mean ± standard error):

| Device | Generated | Native region | Change |
| --- | ---: | ---: | ---: |
| multivac (x86-64), plain memory | 645.5 ± 1.5 ns | 429.1 ± 1.4 ns | -33.5 % |
| Odin 2 (arm64), plain memory, run 1 | 687.7 ± 3.9 ns | 646.7 ± 3.4 ns | -6.0 % |
| Odin 2, plain memory, run 2 | 595.6 ± 2.9 ns | 569.7 ± 3.1 ns | -4.3 % |
| Odin 2, volatile memory, four runs | 675-730 ns | 659-732 ns | +0.2 to -2.4 % |

With plain memory the oracle checked 463,167 calls on the desktop with no difference. On arm64 the generated members already keep their registers in locals, so the region saves the calls between them and the memory traffic it can now merge, not the register file. The region inlines its callees at every call site: `nr_sub_82DE3058` was 40,788 bytes of x86-64 code (8,789 instructions) and is 33,732 bytes on arm64, against 9,440 bytes for the seven generated functions on arm64. That growth is local to one root, unlike the global register localisation below (`.text` 66 % larger, guest code 20-27 % slower). The root runs about 100 times a frame, so even the desktop gain is about 20 µs a frame. It stays off by default.

A second root was chosen from a call-graph profile of the Odin drive (`simpleperf --call-graph fp`, 30 s): `82DE3058` itself is under 0.3 % of process cycles there, while `sub_82DFC570`, the parent of six specialised physics functions, holds about 2.1 % inclusive, on the main thread and a job worker (#756). Its region inlines 77 functions at every call site, 2.5 MB of generated C++. It needed one generator fix: an indirect call binds its own `PPCContext& __restrict ctx = real;`, which the copy-back rewrite had matched. The oracle checked 129,232 of its calls with no difference, but every check stopped at the root's first visible store (see the table above), so it covers only that prefix. Per call:

| Device | Generated | Native region | Change |
| --- | ---: | ---: | ---: |
| multivac, three runs | 19,107 / 16,374 / 16,347 ns | 18,603 / 14,962 / 14,855 ns | -2.6 / -8.6 / -9.1 % |
| Odin 2 | 20,134 ± 95 ns | 22,647 ± 96 ns | +12.5 % |

On arm64 the inlined subtree is slower, most likely from its code size. The root runs about 46 times a frame (about 0.9 ms of main-thread and worker time on the Odin), and an in-run frame A/B on the Odin (region off and on every 150 frames, two runs of five blocks) moved neither the frame (+0.08 ± 0.08 ms both, at the 60 Hz cap) nor process CPU repeatably (-1.5 ± 0.9 and -0.3 ± 0.9 ms). Two of five runs that alternated the two sides call by call also left the car short of the route's 30 m drive-start check (13.6 and 16.3 m), which no run with the first root alone had done; it was not investigated further. The root was rejected and is not in `native_regions`.

Owning the subtree's data in native structures, with an import/export bridge, and per-operation floating-point rules were not built. The region already matches the reference bit for bit, so there is no floating-point difference to fix; and removing all of the subtree's context and memory traffic, before any bridge, is bounded by its 0.9 ms of off-frame-path thread time, while the step that only removed context traffic made the Odin slower.

## Building the output

The clean-slate observable-state census fails its 15% gate under conservative
unknown-call contracts. Caller continuation demand, opaque boundaries and
native-to-original callbacks leave net context-instruction counts of
0.850% render, 0.979% simulation and 0.753% mixer (0.903% pooled), weighted
with matched Odin retired-instruction samples. Unknown indirects read all
state; observed targets do not prove a complete target set. Required stores
remain at their original sites, including the backing state needed when a
callee only conditionally writes a later-read slot. This declines CS-2 at
the present gate. The earlier 23.7–29.6% ABI ceiling used deliberately more
generous contracts. Neither result is an executed optimized backend;
new target/escape proofs would justify a new census.
[Stage 0 method, counts and limits](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/CLEAN_SLATE_STAGE0.md#cs-02-caller-demand-and-net-publications).

Output is split into files of at most 1 MiB, with the function-to-file assignment kept stable between runs (`codegen.partition.json`) so a regeneration doesn't rebuild everything. CMake runs the generator with a depfile covering the manifest, the analysis files, the three images and the SDK version, then builds the main image as an object library with a precompiled header and the facades as shared libraries.

| Setting | Value |
| --- | --- |
| Compiler | Clang 20.1.8, pinned and SHA-256 checked (Command Line Tools clang on macOS, NDK r29 on Android) |
| Optimization | `-O3`, `-ffp-contract=off`, `-fno-strict-aliasing` (measured to change nothing in the output), `-gline-tables-only`. `-ffp-model=strict` is an option: it costs 1–2 % host instructions for a risk never observed. No asynchronous exceptions: no generated unit has an SEH scope |
| x86-64 baseline | SSE4.1; an FMA3 variant when the CPU has it, guarded at start. On Windows the x86-64-v3 variant (`-CpuBaseline v3`) is opt-in: MOVBE replaced a fifth of the byte swaps in the audio routines, under 1 % of their instructions. Linux builds x86-64-v3 when the CPU has it, and the Deck build is v3 ([Platforms](platforms.md#linux-and-the-steam-deck)) |
| Linux x86-64 | The small code model with linker relaxation: the executable's code is 53 MB, far under the model's 2 GB. The large model (`-mcmodel=large -Wl,--no-relax`, still selectable with `REXGLUE_X86_64_CODE_MODEL=large`) made every call a `movabs` and a register-indirect call |
| Android | ARMv8.2-A for every library (inline LSE atomics, no outline-atomic calls; the app refuses an older CPU with a message). `-Wl,-Bsymbolic-functions`: PLT stubs fell from 1.6 % to 0.1 % of cycles; on the runtime libraries it cut jump slots by 70-92 %, but their PLT share stays about 1.3 % of the GPU commands thread, from calls between the libraries. A symbol ordering file from a race's call counts packs the hot generated functions together: `libmain`'s resident pages fell from 52 to 34-36 MB. The v4 build has its own list from a v4 probe build's open-world route (37,638 entered functions, `PINYON_SHIFT_RECOMP_PROBE` with `PINYON_SHIFT_TITLE_UPDATE_V4`): in the Odin's v4 open world `libmain`'s PSS fell from 54.8-54.9 to 34.3-36.2 MB (two interleaved runs each). The base list translated to v4 addresses did not help ([lessons](lessons.md#what-didnt-pay-off-here)) |
| LTO, PGO | wired up, off. ThinLTO is neutral on guest-thread instructions. PGO trained on one route and measured on another cut 1–6 % per guest thread on the Odin in one pair of runs; trained on four routes with the profile kept in step with the generated code, it cut the race's process instructions by only 0.1–0.7 % after allowing for the draw count (NN-1.4), so it stays off |
| First build | 20 to 60 minutes and about 25 GB on a PC; about 20 minutes on an M4 Pro; about 35 on the Deck |

## The title update build

Title update v4 is a second executable. The v4 patches were made for a later disc revision, but applied to the USA disc they reproduce the v4 images exactly: every page verifies against v4's own SHA-1 page chain. The v4 build has its own manifest, analysis and generated tree, and a translated address map:

1. `tools/map-fh1-v4-addresses.py` matches functions by their normalized bodies (branch and absolute immediates masked, unique in both images), then by call-graph anchoring, then by unique context windows, then `lis`/`addi` data pairs. 27,556 of 57,127 functions match by body alone. Unmapped addresses are reported, never guessed.
2. `tools/port-fh1-v4-analysis.py` rewrites the analysis: all hooks, declared functions, `setjmp`/`longjmp` and CRT routes mapped, with 18 reviewed hand overrides (`config/rexglue/analysis-v4/overrides.toml`). It knows every address field of the analysis schema, the code generation lists above included, and fails when a field is unclassified, an entry is unmapped, or a host replacement (`PINYON_GUEST_NATIVE`) names a v4 address that disagrees with the mapped one; `--check` writes nothing on failure. Entries kept on purpose for the base image only are marked `# v4-port: base-only`. A rule declaring virtual-call thunks outside `.pdata` found 253 in v4, and recovers 66 of the base image's 70 hand-listed thunks.
3. Host code writes guest addresses as `FH1_ADDR(base address)`, translated at compile time from a verified table; an unmapped address fails the compile. Structure offsets that moved are listed in `config/mod/fh1-offsets-v4.toml`, each with a matching site in both images.

Until October 2026 the port copied hooks and declarations but not the code generation lists, so the v4 build, the one players use for Rally and the 1000 Club, ran without the register, link-register and physics optimizations above, and `tools/build-v4.ps1` built without FMA. Both now match the base build: register saves in host locals in 23,263 of 24,182 v4 functions (base 22,030 of 22,968), the LR slot in 58,816 of 60,572 (base 55,031 of 56,799), and the same 19 specialised physics functions with 177 flush-mode toggles and 27 single-precision FMAs. Three of the 19 have edited bodies in v4; their pairs were checked through callers, callees and tables ([title update findings](game-title-update.md)). Every desktop build, v4 included, writes `pinyon_shift_build.json` beside the executable (variant, CPU flags, executable and analysis hashes, source and ShiftGlue commits), and each scripted render test records it with its result. In 90 seconds of open world with a player's settings, the two changes together cut the title thread's CPU time from 5.91 to 4.57 ms a frame and the process's from 36.3 to 33.1 ms (four interleaved runs each, [performance](performance.md#the-title-update-build)), and the lockstep verifier ran 245 functions 56,043,375 times on the same route with no mismatch.

Details: [TITLE_UPDATE_V4_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/TITLE_UPDATE_V4_BACKLOG.md).
