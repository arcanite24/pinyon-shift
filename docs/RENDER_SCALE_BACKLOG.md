# Render scale backlog: below 1x, fractional and dynamic

Created 2026-10-31 at `dev` `7e07fe5d` (ShiftGlue `a069c91f`). Goal: let a
weak GPU render the game below the console's 1280x720 (50 %, 67 %, 75 %),
let a 1080p screen get 1.5x, and later let the renderer pick the scale each
frame from the GPU time. This backlog takes over the non-integer and dynamic
scale decisions recorded in NP-4.8, the runtime-scale item NP-4.9 and the
1.5x idea in [NATIVE_PORT_BACKLOG.md](NATIVE_PORT_BACKLOG.md), and the
sub-1x note in [LOW_SPEC_BACKLOG.md](LOW_SPEC_BACKLOG.md). It builds on the
R02 study, [SUB_1X_RENDER_SCALE.md](native-renderer/SUB_1X_RENDER_SCALE.md),
which maps the integer contracts and sizes a fixed half-scale path; that
study's file references are not repeated here.

Items are `RS-*`. Vulkan comes first: it is the renderer on every platform.
D3D12 is legacy and either gets the same path late (RS-7.4) or hides the
new options.

## Where it stands

- **The scale is an integer, 1x to 4x.** `draw_resolution_scale_x/_y`. Every
  EDRAM surface holds scale x scale host pixels a guest pixel; resolves write
  a scaled copy into the scaled resolve buffer (integer scale-squared 16-byte
  groups); the texture cache maps resolved ranges by integer area; the
  translator bakes the scale into shaders as a modification bit; the shader
  pack is per scale (NP-4.7 switches between prepared packs in about a
  second on D3D12; Vulkan restarts).
- **1x is the floor.** Low-spec presets cut shadows, the environment map
  rate, MSAA and texture size, but not pixels. The ULTRA LOW 30 preset
  does not hold 30 on Blindvac's UHD 620 or 930MX (2026-10-29, LS-1.8).
- **The prize is not measured.** R02's only number is an optimistic area
  model of one archived Odin race: the main-scene draw span is 6.44 of
  15.70 ms, so ideal scaling of that whole span saves 30.7 % at 0.5x and
  17.9 % at 0.75x, before added cost. Nothing has been run below 1x.
- **What helps already.** The presenter upscales any source size (bilinear,
  CAS, FSR 1; FSR 2/3 and DLSS with the game's depth, motion and jitter,
  UPSCALING_BACKLOG UP-1). The guest video mode is a cvar
  (`video_mode_width/_height`, read by `xboxkrnl_video.cpp`), and the game
  never learns the host scale.
- **Pieces to reuse** (survey at ShiftGlue `a069c91f`):
  - The Vulkan executor already scales viewport, scissor and system
    constants per draw: `draw_coordinate_scale()` returns 2 for
    shared-depth-alias draws (`include/rex/graphics/vulkan/fh1_native_executor.h`,
    applied in `vulkan/command_processor.cpp`). A raster fraction is a
    second factor in the same place.
  - `fh1_coarse_shading` assigns a fragment shading rate per named
    rendering through `VK_KHR_fragment_shading_rate`. It costs nothing to
    try and approximates the fragment half of the prize (RS-0.3).
  - The DLSS provider already has `InRenderSubrectDimensions` plumbed, and
    the temporal dispatch takes its render size from the source; a
    top-left sub-rectangle input is what RS-4.2 needs.
  - Today's temporal "quality" modes downsample the finished 720p frame
    with CAS before FSR or DLSS (`src/ui/presenter.cpp`): extra work and
    no rendering saved. RS-4.2 replaces that.

## Design: integer storage scale times a raster fraction

R02 proposed resizing the executor's images to half size. This backlog
splits the scale into two numbers instead:

- **Storage scale `N`**, the integer we have: surface images, the scaled
  resolve buffer, resolve-derived textures and the shader pack's
  scaled-texture rules stay exactly as at N today.
- **Raster fraction `f`**, a runtime value in (0, 1]: draws into the frame's
  scene-sized surfaces use a viewport and scissor of `f` times their normal
  host rectangle, in the top-left corner of the unchanged image. A resolve
  from such a surface samples the `f` rectangle and writes the full
  N-scaled destination, so everything downstream (textures, post passes,
  CPU readbacks, thumbnails) sees the sizes it sees today.

