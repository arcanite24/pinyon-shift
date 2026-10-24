# Renderer cache capacity audit

R06 audits the Vulkan renderer and the runtime tables feeding it at root
`34e2f00c`, SDK `102fe952`, on multivac (Ryzen 7 5800X, RTX 4080).
The related FH2 investigation suggested checking for a persistent table that
stops admitting entries and silently repeats expensive work. Only its research
note was consulted; the implementation here comes from ShiftGlue's own tables.

## Scope and method

The inventory follows allocations, full-table branches, reset and reclamation
paths in shared memory, texture and pipeline caches, the native executor, UI
upload/descriptor allocators, display-list decoding and the title-side runtime.
Backing arrays covering every physical page or hardware register have no
admission limit smaller than their address space. Direct-mapped memos replace
entries on collision; filling them does not disable admission.

The desktop soak extends `fh1-long-drive` to 111,900 output frames, with the
60 fps cap and GPU profiling enabled, at 1280 x 720 and 1x resolution scale.
The pinned seed's configuration uses single-sample MSAA and disables bloom;
these occupancy numbers describe that configuration. It copies the pinned
`appdata-2026-09-27-winwarm` seed through `run-fh1-render-test.py` and repeats
the existing steering pattern. This is a scripted stability route: the car can
stop against a barrier, so it does not establish thirty minutes of new world
streaming. No player save is written.

Temporary instrumentation records occupancy every 600 frames, tracked high-water
marks for live write watches and compiled-list counts, and pool growth events.
The temporary probes are removed from the delivered runtime. The perf CSV
retains specialization occupancy and per-frame full-table fallback counters.
Sampled peaks below are lower bounds on transient occupancy between samples;
an allocated pool's size is an upper bound, not its live occupancy. Tracked
high-water snapshots include every allocation up to their log entry; the final
partial interval (fewer than 600 frames) is not logged.

The 111,900-frame route passed: 112,396 CSV rows including startup, with
112,330 source-frame rows having a positive duration. Their median was 16.654 ms,
p95 17.125 ms (range 3.063–130.757 ms); this is one run, with zero A/B pairs.
All seven new capacity-event counters stayed zero. Both host build slots and
the game lock were reserved during measurement to avoid other fleet builds.
Captures show the car stopped at the race-start barrier, with 0% progress.
The separate `fh1-hitch-drive` free-roam route passed its 30-metre movement
wait after 195 frames and ended in a traffic queue. Its 3,921 CSV rows include
3,909 timed source-frame rows: median 16.627 ms, p95 17.125 ms, range
5.064–141.613 ms (one run, zero A/B pairs). It peaked at 2,191 live watch ranges,
2,213 nodes, 47 transfer and 42 resolve specializations, 1,246 textures / 108.7
MiB and 23 samplers. All seven capacity-event counters were zero. Neither
route establishes a continuous long drive through new scenery.

The Odin did not advertise an ADB endpoint; its last documented debugging
ports refused connections. The Android build passed, but no APK, setting,
driver or save was changed, and mobile occupancy remains unverified.

## Inventory

