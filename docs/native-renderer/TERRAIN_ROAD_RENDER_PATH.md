# Terrain and road render-path differential

Phase C1 starts from a title-owned control rather than assigning a semantic
name to a shader or draw-frequency cluster. Static analysis proves that the
retail executable registers `fasttrackrender`, `trackfardistance`,
`renderroaddetailblur`, and `notrackcommandbuffers` on the exact
`CForzaCommandLineParameters` object. The `perfmode` master option fans out to
`fasttrackrender` and eight neighboring fast-family flags, so it is not an
isolated terrain/road experiment.

## Exact configuration bridge

`tools/discover-native-renderer-track-config.py` validates the option strings,
RTTI, registration vtable slot, parser calls, field offsets, and the known
command-line-to-runtime copies. It fails closed if any instruction or image
identity drifts. The relevant title fields are:

| Option | Command-line field | Runtime field | Role |
| --- | ---: | ---: | --- |
| `fasttrackrender` | 4204 | 6297 | isolated title track-family switch |
| `trackfardistance` | 4176 | live option store proved; downstream consumer open | floating distance control |
| `renderroaddetailblur` | 4181 | 6035 | road-detail effect switch |
| `notrackcommandbuffers` | 2732 | 6230/6232 | inverted command-buffer control |

The `trackfardistance` default load and live-object store occur in
`sub_824F7898` at `0x824F7DB8` and `0x824F7DC0`. The source image value is
exactly `55.0`; the isolated mode replaces only that store with `5.0` and
records both values. This proves deterministic ownership of the title option,
but not yet the downstream renderer consumer.

The boolean runtime copy occurs in `sub_8259C7D8` after the title retrieves the live
command-line parameter object. The retail startup path does not consume
ReXGlue's `ExLoadedCommandLine` bridge for this object. The census therefore
uses opt-in hooks at the exact `trackfardistance`, `fasttrackrender`, `renderroaddetailblur`, and
transformed `notrackcommandbuffers` destination stores (`0x8259C834`,
`0x8259C89C`, and `0x8259C8DC`, plus `0x824F7DC0`). It forces a deterministic one-switch mode and
records every original value. This proves a bounded title configuration path;
it does not yet prove which prepared signatures are terrain, road surface,
track props, or an exceptional dependent family.

Generate the payload-free static report with:

```powershell
python tools/discover-native-renderer-track-config.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-track-config.json
```

## Paired runtime census

The census wrapper accepts five deterministic modes. Each mode forces the
proved floating option and all three booleans at their exact stores so only
one value differs from the baseline:

| Mode | Track far distance | Fast track | Road-detail blur | Track command buffers |
| --- | ---: | --- | --- | --- |
| `baseline` | 55.0 | off | on | on |
| `trackfardistance` | 5.0 | off | on | on |
| `fasttrackrender` | 55.0 | on | on | on |
| `noroaddetailblur` | 55.0 | off | off | on |
| `notrackcommandbuffers` | 55.0 | off | on | off |

These controls do not enable the broader `perfmode` group. Explicitly
supplying a mode also arms the exact prepared-draw provenance required by the
paired report. Run the same AppData save and marked scene for the baseline and
one variant, then compare exact prepared signatures and semantic submission
lineage from the two logs.

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
  'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot -Scene open_world_day -TrackRenderMode baseline
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot -Scene open_world_day `
  -TrackRenderMode fasttrackrender
```

The delta is candidate evidence only. A family becomes a Phase C1 rendering
input only after the changed signature has exact semantic PM4 lineage,
mechanically valid replay, representative visual identification, and stable
coverage across open world and race scenes. Xenos remains authoritative, no
native draw or suppression is enabled by this checkpoint, and the capture
does not require any save-file operation.

After both sessions exit, build the strict normalized delta report:

```powershell
python tools/summarize-native-renderer-track-differential.py `
  --baseline <baseline-jsonl> `
  --fasttrackrender <fasttrackrender-jsonl> `
  --output .local/qualification/native-renderer-track-differential.json
