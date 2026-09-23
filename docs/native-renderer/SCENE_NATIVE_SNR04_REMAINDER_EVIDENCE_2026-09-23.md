# SNR-04 remaining-family private diagnostic

The `SNR03R2` source-frame-5000 fixture owns all 880 selected car scene-list,
animated-scene and car-presentation draws in its strict replay (814 / 12 /
54). The frame-wide census attributes all 3,888 backend draws, selects 2,192
across Gate A families and leaves no draw unattributed. The fixture verifier
checks title records, source bytes, texture descriptors, packed constants,
final fetch/system state and the host-converted index rule. The remainder
diagnostic replays those 880 draws into a private 1280×720 identity/depth
target without changing compatibility rendering.

The diagnostic loads 69 exact vertex translations from the validated native
shader pack and rejects a manifest for any other fixture. It compacts 290
captured vertex ranges into 6,864,064 bytes and rebases only the fetches used
by each draw. Raw guest DMA indices stay byte-for-byte unchanged. For the 108
host-converted 32-bit strips, it applies the SDK's guest-endian 24-bit mask
and maps 5,776 restart markers to `0xFFFFFFFF`; the translated shader still
performs its `k8in32` swap. Each draw uses its captured primitive, strip-cut,
viewport/scissor EDRAM tile, cull, clip and depth state. An identity pixel
shader deliberately excludes material color and texture sampling.

The private target covers 136,308 pixels, with 61 visible draw identities.
Its output contains 63,702 colored pixels with zero depth, mostly from the
car-presentation family; the depth file remains finite and in `[0, 1]` for
every colored pixel. Two independent runs produced byte-identical identity,
depth and summary files. The manager and track diagnostics still produced
33,307 and 700,053 pixels after this change. The full selected slice is not
yet on one private target, and this is not material or compatibility parity.

```powershell
$base = '.local/native-renderer/snr04'
$fixture = "$base/remainder-index-live-b/snr03-remainder-5000.bin"
$pack = Join-Path $env:LOCALAPPDATA 'PinyonShift\source\0.1.0\.local\preview\cache\shaders\shareable\4D5309C9.fh1-native-v2.10DE.09.1x1.pnsp'
$shaders = "$base/remainder-index-shaders-b"
python tools/extract-snr04-remainder-shaders.py $fixture "$base/remainder-index-live-b-evidence.log" "$base/remainder-index-live-b-ledger.json" $pack $shaders
& out/build/win-amd64-relwithdebinfo/pinyon_shift_snr04_owned_scene_diagnostic.exe $fixture $shaders "$base/remainder-index-diagnostic-b"
```

| Local evidence | SHA-256 |
| --- | --- |
| `remainder-index-shaders-b/manifest.sha256` | `454F1AD4004F4AB2E7ABD5690C1CC9A32D046A0F39823F9896EF8208151D429B` |
| `remainder-index-diagnostic-b/identity.ppm` | `65DDB4CB9ADD09E4E25210D8927FBD67DB3E8A829E6671A337BB3AC6DB2EA432` |
| `remainder-index-diagnostic-b/depth.f32` | `644DA46CEF24E4A9107EE8B2BD2E7B44292B7CE28BA59E6AB24E4F6156E41F70` |
| `remainder-index-diagnostic-b/summary.json` | `115261C1499B0A71A012120CB12FDCBB5649DAAADCBE636738FB08700FF51901` |
