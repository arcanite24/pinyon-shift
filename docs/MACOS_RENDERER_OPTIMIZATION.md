# Making an Xbox 360 recompilation fast on macOS

A reference for anyone bringing a recompiled Xbox 360 game to Apple
silicon through MoltenVK. It records how Pinyon Shift (a recompilation of
*Forza Horizon*) took its free-roam frame on a MacBook Pro M1 from 131 ms
to 19 ms between 2026-10-15 and 2026-10-18, what each step measured, why
it worked, and what did not pay off. The method and most of the findings
are about MoltenVK, Metal and Apple's tile-based GPUs, not about one game,
so they should transfer to any Vulkan renderer that translates Xenos
shaders and replays the console's render passes.

Everything here is the project's own analysis. There is no game code,
disassembly or game data in it (see `LEGAL.md`).

## The machine and the method

Measured on a MacBook Pro M1 (8-core GPU, 16 GB), macOS 26, MoltenVK 1.4.1
pinned at upstream `db445ff2`, SDL 3, 1280×720 internal resolution (1x),
window hidden, frame rate uncapped unless stated. The scene is the game's
free-roam drive from the save's spawn, driven by a scripted route (throttle
with alternating steering for 3,000 frames). Numbers are the GPU time
median over the driving frames, with the 95th percentile in brackets.

Six rules made the numbers trustworthy. Each exists because its absence
produced a wrong number first.

1. **Measure the scene, not the run.** The route spends 80 % of its frames
   on the title and loading screens at 17 ms. The drive runs at 71 ms. A
   whole-run median is a menu benchmark. Filter the per-frame log to
   frames with more than 800 draws and size any periodic statistics window
   so it lands inside the drive.
2. **Bracket every change with its own controls.** The M1 throttles across
   back-to-back runs: the same binary measured 56 ms as the day's first
   run and 63 ms as the fourth. Run control, change, control, and quote the
   change against the controls on either side of it.
3. **Check that the run is valid before reading it.** Capture positions
   must show the car drove the route (550-670 m here, not 20 m), no frame
   may exceed 0.5 s, and the pipeline-compile count must match the
   controls. A run that stalled compiling 220 pipelines mid-drive read
   46.5 ms for a change whose valid run read 49.2.
4. **The first run of a rebuilt binary is a warm-up.** Any change to the
   translated shaders' Metal source makes Metal recompile every pipeline on
   the first run: 1-9 s stalls, the car never leaves spawn. Run each route
   once, then measure. Routes that share few pipelines each need their
   own warm-up.
5. **Keep the disk and memory free.** Under 1 GB free with 32 GB of swap
   in use, the same binary measured 105-121 ms where it measures 71 with
   15 GB free. Each hidden run writes a 1.3 GB shader cache; delete it as
   the chain goes. One build or one game run at a time on 16 GB.
6. **Check the image, by eye, on a route that lands captures on fixed
   frames.** Mean absolute error against a control cannot tell a
   rendering artifact from camera sway on a non-deterministic route (the
   control-to-control spread was 5-6 here and the artifact was inside it).
   The glints described below were only visible by looking.

Tools that did the work, all on the Mac itself:

| Need | Tool |
| --- | --- |
| Per-encoder GPU time, the gaps between encoders | `xcrun xctrace record --template 'Metal System Trace' --attach <pid> --time-limit 6s`, then export the `metal-gpu-intervals` table and sum busy and idle per game frame |
| What Metal actually compiles from a translated shader | `MVK_CONFIG_SHADER_DUMP_DIR=<dir>` to write the MSL, then `xcrun -sdk macosx metal -std=macos-metal2.4 -O2 -S -emit-llvm <file>.metal` and count the IR operations and calls |
| Time per render pass | The renderer's own timestamp profile, once its query pool fits Metal (see "Traps") |
| Which code ends passes and issues barriers | Counters in the renderer, attributed to the caller, logged per 100 frames |
| Stage bounds | Debug switches that replace every pixel shader with a constant write, or discard primitives after the vertex stage: the frame time with a stage removed bounds that stage |
| Frame rate on screen | Apple's Metal performance HUD, `MTL_HUD_ENABLED=1` set before the first layer is created |

## The frame, in order of what was found

### 1. A configuration bug: 131 → 89 ms