```

For another discriminator, replace `--fasttrackrender` with `--variant
<jsonl>` and pass `--variant-mode trackfardistance`, `noroaddetailblur`, or
`notrackcommandbuffers`.

The v3 report requires distinct sessions from the same executable and patch set,
one shared marked scene, at least 600 frames per side, zero signature overflow,
normal shutdown, and runtime confirmation that the title accepted the requested
mode. It compares exact prepared procedural-model provenance in calls per 1,000
frames and retains shader, template, receiver-generation, and record identity
for each changed family. It also joins materially changed signatures to exact
prepared semantic-visibility candidates and reports their mechanical rejection
masks. A complete report proves a title-owned track delta; it deliberately
leaves representative terrain/road identity, native admission, and suppression
false.

## Qualified open-world differential

The AppData-backed `open_world_day` pair completed on the same local build:

- baseline session `20260830T233745Z-p15720`: 4,388 frames and 6,325,239
  draws;
- `fasttrackrender` session `20260830T234026Z-p31828`: 4,817 frames and
  7,471,561 draws;
- both runtime controls completed with the original title value `false`, the
  requested runtime value applied exactly, normal shutdown, and Xenos
  authority preserved; and
- the normalized report found 331 material exact-family deltas after removing
  504 low-rate jitter rows.

The paired evidence proves the title-owned track-render differential and gives
the next C1 slice a bounded candidate set. It does not identify all 331 rows as
terrain or roads: menu/loading variance and dependent families are still
present in the session-wide aggregates. Native admission therefore remains
disabled until representative candidates receive visual identification,
isolated replay, and open-world/race stability evidence.

## Candidate reduction checkpoint

The first exact `fasttrackrender`-only probe used prepared signature
`044DA8CCB07E4236` in the same stationary festival scene. The title lineage
was repeatable, but isolated admission failed closed with mechanical rejection
mask `00004000` (`render_targets`). The paired visibility census likewise found
no materially changed `fasttrackrender` family that satisfied the current
color replay contract. This shows that the strongest fast-track deltas are
render-to-texture or dependent work, not yet proof of a visible terrain/road
color family.

The matched follow-up matrix completed on executable
`EDC2C531BD61565ACFFCA897DA1FF88DF282F383468D331E404DF701E2BB8B7B`:

- baseline `20260831T000126Z-p16032`: 6,265 frames and 9,313,318 draws;
- `noroaddetailblur` `20260831T000504Z-p27532`: 6,890 frames and
  11,685,250 draws, with 317 material deltas after 491 jitter rows; and
- `notrackcommandbuffers` `20260831T000916Z-p8992`: 5,885 frames and
  8,040,263 draws, with 314 material deltas after 280 jitter rows.

All three controls applied their exact expected values and exited normally.
Both isolated reports prove that the title switches affect submitted work,
but joining every material delta to the semantic-visibility candidate census
found zero changed families with mechanical rejection mask `00000000`.
Consequently neither discriminator currently identifies a safe visible color
replay. Xenos remains authoritative and native admission remains disabled.

## Track-far-distance qualification checkpoint

The matched AppData-backed `55.0` versus `5.0` pair used one clean executable
and the same stationary festival scene:

- baseline `20260831T004121Z-p23820`: 4,146 frames and 4,344,201 draws;
- `trackfardistance` `20260831T004400Z-p35676`: 4,480 frames and 4,860,836
  draws; and
- 77 material families changed after 756 normalized rate-noise families were
  rejected.

This proves that the live floating option reaches submitted renderer work.
Four changed signatures joined to ten exact semantic-visibility candidate
entries. Six entries rejected on mask `00004000`, two on `00000001`, and two
entries for one signature (`BE5FF23CA0389E54`) were mechanically eligible.
That signature had 132 baseline calls and zero variant calls, but its eligible
candidate rows comprised only 17 draws at baseline frames 3,083 and
3,095-3,097 during the transition into the save. Representative gameplay
identity is therefore not proved, and neither native admission nor suppression
is allowed.

The independent title switches are now exhausted as useful C1 discriminators.
The next lead is semantic world-section/mesh ingress, with the exact
visibility-to-prepared lineage retained as its fail-closed replay gate.

## Track world-ingress static proof

`tools/discover-native-renderer-track-ingress.py` now makes that lead exact.
It validates the retail RTTI complete-object locators, full AOT-backed vtables,
and reviewed specialization slots for the unified track presentation, render
model, render-model instance, track model/mesh/submodel, procedural-geometry
object/resource, and PVS-zone object/resource classes.

The proof separates three layers that broad draw deltas could not distinguish:

- the 135-slot unified title presentation surface and its exact overrides;
- the unified render-model and render-instance surfaces; and
- the track model, mesh, procedural-geometry, and visibility-zone resource
  graph that owns world-section identity before prepared draw submission.

Generate the payload-free report with:

```powershell
python tools/discover-native-renderer-track-ingress.py `
  .local/generated/default `
  --image ..\horizon1-recomp\.local\analysis\default-image.bin `
  --output .local/qualification/native-renderer-track-ingress.json
```

This is a static ownership proof, not yet the runtime semantic join. The next
slice may observe only the reviewed title lifecycle boundaries and must join an
exact shared object or resource identity to
`proceduralGeometry::CProceduralModels`. Xenos remains authoritative; native
admission and suppression remain disabled.

## Exact track-texture provider join

The previously captured AppData session `20260831T004400Z-p35676` already
contains the first exact title-to-prepared-record identity join. Its complete
semantic-submission report contains 867 aggregated entries and 397,142 live
submission calls. Every entry resolves its primary resource through vtable
`82001708`. Retail RTTI identifies that vtable as
`Presentation_Unified::CTrackTexture_Unified`, and all four observed provider
methods match its exact slots 6, 9, 10, and 11 (vtable byte offsets 24, 36, 40,
and 44).

