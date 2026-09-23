# Procedural-character same-frame handoff — 2026-09-23

The sustained-race source-frame-5000 replay now owns the view-8
`0x8245AB88` procedural-character packets through output frame 5001. Seven
title items produced ten selected backend draws. The `SNR03C1` fixture
contains each title record, vertex descriptor and packet, 14,224 copied
vertex bytes, prepared vertex constants and shader identities, and the final
bound system/fetch constants, raster/depth state, viewport and scissor for
each ordered draw. A missing, changed or duplicate draw rejects publication.
The SDK's final-state observer now includes the character vertex shader so
these states can be joined to the title-owned packets.

This run passed the strict 4,508-draw frame ledger with no unattributed
draws. The fail-closed partition selected 2,662 draws: 817 shared track,
122 procedural item, 120 vegetation, ten procedural character, 1,067 car
scene-list, 410 character-manager, 44 animated-scene, and 72 car-presentation.
The first four families have owned fixtures for **1,069/2,662** selected
draws in this frame. Track, item, vegetation and character fixture verifiers
all passed against the same evidence log and ledger. The character fixture
has no private raster yet; no material, texture-generation, depth or visible
coverage parity is claimed. In particular, the character-manager's 410
direct draws are a separate family, not covered by these ten packets.

Reproduce the checks from the local capture:

```powershell
$base = '.local/native-renderer/snr04'
python tools/summarize-snr01-frame-wide-census.py "$base/character-scene-live-d-evidence.log" --source-frame 5000 --require-candidate-boundary --output "$base/character-scene-live-d-ledger.json"
python tools/partition-snr00-gate-a-slice.py "$base/character-scene-live-d-ledger.json"
python tools/verify-snr02-track-geometry.py "$base/character-scene-live-d-evidence.log" "$base/character-scene-live-d-ledger.json" "$base/character-scene-live-d/snr02-track-5000.bin"
python tools/verify-snr02-item-scene.py "$base/character-scene-live-d/snr02-items-5000.bin" "$base/character-scene-live-d-evidence.log" "$base/character-scene-live-d-ledger.json"
python tools/verify-snr03-vegetation-publication.py "$base/character-scene-live-d-evidence.log" "$base/character-scene-live-d-ledger.json" --source-frame 5000
python tools/verify-snr03-scene-fixture.py "$base/character-scene-live-d/snr03-scene-5000.bin" "$base/character-scene-live-d-evidence.log"
python tools/verify-snr03-character-fixture.py "$base/character-scene-live-d/snr03-characters-5000.bin" "$base/character-scene-live-d-evidence.log" "$base/character-scene-live-d-ledger.json"
```

| Evidence | SHA-256 |
| --- | --- |
| `character-scene-live-d-evidence.log` | `3C69BF14BC38943D9AB7E629A9A01D7DDC9E965B470C50144E1242442C57C79C` |
| `character-scene-live-d-ledger.json` | `ABFEFD29A2A1FC2E335DD53A7274364076BC75B4E6CE3A22024B2C423F2A53E9` |
| `character-scene-live-d/snr03-characters-5000.bin` | `836628EEA5297243A68FE88D6A87782686B166D66471B36BD1837FB238048263` |

Next, render this fixture through the private identity/depth diagnostic. The
larger uncovered contributions need their own exact multi-stream geometry and
resource generations before a composed selected-slice diagnostic can close
Gate A.