The first measurement had the renderer refreshing its CPU-visible page
state every frame, because a settings file created before the game's first
start had pinned the setting on. The symptom was indirect: turning shadows
off removed 700 draws and five sixths of the EDRAM transfers for no gain.
Fitting GPU time against render-pass restarts across seven settings runs
gave `0.24 ms × restarts + 4.5 ms` (R² 0.94): on Apple's tiler every
restart reloads and stores the colour and depth attachments, and 360 of
the 521 restarts a frame came from CPU-to-GPU memory uploads issued in the
middle of a pass, which the page-state refresh caused by invalidating every
uploaded page each frame. The intended default cut restarts to 184 and
the frame to 89 ms.

Lesson: on a tile-based GPU, count render-pass restarts before looking at
shaders, and check the configuration a first start wrote.

### 2. Uploads hoisted out of the pass: 71 → 56 ms

Of the remaining ~290 restarts a frame, 92-141 ended for shared-memory
uploads and 53-91 for resolves. The uploads were the guest's streamed
vertex and index data arriving one small range at a time, each discovered
by the draw that reads it after the previous draw's pass was already open.
The fix moves the upload (barrier, copies, barrier) in the recorded command
stream to just before the open pass's begin, so the GPU copies first and
then runs one unbroken pass. Guest order is preserved: on the console a CPU
write landing between two draws of a pass races the GPU either way, so
reordering a draw's reads ahead of the pass is safe; a draw that may write
shared memory marks its pass so later uploads stay in order, and any other
reason to end the pass cancels the hoist.

| Run | Drive GPU ms (p95) | Passes a frame | Uploads hoisted a frame |
| --- | ---: | ---: | ---: |
| hoist off | 71.8 (115) | 211, 302 | 0 |
| hoist on, three runs | 56.4, 57.0, 56.8 (103-105) | 88-90, 165-174 | 117-178 |

Then the hoisted uploads of one pass were merged into one barrier pair and
one run of copies, since each had been its own barrier-copies-barrier and
each paid the 20-50 µs encoder-boundary gap the trace showed: 60.9/56.8 ms
controls to 53.9 ms, barrier batches 642-696 to 321-363 a frame.

What a restart actually costs was measured directly by splitting the draw
pass every 4 draws (same image): 170-174 → 402-569 passes took the frame
from 56.8 to 80.2 ms, about **0.06 ms a restart** at 1x. The 0.24 ms fit
above had been taken across runs where every restart also carried a stalled
copy. So after the hoist the remaining restarts were worth about 10 ms, and
the rest was shading.

### 3. Resolves cannot be hoisted: a negative

After the hoist, resolves ended 87-90 passes a frame, one per resolve. A
census counter on the resolve's sources found that in 8,684 of 8,686 cases
the resolved surface is one of the open pass's own attachments: the resolve
reads what the draws just wrote, so on a tiler the attachment must be
stored before compute reads it, and the pass end is inherent. Batching a
multi-source resolve's sub-steps would not remove them (245 of 9,200). The
only ways out are reading the attachment inside the pass
(`VK_KHR_dynamic_rendering_local_read`, which MoltenVK does not expose) or
the guest resolving less often, which is its choice.

### 4. Which passes, and the stage bounds

With the renderer's timestamp profile working on MoltenVK (see "Traps"),
the 56 ms frame split into passes by their bound surfaces. The main scene
pass (1280×720, the console's 4x MSAA depth and 2_10_10_10 float colour,
single-sampled on the host) was 28-30 ms in 7-10 passes a frame; everything
else was 1-7 ms each. The debug replacements then bounded the stages:
every pixel shader writing a constant took the frame from 63.1 to 24.7 ms,
and discarding primitives after the vertex stage took it to 24.1. **Pixel
shading was 38 ms, 61 % of the frame**; rasterization and attachment
writes were 0.6 ms. (The trivial-vertex-shader stub cannot be used on
MoltenVK: Metal rejects a pipeline whose vertex function writes none of
the fragment inputs.)

Quality settings were measured at this point as the fallback: texture
gamma decoded in the sampler instead of the shader −4 ms (7 %, the one
sampling-side switch that moved the M1); shadows off −16 % on the hoisted
build (they had been −9 % before it, hidden behind the upload restarts);
all three with quarter-rate reflections 56 → 42.5 ms. Forced 4x anisotropy
against the game's own: no difference. Coarse 2×2 shading: not available,
MoltenVK 1.4.1 does not expose `VK_KHR_fragment_shading_rate` on the M1.

### 5. fp16 arithmetic: measured, bisected, and then superseded

