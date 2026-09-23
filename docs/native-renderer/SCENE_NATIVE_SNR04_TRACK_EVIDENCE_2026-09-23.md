# SNR-04 shared-track private diagnostic — 2026-09-23

## Final-state and EDRAM-tile follow-up

A second AppData-backed source-frame-5000/output-frame-5001 replay enabled the
clear-producer trace and captured the final backend raster state for every
selected track draw. The `SNR02T4` fixture adds the raw cull/front-face,
clip and normalized depth controls and the actual D3D12 viewport and scissor
at the final draw boundary. The independent fixture/log verifier passed
**624/624** selected draws across **90** title targets, with 94 owned vertex
ranges, 225 index ranges, no failed snapshots and no mutated reused range.
The strict frame-wide candidate-boundary census also passed: 3,718 backend
draws were classified, including the clear-producer direct-root boundary
unresolved in the earlier capture. This does not classify a new route or mode.

The captured viewport/scissor groups reveal three ordered EDRAM passes:
121 draws use a 720-row viewport and 256-row scissor, 343 draws use a
464-row viewport and 256-row scissor, and 160 draws use a 208-row viewport
and 208-row scissor. These are the 0–255, 256–511 and 512–719 portions of
the 720-row scene. The private diagnostic preserves each draw's captured
vertex-system constants, viewport, culling, depth function and depth write,
then translates the viewport and scissor by 0, 256 or 512 rows to assemble
one full-resolution private image. It rejects any other tile geometry rather
than silently applying this race-specific mapping. This also explains why
applying the captured scissor without tile rebasing covered only the top
327,680 pixels.

The rebased diagnostic dispatched all 624 draws; 138 contributed final pixels
and 700,053 of 921,600 pixels have an identity and finite nonzero depth.
Coverage by row group is 327,680/327,680, 310,842/327,680 and
61,531/266,240 respectively. Two runs produced byte-identical identity,
depth and summary outputs. A T3 fixture still reproduces its earlier
781,818-pixel result, and a mismatched shader manifest is rejected. The
private false-color image remains visibly unlike the paired compatibility
frame. The diagnostic still uses an identity pixel shader rather than the
title's materials and textures, does not apply stencil or polygon offset,
and omits the other selected scene contributions. The top group is almost
entirely overwritten by one track draw. No material, visibility or full-slice
parity is claimed; SNR-02 and SNR-04 remain open.

To reproduce the final-state diagnostic from this local capture:

```powershell
$fixture = '.local/native-renderer/snr04/track-raster-state-live-d/snr02-track-5000.bin'
$pack = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview\cache\shaders\shareable\4D5309C9.fh1-native-v2.10DE.09.1x1.pnsp'
$shaders = '.local/native-renderer/snr04/track-raster-state-shaders-d'
python tools/extract-snr04-track-shaders.py $fixture $pack $shaders
python tools/summarize-snr01-frame-wide-census.py .local/native-renderer/snr04/track-raster-state-live-d-filtered.log --source-frame 5000 --require-candidate-boundary --output .local/native-renderer/snr04/track-raster-state-live-d-ledger.json
python tools/verify-snr02-track-geometry.py .local/native-renderer/snr04/track-raster-state-live-d-filtered.log .local/native-renderer/snr04/track-raster-state-live-d-ledger.json $fixture
& out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe $fixture $shaders .local/native-renderer/snr04/track-raster-state-diagnostic-rebased
```

| Final-state evidence | SHA-256 |
| --- | --- |
| `track-raster-state-live-d/snr02-track-5000.bin` | `CCDB5BC0E482C8ACA91140BA5EEBD6CBCFC9B410F150B5EF1F25FA5F1D8F783A` |
| `track-raster-state-live-d/track-source-5000.ppm` | `6E1C8F8667E037755ECFEB587AB69FBE590AD24D54E36ABC994D800620407981` |
| `track-raster-state-shaders-d/manifest.sha256` | `18632DB27FF3B188AF9DE195403C54BD18DC766FE33A031D265D328B52553761` |
| `track-raster-state-diagnostic-rebased/identity.ppm` | `6B244CDC6A74208D0BA0CCA346B6CD4373C01FCB0C4D94145573B6D8A56B88CC` |
| `track-raster-state-diagnostic-rebased/depth.f32` | `A682D83FC2D9043F813C05F9D9E03114ED42A87D65D0C29D6EA917ED22D7B2EF` |

