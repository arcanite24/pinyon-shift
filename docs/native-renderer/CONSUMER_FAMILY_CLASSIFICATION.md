# Exact consumer-family classification

The retained sky/horizon producer has 38 stable later-GPU-consumer shader
families in qualified open-world session `20260829T053639Z-p40004`.
`config/native-renderer/consumer-family-classifier.json` turns that observed
set into a deterministic, drift-detecting identity contract without claiming
semantic knowledge that the capture does not prove.

## Fail-closed model

Each rule matches the exact tuple of vertex shader, pixel shader, vertex
specialization mask, and pixel specialization mask. The initial rules use:

- `semantic_role=retained_unknown`;
- `confidence=identity_only`;
- a reference to the qualified session and activity rank; and
- `native_coverage=false`.

The classifier loader rejects duplicate or malformed family identifiers,
unsupported roles or confidence values, blank evidence, a producer-signature
mismatch, and any rule that claims native coverage. Classification changes
only the deterministic report. It cannot submit native work, skip Xenos work,
or authorize suppression.

## Drift report

Run the exact-family summarizer with the tracked manifest:

```powershell
python .\tools\summarize-native-renderer-pass-consumers.py `
  "$stateRoot\logs\<session>.jsonl" `
  --classifier .\config\native-renderer\consumer-family-classifier.json `
  --output .artifacts\native-renderer-pass-consumers.json
```

The schema-v4 report adds `consumer_family_classification` with separate
identity and semantic status. Exact known families are annotated with their
rule evidence. Unknown families become bounded activity-ranked drift records;
overflow remains explicit. A fully matched `identity_status=complete` does not
make `semantic_status` complete while any family remains `retained_unknown`.

## Promotion requirements

A family may move beyond `retained_unknown` only when reproducible evidence
identifies its role. Shader recurrence, texture slot, activity rank, or a
correct-looking frame is insufficient. Promotion should reference one or more
of:

- paired draw isolation proving the visual contribution;
- target and texture provenance across the producer/consumer boundary;
- an identified high-level title render dispatch;
- query, memexport, or guest-memory side-effect evidence; and
- a scene matrix proving the classification does not drift across supported
  states.

Even a high-confidence semantic rule keeps `native_coverage=false` until a
separate native consumer implementation and parity qualification exist. The
current 38 identity-only rules therefore close classifier drift for the
qualified scene but leave all 38 semantic roles and the later-GPU-consumer
suppression gate unresolved.

Reprocessing session `20260829T053639Z-p40004` through the tracked classifier
produced schema-v4 `identity_status=complete`: 38 of 38 observed shader
families matched, with zero drift records and zero drift overflow. It correctly
reported `semantic_status=incomplete`, 38 retained-unknown families, and zero
semantically classified families. The local deterministic report SHA-256 is
`72BAF6322337F7E01A709BA1F2D5730100F70E2745B7B4C8E378358B86E7463B`.
The later-GPU-consumer gate remained `fail`, guest CPU visibility remained
`pass`, Xenos remained authoritative, and suppression remained disallowed.

## Targeted RenderDoc evidence

The census and RenderDoc helpers can mark only authoritative draws that both
consume an output from the exact retained producer family and match one exact
four-field consumer identity. The first activity-ranked family is:

```text
2E5E0A854BE00027/BDFFA72B7ED2FBA4/000000000000003F/000000000016003F
```

Capture it with the AppData save and the exact producer anchor/follower pair:

```powershell
$family = '2E5E0A854BE00027/BDFFA72B7ED2FBA4/000000000000003F/000000000016003F'
.\tools\capture-native-renderer-renderdoc.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -IsolatedDrawSignature '1D253A52B55C9FB3' `
  -PassAnchorSignature '747837906D0BF484' `
  -IsolatedDrawDir '.local\qualification\consumer-family-isolated' `
  -ConsumerFamily $family `
  -CaptureDir '.local\qualification\consumer-family-capture'
```

After closing the captured run, export the first marked draw's bound color and
depth attachments before and after the draw:

```powershell
.\tools\export-native-renderer-renderdoc.ps1 `
  -Capture '.local\qualification\consumer-family-capture\reference_frame1.rdc' `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -OutputDir '.local\qualification\consumer-family-export' `
  -ConsumerFamily $family
```

