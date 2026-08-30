# Conservative native/Xenos hybrid prototype

Phase B3 adds a complete-frame `hybrid_prototype` mode without guessing a
semantic vehicle, transparency, effects, or UI mask. It remains restart-gated,
default-off, and independent from suppression.

The backend first scales the draw-derived logical scene extent out of the padded
retained allocation into a private RGBA16F target, then converts it with the
same active table or PWL gamma-ramp pipeline used for the Xenos swap source. It
compares that private guest-format result with the already completed Xenos
guest-output texture. A native pixel is admitted only when every channel agrees
within half one 8-bit UNORM step. Every mismatch is copied from Xenos.

This conservative rule has three useful properties:

- the displayed result is complete even though native semantic coverage is
  partial;
- later Xenos vehicles, transparency, effects, post-processing, and UI remain
  authoritative wherever they change the final pixel; and
- no guessed mask, guest draw suppression, resolve suppression, readback, or
  CPU/GPU synchronization is introduced.

The agreement compositor writes a second private guest-format target. Only
after the full dispatch completes is that target copied into guest output. A
missing or stale workset, allocation failure, descriptor failure, or pipeline
failure returns before guest output is modified and presents the complete
Xenos frame.

Agreement is a presentation safety gate, not proof of semantic native coverage
and not a performance optimization. Pixels may agree coincidentally, while
FXAA and unimplemented post effects can conservatively reduce native admission.
Later Phase C/D work replaces this pixel gate with qualified semantic families;
Phase E controls suppression only after those dependencies are closed.

## Diagnostics

Claimed hybrid frames report:

- `mode=hybrid_prototype`;
- `composition=conservative_pixel_agreement_hybrid`;
- `presentation=logical_scene_scale_then_title_gamma_then_title_upscale`;
- `selected_output=hybrid` and `authority=hybrid`;
- whether Xenos FXAA was applied;
- exact matching `frame` and `retained_frame`; and
- preserved Xenos draws with suppression disabled.

The logical extent is `512x288` in the observed 2x path and `256x144` in the
observed 1x path; physical backing dimensions remain separate. The AppData
gameplay and visual qualification is recorded in
[`PROTOTYPE_BATCH_QUALIFICATION.md`](PROTOTYPE_BATCH_QUALIFICATION.md).
