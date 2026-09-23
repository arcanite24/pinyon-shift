# Gate A remaining-family geometry snapshot preflight

The selected car scene-list, animated-scene and car-presentation families are
still missing immutable scene fixtures and private SNR-04 rasters. Their draw
counts and shader mix change across valid replays of the sustained race, so a
shader-hash allowlist did not cover the frozen pilot selection rule. The probe
now captures bounded vertex and guest-index bytes on the two exact candidate
attachment tuples for one requested output frame. The title-side frame ledger,
not the capture predicate, decides which submissions are required.

On the source-frame-5000 replay in
`.local/native-renderer/snr04/remainder-snapshot-live-d`, the frame-wide
owner census passed with 3,861 draws and zero unattributed submissions. The
strict partition selected 2,206 draws. The new verifier checked every one of
the 883 selected remainder-family draws:

| Family | Draws |
| --- | ---: |
| Car scene-list | 814 |
| Animated-scene | 15 |
| Car presentation | 54 |

All recorded vertex and guest-index snapshot statuses were successful. The
verifier also proved stable bytes by hash for 290 repeated vertex ranges and
517 repeated guest-index ranges. Of the 883 draws, 108 have SDK-converted host
indices; their **guest source** is captured, but the converted host stream must
be reconstructed for a private raster. The other 775 use guest DMA indices.
This preflight proves byte availability and same-frame stability, not semantic
mesh/material ownership or a complete diagnostic image.

