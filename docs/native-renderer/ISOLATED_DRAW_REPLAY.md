# Isolated authentic draw replay

NR-02E begins with a one-shot replay at the synchronous prepared-draw point.
The D3D12 backend duplicates one exact, title-qualified draw into private depth
and color targets. The initial path supports direct DMA indexed geometry; the
qualified NR-02F follower also supports the prepared AutoIndex path. It then
restores the guest targets and records the original draw normally. The isolated
target is never presented and Xenos remains authoritative for the displayed
frame.

## Ownership and safety gates

The path is disabled unless the native-renderer census and either an exact
16-digit candidate signature or the startup-only fresh-candidate auto-selector
are supplied. Pinyon requests a draw only when the live observation still
satisfies the qualified candidate boundary:

- direct DMA indexed geometry with supported index format and endianness, or
  the exact non-indexed AutoIndex follower contract;
- one vertex allocation and one through four fully observed textures;
- no observer overflow, memexport, query, or resolved-target dependency;
- active host rasterization; and
- exactly one depth target and the first color target.

Semantic world candidates can add a stricter, fail-closed admission gate with
`-RequireFreshVisibilityCandidate`. In that mode, the exact prepared draw must
also carry a selected game visibility decision from the current or immediately
preceding frame through the semantic submission and physical PM4 lineage. A
missing, rejected, stale, future, or table-overflow decision cannot issue the
isolated native draw. An early matching signature without a fresh decision is
reported once and remains armed for a later fresh occurrence; it is not a
terminal rejection. The exact-signature and mechanical gates remain required.

For discovery captures, `-AutoSelectFreshVisibilityCandidate` waits for the
first prepared draw that passes both the mechanical boundary and the fresh
visibility gate, locks its exact prepared signature, and captures
only that signature from then on. It is mutually exclusive with an explicit
signature, retained-pass capture, and sky/horizon suppression. A rejected,
missing, stale, future, or mechanically unsupported observation cannot lock
the selector or issue native work.

ReXGlue independently requires host render targets, rasterization, and no
memexport. Indexed requests require a direct guest DMA index buffer; AutoIndex
requests use the already prepared host vertex count. It creates private clones
with the same dimensions, formats, and sample count as the live targets,
records the duplicate draw with the already prepared PSO and immutable
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

For a visibility-selected semantic candidate, add:

```powershell
  -RequireFreshVisibilityCandidate
```

To avoid a separate discovery run, capture the first admissible semantic world
draw and its paired native/Xenos color and depth evidence with:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -AutoSelectFreshVisibilityCandidate `
  -IsolatedDrawDir .local\qualification\native-visible-world-auto `
  -Json
```

This option is intended for semantic world bring-up and is not used by the
already-qualified sky/horizon replay family.

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

This milestone proves authentic GPU draw recording and target isolation.
Single-draw and retained-pass captures asynchronously write paired native and
authoritative Xenos color/depth artifacts for later image comparison; a
successful replay is not by itself a claim of visual equivalence.
