# Native renderer post-processing census

## Scope and safety boundary

NR-05G starts with a payload-free topology census. It does not assign tone
mapping, exposure, bloom, motion blur, color grading, depth-of-field, upscale,
or UI-composite semantics from shader shape alone. It exports only RenderDoc
action, attachment, transfer, and resource-usage metadata. Xenos remains
authoritative; native coverage and suppression remain disabled.

The target-usage exporter visits every authoritative draw, inventories its
color targets, and follows texture copy/resolve destinations. Non-texture
transfers are counted but excluded because this report has no bounded buffer
description contract. The offline census then links a resource read to the
most recent authoritative draw producer, crossing an exact copy/resolve only
when the captured source and destination are both known. Missing, cleared,
buffer-backed, or ambiguous lineage stays unresolved.

## Reproduction

```powershell
.\tools\export-native-renderer-target-usage.ps1 `
  -Capture '.local\qualification\native-renderer-renderdoc-seeded\reference_frame8134.rdc' `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -Output '.local\qualification\nr05g-target-usage.json'

python .\tools\build-native-renderer-post-chain-census.py `
  .local\qualification\nr05g-target-usage.json `
  .local\qualification\nr05f-labeled-pass-trace.json `
  --output .local\qualification\nr05g-post-chain-census.json
```

The input capture SHA-256 is
`EF4064929005D08432488FD4649E845630860044A6CDC49E463FA7B3883667DA`.
The enriched pass trace SHA-256 is
`D8D05B35B4EFAE3B4810C3639C8F9562F002F0DB686F6CE68278857797895DC7`.
Local game-derived reports stay below `.local/qualification` and are not
committed.

## Current evidence

The open-world frame produced the following metadata inventory:

| Measurement | Count |
| --- | ---: |
| Tracked texture targets/destinations | 67 |
| Texture copy/resolve transfers | 125 |
| Non-texture transfers excluded and counted | 524 |
| Authoritative color-target draw events | 419 |
| Exact draw-to-draw resource edges | 31 |
| Reads without an exact draw producer | 69 |
| Presentation sinks | 1 |
| Presentation-reachable draws | 1 |
| Presentation source boundaries | 1 |

The sink is event `11363`, a four-index, full-output draw to
`Swapchain Image 309`, followed by the present boundary at event `11372`.
It is a mechanically full-screen candidate only and remains
`operator_review_required`. Its ingress does not appear in the tracked texture
target lineage, so `presentation_ingress_resolved`, effect semantics, the
full-resolution UI boundary, and native implementation readiness are all
false. This is consistent with the final ReXGlue compositor crossing a
buffer-backed or otherwise unbound-to-color-target handoff.

The deterministic local target-usage report SHA-256 is
`2CC702B5259B2A302414650DC1C39E1BC103A1C3C19E325A70AA11F0F5C40A35`;
the derived census SHA-256 is
`A1BC0BFB2503C3AF2BD5C07EBE19A11C2F84C03FCA986F44798938C6C9A07C7F`.

## Next boundary

The next capture-only change must add a bounded inventory of the final
compositor's read-only bindings or the excluded buffer transfer chain. It must
join that ingress back to the guest color-target/resolve graph before any
effect family is named. Only after the presentation ingress and UI boundary
are exact should an isolated native tone-map or upscale implementation begin.
