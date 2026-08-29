# Dual-path native/Xenos comparison

NR-04C adds restart-gated `comparison_native` and `comparison_xenos` output
modes. Both modes preserve the complete Xenos frame and build the exact-frame
retained native display target in the command processor's existing submission.
Only the selected path becomes display authority:

- `comparison_native` copies the completed private native display target into
  guest output after Xenos has finished;
- `comparison_xenos` leaves guest output untouched after composing the native
  target privately.

The modes never suppress guest draws, resolves, queries, fences, memexport, or
other side effects. Missing, stale, unsupported, or failed native work yields
to the existing Xenos output before any guest-output write. Selection is
sequential on the command processor's one command list; the two paths cannot
write guest output concurrently.

## Strict same-frame export

Patch `0069-d3d12-dual-path-comparison.patch` emits two RenderDoc regions only
in comparison modes:

- `PinyonShift NR-04C native display composition` encloses the compute dispatch
  that fills the private target;
- `PinyonShift NR-04C native output selection` encloses the native-to-guest
  copy and is therefore present only when native output is selected.

The selection copy is the deterministic comparison boundary when the capture
contains the command-processor submission. Its destination
contains the completed Xenos frame immediately before the copy and the selected
native frame immediately afterward. Its source is the private native target.
All three images therefore come from the same build, guest frame, dimensions,
and output format.

With the installed AppData save and signed local RenderDoc build, capture a
native-selected frame using:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-output-comparison.ps1 `
  -StateRoot $stateRoot `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -IsolatedDrawSignature 1D253A52B55C9FB3 `
  -PassAnchorSignature 747837906D0BF484 `
  -IsolatedDrawDir '.local\qualification\nr04c-isolated-pass' `
  -CaptureDir '.local\qualification\nr04c-capture' `
  -SelectedOutput native
```

Load the requested scene, press F12 after the retained native output is visible,
then close the game. The wrapper changes only the renderer selector and restores
its original value after the capture process exits.

Export the first complete same-frame pair with:

```powershell
.\tools\export-native-renderer-output-comparison.ps1 `
  -Capture '.local\qualification\nr04c-capture\reference_frame1.rdc' `
  -RenderDocRoot '.local\tools\renderdoc-1.45\RenderDoc_1.45_64' `
  -OutputDir '.local\qualification\nr04c-output-comparison'
```

When both NR-04C markers are present, the exporter writes `xenos-output.png`, `native-private.png`,
`native-selected.png`, and `native-output-comparison.json` below `.local`.
The report records capture and image hashes, dimensions, marker/event IDs,
resource IDs, selection authority, and RenderDoc GPU-duration samples for the
native composition dispatch and selection copy. Export fails if the private
native image differs from the selected native image, if dimensions differ, if
resources alias, or if GPU timing is unavailable.

Use `-SelectedOutput xenos` in a separate gameplay run to qualify that the same
parallel native workload leaves the complete Xenos frame authoritative. That
mode intentionally has no native selection-copy marker, so it is a fallback and
visual-safety qualification rather than the paired-image export source.

RenderDoc's F12 boundary can land on either the 30 Hz guest submission or the
60 Hz presenter frame. In the qualification build, an F12 capture containing
the guest draws did not include the later command-processor composition and
selection markers, while adjacent captures contained only presenter work. The
strict exporter therefore failed closed as designed. Do not interpret a normal
swapchain thumbnail as proof that the same-frame resource boundary was captured.

## Qualification evidence

The AppData save was exercised in both comparison modes with the same clean
binary (`81B1BF6A047732CF3A8968E02AB38B1E7C001DC92017DAE20F2353E31CE9E2CE`)
and the `open_world_day` scene marker. Local, game-derived evidence remains
below `.local/qualification` and is not committed:

- `comparison_native` session `20260829T004321Z-p43056` displayed the retained
  native target and logged exact-frame native authority with Xenos draws
  preserved and suppression disabled. Its 3,837-frame performance capture
  measured 53.868 median renderer FPS, 19.136 one-percent-low FPS, 29.440 Hz
  simulation cadence, and one presentation deadline miss.
- `comparison_xenos` session `20260829T004547Z-p15824` displayed the complete
  Xenos scene and logged Xenos authority while the same private native workload
  remained active. Its 3,734-frame capture measured 54.977 median renderer FPS,
  19.376 one-percent-low FPS, 29.406 Hz simulation cadence, and no presentation
  deadline misses.
- The paired thumbnails have SHA-256 values
  `8C61DF8B76D5F1D2CF3D13A5CF0C377A7F90AB30AA907EFA9F4813F49FC2BD0C`
  (native) and
  `EC1CE75B4EA83BB991AD67622EC1AE192EF18459B1843C45F4ADFDE54067860E`
  (Xenos). A local vertical contact sheet records the difference inventory.

The current native output is deliberately partial: it contains the retained
pass slice and diagnostic amber border, but not the full vehicle, HUD, crowd,
transparent scene, or post-processing coverage visible in Xenos. This is useful
proof that native display authority is real, not a readiness signal for pass
suppression or default enablement.

Per-pass RenderDoc GPU-duration samples were unavailable from the captured
boundary. Engine-owned asynchronous D3D12 timestamp queries now close that
instrumentation gap. The same clean timing build and AppData scene produced:

- `comparison_native` session `20260829T015610Z-p25896`: 32,604.962 us mean
  guest-frame GPU time, 90.184 us native composition, 20.682 us native
  selection, and zero dropped samples;
- `comparison_xenos` session `20260829T015923Z-p23056`: 34,848.473 us mean
  guest-frame GPU time, 73.845 us native composition, no selection samples as
  expected, and zero dropped samples.

See [GPU_TIMING.md](GPU_TIMING.md) for the query lifecycle, counter schema,
full build identity, and safety boundary.

## Qualification gates

- Both comparison modes use exact-frame retained state and remain
  restart-gated and default-off.
- Native-selected and Xenos-selected gameplay runs remain stable and report the
  correct `selected_output` and `authority` diagnostics.
- Xenos draws stay preserved and suppression stays disabled in both modes.
- When the command-processor submission is captured, the strict export contains
  distinct Xenos/native resources and identical hashes for the private and
  selected native output; otherwise it fails closed.
- Runtime frame timing and native GPU buckets are recorded for both authorities
  with no CPU wait and no dropped samples in qualification.
- Unsupported/startup frames yield to Xenos without an output-state fault.
- Clean exit, relaunch, and renderer restoration remain correct.
