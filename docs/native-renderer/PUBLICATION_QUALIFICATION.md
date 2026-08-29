# Retained-pass publication qualification

The retained sky/horizon producer does not need 38 native consumer
implementations before its output can be preserved. The qualified alternative
boundary publishes a bit-exact native color and depth/stencil pair into the
same guest render targets, then leaves every original Xenos resolve and later
consumer unchanged.

`tools/qualify-native-renderer-publication.py` combines five independently
fail-closed artifacts:

1. same-frame exact color comparison;
2. same-frame exact depth/stencil comparison;
3. successful paired target publication;
4. a complete later-consumer identity inventory; and
5. a complete attachment corpus proving an observed consumer contributes to a
   later target after publication.

The report rejects signature drift, partial publication, incomplete consumer
metadata, an unobserved consumer contribution, and any evidence that enables
draw or resolve suppression. A passing report promotes only the
`later_gpu_consumers` preservation gate for the exact producer family and
qualified scene. It does not enable suppression.

## Qualification command

```powershell
python .\tools\qualify-native-renderer-publication.py `
  --color .local\qualification\nr04d-paired-color-report.json `
  --depth-stencil .local\qualification\nr04d-depth-report.json `
  --publication .local\qualification\retained-pass-publication.json `
  --consumers .local\qualification\native-renderer-pass-consumers.json `
  --consumer-corpus .local\qualification\publication-consumer-corpus\consumer-contribution-corpus.json `
  --output .local\qualification\native-renderer-publication-qualification.json
```

The 2026-08-29 local evidence bundle passed with:

- 41,943,040 exact color bytes;
- 83,886,080 exact multisample depth/stencil bytes;
- 12,018 successful paired publications and zero failures;
- 51 complete consumer signatures in 26 shader-specialization families; and
- four complete samples of the leading consumer family, including one real
  depth/stencil contribution.

The original draws, resolves, consumers, queries, fences, and memexport remain
active. Publication changes the producer target contents only after the
original follower has completed, and failed publication retains the complete
Xenos targets.

## Family control plane

Configuration schema 11 reserves the restart-gated CVar
`pinyon_shift_native_renderer_sky_horizon_suppression`. It defaults to `false`
and is independently reset when the renderer is rolled back to Xenos.

The control is deliberately `diagnostic_only`. If requested, runtime emits
`native_renderer.suppression_control` with `status=blocked_not_admitted`, keeps
`suppression_allowed=false`, and executes every original draw and resolve. This
proves the control-plane identity without pretending the rollback gate has been
runtime-qualified against a real suppression implementation.

AppData-backed session `20260829T084847Z-p9268` requested the control on the
schema-11 clean build. It reached the installed festival save with complete
sky, world geometry, crowds, vehicle, UI, and post-processing. Diagnostics
reported `blocked_not_admitted`, mandatory Xenos fallback, the original draw
preserved, both suppression fields false, and a normal process shutdown. The
81.589-second run recorded 3,297 samples, 56.593 median renderer FPS, 29.293 Hz
simulation cadence, 59.983 Hz presentation cadence, zero presentation deadline
misses, 99.903% texture-cache hits, and 100% pipeline-cache hits. The setting
was restored to `false` after the run.

Use the settings helper to exercise either state without editing TOML:

```powershell
.\tools\set-graphics-experiment.ps1 `
  -Action SetSkyHorizonSuppression `
  -SkyHorizonSuppression false `
  -StateRoot $stateRoot
```

The next implementation boundary is the independent, default-off suppression
path itself. It remains prohibited until its rollback behavior is qualified and
the full admission report is 12/12.
