# Shadow and reflection pass census

This is the first capture-and-documentation boundary for NR-05F. It enriches
the existing payload-free RenderDoc pass trace with exact graphics-pipeline,
shader identifiers and labels, viewport, scissor, depth, raster, and target
metadata. It does not export images, buffers, textures, shaders, or other game
payloads.

## Safety boundary

The effect-pass census groups exact pipeline metadata into deterministic
families. Target topology produces only mechanical candidate classes:

- `depth_only_write_candidate`;
- `depth_only_read_candidate`;
- `color_depth_candidate`;
- `color_only_candidate`; and
- `no_output_candidate`.

These names do not assign a semantic role. Every family remains
`unknown_unclassified`, reports no native coverage, is suppression-ineligible,
and leaves Xenos authoritative. A depth-only pass is not automatically a
shadow map, and a repeated square color target is not automatically a
reflection or cubemap.

## Workflow

```powershell
.\tools\export-native-renderer-pass-trace.ps1 `
  -Capture '.local\qualification\reference.rdc' `
  -RenderDocRoot '.local\tools\renderdoc\RenderDoc_64' `
  -Output '.local\qualification\effect-pass-trace.json'

python .\tools\build-native-renderer-effect-pass-census.py `
  .local\qualification\effect-pass-trace.json `
  --classifier config\native-renderer\effect-pass-classifier.json `
  --output .local\qualification\effect-pass-census.json
```

The trace must explicitly prove that it exported no resource payload and that
its added fields are pipeline metadata only. The census rejects legacy traces
without the enriched contract instead of silently producing weak candidates.

## Promotion evidence

A candidate may receive a `shadow` or `reflection` role only after at least one
stronger source agrees with its exact signature, such as:

- a high-level title hook enclosing the complete pass;
- a controlled light, caster, or reflection-probe perturbation;
- a bounded resource-consumer chain proving later shadow/reflection sampling;
- shader reflection or disassembly proving the expected transform and output;
- or a reviewed RenderDoc image/resource inspection performed locally.

Promotion must retain per-item replay fallback, an independent feature gate,
and guest-visible side effects. Native drawing, atlas allocation, reflection
publication, and Xenos suppression remain out of scope for this census.

The later compute-handoff export identifies the two compute consumers that were
previously boundary-only events. Both use pipeline `RT Dump kD24S8 1xMSAA` and
shader `{83b6d426}`, bind the selected D24S8 texture twice as read-only images,
and write the 40 MiB `EDRAM Buffer`. Event 1426 (`52x128x1`) immediately follows
the inspected 80-draw vehicle-shadow epoch. This proves the next ownership
boundary is an EDRAM dump rather than a pixel depth-copy family; it does not by
itself authorize publication or suppression.

## Initial open-world census

The qualified `open_world_day` capture `reference_frame8134.rdc` (SHA-256
`EF4064929005D08432488FD4649E845630860044A6CDC49E463FA7B3883667DA`)
contains 1,582 authoritative Xenos draws and six ignored diagnostic native
draws. The enriched census groups the authoritative work into 273 exact
pipeline families:

| Mechanical output class | Draws |
| --- | ---: |
| Depth-only write candidate | 922 |
| Depth-only read candidate | 241 |
| Color + depth candidate | 357 |
| Color-only candidate | 62 |

One bounded target is the strongest next shadow candidate without yet being a
semantic match. Resource `RT @ 720t, <13t>, 1xMSAA, kD24S8` receives 33
depth-only draws through 1024 by 1024 viewports and 80 through 2048 by 2048
viewports. The 2048 group has no pixel shader and is dominated by vertex shader
labels `Shader {b1ccceb6}` (64 draws), `Shader {d18760b6}` (12), and
`Shader {23c9cd31}` (4). This exact target/view/shader boundary is suitable for
a bounded producer-consumer or controlled-light probe. It is not sufficient to
identify a shadow atlas, cascade split, caster class, or quality tier, so the
report keeps both shadow and reflection qualification false.

## Bounded resource lineage

The candidate target is joined to exact pass metadata with a second
payload-free export:

```powershell
.\tools\export-native-renderer-resource-usage.ps1 `
  -Capture '.local\qualification\reference_frame8134.rdc' `
  -RenderDocRoot '.local\tools\renderdoc\RenderDoc_64' `
  -ResourceName 'RT @ 720t, <13t>, 1xMSAA, kD24S8' `
  -Output '.local\qualification\depth-resource-usage.json'

python .\tools\build-native-renderer-effect-resource-lineage.py `
  .local\qualification\depth-resource-usage.json `
  .local\qualification\effect-pass-trace.json `
  --effect-census .local\qualification\effect-pass-census.json `
  --output .local\qualification\depth-resource-lineage.json
```

