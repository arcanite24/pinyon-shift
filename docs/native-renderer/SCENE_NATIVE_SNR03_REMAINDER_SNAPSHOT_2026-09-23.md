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

Next, publish exact title-linked immutable records for these families, retain
the verified bytes and final bound state in an owned fixture, reconstruct the
108 host-converted index submissions, and render all 883 draws into the same
private identity/depth target as the other selected families.
