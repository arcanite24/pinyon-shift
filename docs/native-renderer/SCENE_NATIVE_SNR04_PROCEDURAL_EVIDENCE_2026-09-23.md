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
