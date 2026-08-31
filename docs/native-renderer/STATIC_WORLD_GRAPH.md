# Static-world SimpleModel resource-to-mesh draw graph

Status: exact model/submodel/mesh draw lineage implemented; runtime
qualification pending

## Purpose

An exact renderer and resource generation still do not identify which title
model members emitted a draw. Phase C2 needs the title-owned resource graph to
reach each PM4 packet without inferring ownership from shader frequency or
visual resemblance.

`tools/discover-native-renderer-static-world-graph.py` validates the graph
against retail RTTI/vtables and generated AOT instructions. It exports only
class, address, slot, and offset facts.

## Exact graph

- `CSimpleModelResource` constructor `82C47DA0` constructs a
  `CSimpleModel` at resource offset 112 through `82C47CA0`.
- That model installs primary vtable `82229208` and secondary vtable
  `822291E8`.
- Renderer slot 12 copies its offset-72 resource reference, derives the exact
  embedded model at `resource + 112`, and calls model slots 2 and 4 to count
  and select a submodel.
- The selected `CSimpleSubModel` uses exact vtable `822291BC`; slots 3 and 5
  count and select a `CSimpleMesh` with exact vtable `822291A0`.
- Immediately around the direct indexed-draw call at `82C4DC54`, registers
  `r26`, `r29`, and `r28` contain that model, submodel, and mesh respectively.
  The balanced exit is `82C4DC58`.

The passive hook accepts the member tuple only inside an already exact live
renderer/resource/payload-generation scope, validates all three vtables, and
requires `model == resource + 112`. The tuple is then carried through physical
PM4 provenance into the prepared-draw record. Unknown or mismatched tuples
remain Xenos-only and are fail-visible in cumulative accounting.

## Generate the static report

```powershell
python tools/discover-native-renderer-static-world-graph.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-graph.json
```

The combined runtime qualifier consumes the report with:

```powershell
python tools/summarize-native-renderer-static-world-runtime-join.py `
  .local/preview/logs/<session>.jsonl `
  --static .local/qualification/native-renderer-static-world-ingress.json `
  --lifetime .local/qualification/native-renderer-static-world-lifetime.json `
  --resource .local/qualification/native-renderer-static-world-resource.json `
  --streaming .local/qualification/native-renderer-static-world-streaming.json `
  --graph .local/qualification/native-renderer-static-world-graph.json `
  --owner .local/qualification/native-renderer-static-world-owner.json `
  --session <session> `
  --output .local/qualification/native-renderer-static-world-runtime-join.json
```

## Remaining boundary

This identifies the exact generic SimpleModel member graph behind each joined
draw. It does not distinguish an individual building from a prop, classify
mesh/material fields, or authorize native replay. Runtime qualification must
also prove the graph and payload-reset transitions under representative
streaming. Native admission, publication, and suppression remain disabled;
Xenos stays authoritative.
