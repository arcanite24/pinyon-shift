# Candidate pass inventory

NR-02F must replay a complete target phase, not merely every occurrence of an
already-qualified draw signature. The pass inventory derives those boundaries
from a RenderDoc capture before any multi-draw runtime path is enabled.

## Safety boundary

`tools/export-native-renderer-pass-trace.ps1` runs the bundled Python script
through an official, Authenticode-valid qrenderdoc executable. Both the input
capture and output report must remain below `.local`. The trace contains only
event IDs, draw counts, target resource IDs and descriptions, and boundary
kinds. It does not export images, buffers, textures, shaders, or other game
payloads.

The offline builder ignores native isolated-replay draws and groups only the
authoritative Xenos draws. A new phase begins after a clear, copy, resolve,
present, or dispatch boundary, or when the bound color/depth target tuple
changes. Every phase is metadata-only and explicitly suppression-ineligible.

Run:

```powershell
.\tools\export-native-renderer-pass-trace.ps1 `
  -Capture '.local\qualification\renderdoc-reference\reference_frame1.rdc' `
  -RenderDocRoot '.local\tools\renderdoc\RenderDoc_64' `
  -Output '.local\qualification\native-renderer-pass-trace.json'

python .\tools\build-native-renderer-pass-inventory.py `
  .local\qualification\native-renderer-pass-trace.json `
  --output .local\qualification\native-renderer-pass-inventory.json
```

## Qualified discovery result

The 2026-08-28 `open_world_day` RenderDoc frame used for the NR-02E exact
comparison contains 1,582 authoritative Xenos draws across 412 target phases.
The builder ignored six injected native replay draws and found all six marked
authoritative occurrences of candidate `747837906D0BF484`.

Each occurrence begins a two-draw phase on the same 640 by 8,192
`R16G16B16A16_FLOAT` color target and `D32S8_TYPELESS` depth target. The two
draws contain 9,304 indices in total: the qualified candidate contributes
9,300, and one immediately following draw contributes four. The first observed
phase spans RenderDoc draw events 6884 through 6893; the same two-draw shape
repeats six times.

This closes the pass-boundary ambiguity. A bounded runtime scan can contract
the prepared draw immediately following the anchor without reading guest
payloads or changing rendering:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  -Scene open_world_day `
  -PassAnchorSignature 747837906D0BF484

python .\tools\select-native-renderer-pass-follower.py `
  .local\native-renderer\pass-follower\run-1-census.json `
  .local\native-renderer\pass-follower\run-2-census.json `
  --anchor 747837906D0BF484 `
  --output .local\native-renderer\pass-follower\contract.json
```

## Qualified follower contract

Two independent AppData-backed `open_world_day` runs on 2026-08-28 observed
the same draw immediately after the anchor. Its prepared signature is
`1D253A52B55C9FB3`; both runs placed it at draw 119 after anchor draw 118 in
the same frame. The frame sequences differed (1,923 and 4,714), demonstrating
that the contract is not tied to a fixed frame number.

The follower uses vertex shader `21FBB5F33759B350`, pixel shader
`CF453BD52292E8E8`, prepared pipeline hash `E08F2FEEA79DC6FE`, primitive 13,
auto-index source selection, four elements, one vertex binding and attribute,
and one texture fetch. Shader specialization masks, pipeline state, and all
recorded dependency flags matched across both processes. It is not an isolated
draw candidate because it uses the auto-index path; that is an expected
contract property, not drift.

This qualifies the ordered phase shape and its two prepared signatures. NR-02F
must next replay the ordered pair into one retained private target and compare
the complete phase against Xenos. Until then, Xenos remains authoritative and
suppression remains forbidden.

Local evidence hashes:

- pass trace SHA-256:
  `15BA3B6375AED140ADB55FC08D2FCA17927671D16369840C661BDF81BE6DDB37`;
- derived inventory SHA-256:
  `9B71679E0971620D192054BC0216CFD3B6EC46668CDB56F224D0C69491CA25D0`;
- two-run follower contract SHA-256:
  `9F1CC53C8D7989EB3EC113D2215848EDA2D1DFD127D57C4F8BAA73A5DEB7923A`.

The capture and derived reports remain under `.local/qualification` and
`.local/native-renderer/pass-follower`.
