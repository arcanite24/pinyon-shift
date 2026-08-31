# Vehicle resource contributions

Status: exact offline C4 partition qualified from the existing v15 semantic
constant-bridge report. No semantic body/glass/wheel/light/livery label is
assigned yet.

## Result

The retained vehicle harness previously exposed 30 prepared-signature
families. Those are not 30 independent geometry contributions. Grouping by the
already-retained exact `geometry_resource_hash` produces 15 resource
contributions, each exercised through exactly two prepared-signature variants.

Within every pair, seed index, draw arguments, shaders, prepared pipeline,
render state, template, texture layout/resource, and material-topology key are
identical. Only the prepared signature and its dynamic parameter payload vary.
The source run exercised every variant for 483 or 484 frames and published the
private draw-atomic semantic constant snapshot on every draw.

`summarize-native-renderer-vehicle-contributions.py` locks this mechanical
partition and emits one unclassified row per exact geometry resource. It fails
closed if a resource does not have exactly two distinct variants, any stable
mechanical field drifts within a pair, publication accounting is incomplete,
or the source report changes Xenos authority or safety policy.

## Why this changes C4

Mesh/material role work now has a 15-item geometry-resource frontier rather
than a 30-family prepared-state frontier. A semantic role must be attached to
the exact resource contribution, while its two prepared variants remain
separate render work. Shared prepared signatures cannot supply a role: two
different resource contributions reuse the same signature pair.

The next bounded step is per-contribution isolated output evidence using the
existing retained private target. Coverage, depth, and color contribution may
mechanically distinguish opaque exterior, glazing, wheels, lights, and small
details, but those names remain hypotheses until an independent title-owned
asset/material discriminator agrees. Player identity, native publication, and
suppression remain closed.

## Reproduction

```powershell
python tools/summarize-native-renderer-vehicle-contributions.py `
  .local/qualification/native-renderer-vehicle-c4-semantic-constant-bridge-v15-20260831.json `
  --output .local/qualification/native-renderer-vehicle-resource-contributions-v1.json
```