Apple GPUs run 16-bit float math at twice the rate, so the translator was
taught to convert each pixel ALU operation's operands to fp16 and back,
leaving registers, interpolators, constants, fetches, comparisons,
`exp2`/`log2` and integer ops in 32 bits. Two findings worth keeping even
though the change is off by default:

- **SPIR-V `RelaxedPrecision` does nothing on MoltenVK.** 201 decorations
  in the largest fragment shader, 3,060 `float` ops and no `half` in the
  MSL: SPIRV-Cross ignores the decoration for Metal. Only real 16-bit
  types reach the fp16 rate.
- **Overflow has to be guarded where the large values come from.** The
  lowering measured −3 to −4 ms but drew bright glints through the tree
  canopy in one scene. Sixteen runs bisected it, by operation class
  (nothing: the bad value flows through every class) and then by shader
  (halving a skip list of the 84 lowered shaders), to one sun-flare
  composite: an `exp2` result past 65,504, kept in 32 bits by design,
  reached the lowered multiplies, became an infinity at the first convert,
  times a zero texture weight made a NaN, and a final `max` wrote the NaN
  out as white. Clamping every operand to ±65,504 fixed the image and gave
  back the whole gain (two clamps per op). Clamping only the results of
  the 32-bit `exp`, `log`, reciprocal and inverse-square-root family, once
  each, fixed the image for free: 50.2 and 50.4 ms against four controls
  at 52.8-54.0.

The whole line of work was then superseded by the next finding: once the
real cost was removed, fp16 measured the same as fp32 (28.3-28.5 ms either
way), and the lowering stays available but off.

### 6. The real cost: `NoContraction` on MoltenVK, 53 → 28 → 21 ms

Compiling the dumped MSL of the largest free-roam fragment shader to LLVM
IR showed 2,638 operations, of which 1,081 were calls, and 398 of those
were to `spvFMul` and `spvFAdd` helpers. MoltenVK's SPIRV-Cross emits a
non-inlined helper for every multiply and add whose result carries the
SPIR-V `NoContraction` decoration (`spirv_msl.cpp`, `get_spv_func_impl`,
`has_legacy_nocontract`), and the helper is marked `[[clang::optnone]]`:

```
[[clang::optnone]] T spvFMul(T l, T r) { return fma(l, r, T(-0.0)); }
```

Xenos shader translators put `NoContraction` on every ALU result so that a
value computed in two passes (a depth pre-pass and the main pass, say)
matches bit for bit. On MoltenVK that means every product and sum runs in
its own unoptimized function: no fusing, no folding of neighbouring
conversions. Only 18 fused multiply-adds survived in that shader; with the
attribute removed from the same MSL, 427 did.

Dropping the decoration from pixel shaders (keeping the Direct3D 9 rule
that 0 × anything is 0 only for NaN products) halved the frame:

| Run | Drive GPU ms (p95) | Drive frames in the window |
| --- | ---: | ---: |
| control | 53.3 (98) | 374 |
| fast pixel math | **27.9 (35)** | 719 |
| control | 53.7 (98) | 370 |
| fast pixel math, repeat | **28.4 (35)** | 791 |
| control | 52.9 (98) | 366 |

−47 %, uniform across draw-count buckets (800-1200 draws 46 → 22 ms,
1200-1600 51 → 28, over 1600 81 → 33), image unchanged on the fixed-clock
route. Re-profiled, the main scene pass had gone 39.2 → 12.4 ms and pixel
shading from 38 ms to 8.2 (29 % of the frame).

The vertex stage was next, for the same reason: an IR census of the
largest vertex shader found 2,267 operations with 843 calls, 324 of them the
same helpers, and 64 of 66 vertex shaders carried them (0 of 97 fragment
shaders did by then). Dropping the decoration from vertex ALU results, while
keeping `Invariant` on the position outputs so Metal still compiles with
`preserveInvariance`:

| Run | Drive GPU ms (p95) |
| --- | ---: |
| control (fast pixel math) | 28.5 (35) |
| fast vertex math | **21.1 (25)** |
| control | 28.6 (35) |

−26 % more, 53 → 21 ms in a day from two decorations. The captures were
checked by eye for depth fighting between the pre-pass and the main pass:
none. Dropping the Direct3D 9 multiply rule from vertex shaders as well
(which helps Adreno) measured within noise here: once the helpers are
inlined, the rule's `abs`/`min`/compare/select per product is free on
Apple's GPU, so the rule stays for its 0 × ∞ protection.

Lesson: read the compiled shader, not the source, before optimizing
arithmetic. Any Xbox 360 recompiler that keeps `NoContraction` for
pass-to-pass invariance pays this on MoltenVK, and the cost hides behind
whatever else is being measured.

