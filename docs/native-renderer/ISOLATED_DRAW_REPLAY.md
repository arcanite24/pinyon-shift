# Isolated authentic draw replay

NR-02E begins with a one-shot replay at the synchronous prepared-draw point.
The D3D12 backend duplicates one exact, title-qualified indexed draw into
private depth and color targets. It then restores the guest targets and records
the original draw normally. The isolated target is never presented and Xenos
remains authoritative for the displayed frame.

## Ownership and safety gates

The path is disabled unless the native-renderer census and an exact 16-digit
candidate signature are both supplied. Pinyon requests a draw only when the
live observation still satisfies the qualified candidate boundary:

- direct DMA indexed geometry with supported index format and endianness;
- one vertex allocation and one through four fully observed textures;
- no observer overflow, memexport, query, or resolved-target dependency;
- active host rasterization; and
- exactly one depth target and the first color target.

ReXGlue independently requires host render targets, rasterization, no
memexport, and a direct guest DMA index buffer. It creates private clones with
the same dimensions, formats, and sample count as the live targets, clears
them, records the duplicate draw with the already prepared PSO and immutable
bindings, and rebinds the guest targets before the original draw. The API has
no suppression operation, and failure records an explicit result while the
guest draw continues.

## Qualification run

Launch the installed AppData save with:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -IsolatedDrawSignature 747837906D0BF484 `
  -Json
```

The expected result is one `native_renderer.isolated_draw.result` event with
`status=recorded`, non-zero target dimensions, `native_draw=isolated_only`,
`xenos_draw=preserved`, `output_authority=xenos`, and
`suppression_eligible=false`. The displayed game must remain visually
unchanged and the process must exit normally without device-loss, validation,
or resource-state errors.

The qualifying AppData-backed run completed on 2026-08-28 as session
`20260828T094158Z-p42200`. The exact signature was recorded once at frame
3553, draw 116, into a 640 by 8192 private target. The guest output remained
visually unchanged, census frames continued through frame 5700, and the
process exited normally with code zero. The structured log contained no fatal,
device-loss, D3D12 error, exception, access-violation, or crash events.

This milestone proves authentic GPU draw recording and target isolation. A
later NR-02E pull request must add asynchronous readback and image comparison
before visual equivalence is claimed.
