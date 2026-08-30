# Native prototype presentation

Phase B2 replaces the retained-pass diagnostic crop with a complete-source
presentation mode. The `native_prototype` renderer remains restart-gated,
default-off, and fail-closed. Selecting it automatically arms the bounded
continuous world workset from Phase B1; the environment override remains
available to capture tooling.

For an exact current-frame retained target, ReXGlue maps the whole source into
the guest-output texture with a deterministic nearest sample. The existing
title presentation boundary then performs the already-proven 3:2 output
upscale. This removes the amber border and checkerboard from the supported
prototype path without guessing bloom, grading, motion blur, depth-of-field,
or UI semantics.

The source and destination mapping is:

- source: the complete current-frame retained replay target;
- intermediate destination: the ordinary guest-output texture;
- final destination: the title's established presentation surface;
- sampling: integer nearest mapping across both axes; and
- ownership: native only after an exact-frame source is available.

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
- `presentation=full_source_nearest_then_title_upscale`;
- exact matching `frame` and `retained_frame` values;
- `xenos_draw=preserved`; and
- `suppression=disabled`.

No AppData-backed visual qualification is claimed by this implementation
checkpoint. It is batched with the remaining Phase B composition work.
