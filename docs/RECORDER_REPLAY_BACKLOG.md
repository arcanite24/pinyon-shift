# Recorder replay backlog: reuse recorded commands for repeated buffers

Created 2026-10-07 at `dev` `1cd8b48` (ShiftGlue `797eebc`). This expands
LS-3 of the [low-spec backlog](LOW_SPEC_BACKLOG.md) into phases that can be
executed and judged one at a time. It builds on DR-3, DR-4.1 and DR-4.2 of the
[desktop renderer backlog](DESKTOP_RENDERER_BACKLOG.md); nothing measured and
dropped there is proposed again without the change that defeated it.

## Goal

On the race's heavy frames (5,000-7,400 draws), cut the GPU recorder thread's
CPU time by at least a third without changing a single rendered pixel, so that
LOW-SPEC 60 has margin on four slow cores and 2 cores with 4 threads (both at
the 59 presents a second gate today, LS-0.5).

**Release gate for the default.** On `fh1-race-start-wait`, `fh1-race-sync`,
`fh1-long-drive` and a menu and transition route, at 60 fps on the simulated
4 cores/8 threads and 4 slow cores (`--host-cpus`, `--sibling-load`):
- recorder CPU (`gpu_recorder_cpu_ns`) a heavy frame at least 30 % lower, and
  no route's total measured thread CPU higher;
- frame cadence no worse (presents a second, long frames), GPU frame phases
  unchanged within run spread;
- the replay correctness harness (RR-0.2) reports zero differences over the
  whole matrix, and route captures are byte-identical to the full path.

## What is known

| Fact | Source |
| --- | --- |
| The recorder costs 1,115-1,472 ns a draw; 7-11 ms a heavy frame at 60 fps on simulated 4-core parts | DR-4.2, LS-0.5 |
| Skipping wholly matching buffers outright takes the recorder from 10.4 to 3.7 ms (a ceiling, not a design) | DR-4.2 ceiling probe |
| 71-87 % of the race's draws match their previous execution in state, bound image views and samplers, with no EDRAM transfer; 70-84 % sit in wholly replayable buffers; transfers touch 0.4-0.9 % of draws and shared memory uploads 0.3-0.8 % | LS-3.3 census |
| Float, bool and loop constants differ in 85-95 % of draws; about 90 % of constant dwords are register writes inside the buffers, about 10 % one 16-dword `LOAD_ALU_CONSTANT` matrix a draw | DR-4.2 census, LS-3.3 |
| The decoder copies `LOAD_ALU_CONSTANT` memory into the record at decode time, so the recorder never reads guest memory for constants | `command_processor.cpp` `ExecutePacketType3_LOAD_ALU_CONSTANT` |
| In the recorder profile (4 cores/8 threads, race) the per-draw path is 48 % of the thread: bindings 13.4 %, textures 4.6 %, system constants 2.9 %, float gather 2.2 %, register writes about 6 %, shared memory requests about 2.6 %; no single hotspot | LS-3.3 profile |
| A replay that proves each draw's signature before reusing it saves nothing: about 3,200 against 3,300 cycles a replayed draw, 1,000 of them constant uploads; the recorder got slower (1,571 against 1,472 ns a draw; 1,459 against 1,339 with persistent constant blocks) | DR-4.2 stages 3a/3b, SDK branch `dr42-buffer-replay` |
| The bit-exact frame replays (`tools/test-fh1-frame-replays.py`) run with `gpu_record_thread=false` and flatten indirect buffers, so they never exercise the recorder or buffer boundaries | `tools/replay-fh1-frame.py`, `fh1_frame_dump.cpp` |
| Existing validity signals: `state_epoch_`/`state_hash_` (non-per-draw registers), `Fh1EdramTiles::generation()`, the texture binding memo epoch and each texture's `payload_generation_`, shared memory page validity and `upload_request_count()` | SDK headers |

**The lesson that shapes every phase:** a replay only pays when its validity is
proved once per buffer (or per segment) from cheap signals, and the work it
keeps per draw is limited to what truly changes: the constants. Anything that
re-derives or re-hashes a draw to decide whether to replay it costs as much as
the draw.

## Verification rules

- **Correctness first, every phase.** A phase that changes recorded commands
  passes RR-0.2's harness with zero differences before it is measured.
- **Off by default** until RR-6's gate, behind `gpu_segment_replay` (hot
  reload where the design allows, so in-run A/B works), with a kill switch that
  needs no restart.