### 7. Encoder gaps and MoltenVK's barrier implementation: 21 → 19 ms

A Metal System Trace of the 21 ms frame, per game frame:

| Channel | Busy ms (was, at 72 ms) | Encoders a frame | Median encoder |
| --- | ---: | ---: | ---: |
| Fragment | 7.0 (37.2) | 123 | 8 µs |
| Compute | 3.6 (4.8) | 140 | 4 µs |
| Vertex | 2.4 (13.6) | 123 | 6 µs |
| any channel busy | 11.9 | 386 | |
| GPU idle | **9.1** (19.4) | 356 gaps | 261 under 20 µs, 78 of 20-50 µs, 10 over 100 µs |

43 % of the frame was the GPU doing nothing between encoders, most of which
were a few microseconds of work behind 15-20 µs of transition. The shading
had become five times cheaper while the encoder count had only fallen from
741 to 386. The 45 compute-to-compute boundaries a frame (consecutive
resolve dispatches in separate encoders) cost 3 ms of gaps for work that
would fit one encoder, and the renderer's barrier census showed why each
resolve began a new encoder: it issues an image layout barrier before each
resolve's dispatch.

MoltenVK's source explained the rest. On this device it defaults to Metal
3 argument buffers, makes every resource resident through an
`MTLResidencySet`, and therefore cannot rely on Metal's automatic hazard
tracking between encoders. It implements Vulkan barriers with `MTLFence`s:
`vkCmdPipelineBarrier` outside a render pass ends the current encoder,
records fence slots, and the next encoder waits on them
(`MVKCmdPipelineBarrier::encode`, `endCurrentMetalEncoding`, `setBarrier`,
`encodeBarrierWaits`, gated on `isUsingMetalArgumentBuffers() &&
hasResidencySet()`). With argument buffers off, descriptors bind by
discrete resource index, there is no residency set, the fence path is
inert, and a barrier between two dispatches leaves the encoder open.

`MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0`, set from the runtime before the
Vulkan loader is loaded: **19.1 and 19.3 ms** against controls at 21.1 and
21.0 (−9 %), image unchanged. The device then reports 128 sampled images
and 16 samplers a stage (256 and 16 with argument buffers); this game's
pixel shaders average 4 fetches, so nothing is lost. Removing the
renderer's own write-after-write buffer barrier between consecutive
resolves instead did nothing (21.1 against 21.1), because each resolve's
batch also carries the image barrier and the encoder split with it.

Lesson: measure per-transition gap totals, not encoder counts alone, and
read the driver's barrier implementation before changing the barriers you
emit. Nothing in a renderer like this needs argument buffers on macOS
unless it uses bindless texturing.

### 8. Frame generation on top

Apple's MetalFX frame interpolator can double the presented rate once the
real frame fits half the panel's interval. Colour-only interpolation works
(no depth or motion texture; MetalFX runs its own optical flow over the
colour pair), the first frame after a history reset is a copy, and the
cost was 6.3 ms a frame at 1280×720 on the M1, more than guessed. With the
game capped at 30 fps on the 21 ms build it presented 58 a second from 29
rendered, 4 real frames dropped in 46 s, at 29-31 ms of GPU a rendered
frame. Because a real frame is held back to make room for the generated
one, input feels a little less immediate, and the player preferred the
uncapped real frames once the frame fit 60 fps, so generation is an
option, off by default. The design is in `FRAME_GENERATION.md`.

### The totals

| Build | Drive GPU ms | What changed |
| --- | ---: | --- |
| first measurement | 130.7 | page-state refresh every frame (a settings bug) |
| intended default | 71 | |
| uploads hoisted and merged | 54-57 | fewer pass restarts |
| fast pixel math | 28 | no `NoContraction` helpers in pixel shaders |
| fast vertex math | 21 | the same for vertex shaders |
| no Metal argument buffers | **19** | barriers no longer end encoders |
| plus texture gamma in the sampler, shadows off, quarter-rate reflections | 20 (on the 28 build) | quality settings, player's choice |

In play, with the frame rate limit at 60 and shadows, bloom, motion blur
and depth of field all on, the M1 holds 60 fps.

## Traps that cost days

- **Timestamp query pools on MoltenVK.** Metal backs a timestamp pool with
  one counter sample buffer of at most 4,096 entries. A larger pool falls
  back to emulated queries that never resolve, silently. Size the pool to
  fit and read results with per-query availability, since a swap's
  timestamp is never sampled.
