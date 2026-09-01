# Continuous native world workset

Phase B1 promotes the qualified visibility-selected private replay from one
draw per frame to a bounded multi-draw target that can participate in the
existing continuous native composition path.

As a standalone experiment this checkpoint is default-off and does not
suppress any Xenos work. The `native_prototype` renderer selector arms the
workset and its exact track-world family automatically. It proves the
accumulation and freshness contract before expanding material-family coverage
or claiming a coherent native scene.

## Selection

Set `PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_WORLD_WORKSET=true` through the
capture wrapper's `-ContinuousWorldWorkset` switch. The mode requires renderer
census and semantic dispatch discovery so every admitted draw has:

- a mechanically replayable prepared-draw contract;
- either a current, selected semantic visibility decision carrying the exact
  unified track-texture provider vtable and four-method tuple, the exact
  previously qualified sky/horizon follower signature, the exact proved
  `82417BC0` procedural color context with a live semantic receiver and first
  color attachment, or, only when the
  additional `-ContinuousStaticWorld` capture switch is set, exact
  `CModelPresentation` resource, asset-key, transform, member-mesh, and
  prepared-layout lineage; and
- exact title-to-backend lineage.

For an explicit C1 qualification probe, add `-ContinuousTrackWorld`. The same
selection is the default when `native_prototype` is active unless
`PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_TRACK_WORLD=false` is set. Semantic draws
then require both the exact unified track render-model scope and a nonzero
shared world-resource identity mask: the same RTTI-proved track model, mesh,
submodel, procedural-geometry, or PVS-zone object/resource address must occur
at the title scope and procedural submission boundary. A provider-only match
is excluded rather than promoted to terrain/road evidence.

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
- `native_renderer.continuous_world_workset.checkpoint` every 300 observed
  frames while the mode is armed; and
- `native_renderer.continuous_world_workset.summary`.

Periodic checkpoints derive the current frame outcome without finalizing or
mutating the live workset. They are diagnostic evidence only: session exit is
unproved, and a later unique shutdown summary always takes precedence.

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
The exact procedural color route is reported independently as
`procedural_color_producer_candidates` and
`procedural_color_producer_requests`; the v8 qualifier requires at least one
accepted request and rejects requests that exceed exact candidates.
Target-construction failures now carry a bounded backend reason code and the
workset summary partitions both all failures and the exact procedural subset.
This distinguishes missing or extra guest attachments, private depth/color
allocation failures, invalid extents or depth formats, and retained-target
mismatches without adding payload capture or weakening Xenos fallback.
When exact track-world selection is armed, accepted requests and provider-only
identity exclusions are reported separately as `track_world_requests` and
`track_world_identity_exclusions`.
Static-world requests and incomplete-lineage rejections are reported
independently. The v6 qualifier requires at least one exact static-world
request and zero static-world lineage rejection when that optional selection
is armed.
Build a payload-free qualification report with:

```powershell
python .\tools\summarize-native-renderer-continuous-world-workset.py `
  .local\preview\logs\events.jsonl `
  --output .local\qualification\continuous-world-workset.json
```

For an interrupted long-session diagnosis only, add `--allow-checkpoint`. The
latest checkpoint may produce `checkpoint_complete`, but cannot satisfy any
gate that requires a normal process exit.

Arm the still-default-off static-world extension for the deferred C1/C2 run:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -ContinuousWorldWorkset `
  -ContinuousTrackWorld `
  -ContinuousStaticWorld
```

Qualification requires at least one exact track-provider visibility request,
one exact procedural color-producer request,
one complete frame with multiple accumulated draws, zero replay or frame
failures, exact accounting, preserved Xenos draws, and disabled suppression.
When `-ContinuousTrackWorld` is armed, at least one accepted semantic request
must also satisfy the exact shared-resource gate.

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
- The optional exact track-world selector admits semantic draws only after the
  strongest already-carried shared-resource identity join. It does not infer
  a road/terrain label from shaders, frequency, or provider identity.
- The optional static-world extension accepts only exact lineage already
  carried into a mechanically replayable prepared draw. It does not embed the
  local category catalog, infer a content class, suppress Xenos, or enable
  itself for the normal prototype selector.
- This checkpoint does not yet prove recognizable world coverage; that requires
  a clean build, an AppData run, and visual inspection after the broader Phase B
  implementation batch is ready.
