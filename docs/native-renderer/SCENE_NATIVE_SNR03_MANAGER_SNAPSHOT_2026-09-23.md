# Character-manager geometry snapshot preflight — 2026-09-23

The sustained-race source-frame-5000 replay exited normally and passed the
strict 4,384-draw frame ledger and fail-closed Gate A partition. Its selected
character-manager contribution has 342 backend draws from 114 title direct
records. Every selected draw uses one vertex shader
`B8489164D5A86043`, a 16-bit indexed triangle list, and two vertex fetches:
fetch 95 has an eight-word stride and fetch 94 a three-word stride. The
index buffer, both vertex fetches and the final-state observer are now
eligible for an opt-in SNR-03 source-frame probe. Compatibility output remains
the default.

Every selected draw returned snapshot status 1 for both vertex fetches and
the index buffer. Repeated snapshots of the same guest range kept one hash:

| Source | Unique ranges | Unique bytes | Bytes checked across draws | Changed ranges |
| --- | ---: | ---: | ---: | ---: |
| Fetch 95, stride 8 | 15 | 914,592 | 20,971,968 | 0 |
| Fetch 94, stride 3 | 1 | 2,487,252 | 850,640,184 | 0 |
| 16-bit indices | 38 | 98,772 | 506,844 | 0 |

The shared fetch-94 range accounts for most diagnostic read traffic. The
1,280 MiB per-frame budget is deliberately separate from the existing track,
item and vegetation budgets. The next fixture should retain each unique
range once, compare every repeated snapshot before publication, and join
all 342 ordered draws to their title record and final state. Hash stability
alone does not own the bytes or prove texture/material generations.

The same output frame also passed the owned track (745 draws), item (171),
vegetation (120) and procedural-character (12) fixture verifiers. Thus
1,048 of 2,541 selected draws already have same-frame owned geometry in
this particular replay; the manager probe is **not** counted in that number.
Car scene-list draws (1,067), manager draws (342), animated scene (12) and
car presentation (72) remain without owned fixtures.

Reproduce the snapshot check:

```powershell
$base = '.local/native-renderer/snr04'
$stateRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
.\tools\launch-preview.ps1 -Configuration RelWithDebInfo -StateRoot $stateRoot -RenderTestScript "$base/track-frame-reference.fh1test" -RenderTestOutput "$base/manager-snapshot-live-a" -RenderTestTimeoutSeconds 3600 -Hidden -CollectFh1PassInventory -GameArgumentsJson '["--pinyon_shift_fh1_gpu_corpus=true","--pinyon_shift_fh1_scene_dump=true","--pinyon_shift_snr01_trace_source_frame=5000","--pinyon_shift_snr01_trace_following_frame=true","--pinyon_shift_fh1_clear_producer_trace=true","--pinyon_shift_snr02_track_payload_probe=true","--pinyon_shift_snr02_item_payload_probe=true","--pinyon_shift_snr03_probe_frame=5000"]' -Json
python tools/summarize-snr01-frame-wide-census.py "$base/manager-snapshot-live-a-evidence.log" --source-frame 5000 --require-candidate-boundary --output "$base/manager-snapshot-live-a-ledger.json"
python tools/partition-snr00-gate-a-slice.py "$base/manager-snapshot-live-a-ledger.json"
python tools/verify-snr03-manager-snapshot.py "$base/manager-snapshot-live-a-evidence.log" "$base/manager-snapshot-live-a-ledger.json"
```

| Evidence | SHA-256 |
| --- | --- |
| `manager-snapshot-live-a-evidence.log` | `D9C7F1662F4A17121E2EBE7AFED7E586628143566C91B9EA554E33382F2A067D` |
| `manager-snapshot-live-a-ledger.json` | `2E12051E3BD91308190F67A41FE0E7F443D3893BA94585D7602CFD4A3294FED2` |

## Owned same-frame fixture

