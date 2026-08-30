# Bounded native shadow-atlas epoch replay

This NR-05F checkpoint extends the exact private shadow-depth draw into one
bounded, capture-proven 80-draw producer epoch. It does not publish a native
atlas or alter the
game-visible render graph. Every original Xenos draw still executes and remains
authoritative.

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

## Qualification

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -Scene open_world_day `
  -ShadowDepthBatch `
  -IsolatedDrawDir .local\qualification\nr05f-shadow-depth-batch
```

Required evidence is a
`native_renderer.shadow_depth_batch.result` event with
`status=recorded_full_80_draw_atlas_epoch`, byte-identical native and Xenos batch
artifacts, and complete request and batch accounting. Every event must retain
`native_publication=false`, `xenos_draw=preserved`,
`output_authority=xenos`, and `suppression_eligible=false`.

Complete atlas ownership, consumer binding, publication, and suppression remain
closed.

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
