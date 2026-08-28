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

This closes the pass-boundary ambiguity but does not yet qualify the second
draw. NR-02F must identify and contract that four-index follower, replay the
ordered pair into one retained private target, and compare the complete phase
against Xenos. Until then, Xenos remains authoritative and suppression remains
forbidden.

Local evidence hashes:

- pass trace SHA-256:
  `15BA3B6375AED140ADB55FC08D2FCA17927671D16369840C661BDF81BE6DDB37`;
- derived inventory SHA-256:
  `9B71679E0971620D192054BC0216CFD3B6EC46668CDB56F224D0C69491CA25D0`.

The capture and derived reports remain under `.local/qualification`.
