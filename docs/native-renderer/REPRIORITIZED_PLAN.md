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
- extensive vehicle provenance investigation, without a qualified semantic
  vehicle rendering bridge yet; and
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
vertex-fetch layouts and material parameter blocks remain open; no admission
or suppression is enabled.

### C3. Semantic batching, culling, and LOD

- Promote the existing visibility and prepared-draw evidence into production
  semantic worksets.
- Implement conservative native frustum/distance culling and title-derived LOD.
- Preserve query and guest-visible behavior independently from visual culling.
- Prove material reductions in draw count and submission time.

### C4. Player and traffic vehicles

- Resume vehicle work from the documented rejected paths rather than repeating
  broad provenance searches.
- Establish a reliable object-to-render transform, mesh, material, wheel, and
  livery contract.
- Implement player vehicle first, then traffic and exceptional materials.
- Retain per-item replay fallback until semantic coverage is complete.

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