`tools/summarize-native-renderer-track-world-join.py` validates that join from
the payload-free static-ingress and semantic-submission reports. It records
the track provider coverage without re-reading captured payloads or requiring
another game run.

This closes track-owned texture-provider identity at the procedural-model
prepared-record boundary. It does not yet prove that any joined geometry is a
terrain or road mesh: the next join must carry track model, mesh, submodel, or
world-section resource identity to the same records. Native admission and
suppression therefore remain disabled and every call still replays on Xenos.

## Prepared-workset provider filter

The runtime now carries that exact primary-provider tuple through the semantic
draw identity and fresh visibility-prepared candidate record. The existing
default-off continuous prototype workset rejects fresh visibility candidates
without it, while retaining the separately qualified sky/horizon seed. Its
summary accounts `non_track_provider_rejections`, and the payload-free
prepared-candidate report partitions exact provider entries and draws.

This is an implementation checkpoint pending the next batched preview build
and AppData-backed run. It narrows the prototype's existing private native
replay; it does not identify terrain/road geometry, enable C1 family admission,
enable suppression, or change Xenos authority.

## Exact track render-model submission scope

The earlier typed-render-item diagnostic at `8240EC18` was originally pursued
as a vehicle lead. Its qualified runtime profile was actually unambiguous track
RTTI: root vtable `820019CC` is
`Presentation_Unified::CTrackRenderModelInstance_Unified`, and child vtable
`82001D74` is `Presentation_Unified::CTrackRenderModel_Unified`. Static title
flow shows that `8240EC80` is reached only after the instance, its child, and
the child-owned 248-byte type-21 descriptor pass the title predicates. The
nested render dispatch returns at `8240ECAC`.

A balanced passive runtime scope now brackets those two addresses. It joins
only procedural-model semantic submissions made synchronously inside the exact
dynamic-type scope, carries the result to prepared candidates, and separately
tests exact equality between the title descriptor/root/child identity and the
procedural receiver, runtime object, bound resource, and provider identities.
The payload-free qualifier distinguishes exact nested ownership from the
stronger shared-object/resource proof rather than conflating them.

This instrumentation awaits the next batched AppData-backed run. Until then it
does not prove the runtime join, terrain/road visual identity, or C1 admission.
It changes no guest state, draw, output authority, or suppression decision.

## Bounded track world-resource graph identity

The balanced render-model scope now extends the passive join without adding a
new title hook. After the exact unified instance/model vtables and type-21
descriptor contract pass, it scans the already-live 64-byte render-model child
prefix and 248-byte descriptor for aligned direct object pointers. A pointer is
classified only when its first word is one of the static-ingress proof's exact
RTTI-backed vtables:

- `CTrackModel`, `CTrackMesh`, or `CTrackSubModel`;
- `CTrackProceduralGeometryObject` or
  `CTrackProceduralGeometryResource`; and
- `CTrackPVSZoneObject` or `CTrackPVSZoneResource`.

The scope records two distinct facts. The world-resource mask means an exact
class appeared directly in the accepted title graph. The shared-resource mask
is stronger: that same object address also equalled the procedural receiver,
runtime submission object, bound resource, or exact provider object for a
synchronous submission. Neither fact is inferred from frequency, shader
similarity, or payload contents.

The scan is bounded and cached. A 1,024-entry thread-local cache is keyed by
child/descriptor address plus a fingerprint of the already-read words; a cache
hit performs no repeated pointer validation. Each graph retains at most 16
unique exact-class references and fail-visible overflow accounting. The runtime
and prepared-candidate qualifiers separately report graph presence and exact
cross-boundary shared identity.

This instrumentation is part of the next batched AppData checkpoint. A graph
identity alone is useful track ownership evidence, while exact shared identity
is the preferred C1 terrain/road admission gate. Until runtime qualification,
Xenos remains authoritative and no native admission or suppression is enabled.

### First-run host mapping correction

The first merged AppData run reached 8,700 frames before an access violation at
native RVA `5D0616F`, reading guest value `40D8D0D8`. The local dump and binary
disassembly identify that RVA as the new direct-pointer vtable load immediately
before comparisons with the exact procedural-geometry vtables. This was not a
title, save, or Xenos draw failure.

The guest heap page table had reported that arbitrary descriptor word readable,
but the translated host page was still uncommitted. The classifier now requires
both the guest heap range check and the platform host mapping/protection query
before loading a candidate vtable. Rejected host-unmapped values are counted in
the runtime summary. Optimized binary disassembly confirms the protection query
and fail-closed branch execute before the vtable load. The failed session is
crash evidence only and cannot qualify C1; a clean batched rerun is required.
