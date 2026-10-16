# Frame generation

Opt-in, off by default. One generated frame is presented between each pair
of frames the game rendered, so a GPU-bound machine shows about twice as
many frames. The setting is **F6 > DISPLAY > FRAME GENERATION**
(`present_frame_generation`). The first target is the MacBook Pro M1, where
free roam renders at about 17 fps (57 ms GPU median, bound by render-pass
restarts on the tile-based GPU; see docs/MACOS.md). The game's rate is not
changed: it still simulates and renders at its own cadence, and the
generated frames are presentation only.

Related: the maintainer's decision of 2026-10-11 (docs/NATIVE_PORT_BACKLOG.md,
parking lot), FB-14.6 to FB-14.9 (docs/FEATURE_BACKLOG.md), DR-5.4
(docs/DESKTOP_RENDERER_BACKLOG.md). A colour-only optical-flow warp of the
finished frame was built and rejected in 2026-09 (it looked like 30 fps and
flickered in the UI and sky); the old `pinyon_shift_fh1_frame_interpolation`
key is stripped by config migration. This design differs in its inputs
(depth, the HUD as its own layer, camera motion) and in using a model built
for the job.

## Backends

| Setting | Backend | Status |
| --- | --- | --- |
| `off` | none | default |
| `metalfx` | Apple MetalFX frame interpolation (`MTLFXFrameInterpolator`, macOS 26, Apple silicon). The presenter's Vulkan images are exported to Metal through `VK_EXT_metal_objects` (MoltenVK) | stage 2 |
| `fsr3` | AMD FidelityFX FSR 3.1 frame generation, dispatched into the presenter's own images without the FidelityFX swapchain (which would fight present IDs, `vulkan_present_wait` and the UI drawers) | stub: reports unavailable |
| `repeat` | development only, never in the menu: re-presents the previous frame as the generated one, to measure the pacing and counters without a backend | stage 1 |

The settings row appears only when a backend is built in (macOS). An
unavailable backend is logged once and shown in the page's note; every
present is then a real frame.

## Design

- **Pacing.** When the game publishes frame N at time t, the presenter
  measures the base interval T (the median of the last four publish
  deltas, clamped to 8-200 ms), generates G = interp(N-1, N), presents G at
  once and presents N at t + f·T, where f is
  `present_frame_generation_delay` (default 0.5 for even spacing; down to
  0.1 trades evenness for latency). The real frame therefore waits f·T:
  about 29 ms on the M1 at the default. If N+1 arrives before N was
  presented, N is dropped (it lives on inside G(N, N+1)) and counted as a
  dropped present.
- **Threads.** The game's swap, the generation and the generated present run
  on the GPU Submission thread as today; the delayed real present runs on a
  presenter-owned pacing thread, so the submission thread never waits.
- **When it runs.** Only while the presenter paints from the guest output
  thread: no menus or overlays, no FIFO swapchain, presentation from the
  non-UI thread allowed. Otherwise every present is a real frame and the
  history is reset.
- **Images.** The presenter keeps its own copies of the last two frames (the
  mailbox releases a frame as soon as the next is taken), a generated image,
  and later the scene without the HUD, the depth and the motion vectors.
  Generation runs at the game's resolution, before output scaling.
- **Inputs by stage.** Stage 2: the two frames and the depth the executor
  already keeps current, with zero motion vectors (ghosting on camera
  motion expected). Stage 3: the scene before the HUD as the colour and the
  composited frame as the UI layer, so the HUD is never warped. Stage 4:
  camera motion vectors from the depth and the previous and current
  view-projection matrices.
- **History reset.** The first frame after enabling; a size or bit-depth
  change; a publish gap above max(3 × median, 250 ms) (loading, pause,
  video, alt-tab); leaving guest-thread painting; a frame without a pre-HUD
  snapshot (menus, video, photo mode); a backend failure.

## Counters

`generated_present_count`, `frame_generation_gpu_time_ns` and
`frame_generation_skipped` join the presentation counters. Generated
presents count in `present_count` but never as duplicates and never as
source frames, so:

```text
distinct presents = present_count - duplicate_present_count - generated_present_count
```

`tools/summarize-performance.py` reports `cadence_hz.generated_present`,
`cadence_hz.distinct_present` and the mean generation GPU time;
`# expect-distinct-presentation` in a route uses the same formula, so a
generated frame never passes as a rendered one.

## Measurement

The M1 method of docs/MACOS.md: the scripted free-roam route, GPU median
over game frames 2500-5500, macOS 26, MoltenVK 1.4.1. For each stage,
compare against the control run: presents a second against source frames a
second, the GPU median (the generation's cost), distinct presents unchanged,
and the route's captures bit-exact (captures are real frames).

| Stage | Result |
| --- | --- |
| 0: settings, backend abstraction, counters | Landed; no visible change. |
| 1: history, generated present, pacing (`repeat`) | |
| 2: MetalFX, depth, zero motion | |
| 3: HUD as its own layer | |
| 4: camera motion vectors | |

## Open questions

- Whether MetalFX accepts the presenter's `RGB10A2Unorm` colour and an
  `R32Float` depth (fall back to `RGBA16Float` and a conversion pass).
- Whether a MoltenVK device-local image exports as a private Metal texture
  with the usage the interpolator asks for.
- Whether MoltenVK's timeline semaphore values match the exported
  `MTLSharedEvent` values directly (fallback: in-order commits on the
  exported queue, valid while MoltenVK's synchronous submits are on).
- The host depth encoding and the game's depth direction.
- The generation cost at 1280 × 720 on the M1's 8-core GPU (expected 2-4 ms).
- Where the game writes its view and projection matrices (stage 4; recorded
  in docs/REVERSE_ENGINEERING.md when found).
