# Pinyon Shift native renderer V3 backlog

Status: active north star, 2026-09-01

This document is the execution order for finishing the native renderer. It
supersedes `REPRIORITIZED_PLAN.md` for prioritization and day-to-day decisions,
but it does not replace the evidence and architecture recorded there or in
`PINYON_SHIFT_NATIVE_RENDERER_INVESTIGATION_AND_EXECUTION_PLAN.md`.

V3 is organized around one correction: isolated native draws and isolated
targets are not a scene. The shortest route to visible progress is to retain
the required scene families, prove that they belong to the same frame and
camera, and compose them before publication.

The final scope is unchanged. The early milestone is deliberately smaller so
that a camera-correct, drivable hybrid renderer is available before completing
every effect and retiring Xenos.

## Current truth

The following foundations are merged or substantially qualified on `dev`:

- native D3D12 draw replay into private render targets;
- shader, resource, material, pass, camera, draw, and ownership provenance;
- resource identity, caching, invalidation, deferred destruction, and GPU
  lifetime handling;
- continuous replay worksets and exact procedural-color replay;
- private resolve assembly and presentation ingress;
- exact native replay of a bounded dynamic-shadow epoch;
- Xenos fallback, fail-closed publication, renderer selection, and independent
  suppression controls;
- capture, comparison, report, and AppData-backed qualification tooling; and
- reproducible application of the complete ReXGlue patch series.

The following are not complete:

- a coherent native open-world frame;
- camera-consistent composition of terrain, road, static world, sky, and
  vehicles;
- a drivable native or hybrid prototype with acceptable frame pacing;
- complete lighting, reflections, transparency, post-processing, frontend,
  and special-mode coverage;
- production pass suppression and material Xenos workload reduction;
- independent low-requirement quality profiles; and
- a no-Xenos build.

The current supported path keeps Xenos authoritative. Native worksets remain
private because publishing the last isolated target produced the wrong view
and an incomplete world. The experimental scaled accumulator is not a
complete-scene source and must not be used as the prototype architecture.

## Rejected approaches and retained lessons

These paths produced useful evidence and infrastructure, but they did not
produce a coherent gameplay scene. Do not restart them as prototype leads
without satisfying the stated revisit condition. Detailed chronology and
runtime evidence remain in the earlier plans and their linked reports.

