# SNR-02 shared-track geometry handoff — 2026-09-23

## Index state and exact shader inputs

The `SNR02T3` fixture records the host primitive, primitive-restart flag and
guest index endianness alongside the previously verified final draw state.
The source-frame-5000/output-frame-5001 sustained-race replay exited normally
with seven compatibility screenshots. Its independent verifier joined all
**813** selected track draws across **84** title targets, including 813 exact
final states and no unreadable or mutated geometry. Every selected draw uses
host primitive `6` (triangle strip), restart enabled, 16-bit host indices,
guest index endianness `1` (`xenos::Endian::k8in16`) and an index byte length
equal to twice its index count. The frame-wide ledger partitions 4,438 draws:
2,652 selected, 64 retained and 1,722 outside, with none unattributed.

The fixture owns 91 vertex ranges and 204 index ranges, totaling 3,826,930
geometry bytes. The T3 verifier and the older T1/T2 fixtures pass. Extraction
against the validated installed shader pack finds all 20 exact vertex
hash/specialization pairs for this frame, totaling 459,928 DXIL bytes.

| Evidence | SHA-256 |
| --- | --- |
| `.local/native-renderer/snr02/track-index-live-e/snr02-track-5000.bin` | `00EE5217C2AD3933791DB70D69FD5E45743D20BDC627EEF0D2F0577F9E67AC23` |
| `.local/native-renderer/snr02/track-index-live-e-filtered.log` | `486BF907051A64BDCB054444F815D218E0E34E9B0D568486DC4FC5C4EA3F9FDA` |
| `.local/native-renderer/snr02/track-index-live-e-ledger.json` | `8D97C18ED1EEB19D2A70A37612C42BC58734F9537A4606C934A8852AA1F146B5` |
| RelWithDebInfo executable | `936324A4BB4EA0C4296C58937DCA28963AFD37F58A329DC0B1DD80BE0A0F08EE` |

The next private raster must apply the guest `k8in16` index conversion and
restart semantics, then validate vertex fetch and post-VS output against the
compatibility renderer. Mesh/material ownership and pixel parity remain open.

## Exact vertex translations and topology check

`tools/extract-snr04-track-shaders.py` verified the installed 1× native
shader pack (`4308F4259A720679729EC2B71551A8CBE267C13933CEE2EF59A6FFE1A3685F6F`)
with the existing pack verifier and extracted the **20/20** vertex
hash/specialization pairs in the owned frame-5000 fixture. Their exact DXIL
containers total 459,928 bytes. The local manifest at
`.local/native-renderer/snr04/track-shaders-pack-a/manifest.json` has SHA-256
`A5FD3C10A4F38FFFE6D8DCCC6969C5D2199BECC22574D5D533C216B7928FA7A5`;
each extracted file is checked against the pack entry digest. This uses the
actual bytes loaded by the preview, without changing the shader pack or save.

The guest primitive value `6` in every selected draw is **triangle strip**
(`xenos::PrimitiveType::kTriangleStrip`), not triangle list. All 673 selected
index buffers are 16-bit (`length == index_count * 2`). The later T3 capture
records host topology, primitive restart and index endianness directly;
index-count divisibility cannot be used to infer topology.

The preview's shader-capture flag produced zero callbacks in two runs because
that observer is compiled into the producer backend. Reading the already
validated installed pack supplied the exact shader inputs directly.

## Final draw-state follow-up

The opt-in fixture now uses `SNR02T2`: each track draw owns its shader
specialization, mapped vertex-constant bitmap and packed words, plus the
final system and fetch-47 words. At the post-bind callback, the capture
compares those packed words with both the final guest registers and the
bytes actually bound to the GPU vertex constant buffer. Any mismatch or
missing final callback rejects the whole frame.

The frame-5000 sustained-race replay exited normally with seven compatibility
screenshots. The independent fixture verifier joined **all 673** selected
track draws across **89** title targets, with 673 matching final states, no
unreadable or mutated geometry and no bound-constant mismatch. The frame-wide
census partition passed 4,002 draws: 2,272 selected, 58 retained and 1,672
outside; none unattributed. The fixture contains 96 vertex ranges and 215
index ranges, totaling 4,119,012 owned geometry bytes. A one-byte mutation
was rejected by the verifier. This frame had 20 distinct vertex
shader/specialization pairs and 42 pixel shaders; all index draws used the
same host index format.

| Evidence | SHA-256 |
| --- | --- |
| `.local/native-renderer/snr02/track-final-live-d/snr02-track-5000.bin` | `7EC3B598E520C8D16CF19089D7AE684908B322DEE5AB49F432424CEE7891E675` |
| `.local/native-renderer/snr02/track-final-live-d-filtered.log` | `D6EBE3C083E00D5D6887CFDC774989BAA08A1B4296471CF1F0602E43DF8FAAA0` |
| `.local/native-renderer/snr02/track-final-live-d-ledger.json` | `EDB6A61C9F5F3AF60D3CF79C827D213E8126EBCD0F6C47336EF1FEE1F013D003` |
| RelWithDebInfo executable | `7871A1BD1C8AC822C13019EDCEF3C6033EAC8371C1F2E3904C3A5452D860E062` |

