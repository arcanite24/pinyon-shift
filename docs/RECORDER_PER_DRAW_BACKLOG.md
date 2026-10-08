# Recorder per-draw backlog: cheaper texture bindings, dispatch and memos

Created 2026-10-07 at `dev` `fbce3be` (ShiftGlue `7fcedde`). This follows the
[recorder replay backlog](RECORDER_REPLAY_BACKLOG.md)'s re-rank: per-draw
replay was closed a second time, so the recorder gets cheaper by trimming the
work every draw pays on the full path. Nothing measured and dropped in the
[performance](PERFORMANCE_BACKLOG.md), [desktop renderer](DESKTOP_RENDERER_BACKLOG.md),
[low-spec](LOW_SPEC_BACKLOG.md) or replay backlogs is proposed again without
the change that defeated it.

## Goal

Cut the GPU recorder thread's CPU time on the race's heavy frames (5,000-6,700
draws) by at least 10 % on simulated 4 cores/8 threads, without changing a
rendered pixel, so that 4 slow cores (58.9 presents a second today, gate 59)
passes LOW-SPEC 60 and 4C/8T gains margin.

**Release gate per slice.** RR-0.4's matrix (`benchmarks/recorder-replay/`)
holds or improves: presents a second, long frames and GPU phases within run
spread; recorder CPU a heavy frame lower; decoder and submission worker CPU
not higher by more than the recorder saves; Vulkan validation clean on the
race; no route expectation lost.

## Where the time goes today

Heavy band, simulated 4C/8T, `gpu_draw_cost_model` (SDK `7fcedde`, memo on),
two runs: `IssueDraw` 1,100-1,250 ns a draw; record batches 8.5-10.8 ms a
frame, of which draws and register entries are 88 % and per-entry dispatch the
rest (72,700-92,100 entries a frame, about 14 a draw).

| Step (ns a draw) | Heavy band | What it holds |
| --- | --- | --- |
| textures | 135-143 | `RequestTextures`: outdated flag exchange, in-sync and memo checks, two passes over every used texture (3D-as-2D views, `MarkAsUsed`/usage barriers) |
| texture bindings | 127-143 | Image infos, vertex set reuse (last set only) or allocate and write, pixel push comparison, **the constants descriptor set** (lookup, allocate, 5 writes on a miss) and **`vkUpdateDescriptorSets` on the recorder thread** |
| constant uploads | 123-157 | Up to four pool requests and copies a draw, about 1.4 KB (RR-2.1) |
| targets | 109-131 | `PrepareTargets`/`BindTargets` |
| translation | 99-123 | Shader translation lookup and **the sampler loop** (per-slot cache, parameters memo, `UseSampler`) |
| primitives | 77-95 | Primitive processing |
| system constants | 68-78 | After RR-2.3's memo (was 88-103) |
| vertex, binds, dynamic, begin rendering, analysis, draw | 35-73 each | |

Record entries a heavy frame: single registers ("ones") 0.34-0.57 ms, calls
0.26-0.40 ms, register runs 0.63-0.87 ms.

## What is known

