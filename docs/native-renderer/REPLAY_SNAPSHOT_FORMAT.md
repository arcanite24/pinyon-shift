# Native replay snapshot format

NR-02E starts from an immutable, exact-signature local snapshot. This capture
freezes the selected draw's bounded payloads and shader inputs at the
synchronous prepared-draw point; it does not upload them, create a native PSO,
submit a native draw, or suppress Xenos work.

## Capture boundary

The capture is armed only when both a 16-digit candidate signature and a new
output directory below the repository's ignored `.local` tree are supplied.
It attempts the signature once per process and rejects the draw before any
payload read unless all of these conditions hold:

- direct DMA indexed geometry with supported format and endianness;
- exactly one bounded vertex allocation, at most 64 MiB;
- at most 1,048,576 indices and 4 MiB of index payload;
- one through four textures, at most 16 MiB each and 32 MiB total;
- every payload range contained in the guest physical aperture;
- complete constant, texture, vertex, and prepared-pipeline observations;
- no query, memexport, observer overflow, or observed resolve dependency; and
- active host rasterization with a bound color target.

After validation, the hook copies every payload into host memory before doing
file I/O. It then writes a staging directory and renames it to the requested
destination only after the manifest is complete. Existing output or staging
directories are never overwritten.

## Local artifact

Arm a capture against the AppData save with:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -ReplaySnapshotSignature 747837906D0BF484 `
  -ReplaySnapshotDir .\.local\native-renderer\replay\747837906D0BF484
```

The resulting `snapshot.json` uses schema
`pinyon-shift.native-replay-snapshot.v1`. It identifies the exact shader
specializations and prepared pipeline, records the current constant and
texture-instruction values, and describes these local payload files:

- `index.bin`: raw guest index data;
- `vertex.bin`: the complete bounded vertex allocation;
- `texture_XX_base.bin`: each bounded base texture allocation; and
- `texture_XX_mip.bin`: an optional separate mip allocation.

Every payload entry includes its byte count and FNV-1a hash. Addresses remain
diagnostic only and may relocate between processes. The output is local game
data and must never be committed or uploaded.

## Offline validation

Join the snapshot with the already qualified contracts before isolated upload:

```powershell
python .\tools\validate-native-replay-snapshot.py `
  .\.local\native-renderer\replay\747837906D0BF484 `
  .\.local\native-renderer\candidate\747837906D0BF484-geometry.json `
  .\.local\native-renderer\candidate\747837906D0BF484-draw-state.json `
  .\.local\native-renderer\candidate\747837906D0BF484-texture-provenance.json `
  .\.local\native-renderer\candidate\747837906D0BF484-pso.json
```

The validator rejects path traversal, missing or changed payloads, signature
or PSO mismatches, unstable texture content, unbounded geometry, and any input
that permits native upload, drawing, or suppression. Success means only
`ready_for_isolated_upload`; Xenos authority remains mandatory.

## Local qualification

The implementation was qualified on 2026-08-28 against the installed 0.1.0
AppData save and prepared candidate `747837906D0BF484`. Session
`20260828T090906Z-p43812` captured exactly once at frame 3996, draw 115:

- 37,200 bytes of index data (9,300 32-bit indices);
- 51,744 bytes of vertex data; and
- two 16,384-byte texture resources (32,768 bytes total).

The offline validator joined the snapshot to all four candidate contracts and
reported `ready_for_isolated_upload: true`, `native_draw: false`,
`suppression_allowed: false`, and `xenos_authority: true`. The preview then
exited normally with code 0 and no error events in the session log.
