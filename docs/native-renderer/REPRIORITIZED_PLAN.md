# Pinyon Shift native renderer reprioritized backlog

Status: active execution backlog, 2026-08-30

This is the concise implementation order for completing the native renderer.
It does not reduce the final scope. The exhaustive local research document
`docs/PINYON_SHIFT_NATIVE_RENDERER_INVESTIGATION_AND_EXECUTION_PLAN.md` remains
the source for architecture, evidence, rejected approaches, detailed acceptance
criteria, legal boundaries, and qualification methodology.

The order here is optimized to produce a visible, playable hybrid prototype
early. After that checkpoint, work continues through full semantic coverage,
production suppression, low-requirement profiles, and eventual Xenos plugin
retirement.

## Final destination

The backlog is fully complete only when:

- all required gameplay, frontend, UI, garage, loading, rewind, photo-mode,
  livery, FMV, and presentation behavior has a native implementation or a
  proven native no-op replacement;
- terrain, roads, world, vehicles, vegetation, lighting, shadows, reflections,
  transparency, post-processing, and UI have qualified native paths;
- guest-visible render targets, queries, memexport, resolves, fences, events,
  and streaming lifetimes remain correct;
- independent quality profiles materially reduce GPU time and memory while
  preserving simulation and UI correctness;
- a no-Xenos build passes the complete qualification matrix; and
- Xenos retirement has a documented rollback release.

Nothing in the original NR-00 through NR-07 scope is dropped. Items below the
prototype line are later work, not optional work.

## Safety invariants

These apply throughout the backlog:

- Xenos remains the default and authoritative fallback until its retirement
  gate is satisfied.
- Native output, pass suppression, and default selection are separate gates.
- Unknown, stale, unsupported, or failed work yields to Xenos.
- Every suppression family has an independent rollback switch.
- Guest side effects are preserved even when equivalent visual work is native.
- Save files and game assets are never modified to qualify rendering.
- Public reports remain payload-free; local captures stay below `.local`.

## Current checkpoint

Already landed or substantially qualified:

- renderer census, pass identity, graphics hooks, and capture infrastructure;
- native guest-output ownership, diagnostic output, and recovery behavior;
- authentic isolated draw replay and one-pass replay foundations;
- resource identity, invalidation, target bridging, caches, and deferred GPU
  lifetime foundations;
- exact-frame publication, private full-size composition, and dual-path output;
- the first independently reversible exact-family suppression experiment;
- bounded visibility worksets with title visibility and LOD lineage;
- exact native replay of an 80-draw dynamic shadow epoch with byte-identical
  D24S8 output and bounded multi-frame publication;
- extensive vehicle provenance plus a qualified private draw-atomic semantic
  constant bridge; exact player-local RTTI is now proved, direct entity and
  numeric-ID pose joins are closed negatively, and the exact owning
  vehicle-map pool lineage is the final bounded follow-up; and
- post-processing topology census plus the mechanical presentation ingress.

Phase A and B1-B5 are merged. The active B6 slice qualifies the first coherent
continuous frame and closes the retained-target lifecycle discovered during
the AppData run. Phase C terrain and roads are the next visible-impact target.

---

## Phase A — Close the active ingress slice

### A1. Final compositor ingress

- Finish the deterministic presentation-binding exporter and report.
- Record the exact source/destination resources, dimensions, formats, and event
  boundary.
- Classify the source as capture-local, imported, or externally produced.
- Fail closed when the expected binding is absent or ambiguous.
- Stop tracing after the minimum safe implementation boundary is known.

Exit gate:

- focused tests and payload-free documentation pass;
- no guessed effect semantics, native publication, or new suppression;
- the focused PR is merged into `dev`.

---

## Phase B — Early visible hybrid prototype

This phase is the first user-visible checkpoint. It deliberately reuses Xenos
for missing content while proving continuous native gameplay rendering.

### B1. Continuous opaque-world workset

- Promote the qualified bounded visibility workset into the existing private
  continuous composition target.
- Render multiple fresh prepared draws from a representative opaque world
  family every frame.
- Preserve title visibility, LOD admission, ordering, and capacity bounds.
- Publish only a complete current-frame target.
- Yield to Xenos when freshness or coverage gates fail.

Implementation checkpoint: bounded multi-draw target reuse and swap-committed
freshness are defined in
[`CONTINUOUS_WORLD_WORKSET.md`](CONTINUOUS_WORLD_WORKSET.md). Runtime visual
qualification remains part of the Phase B batch.

### B2. Minimal presentation path

- Use the proven presentation ingress and output dimensions.
- Implement a deterministic passthrough/upscale sufficient to display the
  native target at output resolution.
- Do not block on exact bloom, grading, motion blur, or depth-of-field.
- Preserve full-resolution UI through hybrid composition when its boundary is
  safe; otherwise fall back to the complete Xenos frame.

Implementation checkpoint: the `native_prototype` selector and deterministic
full-source presentation contract are defined in
[`NATIVE_PROTOTYPE_PRESENTATION.md`](NATIVE_PROTOTYPE_PRESENTATION.md). It
removes the diagnostic crop/checkerboard without claiming hybrid UI coverage;
unsupported or missing current-frame work still yields the complete Xenos
frame.

### B3. Prototype hybrid composition

- Combine the continuous native opaque contribution with Xenos-provided
  vehicles, transparency, effects, and UI.
- Remove diagnostic checkerboard and retained-crop presentation from the
  supported prototype scene.
- Keep Xenos draws and resolves intact; add no new suppression.

Implementation checkpoint: the complete-frame, agreement-gated compositor is
defined in [`HYBRID_PROTOTYPE_COMPOSITION.md`](HYBRID_PROTOTYPE_COMPOSITION.md).
It admits native pixels only after the title gamma conversion and only where
they agree with completed Xenos output; every mismatch remains Xenos.

### B4. First native shadow integration

- Connect the proven 2048-square dynamic shadow epoch only when its exact
  consumer resource and sampling contract are established.
- Publish the depth result with current-frame ownership.
- Report `shadow=fallback_xenos` when the exact consumer is unavailable rather
  than rejecting the entire prototype frame.

Implementation checkpoint: prototype-selected, current-frame shadow ownership
and its fail-closed Xenos fallback are defined in
[`NATIVE_SHADOW_PROTOTYPE_INTEGRATION.md`](NATIVE_SHADOW_PROTOTYPE_INTEGRATION.md).
It reuses the qualified 80-draw producer and exact Xenos render-target-dump
handoff without enabling suppression.