One preceding replay exited at source frame 5,631, before the requested
frame 6,000; it wrote no track fixture. The render-test script's capture
steps and the title source counter are distinct. The accepted 5,000/5,001
window is recorded explicitly rather than treating that short run as a
capture failure or a same-frame match.

The fixture still lacks semantic material ownership, live texture content and
pixel state. No private track raster exists yet. The exact vertex bytecode and
host index state were obtained in the later checks above; vertex-fetch
interpretation still needs validation before comparing coverage or depth.

## Initial geometry handoff

The selected view-8 shared-track producer is now identified before GPU draw
preparation by its title scene-list flush caller `0x824170BC` and exact command
buffer target. A default-off `--pinyon_shift_snr02_track_payload_probe=true`
requests CPU snapshots only for those targets in backend frame `source + 1`.
The SDK copies the guest vertex fetch and DMA index ranges at preparation;
the title observer owns each distinct byte range, rejects a changed reuse,
and publishes a bounded `SNR02T1` fixture at the matching output frame.
Compatibility rendering remains untouched. This is a geometry handoff, not
material reconstruction or native raster coverage.

The AppData-backed sustained-race replay used source frame 6000, the existing
full-census flags, and the new probe. It exited normally with seven
compatibility screenshots. The candidate-boundary census passed 3,516
prepared draws. The independent `verify-snr02-track-geometry.py` join passed
all **733** selected track draws across **91** title targets; no target had an
unselected draw. It matched every owned range to the prepared-draw hash:

| Captured geometry | Distinct ranges | Repeated draw bytes | Owned bytes | Changed reused ranges |
| --- | ---: | ---: | ---: | ---: |
| Vertex | 95 | 61,027,072 | 4,145,650 | 0 |
| DMA index | 233 | 1,395,058 | 531,264 | 0 |

The 4,721,110-byte fixture contains title camera words, the 91 target
addresses, ordered draw identities and shader hashes, and owned vertex/index
bytes. The root capture is capped at 4,096 draws and 8 MiB of distinct
geometry. The SDK's opt-in copy work is capped at 64 MiB per GPU command
thread, with 512 KiB per vertex range and 64 KiB per index range. Failure,
overflow, missing title camera, unmatched target or mutated range rejects
the entire fixture. A one-byte fixture corruption was rejected by the
verifier.

| Evidence | SHA-256 |
| --- | --- |
| `.local/native-renderer/snr02/track-owned-live-b/snr02-track-6000.bin` | `83CDDD756A1971FC6C50ABADE018921E08BA340446B00F3FAC43A4EE2058373E` |
| `.local/native-renderer/snr02/track-owned-live-b-filtered.log` | `19E0F30875C512BD70CA14B72C368E05A87C0D5D5FDEC3D7C50046A904159094` |
| `.local/native-renderer/snr02/track-owned-live-b-ledger.json` | `73E6620D295F6F565B8DAA1CC6EFFB89CB68A7E2A3D0AEF142B12B02930046BFE` |
| RelWithDebInfo executable | `9FF3352882B3C74EA11D350BC4AA3639DBAFB8F9B233CCC189FAE4F74F9D0288` |

An earlier hash-only replay independently passed 744 selected draws, 90
title targets, 94 vertex ranges and 229 index ranges, again with no unreadable
or mutated selected range. Its filtered log and ledger are under
`.local/native-renderer/snr02/track-geometry-live-a*`.

This does **not** close SNR-02/03/04. The title descriptor is a cached
command-list container; the mesh/submesh/material owner and resource lifetime
still need title-side proof. The initial `SNR02T1` fixture did not own final
constants; `SNR02T2` now does. Texture roles and shader bytecode remain
unowned, and there is no track diagnostic raster.
The full frame-role partition reports 2,005 selected, 76 retained and 1,435
outside-candidate draws with `full_owner_census=true`. Its first pass flagged
two late direct-root draws, ordinals 3419–3420. The title's clear producer
record `62825` spans a command-buffer refill: its post-refill end cursor is
`319914588`, and both draw packets fall between the new root buffer start
`319914400` and that end. The bounded refill join assigns both to this
source-frame-6000 clear. The revised ledger is
`.local/native-renderer/snr02/track-owned-live-b-refill-ledger.json`
(SHA-256 `EF58F8CF2E632AA1F956FC3F1BE8D82D29D8E4C4F14B9DC74A1AD96A71CFD2E5`).
The prior 2,670-draw control ledger's classifications did not change.

Next: connect cached track command targets to actual mesh/material ownership,
capture the exact vertex translations and extend this fixture to a private
full-resolution identity/depth diagnostic.