The effective scale is `N x f`:

| Setting | N | f | Scene raster | Memory |
| --- | ---: | ---: | --- | --- |
| 50 % | 1 | 1/2 | 640x360 | as 1x |
| 67 % | 1 | 2/3 | 853x480 | as 1x |
| 75 % | 1 | 3/4 | 960x540 | as 1x |
| 1x | 1 | 1 | 1280x720 | as 1x |
| 1.5x | 2 | 3/4 | 1920x1080 | as 2x |
| 2x | 2 | 1 | 2560x1440 | as 2x |
| 2.5x | 3 | 5/6 | 3200x1800 | as 3x |
| Dynamic | N | f varies per frame | | as N |

Why this shape:

- **One mechanism for sub-1x, 1.5x and dynamic resolution.** `f` changes
  between frames without reallocating anything, which is what dynamic
  resolution needs. 1.5x costs 2x memory but only 1.5x raster.
- **The integer contracts stay.** EDRAM periods, transfer flags, resolve
  constants, texture identity and the per-N shader pack are untouched. Only
  three things learn `f`: the host viewport and scissor, resolve sampling,
  and pixel-position conversion in shaders (RS-2).
- **Transfers stay identity.** Every scaled surface in a frame uses the same
  `f`, so an EDRAM reinterpretation between two of them copies the same
  top-left rectangle.
- **The HUD can stay sharp.** If the front buffer is left at `f = 1`
  (RS-3.2), the tone map reads the upsampled scene and the HUD is drawn
  at full resolution on top.

What it gives up: resolve writes, resolve-sourced texture reloads and the
post passes that read full-size textures cost what they cost at N. That is
R02's "compatibility prototype" trade, made deliberately. A compact layout
(textures physically at `N x f`) is RS-8, only if RS-0 shows that the
retained traffic eats the prize.

## Risks and open questions

| Risk | Settled by |
| --- | --- |
| The prize is too small: geometry, front end and barriers dominate the weak GPUs too | RS-0.2 and RS-0.3, before any real work |
| A surface used both as a scene target and as a fixed-size target (shadow atlases partly overwritten by a 1280x720 resolve, `site/findings/rendering.toml`) gets the wrong policy | RS-1.1 census; policy keyed on the surface, not the draw |
| Shaders that compute screen positions from the pixel position (depth-based effects, the 640x360 and bloom chains) read the wrong texel | RS-2.3 translator change, verified with captures |
| Predicated tiling bands (256, 256, 208 rows) have odd endpoints at 2/3 and leave seams | RS-2.2 shared floor/ceil rule; band-edge captures in RS-6 |
| Content that stays in EDRAM across frames is at the old `f` after a change | RS-5.2: rescale or discard at the frame boundary |
| Upsampling a packed or depth format by filtering mixes bits | RS-2.4: nearest for depth, stencil, integer and packed reinterpretations; filter only after unpacking to colour |
| Temporal upscalers get a 720p grid labelled as 360p | RS-4.2 feeds them the `f` rectangle itself |
| Photo mode and car thumbnails look soft | RS-3.3 renders them at `f = 1` |

## Verification rules

- **Measure before building.** RS-0 sets the prize on the devices this is
  for: Blindvac (UHD 620, reachable over SSH), the Deck, the Odin and the
  Fold6. No item past RS-1 starts unless RS-0.3's probe saves at least
  **25 % of the GPU frame at 50 %** on two of them.
- **A/B inside one run** with the hot cvar toggled, in both orders, A/A
  control, transition frames dropped (the Android in-run method); report
  pairs, median and spread.
- **Pixel identity is not the criterion below 1x.** Captures are compared
  side by side for missing passes, seams at band edges, shifted or
  shimmering post effects, exposure, HUD, bloom, shadows, reflections and
  thumbnails. At `f = 1` the golden replays must stay bit-exact.
- **Kept and rejected results** go on the site (Internals pages, or the
  "What didn't pay off here" table in `site/pages/lessons.md`), and any
  guest fact found on the way gets a `site/findings` record.

## Items

### RS-0 Prize and spikes (gate for everything else)