### B5. Prototype controls and comparison

- Keep Xenos as the default.
- Provide explicit Xenos, native-prototype, and comparison selections using the
  existing renderer configuration model.
- Report native world, shadow, presentation, fallback, and suppression states.
- Export a paired native/Xenos screenshot and machine-readable comparison from
  the same clean build.

Implementation checkpoint: the restart-gated comparison selectors now run the
same logical-scene, linear-intermediate, title-gamma presentation pipeline as
the prototype and self-arm its world and shadow observations. The paired export
contract and B6 capture procedure are defined in
[`NATIVE_PROTOTYPE_COMPARISON.md`](NATIVE_PROTOTYPE_COMPARISON.md).

### B6. Batched prototype qualification

Run focused automated checks during B1-B5, then one full validation batch:

- clean patch application and preview build;
- repository test suites;
- AppData-backed startup, open-world driving, race, pause/UI, and shutdown;
- fallback, relaunch, and renderer-reset behavior;
- absence of device removal, validation errors, fatal signatures, save-data
  changes, or unintended suppression; and
- observed median FPS, one-percent-low FPS, presentation cadence, and native
  GPU timing without making performance claims.

Prototype exit gate:

- a supported gameplay scene shows recognizable, stable, continuous native
  world rendering in the final displayed frame;
- missing families remain visibly correct through hybrid composition or clean
  Xenos fallback; and
- the result is manually testable without developer capture tooling.

Qualification checkpoint: the clean 102-patch build and AppData-backed 1x run
showed a recognizable, stable native world slice with exact current-frame
authority, continuous multi-draw accumulation, and clean Xenos fallback. The
retained source now carries draw-derived logical dimensions independently from
its padded resource. Evidence and remaining visual limitations are recorded in
[`PROTOTYPE_BATCH_QUALIFICATION.md`](PROTOTYPE_BATCH_QUALIFICATION.md). This
qualifies B6 as an early prototype; it does not enable suppression, change the
default renderer, or satisfy any Phase C family.

---

## Phase C — Complete native gameplay-scene coverage

After the prototype, expand semantic coverage in visible-impact order. Each
family follows the same ladder: exact census, semantic extraction, isolated
native output, continuous hybrid output, replay fallback, optimization, then
qualification.

### C1. Terrain and road network

- Extract world sections, meshes, materials, transforms, visibility, and LOD.
- Batch compatible opaque terrain and road instances.
- Cover representative daytime, nighttime, race, and high-speed streaming
  scenes.

Active checkpoint: the title-owned `fasttrackrender`, road-detail, and
track-command-buffer controls are proven from retail RTTI and exact AOT
instructions. The `trackfardistance` live option default and store are also
proved: baseline holds the retail `55.0`, while an isolated mode
deterministically forces `5.0`. The paired census path in
[`TERRAIN_ROAD_RENDER_PATH.md`](TERRAIN_ROAD_RENDER_PATH.md) now proves the
runtime differential against matched AppData-backed open-world sessions and
records the bounded exact-family candidate set without promoting frequency or
shader resemblance to semantic evidence. Native admission remains off until
representative candidates receive visual identity, isolated replay, and race
coverage.

The first fast-track-only isolated candidate failed the color replay contract
on its render-target layout. A subsequently matched baseline,
`noroaddetailblur`, and `notrackcommandbuffers` matrix proved both additional
title switches affect submitted work, but zero material delta joined to a
mechanically color-replay-eligible semantic candidate. The matched
`trackfardistance` `55.0`/`5.0` pair then proved a 77-family submitted-work
delta. Only one changed signature passed the mechanical color gate, and its 17
eligible draws occurred solely during the transition into the save rather than
a representative gameplay window. The title-switch leads are therefore
exhausted. C1 now moves to semantic world-section/mesh ingress instead of
collecting more broad frequency deltas. This is a lead change, not a scope
reduction: terrain/road ownership, continuous hybrid output, and
race/streaming qualification remain required.

Static ingress checkpoint: retail RTTI, complete-object locators, and full
AOT-backed vtables now prove the unified track presentation/model/instance
surfaces and the track model, mesh, procedural-geometry, and PVS-zone resource
graph. The next batched slice is the passive exact-identity runtime join from
those title-owned lifetimes to the existing procedural-model prepared-record
boundary; this checkpoint does not enable native admission or suppression.

Runtime identity checkpoint: the existing matched AppData evidence joins all
867 aggregated procedural-model submission entries (397,142 calls) to the
exact `Presentation_Unified::CTrackTexture_Unified` provider vtable and its
four proved resource-provider methods. This proves track-owned texture ingress
at the prepared-record boundary without a new capture. Track model/mesh or
world-section identity is still required before terrain/road visual admission.

Implementation checkpoint: the exact track-texture provider tuple is carried
through semantic draw identity into the fresh visibility-prepared records. The
default-off continuous prototype workset now admits ordinary fresh candidates
only with that tuple and accounts all non-track exclusions; its independently
qualified sky/horizon seed remains available. Runtime qualification is deferred
to the next batched build/AppData checkpoint. This precision filter is not yet
a terrain/road mesh identity or C1 family-admission claim.

Exact-output checkpoint: the default-off continuous workset now has a stricter
C1 selector that requires the exact unified track render-model scope and a
nonzero shared RTTI-proved world-resource identity at the procedural submission
boundary. Provider-only candidates are excluded, while the qualified sky seed,
independent exact C2 selection, Xenos draws, and fallback remain intact. The
next combined AppData run arms `-ContinuousTrackWorld`; runtime and visual
qualification remain pending before any family promotion or suppression.

Long-session output checkpoint: the continuous workset now emits a
non-mutating cumulative checkpoint every 300 observed frames. Its qualifier
requires explicit checkpoint opt-in, records session exit as unproved, and
always prefers the unique final summary. This preserves evidence from long C1/C2
runs without weakening the clean-shutdown admission gate.

Combined qualification checkpoint: the payload-free C1/C2 batch gate now
requires the exact track join, complete static-world join, catalog-backed
instance classification, and swap-committed workset reports to describe one
clean final session. It proves neither manual visual acceptance nor race and
streaming coverage. The contract and command are documented in
[`C1_C2_BATCH_QUALIFICATION.md`](C1_C2_BATCH_QUALIFICATION.md).

