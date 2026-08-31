# Vehicle retained color pass

Status: privately qualified behind a default-off switch; native publication
remains disabled.

## Evidence boundary

The qualified dynamic-shadow epoch correlates 30 bounded color families by
exact geometry-resource identity. In the 2026-08-31 topology run, every family
appeared exactly once in every frame from 8,822 through 9,008. The 5,610
matches were split into 2,992 consecutive runs, with a maximum run length of
five, because unrelated guest draws occur between vehicle submeshes.

This rules out a consecutive 30-draw replay. It supports a frame-wide retained
pass that preserves the relative guest order of the 30 correlated draws while
leaving all intervening guest work on Xenos.

## Admission contract

The retained pass is armed only when all of these conditions hold:

- the exact 80-draw vehicle shadow epoch was recorded successfully;
- the one-family private native/Xenos color capture succeeded;
- the correlation table contains exactly 30 families and did not overflow;
- the current draw is an exact correlated family accepted by the private
  vehicle replay gate; and
- the process has not encountered a prior retained-pass failure.

Each accepted frame must contain exactly 30 matches in monotonically
increasing guest draw order. The first draw creates and retains a private color
target, the middle 28 reuse it, and the final draw reuses and releases it. The
first complete target can be read back below `.local`; later frames remain
private. The path is bounded to 120 frames per process.

Any missing or extra family, non-monotonic ordering, target-creation failure,
or unsupported replay fails the experiment closed for the rest of the
process. Xenos draws remain intact in every case.

## Safety and non-claims

- The target is never published to the guest or final presentation path.
- No guest draw, resolve, query, or side effect is suppressed.
- Xenos remains the only output authority.
- No guest payload is included in diagnostics or public reports.
- Correlated shadow geometry does not yet prove player/traffic object identity,
  wheels, livery, glass, every material, or semantic full-vehicle coverage.

## Batched qualification

Build once, then launch the AppData save with:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -ShadowDepthBatch `
  -VehicleShadowGeometryCorrelation `
  -CaptureVehicleShadowColor `
  -RetainVehicleShadowColorPass `
  -IsolatedDrawDir .local\qualification\vehicle-retained-color
```

The v6 vehicle qualifier must report:

- 120 started and completed frames, zero failed frames;
- 3,600 requests and 3,600 recorded outcomes;
- 3,480 retained-target reuse requests;
- one complete native retained-pass readback;
- no target failures, unsupported replays, errors, crashes, publication, or
  suppression; and
- a clean normal exit.

Visual acceptance is a recognizable multi-submesh vehicle contribution rather
than the previously captured single rear-body slice. It remains a private
prototype until object identity, remaining vehicle material families, hybrid
publication, and per-item fallback are qualified.

## Qualification result

The clean AppData-backed session `20260831T164716Z-p35116` completed normally
with the retained mode enabled. It recorded all 3,600 requested draws across
120 complete frames, including 3,480 retained-target reuses, with zero failed
frames, target failures, unsupported replays, errors, or suppression. The
session observed 9,600 exact color correlations and produced one complete
retained readback.

The readback is a coherent multi-submesh rear view: body panels, bumper,
glazing, wheels, and lower geometry coexist in one native target. This is a
material improvement over the single rear-body slice. The diagnostic remains
unlit and isolated, with flat gray/black material regions and no scene
composition, so it proves frame-wide geometry retention rather than material,
lighting, object-identity, or final-frame parity.