The exporter requires one exact resource-name match, records action metadata
only, and exports no resource payload. The joiner requires all reports to name
the same capture hash, rejects pixel reads without authoritative draw metadata,
and maps each depth write through the census's exact event inventory. Every
epoch reports its producer families, caster classes, classified shadow writes,
and unclassified writes. `caster_class_complete` remains false if even one
write lacks a capture-bound caster class.

The 1xMSAA D24S8 candidate has six clear/write epochs, 207 unique depth-target
writes, 36 pixel-shader reads, and two unique compute-read events. Every epoch
is sampled after a write. All 36 pixel consumers write another depth target;
none writes color. Their fixed vertex shader is `Shader {c700dc5c}`, and the
pixel shaders are `Shader {1007aa27}` and `Shader {ea1021af}`. The immediate
destination is `RT @ 720t, <13t>, 4xMSAA, kD24S8`.

Following that destination proves the same mechanical pattern: four complete
clear/write epochs, 40 unique depth-target writes, 59 pixel reads, and two
unique compute-read events. Every pixel consumer again writes depth only, with
zero color outputs. The square-view target is therefore a qualified
depth-to-depth propagation chain and not a direct scene-color shadow sampler.
That mechanical result does not identify the source contents by itself.

## Exact shadow-depth promotion

Reviewed local depth exports supply the stronger semantic evidence required by
the promotion contract. The image after event 803 shows an orthographic world
caster view in the 1024-square epoch. The image after event 1417 shows an
isolated top-down vehicle silhouette in the 2048-square epoch; its SHA-256 is
`3CAE4CEFD2F93B5E6645653D81440C9FED47CA22557A16B2CA3B90FCA828DF9A`.
The payload images remain local and are not tracked or distributed.

`config/native-renderer/effect-pass-classifier.json` promotes only the three
exact 2048-square producer families enclosed by that inspected epoch. Each is
also classified as `dynamic_vehicle` in atlas region `0,0,2048,2048`:

| Pipeline label | Vertex shader label | Draws | Role |
| --- | --- | ---: | --- |
| `VS 4E1DA281CC3D7EDB` | `Shader {b1ccceb6}` | 64 | `shadow_depth` |
| `VS CDDB454589126317` | `Shader {d18760b6}` | 12 | `shadow_depth` |
| `VS 68DF329C66481843` | `Shader {23c9cd31}` | 4 | `shadow_depth` |

The match also requires the exact D24S8 target label, 2048 by 2048 viewport,
depth-only output class, and absent pixel shader. Each rule is bound to the
qualified capture hash and reviewed image hash, and must match exactly one
family. The classified report contains 80 `shadow_depth` draws in three
`dynamic_vehicle` families; the other 1,502 draws in 270 families remain
`unknown_unclassified`. This proves a shadow-depth producer seed, not an atlas
layout, cascade model, native renderer, or suppression boundary. Native
coverage and suppression remain false, Xenos stays authoritative, and
reflection remains unidentified.

The inspected 1024-square atlas region is deliberately not labeled static.
Its event-803 image (SHA-256
`A87E3AF9A36023E29D1F294F1E7155F7973FC78CB9B9CB75207E7B6CF866C675`)
contains an orthographic mixed world view with both environment and vehicle
silhouettes across ten exact families and 33 draws. Calling that region
`static_world` would therefore erase a real dynamic-caster dependency. A later
classifier may promote individual 1024-square families only after per-family
contribution or title provenance distinguishes their caster class.

The exact event-inventory join makes that incompleteness machine-checkable.
Across the selected resource's six clear/write epochs, no epoch is yet
caster-complete. The epoch from clear event 947 through event 1446 contains all
80 classified `dynamic_vehicle` writes plus nine additional unclassified depth
writes. The 1024-square world-view epoch from clear event 514 through event 832
contains 42 total depth writes, all still unclassified by caster. The report
therefore records `caster_complete_epochs=0`; the 80-draw native subepoch stays
usable, but neither a whole-resource vehicle classification nor a static-cache
policy is admitted.

The first executable follow-up is documented in
`SHADOW_DEPTH_ISOLATED_REPLAY.md`. It admits only the dominant
`4E1DA281CC3D7EDB` producer through its complete stable draw and attachment
contract, duplicates one draw into a private depth-only target, and preserves
the authoritative Xenos draw. It does not yet allocate or publish a native
atlas.

The next bounded follow-up is documented in
`SHADOW_DEPTH_BATCH_REPLAY.md`. The capture proves that all 80 promoted draws
form one uninterrupted producer epoch: 64 dominant-family draws followed by an
exact four-times repetition of three secondary-family draws and one
tertiary-family draw. The private path may seed once and reuse its depth-only
target for exactly that epoch. Gaps, frame changes, family/count reordering,
target mismatches, and backend failures remain fail-closed; Xenos stays
authoritative.