- **The debug trivial-vertex-shader stub fails on Metal**, which requires
  every fragment input to be written. Bound the vertex stage from the
  trace's vertex channel or from an IR census instead.
- **Pipeline compilation at a cold Metal shader cache.** A fresh build's
  first start rebuilt 611 pipelines stored from earlier sessions in 20 s
  behind a black window and was force-quit as a hang; the second start took
  0.1 s. Show the player what is happening: the renderer counts its
  startup pipeline builds, queued asynchronous builds and shaders still
  translating, and the host draws "LOADING SHADERS n / total" at the bottom
  of the window until they finish. If the renderer is a plugin library,
  put those counters behind its interface: a header-only singleton
  compiled into both sides is two singletons, and the host reads zeros.
- **Fullscreen transitions on macOS.** Cocoa reports the new pixel size
  while the window is still animating into the fullscreen Space. A
  swapchain made then is bound to a layer state the end of the transition
  replaces: presents succeed and nothing reaches the screen (black in
  fullscreen, the clear colour back in the window) until something
  rebuilds the connection. SDL's `SDL_EVENT_WINDOW_ENTER_FULLSCREEN` and
  `LEAVE_FULLSCREEN` fire when the transition has finished; rebuild the
  swapchain on them even though the size event that follows is unchanged.
- **Measurement traps**, all in the method section: menu medians, thermal
  drift across runs, stalled first runs, a full disk, and an image check by
  MAE alone.

## What did not pay off here

| Tried | Result |
| --- | --- |
| Single-pass scene with predicated tiling (an Android win) | 17 % worse on the M1: it saves three of ~290 restarts a frame |
| Batching a resolve's sub-steps into one pass | not a lever: the resolve reads the open pass's own attachment, so the pass must end |
| SPIR-V `RelaxedPrecision` on pixel shaders | no change: SPIRV-Cross emits `float` for all of it |
| fp16 ALU lowering, after fast math | no change once the helper calls were gone; stays available, off |
| Clamping every fp16 operand against overflow | correct image, whole gain lost; clamp the 32-bit sources once instead |
| Dropping the Direct3D 9 multiply rule from vertex shaders | within noise once contraction is allowed |
| Removing the renderer's buffer barrier between consecutive resolves | no change: the image barrier in the same batch still ends the encoder |
| Coarse 2×2 shading | `VK_KHR_fragment_shading_rate` not exposed by MoltenVK 1.4.1 on the M1 |
| Game's own anisotropy instead of forced 4x | no change: sampling is not the cost at 1x |
| Skipping the mid-frame submission split | no change |

## If you are starting on a new game

In the order that would have saved the most time here:

1. Build the drive-window measurement and the three validity checks first.
   Everything else was wrong until they existed.
2. Dump the MSL and compile one large pixel shader and one large vertex
   shader to LLVM IR. Count calls. If `spvFMul`/`spvFAdd` are there, lift
   `NoContraction` from ALU results and keep `Invariant` on positions.
   Expect the biggest single gain of the port.
3. Set `MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0` unless you need bindless
   resources, and check the per-stage binding limits.
4. Take a Metal System Trace. Sum GPU idle per frame and the gaps per
   transition type. Count render-pass restarts and attribute them to the
   code that ended the pass.
5. Hoist CPU-to-GPU uploads out of open passes, merging each pass's
   uploads into one barrier pair.
6. Accept the resolve-driven pass ends unless MoltenVK gains local read.
7. Then look at the passes themselves, with the timestamp profile sized
   for Metal, and only then at arithmetic.
8. Explain stalls and transitions to the player: a compile progress line
   and a swapchain rebuilt after fullscreen transitions.

## Where the detail is

The measurements above are recorded in full, with dates and the exact
flags, in `REVERSE_ENGINEERING.md` (section "Host performance (Apple
M1)"), the kept and rejected techniques in the site's GPU optimizations
and Lessons pages, and the frame generation design in
`FRAME_GENERATION.md`. The changes themselves are in the ShiftGlue SDK
(the fork of ReXGlue this project uses): `spirv_fast_pixel_math`,
`spirv_fast_vertex_math`, `vulkan_moltenvk_argument_buffers`,
`fh1_hoist_uploads`, `fh1_hoist_uploads_merge`, `fh1_shader_float16`,
`fh1_shader_float16_clamp`, `IGraphicsSystem::shader_compile_status`, and
the SDL window's fullscreen-transition handling.