Phase C capture profile checkpoint: `-PhaseCQualification` now arms the exact
C1 track-world selector, exact C2 static-world selector, continuous
swap-committed workset, and passive C4 player/material provenance in one
AppData-backed process. The incompatible isolated vehicle-resource readback
stays in a later dedicated run. This gives the next manual session one clear
purpose and prevents accidental combinations that would invalidate the
continuous and shadow-depth gates.

Next runtime checkpoint: the old typed-render-item evidence is now correctly
classified by RTTI as the unified track render-model instance/model pair. A
balanced passive scope at its accepted nested dispatch (`8240EC80`-`8240ECAC`)
joins exact dynamic-type ownership and explicit shared-identity relations to
procedural-model submissions and prepared records. The implementation and
payload-free qualifier are ready; runtime proof is deferred to the next batched
AppData session. No C1 admission or suppression is enabled by this probe.

Implementation checkpoint: the exact model scope now inspects only its
already-validated 64-byte child prefix and 248-byte type-21 descriptor for
direct pointers to the seven RTTI-proved track model, mesh, submodel,
procedural-geometry, and PVS-zone object/resource vtables. A 1,024-entry
fingerprinted cache avoids repeating guest pointer validation for unchanged
graphs. Detected identities and stronger exact address equality to procedural
submission objects/resources are carried separately into prepared records.
This is ready for the same deferred AppData checkpoint; it still changes no
admission, draw, authority, or suppression decision.

Safety correction: the first batched run exposed that the guest heap page
table can label an arbitrary descriptor word readable while its translated
host page remains uncommitted. The exact classifier's speculative vtable load
faulted on guest `40D8D0D8` (RVA `5D0616F`). Every candidate pointer now also
passes the host mapping/protection query before dereference, with explicit
rejection accounting. C1 qualification remains pending a clean rerun.

Long-session evidence checkpoint: cumulative track render-model and world-graph
accounting is now durably emitted every 300 observed frames under a distinct
periodic event. A checkpoint can diagnose an interrupted run, but it explicitly
does not prove clean shutdown or permit native admission; the unique final
summary remains authoritative. This removes an observability dead end without
weakening the pending C1 gate.

Failed-batch correction: the first combined Phase C session exposed that the
static presentation runtime gate accepted only the base `CModelPresentation`
primary vtable even though the existing complete RTTI census also proves the
thread-safe ref-counted complete object's primary vtable at the same object
offset and with the same inherited slot-12 draw target. The exact owner gate now
accepts both `822432D4` and `82002464`; all resource, renderer, transform,
metadata, prepared-layout, and lifecycle joins remain independently required.
This fixes a type-family omission without weakening C2 admission.

C1 receiver-handoff correction: that same clean session observed 110,023
track-render scopes and 94,826 exact unified instance/model scopes, but zero
procedural submissions inside them. The synchronous-scope join is therefore a
disproved assumption, not a reason to gather more broad census data. Generated
title code gives a stronger bounded edge: `82437040` moves the retained
`CProceduralModels` receiver from `r25` to `r3` immediately before the semantic
producer call at `82437044`. The passive runtime bridge now attaches the exact
track owner tuple to the receiver's independently proved live generation and
requires a later semantic submission from that same generation. Reuse clears
the bridge; Xenos authority, native admission, and suppression remain unchanged
until the next batched qualification proves the new edge.

### C2. Static world buildings and props

- Expand opaque-world material and geometry coverage.
- Preserve exceptional shader states through exact replay fallback.
- Track streaming registration, invalidation, and destruction.

Static ingress checkpoint: retail RTTI and complete-object locators now prove
the generic SimpleModel mesh/submodel/model/resource chain plus immediate,
deferred, and unified presentation surfaces. All vtable extents resolve to AOT
functions or one exact reviewed adjustment thunk. The payload-free proof is
recorded in [`STATIC_WORLD_INGRESS.md`](STATIC_WORLD_INGRESS.md). Concrete
building/prop instance identity, streaming lifetime, prepared-record joining,
native admission, and suppression remain pending.

Implementation checkpoint: primary `CSimpleModelRenderer` slot 12 now has a
balanced exact scope from `82C4CCC8` to its common `82C4DEA0` exit. Its direct
`82416380` indexed-draw emissions carry the exact renderer, render-context, and
opaque graph identity through physical PM4 generation into prepared-draw
records, with periodic and final fail-closed accounting. Runtime qualification
is batched after the current guarded C1 session. This proves no concrete
building/prop instance or streaming lifetime and enables no native admission.

Lifetime checkpoint: static instruction flow now proves the 368-byte
`CSimpleModelRenderer` construction, its actual slot-16 deleting destructor,
and the bind/clear/release ownership protocol for its offset-72 graph field.
Runtime lineage carries independent renderer and graph generations and rejects
unregistered, non-live, unbound, or mismatched ownership before attribution.
The proof and batched qualifier are documented in
[`STATIC_WORLD_LIFETIME.md`](STATIC_WORLD_LIFETIME.md). Concrete graph dynamic
type and registration are closed by the next checkpoint; building/prop
identity and complete streaming invalidation remain pending.

Resource checkpoint: the renderer's bound graph is now statically proved as
the exact 320-byte `CSimpleModelResource` produced by factory `82C47F10`.
Allocation and reuse paths converge at one registration boundary, while
generation-aware construction and destruction hooks prevent address reuse
from contaminating prepared-draw provenance. Runtime qualification is batched
with C1/C2 and documented in
[`STATIC_WORLD_RESOURCE.md`](STATIC_WORLD_RESOURCE.md). Concrete building/prop
identity, mesh/material decoding, and independent streaming invalidation paths
remain required; no admission or suppression is enabled.

Payload-reset checkpoint: exact resource slots 16 and 22 both clear and
release the offset-64 owned payload, while slot 15 rebuilds through the
offset-112 graph and offset-76 binding object. Balanced hooks now advance an
independent payload generation, so a same-address resource reset cannot reuse
stale prepared-draw provenance. Static proof and the deferred runtime gate are
documented in
[`STATIC_WORLD_STREAMING.md`](STATIC_WORLD_STREAMING.md). Representative
runtime transition coverage, any additional invalidation routes, concrete
building/prop identity, and mesh/material decoding remain pending. Xenos stays
authoritative and no admission or suppression is enabled.

