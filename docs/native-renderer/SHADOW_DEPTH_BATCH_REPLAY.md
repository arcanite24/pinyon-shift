# Bounded native shadow-atlas epoch replay

This NR-05F checkpoint extends the exact private shadow-depth draw into one
bounded, capture-proven 80-draw producer epoch and an independently gated
depth-only publication experiment. Every original Xenos producer draw, the
following render-target dump, and all later consumers still execute. No draw or
resolve suppression is enabled.

## Capture-proven boundary

The qualified `reference_frame8134.rdc` capture contains exactly 80 draws and
no other authoritative draw from event 1004 through event 1417. All 80 have no
pixel shader or color attachment and write the same `ResourceId::19359` D24S8
target through the same 2048-square viewport and scissor. Their exact order is
64 draws from `4E1DA281CC3D7EDB`, followed by four repetitions of
`CDDB454589126317` index counts `1474, 506, 3223` and one
`68DF329C66481843` draw with index count `703`. The runtime therefore requires:

- the complete exact 881-index draw from `SHADOW_DEPTH_ISOLATED_REPLAY.md` as
  the batch seed;
- 63 followers that retain the capture-proven shader family, depth-target,
  scissor, depth/raster, indexed-DMA, attachment, and overflow contracts while
  allowing each follower's title-selected geometry count and prepared shader
  specialization;
- the exact 16-draw tail pattern: three zero-specialization
  `CDDB454589126317` draws with index counts `1474, 506, 3223`, then one
  zero-specialization `68DF329C66481843` draw with index count `703`, repeated
  four times;
- one frame and strictly adjacent draw sequence numbers;
- exactly 80 admitted draws; and
- at most one completed batch in the process lifetime.

The capture-bound semantic classifier identifies this complete epoch as the
`dynamic_vehicle` caster class in atlas region `0,0,2048,2048`. Runtime result,
publication, and summary events repeat both fields so a later static/dynamic
policy cannot silently widen this contract to the mixed 1024-square region.

A nonmatching draw, frame transition, sequence gap, target mismatch, or backend
failure abandons the private batch. The next exact draw may begin a newly seeded
batch, but no incomplete result is read back or published. After one batch
completes, all later draws remain solely on the authoritative Xenos path; the
qualification mode does not repeat the private replay every frame.

## Private accumulation

The first draw clones the authoritative D24S8 allocation into a private
depth-only target. The following 79 draws rebind that same private target
without reseeding it. ReXGlue's resume path revalidates the depth attachment
key and rejects every guest color attachment before each duplicate draw. The
16-draw tail reuses the normal draw path's already converted host index buffer;
private replay admits only guest-DMA and host-converted indexed draws.

The first completed batch queues asynchronous native and Xenos depth/stencil
readbacks. Artifacts use `.depth.batch` and `.depth.batch.xenos` suffixes. The
runtime reports draw, batch, interruption, backend-failure, and per-frame quota
accounting at shutdown.

## Compute handoff and publication boundary

The payload-free compute-handoff report for `reference_frame8134.rdc` proves
that event 1426 is the first consumer after the exact event-1417 producer
epoch. Pipeline `RT Dump kD24S8 1xMSAA`, compute shader `{83b6d426}`, reads the
same D24S8 resource through two image descriptors and writes the 40 MiB
`EDRAM Buffer` through a read/write typed-buffer descriptor. Its dispatch is
`52x128x1`. This is a render-target dump into emulated EDRAM, not a pixel
consumer or a final scene-color sample.

`-PublishShadowDepth` requests publication only on draw 80, after its
authoritative Xenos draw has executed. ReXGlue revalidates the exact depth
target key and complete D3D12 resource description, transitions only the depth
resources, copies the accumulated private D24S8 target into the authoritative
target, and restores both states before the retained Xenos dump runs. The
depth-only path rejects every color attachment. A failed or incomplete copy
leaves the authoritative Xenos content in place. Suppression is structurally
disabled for this request.

The metadata-only handoff can be reproduced without launching the game:

```powershell
.\tools\export-native-renderer-compute-handoff.ps1 `
  -Capture .local\qualification\native-renderer-renderdoc-seeded\reference_frame8134.rdc `
  -RenderDocRoot .local\tools\renderdoc-1.45\RenderDoc_1.45_64 `
  -ResourceName 'RT @ 720t, <13t>, 1xMSAA, kD24S8' `
  -Output .local\qualification\nr05f-compute-handoff.json
```

## Qualification

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -Scene open_world_day `
  -ShadowDepthBatch `
  -PublishShadowDepth `
  -IsolatedDrawDir .local\qualification\nr05f-shadow-depth-batch
```

The AppData qualification session `20260830T153020Z-p2564` completed normally
with exit code 0. At frame 5456, draw 1038, the runtime published exactly one
2080x5056 D24S8 private target, with `color=not_bound`, into the retained Xenos
render-target dump. The completed batch contained all 80 draws (64 primary,
12 secondary, and 4 tertiary), with zero interruptions, backend failures,
unsupported requests, target-creation failures, or publication failures.
Native and Xenos readbacks were both 56,950,304 bytes and had identical SHA-256
`B1950219B977C3BAB75715ABEA5A9E7E70881082D6884429CA0DF82334FE5D64`.
The session reported no error-like diagnostic events.