## Initial raw-geometry raster

The default-off standalone SNR-04 diagnostic now accepts an owned `SNR02T3`
shared-track scene. It verifies the fixture bounds and ordered draws, matches
the exact 20 vertex hash/specialization pairs to shader files and SHA-256
digests extracted from the validated installed pack, and renders every owned
draw into private 1280×720 identity and depth targets. It binds the **raw**
16-bit guest index bytes as a triangle strip with `0xFFFF` restart; the exact
translated vertex shader applies `k8in16` through the captured system constant.
Each draw has its own captured packed vertex constants, system constants and
rebased fetch constant. The private pixel shader writes an ordinal identity.
This diagnostic never replaces or presents game output.

To reproduce the offline diagnostic after a validated capture:

```powershell
$fixture = '.local/native-renderer/snr04/track-frame-reference-live-c/snr02-track-5000.bin'
$pack = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview\cache\shaders\shareable\4D5309C9.fh1-native-v2.10DE.09.1x1.pnsp'
$shaders = '.local/native-renderer/snr04/track-frame-reference-shaders-c'
python tools/extract-snr04-track-shaders.py $fixture $pack $shaders
& out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe $fixture $shaders .local/native-renderer/snr04/track-frame-reference-diagnostic-c
```

The AppData-backed sustained-race route added `capture 5000 track-source-5000`
between the existing moving and sustained captures. The corpus-enabled replay
exited normally with eight compatibility screenshots and wrote the track
fixture at output frame 5001 for title source frame 5000. The independent
fixture verifier joined **all 591 selected track draws** across **86 title
targets**, with 591 final bound states, no failed geometry snapshots and no
mutated reused range. The fixture owns 90 vertex ranges and 219 index ranges,
totaling 4,289,808 bytes. The private diagnostic dispatched all 591 draws;
99 contributed final pixels, for 781,818 covered pixels. A second offline run
produced byte-identical identity and depth files. A different fixture's shader
manifest was rejected before rendering.

| Paired evidence | SHA-256 |
| --- | --- |
| `.local/native-renderer/snr04/track-frame-reference-live-c/snr02-track-5000.bin` | `15743438527CC2BEBD6D9668FDF16F9A7E7A4EFCDAE2D07D12C28487C5857951` |
| `.local/native-renderer/snr04/track-frame-reference-live-c/track-source-5000.ppm` | `CD521BBEEC95C9A761568BC59707567076CC1AB2E35FD03D414DF1244847E4B9` |
| `.local/native-renderer/snr04/track-frame-reference-diagnostic-c/identity.ppm` | `6973B55DDFBC9E6A29CEB64F1CA06720517EE032C1B09D754FC164D41BE35A0D` |
| `.local/native-renderer/snr04/track-frame-reference-diagnostic-c/depth.f32` | `89189AB0056D04414305DE443348A9FB8C8176810D4531E2A85DE952337F48ED` |
| `.local/native-renderer/snr04/track-frame-reference-shaders-c/manifest.sha256` | `8B1DDE6D376F5DC3CD133C945058376BC56C6F76FEA6F311A08A1A908D3B5BB7` |
| Local route `.local/native-renderer/snr04/track-frame-reference.fh1test` | `BEE98F970396E518324DFE6E3F64D86465BB71471CD4EF19EBBBCBB27C428BF7` |

The paired compatibility image and false-colored identity output do **not**
establish pixel parity. The diagnostic currently forces no culling, a
greater-equal depth test/write, a full-window scissor and a 0–0.5 depth
viewport; it lacks the final per-draw raster state, alpha testing and retained
passes. Its projected visible shapes differ substantially from the reference.
The result proves the owned geometry/shader ABI can produce a bounded raster,
not that this subset can be admitted as a faithful scene contribution.

The initial frame-wide ledger counted 3,593 backend draws and the selected-track join
passed, but the strict candidate-boundary check did **not** pass: ordinal 1467
is an unclassified direct-root rectangle draw on a candidate target. This
replay omitted the clear-producer trace needed to prove its title owner. The
final-state replay above resolved this boundary and captured viewport,
scissor, cull/front-face and depth state. Stencil state remains open.
Material/resource lifetime and complete selected-slice coverage remain open.

Validation: standalone and game RelWithDebInfo builds; T3 fixture verifier
591/591; 20/20 shader extraction; deterministic private identity/depth rerun;
mismatched manifest rejection. SNR-04 and Gate A remain open.