Invalidation-census checkpoint: all 23 `CSimpleModelResource` vtable slots are
now locked to their retail targets. Only slots 16 and 22 reset the live
offset-64 payload; slot 0 destruction reaches the base destructor that releases
the same reference. This closes the class-exposed invalidation surface while
leaving representative runtime transition coverage, external invalidation
routes, and post-transition rebinding for the batched C1/C2 AppData run. The
proof is recorded in
[`STATIC_WORLD_STREAMING.md`](STATIC_WORLD_STREAMING.md).

Member-graph checkpoint: the exact live resource now joins its embedded
`CSimpleModel` at offset 112, selected `CSimpleSubModel`, and selected
`CSimpleMesh` to the direct indexed-draw call and prepared PM4 provenance.
All three RTTI vtables and the resource-to-model address equation are checked
at runtime. Static proof and the deferred combined qualifier are documented
in [`STATIC_WORLD_GRAPH.md`](STATIC_WORLD_GRAPH.md). This closes the generic
SimpleModel member lineage, not concrete building-versus-prop semantics or
mesh/material decoding; native admission and suppression remain off.

Presentation-owner checkpoint: exact retail vtable and instruction flow now
prove `Presentation_Unified::CModelPresentation` as the synchronous owner above
the SimpleModel resource reference and renderer. Its balanced slot-12 scope
constructs/binds the renderer and invokes the renderer's exact slot-12 draw
path. The proof is documented in [`STATIC_WORLD_OWNER.md`](STATIC_WORLD_OWNER.md).
The passive runtime scope now carries the exact presentation owner and opaque
resource identity through the existing renderer/PM4/prepared-draw lineage,
with an exact offset-1608 renderer equality gate. Runtime qualification remains
batched with C1/C2. This does not prove building-versus-prop identity or
mesh/material semantics.

Presentation-type checkpoint: a complete retail RTTI hierarchy census finds
only generic `CModelPresentation` and its thread-safe reference-count wrapper;
there is no building- or prop-specific derived presentation class. Slot 7 and
the renderer bind helpers now also prove that presentation offset 148 and
renderer offset 72 hold the same exact `CSimpleModelResource`. Runtime lineage
requires that address equation before attribution. The locked census is
documented in
[`STATIC_WORLD_PRESENTATION_TYPES.md`](STATIC_WORLD_PRESENTATION_TYPES.md).
The next semantic lead is bounded resource/asset metadata, not another RTTI
subclass search.

