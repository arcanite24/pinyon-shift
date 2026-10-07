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
| PD-0.1 | **Split the texture bindings step**: image infos and comparisons, the constants set (lookup, allocate, writes), texture set allocate and writes, `vkUpdateDescriptorSets`; and move the sampler loop out of translation into its own step. | Whether PD-2 targets the driver call, the constants set or the texture sets | S | Not started |
| PD-0.2 | **Entry census**: ones by register, runs by class and sub-runs per source run (elision fragmentation), calls by producer, batches a frame. Fix the cost model's double count when a run crosses a class boundary (`vulkan/command_processor.cpp` 2913) and attribute run entries in the timed loop. | Sizes PD-1.1 to PD-1.4 | S | Not started |

### PD-1 Lighter entry dispatch (2-3 weeks)

Gate: entries a heavy frame at least 20 % fewer, per-entry dispatch (batch
loop minus entries) and single-register time at least 30 % lower, recorder CPU
a heavy frame lower in every interleaved pair.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-1.1 | **Fused draw entry.** Carry `VGT_DMA_BASE` and `VGT_DMA_SIZE` in `DrawRecord` (its padding word and one more) and stop recording the draw's two or three single-register entries; `ExecuteDrawRecord` stores the three registers before `IssueDraw`. The decoder's shadow file is written as today. | 15,000-20,000 fewer entries a frame, most of the 0.34-0.57 ms of single registers | S | Not started |
| PD-1.2 | **Typed shader load entry.** IM_LOAD and IM_LOAD_IMMEDIATE as data entries (type, address, microcode pointer or copied words, size, hash) instead of `std::function`; other calls stay closures. | Indirection, destructor and (on Android) a heap allocation a load | S | Not started |
| PD-1.3 | **Merge elided sub-runs across small gaps** for render state runs (rewriting an unchanged register is a compare and no effect there); fetch constants excluded or capped, since a merged gap widens their invalidation. Sized by PD-0.2. | Fewer run entries (0.63-0.87 ms today) | S | Not started |
| PD-1.4 | **Direct store for side-effect-free single registers** in the batch loop (per-draw and plain state registers outside the constant ranges and `WriteRegister`'s switch), the virtual call for the rest; `IsKnownRegister` and its debug log only with debug logging. | 5-15 ns an entry that remains after PD-1.1 | S | Not started |
| PD-1.5 | **Batch handoff.** Notify `record_done_` only when `RecordSync` waits (a flag), and return the finished batch and take the next under one lock. | About 1 us a batch, 160-210 batches a frame | S | Not started |

### PD-2 Texture and descriptor bindings (3-6 weeks)

Gate: textures, texture bindings and binds together at least 25 % lower a draw
by the cost model; submission worker CPU not up by more than the recorder
saves; zero verify differences; validation clean.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-2.1 | **Descriptor writes on the submission worker.** Record the set writes (set handle, binding, image and sampler infos, buffer infos) into the deferred command buffer ahead of the bind, and call `vkUpdateDescriptorSets` (or a template, PD-2.3) on the worker. The sets are not bound until the worker records the bind, so ordering holds; frame dumps and checkpoints that read sets need the writes applied first. | The driver call off the recorder (its share known after PD-0.1) | M | Not started |
| PD-2.2 | **Content-keyed texture descriptor sets.** A table keyed by (layout, image views, samplers) for vertex and non-pushed pixel sets, kept across frames with an LRU and dropped with any view or sampler it names, in place of last-set-only reuse; a hit is a lookup and a bind. Size first: share of draws with vertex textures, and how many misses are recurring combinations rather than new ones. | Allocation and writes on recurring material combinations | M | Not started |
| PD-2.3 | **Update templates** for the texture and constants sets and for pushes (`vkUpdateDescriptorSetWithTemplate`, `vkCmdPushDescriptorSetWithTemplateKHR`), from flat structs instead of `VkWriteDescriptorSet` arrays. On the worker after PD-2.1. | Driver CPU on whichever thread writes | S | Not started |
| PD-2.4 | **`RequestTextures` trims.** A relaxed load before the `texture_became_outdated_` exchange; one fused pass over used textures for 3D-as-2D views and usage, skipping the 3D check by a per-slot dimension mask. A fast path on generations is not proposed again (DR-3). | 10-30 ns a draw | S | Not started |
| PD-2.5 | **Fixed arrays in `UpdateBindings`.** Image and sampler infos, the last-set copies and the free-set lookup (`unordered_map` keyed by counts and stage) as fixed arrays; `nullDescriptor` cached. | A few ns each, low risk | S | Not started |
| PD-2.6 | **Push descriptors on Adreno.** On the Odin's Qualcomm driver, measure pushed against set-based pixel textures (`vulkan_push_texture_descriptors` off) per the [Android in-run A/B method](ANDROID_60FPS_BACKLOG.md); Turnip and desktop keep pushes. | No slow driver path on Android | S | Needs hardware |

### PD-3 Constants, samplers and targets memos (2-4 weeks)

Gate: the four steps together at least 15 % lower a draw, with verify cvars
reporting zero differences.

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-3.1 | **One pool request a draw** for every dirty constant buffer (aligned sub-offsets in one allocation) instead of up to four. | Part of the 123-157 ns upload step | S | Not started |
| PD-3.2 | **Fetch constant upload by used slots.** Every fetch write invalidates the 768-byte block (0.67-0.82 uploads a draw, 0 % whole-block repeats); census whether the slots the draw's shaders read changed, and skip the upload (keep the previous offset) when they did not. | Fetch uploads a draw | S | Not started |
| PD-3.3 | **Constants descriptor set.** After PD-0.1 sizes it: its key and per-frame map against the dynamic offsets that change every draw; one set with dynamic offsets for all five buffers so a draw only changes offsets. | Constants set lookups and writes | M | Not started |
| PD-3.4 | **Sampler loop.** Per-slot key over the fetch words and the filter cvars in one compare, `UseSampler` skipped while the slot's key and submission hold. | Part of translation's 99-123 ns | S | Not started |
| PD-3.5 | **Targets memo.** Census what `PrepareTargets`/`BindTargets` re-derive while the render state epoch (RR-2.3) and the FH1 tile generation hold, and memoize as RR-2.3 did, with a verify cvar. | Part of 109-131 ns | M | Not started |

### PD-4 Bindless textures (only if PD-2 leaves textures above 15 % of a draw)

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| PD-4.1 | **Descriptor-indexed textures** (RR-5.1): persistent slots for image view and sampler pairs (combined image samplers for Adreno's bindless mode), the per-stage indices in the fetch constants block, behind a capability check. Translator change. | Texture binding work down to index stores | L | Not started |

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
| PD-2.6 | Pushed against set-based textures on the Odin | Whoever holds the device |

## Progress

Rows are added here as items are measured or done.

| Item | Status | Evidence |
| --- | --- | --- |
