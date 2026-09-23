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