| Structure | Capacity / lifetime | Full behavior and prior visibility | Long-soak peak / outcome |
| --- | --- | --- | --- |
| Shared-memory range/node watches | 8,192 per pool; growable pool vectors, 128 address buckets | Recycle cancelled/fired ranges and nodes; allocate another pool; no untracked-range fallback | 2,599 ranges / 2,630 nodes high-water snapshot; one 8,192-slot pool each; growth test passes |
| GPU mirror valid/GPU-written flags | Entire 512 MiB physical address space, 131,072 4 KiB pages | Direct page indexing; every valid address is representable | 37,711 valid / 7,970 GPU-written pages sampled; direct indexing |
| GPU mirror sparse allocation bits | Entire 512 MiB mirror; at most 128 logical units, each at least 4 MiB | Allocate resident units on demand; allocation failure logged; every unit representable | 59 / 128 resident 4 MiB units, 55 allocation calls, 236 MiB sampled |
| Shared D3D page generations / armed flags | 131,072 physical pages | Direct indexing, watches re-arm after writes | 257 armed shader-cache pages sampled; direct indexing |
| Shader-load cache | 4,096 direct-mapped entries, up to five pages per entry | Replace collided key; larger shader hashes normally; hits/stale/backoff/uncacheable logged | 636 / 4,096 occupied sampled; collision replacement works |
| Compiled display lists and plans | Growable map, expire after 600 idle swaps; 65,536 words per list | Oversized/volatile/unsupported lists decode normally; fallback reasons logged | Feature off; zero compiled lists; word limit reviewed only |
| Texture cache | 1,024 MiB soft / 2,048 MiB hard defaults at 1x; budget/pressure can reduce them | Age/usage eviction after GPU completion; memory gauges and pressure logs | 1,541 textures / 144.6 MiB sampled, well below soft budget |
| Bindless 3D / cube descriptors | 4,096 each | Free slots recycled after usage completes; overflow binds null, counted and first overflow logged | Bindless off on this route; zero slots/overflows; full behavior reviewed |
| Bindless 2D-array / samplers | Device-limited; 2D at most 65,536; samplers bounded by the sampler allocation budget | Same recycling/full behavior | Bindless off on this route; zero slots/overflows; full behavior reviewed |
| Sampler objects | Device sampler limit minus UI samplers and 16 reserve | LRU eviction; if all in flight, submit/wait before retry | 26 / 3,980 sampled; zero capacity waits; retain diagnostics |
| Shader lookup front | 64 direct-mapped entries | Collision replaces front entry; growable shader map remains authoritative | 64 / 64 sampled; safe replacement, no admission cliff |
| Shaders / graphics pipelines / texture-sign variants | Growable maps | Grow until allocation failure; no fixed entry-count admission limit | 467 shaders / 370 pipelines / zero texture-sign variants sampled; no fixed cap |
| Transfer / resolve pipeline specializations | 256 each, persistent | New keys use generic shader after cap; previously silent | 47 / 256 transfer, 48 / 256 resolve (CSV); zero generic-capacity fallbacks; retain diagnostics |
| Sampler-parameter / pipeline / translation / viewport memos | 1,024 / 4,096 / 4,096 / 4,096 direct-mapped | Replace collided entry; derive missed state normally | 346 / 3,844 / 3,946 / 3,882 occupied sampled; replacements remain enabled |
| Constants descriptor memo | Starts at 1,024 slots, grows before 50% occupancy, clears each frame | Double and rehash; no fixed ceiling | 358 live entries high-water snapshot / 1,024 slots; no growth required |
| Native surfaces / retired images | Growable map/vector | Reuse keyed surfaces, retire replaced images after GPU completion; allocation failures logged | 34 surfaces / zero retired images sampled |
| Native executor descriptor pools | 512 sets/page; 1,024 sampled images and 512 each storage images/buffers; frame slots | Grow pages on pool exhaustion; reset only after frame completion | Three allocated pages total across frame slots sampled; growable |
| Transient linked-type descriptors | 32,768 sets/page with per-type budgets | Grow another page; completed descriptor sets recycled; allocation failures logged | One allocated page per allocator logged (four allocators); growable |
| Single-layout descriptor allocator | Growable pages, caller chooses sets/page | Reuse freed set indices / grow pools; allocation failures logged | Not used by this renderer route |
| Upload, uniform and converted-index pools | Normally 2 MiB pages; converted indices can use larger pages | Grow pages and recycle by submission completion; oversized single request returns failure | Up to 16 pages created per pool; 2 MiB standard / 12,582,336-byte converted-index pages; growable |
| Resolve / memexport readback maps | 256-entry maintenance target, 60-frame age | Evict buffers; transient size can exceed target before maintenance | Zero cached resolve/memexport buffers sampled on native path |
| Native synchronous readback staging | Starts at 8 MiB, doubles for a larger single copy | Flush pending copies before reuse/growth; counted readback requests/waits | 8 MiB staging allocated; zero pending bytes sampled |
| Deferred small readback ring | 64 KiB | Wrap; drop overlapping in-flight copies, executor counter `resolve_readback_deferred_dropped` | One deferred copy sampled; cursor reaches 64 KiB and wraps; zero drop records |
| Draw-program list marks | 4,096 entries, 16 probes; lookup expires marks after eight swaps | Previously never reclaimed expired marks; silently dropped new keys after a chain filled | Default off; synthetic saturation regression |
| Owned draw-program front / map | 256 direct-mapped front entries; growable map, 600 idle swaps | Replace front; expire map entries | Off; zero programs/front entries sampled; normal map expiry retained |
| Per-program draw records / owned index versions | 4,096 draws/program; 16 MiB index arena | Extra draws use normal derivation; arena reclaims completed versions, then falls back to guest ranges; aggregate `arena full` logged | Off; zero arena bytes/versions/fallbacks; retain expensive-fallback diagnostics |
| D3D draw descriptions | 1,024 slots; 3,072 words and 32 recorded loads/draw; replacement arena 32 x 512 KiB | Ring replacement; overflow/stale/missing IDs or chunks still in use fall back to PM4; title draw stats count overflows | Feature off; not dynamically exercised |
| Guest occlusion / profile / visibility query pools | 8,192 / 32,768 per profile slot / 16,384 census queries | Occlusion cursor wraps; profiling omits excess samples; visibility census skips excess draws and counts it | Occlusion cursor zero; profile high-water snapshot 2,607 / 32,768; visibility census off |
| Optional visibility oracle | Clears after exceeding 1,000,000 keys (one census batch may overshoot) | Quiet full reset; admission resumes; optional oracle skip returns to normal rendering until relearned | Census/oracle off; not dynamically exercised |
| Object-motion slots | 256 per frame | Extra objects use slot zero; executor `object_slots_full` counts it | Default off |
| Shader capture / shader-pack miss records | Capture: 65,535 entries / 512 MiB, 16 MiB bytecode and 255 bindings/record; Vulkan pack misses use a 64-bit counter | Capture rejects callbacks and reports rejects; first 64 Vulkan pack misses logged, later misses still translate | Capture off; zero Vulkan shader-pack misses (warm disk cache) |
| Optional D3D census packet marks | 1,048,576 direct-mapped words; four-frame expiry | Replace collisions; maps for lists/fixup metadata grow; other-writer ranking quietly stops updating at 4,096 keys, affecting diagnostics only | Default off |
| Optional frame inspector | 512 textures, 256 image previews, 128 resolves per captured frame | Marks capture truncated / returns a capture-limit error; does not suppress rendering | Off; zero captures requested |

