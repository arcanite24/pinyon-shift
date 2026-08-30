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
`operator_review_required`. The initial target-lineage census could not see its
ingress, so it kept effect semantics, the full-resolution UI boundary, and
native implementation readiness false and required the bounded binding
follow-up below.

The deterministic local target-usage report SHA-256 is
`2CC702B5259B2A302414650DC1C39E1BC103A1C3C19E325A70AA11F0F5C40A35`;
the derived census SHA-256 is
`A1BC0BFB2503C3AF2BD5C07EBE19A11C2F84C03FCA986F44798938C6C9A07C7F`.

## Presentation ingress checkpoint

A bounded follow-up inspects only event `11363` and verifies its later present
boundary. It exports one active pixel-stage image binding and no resource
payload:

```powershell
.\tools\export-native-renderer-presentation-bindings.ps1 `
  -Capture '.local\qualification\native-renderer-renderdoc-seeded\reference_frame8134.rdc' `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -EventId 11363 `
  -Output '.local\qualification\nr05g-presentation-bindings.json'

python .\tools\build-native-renderer-presentation-ingress.py `
  .local\qualification\nr05g-presentation-bindings.json `
  .local\qualification\nr05g-post-chain-census.json `
  --output .local\qualification\nr05g-presentation-ingress.json
```

The binding is `ResourceId::2404`, a `2560×1440`
`R10G10B10A2_UNORM` texture at pixel descriptor zero. Event `11363` writes the
single `3840×2160 B8G8R8A8_UNORM` swapchain target. Both axes therefore have
the exact uniform ratio `3/2`, proving the mechanical presentation-upscale
boundary. The capture records only the event-11363 pixel read for this input;
it has no capture-local color, copy, resolve, or unordered-write producer.
The input is consequently classified as external or pre-capture, not joined
to the guest post-process graph.

This closes `presentation_ingress_resolved` and
`presentation_upscale_boundary_proven`, but deliberately leaves the upscale
algorithm, guest post-chain join, effect semantics, UI-composite boundary, and
native implementation readiness false. The local binding report SHA-256 is
`FA7E0D5CC476DD3554D21204B47EB157DB1C7CC817A1F474179A1AD2E406EDB5`;
the derived ingress report SHA-256 is
`2AFB97FB0982F46C7EEB39296593D9B450886E67F9BAF2B6B31E36C9A4C87C20`.

## Next boundary

The next capture-only change must locate the creation/update/import boundary
for `ResourceId::2404`, or add equivalent ReXGlue diagnostics for the Xenos
presentation surface before event `11363`. It must join that surface back to
the guest color-target/resolve graph before any guest effect family is named.
The already proven 3:2 presentation boundary may support an isolated native
upscale experiment, but its algorithm and UI ordering must remain independently
gated until exact shader or visual evidence is captured.