- **Measure total work.** Recorder, decoder and submission worker CPU
  (`gpu_*_cpu_ns`, cycle-exact on Windows) and the whole frame, by draw band;
  in-run A/B in 300-frame alternation for hot settings, interleaved runs
  otherwise. Diagnostics off for benchmarks.
- **Seeds only**, through `tools/run-fh1-render-test.py`; records through
  `tools/summarize-low-spec.py`.
- **Two inconclusive trials on one gap mean re-rank**, not a third trial.

## Phases

Effort: S under a week, M 1-3 weeks, L 1-2 months. Each phase ends with a go
or no-go recorded in Progress.

### RR-0 Instruments before any replay (2-3 weeks)

Gate: the harness catches a deliberately wrong replay (a skipped bind, a stale
constant, a wrong dynamic offset) on every route, and the cost model accounts
for at least 90 % of the recorder's busy time.

| ID | Item | Decides | Effort | Status |
| --- | --- | --- | --- | --- |
| RR-0.1 | **Per-draw cost model.** Sampled cycle counters (one draw in 16, `__rdtsc`) around each step of `IssueDrawImpl`: translation and samplers, `RequestTextures`, `PrepareTargets`/`BindTargets`, pipeline, viewport and dynamic state, system constants, `UpdateBindings` (constants, textures, binds separately), vertex residency, memexport, `BeginDrawRendering`, the draw command; plus register application (`WriteRegistersHost`) and `ExecuteDrawRecord`'s own work. Logged per draw band every 600 frames. | Exactly what a replayed draw saves, per phase | S | Not started |
| RR-0.2 | **Replay correctness harness.** A verify mode (`gpu_segment_replay_verify`) that, for every replayed segment, also runs the full path into a scratch `DeferredCommandBuffer` and compares the two command streams element by element, normalizing only the fields replay is allowed to change (constant buffer dynamic offsets and upload buffer handles, compared by the uploaded bytes instead). Any difference logs the segment, draw and command and turns replay off for that buffer. Plus route captures compared byte for byte against a replay-off run. | Every later phase's correctness | M | Not started |
| RR-0.3 | **Frame dumps that keep buffers.** `fh1_frame_dump` option that keeps indirect buffer packets (not flattened) and a replay mode with `gpu_record_thread=true`, so the bit-exact replays cover the recorder and buffer boundaries; two frames back to back so the second can replay the first's segments. | Bit-exact coverage of replay | M | Not started |
| RR-0.4 | **Benchmark matrix.** Routes above at 60 fps on 16 threads, simulated 4C/8T, 4C/4T, slow cores and 2C/4T, plus 120 fps on 16 threads; recorder CPU a draw by band, cadence, GPU phases. Baseline records in `benchmarks/recorder-replay/`. | The numbers every phase is judged by | S | Not started |

### RR-1 Prove validity per buffer, cheaply (2-4 weeks)

Gate: over the matrix, buffer-level validity agrees with the per-draw census
(LS-3.3) with **zero false positives** (valid by RR-1, different per draw)
and covers at least 90 % of the census's replayable draws; its cost is under
2 % of the recorder's.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| RR-1.1 | **Buffer identity on the decoder.** XXH3 of every indirect buffer's dwords (today only under the census cvars), keyed by address, size and occurrence in the frame, carried to the recorder as a buffer-begin record. Measure the hashing cost (about 1,200 buffers a frame). | Identity at a few microseconds a frame | S | Not started |
| RR-1.2 | **Entry state.** The register state a buffer starts from must equal its recording's: a running hash on the decoder of every register write applied since the frame began (it already sees them all, in the shadow file), sampled at buffer begin. Per-draw registers are included; constants inherited from before the buffer are included, since the buffer's draws may read them. | Validity without hashing any draw | M | Not started |
| RR-1.3 | **Host generations.** Per segment, the texture binding memo epoch and the payload generations of the textures it binds, `Fh1EdramTiles::generation()` at entry (or a narrower ownership check over the tiles it claims), shared memory validity of its index and vertex ranges (an upload marks the segment for revalidation, not for rejection), and the open rendering at entry. | The reasons a valid buffer still cannot replay | M | Not started |
| RR-1.4 | **Agreement census.** Run RR-1's decision beside the per-draw census without replaying anything: count agreements, false negatives and false positives by reason. | Go or no-go for RR-3 | S | Not started |

