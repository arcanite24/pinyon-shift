# Scene-native renderer backlog

Status: in progress. The frame-wide boundary and complete selected-draw
diagnostic are proved for sampled race frames, including adjacent moving
frames. The file-backed path fails the visual bar and is no-go as a speed
candidate; no net renderer performance gain is claimed. Material coverage,
other-family lifetimes and retained-pass bridges remain open.
**Delivery priority changed on 2026-09-24:** get an opt-in live native frame,
then a usable race renderer. Performance and the approximately 90% visual
target are later optimization/qualification goals, not blockers to those
first two milestones. See the [Skate 3 development sequence](SKATE3_NATIVE_RENDERER_MILESTONES_2026-09-24.md).
An opt-in in-process six-family handoff now preserves the exact diagnostic
target on two adjacent checked frames, but still serializes fixture bytes and
uses stage waits and readback. It is a correctness step, not the production
feasibility measurement; see the [in-process evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#in-process-exact-frame-diagnostic-handoff--2026-09-24).
The diagnostic now shares one queue. Paired capture-only and worker route
measurements reject reuse of the SNR-01/full-fixture probe pipeline for
production: capture-only drops the matched 30-second interval from roughly
1,200 to 715 consumed swaps. This is a path-level no-go, not a decision on
the native architecture; see the [cost decision](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#shared-queue-and-legacy-capture-cost-decision--2026-09-24).
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
The selected foliage keys join through the title manager table to five
distinct manager objects, returned records and byte-matched live BC3 chains;
host-cache allocation and completed-load generations are now sampled. The
selected title chain/base resources now have a same-process title-return
unload and second-race rebind: all ten original allocations were destroyed,
their five keys resolved to new title generations, and five fenced BC3
payloads matched the independent reference with advanced load generations.
The checked race-retire route alone did not unload them; the title return did.
The two provider references are identified by live vtables and title RTTI as
`CBixTextureChainResource` and `CBixTextureBaseResource`; their allocation
generation must be checked separately from host-cache payload generation.
The [shared-track geometry handoff](SCENE_NATIVE_SNR02_TRACK_GEOMETRY_2026-09-23.md)
owns the selected track vertex/index bytes and final bound draw state at the
exact output frame. An 813-draw replay passed the full 4,438-draw partition;
mesh/material ownership and native raster coverage remain open. A bounded
post-refill clear join also attributes two late noncandidate direct-root
draws found in an earlier replay. All 20 exact track vertex translations are
extracted from the validated installed pack. Host triangle-strip topology,
restart and guest index endianness are proved; vertex-fetch interpretation
and a private track diagnostic raster remain open.
The [SNR-04 procedural diagnostic](SCENE_NATIVE_SNR04_PROCEDURAL_EVIDENCE_2026-09-23.md)
replays every owned procedural draw through a private full-resolution
identity/depth target at the output-frame handoff. It also checks original
post-VS output and the actual bound vertex-constant bytes. A direct
backend-frame RenderDoc capture now joins all 189 vegetation actions to the
owned fixture with exact draw sequence, vertex bytes, bound constants and
system words; pixel-aligned post-VS comparison remains open. This is
geometry/ABI evidence, not material parity or full-slice coverage. The
[SNR-03 evidence log](SCENE_NATIVE_SNR03_EVIDENCE_2026-09-22.md) records
bounded same-frame vegetation metadata, guarded vertex bytes and a private
same-frame identity/depth diagnostic; full-slice coverage remains open.
The [shared-track private diagnostic](SCENE_NATIVE_SNR04_TRACK_EVIDENCE_2026-09-23.md)
renders all owned track draws from a paired source-frame-5000 fixture with
verified shader/index inputs. A second capture passed the strict frame-wide
candidate census and final per-draw viewport, cull and depth-state joins.
Rebasing its three EDRAM tiles produces 700,053 private identity/depth pixels,
but stencil, material visibility and full selected-slice parity remain open.
The [combined Gate A capture](SCENE_NATIVE_GATE_A_COMBINED_CAPTURE_2026-09-23.md)
first joined track, procedural-item and vegetation fixtures to one
source/output frame, covering 1,229 of 1,670 required draws. It also corrected
the procedural-character/vegetation partition and isolated their snapshot
budgets. A later same-frame replay owns all 2,192 selected draws in six
verified fixtures. The [complete selected-slice diagnostic](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md)
now replays those draws in global sequence through logically carried private
color/depth state. An adjacent moving-view sample independently owns 2,442
selected draws and replays them through 36 stages. A further same-run
RenderDoc/fixture capture compares all 1,562 selected draws with sample-0
compatibility depth at the final draw of each EDRAM band; its 99.46% nonzero
depth-mask overlap is a coordinate diagnostic, not parity. Material,
other-family resource-lifetime and pixel-aligned moving-frame parity checks
remain open. A later **one-run adjacent** capture owns all 1,926 and 1,992
selected draws from source frames 5000 and 5001, respectively, with both
single-target 4× replays matching staged controls. Its same-run presented
side-by-side review records recognizable moving geometry but fails the
visual bar on materials, foliage alpha and shadows; it is not target-space
color parity or continuous in-game native rendering.
The carried 4× diagnostic now counts every sample: 144 of 1,562 selected
draws are visible in one capture, including four missed by sample-0-only
accounting; a second 2,307-draw capture has eight such edge-only IDs.
Both final 4× targets contain visible samples from all eight selected
family labels, with per-family counts checked against the full sample mask.
The [procedural-character handoff](SCENE_NATIVE_SNR03_CHARACTER_2026-09-23.md)
adds an exact same-frame fixture for that separate family. Its new strict
replay owns 1,069 of 2,662 selected draws across four fixture families; the
character fixture now renders 37,613 deterministic identity/depth pixels
from ten draws. The larger car/character-manager families remain unowned.
The [character-manager snapshot preflight](SCENE_NATIVE_SNR03_MANAGER_SNAPSHOT_2026-09-23.md)
checks both vertex streams and 16-bit indices for every one of 342 selected
draws in a later strict replay. Repeated ranges stayed byte-hash stable; an
owned `SNR03M1` fixture now joins all 102 selected manager draws in another
strict replay. Its private two-stream identity/depth raster produces 33,307
deterministic pixels. Five owned geometry fixtures cover 1,272 of 1,596
selected draws in that replay; they remain separate private targets.
The [remaining-family snapshot preflight](SCENE_NATIVE_SNR03_REMAINDER_SNAPSHOT_2026-09-23.md)
checks every selected car scene-list, animated-scene and car-presentation
vertex and guest-index range in a later strict replay: 883 draws, including
108 whose guest indices are converted by the SDK. This is byte availability
evidence. Later strict replays join every selected draw in those families to
immutable title records, including 814 car, 12 animated and 54 presentation
draws in one frame. An `SNR03R1` fixture now owns all 1,149 selected draws
from these three families in a later strict replay, including final bound
fetch state. A subsequent `SNR03R2` replay captured host index endian and
restart state; its 108 converted draws follow the SDK's mask-and-restart path
with shader-side swapping. The [remaining-family private diagnostic](SCENE_NATIVE_SNR04_REMAINDER_EVIDENCE_2026-09-23.md)
renders all 880 of its selected draws on a private identity/depth target.
The combined staged diagnostic carries color/depth across all six families.
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
That complete-slice rule applies to the later supported renderer, not the
first opt-in live-output pilot. The pilot may render a bounded subset if its
missing content is explicit and compatibility can be restored immediately.

For the race pilot, the **Gate A diagnostic slice is explicitly revised** to
the title-linked scene-list, character-manager, procedural-character,
procedural-item, vegetation,
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
  compromises cannot qualify as current-resource performance. [Scene state][skate-state]
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

## Delivery milestones

The [Skate 3 history](SKATE3_NATIVE_RENDERER_MILESTONES_2026-09-24.md)
shows a rough live world renderer before texture/character coverage, parity
work, performance overhaul or native-by-default release. Follow that order
for FH1 while preserving exact-frame ownership and whole-frame fallback.
The existing SNR tickets below remain the technical ledger; parts of SNR-08
and SNR-09 move forward for the first live output.

| Milestone | Required result | Explicitly deferred |
| --- | --- | --- |
| L0 — Owned scene diagnostic (current evidence) | Strict selected-draw census, immutable same-frame geometry and one private GPU target on sampled race frames | Presented native output, materials and continuous gameplay |
| L1 — First live native frame | In-memory current-frame scene on the existing D3D12 queue; an opt-in early output callback presents native race geometry with a visible native/compatibility toggle and whole-frame fallback | Complete scene, HUD, accurate materials, FPS gain |
| L2 — Usable race renderer | Continuous sustained-race gameplay with road, vehicles, vegetation, basic colors/textures and alpha, stable motion, and readable HUD/gameplay cues; unsupported modes yield entirely to compatibility | 90% visual score, 15% speedup, all modes and exact material ports |
| L3 — Efficient replacement | Proved retained-pass bridges and safe early suppression remove replaced compatibility work; measure net frame cost and fix the critical path | Default-native release or pixel-perfect parity |
| L4 — Qualify and expand | Optimize and compare against the declared performance/visual targets, extend modes as needed, then consider native-by-default | Complete Xenos retirement without the separate migration checklist |

**L1/L2 safety floor:** the current output frame must use current scene and
resource data; invalid scene/resource or output failure selects a complete
compatibility frame. Keep original UI/cues readable at L2 and do not change
game speed or hide repeated/dropped frames. An L1 flat-shaded image is a
development milestone, not a claim that the game is usable. A rough but
playable L2 image is allowed; document unsupported content and visible
shortcomings. Do not promote a diagnostic screenshot or double rendering to
a speed result.

The later optimization target remains **at least 15% lower median frame time**
at equal output settings, also exceeding twice the observed control-to-control
median variation. Predeclare the comparison and tail-noise envelope in SNR-00;
p95/p99 must not regress beyond that envelope. This is a go/no-go target, not a
forecast or a prerequisite for L1/L2. The later visual target is approximately
**90% acceptable fidelity** in predeclared representative scene regions and
motion, judged side by side with the compatibility renderer. Bit-identical
pixels, depth, sample masks and
shader arithmetic are not required. Record visible differences, including
minor approximations or omissions, and accept them when they do not materially
impair the scene or gameplay. Every selected submission must still be
accounted for; current poses/resources for rendered content, readable original
UI, correct game speed and no concealed repeated/dropped frames remain
mandatory. An average score cannot hide a missing road, vehicle or other
major feature. If visual quality passes but the speed target fails, retain
the work as an experimental renderer only and use the new profile to decide
whether another bounded change is justified.

## Work order

Ticket checkboxes remain open until their full acceptance checks pass. L1 and
L2 deliberately use bounded parts of later tickets; the full SNR-00–12 list
is no longer a serial prerequisite chain for the first usable renderer.
Effort is relative scope, not a time estimate.

| ID | Task | Prerequisites | Effort / owner area |
| --- | --- | --- | --- |
| SNR-00 | Freeze slice, controls and success criteria | None | Small / tooling + renderer |
| SNR-01 | Recover live view and submission ownership | SNR-00 | Large / title reverse engineering |
| SNR-02 | Recover materials, resources and dynamic identities | Basic current inputs for L1; expand for L2 | Large / title + resources |
| SNR-03 | Publish an immutable FH1 frame scene | In-memory current-frame subset for L1 | Medium / title + renderer |
| SNR-04 | Render authoritative full-resolution diagnostics | Existing GPU diagnostic feeds L1 | Medium / D3D12 |
| SNR-05 | Prove the pass/dependency cut and bridges | Minimal HUD/retained-pass bridge for L2; full cut for L3 | Large / title + SDK |
| SNR-06 | Establish native shader ABI and material coverage | Basic color/alpha for L2; broad coverage later | Large / shaders |
| SNR-07 | Render the supported native slice | L1 geometry; L2 recognizable scene | Large / D3D12 |
| SNR-08 | Implement native output and retained-pass composition | **Early takeover for L1**; retained composition for L2 | Medium / SDK output |
| SNR-09 | Establish per-frame admission and recovery | **Whole-frame fallback for L1**; full recovery before L3 | Medium / title + SDK |
| SNR-10 | Suppress replaced compatibility work early | L2 usable output and complete SNR-05 cut; L3 | Medium / SDK commands |
| SNR-11 | Qualify images, streaming and net performance | L3 replacement; L4 | Large / validation |
| SNR-12 | Remove a proven upstream preparation path | New post-L3 critical-path evidence | Large / title |

### Active delivery path — L1, then L2

**Output-seam checkpoint (2026-09-24):** the D3D12 refresh now asks an
opt-in native callback before compatibility gamma/FXAA and retains the final
render-test observation after either choice. Returning false leaves the
compatibility frame intact. A render-test-only clear probe claimed the output
at 1280×720: adjacent captured frames had uniform RGB (32, 96, 64) and
(32, 96, 191), while the same-route probe-off capture contained the game
image. All three runs exited normally with the AppData save. This validates
selection, exact-frame advancement and basic fallback; it does **not** close
L1, because the callback does not yet consume or render the owned race scene.
Repeat with `fh1-native-output-adjacent.fh1test` once without and once with
`--pinyon_shift_native_output_clear_probe=true`, then run
`tools/verify-native-output-seam.py <control-dir> <probe-dir>`.

**Early scene-boundary checkpoint (2026-09-24):** SNR-02/03 owned-frame
consumption now runs before native output admission; final image observation
still runs after presentation. The adjacent AppData race replay exited normally
and the output-seam check still passed. With the live handoff enabled and its
worker disabled, source frames 5000/5001 reached the early boundary with
track, procedural items, vegetation, manager and remainder payloads. The
character payload was incomplete on both frames (0 and 1 captured draws for
13 and 14 character records), and six-family admission correctly rejected
them. This is evidence that a fixed source-frame number cannot be an L1
admission rule. The first visual pilot may omit the character family, as in
Skate's first live frame, but must declare its required subset and yield a
whole compatibility frame whenever that subset is incomplete.

**Core-scene handoff checkpoint (2026-09-24):** the early callback can now
borrow an immutable exact-source-frame snapshot with owned track bytes,
typed procedural items and typed vegetation, plus optional character,
manager and remainder payloads. Admission checks source-frame tags and
unique nonzero draw sequences across the required core. A render-test-only
scene-gated clear probe returns to compatibility when that core is missing.
An exact-output-frame replay (the usual `# clock-hz 60` line was removed)
admitted source frames 5000/5001 with 1,168/1,181 core draws and exited
normally. The first PPM was the preceding compatibility image; the next two
were distinct scene-coded RGB (73, 96, 64) and (74, 96, 191). The presenter's
readback is one output behind the admission callback, so three captures
are needed to observe two adjacent claimed frames. Reproduce with
`fh1-native-scene-exact.fh1test`, the opt-in live-handoff and scene-clear
probe flags, and `tools/verify-native-scene-handoff.py <output-dir>`.
An otherwise identical short run with the scene-clear probe but no live
scene handoff exited normally and retained nonuniform compatibility images.
This proves direct current-frame ownership and output selection, **not**
geometry presentation or continuous L1 gameplay. Track, manager and
remainder still pass in-memory fixture bytes, and collection remains limited
to selected source frames.

**Live graphics-command checkpoint (2026-09-24):** the D3D12 callback now
exposes its frame-scoped deferred list, output state and completed submission;
the guest-output resource accepts an RTV. A scene-gated diagnostic records a
clear and a rasterized triangle into that same presentation submission, then
restores the output state. It retains the per-frame RTV descriptor until its
submission completes. The exact-output race route exited normally and its
two admitted captures each contained precisely the sky color plus a distinct
triangle color (222,106 triangle pixels); the preceding capture remained the
game image. The compatibility and earlier clear-probe routes still passed,
and an absent-scene triangle run yielded complete compatibility images.
`tools/verify-native-scene-handoff.py <output-dir> --triangle` checks the
scene-gated graphics captures. This proves a real native graphics draw can
reach the presented image; the triangle is generated diagnostic geometry,
not FH1 mesh content. L1 still needs the owned road/terrain and other scene
draws, continuous frame capture, and a player toggle.

**Continuous capture checkpoint (2026-09-24):** an opt-in, worker-free live
collector and the SDK's prepared-draw snapshot gate now follow the same
source-frame range. The `fh1-native-scene-continuous.fh1test` AppData race
route exited normally; `verify-native-scene-handoff.py <output-dir>
--triangle --continuous` confirmed twenty consecutive scene-gated graphics
frames (sources 5000–5019). An earlier run fell back at source 5010 while
the compatibility image still showed the road. Its track inventory stopped
at zero targets because a scene-command counter hit its 8,192 cap without
resetting per source frame. Resetting that counter restored track ownership;
the later run admitted every source through 5030. The generated triangle
still proves only output submission, not FH1 geometry. This capture mode
emits extensive diagnostic logs and is not yet a performance-qualified
player mode.

**Live track-raster checkpoint (2026-09-24):** the early callback can now
look up validated vertex bytecode from the installed FH1 shader pack, parse
the same owned track fixture used by the private diagnostic, and record its
indexed draws directly on the presentation submission. It builds an owned
upload buffer and depth target before claiming the frame, uses captured
viewport/scissor/depth state, and retains GPU resources until submission
completion. The refactored private diagnostic still covered 700,053 pixels.
The AppData race route exited normally; `tools/verify-native-track-output.py
<race-output> <missing-scene-output>` confirmed twenty consecutive changing
track-geometry frames plus complete compatibility output when no scene was
available. The material color is currently a flat hash-derived placeholder.
Visual review shows partial buildings and trackside structures, with road,
vehicles, foliage and HUD absent. This is the first in-game FH1 mesh draw,
not a usable L1 native race view. It still depends on expensive diagnostic
capture hooks and remains render-test-only and default-off.
Repeat with `fh1-native-scene-continuous.fh1test` and the live handoff,
continuous, worker-off, SNR-02 item/track, SNR-03 frame-5000 and
`--pinyon_shift_native_track_probe=true` flags. The short
`fh1-native-output-adjacent.fh1test` route with only the track flag checks
no-scene compatibility fallback.

**Live item-geometry checkpoint (2026-09-24):** the same native submission
now also draws the owned SNR-02 procedural items against the track depth
target, using their validated vertex shaders and shared upload arena. The
AppData continuous route exited normally and the twenty-frame moving-output
check passed; a matching source-frame capture changed 226,638 RGB bytes
compared with the track-only checkpoint. This remains a partial, flat-color
scene. A first vegetation attempt caused `DEVICE_HUNG`: it accidentally
selected the manager vertex shader `B8489164D5A86043` for foliage vertex
data. The installed pack confirms that foliage uses `5834939992FFC765`,
matching the private diagnostic's shader digest. Correcting that binding
restored normal short and continuous route exits, visibly added foliage
geometry, and passed the twenty-frame moving-output check. The current flat
opaque foliage still needs captured alpha and material state.

**Upright car-scene checkpoint (2026-09-24):** the existing strict SNR-03
remainder parser now returns owned host vertex/index streams for the live
callback. Its private diagnostic still reports 880 draws and 136,308 covered
pixels, with the same summary as before extraction. The live callback draws
that family in the same depth target, including both index widths and strip
restart. It then rotates the private scene target 180° into the presented
output, matching the compatibility resolve's known orientation. Visual
review shows an upright trackside scene and moving player-car silhouette.
The AppData continuous route exited normally; the strengthened
`verify-native-track-output.py` passed twenty changing native frames with
sky in the top half and car pixels in the bottom half. The checker rejects
the prior inverted capture. A missing-scene route still exited normally and
presented complete compatibility frames. These are flat-color geometry
frames without materials, alpha, original HUD or a player toggle, so L1/L2
remain open.

1. Add the narrow D3D12 output-takeover seam first. The current FH1 output
   callback is an observer after compatibility output processing; it cannot
   replace the presented image. Let an opt-in native callback draw to the
   presented output and signal success before compatibility gamma/FXAA,
   while retaining the final render-test observer after either path. Keep
   compatibility rendering available and do not suppress its draws yet.
2. Feed that callback a bounded immutable scene directly from the current
   title/output frame. Reuse the six-family ordered GPU diagnostic and
   existing device/queue; eliminate fixture files, external manifest polling,
   inter-family readback and worker waits from the live path. Use owned
   current-frame bytes where a persistent generation is not proved.
3. Deliver an opt-in **live native frame** and a manual native/compatibility
   toggle. Prove continuous moving-frame presentation, no stale frame, safe
   fallback on missing scene/resource/resize, normal route exit and unchanged
   save/gameplay. Flat colors and missing HUD are acceptable only for L1;
   label the mode experimental and keep compatibility as the default.
4. Make the sustained race **usable**: add basic road/terrain, car and foliage
   color/texture/alpha, sky or an intentional approximation, stable dynamic
   transforms, and readable original HUD/gameplay cues via a proved retained
   bridge or a native equivalent. Unsupported menus, photo/mirror/video and
   other modes select a complete compatibility frame. Validate several
   minutes of driving, transitions and a title reload without stale content.

L1 is complete when the player can toggle to a continuously presented native
race view and back without a crash or stale frame. L2 is complete when the
player can drive the selected race using native scene output and readable
gameplay cues, with documented visual gaps and clean fallback for unsupported
modes. **Neither milestone requires a 15% gain or 90% visual score.**
Those are L4 qualification targets. Preserve exact-frame ownership, resource
freshness and safe fallback throughout.

### Prior Gate A preflight (retained as evidence)

The following census and stop/go notes explain why the file-backed identity
diagnostic is not a production renderer. They no longer block L1's live-output
pilot or L2's basic material work. Do not restart broad reverse engineering
before the first in-game native frame.

Earlier work treated **Gate A (SNR-00–04)** as the active execution phase.
That ordering is superseded by L1/L2 above. A process-bounded replay
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
   The selected foliage BC3 probe now joins five live cache objects and
   clean-at-copy payloads to independently captured mip chains. One key had
   three CPU-triggered invalidations/reload attempts before the sample;
   a second run confirmed two invalidation → attempt → completed-load chains
   on the same sampled cache object before its fenced copy;
   an owner-local vegetation key now joins all 60 selected title records in
   one run to five distinct BC3 ranges and fenced payloads, while the shared
   global state entry is ruled out as the per-texture key;
   a further run joins five keys to five distinct resolved title objects
   and all 65 selected records to five BC3 payloads;
   distinct host-cache allocation and completed-load generations now label
   the five sampled BC3 sources. A same-process title return now proves the
   ten selected title allocations are destroyed, all five keys rebind to new
   chain/base generations, and current fenced BC3 payload generations advance
   (see the [reload evidence](SCENE_NATIVE_SNR02_EVIDENCE_2026-09-22.md#same-process-title-return-proves-selected-foliage-unload-and-rebind)).
   Other selected material families still need ownership and lifetime rules.
   Six scalar draws have a retained skid-presentation
   path. Resolve scene membership and resource ownership before freezing
   the slice.
2. **Finish the Gate A diagnostic (SNR-02–04):** the staged offline replay now
   owns the selected draw order and private depth. The sampled foliage
   allocation/payload generations now pass an unload/rebind replay. The
   one-run complete-slice source-frame-5000/5001 capture is recorded in the
   [SNR-04 evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#one-run-adjacent-source-frames--2026-09-24):
   both strict ledgers and six-family joins pass, but identity shading fails
   the predeclared visual regions. Next obtain target-space color/alpha/stencil
   comparison in these adjacent frames with material-aware shading and
   retained-pass composition; presented screenshots do not establish
   final-output parity. A two-output-frame RenderDoc capture now exports the
   six final compatibility scene-target bands across those adjacent frames.
   Both strict censuses and six-family fixture joins pass, and sample-0
   target-space depth coverage overlaps by 99.78% in each frame; see the
   [target-space evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#adjacent-compatibility-scene-target-capture--2026-09-24).
   The approximately 90% visual bar remains failed for identity shading,
   and material-aware color/alpha/stencil parity remains unmeasured.
   Investigate an isolated sample/byte mismatch only when it suggests a
   general rendering error or visible defect. Draw identity and freshness
   must remain exact even when image appearance is approximate.
3. **Test the real execution shape:** render the owned diagnostic into an
   in-game private target on the existing D3D12 device, without per-family
   CPU readback/upload. A one-target offline batch now matches both verified
   staged 4× targets byte for byte, and an asynchronous archived-fixture batch
   completed on the borrowed in-game device with normal game exit. A later
   fresh capture joined all 2,367 selected draws in six fixtures and its
   offline one-target replay matched its staged control exactly; see the
   [complete-slice evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#fresh-six-family-source-frame-5000-admission--2026-09-24).
   A subsequent 1,796-draw current-run batch also completed on the borrowed
   game device, matched a same-fixture staged control byte for byte and let
   the game exit normally; see the
   [live private-target evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#current-run-private-target-on-the-game-device--2026-09-24).
   The next current-run measurement separates selected-frame capture, CPU
   upload calls, GPU timestamped draw loops, stage wall time and zero
   inter-family CPU target bridges; see the
   [cost evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#separated-current-run-diagnostic-costs--2026-09-24).
   Batch-local immutable upload reuse now cuts the same-fixture diagnostic
   from 185.322 MB to 28.710 MB of actual uploads and from 23.527 s to
   4.720 s stage wall, with identical final coverage/identity/depth. A fresh
   2,005-draw borrowed-device run and independent staged control also match;
   see the [cache evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#batch-local-immutable-upload-reuse--2026-09-24).
   **No-go for the present file-backed diagnostic as a speed candidate:** its
   22.2 ms debug capture alone exceeds the illustrative 15% frame-time
   saving; external fixture handoff adds latency even after batch-local
   reuse. This does not measure a production
   native replacement. Keep compatibility authoritative. This rejects the
   diagnostic capture path, but no longer defers basic L2 material work until
   a paired net benchmark.

### Current direct-scene handoff (supports L1)

The previous Gate A continuation proved one-run adjacent ownership,
selected foliage unload/rebind and current-run private-target execution. Its
stop/go result rejects the **file-backed diagnostic**, not native rendering
itself. Items 1–3 below support the live-output pilot; the cost qualification
in item 4 belongs after usable gameplay:

1. Hand the checked current-frame immutable scene directly to the in-game
   worker. Remove fixture-file encoding, external manifest polling and debug
   readback from this path; keep them as opt-in verification tools. Preserve
   exact source/output-frame joins and bounded queues.
2. Reuse GPU geometry, shaders and PSOs across frames only where identity and
   allocation/payload generations are proved; retire them after fences.
   Upload owned current-frame bytes for unresolved dynamic inputs and measure
   those misses. Validate a reload/rebind; never cache by guest address alone
   or reuse stale data. Reuse the existing D3D12 device and batch code,
   without a new scene framework.
3. Submit the selected draw order to one private target without a queue wait
   per family. Capture two adjacent moving frames in one run; verify their
   draw census and compare the opt-in target with the existing offline
   diagnostic. Keep compatibility output authoritative.
4. **After L2**, run matched control/probe-off/probe-on measurements at
   production settings,
   separately reporting capture CPU, uploads, native GPU work, retained work,
   memory, frame cadence and any critical-path stall. Estimate removable
   compatibility work only from the SNR-05 dependency cut, never from draw
   counts or overlapping CPU/GPU spans. State a go/no-go for a **15% net median
   frame-time gain** with the roughly 90% visual bar. This diagnostic cannot
   claim net speedup while compatibility draws still run.

**Later decision:** if a usable L2 renderer misses the speed target, revise
the slice or identify a proven upstream preparation saving during L3/L4.
Do not withhold basic material/alpha and HUD work merely because the current
identity diagnostic is slow or visually rough.

**Current implementation cut:** stop treating the SNR-04 fixture encoder and
SNR-01 census as a candidate frame path. Publish the six already owned typed
family payloads and their exact sequence order directly to a bounded worker;
keep fixture generation only for sampled verification. The worker must build
and retain its own native render inputs once per frame, with proven resource
identity/generations, rather than reparsing each family fixture for every
contiguous run. Keep the shared-queue diagnostic as an output oracle while
implementing this cut. Re-run the paired production-settings benchmark only
after the direct path can sustain adjacent moving frames without debug
readback or per-family waits. This is the next action, not a completed gate.

A selective-frame check without the SNR-01 trace target still measured a
29.490 ms median against 21.829/22.119 ms controls; it captured both adjacent
frames but retained SNR-02/03 probes and in-memory fixture encoding. See the
[SNR-04 cost evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#shared-queue-and-legacy-capture-cost-decision--2026-09-24).

The SDK draw-order counter has now been decoupled from the broad GPU corpus
for live handoff. A corpus-off run reduced the probe median to 26.044 ms,
but fixed source frames 5000/5001 did not both meet six-family admission.
The direct producer must account for scene-dependent missing families and
publish only complete frames; this sensitivity run does not close SNR-04.

The vegetation family now uses a direct immutable-scene queue entry in the
ordinary live path. A same-run verification dump replayed both adjacent
frames through the fixture oracle and matched all final coverage, depth and
4× identity bytes; see the [typed-family evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#first-typed-family-handoff--2026-09-24).
The current diagnostic worker still reparses the other four families and
waits after each segment. Convert them before repeating the later cost gate;
this is not a prerequisite to L1's bounded live-output pilot.

The procedural-item family now also uses a typed live handoff and matched
same-run fixture replay on both adjacent frames; see the
[typed-item evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md#typed-procedural-item-handoff--2026-09-24).

The prior Gate A quality/cost stop-go is superseded for L1/L2. Unknown scene
identity, stale resources and unsafe fallback still reject a native frame;
visual roughness or poor speed does not block the opt-in pilot. Apply the
15% net-speed and approximate 90% visual targets at L4, after L2 is usable
and L3 removes paired compatibility work.

### [ ] SNR-00 — Freeze the experiment

- Record executable/DLL hashes, root/SDK revisions and local patches, shader-pack
  identity, resolution/scale, presentation settings, hardware/driver and route.
  Reuse `config/render-tests/fh1-race-sustained.fh1test` and the repaired saved race
  as the initial 1x pilot; identify exact starting state and source-frame windows.
- Freeze selected view/pass coverage and a reference image set: road/terrain,
  foliage alpha edges, vehicle paint/glass boundaries, shadows, HUD and motion.
  Record unsupported views/modes and their expected whole-frame compatibility
  behavior. Existing UI, mirrors and reflections cannot silently disappear.
- Before viewing native results, mark critical regions and a representative
  set of scene/motion review regions from the existing references. Gate B aims
  for roughly 90% of those regions to be acceptable side by side; document
  every failed region and require all critical content and gameplay cues to
  remain usable. Use pixel/depth metrics to locate defects, not as an
  automatic byte-match threshold.
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
- Compare the complete selected slice against the same-frame compatibility
  target in at least two adjacent moving frames. Classify visible differences
  by missing content, pose, alpha/material, stencil, lighting and retained-pass
  composition; an isolated sample or float-bit mismatch is a diagnostic, not
  an automatic gate failure under the agreed visual bar.
- Keep the selected order on one in-game private D3D12 target, then replace
  the current file-backed handoff and per-stage submissions with in-memory
  publication, persistent resources and bounded GPU work. The staged replay
  and borrowed-device worker remain verification tools, not frame-time
  evidence. Record extraction, update, draw, bridge and presentation costs
  separately; double rendering is not a net FPS result.

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
The complete same-frame fixture set now replays 2,192/2,192 selected draws
in 35 ordered stages with carried private color/depth. It covers 659,995
pixels and is byte-repeatable; see the [complete-slice evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md).
A second same-run RenderDoc capture owns 1,562/1,562 selected draws and
compares the private target to sample-0 compatibility depth at the final
draw of each of three EDRAM bands. The 99.46% nonzero-depth mask overlap
supports the coordinate mapping, while the p90 absolute depth difference
of `0.00489` leaves substantial unexplained depth error. Reproduce at 4×
with matched alpha, stencil and per-draw event state before claiming parity.
Attribution to each tile's private draw IDs puts 69,490/85,908 depth
differences of at least `0.005` on vegetation; 99.0% write nearer private
depth. The five leading foliage draws all bind two pixel textures. The
same-run capture matches all 179 foliage actions and exports their five BC3
mip chains. This motivated the captured alpha/sample-mask diagnostic below;
the ordinary private identity shader still ignores it.
The vegetation diagnostic now restores four-sample identity/depth from a
prior private segment. A 45/67/67 split matches an uninterrupted 179-draw
four-sample replay byte for byte. All selected families now carry this
four-sample target across the 35-stage same-run slice; two complete replays
match byte for byte at every stage. Sample-0 compatibility mask overlap is
99.50%, but p90 absolute depth error is still `0.00488`. Vegetation still
accounts for 70,082/85,659 large depth errors. The same-frame alpha census
below tests one part of this gap; stencil and per-draw state remain. An
exact-prior single-draw check for matched event 11204 explains the immediate
next step: 133,449/133,488 compatibility depth writes also occur in the
private draw, but the unmasked private draw adds 222,835 samples. An opt-in
event-11204 probe matches each compatibility per-sample
write count within 0.8% using the verified BC3 mip chain, but the original
fixture's spatial pixel overlap is only 73.67%. Its vertex bytes and 64
system words match RenderDoc; 35/92 bound vertex constant words do not. Replacing
only those constants in a guarded local diagnostic fixture produces exact
pixel/sample coverage and depth for all 133,488 writes of this draw. A
179-action census finds exact fetched vertex bytes throughout the foliage
slice, the same 35 bound constant slots differing on every draw, and one system
word differing on the 67 middle-band draws. The captured constants also
vary by tile draw within an item. `SNR03F4` now retains the 92 actually
bound words per final draw; a real output-frame fixture passed log/hash
verification for 135 draws, and a synthetic same-capture F4 fixture has
zero bound-constant differences across 179 draws. The live F4 frame also
passed the six-family verifier for all 2,307 selected draws; two complete
4× replays matched at all 35 stages. The direct backend-frame capture below
resolves the frame mismatch. Test the original pixel shader, stencil
and resource lifetime before broadening native admission; see
the [complete-slice evidence](SCENE_NATIVE_SNR04_COMPLETE_SLICE_2026-09-23.md).
Semantic material admission, resource freshness and continuous
moving-frame/unload checks remain open.
A direct backend-frame capture now joins all 1,559 selected draws, including
189 foliage actions, to source-5000/output-5001 fixtures with exact foliage
vertex inputs and constants. A same-frame four-sample replay of matched
foliage event 10089 with its captured BC3 alpha path and exact compatibility
prior reproduces all 60,826 changed pixels, every per-sample write and depth
value within its active EDRAM tile. This resolves that draw's earlier
unmasked depth discrepancy but does not prove the original material path,
full-family alpha parity, semantic resource
lifetimes or full-slice image parity. See the complete-slice evidence.
A second same-frame draw using a different captured BC3 chain also matches
all four sample masks and written depth values exactly.
The complete same-frame BC3 depth census covers all 54 textured foliage
actions in their active EDRAM tiles: 28 make no depth writes, 25 visible
draws have exact per-sample coverage, and one visible draw misses one sample.
The largest overlapping depth error is `1.3e-08`; nine draws are not
bit-exact. The tile mapping is explicit and reproducible in the
complete-slice evidence. This is a diagnostic alpha-path result, not
semantic material, lifetime or full-slice parity admission.
A paired RenderDoc target check explains the apparent 180° mismatch against
the presented screenshot: the compatibility scene attachment is itself
inverted and reused in EDRAM bands. Compare target-space coverage/depth before
claiming parity; see the complete-slice evidence.

**Full SNR-04 acceptance (later than L1/L2):** every selected item is
accounted for and the diagnostic scene is stable at reference resolution,
with no silent missing, duplicated, stale or misattributed objects. Small
documented rendering approximations may
pass the visual bar; stale or wrong-owner data cannot.
The in-memory in-game private-target path and moving-frame comparison meet the
predeclared visual bar, and an unload/reload check validates resource
freshness. Unknown authoritative relationships stop this gate; isolated
byte/sample differences do not. Publish the measured in-game cost for L3/L4
optimization without using it to block the first live or playable renderer.

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

**Done when:** representative materials meet the predeclared visual bar and
all admitted variants have a deterministic source/build route. A deliberate
approximation is acceptable when its visible effect is documented and remains
within that bar; an absent shader or local-cache-only source is not.

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

**Done when:** the complete slice meets the agreed visual bar during movement
and streaming, with measured resource memory and no stale/placeholder content.
Private rendering may still coexist with compatibility until SNR-09–10; no gain
is claimed.

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

**Done when:** suppression is paired and meets the agreed visual bar, and
counters plus profiles prove substantial replaced work no longer executes.
A native image alongside the original renderer cannot close this ticket.

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

**Done when / L4 qualification:** the predeclared approximate visual bar and
gameplay checks pass, the entire supported slice is admitted without concealed
omissions, memory/tails meet the frozen limits, and median improvement clears
both the 15% target and control noise. Do not require byte-identical output.
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
