# Authentic draw visual comparison

NR-02E compares the private native replay with the original ReXGlue/Xenos
draw. The workflow keeps captures and game-derived images below `.local`; only
the tooling, thresholds, and result summary belong in the public repository.

## Reference capture

Patch `0060-d3d12-isolated-draw-debug-markers.patch` adds two RenderDoc-visible
D3D12 regions when an exact isolated-draw signature is configured:

- `PinyonShift NR-02E isolated native draw` marks the private replay. After its
  one-shot diagnostic result is recorded, the exact-signature debug run repeats
  the replay without readback or completion callbacks so it remains available
  to a frame debugger;
- `PinyonShift NR-02E authoritative Xenos draw` marks the original draw that
  immediately follows each private replay.

Patch `0061-d3d12-seeded-isolated-replay-targets.patch` copies the current
guest color and depth attachments into the private clones before replay. This
preserves the candidate draw's existing depth and target context while keeping
the guest attachments read-only and restoring their tracked resource states.
The private replay still never replaces or suppresses the Xenos draw.

The marker path does not skip or suppress either draw. Use an official signed
RenderDoc portable build and launch the capture with:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-renderdoc.ps1 `
  -StateRoot $stateRoot `
  -RenderDocRoot '.local\tools\renderdoc\RenderDoc_64' `
  -IsolatedDrawSignature 747837906D0BF484 `
  -CaptureDir '.local\qualification\native-renderer-renderdoc-reference'
```

Load the saved open world, press F12, and verify the authoritative marker is
present in the captured frame. Export the first adjacent marker pair with:

```powershell
.\tools\export-native-renderer-renderdoc.ps1 `
  -Capture '.local\qualification\native-renderer-renderdoc-reference\reference_frame1.rdc' `
  -RenderDocRoot '.local\tools\renderdoc\RenderDoc_64' `
  -OutputDir '.local\qualification\renderdoc-reference-export'
```

The first qrenderdoc launch may present RenderDoc's own analytics privacy
choice. Make that choice in the visible official UI; the wrapper neither
selects nor bypasses it. The export report records marker counts, paired event
IDs, output dimensions, resource IDs, and hashes. It preserves color alpha in
the two lossless color PNGs and also exports the bound depth attachment at each
marked draw as a grayscale PNG. The comparator accepts binary PPM or
non-interlaced 8-bit PNG, so the lossless exports can be compared directly.
Keep the RDC and all exports local.

## Deterministic comparison

Run:

```powershell
python .\tools\compare-native-renderer-images.py `
  .local\qualification\renderdoc-reference-export\isolated-native.png `
  .local\qualification\renderdoc-reference-export\authoritative-xenos.png `
  --native-before `
    .local\qualification\renderdoc-reference-export\isolated-native-before.png `
  --reference-before `
    .local\qualification\renderdoc-reference-export\authoritative-xenos-before.png `
  --crop 0,0,512,280 `
  --color-space linear `
  --difference-output `
    .local\qualification\visual-comparison\difference.ppm `
  --output .local\qualification\visual-comparison\report.json

python .\tools\compare-native-renderer-images.py `
  .local\qualification\renderdoc-reference-export\isolated-native-depth.png `
  .local\qualification\renderdoc-reference-export\authoritative-xenos-depth.png `
  --content depth `
  --crop 0,0,512,280 `
  --difference-output `
    .local\qualification\visual-comparison\depth-difference.ppm `
  --output .local\qualification\visual-comparison\depth-report.json
```

The report records input hashes, dimensions, color-space declaration,
per-channel MAE and RMSE, the maximum error, the fraction of pixels outside the
channel tolerance, and foreground coverage intersection-over-union. A mismatch
returns exit code 2; malformed or dimensionally incompatible input returns 1.
The optional difference image amplifies each absolute channel error by 16 for
direct inspection; this affects visualization only, never the numeric gate.

The default gate is intentionally strict: MAE at most 2, RMSE at most 4, no
more than 1 percent of pixels beyond a four-value channel tolerance, and
coverage IoU of at least 0.99.

The color before/after pairs derive draw-only coverage, excluding unrelated
contents already present in the authoritative Xenos target. The RGBA color
comparison gates geometry coverage, texture orientation, alpha, and output
color. The separate post-draw depth comparison gates the seeded mapped depth
target. The qualified sky candidate does not write depth, so comparing its
before/after depth delta would produce an empty and therefore meaningless set.
NR-02E acceptance requires both reports to pass and the paired event IDs in the
export report to show the isolated native marker immediately followed by the
authoritative Xenos marker.

