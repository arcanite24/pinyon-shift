# Scene-native renderer backlog

Status: in progress; SNR-00/01 have pilot controls and a passing frame-wide
view/pass boundary census. Exact full-slice mesh/material/lifetime ownership
and retained-pass bridges remain open. No performance result is claimed.
This is the primary execution roadmap for new renderer architecture. The
[performance backlog](PERFORMANCE_BACKLOG.md) remains the record of previous
experiments; the [resource migration checklist](NATIVE_RESOURCE_MIGRATION_CHECKLIST.md)
remains the acceptance ledger for resource ownership and eventual Xenos retirement.
The [SNR-00/01 evidence log](SCENE_NATIVE_SNR00_01_EVIDENCE_2026-09-22.md)
records the first clean controls, the procedural packet probe and the current
title-to-GPU join gaps.
The [SNR-02 evidence log](SCENE_NATIVE_SNR02_EVIDENCE_2026-09-22.md) records
the local-car resource census, seven selected title submodels, a complete
procedural descriptor/runtime join and all 308 selected prepared vertex
snapshots in one replay. A later replay owns every selected procedural
packet's title records, vertex bytes and ordered final draw states through
its output-frame handoff. The four selected procedural vertex shaders now
have live packed-register maps. Material roles, texture generations and
private render coverage remain open.
The [shared-track geometry handoff](SCENE_NATIVE_SNR02_TRACK_GEOMETRY_2026-09-23.md)
owns the selected track vertex/index bytes at the exact output frame and
verifies all 733 draws in one replay. Its title target boundary is exact in
that capture, but mesh/material ownership and native raster coverage remain
open; two noncandidate direct-root draws also lack title attribution.
The [SNR-04 procedural diagnostic](SCENE_NATIVE_SNR04_PROCEDURAL_EVIDENCE_2026-09-23.md)
replays every owned procedural draw through a private full-resolution
identity/depth target at the output-frame handoff. It also checks original
post-VS output and the actual bound vertex-constant bytes. A RenderDoc
post-VS comparison is still unaligned with the owned source frame. This is
geometry/ABI evidence, not material parity or full-slice coverage. The
[SNR-03 evidence log](SCENE_NATIVE_SNR03_EVIDENCE_2026-09-22.md) records
bounded same-frame vegetation metadata, guarded vertex bytes and a private
same-frame identity/depth diagnostic; full-slice coverage remains open.
The [Gate A preflight](SCENE_NATIVE_GATE_A_PREFLIGHT_2026-09-22.md) bounds
candidate-attachment GPU work and lists the retained resource dependencies;
it does not qualify a suppression cut.

## Decision and scope

Adopt Skate 3 Recomp's architectural direction: capture authoritative FH1 scene
objects and render them with native resources, material bindings and output.
Replace enough compatibility rendering to remove substantial preparation and
execution work. Retain the existing renderer as the visual reference and fallback.
The current compatibility renderer stays the default until milestone B passes.

Start with D3D12 on the existing device, queue, submission and deferred-command
infrastructure. Write FH1-specific capture and the smallest required SDK adapter.
Do not import Skate's SDK fork or build a general rendering framework first.
Preserve the original game UI; extending it remains in the [UI API plan](../UI_API_PLAN.md).

The proposed first useful slice is the **complete opaque and alpha-tested
main-view color/depth contribution** in the sustained Recaro race: all participating
world, terrain, vegetation and vehicle submissions, including their actual LODs
and dynamic transforms. SNR-00 freezes the precise boundary; SNR-05 must prove
that remaining passes can consume its color/depth correctly. Transparent geometry,
particles, HUD/video, shadows, reflections and post-processing may initially stay
compatible only where their producers, consumers and composition are preserved.
If that boundary is not separable, revise the slice explicitly before suppression.
One easy mesh or a subset selected by shader hash cannot complete this milestone.