| Fact | Source |
| --- | --- |
| Every draw records `VGT_DRAW_INITIATOR` as a single-register entry, and indexed draws also `VGT_DMA_BASE` and `VGT_DMA_SIZE`: about 3 of the 14 entries a draw, 15,000-20,000 a frame, never elided (0x21F9-0x21FC always matter), yet their `WriteRegister` does nothing but store | `command_processor.cpp` `ExecutePacketType3Draw` (2322, 2344, 2353), `PacketWriteRegister`; research 2026-10-07 |
| A single-register entry is a virtual `WriteRegister` (Vulkan override, then base: bounds, per-draw and constant tests, epoch and hash, volatile store, out-of-line `IsKnownRegister`, switch) | `vulkan/command_processor.cpp` 2752, `command_processor.cpp` 908-1063 |
| Calls are `std::function` entries; IM_LOAD and IM_LOAD_IMMEDIATE (shader loads) are the hot ones, IM_LOAD_IMMEDIATE always heap-copies the microcode, and on libc++ (Android) IM_LOAD's 40-byte capture leaves the small buffer | `command_processor.cpp` 2680, 2722 |
| Unchanged-register elision splits a run into one sub-run per changed span; gap merging (16 or fewer) applies only to float constants, so render state and fetch runs fragment | `command_processor.cpp` 648-713; DR-3 (float runs 12 to 5.5 a draw, frame 10.16 to 9.71 ms) |
| Each batch takes the record mutex three times and notifies `record_done_` even when no one waits; about 160-210 batches a heavy frame | `command_processor.cpp` 480-514, 747-765 |
| The texture bindings step contains the constants set and a driver `vkUpdateDescriptorSets` call made on the recorder thread; the deferred command buffer already carries binds and pushes to the submission worker | `vulkan/command_processor.cpp` 8488-8606, `deferred_command_buffer.cpp` |
| Vertex texture sets are reused only against the stage's last set (PB-2.1: reuse covered 29 % of requests); pixel textures are pushed (`vulkan_push_texture_descriptors`) after a comparison with the last push | 8417-8470, 8660-8778 |
| Bindings change on nearly every draw: a `RequestTextures` fast path on binding and usage generations measured no change; a shared 2048-entry binding memo was within noise | DR-3, PB-8.11 |
| Bindless textures were estimated at about 3 % of the recorder for the texture half of `UpdateBindings` and deferred | PB-7.3, RR-5.1 |
| Outside practice: cache descriptor sets by content across frames (Arm's sample: CPU-bound frame 44 to 27 ms), write them with update templates (yuzu, Ryujinx, zeux), never allocate or update when nothing changed; push descriptors are slow on Qualcomm's proprietary driver (yuzu disables them there); descriptor buffer and heap give the largest driver CPU cut on new desktop drivers but are still unsettled (DXVK 2.7 and 3.0 disable them on Pascal, older RDNA and Intel Alchemist) | Research 2026-10-07: [Arm](https://docs.vulkan.org/samples/latest/samples/performance/descriptor_management/README.html), [zeux](https://zeux.io/2020/02/27/writing-an-efficient-vulkan-renderer/), [DXVK 2.7](https://github.com/doitsujin/dxvk/releases/tag/v2.7), [Qualcomm](https://docs.qualcomm.com/bundle/publicresource/80-78185-2/topics/mobile_best_practices.md) |

## Verification rules

- **Correctness first.** Changes that alter recorded commands (PD-2) carry a
  verify cvar in RR-0.2's manner where the old path can run beside the new one
  (compare the descriptor contents or the deferred stream, count differences),
  and pass the Vulkan validation layer on `fh1-race-sync`. Pure dispatch
  changes (PD-1) are checked by route expectations and the cost model's entry
  counts. Route captures differ run to run on the same build (RR-0.2), so they
  are not a byte-for-byte check.
- **Hot-reloadable cvars** where the design allows, with the old path kept
  until the slice's gate holds.
- **Measure by the cost model's steps** in interleaved runs (two pairs at
  least) on simulated 4C/8T, plus recorder, decoder and submission worker CPU
  (`gpu_*_cpu_ns`). In-run A/B (`tools/summarize-replay-ab.py --route`) only
  where the toggled frames cover the same draw bands.
- **Seeds only**, through `tools/run-fh1-render-test.py`; records through
  `tools/summarize-low-spec.py`; no builds while a route runs.
- **Two inconclusive trials on one gap mean re-rank.**

## Slices

Effort: S under a week, M 1-3 weeks, L 1-2 months. Each slice ends with a go
or no-go recorded in Progress.

### PD-0 Instruments (S)

Gate: the texture bindings step is split so its parts account for it within
10 %, and entry counts by kind and producer are logged by band.

| ID | Item | Decides | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-0.1 | **Split the texture bindings step**: image infos and comparisons, the constants set (lookup, allocate, writes), texture set allocate and writes, `vkUpdateDescriptorSets`; and move the sampler loop out of translation into its own step. | Whether PD-2 targets the driver call, the constants set or the texture sets | S | Done (2026-10-07) |
| PD-0.2 | **Entry census**: ones by register, runs by class and sub-runs per source run (elision fragmentation), calls by producer, batches a frame. Fix the cost model's double count when a run crosses a class boundary (`vulkan/command_processor.cpp` 2913) and attribute run entries in the timed loop. | Sizes PD-1.1 to PD-1.4 | S | Done (2026-10-07) |

### PD-1 Lighter entry dispatch (2-3 weeks)

Gate: entries a heavy frame at least 20 % fewer, per-entry dispatch (batch
loop minus entries) and single-register time at least 30 % lower, recorder CPU
a heavy frame lower in every interleaved pair.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-1.1 | **Fused draw entry.** Carry `VGT_DMA_BASE` and `VGT_DMA_SIZE` in `DrawRecord` (its padding word and one more) and stop recording the draw's two or three single-register entries; `ExecuteDrawRecord` stores the three registers before `IssueDraw`. The decoder's shadow file is written as today. | 15,000-20,000 fewer entries a frame, most of the 0.34-0.57 ms of single registers | S | Done (2026-10-07) |
| PD-1.2 | **Typed shader load entry.** IM_LOAD and IM_LOAD_IMMEDIATE as data entries (type, address, microcode pointer or copied words, size, hash) instead of `std::function`; other calls stay closures. | Indirection, destructor and (on Android) a heap allocation a load | S | Done (2026-10-07) |
| PD-1.3 | **Merge elided sub-runs across small gaps** for render state runs (rewriting an unchanged register is a compare and no effect there); fetch constants excluded or capped, since a merged gap widens their invalidation. Sized by PD-0.2. | Fewer run entries (0.63-0.87 ms today) | S | No-go by PD-0.2 (2026-10-07) |
| PD-1.4 | **Direct store for side-effect-free single registers** in the batch loop (per-draw and plain state registers outside the constant ranges and `WriteRegister`'s switch), the virtual call for the rest; `IsKnownRegister` and its debug log only with debug logging. | 5-15 ns an entry that remains after PD-1.1 | S | No-go by PD-0.2 (2026-10-07) |
| PD-1.5 | **Batch handoff.** Notify `record_done_` only when `RecordSync` waits (a flag), and return the finished batch and take the next under one lock. | About 1 us a batch, 160-210 batches a frame | S | Done (2026-10-07) |
| PD-1.6 | **Coalesced scratch writes** (found by PD-0.2). Scratch registers whose writes do not write back (their `SCRATCH_UMSK` bit clear) are recorded once with their latest value before the next publish, call, run over the scratch registers or scratch control write. | The race writes `SCRATCH_REG6` 2-4 times a draw and never writes it back | S | Done (2026-10-07) |

### PD-2 Texture and descriptor bindings (3-6 weeks)

Gate: textures, texture bindings and binds together at least 25 % lower a draw
by the cost model; submission worker CPU not up by more than the recorder
saves; zero verify differences; validation clean.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-2.1 | **Descriptor writes on the submission worker.** Record the set writes (set handle, binding, image and sampler infos, buffer infos) into the deferred command buffer ahead of the bind, and call `vkUpdateDescriptorSets` (or a template, PD-2.3) on the worker. The sets are not bound until the worker records the bind, so ordering holds; frame dumps and checkpoints that read sets need the writes applied first. | The driver call off the recorder (its share known after PD-0.1) | M | No-go by PD-0.1 (2026-10-07) |
| PD-2.2 | **Content-keyed texture descriptor sets.** A table keyed by (layout, image views, samplers) for vertex and non-pushed pixel sets, kept across frames with an LRU and dropped with any view or sampler it names, in place of last-set-only reuse; a hit is a lookup and a bind. Size first: share of draws with vertex textures, and how many misses are recurring combinations rather than new ones. | Allocation and writes on recurring material combinations | M | No-go by PD-0.1 (2026-10-07) |
| PD-2.3 | **Update templates** for the texture and constants sets and for pushes (`vkUpdateDescriptorSetWithTemplate`, `vkCmdPushDescriptorSetWithTemplateKHR`), from flat structs instead of `VkWriteDescriptorSet` arrays. On the worker after PD-2.1. | Driver CPU on whichever thread writes | S | Not built: no recorder share |
| PD-2.4 | **`RequestTextures` trims.** A relaxed load before the `texture_became_outdated_` exchange; one fused pass over used textures for 3D-as-2D views and usage, skipping the 3D check by a per-slot dimension mask. A fast path on generations is not proposed again (DR-3). | 10-30 ns a draw | S | Done (2026-10-07) |
| PD-2.5 | **Fixed arrays in `UpdateBindings`.** Image and sampler infos, the last-set copies and the free-set lookup (`unordered_map` keyed by counts and stage) as fixed arrays; `nullDescriptor` cached. | A few ns each, low risk | S | No-go (2026-10-07) |
| PD-2.6 | **Push descriptors on Adreno.** On the Odin's Qualcomm driver, measure pushed against set-based pixel textures (`vulkan_push_texture_descriptors` off) per the [Android in-run A/B method](ANDROID_60FPS_BACKLOG.md); Turnip and desktop keep pushes. | No slow driver path on Android | S | Needs hardware; now also bindless (PD-4) |

### PD-3 Constants, samplers and targets memos (2-4 weeks)

Gate: the four steps together at least 15 % lower a draw, with verify cvars
reporting zero differences.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-3.1 | **One pool request a draw** for every dirty constant buffer (aligned sub-offsets in one allocation) instead of up to four. | Part of the 123-157 ns upload step | S | No-go (2026-10-07) |
| PD-3.2 | **Fetch constant upload by used slots.** Every fetch write invalidates the 768-byte block (0.67-0.82 uploads a draw, 0 % whole-block repeats); census whether the slots the draw's shaders read changed, and skip the upload (keep the previous offset) when they did not. | Fetch uploads a draw | S | No-go (2026-10-07) |
| PD-3.3 | **Constants descriptor set.** After PD-0.1 sizes it: its key and per-frame map against the dynamic offsets that change every draw; one set with dynamic offsets for all five buffers so a draw only changes offsets. | Constants set lookups and writes | M | Done as a fix (2026-10-07) |
| PD-3.4 | **Sampler loop.** Per-slot key over the fetch words and the filter cvars in one compare, `UseSampler` skipped while the slot's key and submission hold. | Part of translation's 99-123 ns | S | Done (2026-10-07) |
| PD-3.5 | **Targets memo.** Census what `PrepareTargets`/`BindTargets` re-derive while the render state epoch (RR-2.3) and the FH1 tile generation hold, and memoize as RR-2.3 did, with a verify cvar. | Part of 109-131 ns | M | No-go (2026-10-07) |

### PD-4 Bindless textures (only if PD-2 leaves textures above 15 % of a draw)

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-4.1 | **Descriptor-indexed textures** (RR-5.1): persistent slots for image view and sampler pairs (combined image samplers for Adreno's bindless mode), the per-stage indices in the fetch constants block, behind a capability check. Translator change. | Texture binding work down to index stores | L | No-go on desktop (2026-10-07); opt-in for Adreno |

## Not to build

- **Per-draw replay or templates** (RR-3, DR-4.2): closed twice.
- **A generations fast path for `RequestTextures`** (DR-3) and **a larger
  shared binding memo** (PB-8.11): measured within noise.
- **Compare-before-upload of whole constant blocks** (PB-2.5, RR-2.1: under
  3 % repeat).
- **Publishing batches as soon as the queue empties** (DR-1.1).
- **Descriptor buffer or heap** before PD-2 shows the driver calls still bind
  on desktop: drivers are unsettled and it needs shader changes.

## Working order

1. **PD-0** (days).
2. **PD-1.1, PD-1.5, PD-2.4, PD-2.5, PD-3.1**: small, independent, low risk.
3. **PD-2.1**, then **PD-2.3**; **PD-2.2** if PD-0.1 shows allocation and
   writes still matter.
4. **PD-1.2 to PD-1.4** and **PD-3.2 to PD-3.5** by the census.
5. **PD-4** only by its condition; **PD-2.6** with the Odin.

## Needs a person

| Item | What | Who |
| --- | --- | --- |
| PD-2.6 | Pushed against set-based textures on the Odin | Needs hardware; now also bindless (PD-4) |

## Progress

Rows are added here as items are measured or done.

| Item | Status | Evidence |
| --- | --- | --- |
| PD-0 instruments | Done (2026-10-07) | SDK `6917415`. Heavy band, simulated 4C/8T: the texture bindings step splits into image infos and checks 101-103 ns a draw, the constants set 35-39, texture set writes 11 and `vkUpdateDescriptorSets` 21-23; samplers (apart from translation) 96-104. Entries a draw: 5.0-5.4 single registers (`VGT_DRAW_INITIATOR`, `VGT_DMA_BASE`, `VGT_DMA_SIZE` 2.7, `SCRATCH_REG6` 2.1-2.6), runs 6.9 (float 3.0-3.3 of 15-19 registers, fetch 2.1-2.3 of 3, render state 1.0-1.3 of 1.3), calls 1.0-1.2; elision splits 0.8-0.9 sub-runs a source run. The RR-2.1 constant census moved to `gpu_constant_census` (its copies inflated the uploads step to 197-235 ns) |
| PD-1.1 fused draw entry | Done (2026-10-07) | SDK `6d82bb4`, `gpu_record_fused_draw_registers`. Two interleaved pairs: single registers 5.0-5.4 to 2.2-2.7 a draw, their time 0.45-0.70 to 0.19-0.34 ms a frame; record batches 11.63-11.84 to 10.96-11.12 ms on the 6,700-draw frames (with PD-3.4 in the same build) |
| PD-1.2, PD-1.5, PD-1.6 | Done (2026-10-07) | SDK `6a97801`, `gpu_record_shader_load_entries`, `gpu_record_coalesce_scratch`. 0.36-0.62 shader loads a draw skipped as repeats, the rest data entries; scratch writes recorded 2.1-3.9 to 0.4-0.7 a draw. Single registers 2.2-2.7 to 0.5-0.6 a draw, calls 1.0-1.2 to 0.6-0.8; recorder CPU 9.67-9.79 to 9.16-9.71 ms, decoder unchanged. The batch handoff (one lock, notify only waiters) measured with PD-2.4: recorder CPU 10.18-10.43 to 9.76-9.81 ms |
| PD-1.3, PD-1.4 | No-go by census (2026-10-07) | Elision splits 0.8-0.9 sub-runs a source run, so merging gaps has little to join; after PD-1.1 and PD-1.6 about 0.5 single registers a draw remain for a direct-store path |
| PD-1 gate | **Passed** (2026-10-07; maintainer accepted dispatch at -25 to -28 % against -30 %) | Entries a heavy frame 92,100 to 56,800 (-38 %), single register time 0.69 to 0.07-0.08 ms (-89 %), per-entry dispatch 1.46-1.48 to 1.06-1.11 ms (-25 to -28 %), recorder CPU lower in every interleaved pair |
| PD-2.4 `RequestTextures` trims | Done (2026-10-07) | SDK `8bbd24f`. The textures step 143-162 to 113-129 ns a draw |
| PD-3.1 one pool request | **No-go** (2026-10-07) | Two pairs: recorder CPU 9.76-9.81 ms without, 10.25-10.42 with; the uploads step did not fall. Removed |
| PD-3.2 fetch upload by used slots | **No-go** (2026-10-07) | With verify (0 differences), a used slot changed in nearly every draw: the block was kept 0.05 a draw against 0.63-0.72 uploads. Removed |
| PD-3.4 sampler key | Done (2026-10-07) | SDK `6d82bb4`, `1931dc6`, `gpu_sampler_fetch_key` (verify `gpu_sampler_fetch_key_verify`, 0 differences). Sampler parameters read the texture addresses only as zero or not: slot cache hits 52-56 to 61-65 %, and a slot whose parameters hold keeps its sampler, so `UseSampler` runs for 18-20 % of slots instead of 44-48 %; the samplers step 95-110 to 82-88 ns a draw |
| Validation | Note (2026-10-07) | The validation layer reports one `VUID-vkCmdEndQuery-None-01923` (a guest occlusion query ended in a later command buffer) at startup on every route; it reproduces on SDK `6d82bb4` with the new cvars off, so it predates this backlog. Tracked as its own task |
| PD-2.1, PD-2.2, PD-2.3 | No-go by PD-0.1 (2026-10-07) | `vkUpdateDescriptorSets` is 19-23 ns a draw and texture set allocation and writes 11-15: moving the driver call to the submission worker would move about 2 % of a draw from one thread to the other, and content-keyed sets could save at most the 11-15 ns. Update templates help only the thread that writes, which after PD-2.1 would not be the recorder |
| PD-2.5 inline image views | **No-go** (2026-10-07) | The common case of `GetActiveBindingOrNullImageView` inline: image infos 66-77 ns a draw against 63-72 before (two runs). Removed |
| PD-2 gate | **Not met** (2026-10-07) | Textures, texture bindings and binds a draw: about 380 ns at PD-0 to about 345 (textures 143-162 to 113-129 by PD-2.4; the rest unchanged), -9 % against -25 %. What remains is per-texture work (image infos 63-77 ns, the set reuse and push checks 34-41) that changes with nearly every draw's bindings |
| PD-3.3 constants set key | Done as a fix (2026-10-07) | SDK `4db9fea`. The set's key compared its bytes with 4 bytes of indeterminate padding, so equal keys matched or not by stack contents: an unrelated layout change made 43 % of draws write a new set (constants set 108-131 ns, descriptor update 74-92, recorder CPU +1.1 ms). With the padding explicit: 72 % reuse the last set, 23-27 % the frame table, 5-6 % new; 33-43 and 19-23 ns. Census by outcome in SDK `a59ccef` |
| PD-3.5 targets memo on the render epoch | **No-go** (2026-10-07) | Two trials of two pairs: memo hits 50-62 % either way, so the misses come from the shader, depth control, color mask or tile generation, not register state; targets step and recorder CPU within run spread. Removed; the hit count stays as an instrument |
| PD-3 gate | **Not met** (2026-10-07) | Constant uploads, constants set, samplers and targets a draw: about 420 ns at PD-0 to about 380 (samplers 96-104 to 82-88 by PD-3.4; the rest within spread), -9 % against -15 % |
| PD-4 condition | **Met; needs a decision** (2026-10-07) | Texture work is still about 27 % of a draw after PD-2 (textures 113-129, image infos 63-77, checks 34-41, sets and update 30-38, binds 56-59 ns), above the 15 % condition. Bindless textures are an L item (a translator change, a capability path, Adreno combined image samplers); it is the remaining large lever on the recorder and waits for the maintainer's go |
| Goal | **Partly met** (2026-10-07) | Interleaved in one session, race start on simulated 4C/8T, cost model off, heavy band: with the switchable changes off (`gpu_record_fused_draw_registers`, `gpu_sampler_fetch_key`, `gpu_record_shader_load_entries`, `gpu_record_coalesce_scratch`, `gpu_system_constants_memo`) recorder CPU 9.77 and 10.27 ms a frame (1,540 and 1,596 ns a draw), with them on 8.41 and 9.58 ms (1,374 and 1,503 ns), -7 to -14 %; decoder and title CPU within spread. The batch handoff, `RequestTextures` trims and the constants key fix have no switch and add about 5 % more by their own pairs. The matrix rerun (records in `benchmarks/recorder-replay/2026-10-07-per-draw/`, SDK `a59ccef`) ran on a slower machine state than RR-0.4's (title thread CPU, which nothing here touches, 0.8-0.9 ms higher on the simulated parts), so its rows are not comparable to the baseline: 16 threads recorder 7.7 to 7.0 ms; 4 slow cores 57.9 presents a second (58.9 at RR-0.4), still short of 59 |
| PD-4 bindless textures | **No-go on desktop** (2026-10-07; maintainer's go) | SDK `3bdd21f`, `vulkan_bindless_textures` (off, restart). Vulkan 1.2 descriptor indexing: each image view and sampler holds a slot in one update-after-bind set for its life (freed only when destroyed, after its last submission), shaders index 2D array, 3D, cube and sampler runtime arrays with per-draw indices after the fetch constants, and one pipeline layout serves every shader; the shader pack key carries the mode. Validation clean beyond the existing query error, captures render correctly, GPU time unchanged (16.24-16.42 ms). Three trials of interleaved pairs on simulated 4C/8T: image infos 63-72 to 21-34 ns a draw, set checks 34-37 to 15-18, binds 48-57 to 31-45, but computing the indices (still 53-56 % of draws after a memo on shaders, binding and sampler generations) and the 1,280-byte fetch block add 40-70 ns to the uploads step; recorder CPU +1.5 and -1.2 % in the final pairs (9.61 to 9.76 and 9.76 to 9.65 ms). NVIDIA's push descriptors were already cheap; on Adreno, where push descriptors are reported slow, it may pay, so it is kept off by default for PD-2.6's measurement on the Odin |