### RR-2 Cheaper constants, with or without replay (3-6 weeks)

Constants are the one input that changes in nearly every draw, so they decide
what a replayed draw still costs (about 1,000 of 3,200 cycles in DR-4.2).
This phase pays on its own and is the prerequisite for RR-3 paying at all.

Gate: float, system, bool and loop constant work a draw at least 40 % lower
by RR-0.1's model, bit-exact replays and captures unchanged, no GPU time
regression.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| RR-2.1 | **Constant source census per buffer.** For each draw's float, bool and loop constants: written inside its buffer by register writes, loaded from memory inside the buffer, or inherited from before the buffer; and how many dwords change between executions of the same buffer. | Sizes RR-2.2 to RR-2.4 | S | Not started |
| RR-2.2 | **Incremental gather.** Keep each stage's gathered float constant block per (shader, buffer position) and, on the next draw or execution, patch only the registers written since (the recorder knows them from the runs it applies) instead of gathering the whole bitmap. Uploads stay per draw. | Most of `GatherFloatConstants` and part of the upload copy | M | Not started |
| RR-2.3 | **System constants memo.** `UpdateSystemConstantValues` derives the same values from the same registers: memoize by `state_hash_` and the few per-draw inputs, as the pipeline and viewport memos do. | Most of its 2.9 % | S | Not started |
| RR-2.4 | **Immutable and dynamic constants apart** (LS-3.1). For a buffer whose bytes and entry state match, the register-written constants are fixed: build them once into a persistent block (the `ad02bf0` persistent buffer), and upload only the per-draw `LOAD_ALU_CONSTANT` matrices as a compact dynamic block. Start without shader changes (the persistent block is copied into the per-draw upload); move the shader to two bindings only if RR-0.1 shows the copy still binds. Every register a draw reads must be written inside its buffer or proved by RR-1.2's entry state. | Constant uploads toward the 10 % that really change | L | Not started |

### RR-3 Segment capture and replay, narrow first (1-2 months)

Gate: RR-0.2 and RR-0.3 report zero differences; on the narrow family,
recorder CPU a heavy frame at least 15 % lower on simulated 4C/8T with no
cadence or GPU regression. If not, stop and re-rank (DR-4.2 already showed a
per-draw replay losing).

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| RR-3.1 | **Command range API.** Port from `dr42-buffer-replay`: `DeferredCommandBuffer` element ranges, append, and a scanner that accepts only binds, texture pushes, dynamic state, index binds and draws; constant set and dynamic offset patching. Unit tests on synthetic streams. | The mechanism, already proven to render | S | Not started |
| RR-3.2 | **Whole-buffer capture.** Record a buffer's commands from its first draw to its end as one segment, with the entry state forced complete (`ForceFullDrawState`), the exit state snapshot (`ReplayState`: pipeline, layout, dynamic state, update bits, bound sets) and the recorder's caches it leaves (current pipeline, descriptor sets, memos). Capture only buffers that are wholly draws inside one open FH1 rendering, without memexport, index scratch, clears, resolves or CPU-visible packets. | Segments for the narrow family | M | Not started |
| RR-3.3 | **Replay without derivation.** When RR-1 proves the buffer valid: apply its register runs to the recorder's register file (later draws need them), revalidate textures and memory by generation, upload constants (RR-2), append the segment with patched constant binds, restore the exit state, and skip `ExecuteDrawRecord` for its draws. Any failed check falls back to the full path before anything is appended. | The saving RR-0.1 attributes to derivation | L | Not started |
| RR-3.4 | **Narrow family first.** The most frequent buffer shape in the heavy race band (by the census: draws a buffer, rendering, shaders), then widen by measured share. Telemetry: replays, rejects by reason, draws replayed a frame. | Go or no-go for RR-4 | M | Not started |

### RR-4 Scale: coalesced segments and less record traffic (1-2 months)

