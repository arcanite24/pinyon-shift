# Experimental graphics qualification

The launcher exposes validated anisotropic filtering, FXAA, and a restart-only
2x internal-resolution experiment. The recovery default is 1x. Every save,
reset, and restore is handled by `tools/set-graphics-experiment.ps1`; it backs
up only `pinyon_shift.toml` and never changes saves, generated code, or caches.

The 2x option remains explicitly experimental until a candidate run meets all
of these gates on the same exact build fingerprint as its 1x control:

- all eight scenes accepted by `tools/visual-baseline.py` with no missing or
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

Renderer A/B sessions use `tools/renderer-ab.py`. It changes only one temporary
override at a time, keeps shipping defaults intact, and refuses to compare the
memexport toggle until the performance evidence includes exporting-draw,
byte, synchronous-fallback, queue-wait, and fence-wait counters.