| Item | Work | Gives | Size | Status |
| --- | --- | --- | --- | --- |
| RS-0.1 | **Guest-side spike**: start the title with `video_mode_width/_height` at 640x360 and at the SD 640x480 mode and see whether FH1 sizes its surfaces from the video mode; then look for where the main view's 1280x720 comes from (the Hor+ hook reads it at `sub_823E22C8`; the leftover split-screen code in `site/findings/systems.toml` suggests the engine can draw a scene into a smaller view). If the game can render natively small, there is no reconstruction at all and this backlog may shrink to a presenter change. Record the answer either way in `site/findings` | Rules out (or in) a near-free path | S (hours to 2 days) | **Video mode done, negative** (see Progress); the main-view and split-screen dig is open |
| RS-0.2 | **Current-pin GPU profiles at 1x** with `fh1_native_gpu_profile` on Blindvac (UHD 620), the Deck, the Odin and the RTX 4080: race and free roam, the device's own preset, plus 2x where the device can run it. The 1x-to-2x growth bounds the area-proportional work from above (`T(2) - T(1) <= 3 x pixel work at 1x`, an overestimate because resolves also grow) | A per-device ceiling for the prize | S-M | Open; on Blindvac the RS-0.3 probe measured the slope directly, so only the phase breakdown is left there |
| RS-0.3 | **Raster-only probe**: first, `fh1_coarse_shading=2x2` on the scene renderings where the device has the extension (no code; fragment work only). Then a debug cvar that multiplies `draw_coordinate_scale()` by `f` for scene-surface draws and nothing else. The image is wrong (a corner of the frame, stretched later), but the GPU does exactly the raster work the real path would. In-run A/B of `f = 1, 0.75, 0.5` on the same devices. This measures the prize directly, before the 3-4 weeks of real work | The gate number | S-M | **Probe built** (`fh1_debug_raster_percent`, `fh1_debug_raster_pitches`); **UHD 620, Steam Deck and RTX 4080 done** (see Progress); Odin open |
| RS-0.4 | **Decision**: keep going, cut to 50 % only, or record the rejection in `lessons.md` with the numbers | Go / no-go | S | Open |

### RS-1 Surface policy

| Item | Work | Gives | Size | Status |
| --- | --- | --- | --- | --- |
| RS-1.1 | **Surface census** from a race and a free-roam frame log: every EDRAM surface and resolve with its extent, format and consumers, sorted into "follows the screen" (1280x720 scene, 1280x512 band area, 640x360 and the bloom chain) and "fixed" (1024x1024 shadow atlases, reflection and env maps, 32x32 luminance, thumbnails, UI). Records go to `site/findings/rendering.toml` | The policy table | M | Open |
| RS-1.2 | **Policy in the executor**: each surface carries `f` (1 for fixed surfaces), decided once at creation from the census rule (extent relative to the video mode), with a debug override per surface key | Only screen-sized work shrinks | M | Open |
| RS-1.3 | **Shadow maps on their own knob**: if the census shows shadow raster is a large share on the weak GPUs, a shadow-resolution fraction reuses the same mechanism instead of the screen `f` | Separate quality trade | S after RS-1.2 | Open |

### RS-2 The raster fraction in the executor and translator

| Item | Work | Gives | Size | Status |
| --- | --- | --- | --- | --- |
| RS-2.1 | **Runtime `f` in the command processor and executor** (`draw_resolution_raster_fraction`, a rational with a small denominator), applied at frame boundaries only; `f = 1` takes today's code path unchanged | The plumbing | S-M | Open |
| RS-2.2 | **Viewport, scissor, clears and tiling bands**: one guest-to-host rectangle function with a single floor/ceil rule (start floored, end ceiled, never empty), used by `GetHostViewportInfo` (which today rounds to whole guest pixels and then multiplies), scissors, clears, the predicated-tiling window offsets and the untiled copy-down. Half-pixel offset applied in host pixels. Point sprite size, the depth-bias slope factor and the occlusion sample normalization use `N x f` instead of `N` | Seamless bands at 2/3 | M | Open |
| RS-2.3 | **Pixel position in shaders**: the translator converts the fragment position to guest pixels with a reciprocal it reads from the system constants (push constants on Vulkan) instead of only the baked integer, so one pack per N serves every `f`. New translation flag and pack identity. Memexport from pixel shaders ("once per guest pixel", an integer modulo rule today) needs a rule for host pixels that cover more than one guest pixel; first check whether FH1 uses it at all. This is also NP-4.9's first step | Correct screen-space reads | M | Open |
| RS-2.4 | **Resolves from the `f` rectangle**: the resolve and the direct resolve-to-texture path sample the source rectangle and write the full N-scaled destination. Nearest for depth, stencil, integer and packed reinterpretations; bilinear after unpacking for colour formats. Small CPU-read resolves (luminance, thumbnails) are reconstructed at guest size before the readback queues see them | Everything downstream unchanged | L | Open |
| RS-2.5 | **Transfers and aliases**: EDRAM reinterpretations between two scaled surfaces copy the `f` rectangle; a transfer between a scaled and a fixed surface (if RS-1.1 finds one) resamples | Ownership changes stay correct | M | Open |
| RS-2.6 | **Guest MSAA below 1x**: force `fh1_msaa_single_sample` while `f < 1`, unless RS-0 shows the 2x samples are cheap there | One fewer combination to qualify | S | Open |

