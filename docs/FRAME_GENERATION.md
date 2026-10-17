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
(the HUD as its own layer, optionally depth and camera motion) and in using
a model built for the job: MetalFX runs its own optical flow, so it finds the
motion between the two finished frames rather than warping one of them.

## Backends

| Setting | Backend | Status |
| --- | --- | --- |
| `off` | none | default |
| `metalfx` | Apple MetalFX frame interpolation (`MTLFXFrameInterpolator`, macOS 26, Apple silicon). The presenter's history and output images are exported to Metal through `VK_EXT_metal_objects` (MoltenVK) and the interpolator runs on the Metal queue MoltenVK exports from the Vulkan graphics queue | on, colour only |
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
- **Inputs by stage.** Stage 2: the two finished frames only. A probe on the
  M1 (below) showed MetalFX interpolating correctly from the colour pair with
  no depth and no motion texture, both of which its interface marks optional,
  so neither is plumbed yet. Stage 3: the scene before the HUD as the colour
  and the composited frame as the UI layer, so the HUD is never warped.
  Stage 4: depth and camera motion vectors, if a measurement shows they
  reduce ghosting enough to be worth the extra passes and the matrix hook.
- **History reset.** The first frame after enabling; a size or bit-depth
  change; a publish gap above max(3 × median, 250 ms) (loading, pause,
  video, alt-tab); leaving guest-thread painting; a backend failure. From
  stage 3 on, also a frame without a pre-HUD snapshot (menus, video, photo
  mode). MetalFX needs two frames after a reset before it interpolates (the
  probe showed the first generated frame equal to the current one); the
  pacer's one-frame-since-reset skip already covers this.

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
| 2: MetalFX, colour only | M1, `fh1-open-world-performance` at the game's 20 fps limit, 805 source frames in 46.7 s. MetalFX ran its own optical flow over the colour pair, no depth or motion texture. Present rate 21.8 a second (17.2 source, 10.1 generated, 11.7 distinct real), against the control's 16.6, all real. The frame-time median was unchanged (50.8 against 51.6 ms): the interpolation runs on the Metal queue between frames, not inside a frame. The generation cost 7.3 ms a frame (Metal GPU timestamps), close to the 6.3 ms the probe measured. 153 real frames were dropped and 436 generations skipped: the first MetalFX version waits for the Metal command buffer to complete inside the paint, so each generated frame holds the paint thread about 7 ms, and on the FIFO/UI-thread path that time comes out of the real frames. The asynchronous handoff reserved in the inputs (a Metal shared event from the timeline semaphore) is the next measurement; it should return the distinct rate to the control. The route's free-roam captures are wall-clock nondeterministic (two control runs differ by MAE 92-98, against MetalFX-to-control MAE 20-27), so they do not gate this stage. |
| 3: HUD as its own layer | |
| 4: depth and camera motion vectors (if measured worthwhile) | |

## What the M1 probe settled (2026-10-16)

A standalone Metal probe (not in the build; MetalFX framework only, Apple M1,
macOS 26) answered the questions that shaped stage 2:

- **Colour-only interpolation works.** With `RGB10A2Unorm` colour and output,
  no depth texture and no motion texture, `MTLFXFrameInterpolator` produced a
  correct temporal midpoint: a bar moving ten pixels a frame landed within one
  pixel of the midpoint once the history had two frames. Supplying a correct
  motion texture changed nothing; supplying none changed nothing. MetalFX runs
  its own optical flow over the colour pair.
- **The first frame after a reset is a copy.** With `shouldResetHistory`, and
  on a flat fill with no features, the output equalled the current frame; the
  midpoint appeared only from the third encode. The pacer's existing skip of
  the one-frame-since-reset case matches this.
- **Cost is 6.3 ms a frame at 1280 × 720** on the M1 (mean of 100,
  `GPUEndTime − GPUStartTime`), higher than the 2-4 ms guessed. At the game's
  20 fps that is about 13 ms of generation a second, well inside the headroom
  to the 60 Hz panel, but it is added GPU work the real frames share.
- **Formats:** the interpolator was created for `RGB10A2Unorm` colour and
  output and `RG16Float` motion; it rejected an invalid colour format but
  accepted an invalid (absent) depth and motion format. No `RGBA16Float`
  conversion pass is needed.

Open, deferred to their stages:

- Whether a MoltenVK device-local image exports as a private Metal texture
  with the usage the interpolator asks for (stage 2 logs it at startup).
- Whether depth and camera motion vectors reduce camera-pan ghosting enough
  to justify the depth snapshot and the matrix hook (stage 4; the game's
  depth direction and where it writes its matrices are recorded in
  docs/REVERSE_ENGINEERING.md if that work happens).
