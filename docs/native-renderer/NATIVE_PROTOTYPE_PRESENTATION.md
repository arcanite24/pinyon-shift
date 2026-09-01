# Native prototype presentation

Phase B2 replaces the retained-pass diagnostic crop with a complete logical
scene presentation mode. The `native_prototype` renderer remains
restart-gated, default-off, and fail-closed. Selecting it automatically arms
the bounded continuous world workset from Phase B1 and the runtime-proved exact
indirect track-world family from C1. Environment overrides remain available to
capture tooling; setting
`PINYON_SHIFT_NATIVE_RENDERER_CONTINUOUS_TRACK_WORLD=false` explicitly removes
the exact track family without changing the Xenos fallback.

For an exact current-frame retained target, ReXGlue maps the draw-derived
logical scene extent out of the padded backing allocation into a private
RGBA16F output-sized target. The extent is bounded by the active viewport and
scissor and clamped to the physical resource dimensions. It then uses the same
title gamma-ramp pipeline
used by the authoritative Xenos swap source. The existing title presentation
boundary performs the already-proven 3:2 output upscale. This removes the amber
border and checkerboard from the supported prototype path without treating
padded storage as visible image data or guessing bloom, grading, motion blur,
depth-of-field, or UI semantics.

The source and destination mapping is:

- source: the draw-derived logical region of the current-frame retained replay
  target (`512x288` observed at 2x and `256x144` at 1x);
- linear intermediate: output-sized RGBA16F nearest-neighbor mapping;
- converted destination: the ordinary guest-output texture;
- final destination: the title's established presentation surface;
- conversion: the active table or PWL title gamma ramp; and
- ownership: native only after an exact-frame source is available.

The physical backing remains padded (`640x8192` at 2x and `320x4096` at 1x).
Its dimensions are used for D3D resource access only; crop and upscale math use
the retained logical extent. This distinction prevents padded storage from
becoming visible and makes the prototype independent of the launcher scale.

If the workset is absent, stale, unsupported, or failed, the callback records
the existing waiting diagnostic and returns `false` before touching guest
output. The complete Xenos frame is then presented. Every authoritative Xenos
draw and side effect remains enabled, and suppression remains disabled.

This checkpoint is intentionally not Phase B3 hybrid composition. The retained
target is seeded at the first admitted world draw and does not yet prove the
safe ordering boundary needed to preserve later vehicles, transparency,
effects, and full-resolution UI while overlaying native opaque work. Those
families therefore require the next composition slice or whole-frame Xenos
fallback.

## Controls and diagnostics

The launcher developer-preview selector and `tools/set-graphics-experiment.ps1`
accept `native_prototype`, `comparison_native`, and `comparison_xenos` in
addition to the safe `xenos` default. Native prototype frame markers report:

- `composition=continuous_world_passthrough`;
- `presentation=logical_scene_scale_then_title_gamma_then_title_upscale`;
- exact matching `frame` and `retained_frame` values;
- `xenos_draw=preserved`; and
- `suppression=disabled`.

The AppData-backed Phase B6 qualification is recorded in
[`PROTOTYPE_BATCH_QUALIFICATION.md`](PROTOTYPE_BATCH_QUALIFICATION.md).
