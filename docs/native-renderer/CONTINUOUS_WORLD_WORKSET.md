# Continuous native world workset

Phase B1 promotes the qualified visibility-selected private replay from one
draw per frame to a bounded multi-draw target that can participate in the
existing continuous native composition path.

This checkpoint is default-off and does not suppress any Xenos work. It proves
the accumulation and freshness contract before expanding material-family
coverage or claiming a coherent native scene.

## Selection

Set `PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_WORLD_WORKSET=true` through the
capture wrapper's `-ContinuousWorldWorkset` switch. The mode requires renderer
census and semantic dispatch discovery so every admitted draw has:

- a mechanically replayable prepared-draw contract;
- either a current, selected semantic visibility decision carrying the exact
  unified track-texture provider vtable and four-method tuple, the exact
  previously qualified sky/horizon follower signature, or, only when the
  additional `-ContinuousStaticWorld` capture switch is set, exact
  `CModelPresentation` resource, asset-key, transform, member-mesh, and
  prepared-layout lineage; and
- exact title-to-backend lineage.

The exact retained family supplies a current-frame seed in supported gameplay
scenes where the visibility-selected opaque set contains no mechanically
replayable color target. It does not admit unknown signatures. The mode accepts
at most 64 draws in one guest frame. The first accepted draw seeds a private
color/depth pair from the authoritative guest attachments.
Later accepted draws in the same frame resume that private pair without another
seed copy. Target incompatibility, unsupported state, or a replay failure marks
the frame failed and rejects every later candidate in that frame.

## Swap-committed freshness

ReXGlue patch `0094-d3d12-deferred-replay-preview-publication.patch` separates
recording a private replay from declaring it display-fresh:

1. each accepted draw records into the retained private target;
2. successful draws leave a pending frame sequence rather than publishing it;
3. any failed selected draw cancels that pending sequence; and
4. the matching swap commits the sequence immediately before the existing
   guest-output callback checks retained-frame freshness.

The callback can therefore select only a complete accumulated target from the
current frame. A partial or stale workset cannot satisfy the existing exact
frame comparison and the complete Xenos output remains authoritative.

## Diagnostics

The runtime emits:

- `native_renderer.continuous_world_workset.config`; and
- `native_renderer.continuous_world_workset.summary`.

The summary reconciles prepared observations, selection outcomes, replay
outcomes, target reuse, complete frames, failed frames, and the 64-draw bound.
The payload-free qualifier treats an accounted unsupported frame as a proven
Xenos fallback, not as a native success. Continuous native qualification also
requires at least three strictly increasing output markers with exact matching
frame and retained-frame identifiers; every waiting marker must retain Xenos
authority with suppression disabled.
It reports the exact-family seed count separately as
`qualified_retained_family_requests`, and reports fresh visibility candidates
excluded by the track-provider gate as `non_track_provider_rejections`.
Static-world requests and incomplete-lineage rejections are reported
independently. The v4 qualifier requires at least one exact static-world
request and zero static-world lineage rejection when that optional selection
is armed.
Build a payload-free qualification report with:

```powershell
python .\tools\summarize-native-renderer-continuous-world-workset.py `
  .local\preview\logs\events.jsonl `
  --output .local\qualification\continuous-world-workset.json
```

Arm the still-default-off static-world extension for the deferred C1/C2 run:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -ContinuousWorldWorkset `
  -ContinuousStaticWorld
```

Qualification requires at least one exact track-provider visibility request,
one complete frame with multiple accumulated draws, zero replay or frame
failures, exact accounting, preserved Xenos draws, and disabled suppression.

## Safety boundary

- Xenos draws, resolves, queries, fences, memexport, and guest-visible side
  effects remain enabled.
- Output selection remains controlled by the existing renderer selector.
- The mode performs no readback and no guest-target publication.
- Missing semantic lineage, incompatible replay experiments, stale visibility,
  non-track provider identity, capacity exhaustion, or replay failure yields
  without weakening freshness.
- Track-texture ownership is a precision filter for the existing prototype
  workset. It is not a terrain/road mesh ownership claim and does not satisfy
  the C1 semantic-family admission gate by itself.
- The optional static-world extension accepts only exact lineage already
  carried into a mechanically replayable prepared draw. It does not embed the
  local category catalog, infer a content class, suppress Xenos, or enable
  itself for the normal prototype selector.
- This checkpoint does not yet prove recognizable world coverage; that requires
  a clean build, an AppData run, and visual inspection after the broader Phase B
  implementation batch is ready.
