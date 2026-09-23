# SNR-02 shared-track geometry handoff — 2026-09-23

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
still need title-side proof. The fixture does not yet own final constants,
texture roles or shader bytecode, and there is no track diagnostic raster.
The full frame-role partition reports 2,005 selected, 76 retained and 1,435
outside-candidate draws. It flags **two** of the latter as unattributed direct
roots, ordinals 3419–3420, and `full_owner_census=false`. They share root
command buffer `319914400`, which was linked from a title view-0 command in
source frame 6000 and executed in backend frame 6001. That proves a buffer
handoff, but not the producers of its two draw packets. The partition tool
now reports this gap explicitly; the candidate-boundary verifier alone does
not prove the entire remaining-draw census.

Next: resolve those direct-root producers, connect cached track command
targets to actual mesh/material ownership, then extend this exact-frame
fixture with final draw state and private full-resolution identity/depth.