The schema-v1 report records the exact family, total marker count, up to 64
deterministic marker event IDs, capture and attachment hashes, and the first
draw's before/after images. This is evidence for operator semantic review, not
an automatic role promotion. Marker insertion does not replay, redirect, or
suppress work: every Xenos draw remains authoritative and both draw and resolve
suppression remain false.

### Automatic exact-draw contribution corpus

Manual F12 capture can land on a frame that does not contain the selected
family. For deterministic semantic evidence, request a bounded asynchronous
corpus of the authoritative color and depth/stencil attachments immediately
before and after exact lineage/four-field matches. Capture between 1 and 16
occurrences; eight is a useful qualification batch:

```powershell
$family = '2E5E0A854BE00027/BDFFA72B7ED2FBA4/000000000000003F/000000000016003F'
$readback = '.local\qualification\consumer-family-readback'
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -Scene open_world_day `
  -IsolatedDrawSignature '1D253A52B55C9FB3' `
  -PassAnchorSignature '747837906D0BF484' `
  -ConsumerFamily $family `
  -ConsumerReadbackDir $readback `
  -ConsumerReadbackSamples 8
```

The D3D12 backend owns four independent pending slots for pre/post color and
pre/post depth/stencil. A new occurrence is armed only after all four callbacks
for the previous occurrence complete, so copies cannot alias each other or the
existing isolated-pass readbacks. Every copy is queued around the original
authoritative draw and completes after its submission fence without a GPU
wait. The output remains local, is grouped into deterministic `sample-NNNN`
directories, and contains raw row-pitched target bytes plus fail-closed
metadata.

Build a deterministic visual contribution report with:

```powershell
.\tools\analyze-native-renderer-consumer-readback.ps1 `
  -ReadbackRoot $readback `
  -OutputDir '.local\qualification\consumer-family-contribution'
```

The report validates exact family/frame/draw/sample identity, attachment
layout, and the no-suppression safety fields. Each sample contains color
before/after, difference, and mask images. Multisampled depth/stencil tuple
captures also produce grayscale depth previews and an exact changed-sample
mask; single-sample planar layouts are compared byte-exactly even when they
cannot be visualized safely. The corpus summary counts samples with color and
depth/stencil deltas and records whether every sampled occurrence is unchanged.

The analyzer deliberately leaves
`semantic_role=operator_review_required`. Multiple unchanged occurrences are
stronger negative evidence than one occurrence, but never automatically
promote a semantic role, claim native coverage, or permit suppression. Xenos
remains authoritative throughout.

### Qualification evidence

The `open_world_day` AppData qualification on 2026-08-29 captured four
occurrences of the selected family at frames 3226 through 3229 and draws 236,
540, 338, and 389. Each occurrence produced complete before/after color and
depth/stencil artifacts. The color source was a 2560x1024 four-sample
`R16G16B16A16_FLOAT` target resolved to a single-sample readback payload; the
depth source was retained as exact four-sample depth/stencil tuples.

All four color pairs were byte-identical. Samples 1 and 3 also left the
depth/stencil attachment unchanged. Samples 2 and 4 changed 16,218 and 16
stencil tuples respectively while changing zero depth tuples. The corpus is
therefore complete but does not prove the family inert:
`all_samples_no_attachment_delta=false` and
`semantic_role=operator_review_required`. The stencil contribution is positive
evidence that suppression must remain disallowed until its downstream role and
native parity are understood.

Runtime diagnostics reported four bounded requests, all 16 expected
completions, 1080 exact matches, a normal process exit, and no error,
unsupported-layout, or device-loss events. The 96.340-second run recorded 3744
frame samples, 53.974 median derived FPS, 19.194 one-percent-low FPS, 59.944 Hz
host presentation cadence, no presentation deadline misses, and no
pipeline-cache misses. Xenos remained authoritative, every original draw was
preserved, and both draw and resolve suppression stayed false.

## Rollback-switch boundary

`config/native-renderer/suppression-switches.json` reserves one independent,
startup-only, default-off switch name for the exact producer family. The
validator reports its implementation as absent and the rollback gate as
`unknown`. This is intentional: specifying a switch before suppression exists
prevents a future global or default-on implementation, but it is not evidence
that rollback behavior has been runtime-qualified.

Validate the specification with:

```powershell
python .\tools\validate-native-renderer-suppression-switches.py `
  .\config\native-renderer\suppression-switches.json
```

The report always preserves Xenos authority and keeps suppression disallowed.
