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
