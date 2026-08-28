# Native retained-frame publication

NR-04A starts with an immutable freshness contract for the existing retained
authentic-pass preview. It does not expand native visual coverage and does not
suppress any Xenos work.

Each isolated replay request now carries the guest frame sequence captured with
its prepared draw. The D3D12 render-target cache publishes that sequence only
after the private replay commands have been recorded and the original guest
targets have been restored. The guest-output callback receives both the current
swap frame and the last successfully published retained-pass frame.

The title and backend independently require an exact frame match before the
retained target can be sampled. If the pass was not reproduced during the
current guest frame, the callback records a paced `retained_pass_stale` or
`retained_pass_unavailable` diagnostic and returns `false` without touching
guest output. ReXGlue then presents the complete Xenos frame. This prevents a
loading screen, map transition, menu, or unsupported scene from displaying a
retained target produced by an older frame.

The frame stamp resets during backend shutdown. Unsupported targets, missing
callbacks, allocation failures, and all early-return paths retain the existing
Xenos fallback. No draw, resolve, query, fence, or guest-visible side effect is
suppressed.

## Qualification gates

- Automated contracts must prove that both the title and D3D12 backend enforce
  the exact-frame comparison.
- The complete patch stack must apply from the pinned ReXGlue revision.
- A clean preview build must pass.
- An AppData-backed retained-pass run must show matching `frame` and
  `retained_frame` values whenever native output is claimed.
- Frames without a current retained pass must report the stale or unavailable
  reason and continue through Xenos.
- Shutdown must remain normal, with no renderer failure, device loss, fatal
  event, or crash.

## Qualification result

Clean-build AppData-backed session `20260828T233352Z-p39060` remained on the
complete Xenos frame through startup, the title flow, and the period before the
qualified pass became available. It then displayed the amber-framed authentic
native crop continuously in the loaded scene.

The session claimed 2,571 callbacks. All nine paced claimed-frame markers had
identical `frame` and `retained_frame` values. Seventeen pre-publication markers
reported `retained_pass_unavailable`, `fallback=xenos`, and
`suppression=disabled`. Every claimed marker reported `xenos_draw=preserved`;
there were no native-output failures, device-removal events, validation errors,
fatal events, or crashes, and shutdown was normal.

The 7,781-sample performance capture measured 30.366 median FPS, 19.392
one-percent-low FPS, 59.988 Hz presentation cadence, and zero presentation
deadline misses.