## Qualified reference result

The 2026-08-28 `open_world_day` qualification used exact draw signature
`747837906D0BF484`. RenderDoc exported the isolated native draw at event 6880
and the immediately following authoritative Xenos draw at event 6884. Six
paired markers were present in the captured frame.

For the 512 by 280 gameplay crop, both comparisons passed with exact output:

- color draw delta: 122,516 compared pixels, 0 different pixels, MAE 0,
  RMSE 0, and coverage IoU 1.0;
- post-draw depth: 143,360 compared pixels, 0 different pixels, MAE 0,
  RMSE 0, and coverage IoU 1.0.

The isolated and authoritative color PNGs had the same SHA-256, as did their
pre-draw color PNGs and post-draw depth PNGs. The capture and game-derived
exports remain local under `.local/qualification`.

The six exact-signature occurrences do not by themselves define the complete
pass. Their target-phase correlation and the remaining four-index follower are
documented in [PASS_INVENTORY.md](PASS_INVENTORY.md).

## Complete-pass comparison

NR-04D admission compares the entire two-draw family rather than promoting the
anchor result above. The preferred color path is a same-frame paired asynchronous
readback. Launch the pass with the existing isolated readback directory set. The
native artifact is committed at that path and the authoritative guest artifact
is committed beside it with `.xenos` appended. Compare active texel bytes while
excluding D3D12 row padding:

```powershell
python .\tools\compare-native-renderer-pass-readbacks.py `
  '.local\qualification\nr04d-pass-readback' `
  --output '.local\qualification\nr04d-pass-color-report.json'
```

Both copies are inserted into the same command list: native after the private
follower, and Xenos after the original authoritative follower. They retire by
submission fence without a CPU/GPU wait. The comparison rejects mismatched
signature, frame, follower draw, dimensions, row pitch, format, role, or safety
metadata, and requires exact active color bytes. Xenos remains the displayed
and authoritative output throughout.

RenderDoc remains the strict color-and-depth path. Capture with both the anchor
and follower configured, then export their native/Xenos spans:

```powershell
.\tools\export-native-renderer-renderdoc.ps1 `
  -Capture '.local\qualification\nr04d-pass\reference_frame1.rdc' `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -OutputDir '.local\qualification\nr04d-pass-export' `
  -CompletePass
```

The exporter requires this exact marker order: native anchor, Xenos anchor,
native follower, Xenos follower. It saves each target before its anchor and
after its follower, verifies stable resources and dimensions within each span,
and rejects aliasing between native and Xenos output. The resulting image names
remain compatible with the color and depth comparator commands above.

The complete-pass report records
`pinyon-shift.native-renderer-pass-renderdoc-export.v1`, two draws per path,
all marker/event IDs, capture and image hashes, and an explicit safety object.
It never enables draw or resolve suppression. A passing paired readback can
promote `color_parity`; `depth_parity` still requires the RenderDoc depth export
or a future same-frame depth capture. Both gates must pass before suppression
admission can complete.

### Qualified complete-pass color result

The 2026-08-28 AppData-backed `open_world_day` run used clean-build executable
SHA-256 `9965749C430F0011A691BEEF851F08170089F2F1EEB1B3F5647E9AAF12A261B2`.
Frame 2800 replayed anchor `747837906D0BF484` at draw 115 and follower
`1D253A52B55C9FB3` at draw 116. Both native and authoritative Xenos readbacks
were 640 by 8192 `R16G16B16A16_FLOAT` resources with 41,943,040 active bytes.

The comparison passed exactly: zero differing bytes, zero maximum error, and
identical binary SHA-256
`E238DB4ED42A27EF04386C7F196EF2EB5C9F1182E750F91A95453E8356888660`.
Runtime diagnostics recorded both roles as captured, preserved both Xenos
draws, reported no error/fatal/device-loss events, and exited normally. GPU
timing recorded zero drops; native composition averaged 77.223 microseconds
and native selection averaged 19.245 microseconds. The admission report now
passes 8 of 12 gates, with depth parity, later GPU consumers, guest CPU
visibility, and a rollback switch still deliberately blocking suppression.
