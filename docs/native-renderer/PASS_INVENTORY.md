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
recorded dependency flags matched across both processes. A third observation
confirmed host primitive 13, prepared index-buffer type zero, host index format
zero, primitive restart disabled, prepared flags `00000003`, and bound target
bits `00000003`.

The title-qualified AutoIndex replay path was then exercised against the
installed AppData save as session `20260828T154921Z-p40752`. Signature
`1D253A52B55C9FB3` recorded once at frame 3,143, draw 117, and completed an
asynchronous readback from the 640 by 8,192 private target. The 512 by 512 crop
contains the expected sky and horizon phase prefix, the process exited normally
with code zero, and the structured result retained `xenos_draw=preserved`,
`output_authority=xenos`, and `suppression_eligible=false`.

## Retained-pass runtime result

NR-02F now replays the ordered pair into one retained private target. The
indexed anchor seeds and retains the isolated color and depth attachments; the
immediately adjacent AutoIndex follower resumes those same attachments before
the private target is released. Each original guest draw still executes.

AppData-backed sessions `20260828T161429Z-p41368` and
`20260828T162849Z-p8536` both recorded the complete pass. The latter recorded
anchor draw 117 and follower draw 118 at frame 3,190, produced an asynchronous
readback from the 640 by 8,192 private target, then recorded a second retained
pair at draws 126 and 127 in the same frame. Both readback crops have SHA-256
`AF82E49BAE46AA67B0255BC3B1B5120BA7F69205BB8526F1DB9F8ED151090150`,
confirming deterministic output across the two runs. The crop contains the
expected combined sky and horizon phase output. Both processes exited normally
with code zero.

The structured results report `draw_count=2`, `status=recorded`,
`xenos_draw=preserved`, `output_authority=xenos`, and
`suppression_eligible=false`. The one-shot repeat result also reports
`status=recorded`, proving that the retained target can be recreated after the
diagnostic readback for later frame-debugger runs.

RenderDoc captures taken after the readback contained only the final 3840 by
2160 presentation draw and no Pinyon marker regions; the metadata-only trace
therefore cannot be used as a visual-equivalence result. A complete-pass Xenos
image comparison remains an explicit gate before any suppression work. The
runtime replay itself is qualified only as an isolated, default-off diagnostic.
Xenos remains authoritative and suppression remains forbidden.

Local evidence hashes:

- pass trace SHA-256:
  `15BA3B6375AED140ADB55FC08D2FCA17927671D16369840C661BDF81BE6DDB37`;
- derived inventory SHA-256:
  `9B71679E0971620D192054BC0216CFD3B6EC46668CDB56F224D0C69491CA25D0`;
- two-run follower contract SHA-256:
  `9F1CC53C8D7989EB3EC113D2215848EDA2D1DFD127D57C4F8BAA73A5DEB7923A`;
- retained-pass readback metadata SHA-256:
  `B0C6395F5C8BD6294A54837C94E85536BFBEFA99E340DCDA5A8C442829E954CB`.

The capture and derived reports remain under `.local/qualification`,
`.local/native-renderer/pass-follower`, and
`.local/native-renderer/pass-replay`.