For private replay alone, required evidence is a
`native_renderer.shadow_depth_batch.result` event with
`status=recorded_full_80_draw_atlas_epoch`, byte-identical native and Xenos batch
artifacts, and complete request and batch accounting. Publication qualification
additionally requires exactly one
`native_renderer.shadow_depth_batch.publication` event with
`status=published_depth_stencil`, `color=not_bound`,
`consumer_handoff=xenos_rt_dump_retained`, and no publication failure. Every
event must retain `xenos_producer_draws=preserved`,
`xenos_draw_suppression=false`, `resolve_suppression=false`, and
`suppression_eligible=false`.

Continuous atlas ownership and suppression remain closed. This mode qualifies
only a one-shot native producer-to-Xenos-dump handoff.

## Multi-epoch ownership experiment

`-ContinuousShadowDepth` extends the admitted one-shot handoff across later
exact 80-draw epochs. It requires both `-ShadowDepthBatch` and
`-PublishShadowDepth`. The experiment is bounded to eight published epochs by
default and accepts `-ContinuousShadowDepthEpochs` from 2 through 120. Only the
first completed epoch requests native and Xenos readbacks; later epochs reuse
the same private target path without producing additional artifacts.

The experiment is fail-closed for the lifetime of the process. A non-contiguous
epoch, backend replay failure, non-monotonic publication, or publication failure
emits `native_renderer.shadow_depth_continuous.fail_closed` and permanently
stops later native shadow requests. The current and every later Xenos producer,
render-target dump, consumer, query, fence, and resolve remain active. Draw and
resolve suppression are unavailable in this mode.

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -Scene open_world_day `
  -ShadowDepthBatch `
  -PublishShadowDepth `
  -ContinuousShadowDepth `
  -ContinuousShadowDepthEpochs 8 `
  -IsolatedDrawDir .local\qualification\nr05f-shadow-depth-continuous
```

Qualification requires `status=bounded_multi_epoch_complete`, exactly the
configured number of strictly increasing publication epochs, exact
request/batch accounting, zero fail-closed events, and the same first-epoch
native/Xenos byte parity as the one-shot mode. This proves hybrid multi-epoch
ownership before any Xenos suppression; it does not yet prove an independently
consumed native atlas.

After shutdown, verify the session and paired first-epoch artifacts with:

```powershell
python .\tools\verify-native-renderer-shadow-depth-continuous.py `
  --log <session.jsonl> `
  --native-dir <output>.depth.batch `
  --xenos-dir <output>.depth.batch.xenos `
  --expected-epochs 8
```

The AppData qualification session `20260830T155030Z-p35164` completed normally
with eight consecutive publications on frames 5268 through 5275. The verifier
qualified all 640 requested and recorded draws, retained every Xenos stage,
observed no fail-closed or suppression event, and proved byte-for-byte parity
between the 56,950,304-byte native and Xenos payloads. Both payloads produced
SHA-256
`7F66FEA3EBAF1995C89339095185C0693A3C15F6A0BEDE0B72AFC79E6BC991E5`.

The first AppData qualification attempt (`20260830T140611Z-p3944`) proved why
the seed and follower contracts must be separate: 8,252 exact seeds were
recorded successfully, every one was interrupted by the next family draw, and
the run exited normally with zero backend failures. This fail-closed evidence
prevented broadening the one-shot seed contract; only the capture-proven
followers are admitted after a seed and before the 64-draw boundary.

The corrected AppData qualification (`20260830T141806Z-p28280`) completed
3,481 consecutive batches with zero interruptions or backend failures before
the process exited normally. Its first asynchronous native and Xenos D24S8
artifacts were both 56,950,304 bytes and byte-identical at SHA-256
`0A526FD009A52BD41DE92C63CF20252A1A214F0AC89965F6B746D8D2534D25B9`.
That run also exposed avoidable qualification overhead: completed batches kept
replaying every frame after the evidence was captured. The final contract is
therefore process-one-shot while retaining retry-after-failure behavior.

The 64-draw Release/AppData qualification (`20260830T142402Z-p16956`) exercised
the process-one-shot contract in live festival gameplay. Exactly one batch
started and completed, all 64 requests were recorded, and the run reported zero
interruptions, target failures, unsupported draws, or backend failures. The
result count remained one while gameplay continued. Native and Xenos artifacts
were both 56,950,304 bytes and byte-identical at SHA-256
`A6AA07AC55B4A4851D4636F18D5148C1A52EDD8F2D44FB00CE34DC4F48284DCD`.
Request and batch accounting were complete, Xenos remained authoritative with
suppression disabled, and the process exited normally.

The full-epoch Release/AppData qualification
(`20260830T145725Z-p34560`) reached live festival gameplay and recorded one
complete 80-draw epoch: 64 primary, 12 secondary, and four tertiary draws. All
80 requests were recorded with zero interruptions, unsupported draws, target
creation failures, or backend-failed batches. Native and Xenos D24S8 artifacts
were both 56,950,304 bytes and byte-identical at SHA-256
`B612D06B2599FC84441256DFC08552AFEF2865AD6A58A81AF2A3916E6FE9D128`.
Request and batch accounting were complete, the process exited normally, Xenos
remained authoritative, and native publication and suppression stayed closed.
