# Continuous native composition

NR-04B moves the qualified retained-pass preview behind a private, full-size
native display target. The visible experiment remains default-off and does not
expand draw coverage or suppress Xenos work.

For each current-frame retained pass, the D3D12 command processor creates or
reuses one single-sample display texture matching the guest-output dimensions
and format. The existing native composition shader writes every pixel of that
private texture. Only after composition has been recorded does the command
processor transition the completed texture to copy source, transition guest
output to copy destination, copy the whole texture, and restore the presenter's
guest-output state.

The texture stays private to the command processor and uses the same open
submission as the guest swap. There is no second presenter or swapchain. A
resize allocates a correctly sized replacement and retains the old texture
until its last recorded submission is complete. Context shutdown waits for GPU
work before releasing the active display target, pipelines, and root
signatures.

All failure paths before composition leave guest output untouched. The title
and backend exact-frame checks from `FRAME_PUBLICATION.md` still run before the
private target is sampled or copied. Missing, stale, unsupported, or failed
native work therefore returns `false` and presents the complete Xenos frame.
Original Xenos draws, resolves, queries, fences, and guest-memory effects remain
enabled.

This is the composition surface required by the next dual-path milestone. It
does not yet claim complete native scene coverage or measurable GPU savings;
those require paired capture followed by separately qualified pass-level
suppression.

## Qualification gates

- The complete 68-patch ReXGlue stack must apply from the pinned revision.
- A clean preview build and the repository test suites must pass.
- Claimed output markers must report `composition=private_display_target`,
  exact matching frame identifiers, preserved Xenos draws, and disabled
  suppression.
- Startup and unsupported frames must continue through Xenos.
- A sustained AppData-backed run must show no output-state warning, device
  removal, validation error, fatal event, or crash.
- Shutdown must be normal and performance must remain within the established
  retained-preview envelope.

## Qualified checkpoint

Session `20260829T000459Z-p37956` qualified this milestone against the installed
`0.1.0` AppData save in `open_world_day` on the clean 68-patch build. The run
lasted 238.54 measured seconds and exited normally.

- All 13 sampled claimed-output markers used
  `composition=private_display_target` and exact matching `frame` and
  `retained_frame` identifiers.
- Every sampled marker reported `xenos_draw=preserved` and
  `suppression=disabled`.
- The run reached 3,690 native claims with no output failure, device removal,
  fatal event, or crash.
- The native crop remained continuously visible inside the amber diagnostic
  boundary, with checkerboard fill identifying deliberately unsupported output
  regions.
- Across 7,581 performance samples, median frame rate was 30.19 FPS, 1% low was
  19.20 FPS, and presentation cadence was 59.98 Hz. Two presentation deadline
  misses and two dropped presents were recorded; no sustained cadence failure
  or renderer fault accompanied them.

After qualification, the AppData configuration was returned to the default
`xenos` renderer while preserving the existing graphics settings.

NR-04C builds on this surface with the controlled selector, paired visual
qualification, and strict capture workflow documented in
[DUAL_PATH_COMPARISON.md](DUAL_PATH_COMPARISON.md).