| Approach | Observed result | V3 decision | Reusable work | Revisit condition |
| --- | --- | --- | --- | --- |
| Publish the last completed isolated target | Displayed whichever scene family finished last, producing the wrong camera, repeated fragments, and a missing open world | Rejected as a scene architecture; [PR #308](https://github.com/arcanite24/pinyon-shift/pull/308) restored Xenos-authoritative output | Isolated replay, target identity, invalidation, and publication safety gates | Do not revisit; replace it with camera-consistent multi-target composition |
| Treat the procedural scaled accumulator as a complete scene | Correctly assembled regions from one procedural producer, but could not supply terrain, static world, vehicles, and background as one frame | Retain as diagnostic and producer evidence only | Resolve topology, source-region contracts, exact copies, and private accumulation | May feed one compositor slot after V3-01, but must never define scene completeness |
| Present the accumulator at 2x draw scale | Produced incomplete output and triggered `DEVICE_HUNG`/TDR GPU resets during qualification | Deferred; 1x composition is the only supported prototype target | Scaled-layout contracts, source-row calculations, failure evidence, and fail-closed gates | Reconsider only after V3-04 is stable at 1x and a GPU capture identifies and removes the unsafe path |
| Run broad census, hashing, and observers continuously | Improved provenance knowledge but processed very large draw volumes and materially harmed prototype CPU cost | Discovery features default off; enable only a bounded observer for a named blocker | Capture tools, semantic classifiers, counters, and provenance reports | Enable temporarily when a V3 exit gate cannot be answered by existing evidence or focused tests |
| Split one capability into topology, counter, request, result, and qualification PRs | Kept individual diffs small but multiplied CI, clean-build, review, documentation, and integration overhead while delaying visible results | Use vertical capability PRs with their minimum instrumentation and tests included | Focused tests and narrowly scoped commits remain useful inside a larger PR | Split only across a genuine safety boundary or when a single capability cannot be reviewed independently |
| Fully qualify every small change with an AppData run | Repeated expensive builds and gameplay sessions often reconfirmed unchanged behavior | Batch runtime qualification at V3 batch exits or true runtime-only blockers | AppData launch procedure, capture scripts, reports, and crash bundles | Run early only when synthetic tests cannot establish safety or a runtime observation determines the next implementation step |

General lesson: instrumentation is valuable when it closes a decision. A V3
change should primarily create a compositor capability, integrate a required
producer, make the scene visible, or remove measured prototype cost. Evidence
collection is supporting work rather than a milestone by itself.

## North-star milestones

### Milestone 1 — Drivable hybrid prototype

At one fixed reference configuration, the player can drive through the open
world while the native renderer supplies the essential gameplay scene and
Xenos supplies unsupported presentation work.

Required native scene families:

- sky or horizon clear/background;
- opaque terrain and road;
- opaque static world geometry; and
- the player vehicle.

Allowed Xenos work:

- UI and HUD;
- unsupported transparent effects;
- post-processing;
- traffic, crowds, and nonessential decoration; and
- any family that fails closed without corrupting the native scene.

Prototype acceptance gate:

- use 1x draw scale and the established 1280x720 logical reference path;
- use the installed AppData save and a repeatable festival-to-open-world route;
- the native view matches the Xenos camera, projection, and player position;
- the minimum native family set comes from one agreed frame and camera;
- missing, stale, or ambiguous families atomically yield to Xenos;
- driving does not expose repeated, stacked, frozen, or last-target output;
- the reference route sustains the 30 fps target without severe recurring
  frame-time stalls;
- no device removal, TDR, crash, guest-memory mutation, or save mutation;
- Xenos remains available as an immediate comparison and fallback; and
- paired screenshots and a frame-time report are attached to the milestone.

### Milestone 2 — Complete production hybrid

All normal gameplay and frontend scenes have native coverage, and qualified
native families can suppress equivalent Xenos visual work. Unsupported or
failed work still falls back independently.

### Milestone 3 — Native-only release candidate

All guest-visible rendering dependencies have native implementations or
proved native no-op replacements. A no-Xenos build passes the full scene,
stability, performance, and recovery matrix.

## Prototype critical path

The first four batches form one vertical slice. Avoid side work that does not
remove a listed exit-gate blocker.

### V3-01 — Scene-frame compositor contract

Build the structure that the previous accumulator path was missing.

- Define retained slots for background, opaque world, static world, player
  vehicle, and later optional families.
- Attach exact guest frame, camera, projection, viewport, resolution, sample
  topology, and attachment identity to every candidate.
- Define a minimum-family coverage mask and deterministic composition order.
- Reject mixed-frame, mixed-camera, stale, duplicate, or ambiguous candidates.
- Keep targets private until the complete minimum set passes the agreement
  gate.
- Preserve Xenos output and all guest-visible side effects.
- Add bounded compositor state reporting without broad per-draw census.

Exit gate:

- tests prove retention, replacement, invalidation, ordering, agreement, and
  atomic fallback;
- a synthetic complete frame composes deterministically;
- an incomplete frame never publishes; and
- no application gameplay run is required unless a contract cannot be proved
  synthetically.

### V3-02 — Opaque open-world producers

Feed the compositor with the largest visible part of the scene.

- Route qualified terrain and road work into the opaque-world slot.
- Route qualified buildings and large static props into the static-world slot.
- Preserve depth behavior needed to join both families.
- Bind producer output to the exact scene-frame contract from V3-01.
- Prefer already proved render paths; add instrumentation only for a specific
  unresolved producer boundary.
- Do not publish partial world targets.

Exit gate:

- a private capture contains camera-correct terrain, road, and representative
  static geometry together;
- target ownership survives ordinary streaming and attachment reuse;
- incomplete coverage yields cleanly; and
- focused tests plus one batched AppData capture qualify the producer set.

### V3-03 — Background and player vehicle

Complete the minimum gameplay family set.

- Retain the qualified sky, horizon, or background-clear family.
- Route player-vehicle opaque color and required depth into its own slot.
- Use exact camera and player ownership; do not admit hash-only correlations.
- Compose vehicle and world depth deterministically.
- Keep traffic, glass, particles, shadows, and reflections optional for this
  milestone.

Exit gate:

- a private composed frame contains background, world, static geometry, and
  the correctly positioned player vehicle;
- the view matches a paired Xenos capture at the same frame and camera;
- missing vehicle or background work causes fallback instead of a partial
  native frame; and
- focused tests plus one batched AppData capture pass.

### V3-04 — Hybrid publication and prototype performance

Make the minimum scene visible, drivable, and affordable.

- Publish only complete, camera-agreed scene frames.
- Compose Xenos UI and unsupported effects over or with the native scene.
- Provide immediate Xenos, hybrid, and comparison selections.
- Disable discovery census, broad hashing, verbose observers, readback, and
  captures by default.
- Cache semantic classification and avoid replaying rejected work.
- Bound retained targets, command lists, uploads, and deferred destruction.
- Measure CPU time, GPU time, memory, frame pacing, and fallback frequency.
- Optimize the reference route before adding resolution scaling.

Exit gate:

- all Milestone 1 acceptance criteria pass in one complete qualification run;
- paired Xenos and hybrid screenshots demonstrate camera and scene agreement;
- logs contain no device removal, GPU validation error, native publication
  rejection loop, or unbounded resource growth; and
- the prototype is merged behind an explicit nondefault selector.

## Completion backlog after the prototype

These batches remain mandatory. Their order prioritizes gameplay coverage and
performance before removing the fallback.

### V3-05 — Gameplay-scene breadth

- traffic and non-player vehicles;
- vegetation, crowds, repeated instances, and LOD/culling behavior;
- transparent world and vehicle materials;
- particles, weather, lens effects, and gameplay overlays;
- rewind, streaming transitions, races, and representative open-world routes;
- semantic batching that replaces diagnostic draw-by-draw replay where safe.

Exit gate: the normal gameplay matrix has camera-correct native coverage with
family-local fallback and no material visual omissions.

### V3-06 — Lighting, shadows, reflections, and presentation

- complete shadow ownership, cascades, filtering, and dynamic casters;
- local, global, vehicle, and environment lighting;
- planar, cubemap, vehicle, and road reflections;
- exposure, tonemapping, anti-aliasing, bloom, depth of field, motion blur,
  color grading, and final presentation;
- native UI composition boundaries where required.

Exit gate: paired captures pass the agreed visual comparison thresholds across
day, night, weather, tunnel, race, and festival scenes.

### V3-07 — Frontend and special modes

- boot, loading, menus, garage, paint, upgrade, photo mode, replay, and FMV;
- livery and user-generated texture paths;
- resize, fullscreen, focus, suspend, resume, and device-recovery behavior;
- frontend-specific render targets, queries, resolves, and synchronization.

Exit gate: the complete scene matrix works without relying on unclassified
Xenos presentation behavior.

### V3-08 — Production hybrid and low-requirement profiles

- close the renderer census by family rather than by isolated draw;
- enable measured, independently reversible Xenos suppression;
- harden streaming, resource budgets, deferred GPU lifetime, and recovery;
- add independent scene resolution, geometry, world-density, shadow,
  reflection, material, and effect controls;
- qualify representative low-end CPU and GPU configurations;
- verify that each profile materially reduces cost rather than only changing
  launcher state.

Exit gate: native mode is the qualified default, materially reduces Xenos
work, and has stable rollback at family granularity.

### V3-09 — Xenos retirement

- enumerate and close every remaining Xenos dependency;
- preserve required guest side effects without executing Xenos visual work;
- produce and qualify a no-Xenos build;
- run the full gameplay, frontend, visual, performance, soak, and recovery
  matrix;
- document release rollback and retained diagnostic builds.

Exit gate: the native-only release candidate passes the full matrix and Xenos
is no longer required for supported execution.

## Work that is explicitly deferred

Until Milestone 1 passes, do not prioritize:

- scaled or supersampled accumulator presentation;
- 2x draw-scale qualification;
- full shadows, reflections, transparency, or post-processing;
- traffic, crowds, vegetation quality, or special modes;
- broad census expansion without a named compositor blocker;
- pass suppression or Xenos retirement;
- low-requirement profile UI; or
- visual polish on isolated targets that cannot contribute to a complete
  scene frame.

Deferred means later, not removed from the final scope.

## Development and validation cadence

### Every commit

- Run only affected focused tests.
- Keep commits independently reviewable and use Conventional Commits.
- Record new evidence only when it changes an implementation decision.

### Every pull request

- Prefer one vertical capability over one observer, counter, or field.
- Include supporting instrumentation in the capability PR.
- Run the relevant automated suite and an incremental Release build.
- Confirm Xenos fallback and guest-memory invariants synthetically when
  possible.

### End of a V3 batch

- Rebase or merge the latest `dev` before final qualification.
- Run clean ReXGlue preparation and the full automated suite once.
- Run a clean Release build once.
- Perform one AppData-backed run only when the batch has a runtime exit gate.
- Review logs, crash artifacts, GPU messages, and bounded resource counters.
- Merge only after the batch exit gate is satisfied.

### Visual milestones

- Use the same save, reference route, resolution, draw scale, and camera points.
- Capture paired Xenos and native/hybrid frames.
- Retain frame-time summaries and fallback counts.
- Do not repeat a full qualification run for documentation-only changes.

## Decision rules

- No evidence-only PR unless it resolves a binary blocker for the active batch.
- Stop tracing once the minimum safe implementation boundary is known.
- If one targeted runtime capture disproves an architectural hypothesis, record
  it and leave that path rather than adding increasingly broad observers.
- Never publish a last-writer or best-effort partial scene.
- Never mix targets from different frames, cameras, projections, or unresolved
  attachment lifetimes.
- Optimize the coherent 1x prototype before revisiting scaling.
- Measure performance with discovery and capture features disabled.
- Treat fallback frequency as a product metric, not just a debug counter.
- Keep renderer selection, native publication, and Xenos suppression as
  separate gates.
- Unknown or failed work always yields to Xenos until V3-09 is complete.

## Pull-request sizing

The preferred unit is a vertical capability with tests and the minimum
instrumentation required to prove it. A batch may use more than one PR when
risk or reviewability requires it, but avoid splitting a single capability
into a sequence of topology, counter, request, and result PRs.

For the prototype, the expected shape is three to five substantial PRs:

1. compositor contract and retained scene-frame state;
2. opaque world and static-world producers;
3. background and player-vehicle producers;
4. hybrid publication and fallback; and
5. an optional focused performance/hardening PR if V3-04 cannot contain it.

## Status reporting

Keep this section short. Update it only when a V3 batch changes state.

| Batch | State | Visible result | Primary blocker |
| --- | --- | --- | --- |
| V3-01 | next | none; architectural foundation | multi-target scene retention |
| V3-02 | blocked by V3-01 | private opaque open world | producer-to-slot binding |
| V3-03 | blocked by V3-01/02 | complete private gameplay scene | vehicle/background ownership |
| V3-04 | blocked by V3-01/02/03 | drivable hybrid prototype | complete-frame publication |
| V3-05 | pending | broad gameplay coverage | prototype exit gate |
| V3-06 | pending | complete lighting and presentation | gameplay-scene breadth |
| V3-07 | pending | frontend and special modes | presentation coverage |
| V3-08 | pending | production hybrid and profiles | complete native coverage |
| V3-09 | pending | native-only release candidate | all Xenos dependencies |

The next implementation action is V3-01: introduce camera-consistent,
multi-target scene-family retention and an explicit complete-frame coverage
gate while keeping Xenos authoritative.