A second source-frame-5000 replay published an immutable `SNR03M1` manager
fixture at output frame 5001. Thirty-four view-8 title records joined 102
selected backend draws. The fixture retains 15 fetch-95 ranges, one shared
fetch-94 range and 24 index ranges, totaling 3,468,072 unique bytes. It
stores every ordered draw's two fetch references, index reference, shader and
texture descriptors, packed vertex constants, and final bound constants,
raster state, viewport and scissor. Every repeated snapshot was compared
with the first owned copy before publication. The independent fixture
verifier checked the contained bytes and hashes against all title, prepared,
fetch, texture and final-state log rows, plus the strict frame ledger.

This replay exited normally with seven compatibility screenshots. Its
2,897-draw census had zero unattributed draws, and the partition selected
1,596. The five owned geometry fixtures now cover **1,272/1,596** selected
draws: track 721, procedural item 309, vegetation 122, procedural character
18 and manager 102. The remaining selected families are car scene lists 292,
animated scene 23 and car presentation 9. The manager fixture has no private
raster or proven texture generations yet.

```powershell
$base = '.local/native-renderer/snr04'
python tools/summarize-snr01-frame-wide-census.py "$base/manager-fixture-live-a-evidence.log" --source-frame 5000 --require-candidate-boundary --output "$base/manager-fixture-live-a-ledger.json"
python tools/partition-snr00-gate-a-slice.py "$base/manager-fixture-live-a-ledger.json"
python tools/verify-snr03-manager-fixture.py "$base/manager-fixture-live-a/snr03-manager-5000.bin" "$base/manager-fixture-live-a-evidence.log" "$base/manager-fixture-live-a-ledger.json"
```

| Evidence | SHA-256 |
| --- | --- |
| `manager-fixture-live-a-evidence.log` | `B7801C57D445DA357D3F7333515C906D211495AE706D219664C55A019646ED2E` |
| `manager-fixture-live-a-ledger.json` | `3BBD3EC51929E3DD710AF711B6DBAD19D334C1C672FB64816FF857822FD7FB13` |
| `manager-fixture-live-a/snr03-manager-5000.bin` | `53F92EFF6438923A45B9F689355862B330187E62C3ABF363939E200CD5187645` |

## Private two-stream identity/depth diagnostic

The standalone SNR-04 diagnostic now reads `SNR03M1`, checks the exact
translated vertex shader `B8489164D5A86043` specialization `1F` (SHA-256
`1CD5925B8515AADB7DB9C94911CF3AEE1F66746BF2E899E218428845D990A248`),
and assembles only captured vertex ranges into a bounded 17,082,120-byte
guest-address span. Both recorded fetch descriptors are rebased to that
private buffer. It draws all 102 indexed submissions with the captured
constants, cull/depth state and three EDRAM tile viewports/scissors into one
1280×720 private identity/depth target. Guest index bytes stay in their
captured order: the translated vertex shader applies the recorded `k8in16`
swap after D3D12 supplies the raw index.

Two standalone runs each produced 33,307 covered pixels, with 31 draw IDs
visible after depth and overdraw. Their identity and depth files matched
byte for byte. The identity silhouettes occupy the spectator positions in
the same-frame compatibility screenshot, but this visual check does not
establish pixel-aligned coverage or depth parity. The diagnostic replaces
the material pixel shader and does not sample the two captured texture
descriptors. It is geometry/ABI evidence, not material or resource-lifetime
admission.

```powershell
& out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe .local/native-renderer/snr04/manager-fixture-live-a/snr03-manager-5000.bin .local/native-renderer/seeded-probe/translation/dxil .local/native-renderer/snr04/manager-diagnostic-a
```

| Private output | SHA-256 |
| --- | --- |
| `manager-diagnostic-a/identity.ppm` | `D700A1B576A29A4321695151A7E09597645A61C9AF8061B5E4275ACDC50A7AEC` |
| `manager-diagnostic-a/depth.f32` | `BDEF1E7FE255BA07BB3398A9BCD69B286559BBF359B39753F87475D359302D79` |
