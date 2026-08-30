# Native prototype comparison

Phase B5 makes the existing restart-gated comparison controls representative
of the current prototype rather than the earlier retained-pass diagnostic.
Xenos remains the default renderer and no comparison mode suppresses a guest
draw, resolve, query, fence, memexport, or other side effect.

## Renderer selections

- `xenos` leaves the complete Xenos frame authoritative and does no native
  output work.
- `native_prototype` presents the continuous native world workset through its
  draw-derived logical scene extent, RGBA16F linear intermediate, title gamma
  conversion, and title upscale path.
- `hybrid_prototype` admits a native pixel only when it agrees with completed
  Xenos output and otherwise retains the Xenos pixel.
- `comparison_native` builds the same native-prototype output privately, then
  selects it after the completed Xenos frame.
- `comparison_xenos` builds the same private native-prototype output but leaves
  the completed Xenos frame authoritative.

Both comparison selections self-arm the prototype world workset and exact
80-draw shadow observer. Shadow publication remains current-frame and
fail-closed; an unavailable exact consumer reports Xenos fallback without
rejecting the rest of the prototype frame.

The diagnostics contract reports renderer mode, composition, presentation,
selected output, authority, world fallback, shadow state, preserved Xenos
draws, and disabled suppression. All selectors require a restart.

## Same-build paired export

The strict paired export uses `comparison_native`. Its selection copy provides
one deterministic same-frame boundary: the destination contains completed
Xenos output immediately before the copy, the source contains the private
native output, and the destination contains selected native output immediately
after the copy. This produces the pair without comparing different gameplay
runs.

At the batched B6 qualification checkpoint, use the installed AppData save and
the signed local RenderDoc build:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-output-comparison.ps1 `
  -StateRoot $stateRoot `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -CaptureDir '.local\qualification\native-prototype-comparison' `
  -SelectedOutput native
```

Load the requested scene, press F12 after the world is stable, and close the
game. The wrapper restores the original renderer selection in a `finally`
block. It no longer supplies legacy isolated-draw or pass-anchor signatures;
the prototype comparison path owns its exact automatic configuration.

Export a capture containing both comparison markers:

```powershell
.\tools\export-native-renderer-output-comparison.ps1 `
  -Capture `
    '.local\qualification\native-prototype-comparison\reference_frame1.rdc' `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -OutputDir '.local\qualification\native-prototype-comparison-export'
```

The exporter writes `xenos-output.png`, `native-private.png`,
`native-selected.png`, and `native-output-comparison.json`. It fails closed if
the resources alias, dimensions differ, the private and selected native hashes
differ, required markers are missing, or GPU timing is unavailable.

Use a separate `comparison_xenos` gameplay run to qualify visual fallback and
Xenos authority. That mode intentionally has no native selection-copy marker,
so it is not the paired-image export source.

## B5 safety boundary

- Xenos stays default and remains complete before native selection.
- Comparison uses the same presentation math and source extent as the actual
  prototype.
- Native failure or stale retained state yields to Xenos.
- Comparison does not enable suppression.
- Captures and game-derived images remain below `.local` and are not committed.
- Full build, AppData gameplay, performance, relaunch, fallback, and screenshot
  qualification are deliberately batched into B6.

The B6 implementation keeps physical backing dimensions separate from the
logical crop: `512x288` was observed at 2x and `256x144` at 1x, while the
corresponding padded resources were `640x8192` and `320x4096`. See
[`PROTOTYPE_BATCH_QUALIFICATION.md`](PROTOTYPE_BATCH_QUALIFICATION.md) for the
clean-build and AppData evidence.
