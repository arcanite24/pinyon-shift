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
- **Threads.** The game's swap publishes the frame on the GPU Submission
  thread as today. Where the presenter paints from that thread (a mailbox
  swapchain, no menus), it paints the generated frame there and a
  presenter-owned pacing thread paints the real one later, so the submission
  thread never waits. Where the UI thread paints on request (MoltenVK offers
  only FIFO and immediate present modes, so with vsync on macOS always paints
  from the UI thread), the publish and the pacer each ask the window for a
  paint and the UI thread paints the generated or the real frame; a real
  frame waiting to be painted goes before a newer generated one.
- **When it runs.** Only without menus or overlays (they show real frames and
  the pair history starts over), and only while twice the base rate fits
  under what the host shows: the frame rate limit, and the display's refresh
  on a FIFO swapchain. On a 60 Hz panel that means a base rate of 30 fps or
  less; above it the presenter waits, logs why once, and shows real frames.
- **Dropped frames.** A real frame the display could not take before the next
  frame arrived is dropped (it lives on inside the next generated frame) and
  counted in `dropped_present_count`; a generated frame whose pair was
  superseded is simply not shown.
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
| 1: history, generated present, pacing (`repeat`) | M1, `fh1-open-world-performance` at the game's 20 fps limit (so twice the base rate fits the 60 Hz panel), 779 title frames each: control 16.8 presents a second, all real; `repeat` 28.3 presents a second, of which 14.5 generated and 13.8 real, 24 real frames dropped, GPU median unchanged (52.0 against 52.2 ms). The missing real frames are the FIFO limit: the UI thread paints every frame on macOS and one paint blocks for a vblank, so when the title releases a frame early the generated frame of the previous pair gives way to it. `fh1-hfr-modes-control` with `repeat` against a control run: four of its five capture gates pass; the map capture's changed-pixel ratio is 0.29 against its 0.15 limit at a mean error of 3.4 (limit 4), the drive's timing noise, and the content matches. `fh1-smoke` passes. The `fh1-source-60` gate (55 distinct frames a second) is out of the M1's reach with or without generation. |
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