The extra read path is gated on `pinyon_shift_snr03_probe_frame`, source
frame + 1, the two frozen candidate attachment tuples, a 3 MiB vertex-range
limit, a 128 KiB index-range limit and a 512 MiB additional snapshot budget.
Compatibility rendering remains unchanged and default.

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview'
$base = '.local/native-renderer/snr04'
.\tools\launch-preview.ps1 -Configuration RelWithDebInfo -StateRoot $stateRoot -RenderTestScript "$base/track-frame-reference.fh1test" -RenderTestOutput "$base/remainder-snapshot-live-d" -RenderTestTimeoutSeconds 3600 -Hidden -CollectFh1PassInventory -GameArgumentsJson '["--pinyon_shift_fh1_gpu_corpus=true","--pinyon_shift_fh1_scene_dump=true","--pinyon_shift_snr01_trace_source_frame=5000","--pinyon_shift_snr01_trace_following_frame=true","--pinyon_shift_fh1_clear_producer_trace=true","--pinyon_shift_snr02_track_payload_probe=true","--pinyon_shift_snr02_item_payload_probe=true","--pinyon_shift_snr03_probe_frame=5000"]' -Json
python tools/summarize-snr01-frame-wide-census.py "$base/remainder-snapshot-live-d-evidence.log" --source-frame 5000 --require-candidate-boundary --output "$base/remainder-snapshot-live-d-ledger.json"
python tools/partition-snr00-gate-a-slice.py "$base/remainder-snapshot-live-d-ledger.json"
python tools/verify-snr03-remainder-snapshots.py "$base/remainder-snapshot-live-d-evidence.log" "$base/remainder-snapshot-live-d-ledger.json"
```

The runtime log rotated during the run; `remainder-snapshot-live-d-evidence.log`
concatenates its current-run `runtime.11.log` through `runtime.log` in order.

| Local evidence | SHA-256 |
| --- | --- |
| `remainder-snapshot-live-d-evidence.log` | `D8FF20A1B0385ACF064BBE9178673DF6079411948AEFC9946FE88B28E4A45CE1` |
| `remainder-snapshot-live-d-ledger.json` | `93A089A700AD5F9CDC531E8374F3645BE644274FFBAE9370D93D715ABADBD024` |

The title join, owned geometry fixture, converted-index reconstruction and
combined private identity/depth target were still open in this preflight.

## Car scene-list title handoff

A later strict replay froze 329 title view-8 car scene-list dispatch records
into one immutable source-frame scene. Each record holds the exact dispatch
packet, target command buffer, scene owner/vtable, owner call and arguments.
The output-frame callback joins that record by dispatch packet and target,
then checks live vertex and guest-index snapshot readiness. This join matched
all 1,067 selected car scene-list draws; every join was valid, and there were
no extra or missing joins. The frame-wide census attributed all 4,997 draws,
and the partition selected 2,650 across all Gate A families. The snapshot
verifier also passed the 43 animated and 72 car-presentation draws and found
136 host-converted index sources in these three families.

```powershell
python tools/summarize-snr01-frame-wide-census.py "$base/car-title-join-live-a-evidence.log" --source-frame 5000 --require-candidate-boundary --output "$base/car-title-join-live-a-ledger.json"
python tools/partition-snr00-gate-a-slice.py "$base/car-title-join-live-a-ledger.json"
python tools/verify-snr03-remainder-snapshots.py "$base/car-title-join-live-a-evidence.log" "$base/car-title-join-live-a-ledger.json" --require-car-title
```

| Local evidence | SHA-256 |
| --- | --- |
| `car-title-join-live-a-evidence.log` | `A9D38858DE8D1A28224E4578B76D08DB26DF77F90AD9A96A219A3AEC64696548` |
| `car-title-join-live-a-ledger.json` | `F2D3A9F517A0C494258EAE5101CCA8E3F609CAE1BB398016B33E278AA7271F0C` |

The car title scene currently retains metadata only. The verified geometry,
textures, packed constants and final raster state still need an owned fixture.

## Animated and presentation scalar title handoff

The title's active scalar-draw scope now freezes each direct packet from the
animated caller `82415A28` and the three car-presentation callers `82443B98`,
`82443C40` and `82444018`. Each immutable record retains the direct and
scalar ordinals, packet, caller, object, command, selector and input count.
The output callback joins by exact packet and checks the recorded geometry
sources. A later strict replay passed with 3,690 fully attributed draws and
2,174 selected draws. Its 234 car title records joined all 814 selected car
scene-list draws; 26 scalar title records joined all 12 animated and 54
car-presentation draws. Every join was valid, with no missing or extra joins.
All three families' vertex and guest-index snapshot checks passed, including
108 SDK-converted index sources.

```powershell
python tools/summarize-snr01-frame-wide-census.py "$base/scalar-title-join-live-a-evidence.log" --source-frame 5000 --require-candidate-boundary --output "$base/scalar-title-join-live-a-ledger.json"
python tools/partition-snr00-gate-a-slice.py "$base/scalar-title-join-live-a-ledger.json"
python tools/verify-snr03-remainder-snapshots.py "$base/scalar-title-join-live-a-evidence.log" "$base/scalar-title-join-live-a-ledger.json" --require-car-title --require-scalar-title
```

| Local evidence | SHA-256 |
| --- | --- |
| `scalar-title-join-live-a-evidence.log` | `3D5C1FE00D4B229E5BE8FD67BAAFC9A0FF1CA62160D573BE0A6C22ACA608A18C` |
| `scalar-title-join-live-a-ledger.json` | `77780A43927FD1E11D7842F8942A960440A1B5733C9A4C51C0C488D1DCBCBB0F` |

These title scenes still hold metadata only. The next capture must own the
already verified bytes, per-draw constants, texture descriptors and final
raster state in a fixture, then replay the full selected slice together.

## Owned same-frame remainder fixture

The `SNR03R1` fixture now owns both title scenes, source-frame camera matrices,
deduplicated vertex and guest-index bytes, per-draw shader identities,
primitive/index modes, packed constants, texture descriptors and final bound
system/fetch constants, viewport, scissor and raster/depth state. The SDK
observer exposes all 48 final fetch constants so the car's fetches 89, 90 and
95 can each be checked against their prepared ranges. A repeated range whose
bytes change rejects the entire fixture.

A strict source-frame-5000 replay attributed all 4,614 draws and selected
2,443. The owned remainder fixture contains exactly its 1,149 selected car
scene-list, animated-scene and car-presentation draws (1,067 / 10 / 72),
including 136 draws whose guest indices are SDK-converted. The independent
parser joined every draw to the title ledger and verified 290 vertex and 689
index ranges, all texture descriptors, packed-constant hashes and final
system/fetch-state hashes. Flipping one fixture byte caused its hash check to
fail. Other selected families still have separate fixtures, and this new
fixture has no private identity/depth raster yet.

```powershell
python tools/summarize-snr01-frame-wide-census.py "$base/remainder-fixture-live-a-evidence.log" --source-frame 5000 --require-candidate-boundary --output "$base/remainder-fixture-live-a-ledger.json"
python tools/partition-snr00-gate-a-slice.py "$base/remainder-fixture-live-a-ledger.json"
python tools/verify-snr03-remainder-snapshots.py "$base/remainder-fixture-live-a-evidence.log" "$base/remainder-fixture-live-a-ledger.json" --require-car-title --require-scalar-title
python tools/verify-snr03-remainder-fixture.py "$base/remainder-fixture-live-a/snr03-remainder-5000.bin" "$base/remainder-fixture-live-a-evidence.log" "$base/remainder-fixture-live-a-ledger.json"
```

| Local evidence | SHA-256 |
| --- | --- |
| `remainder-fixture-live-a-evidence.log` | `78E9206B5715BEF9767DA37849253A7054823C04117BE79FA8B346FF3C8CC612` |
| `remainder-fixture-live-a-ledger.json` | `7F2806B162EFCFD175BC88B7F2D9947A0D6E34B2D2A04D5017D597F470C033EE` |
| `remainder-fixture-live-a/snr03-remainder-5000.bin` | `9F7EF77A1D58196D1E6E7BA4A9071C05577600969AA3F3ACA3B729C000BA7BDC` |