### RS-3 Image quality

| Item | Work | Gives | Size | Status |
| --- | --- | --- | --- | --- |
| RS-3.1 | **Better upsampling of the main scene resolve**: EASU (FSR 1's edge-adaptive upsample) or Catmull-Rom instead of bilinear for the 1280x720 `2_10_10_10` scene resolves only; measure its cost on the weak GPUs | Less blur at 50 % | M | Open |
| RS-3.2 | **Full-resolution front buffer and HUD**: the front buffer stays at `f = 1`, so the tone map and the HUD run at full size. Measure the tone map's cost; if it matters, the alternative is a scaled front buffer with UP-1.2's HUD composite | Sharp HUD and text | S | Open |
| RS-3.3 | **Photo mode and thumbnails at full resolution**: `f` goes to 1 for the frames that feed a photo or a car thumbnail, through the same frame-boundary switch | Saved images unchanged | S-M | Open |

### RS-4 Presenter and upscalers

| Item | Work | Gives | Size | Status |
| --- | --- | --- | --- | --- |
| RS-4.1 | **Spatial output scaling unchanged**: the presenter still gets an N-scaled front buffer, so bilinear, CAS and FSR 1 work as today | No presenter change for v1 | S (check) | Open |
| RS-4.2 | **Temporal upscalers from the real low-resolution grid**: FSR 2/3, DLSS and later XeSS take the pre-HUD scene's `f` rectangle with depth and motion at the same size, jitter scaled to it, and the dynamic-resolution input-size field set each frame. Requires choosing where the HUD-less colour comes from at `f < 1` | DLSS/FSR quality from 50 % input | M-L | Open |
| RS-4.3 | **Named upscaler modes on top**: Quality, Balanced, Performance and Ultra Performance map to an `N x f` pair for the output size (UP-2.1's open item) | The usual PC presets | S after RS-4.2 | Open |

### RS-5 Settings and dynamic resolution

| Item | Work | Gives | Size | Status |
| --- | --- | --- | --- | --- |
| RS-5.1 | **RESOLUTION SCALE as percentages**: 50, 67, 75, 100, 150, 200, 250, 300, 400 in the in-game settings and both launchers, written as `N` plus `f`; existing configs keep their integer. The info line shows the raster size ("RENDERS AT 960x540"). Changes between values with the same N apply live on Vulkan too | The player-facing setting | M | Open |
| RS-5.2 | **Frame-boundary switching**: on an `f` change, rescale or invalidate EDRAM contents that persist across frames, reset temporal history, mark the transition for routes (`cvar` route command) | Clean live changes | M | Open |
| RS-5.3 | **Presets**: ULTRA LOW 30 and LOW-SPEC 60 get the scale RS-6 measures on Blindvac, the Deck and the Odin; the launcher's preflight recommends it for integrated graphics | Weak machines start playable | S | Open |
| RS-5.4 | **Dynamic resolution**: a controller reads the executor's GPU frame time (timestamps already exist), moves `f` between a floor and 1 in steps of 1/16 with hysteresis, never more than once every few frames; on when the frame limit is set. Setting: DYNAMIC (target from the frame limit) | Holds the frame rate in heavy scenes | M | Open |

### RS-6 Qualification and keep/reject

| Item | Work | Gives | Size | Status |
| --- | --- | --- | --- | --- |
| RS-6.1 | **Image matrix**: race and free roam, tiled and untiled, day and night, every resolve kind, exposure through a tunnel, HUD, bloom, sun shadows on, reflections, a saved thumbnail reloaded, photo mode; at 50, 67, 75 % and 1.5x | No missing passes | M-L | Open |
| RS-6.2 | **Performance gate**: in-run A/B per device; keep 50 % if the GPU frame drops at least 25 % on Blindvac's UHD 620 and the Odin with pacing inside the A/A spread; keep 1.5x if it costs clearly less than 2x on the RTX 4080 at the same image size on a 1080p output | Kept or rejected, with numbers | M | Open |
| RS-6.3 | **Docs**: `site/pages/renderer.md` (Scaling), `playing.md` (no longer "whole multiples only"), `troubleshooting.md`, `site/features.toml`, `lessons.md` | The site matches `dev` | S | Open |

### RS-7 Later

| Item | Work | Gives | Size | Status |
| --- | --- | --- | --- | --- |
| RS-7.1 | **Fully runtime N** (rest of NP-4.9): the scale as a constant instead of a pack bit for scaled-texture and resolve paths, so N changes live on Vulkan with one pack | No restarts for any scale | L | Open |
| RS-7.2 | **Per-pass fractions**: bloom chain, depth-of-field or the 640x360 target at a lower `f` than the scene, if RS-1.1 shows them large | Finer trades | M | Open |
| RS-7.3 | **Android and macOS specifics**: the merged-band path, Adreno tile memory (a smaller viewport in a full-size image may not save bin passes; check with the Odin GPU counters), MoltenVK | Phones and the Mac mini | M | Open |
| RS-7.4 | **D3D12** gets the same path, or the sub-1x options are hidden there | Parity or a clear limit | M | Open |
| RS-7.5 | **Coarse shading as a setting**: if RS-0.3 shows `fh1_coarse_shading` gets most of the prize on GPUs that have the extension, offer it as a quality option beside the scale (sharp edges, coarser shading), with no reconstruction work | A cheaper alternative on capable GPUs | S | Open |

### RS-8 Compact fractional storage (only if RS-0 or RS-6 demands it)

Keep render-derived textures physically at `N x f` through post passes,
reflections and resolves, with a new scaled-resolve layout, texture identity
and alias tracking, and expand only CPU-visible outputs. R02 estimates two
to four engineer-weeks. It saves resolve and reload bandwidth that the
design above keeps; start it only if a profile at `f = 0.5` shows resolves,
transfers and post passes holding most of the remaining frame.

## Rejected or set aside

- **A percentage typed into the existing integer setting** (R02): the
  integer is in shader fields, EDRAM groups and pack names.
- **Shrinking the images themselves for a fixed 0.5x** (R02's first
  choice): it works for one fraction, but every change reallocates surfaces,
  so it cannot grow into dynamic resolution or 1.5x. The raster fraction
  gives the same saving with a smaller change.
- **Downsampling a normal 1x frame**: saves no rendering work.

## Order and estimate

RS-0 first: about a week, mostly device time, and it can end the backlog.
Then RS-1 and RS-2 (2-3 weeks), RS-3.2/3.3 and RS-5.1/5.2 for a first
shippable 50/67/75 % and 1.5x behind an off-by-default setting, RS-6, then
RS-4.2, RS-5.4 and the rest. Planning estimates, not measurements.

## Progress

**2026-10-31, RS-0.1 (video mode).** With `--video_mode_width=640
--video_mode_height=480` (not widescreen, not HD) `fh1-race-sync` drew and
presented exactly as at 720p: all captures 1280x720 with the 16:9 HUD. The
title calls `VdQueryVideoMode` but does not size its targets from it, so the
video mode cannot make it render smaller (finding "render size ignores the
video mode" in `site/findings/rendering.toml`). Whether the main view's size
can be changed in guest code is still open.

**2026-10-31, RS-0.3 (raster probe), ShiftGlue `a069c91f` plus the probe,
Release `5998377`.** `fh1_debug_raster_percent` (hot reload) shrinks the
viewport and scissor of draws into surfaces whose pitch (32bpp tiles) is in
`fh1_debug_raster_pitches`, into the top-left corner; resolves, transfers
and clears keep their size, so the image is wrong by design. Route: seed
`appdata-2026-09-27`, `fh1-race-sync` to the moving race, then 13 blocks of
240 (Blindvac) or 480 (multivac) output frames in the order
100/50/75/100/75/50 twice and a final 100, a capture marking each switch.
Per block: median `guest_frame_gpu_time_ns` from the perf CSV, the first
second after a switch dropped. Ratio = block over the mean of its
neighbouring 100 % blocks; four pairs per fraction in one run.

| Device, preset | Surfaces shrunk (pitch) | 50 %: GPU ratio (4 pairs) | 75 %: GPU ratio | 100 % GPU ms |
| --- | --- | --- | --- | --- |
| RTX 4080, 1x, uncapped | 16 | 0.991-1.024 (median 1.006) | median 1.000 | 5.9-8.7 (drifts with the route) |
| UHD 620 (Blindvac), LOW-SPEC 60, 1x | 16 | 0.784-0.839 (median 0.809) | 0.858-0.901 (0.890) | 65-73 |
| UHD 620 | 16, 32 (all 1280-wide surfaces) | 0.673-0.713 (**0.705**) | 0.817-0.836 (0.818) | 73-76 |
| UHD 620 | 13 (the 1024x1024 shadow maps) | 0.992-0.997 (0.995) | 0.985-1.006 (0.996) | 70-72 |
| UHD 620 | 4-32 (every surface but tiny ones) | 0.655-0.665 (0.662) | 0.798-0.832 (0.810) | 73-75 |

What it shows:

- **The UHD 620 is GPU-bound** (frame time follows GPU time within 1 ms)
  and about 40 % of its frame scales with the area of the 1280-wide
  surfaces: fitting `T = fixed + pixels x f^2` gives 39 % from the 50 %
  blocks and 42 % from the 75 % blocks. Shrinking them to 50 % saves
  **29.5 %**, above the 25 % gate; 75 % saves 18 %.
- **Pitch 32 matters as much as pitch 16.** Pitch 16 alone saved 19 %;
  the 1280-wide surfaces at pitch 32 (wider formats) add the rest. RS-1.1's
  policy must key on the width in pixels, not on one pitch.
- **Shadow maps are not where the time goes** on this route: shrinking the
  three 1024x1024 maps changed nothing, so RS-1.3 is dropped unless another
  device disagrees. The 640x360 chain and the other small surfaces add
  about 4 points more.
- **The RTX 4080 saves nothing**, as DR-0.1 predicted (front end and
  barriers, not pixels). Sub-1x is for weak GPUs only.
- 50 % takes the UHD 620 from about 74 to 52 ms, not to 33: below 1x helps
  the weakest GPUs, but it does not bring them to 30 fps alone.

Limits: one device passes so far, one run per configuration (two of the
six runs had to be repeated: a Vulkan device loss while loading and a
route wait timeout before the race, both before the probe was active). The
probe also shrank the front buffer and HUD, which RS-3.2 keeps full size,
and it has none of the real path's resolve reconstruction, so the real
saving will be smaller; RS-0.2's phase breakdown should size the resolves.

**2026-10-31, RS-0.3 on the Steam Deck LCD** (dev `146e65bd`, ShiftGlue
`9b8e8473`, Linux v3 build, now also the play build). Same route with
480-frame blocks, pitches 16 and 32, started from a temporary Steam
shortcut so the GPU ran at game clocks (sampled 995-1284 MHz, `auto`),
120 limit and vsync off so the GPU never waits; two runs, eight pairs per
fraction:

| Run | 50 %: GPU ratio | 75 %: GPU ratio | 100 % GPU ms |
| --- | --- | --- | --- |
| a | 0.821-0.864 (median 0.854) | 0.872-0.995 (0.904) | 14.6-16.8 |
| b | 0.828-0.865 (median 0.861) | 0.881-1.080 (0.904) | 14.6-17.5 |

The Deck saves **14.5 %** at 50 % and 10 % at 75 %: about 20 % of its
frame scales with the 1280-wide surfaces, half the UHD 620's share. It
fails the 25 % gate. Its GPU is near its 1x frame budget already (about
15 ms), so the saving moves it from about 65 to 77 fps of GPU headroom;
the 75 % outliers are each run's first 75 % block, right after the first
switch. The `auto` clock may drop on the lighter blocks, which would hide
part of the saving, but that is how players run it.

So far: UHD 620 passes (29.5 %), the Deck fails (14.5 %), the RTX 4080 has
nothing to gain. The gate needs two devices; the Odin decides it (its
Adreno bins the frame into tiles, so a smaller viewport may cut whole bin
passes). Next: the probe on the Odin, then RS-0.4.