The title's guest fixup tables are not a host cache. The host census observes
fixups in growable maps; no separate fixed-capacity production fixup cache was
found. The retired D3D12 executor has 1,024 RTV / 256 DSV descriptors and logs
`surface_descriptors` skips at exhaustion. It is not the shipped Vulkan path
and was not run in this audit.

Sparse allocation calls may cover adjacent units. The host's minimum sparse
unit is 4 MiB (`kHostGpuMemoryOptimalSparseAllocationLog2 = 22`); the logged
resident-byte increments have a 4 MiB greatest common divisor, establishing
that granularity for this run. Thus 236 MiB is 59 resident units, rather than
55 occupied entries. The bookkeeping covers all 128 units in the mirror.

The three-frame Vulkan rings (including the native descriptor frame slots)
reuse completed frame indices rather than admitting session-long entries.
Decoder batches publish at 65,536 register words or 32 deferred calls and are
recycled after recording; those are flush thresholds on growable vectors,
not limits after which draws lose caching. The unused
`src/native_renderer/resource_cache_budget.h` describes no live runtime pool.
The push-descriptor path accepts at most 32 texture bindings per draw; larger
binding sets use the growable transient descriptor allocator instead.
The immutable precompiled shader-pack file accepts at most 65,535 entries;
it never appends during play. An incompatible header rejects the pack through
the loader's error path, leaving normal shader translation available. Shader
override files likewise have a 16 MiB input-validation limit, not a growing pool.

## Kept changes

The optional draw-program mark table now replaces expired entries with an
atomic compare/exchange, preserving its existing eight-swap lifetime and
16-probe bound. A probe chain containing only recent marks can still reject a
new mark; it reports the first rejection and counts every rejection in
`d3d_program_mark_drops`. Reuse is counted in `d3d_program_mark_reclaims`.
The regression fills the table, demonstrates a blocked new key, advances past
expiry, and checks that new keys are admitted again.

The other changes add diagnostics to existing full behavior:

- `fh1_transfer_specialization_entries` and
  `fh1_resolve_specialization_entries` are occupancy gauges.
- `fh1_transfer_specialization_fallbacks` and
  `fh1_resolve_specialization_fallbacks` count generic-pipeline uses caused by
  capacity, with a first-saturation warning per cache, for both synchronous and
  asynchronous specialization.
- `gpu_index_arena_fallbacks`, `gpu_sampler_capacity_waits` and
  `gpu_bindless_overflows` expose existing full behavior in the perf CSV.
  Index-arena pressure and sampler waits now warn on their first occurrence.

The write-watch regression creates 16,385 synthetic overlapping watches,
cancels and replaces half, invalidates their page, and requires exactly one
callback per live watch and none on a second invalidation. It exercises growth
past two 8,192-entry pools and free-list reuse without game data or a GPU.

## Evidence and limits

Large evidence stays outside git in the fleet's `reports/R06/` directory:
route, probe scripts/diff, runtime log, perf CSV, captures and summaries.
No shader, disassembly or game payload is included in this document.
Timing from this instrumented soak is descriptive; this audit makes no FPS
improvement or cross-device image-parity claim.