Asset-metadata checkpoint: presentation initialization now proves that the
stored name at owner offset 16 is the exact key passed to the
`CSimpleModelResource` binder. Preparation also proves bounded 28-byte effect
and texture-reference tables at resource offsets 124/128 and 288, including
the exact `.fx`, `Id=`, and `textures\` path construction. The static proof is
documented in
[`STATIC_WORLD_ASSET_METADATA.md`](STATIC_WORLD_ASSET_METADATA.md). A
payload-free hashed runtime category census remains required before assigning
building-versus-prop semantics. No native admission or suppression is enabled.

Hashed asset-lineage checkpoint: the passive presentation observer now reads
only the proved bounded key and reference-count fields, exports no plaintext,
and carries their stable hash/length and effect/texture counts through the
renderer, PM4 packet, and prepared-draw provenance. Independent outcome and
join accounting fails closed when a renderer-joined presentation lacks valid
metadata. Runtime qualification remains batched with C1/C2; concrete
building-versus-prop labels remain unproved.

Mesh-semantics checkpoint: the SimpleMesh draw path now proves numeric
primitive type at mesh offset 36, index-buffer binding at 96, source element
count at 100, the exact primitive-count and scale/bias conversion, and the
bind/draw/clear sequence. The bounded submodel state and optional mesh material
resource branches are also locked. See
[`STATIC_WORLD_MESH_SEMANTICS.md`](STATIC_WORLD_MESH_SEMANTICS.md). Complete
shader-derived layouts and parameter metadata are handled by the prepared-layout
checkpoint below; no admission or suppression is enabled.

Runtime-lineage checkpoint: those bounded mesh and material-selection fields
are now sampled only after the exact live member-graph gates and carried through
the physical PM4 origin into prepared-draw provenance. Separate fail-closed
observation, read-fault, and packet-origin accounting is ready for the next
combined C1/C2 AppData qualification. This exports numeric identity only and
does not enable native admission or suppression.

Prepared-layout checkpoint: the exact mesh-to-PM4 join now snapshots the
complete bounded shader-derived vertex bindings and attributes plus the float,
bool, loop, and texture parameter boundary needed by a native implementation.
The 512-family census and its independent overflow accounting are documented in
[`STATIC_WORLD_PREPARED_LAYOUT.md`](STATIC_WORLD_PREPARED_LAYOUT.md). Runtime
qualification remains batched; resource payload bytes are not exported and
Xenos remains authoritative.

Instance-classification checkpoint: retail instruction flow now proves the
complete 64-byte `CModelPresentation` transform at owner offset 80 and its
slot-6 copy into renderer offset 128 before the exact draw. The passive runtime
lineage carries all 16 numeric words and their hash into prepared-draw
provenance with fail-closed accounting. Separately, the title-authored Colorado
collision and gameplay manifests produce a payload-free catalog of 24,025
hashed spatial entries (21,877 collision props and 2,148 gameplay objects).
See
[`STATIC_WORLD_INSTANCE_CLASSIFICATION.md`](STATIC_WORLD_INSTANCE_CLASSIFICATION.md).
The next combined C1/C2 AppData run must prove the matrix convention and a
unique runtime-to-catalog match; no building/prop category, native admission,
or suppression is claimed yet.

Category-join implementation checkpoint: the offline qualifier now tests both
plausible 4x4 translation layouts against the hashed spatial catalog. It
requires a unique convention, at least eight distinct exact matches including
a collision prop, zero ambiguous/unmatched/non-finite transforms, a clean
process lifecycle, and a complete static-world runtime summary. The qualifier
is ready for the deferred combined AppData run; it cannot self-qualify from
static fixtures and still enables no native admission or suppression.

Native-output implementation checkpoint: the existing one-frame,
swap-committed continuous world target now has an independent default-off
static-world selection. It admits only mechanically replayable draws carrying
the exact presentation/resource, hashed asset, transform, member-mesh, and
bounded prepared-layout lineage, with separate request and rejection
accounting. It neither embeds the local catalog nor changes the normal
prototype selector, Xenos execution, publication authority, or suppression.
Runtime and visual proof is batched with the pending C1/C2 AppData run.

### C3. Semantic batching, culling, and LOD

- Promote the existing visibility and prepared-draw evidence into production
  semantic worksets.
- Implement conservative native frustum/distance culling and title-derived LOD.
- Preserve query and guest-visible behavior independently from visual culling.
- Prove material reductions in draw count and submission time.

Implementation checkpoint: the bounded visibility-to-prepared candidate table
now preserves independent exact C1 track-world and C2 static-world family tags.
Its payload-free report reconciles generic static origins and the stricter
presentation/resource/mesh/transform-qualified subset before any production
batch, native culling, or native LOD policy is enabled. Runtime qualification is
batched with the pending representative C1/C2 AppData session; Xenos remains
authoritative and suppression stays disabled.

Batch-planning checkpoint: the exact world-family mask is also part of the
order-preserving semantic opportunity key. Generic, exact-track, and
exact-static draws therefore cannot extend one another's runs solely because
their GPU resources match. The report exposes family-local multi-draw evidence
without admitting an executor; runtime qualification remains in the same
deferred C1/C2 session.

LOD-safety checkpoint: exact title-LOD validity and the normalized title index
are now also part of the semantic batch key. Missing observations collapse only
to `(false, 0)`, while different proved LODs can never share a run. Family-local
LOD opportunity signals remain measurement-only; independent native LOD
selection is still disabled until the batched runtime evidence proves this
passthrough boundary.

### C4. Player and traffic vehicles

- Resume vehicle work from the documented rejected paths rather than repeating
  broad provenance searches.
- Establish a reliable object-to-render transform, mesh, material, wheel, and
  livery contract.
- Implement player vehicle first, then traffic and exceptional materials.
- Retain per-item replay fallback until semantic coverage is complete.

Shadow-geometry ingress checkpoint: the already qualified exact 80-draw
dynamic-vehicle shadow epoch now seeds a bounded, default-off cross-pass
resource correlation. Geometry is staged during the consecutive epoch and
committed only after backend confirmation of all 80 draws; interruptions and
replay failures discard the entire set. Later indexed color draws must share
either the complete geometry resource set or the exact index buffer plus an
exact vertex resource. The observer exports only hashes and numeric resource
identity, captures no guest payload, draws nothing, preserves Xenos authority,
and cannot suppress. The next batched gameplay run determines whether this
produces a working player-vehicle color ingress before transform, wheel,
livery, traffic, and full material contracts are added.

Color-family hardening checkpoint: correlated draws are now partitioned by
exact draw arguments, geometry, texture resources, prepared pipeline, and the
committed shadow seed rather than by a loose shader family. Stable aggregate
records retain draw/frame coverage and parameter-switch counts, so animated
pose candidates can be identified without exporting constant payloads and
different submeshes or liveries cannot silently collapse together. Runtime
qualification remains part of the next batched gameplay run.

Same-session visual checkpoint: an independent opt-in now privately replays
the first mechanically eligible correlated color family after the full shadow
epoch has been committed. It captures native and Xenos color targets in the
same long session, never publishes the private target, preserves the original
Xenos draw, and cannot suppress. This is intended to produce the first direct
C4 image pair without requiring a second gameplay run.

Batched ingress result: the first AppData qualification committed one exact
80-draw epoch with 68 unique geometry seeds and no overflow. Across 1,929
loaded-game frames it found 57,870 exact full-resource color matches in 30
bounded families; every family changed its parameter hash on every subsequent
frame. This confirms a stable animated vehicle color ingress, while still not
proving object identity or a complete material contract. No private color
capture request was issued because none of the correlated draws passed the
existing isolated-draw mechanical gate.

Replay-gate diagnostic checkpoint: each matched draw now records the exact
mechanical rejection mask before capture selection. Bounded family aggregates
retain eligible/rejected draw counts, first/last/OR/AND masks, and mask-switch
counts; the final summary emits per-reason draw totals and strict accounting.
This does not relax admission, publish a native target, capture guest payload,
or allow suppression. The next batched run will identify the smallest missing
geometry, texture, pipeline, or render-target contract before any native
vehicle implementation is admitted.

Replay-gate result: a clean AppData session reproduced all 30 families across
25,200 exact matches. Every draw retained the same `00000808` generic mask:
three-stream vertex input and zero sampled textures. All other rejection
reasons were zero, and every family kept the same mask across 840 animated
frames. Backend inspection confirms that private replay restores and duplicates
the already-prepared guest pipeline, bindings, and texture state; the one-stream
and at-least-one-texture rules belong to payload snapshot serialization rather
than backend replay.

Private vehicle capture therefore uses a narrower admission contract. It still
requires bounded geometry, no overflows, supported indexed input, complete
prepared pipeline and render targets, no query, memexport, or resolved input,
and at most four valid textures. It additionally permits bounded multi-stream
input and a shader that samples no textures. Generic isolated-draw admission is
unchanged. This exception remains correlation-gated, private, one-shot,
non-publishing, Xenos-authoritative, and unable to suppress.

First visual result: the next AppData session privately replayed exact family
`436C58CA13690625` at frame 2,633, draw 4,358 into a 2560x1024 target. The
cropped native and Xenos images contain the same rear vehicle body/bumper
submesh, and their full raw source hashes are identical
(`F30FFA26CCF670DD`). All 7,320 correlated draws in that session passed the
private vehicle gate, while generic admission remained closed. This proves one
working animated vehicle color slice, not a complete car or material system.

Private stability checkpoint: after the one-shot image pair succeeds, the same
exact prepared signature may now replay privately at most once per frame for a
hard limit of 300 draws. It performs no further readbacks, never publishes,
never suppresses, and stops all later private requests on the first backend
failure. Final accounting distinguishes recorded draws, target failures,
unsupported state, per-frame quota yields, and limit yields. Long-session
success is required before considering visible native publication of this
submesh.

Private stability result: the AppData qualification reached the complete
300-request bound with 300 recorded replays, zero target failures, zero
unsupported states, and no per-frame quota misses. A further 168 matching
frames were correctly declined after the limit. The session observed 14,070
exact correlations, exited normally, and logged no error or crash. The exact
submesh is therefore stable in private animated replay, but native admission
remains closed because player identity and complete vehicle coverage are not
yet proven.

Full-vehicle topology checkpoint: matched color draws are now grouped into
exact consecutive prepared-draw runs. The census records run count, matched
draw accounting, multi-draw runs, maximum length, runs covering the complete
bounded family table, and the ordered signature hash of those full-family
runs. It remains measurement-only. A stable full-family sequence is the gate
for assembling the 30 proven submeshes into one retained private vehicle pass.

Topology result: the clean AppData run observed all 30 families exactly once
per frame for 187 consecutive frames (5,610 matches), but unrelated guest work
partitions them into 2,992 consecutive runs whose maximum length is five. A
single consecutive 30-draw pass therefore does not exist. The retained-pass
gate is corrected to the stronger frame-wide contract already implied by the
per-family summaries: all 30 exact families, once each in original guest draw
order, may accumulate across unrelated Xenos draws in one private target.

Retained-pass implementation checkpoint: the default-off qualification mode
starts only after the one-family native/Xenos capture succeeds and the exact
correlation table contains 30 families. It retains the first matching draw,
reuses the private target for the remaining 29 in guest order, releases and
optionally reads back only the complete frame, and repeats for at most 120
frames. Missing, extra, non-monotonic, unsupported, or failed work disables the
path for the process. It never publishes, suppresses, or changes Xenos output
authority.

Retained-pass result: the clean AppData run completed all 120 bounded frames
and recorded all 3,600 requested draws, including 3,480 retained-target reuses,
with zero failures, unsupported replays, errors, or suppression. Its one
readback contains a coherent multi-submesh rear view with body, bumper,
glazing, wheels, and lower geometry in the same native target. This closes the
frame-wide retention mechanism. The result remains an isolated unlit
diagnostic; exact player identity, transforms, material completeness, hybrid
publication, traffic coverage, and per-item fallback remain open C4 work.

Transform-identity implementation checkpoint: every exact correlated color
draw now compares its already-bounded vertex constants with title-owned vehicle
positions and both forward signs no more than one frame old. Per-family
accounting distinguishes unique, ambiguous, and missing matches and requires a
stable constant register and identity across every observation. The offline
gate recognizes a complete shared vehicle-transform candidate only when all 30
families consistently name the same generation, owner, and slot. No constant
payload is exported, and the result cannot label the instance as the player,
publish native output, or suppress Xenos. Runtime evidence is batched with the
next C4 AppData session; the contract is documented in
[`VEHICLE_COLOR_CONSTANT_IDENTITY.md`](VEHICLE_COLOR_CONSTANT_IDENTITY.md).

Material-topology implementation checkpoint: the same 30 exact families now
carry a geometry-independent key over shader identity and specialization,
prepared render state, and texture layout. Pixel-float parameter changes are
counted through hashes without exporting their values. The v8 report groups
every family by that key, providing the bounded mechanical topology needed to
target body, glass, wheel, light, livery, and exceptional-material follow-ups.
Hashes do not receive semantic labels and cannot establish completeness,
publication, or suppression. Runtime evidence is combined with the pending
transform census; the contract is documented in
[`VEHICLE_MATERIAL_TOPOLOGY.md`](VEHICLE_MATERIAL_TOPOLOGY.md).

Combined transform/material result: the clean merged-`dev` build loaded the
AppData save and exited normally with no error or fatal log entries. The
retained full-vehicle diagnostic again completed 120/120 frames and all 3,600
draws, including 3,480 retained-target reuses, with zero failures. Across
18,360 correlated draws, the constant census completed 18,360 scans and
18,207,360 comparisons but found no stable world-position carrier in the raw
vertex constants; the nearest squared position delta was still about 753,399.
Forward matches were close but ambiguous. The v8 report therefore correctly
keeps the shared-transform and object-identity gates closed.

The material census reconciled all 30 families into one stable mechanical
topology while every family varied its hashed material parameters. C4 is now
re-prioritized around the typed constant/material upload and bind edges: first
recover the exact player transform carrier and semantic player discriminator,
then label body, glass, wheel, light, and livery contributions within the
shared topology. More broad raw-constant or hash-only scans are deferred. The
retained private pass remains the stable geometry/output harness throughout.

Typed constant-upload implementation checkpoint: the exact generic title
writer at `82435E78` now feeds a bounded 8,192-entry recent-upload ledger. Each
entry retains its destination register range, title source/destination
addresses, exact caller return address, and per-vector semantic hashes without
exporting constant values. Every
exact vehicle color family joins its observed vertex registers to uploads no
more than one frame old. The first AppData run strictly accounted 2,419,537
writer observations and 16,230 vehicle draw scans, but the whole-range rule
produced zero matches because prepared observations contain only constants
referenced by the active shader. The rule is rejected and replaced by an exact
shader-used subset join. The v10 qualifier requires
complete upload/outcome accounting and recognizes a 30-family bridge only
when every family matches on every draw with a stable caller, upload range, and
consumed subset size. Runtime proof remains batched with the next substantial
C4 slice; the corrected contract and first-run evidence are documented in
[`VEHICLE_TYPED_CONSTANT_UPLOAD.md`](VEHICLE_TYPED_CONSTANT_UPLOAD.md).

Shader-used subset qualification result: the AppData-backed
`20260831T184645Z-p11956` run exited normally and strictly accounted 2,245,612
writer observations, including 469,815 valid uploads and zero invalid source
ranges. It reproduced all 30 families across 15,750 exact geometry matches but
the subset rule still produced zero upload matches. The join is therefore not
promoted. The next bounded slice partitions every fresh candidate into
no-overlap, hash-mismatch, or exact outcomes and records each family's observed
register envelope without exporting values. This selects the next exact
contract before any semantic caller bridge, native admission, or suppression.

The short v11 run `20260831T190405Z-p11884` completed that partition across
11,880 draws and 8,331,453 fresh candidates. It found 1,330,751 real register
overlaps and the same observed `0..255` register envelope in all 30 families;
therefore neither freshness nor register space explains the failed join. The
v12 contract reconstructs exact last-writer provenance per shader-used
register, allowing later writes to replace unrelated vectors from a broader
upload without erasing exact matches. It still requires exact index/hash
equality for every credited register and changes no draw authority.

Per-register qualification result: the corrected AppData run
`20260831T191732Z-p39892` completed 308 exact epochs and 9,210 correlated draws
across all 30 families, but found zero exact typed-writer register matches.
This closes the generic title writer route. The next bounded slice observes the
command processor's final shader-register writes instead, retaining exact
packet and command-buffer lineage for current vertex-constant components. A
fixed 4,096-source table aggregates source identity by family, packet header,
packet offset, and nesting depth while retaining dynamic buffer length and
physical-address variation as evidence. Strict component/source accounting
selects the semantic command-buffer producer before player identity,
publication, or suppression can advance.

Command-stream qualification `20260831T200117Z-p31000` is bounded and
repeatable: 255 exact epochs, 7,650 correlated draws, and all 30 families were
observed. Final register state matched 114,750 of 122,400 shader-used vectors
(15 of 16 per draw), with no missing or split-component vectors and zero-frame
age. The structural packet table retained 1,620 sources without overflow.
The draw-atomic follow-up `20260831T203519Z-p39592` identifies register 254 as
the sole mismatch: all four components differ on every one of 14,505 matched
draws, with no mask variation, while the other 15 vectors remain exact. This
proves a special-register path rather than observer timing drift.

First semantic constant-bridge checkpoint: all 14,505 matched draws now publish
a private current-draw snapshot into the bounded 30-family table with zero
rejections and zero register-layout variations. Each family carries the same
16 shader-used registers, 15 exact packet-lineage vectors, and one explicitly
unresolved register-254 vector. The bridge exports hashes and counts only,
draws nothing, publishes nothing, and cannot suppress Xenos. It is sufficient
to advance the retained player-vehicle harness without attributing register
254 to a guessed title producer. The next C4 slice joins player identity and
mesh/material roles to this snapshot, then uses per-item replay fallback for
unresolved or exceptional work.

Player/traffic semantic-ingress checkpoint: retail RTTI now locks distinct
`player_local`, `ai`, `traffic`, and `player_remote` map-entity vtables. Shared
slot 11 returns the exact vehicle ID at offset 12, while shared slot 3 returns
the title-owned semantic type-name pointer at offset 16. A default-off passive
hook on the getter admits only those exact vtables and retains bounded direct
entity/source, entity/owner, and vehicle-ID/pose-slot correlations. The static
proof and pending runtime gate are documented in
[`VEHICLE_PLAYER_INGRESS.md`](VEHICLE_PLAYER_INGRESS.md). Runtime qualification
is batched with the next meaningful C4 slice; until it proves one stable unique
player-to-pose relationship, player attribution, mesh/material labels, native
publication, and suppression remain closed.

Resource-contribution checkpoint: the existing 30 retained prepared-signature
families reduce exactly to 15 geometry-resource contributions, each with two
distinct prepared variants and otherwise identical mechanical state. The
offline fail-closed partition is documented in
[`VEHICLE_RESOURCE_CONTRIBUTIONS.md`](VEHICLE_RESOURCE_CONTRIBUTIONS.md). C4
role attribution now targets those 15 exact resources; prepared signatures
alone cannot carry a semantic label because two resources reuse one signature
pair. A default-off private capture now retains the two exact variants for one
selected resource, releases after the second, and reads back only that bounded
contribution while preserving both Xenos draws. The next batched gameplay run
qualifies the first isolated resource result and joins it to an independent
title-owned asset/material discriminator before
assigning body, glass, wheel, light, livery, or exceptional-work labels.

Asset/material discriminator checkpoint: retail construction now proves the
exact title-owned tire/wheel shader-settings path builder and its root-plus-1056
binding object. A passive bounded hook hashes only the model-owned asset key,
retains Normal/SLOD and UI flags, and records exact title draw-argument joins.
The static proof and pending runtime gate are documented in
[`VEHICLE_ASSET_MATERIAL_BINDING.md`](VEHICLE_ASSET_MATERIAL_BINDING.md).
This narrows one independent semantic family without guessing from shared
shader topology; per-resource role labels remain closed until the next batched
visual-contribution run agrees with this title-owned evidence.

Runtime material-join checkpoint: a strict payload-free qualifier now maps
the binding census's exact backend signatures onto the 15-resource partition.
It produces a unique tire/wheel contribution candidate or one of two bounded
negative results (no direct draw join or an ambiguous multi-resource join).
Visual-role proof remains independently closed until isolated output agrees,
so this tooling can be exercised in the combined Phase C session without
weakening native admission or Xenos fallback.

### C5. Sky, atmosphere, and global lighting

- Replace the qualified sky/global-light families.
- Preserve exposure and downstream target dependencies until the native post
  chain owns them.

### C6. Vegetation, crowds, and repeated world instances

- Build instanced native paths with measured density and LOD behavior.
- Preserve ordering and alpha-test semantics.

### C7. Transparent scene and gameplay effects

- Add ordered transparent rendering, particles, weather, and remaining effects.
- Keep exceptional or order-sensitive work on replay until independently
  qualified.

Scene-coverage exit gate:

- open world and active races have coherent native terrain, roads, static
  world, vehicles, sky, vegetation, transparency, and gameplay effects;
- unsupported items fall back individually without losing the frame;
- representative heavy scenes materially reduce the roughly 2,000-draw
  baseline; and
- streaming and long-session qualification remain green.

---

## Phase D — Complete lighting, reflections, and presentation

### D1. Full shadow system

- Finish static/dynamic caster ownership and atlas-region classification.
- Implement required cascades or equivalent qualified regions.
- Cover terrain, world, vehicle, vegetation, and exceptional casters.
- Add profile-ready shadow resolution and distance controls.

### D2. Reflection system

- Classify and implement cubemap, planar, probe, vehicle, and other observed
  reflection paths.
- Preserve update cadence and render-to-texture consumers.
- Add independently selectable simplified and full modes.

### D3. Native post-processing chain

Implement in dependency order:

1. scene input and output-resolution upscale;
2. tone mapping and exposure;
3. color grading;
4. bloom;
5. motion blur where required and validated;
6. depth-of-field where required;
7. remaining measured screen-space effects; and
8. full-resolution UI/HUD composition.

Each effect receives a native implementation, Xenos/replay fallback, visual A/B
report, timing report, independent gate, and documented reduced-quality mode.

### D4. Frontend and special-mode coverage

- Frontend and HUD.
- Garage and autoshow.
- Loading screens and FMVs.
- Rewind and photo mode.
- Liveries, thumbnails, mirrors, and other guest-visible render-to-texture work.
- Save/reload and map-transition freshness.

Presentation exit gate:

- the required gameplay and non-gameplay scene matrix is visually complete in
  native-selected mode;
- UI remains output-resolution and legible;
- every render-target consumer is native, bridged, or deliberately retained;
- native/Xenos visual differences are documented and accepted.

---

## Phase E — Production hybrid renderer and measured suppression

This phase turns complete native coverage into real performance savings.
Suppression remains independently reversible and proceeds only from exact
dependency evidence.

### E1. Close the renderer census

- Reach the original NR-00 classification and dependency gates across every
  required scene.
- Keep unknown and low-confidence work explicit.
- Identify every guest CPU read, query, memexport, resolve, and later texture
  consumer.

### E2. Harden resources and streaming

- Complete physical resource generations, guest-write invalidation, buffer and
  texture formats, render-target bridging, PSO/descriptor caches, workers,
  deferred destruction, and memory budgets for all covered families.
- Pass long high-speed routes, address reuse, map transitions, cache pressure,
  and device-shutdown stress.

### E3. Expand pass-level suppression

Admit one exact family at a time:

1. presentation-only work with no downstream dependency;
2. complete opaque scene;
3. transparent scene;
4. redundant Xenos post-processing;
5. native-owned depth, shadow, and reflection producers; and
6. remaining replayed families after full coverage.

For every family:

- preserve PM4 parsing, queries, events, fences, memexport, resolves, and
  guest-memory effects;
- prove paired visual coverage before suppression;
- measure an actual Xenos GPU-time reduction;
- qualify failure, warm-up, cooldown, stale-frame, and rollback routes; and
- keep an independent switch until final retirement.

### E4. Production state-based yield and recovery

- Cover boot, loading, frontend, garage, rewind, photo mode, FMVs, unknown
  states, renderer failure, and stale scene generations.
- Guarantee a complete Xenos fallback before any native write.
- Expose renderer state and recovery actions in launcher diagnostics and support
  bundles.

Hybrid-production exit gate:

- continuous native output is stable across the full scene matrix;
- suppressed families show measured CPU/GPU benefit;
- save, reload, pause, exit, relaunch, and long sessions remain correct;
- no guest side-effect dependency is lost; and
- all suppression behavior has a tested rollback.

---

## Phase F — Low-requirement renderer profiles

Complete original NR-06 after the production hybrid path is stable.

### F1. Independent scene resolution

- Profile-controlled 3D resolution with output-resolution UI.
- Correct sampling, half-pixel behavior, and stable upscale.

### F2. Geometry and world controls

- LOD bias, visual world distance, traffic draw distance, vegetation density,
  far impostors, and shadow-caster distance without changing simulation.

### F3. Material and effect tiers

- Full and reduced materials.
- Shadow, reflection, SSAO, bloom, motion-blur, atmosphere, and AA tiers.
- Explicit format and memory tradeoffs.

### F4. CPU builds and hardware qualification

- Preserve the SSE4.1 baseline and optionally provide an AVX2 build.
- Qualify development, midrange, low-end discrete, integrated, and available
  handheld-class hardware.
- Record median, p95/p99, memory, and recovery behavior per profile.

Profile exit gate:

- Minimum materially reduces GPU time and native memory versus Balanced;
- UI, input, physics, audio, saves, and game logic are unchanged;
- conservative automatic defaults and manual recovery are reliable.

---

## Phase G — Xenos plugin retirement

This remains last because it has the highest compatibility risk and little
benefit after successful main-scene suppression.

### G1. Remaining dependency closure

- Inventory every remaining Xenos-only pass and side effect.
- Replace it natively or prove it unnecessary.
- Close queries, fences, events, memexport, guest-visible render targets, and
  presentation semantics.

### G2. No-Xenos build

- Add a build configuration with no runtime Xenos GPU-plugin dependency.
- Retain diagnostic and recovery paths suitable for the new architecture.

### G3. Release-candidate qualification

- Run every required scene, save/reload, garage, race, rewind, frontend,
  special mode, and long-route test.
- Verify performance and memory are no worse than the qualified hybrid build.
- Maintain an extended release-candidate period.
- Publish a documented rollback release before removing the ordinary fallback.

Final exit gate:

- no runtime Xenos GPU-plugin load or dependency;
- no unimplemented guest graphics side effect;
- complete qualification and long-session matrices pass;
- the no-Xenos renderer is recoverable, supportable, and release-ready.

---

## Original-epic coverage map

| Original epic | Reprioritized phases |
|---|---|
| NR-00 — Census and pass identity | Existing foundation; A, C, D, E1, G1 |
| NR-01 — Guest-output bridge | Existing foundation; B2-B5, E4, G2 |
| NR-02 — Authentic replay | Existing foundation; B1, C, D |
| NR-03 — Resources and streaming | Existing foundation; B, C, E2 |
| NR-04 — Continuous hybrid rendering | B, E3-E4 |
| NR-05 — Semantic Forza fast paths | B1-B4, C, D |
| NR-06 — Low-requirement profiles | F |
| NR-07 — Xenos retirement | G |

## Validation cadence

To avoid spending most implementation time on repeated full builds:

- run focused unit, schema, formatter, and static checks per implementation
  slice;
- batch related PR work before a clean preview build when safety permits;
- run one AppData-backed gameplay session at each phase exit or when a runtime
  contract changes materially;
- run the full multi-scene matrix only at prototype, production-hybrid,
  profile, and retirement gates; and
- never weaken a fail-closed gate merely to obtain visible output.

## Decision rules

- After B1, inspect one representative frame. If it is still only a diagnostic
  fragment, spend one bounded slice on the missing opaque-world family before
  broadening the census again.
- If native world composition remains temporarily blocked, a native
  presentation/upscale over the complete Xenos scene may become the first
  visible demonstration, but it does not replace B1 or remove any later work.
- Reopen a deep investigation only when it blocks the next concrete rendering
  acceptance gate. Start from the original document’s evidence and rejected
  paths.
- Prefer visible vertical slices over completing every subsystem horizontally,
  while still closing every original epic before final completion.
- Never market prototype or hybrid results as a native-only renderer.

## Working rules

- Use focused `arcanite24/*` branches and PRs against `dev`.
- Use conventional commits and keep each PR independently reviewable.
- Preserve user-local work and local qualification artifacts.
- Launch AppData-backed tests only through the repository’s documented preview
  script and exact installed preview state root.
- Keep the exhaustive plan for technical detail; update this file for ordering,
  phase status, and completion decisions.
