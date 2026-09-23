# SNR-04 procedural identity/depth diagnostic — 2026-09-23

An opt-in private D3D12 diagnostic now consumes the immutable `SNR02I3`
procedural-item fixture at the source-frame 6000/output-frame 6001 handoff.
It verifies the four captured vertex bytecodes by SHA-256, packs only their
live vertex-register bitmaps, replays every owned draw in sequence, and writes
1280×720 item identity and floating-point depth. It uses the captured vertex
bytes, fetch state and system constants; no mutable guest-memory read or
compatibility draw suppression occurs in this path. The pixel shader encodes
item identity and deliberately ignores material textures and alpha testing.

The AppData-backed sustained-race replay exited normally with seven
compatibility screenshots. Its strict frame-wide census passed 3,184 draws:
1,789 selected, 70 retained and 1,325 outside the pilot slice. The independent
`verify-snr02-item-scene.py` join passed all 174 procedural calls and 312 final
draws, including their vertex bytes, shader identity, mapped registers, system
state and fetch state. The private diagnostic covered 63,015 pixels; 107 items
were visible after depth testing. Running the standalone executable against
the saved fixture produced byte-identical `identity.ppm` and `depth.f32`.

| Evidence | Local path | SHA-256 |
| --- | --- | --- |
| Owned fixture | `.local/native-renderer/snr04/procedural-live-a/snr02-items-6000.bin` | `B8460BCDB3582E38F1AE893E8CE39D203D7A3D8C1293DB2F5C2A7A0CA5A7B1D2` |
| Filtered run log | `.local/native-renderer/snr04/procedural-live-a-filtered.log` | `E66198C77C673B9E9C19B55B50CC5EA6A188D34AE19917BB02987FEF3C344E68` |
| Strict ledger | `.local/native-renderer/snr04/procedural-live-a-ledger.json` | `8D7B97036F9F084810354DF079241C1E56C38EEA3B4791DEB50B27D54FBEAA0B` |
| Identity image | `.local/native-renderer/snr04/procedural-live-a/snr04-procedural-6000/identity.ppm` | `CE8F5820ABEB4747DCBFE5686D1FA4FF382148AC7F42F61A80E058707F7FB0C7` |
| Depth image | `.local/native-renderer/snr04/procedural-live-a/snr04-procedural-6000/depth.f32` | `4B32F40D3CD635E97008EA994AD71CF7F2A6F86A22E9C51B99F86F6A4133210B` |

The diagnostic is enabled only with `PINYON_SHIFT_SNR04_PROCEDURAL_VS_DIR`
pointing to the four exact captured `vertex_*.dxil` files, along with the
existing source-frame 6000 item probe. The standalone executable also accepts
an `SNR02I3` fixture, shader directory and output directory. Its viewport
conversion, guest quad expansion and reverse-depth state are checked against
the captured draw fields. The output is a geometry/ABI check, not a faithful
render: alpha masks, material bindings, texture generations, other selected
families, compatibility attachment pixel parity and retained-pass bridges
remain unproved. Source frame 6000's compatibility color/depth attachments
were not captured as pixel-aligned references in this replay. Gate A remains
open until the entire selected slice is covered and compared on the same frame.

## Post-VS and bound-constant follow-up

The private diagnostic now also stream-outputs each draw's original-viewport
`SV_Position` before its separate normalized identity/depth raster pass. An
extended-route replay published 178 items and 262 draws; the strict frame
census passed 2,670 prepared draws and the independent fixture join passed.
All 262 selected draws had identical prepared registers, final registers and
the **packed bytes actually bound to the GPU vertex constant buffer**. Its
1,335,296-byte `postvs.f32x4`, identity and depth files were each byte-identical
between the live borrowed-device diagnostic and a separate offline run.

| Evidence | Local path | SHA-256 |
| --- | --- | --- |
| Owned fixture | `.local/native-renderer/snr04/procedural-bound-live-b/snr02-items-6000.bin` | `3437B2DB1E33929E9229D63C71C701B5AEC0767EA32CB6155DAC3A09F1564244` |
| Filtered log | `.local/native-renderer/snr04/procedural-bound-live-b-filtered.log` | `5EA45591F48E296DBEDC15B9D26F9D150C6E68CFAF1D77C3204819929703EADE` |
| Strict ledger | `.local/native-renderer/snr04/procedural-bound-live-b-ledger.json` | `DF6233867FCE5D827410D390E95EDA6ED3A72E93085CFEEB09FC5EB4A05B25FB` |
| Private post-VS | `.local/native-renderer/snr04/procedural-bound-live-b/snr04-procedural-6000/postvs.f32x4` | `D5160150C3E4ECAF50C637724757AC42C8A778A6C82A72127852AB6D53D07A8B` |

A separate RenderDoc run probed a fixture with 181 items and 273 selected
draws. The capture has 238 actions using ShiftGlue's replacement
`fh1_layered_scene_vs` for guest shader `3BC346726C1C2535`, plus 9, 12 and
14 actions using the other three captured guest bytecodes. This exactly
matches that fixture's shader/count distribution, but **none** of the 273
captured post-VS position streams matched the private fixture byte for byte.
One captured draw had the same 64 system words but 30 different packed vertex
words from a same-count fixture draw. The files named `frame6000` and
`frame6002` both contain full scene work; `frame6001` contains almost none.
The captured actions are not yet joined to fixture draw sequences or a
verified source-frame boundary, so the mismatch cannot be attributed to
shader math or stale scene publication. The comparison is recorded at
`.local/native-renderer/snr04/procedural-marker-comparison-6002.json`
(SHA-256 `7DB6505D5D87136F7FF214823E4DF28DFFA109CBBFDEACDBCA4E4C27B0BE15AB`).
`tools/probe-snr04-renderdoc-procedural.py` and
`tools/check-snr04-procedural-capture.py` reproduce the export and exact
comparison; a sequence- or attachment-matched compatibility capture is the
next parity requirement. The bound-byte check supports the owned fixture in
its own replay; it does not retroactively align the separate RenderDoc run.

Moving the shared final-state callback after binding was also checked with
the source-frame 6000 vegetation probe. It published a 445,968-byte scene
fixture and rendered 127 private draws; its live identity, depth and post-VS
files were each byte-identical to an offline replay of that fixture.