For the race pilot, the **Gate A diagnostic slice is explicitly revised** to
the title-linked scene-list, character, procedural-item, vegetation,
animated-scene and car-presentation scalar submissions on the two exact
candidate target tuples. The car scalar owner spans both color words: its two
depth-only passes and color pass belong to one required diagnostic contribution
until their semantic role and consumers prove otherwise. Keep sky, particles,
race line, presentation strip, skid effects, clear and no-attachment-write
points in the retained compatibility path. Every other target is outside this
pilot slice, not an inferred scene pass. The
[frame-wide partition](SCENE_NATIVE_SNR00_01_EVIDENCE_2026-09-22.md#revised-gate-a-diagnostic-slice-across-both-candidate-targets)
checks every prepared draw in two independent frames and fails on a new
candidate caller. This freezes the **pilot selection rule**, not native
admission: SNR-02 must still prove geometry, material and lifetime for every
required contribution, and SNR-05 must prove retained composition before
suppression. Route/mode changes must be reclassified rather than silently
treated as this same slice.

## Evidence and changes to Pro's proposal

The supplied Pro research reviewed Skate at `f6e0ae8`, SDK `7eb0faf`, and Pinyon
at `ddc1e9`. This source audit used:

| Repository | Inspected revision / condition |
| --- | --- |
| Pinyon | `fb08b91ea4604040ae8bf405f46db831546d1b99` on `dev` |
| ShiftGlue | `bf7df82c6322d98b099e19909a8cfc657cfbea36`; pre-existing local changes in `xboxkrnl_io.cpp`, `xobject.cpp` and nested `libmspack` must be recorded in a build baseline |
| Skate reference, `.local/skate3recomp` | `f6e0ae87fdfecbadb5c1e36c55d66a744187a3cd` |
| Skate SDK, `third_party/rexglue-sdk` inside that clone | `7eb0faf7787f5e01333c228b8e3f03c32f7295ea` |

This is source research, not a runtime qualification of Skate or a promise of its
reported speedup on FH1. The following findings change the execution plan:

- **The capture boundary is title-specific.** Skate captures sorted scene entries,
  dynamic mesh state, final matrices and texture lifetimes. Some dynamic constants
  are authoritative only after the original draw preparation executes. Its scene
  dispatcher still calls the original guest code. Keep original FH1 preparation
  until equivalent authoritative state is proved; initial native rendering does
  not automatically remove hot title functions. [Capture hooks][skate-hooks]
- **Immutable publication is useful; approximate freshness is not our acceptance
  standard.** Skate publishes a shared immutable scene. Its resource paths also
  document white/missing textures during warmup and previous decoded data for
  some asynchronous updates. FH1 needs explicit generations and readiness; those
  compromises cannot qualify as equal-quality performance. [Scene state][skate-state]
- **Our output callback is an observer, not a takeover seam.**
  [Our callback](../../src/native_renderer/guest_output_renderer.cpp) only installs
  the render-test observer. ShiftGlue's
  [IssueSwap](../../thirdparty/shiftglue-sdk/src/graphics/d3d12/command_processor.cpp)
  requests a compatibility swap texture first,
  invokes the callback after gamma/FXAA, and ignores its return value. Skate has
  an earlier native-output branch that can skip compatibility output processing.
  SNR-08 must provide that behavior without losing final-image test observation.
  [Skate output path][skate-output]
- **Suppression must include resolves and preserve guest-visible effects.** Skate
  skips covered draws before primitive, pipeline, texture and target preparation,
  while retaining memory exports and selected producers. Its pitch-based pass
  rules are title-specific heuristics, not FH1 pass identities. It also substitutes
  positive occlusion-query counts when suppressing rendering. Merely continuing
  to parse query packets therefore does not prove equivalent query results.
  FH1 query consumers require their own investigation. [Draw suppression][skate-draws],
  [query handling][skate-queries], [policy][skate-policy]
- **The deferred tape is not the architectural blocker.** Skate's D3D12 native
  adapter uses the existing deferred command list, barrier queue and submission
  counters. Reuse ours unless a separate measured experiment justifies replacing
  it. [D3D12 adapter][skate-adapter]
- **The old short capture and logging recommendation are superseded.** The
  [post-fix CPU trace](CPU_HOTSPOT_RESULTS_2026-09-21.md#post-fix-elevated-cpu-trace--2026-09-22)
  already has 30.028 seconds of movement, 1,621 consumed swaps, zero lost events,
  and 18.922/26.074 ms median/p95 swap intervals. Title and GPU command threads
  used 27.884 and 25.730 seconds of sampled CPU. GPU-thread `spdlog` appears in
  only 0.002 seconds. Do not reopen INFO-flush batching or ask for the missing
  first post-fix trace. Reproduce this baseline when implementation begins.
- **Busy CPU is not all removable rendering work.** `sub_829F04A8` has 9.320
  seconds of leaf samples and polls a guest counter; its synchronization meaning
  remains unresolved. GPU-thread samples include tape execution, bindings and
  shared-memory uploads. Inclusive stacks overlap; neither thread totals nor
  source-to-present latency can be summed into a per-frame work budget.
- **Shader repair is not portable corpus completion.** The repaired saved race
  runs without GPU errors, but its repair used installed legacy shader/pipeline
  caches. Clean-install coverage remains open. Native shader reuse must have a
  reproducible source path, rather than depending on one user's cache.
- **Study the architecture before considering code reuse.** No `LICENSE`,
  `COPYING` or `NOTICE` file was found in Skate's tracked application tree at the
  pinned revision. Its SDK has a license file; that does not establish application
  file permissions. Implement FH1 behavior independently; review applicable
  per-file terms before any source transplant.

## Milestones and qualification gates

| Gate | Required result | What it does not claim |
| --- | --- | --- |
| A — Authoritative scene, SNR-00–04 | Same-frame full-resolution diagnostic color/identity and depth from an immutable scene; every item in the selected slice accounted for, with exact view/material/resource ownership | Faithful shading, removed compatibility work or higher FPS |
| B — Useful renderer, SNR-05–11 | Faithful complete slice integrated with retained passes; early paired draw/resolve suppression; safe admission/fallback; measured equal-quality improvement | All cameras/modes, complete Xenos retirement or removal of original title preparation |
| C — Earlier bypass, SNR-12 | A measured original preparation path removed without changing authoritative state, side effects or gameplay | Permission to skip all guest rendering functions |

Gate B's initial retention target is **at least 15% lower median frame time**
at equal output settings, also exceeding twice the observed control-to-control
median variation. Predeclare the comparison and tail-noise envelope in SNR-00;
p95/p99 must not regress beyond that envelope. This is a go/no-go target, not a
forecast. Missing content, stale poses, white textures, extra repeated/dropped
frames or changed game speed cannot count as a gain. If quality passes but the
speed target fails, retain the work as an experimental renderer only and use the
new profile to decide whether another bounded change is justified.

## Work order

All checkboxes are intentionally open. Research findings above are inputs, not
completed implementation tickets. Effort is relative scope, not a time estimate.

| ID | Task | Prerequisites | Effort / owner area |
| --- | --- | --- | --- |
| SNR-00 | Freeze slice, controls and success criteria | None | Small / tooling + renderer |
| SNR-01 | Recover live view and submission ownership | SNR-00 | Large / title reverse engineering |
| SNR-02 | Recover materials, resources and dynamic identities | SNR-01 | Large / title + resources |
| SNR-03 | Publish an immutable FH1 frame scene | SNR-01, SNR-02 | Medium / title + renderer |
| SNR-04 | Render authoritative full-resolution diagnostics | SNR-03 | Medium / D3D12; closes A |
| SNR-05 | Prove the pass/dependency cut and bridges | SNR-01, SNR-02; bridge implementation after A | Large / title + SDK |
| SNR-06 | Establish native shader ABI and material coverage | A, SNR-05 | Large / shaders |
| SNR-07 | Render the complete slice with native resources | SNR-06 | Large / D3D12 |
| SNR-08 | Implement native output and retained-pass composition | A, SNR-05 | Medium / SDK output |
| SNR-09 | Establish per-frame admission and recovery | SNR-07, SNR-08 | Medium / title + SDK |
| SNR-10 | Suppress replaced compatibility work early | SNR-05, SNR-09 | Medium / SDK commands |
| SNR-11 | Qualify images, streaming and net performance | SNR-10 | Large / validation; closes B |
| SNR-12 | Remove a proven upstream preparation path | B, new critical-path evidence | Large / title; closes C |

### Immediate priority and stop/go checks

Treat **Gate A (SNR-00–04)** as the active execution phase. SNR-05–12 remain
the roadmap, not simultaneous implementation work. A process-bounded replay
now attributes all 4,605 prepared draws and 131 root buffers in backend frame
6001; both candidate color groups account for 2,705 draws, with no
unattributed attachment writer. This proves the title view/pass boundary for
that frame, not a frozen opaque-scene slice. Retained sky, particle, race-line
and presentation draws interleave with candidate scene writes; other direct
and scene-list families still lack exact geometry/material/lifetime ownership.
See the [SNR-00/01 evidence](SCENE_NATIVE_SNR00_01_EVIDENCE_2026-09-22.md#process-bounded-replay-passes-the-full-candidate-boundary-census)
and [Gate A preflight](SCENE_NATIVE_GATE_A_PREFLIGHT_2026-09-22.md#exact-view-8-ordering-check).

1. **Boundary first (SNR-00/01):** attribute both color groups and the
   remaining draws to title views, owners and pass order. The final strict
   replay now joins the six apparent noncandidate gaps to prior-source-frame
   title clears; its frame-wide boundary has no unjoined attachment writer.
   Record every unmatched draw and every producer/consumer crossing the
   proposed cut.
   Freeze the exact slice only after that census; the present slice is a
   hypothesis. Candidate attachments also carry proven
   `CParticleSystemNew`/`CStandardParticleRenderer` draws; retain that path
   across the cut (see SNR-00/01 evidence) rather than counting it as native
   opaque-scene coverage. The latest disjoint partition joins 15
   animated-scene scalar draws to selected bucket objects and child contexts,
   but their geometry/material/generation fields remain unknown. Another 36
   car-presentation scalar draws form four same-owner depth/depth/color
   triples across both candidate groups; their native-versus-retained role
   remains undecided. A bounded resource join now identifies the car
   subobject's `CFXLShaderResource` and selected `CTextureResource` in two
   further replays. A later descriptor join maps the selected color texture
   to its prepared fetch base, format and dimensions in two strict replays;
   payload freshness, semantic role and lifetime remain unproved (see
   [SNR-02 evidence](SCENE_NATIVE_SNR02_EVIDENCE_2026-09-22.md#car-color-texture-resolves-to-the-prepared-fetch-descriptor)).
   Six scalar draws have a retained skid-presentation
   path. Resolve scene membership and resource ownership before freezing
   the slice.
2. **Diagnostic vertical slice (SNR-02–04):** recover the minimum authoritative
   geometry, transform and lifetime fields for one bounded view contribution;
   publish and render same-frame identity/depth beside untouched compatibility
   output. Expand to *every* item in the frozen slice before closing Gate A.
   A car-only or shader-selected diagnostic is useful evidence, not Gate A.
3. **Cost and dependency check:** use the measured control and a bounded pass
   work census to estimate removable compatibility work and added capture,
   upload and bridge cost. Investigate SNR-05 dependencies early enough to
   reject an inseparable or uneconomic cut. Do not infer a 15% gain from draw
   counts or busy CPU samples. Defer production materials, broad shader work
   and suppression until the boundary and diagnostic scene are proved.

**Stop/go after the boundary census:** if view/pass membership or retained-pass
inputs cannot be established, revise the slice explicitly and rerun the census;
do not hide unknown draws in admission. **Stop/go after the Gate A diagnostic:**
if same-frame coverage, resource freshness or the dependency/cost case fails,
keep compatibility as the default and revise the boundary or renderer approach
before starting SNR-06–10. Preserve Gate B's equal-quality 15% threshold.

### [ ] SNR-00 — Freeze the experiment

- Record executable/DLL hashes, root/SDK revisions and local patches, shader-pack
  identity, resolution/scale, presentation settings, hardware/driver and route.
  Reuse `config/render-tests/fh1-race-sustained.fh1test` and the repaired saved race
  as the initial 1x pilot; identify exact starting state and source-frame windows.
- Freeze selected view/pass coverage and a reference image set: road/terrain,
  foliage alpha edges, vehicle paint/glass boundaries, shadows, HUD and motion.
  Record unsupported views/modes and their expected whole-frame compatibility
  behavior. Existing UI, mirrors and reflections cannot silently disappear.
- Treat the current full opaque/alpha-tested main-view slice as provisional.
  Resolve the two candidate scene-color groups and full prepared-draw census
  with SNR-01 before declaring exact membership frozen.
- Plan at least two warmed ABBA blocks for retention (A = compatibility control,
  B = native candidate), with controls at both ends of each block. Establish
  control noise now; execute the candidate comparison in SNR-11. Predeclare
  how per-run statistics and control-to-control variation will be aggregated;
  measure cold startup/streaming separately. Use identical instrumentation on
  both sides and a production-settings check with diagnostic capture disabled.

**Done when:** a reproducible baseline and comparison protocol specify Gate B's
median/tail thresholds, visual checks, memory limits and exact slice. Reuse the
existing capture/summarizer tools. Launch saved gameplay through
`tools/launch-preview.ps1 -StateRoot ...` under the repository save instructions;
never copy/reset a save to normalize a benchmark. Log actual route divergence.

### [ ] SNR-01 — Find authoritative views and submission owners

- Trace main camera/view creation through visible lists, selected LODs, render
  owners and submission dispatch. Distinguish main, shadow, reflection, mirror,
  menu/photo and auxiliary views by their title relationships, not dimensions.
- Instrument a bounded selection read-only, retaining original calls. Determine
  whether each transform, palette and material state becomes final before or
  after draw preparation. Correlate every selected entry with actual submitted
  work, including deferred submissions and interleaving.
- Prioritize a frame-wide view/pass/owner census over additional local-car
  pointer probes. Join both candidate scene-color groups to title view and
  pass identities, including direct root-buffer draws, and classify the
  remainder as selected, retained or outside the slice with evidence.
- Start from existing research: static SimpleModel ownership, procedural helper
  `0x82417418`, and shared player/traffic pose path `0x82BC5A3C`. These are leads,
  not a complete main-view API. Recover the player render owner explicitly.

**Done when:** a documented address/call-path map and bounded capture prove
view → owner → mesh/instance → submission for the selected slice, report every
unmatched entry/draw and distinguish intentional culling from missing capture.
Do not revive approximate matching against the 24,025-entry spatial catalogue.

### [ ] SNR-02 — Recover semantic materials and resource lifetimes

- Follow title material objects into actual texture roles, parameters, vertex
  layouts and render state. Name paint, glass, foliage, terrain, decals and other
  participating roles only with owner/material evidence; shader hashes remain
  diagnostics. The historical 30 vehicle shader families are not a semantic map.
- Establish mesh/submesh/index ranges, instance transforms, palettes, skinning,
  morph/cloth data where present, LOD and ordering. Preserve the current selected
  instances first; do not invent native visibility or broaden batching yet.
- Separate owner/allocation generation from payload generation. Track address
  reuse, overlapping writes, streaming unload/reload and dynamic mutations. Mark
  GPU-produced resources explicitly; a CPU byte snapshot may not be their current
  contents. Use existing resource invalidation evidence where it applies.

**Done when:** each selected submission has an authoritative material/geometry
record and a validated freshness/lifetime rule. Unresolved resources make the
frame unsupported; no stale bytes, guessed roles or fallback white textures.

### [ ] SNR-03 — Publish a minimal immutable frame scene

- Define a concrete FH1 frame/view structure containing only recovered fields:
  source identity, camera, ordered instances, mesh/material references, final
  transforms and resource generations. Do not create a general scene graph/ECS.
- Publish one bounded, fully owned contribution first to test the exact-frame
  contract; expand the same structure to the frozen complete slice for Gate A.
- Publish immutable owned data or explicitly pinned immutable resources, and
  keep GPU resources alive through their submission fences. Never reread mutable
  guest constants from a later frame. Establish the title/command-thread ordering
  that pairs a scene with the exact frame being consumed.
- Bound capture buffers, pending scenes, worker queues and resource memory.
  Document overload behavior and time capture/build/upload separately. A newer
  scene cannot substitute for the scene corresponding to a consumed swap.

**Done when:** same-frame correlation, concurrent consumption, map change,
streaming mutation, restart and shutdown show no stale pointers, deep per-draw
scene copies, unbounded queues or waits that cycle between title and GPU threads.

### [ ] SNR-04 — Prove capture with a full-resolution diagnostic renderer

- Render the selected scene to private native color/identity and depth targets
  using authoritative geometry, camera and dynamic transforms. Keep compatibility
  output intact for a same-frame reference. Label this diagnostic rendering.
- Use the bounded contribution as an early vertical-slice check. Its result
  exposes missing transforms, resources and ordering; only complete frozen-slice
  coverage can close this ticket.
- Compare coverage/depth and identity overlays across moving frames, foliage,
  traffic/player animation and at least one unload/reload. Account for every
  selected item: rendered correctly or explicitly unsupported before admission.
- Record extraction/build/diagnostic costs and failures. Readbacks/overlays stay
  outside production performance runs; double rendering is not an FPS result.

First bounded implementation cut (not Gate A completion):

1. On the exact output-frame callback, allocate private reference-resolution
   identity/color and depth targets. Keep them and any readback alive through
   their submission fence; never write the guest output.
2. For the SNR-03 vegetation packets, validate the exact VS bytecode source and
   specialization, bind the owned vertex bytes with fetch 95 rebased to the
   private buffer, and upload the first 23 captured float vectors in SDK bitmap
   order. Use the captured final system words with the measured full-view viewport
   remap. Expand each four-vertex guest quad to two indexed triangles. Reject a
   missing shader, state variant, resource or ambiguous winding before drawing.
3. Compare one packet's post-VS positions, coverage and depth against a
   same-frame compatibility capture, then the complete bounded contribution.
   Record item/variant counts, unsupported reasons and extraction/upload/draw/
   readback timings. Only then expand SNR-03/SNR-04 to all selected main-view
   owners and dynamic geometry.

Current evidence: the standalone private diagnostic matches captured post-VS
positions byte-for-byte for all 72 vegetation items in one same-run frame;
189 captured variants match the fixture's vertex-count distribution. See the
[SNR-03/04 evidence](SCENE_NATIVE_SNR03_EVIDENCE_2026-09-22.md#same-run-renderdoc-post-vs-comparison).
The captured 0–0.5 viewport depth range is now reproduced in the private
raster, and one draw has a bounded sample-0 before/after depth comparison.
The private diagnostic now runs on the exact output-frame callback and writes
identity/depth readbacks without changing compatibility output; two replays
exited with all seven compatibility captures. A later `SNR03F2` replay also
owned three shader-selected pixel float registers and 64 final system words
per variant; its fixture and live/private outputs passed the bounded checks.
The matched RenderDoc frame partitions 189 vegetation executions into 135
zero-pixel-texture draws and 54 two-texture color draws. The latter use five
BC3 images, one shared full-view image and one pixel shader; the BC3 alpha
path is the next bounded coverage input to bridge.
The live binding join maps all 67 selected packets to five BC3 SRV positions
and one shared full-view SRV position in the same output frame. The guest
submission is signaled after the output callback, so the texture copy and
private-queue wait must be ordered without blocking that callback; see the
[SNR-03/04 evidence](SCENE_NATIVE_SNR03_EVIDENCE_2026-09-22.md#same-frame-final-pixel-descriptor-join).
An opt-in guest-command-list readback now verifies the five live BC3
nine-mip chains and all 67 packet joins in a later frame. All five compressed
chains match the RenderDoc capture byte for byte. The debug CPU wait is not a
native sampling bridge or a performance result; the captured anisotropic
sampler requires the full mip chain for a faithful alpha diagnostic.
At the matched event ordinary alpha discard is inactive and the pixel shader
emits a four-bit sample mask. The one-sample private target cannot establish
coverage parity; the next bounded check needs 4× private coverage/depth.
The RenderDoc side now has a repeatable four-sample before/after depth mask
for matched event 11206: 134,885 changed depth samples in 60,654 pixels of
one 1280×512 EDRAM tile. This is a single-draw reference, not a full-view
or full-slice comparison; see the SNR-03/04 evidence.
The private diagnostic now has opt-in 4× targets and per-sample identity,
coverage and depth readback. A same-frame live fixture with 67 packets and
127 ordered draws passed verification; its exact standalone replay produced
byte-identical four-sample output. It is still unmasked and has no preceding
scene depth, so it does not establish compatibility coverage or close SNR-04.
The `SNR03F3` fixture now retains the SDK draw sequence for every selected
final-state execution. A same-frame replay verified 135 ordered private raster
draws from 67 packets, while the diagnostic remains unmasked and its post-VS
file still covers only the first state per packet.
Full compatibility
coverage/depth parity, unload/reload and complete main-view ownership remain
open.

**Done when / Gate A:** the selected main-view scene is complete and stable at
reference resolution with no missing, duplicated, stale or misattributed objects.
Unknown authoritative relationships stop this gate; adding more guessed offsets
or rendering a tiny logical target does not close it.

### [ ] SNR-05 — Prove the dependency boundary

- Produce a pass/resource table with semantic owner, producers, consumers,
  generations, access order, format/subresources, temporal history, CPU reads,
  guest-memory writes and required synchronization. Reuse pass census/provenance
  tools, but do not treat their structural signatures as material semantics.
- Perform a read-only dependency and cost preflight during Gate A using the
  chosen boundary, existing controls and command-thread measurements. Record
  likely removable work and unavoidable bridge/retained work as estimates,
  then replace estimates with paired measurements in SNR-10/11.
- Identify query consumers starting at `0x82D951E0`/`0x82D95230`/`0x82D95378`,
  and resolve/control paths `0x824587D8`/`0x82458A88`. Preserve observable memory
  exports, event writes, waits and visibility decisions. Retain or replace actual
  query contributions; do not use generic fake-positive results.
- Specify how native color/depth is consumed by retained transparency, particles,
  decals, HUD, shadows/reflections and post-processing, where applicable. Include
  transfers, conversions, barriers and synchronization in the cost budget.
- Preserve existing temporal producers until the full connected chain and all
  external consumers are replaced. PERF-10's rejected latest-producer handoff
  does not become valid because the main scene is native. Old physical addresses
  are historical evidence, never permanent resource identities.

**Done when:** the selected slice has a complete, implementable boundary with no
unaccounted guest-visible dependency. Every retained producer has an explicit
reason; every proposed suppressed draw and resolve belongs to a proven replaced
chain. Revise the slice if bridges would require reproducing nearly all original
work. See [dependency evidence](GUEST_VISIBLE_RENDER_DEPENDENCIES.md) and
[PERF-10](PERFORMANCE_10_RESULTS_2026-09-21.md).

### [ ] SNR-06 — Define the native shader ABI and faithful material path

- Probe reuse of existing translated shader arithmetic under explicit native
  bindings. Document vertex addressing/endian conversion, attribute formats,
  interpolants, texture/sampler roles, constant layouts, depth/clip conventions,
  derivatives, pixel coordinates and color/gamma. Existing DXIL is not assumed
  independent of the compatibility ABI.
- Choose arithmetic reuse or a targeted native HLSL implementation per actual
  material family. Preserve alpha testing, blending, fog/lighting, skinning and
  depth/stencil behavior. Avoid a broad handwritten shader replacement sweep.
- Produce a coverage table for every material variant in the slice and an offline
  reproducible build path from available sources. Record binding/translator/scale
  identity using the [shader pack contract](SHADER_PACK_FORMAT.md); existing
  integer-scale variants do not prove arbitrary-resolution support.

**Done when:** representative materials match controlled reference images and
all required variants have a deterministic source/build route. Missing generated
shader source is a blocker to that material, not permission to rely on the local
legacy cache or use approximate shading in performance acceptance.

### [ ] SNR-07 — Implement the complete native slice

- Use the current D3D12 device/recording infrastructure for persistent vertex,
  index, texture and material resources keyed by proven identity and generation.
  Upload current dynamic data and retire replaced objects through fences.
- Render all admitted opaque/alpha-tested items with faithful material state,
  depth/stencil, ordering and native color/depth. Implement the SNR-05 bridges.
  Preserve required GPU-generated texture producers until their replacements
  are independently complete.
- Bound residency and compilation/streaming work. Prewarm known PSOs; missing
  content or readiness rejects admission. Account for cold-path cost as well as
  steady-state cost; asynchronous decoding may not silently reuse old content.

**Done when:** the complete slice matches the reference during movement and
streaming, with measured resource memory and no stale/placeholder content. Private
rendering may still coexist with compatibility until SNR-09–10; no gain is claimed.

### [ ] SNR-08 — Add real output takeover and composition

- Add the minimum SDK branch that selects native output early enough to avoid
  replaced compatibility output work. Native output must not require the old
  compatibility frontbuffer to exist just to pass `RequestSwapTexture`.
- Define ownership, dimensions, format, resource states and submission lifetime
  of the selected output. Apply gamma/FXAA or their qualified replacement once.
  Keep the final-image test observer after whichever renderer actually produced
  the presented image, with correct source/frame identity and one observation.
- Integrate retained passes in their required order using SNR-05's bridges. Handle
  resolution changes, menu/video transitions and unsupported views explicitly;
  preserve the original UI and render-test capture/timing behavior.

**Done when:** native output and full compatibility output can be selected at
controlled frame boundaries, captured correctly and presented without extra
compatibility output processing on the admitted path. Keep the adapter narrow;
no second D3D12 device/queue or cross-platform RHI is required.

### [ ] SNR-09 — Make admission and recovery safe before suppression

- Establish when the exact frame's immutable scene, resources, PSOs and bridges
  are ready relative to the **first** command that would be suppressed. A scene
  built at guest swap may be too late for earlier command-thread draws; prove the
  ordering or implement bounded staging without a title/GPU-thread wait cycle.
- Commit a frame-level mode only after readiness checks. Unknown view/material,
  resource generation or dependency selects full compatibility before skipping
  work. Last frame's successful native output alone is not current readiness.
- Define recoverable failures after commitment. Either retain a demonstrably
  replayable fallback until success or ensure expected failures are resolved
  before commitment. A flag change at swap cannot recreate discarded rendering.
  Any recovery that repeats/drops output must be counted, tested and excluded
  from claimed gains; the next frame must establish complete compatibility state.
- Test enable/disable, load/restart, streaming misses, resize and device failure
  using existing cancellation/fence rules. Keep output mode changes frame-boundary
  controlled; do not add a public settings matrix before qualification.

**Done when:** injected readiness/failure cases prove correct complete-frame
behavior, no deadlock or invalid retirement, and no silent use of stale native
output. Document the exact recovery guarantee rather than promising immediate
fallback after original work has already been discarded.

### [ ] SNR-10 — Remove paired compatibility work at the earliest safe point

- Use admitted frame/view/pass/generation identities to skip replaced draws
  before compatibility primitive, pipeline, texture, target and binding preparation
  where dependencies allow. Skip their corresponding resolves so unrendered
  compatibility data cannot overwrite native or retained resources.
- Continue required command/state parsing, synchronization, memory exports,
  query behavior and retained producers. Never identify a suppressible pass by
  resolution/pitch alone or treat an unobserved consumer as nonexistent.
- Count original/remaining/suppressed draws and resolves, avoided preparation,
  bytes uploaded/transferred and added bridge work by slice. Leave original
  title dispatch intact until SNR-12. Keep a controlled compatibility reference.

**Done when:** suppression is paired and visually equivalent, and counters plus
profiles prove substantial replaced work no longer executes. A native image
alongside the original renderer cannot close this ticket.

### [ ] SNR-11 — Qualify the integrated renderer

- Execute the frozen alternating comparisons and image/behavior checks. Extend
  the 30-second pilot to at least 3–5 minutes of sustained streaming and racing;
  include representative traffic, turns, shadows, HUD/menu transitions, reloads
  and unsupported-mode fallback. Treat broader weather/time/camera coverage as
  explicit additional scope, not inferred from the saved race.
- Measure source/consumed/present cadence, median/p95/p99 frame times, GPU spans,
  thread CPU, memory, admission rate and every fallback/repeated/dropped frame.
  Attribute capture/build, decoding/upload, native draws, bridges and remaining
  compatibility work. Use matched CPU traces and GPU markers where they answer
  a bottleneck question; an extra profiler integration is not a prerequisite.
- Use the corrected ordinal joins from the post-fix trace. Do not add overlapping
  inclusive samples, asynchronous frame-domain spans or means and medians.
  Compare diagnostic-on overhead separately from production-settings behavior.

**Done when / Gate B:** equal quality and gameplay pass, the entire supported
slice is admitted without concealed omissions, memory/tails meet the frozen
limits, and median improvement clears both the 15% target and control noise.
Publish results with scope, rejected cases, remaining work and exact artifacts.
Do not widen scope or change defaults to rescue a failed comparison.

### [ ] SNR-12 — Remove measured upstream title preparation

- Reprofile the qualified renderer. Select one proven render-preparation path
  whose outputs the native contract already replaces and whose cost affects the
  critical path. Preserve visibility, animation, simulation and any state still
  needed for authoritative capture or retained compatibility producers.
- Establish all side effects and fallback-before-effects behavior, then bypass
  the bounded path. Count eliminated title preparation/PM4 production and parsing,
  not merely suppressed GPU draws.
- Investigate the sampled guest-counter wait separately before any change to it.
  Reduced spinning may lower CPU/power without reducing frame time; do not label
  it disposable render preparation based on the sampled function name alone.

**Done when / Gate C:** matched quality/game-speed/tail checks pass and measured
net work and frame cost improve. Apply this process to another path only if the
new profile justifies it. Deferred-tape removal remains a separate conditional
experiment, not a graduation requirement.

## Supporting work and later expansion

- [ ] **SNR-M01 — Portable reference/fallback shaders.** Complete clean-install
  shader-source/specialization coverage and validate the chosen route without an
  installed legacy cache. Existing saved-state repair is evidence, not completion.
  This is a release gate and a prerequisite wherever SNR-06 needs that source; it
  need not block read-only scene research on the qualified local installation.
- [ ] **SNR-M02 — Explain the title counter wait.** The bounded
  [runtime join](SCENE_NATIVE_SNRM02_EVIDENCE_2026-09-22.md) maps the polling
  word to `EVENT_WRITE_SHD` command-processor stores. Establish any remaining
  submission/fence guarantee and run a bounded pacing-safe experiment. Keep
  the result independent of scene-renderer claims and retain no unconditional
  sleep/yield patch based solely on high CPU samples.

After B, select the next expansion from observed unsupported coverage and cost:
additional materials/cameras/modes, a complete shadow or post-processing chain,
then native resolution/aspect with correct projection, title visibility/culling
and original UI safe areas. Treat CPU culling and shader pixel-coordinate
assumptions as part of arbitrary-resolution work. Add another graphics backend
only for an actual target. Full Xenos removal still requires the migration
checklist's B/C acceptance; scene-native main-view success does not complete it.

Do not reopen rejected cache/clear/HUD/temporal experiments unchanged. Do not add
INFO batching, generic material inference from shader hashes, address-only
resource identities, pitch-only suppression, fake query results, broad shader
rewrites, a transplanted SDK fork or a new general RHI to this first batch.

## Evidence and handoff convention

For each completed ticket, link a concise result document with the exact code
revisions, reproduced command, captured frame range, acceptance evidence and
remaining limitations. Keep raw traces, extracted assets and local reference
checkouts in `.local`; document reproducible inputs without committing game data.
Update this checklist only when its acceptance condition passes.

Reuse the existing census/dispatch tools, scene-binding analysis, shader-pack
tools, render-test runner and drive/performance/critical-path/CPU summarizers.
Inspect historical snapshot schemas before adapting them; do not build another
capture framework merely to give this plan a new name. The consolidated
[FH1 research](RESEARCH.md) preserves ownership, immutable-state and failed
association findings; retrieve older experiments only when they answer a current
ticket's question.

[skate-hooks]: https://github.com/mchughalex/skate3recomp/blob/f6e0ae87fdfecbadb5c1e36c55d66a744187a3cd/src/skate3_native_render.cpp#L384
[skate-state]: https://github.com/mchughalex/skate3recomp/blob/f6e0ae87fdfecbadb5c1e36c55d66a744187a3cd/src/skate3_native_scene_state.h#L34
[skate-output]: https://github.com/mchughalex/rexglue-skate3/blob/7eb0faf7787f5e01333c228b8e3f03c32f7295ea/src/graphics/d3d12/command_processor.cpp#L2240
[skate-draws]: https://github.com/mchughalex/rexglue-skate3/blob/7eb0faf7787f5e01333c228b8e3f03c32f7295ea/src/graphics/d3d12/command_processor.cpp#L2518
[skate-queries]: https://github.com/mchughalex/rexglue-skate3/blob/7eb0faf7787f5e01333c228b8e3f03c32f7295ea/src/graphics/d3d12/command_processor.cpp#L262
[skate-policy]: https://github.com/mchughalex/rexglue-skate3/blob/7eb0faf7787f5e01333c228b8e3f03c32f7295ea/src/graphics/native_guest_renderer.cpp#L11
[skate-adapter]: https://github.com/mchughalex/rexglue-skate3/blob/7eb0faf7787f5e01333c228b8e3f03c32f7295ea/include/rex/graphics/d3d12/native_rhi_d3d12.h#L1