Gate: recorder CPU a heavy frame at least 30 % lower on simulated 4C/8T and
slow cores (the goal), decoder CPU not higher, all correctness gates.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| RR-4.1 | **Coalesced segments** (LS-3.4). About 3.6 draws a buffer is too few to pay a segment's checks: span adjacent valid buffers in one segment, split at target changes, transfers, resolves, clears and CPU-visible packets, keeping the order. | Fewer, larger segments | M | Not started |
| RR-4.2 | **Lighter records for replayed buffers.** When the decoder knows a buffer will replay (its identity and entry state match and no host generation changed since), it records only the buffer reference, the register runs and the constant payloads, not the draw records. | Decoder and record traffic | M | Not started |
| RR-4.3 | **Pre-encoded segments (optional).** Today the submission worker re-encodes the deferred stream into Vulkan calls. For the hottest segments, measure recording them once into secondary command buffers or keeping their encoded form; Khronos and AMD warn that small secondaries can cost GPU time, so only with LS-3.6's GPU check. | Submission worker CPU | M | Not started |
| RR-4.4 | **Nested and repeated buffers.** Buffers executed several times a frame (passes, views) and buffers inside buffers, keyed by occurrence as the census does. | Coverage | S | Not started |

### RR-5 Stable resource identities (LS-3.2, 1-2 months, only if RR-0.1 says so)

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| RR-5.1 | **Descriptor-indexed textures** behind a capability check: a texture and sampler table where a binding is an index, so a replayed segment's texture state survives a texture's recreation and pushes disappear. Devices without the features keep the current path. | Texture binding work, and fewer replay rejects | L | Not started |

### RR-6 Default and rollout (2-4 weeks)

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| RR-6.1 | **GPU-time check on AMD and Intel** (LS-3.6) and on the Odin (Adreno): replayed segments must not cost GPU time. | No regression off NVIDIA | S | Needs hardware |
| RR-6.2 | **Long-session soak.** 30 minutes of `fh1-long-drive` and three races with menus, verify mode on, then off: zero differences, bounded segment memory (a cap and LRU eviction), no growth. | Safe default | S | Not started |
| RR-6.3 | **Default on** for desktop at 60 fps and below when the release gate holds; crash reports carry `gpu_segment_replay` and the replay counters; `docs/TROUBLESHOOTING.md` names the setting. Android follows its own measurements. | The low-spec margin shipped | S | Not started |

## Not to build

- **Per-draw signature matching before replay** (DR-4.2 stage 3a): proving a
  draw costs what deriving it does.
- **Per-draw templates** (DR-4.2 stage 2): measured slower.
- **Moving the gather to the decoder** as a saving: it moves work, it does not
  remove it.
- **Generic batching or multi-draw indirect**: the census found only
  single-draw runs; replay reuses commands, it does not merge draws.
- **Replay of buffers with CPU-visible results** (REG_TO_MEM, MEM_WRITE,
  COND_WRITE, occlusion queries) or memexport until RR-4 proves the simple
  family.

## Risks and open questions

| Risk | Settled by |
| --- | --- |
| A replay that is wrong but looks right (a stale constant, a missed bind) | RR-0.2 command-stream verify, RR-0.3 bit-exact dumps through the recorder, captures, the soak |
| Entry-state hashing on the decoder costs more than it saves | RR-1.1/1.2 cost measured before RR-3; the decoder already applies every write to its shadow |
| Constants keep the per-draw cost high whatever replay skips | RR-2 is a gate for RR-3; if RR-2 misses its gate, re-rank before building replay |
| Segments too small to amortize (3.6 draws a buffer) | RR-4.1 coalescing; RR-3.4 starts with the largest family |
| Replay changes GPU time on other vendors | RR-6.1 |
| Memory for stored segments grows | Cap and LRU in RR-6.2; segments keyed by identity and dropped with their buffer |

## Working order

1. **RR-0** (instruments): RR-0.1 and RR-0.4 first (days), then RR-0.2, then
   RR-0.3.
2. **RR-2.1, RR-2.3, RR-2.2** in parallel with **RR-1**: they pay without
   replay and size it.
3. **RR-1.4** decides whether RR-3 starts. **RR-2.4** before RR-3.3.
4. **RR-3**, narrow family; go or no-go.
5. **RR-4**, then **RR-6**. **RR-5** only if RR-0.1 or RR-3's rejects point
   at textures.

## Needs a person

| Item | What | Who |
| --- | --- | --- |
| RR-6.1 | AMD, Intel and Adreno GPU-time checks | Whoever holds the hardware |
| RR-6.3 | Deciding the default from the gate's numbers | The maintainer |

## Progress

Rows are added here as items are measured or done.

| Item | Status | Evidence |
| --- | --- | --- |
| Gate (LS-3.3) | Passed (2026-10-07) | 71-87 % of the race's draws replayable as recorded commands with fresh constants; host bindings and transfers almost never break it; constants do. See LOW_SPEC_BACKLOG's Progress |
