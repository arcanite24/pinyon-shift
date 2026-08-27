# Experimental graphics qualification

The launcher exposes validated anisotropic filtering, FXAA, optional FH1 motion
blur and depth-of-field removal, and a restart-only 2x internal-resolution
experiment. The recovery defaults are 1x with both original post-processing
effects enabled. Every save,
reset, and restore is handled by `tools/set-graphics-experiment.ps1`; it backs
up only `pinyon_shift.toml` and never changes saves, generated code, or caches.

The 2x option remains explicitly experimental until a candidate run meets all
of these gates on the same exact build fingerprint as its 1x control:

- all ten scenes accepted by `tools/visual-baseline.py` with no missing or
  mismatched labels;
- at least five minutes of compatible per-frame data accepted by
  `tools/summarize-performance.py`;
- median frame time no more than 35% slower, p95 frame time no more than 50%
  slower, and 1% low no more than 35% lower than the 1x control;
- peak committed GPU memory no more than 1.8 GiB above the 1x control; and
- no new crash, device-removal, guest-memory coherency, or visual-correctness
  signature.

If a run fails to start or display correctly, select **Reset defaults** in the
launcher. This restores 1x resolution and preserves a timestamped backup for
diagnostics.

## FH1 post-processing switches

**Disable motion blur** and **Disable depth of field** are generated-code
substitutions for the exact supported USA retail base executable only. The
build refuses any `default.xex` whose size and SHA-256 do not match
`config/supported-dumps.json`. The substitutions reproduce the instruction
values published for Xenia patch hash `D48ABF1704CE5C4A`; they do not modify
the extracted executable or patch guest memory at runtime.

Both options default to `false`. With an option disabled, its hook executes the
original generated instruction. With motion blur removal enabled, the hook
skips the store at `0x82D7894C` (equivalent to PPC `nop`). With depth-of-field
removal enabled, the hooks set `r11` to zero and skip the original loads at
`0x8245B494`, `0x8245846C`, and `0x8245849C` (equivalent to PPC `li r11, 0`).
Saving either option requires a preview restart. The effective values appear in
`logging.ready` and privacy-safe support bundles. Build and visual-baseline
fingerprints include the generated substitution profile and its SHA-256.

Qualification uses the same exact build for the original-effects control and
each enabled profile. Capture at minimum open-world day, open-world night,
high-speed race, cockpit, and rewind scenes. Confirm the intended temporal or
focus effect changes while menus, HUD, car paint, and player-car motion remain
free of new corruption or jitter.

Renderer A/B sessions use `tools/renderer-ab.py`. It changes only one temporary
override at a time, keeps shipping defaults intact, and refuses to compare the
memexport toggle until the performance evidence includes exporting-draw,
byte, synchronous-fallback, queue-wait, and fence-wait counters.
