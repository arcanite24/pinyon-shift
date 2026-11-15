# Beyond recompilation: effort against payoff

Written 2026-11-15 at `dev` `87f04b7b`. The question: performance work on
the recompiled game has hit its walls, so what is left, from a cheap probe
up to a full open reimplementation of the engine, and what does each step
buy in frame time, hardware requirements and control? Performance comes
before correctness throughout: a technique that changes the image a little,
or adds a frame of latency to a culling decision, is allowed if it plays
well.

Nothing was built or run for this page. The numbers for this project come
from the pages it links. The numbers for other projects are what those
projects publish; none was reproduced here.

The effort scale runs from 0 to 100. A setting change is about 1. **100** is
a full decompilation and an open reimplementation of the engine, which reads
the player's extracted assets and runs without the recompiled executable.

## Where the walls are

The measured state, from [limits](../site/pages/limits.md),
[lessons](../site/pages/lessons.md#what-didnt-pay-off-here) and the #1071
work:

| Device | Bound by | Detail |
| --- | --- | --- |
| RTX 4080 desktop | CPU: the GPU emulation front end | PM4 decoder 6.3-7.2 ms and draw recorder 7.5-8.2 ms a frame. With every draw skipped the frame is still 6.8-7.3 ms, because the decoder still walks every command list |
| Steam Deck LCD | GPU and its share of the 15 W budget | 16.4 ms of GPU time. Process CPU is 44-52 ms a frame, of which the decoder is about 9, the recorder 10 and submission 5 ms; the guest render thread is about 8 |
| Odin 2 Portal | GPU | 15.5 ms of 16.7 |
| Intel UHD 620 laptop | GPU | about 78 ms, about five times too slow for 60 |

What the rejected list establishes:

- **The CPU cost follows the number of draws, not the work in each one.**
  A race frame is about 4,500 draws (2,900-7,400). Per-draw work is about
  20 small steps of 90-360 ns each, and the driver is only 1.6 % of the
  recorder. Templates, replay, owned draw programs, parallel recording, the
  D3D-level renderer (DL-3, -0.9 ms) and the native draw slice all kept the
  per-draw path and landed on the same floor. "Only fewer draws move the
  GPU threads" (#1071 P2).
- **Translated guest code is close to native already.** Rewriting scene
  submission natively ran only 1.2-1.5 times faster (#1071 P2), and guest
  profiles are flat: no function above 3 %. Rewriting game logic has a
  ceiling of roughly a third of the guest threads' time.
- **GPU time is not mostly pixels.** Half the resolution saved 14.5 % on
  the Deck and 8.5 % on the Odin (RS-0). On the Odin, 48-70 % of the main
  scene's depth-writing draws pass no samples, worth 2.2-3.2 ms of the main
  pass (#784). The game has no occlusion culling of its own.

So every lever left below a large project either cuts draws or changes what
the GPU draws. The tiers below are ordered by effort.

## The ladder

| Effort | Step | Desktop (CPU-bound) | Deck / Android (GPU-bound) | UHD 620 | Control gained |
| --- | --- | --- | --- | --- | --- |
| 5 | **B1.** Probes from The Simpsons Game recomp | none | 0.5-1.5 ms GPU if any applies (guess) | small | none |
| 20 | **B2.** Occlusion culling one frame late | about 1 ms (recorder only) | up to 2.2-3.2 ms GPU on the Odin (#784 bound) | some of the main pass | none |
| 25 | **B3.** A "performance" image contract | none | MSAA and shadow costs, unmeasured | needed to reach 30 | none |
| 60 | **B4.** An owned static-world renderer | frame toward 3-4 ms (estimate) | process CPU -12 to -18 ms; GPU -3 to -6 ms (estimate) | toward 40-50 ms | world LOD, draw distance, culling |
| 80 | **B5.** An owned renderer for the whole frame | frame set by guest threads (~3.6 ms) | GPU emulation front end gone; mirror -512 MB | 30 at lower settings becomes reachable | any renderer feature: TAA, dynamic resolution, new effects |
| 100 | **B6.** Decompilation and open reimplementation | about the same as B5 | guest threads up to a third faster | same as B5 | everything: new content, any platform, no SDK |

The payoffs for B4-B6 are estimates from the shares above. Each step has a
gate probe (below) that measures its ceiling before the large work starts.

### B1. Probes from The Simpsons Game recomp (effort 5)

The Simpsons Game Recompiled (YesterMester, also ReXGlue) publishes dated
Steam Deck measurements for each release from 0.0.6.0 to 0.0.7.1
([releases](https://github.com/YesterMester/TheSimpsonsGameRecomp/releases),
[native renderer plan](https://github.com/YesterMester/TheSimpsonsGameRecomp/blob/main/simpsons/re/native_renderer_plan.md)).
Most of its renderer gains are things the FH1 executor already does:

- resolves straight into textures;
- host images sized to what the game draws;
- partial resolves;
- specialized resolve pipelines;
- clears folded into `loadOp` (A60-1).

Three of its gains have no record here:

- **Colour compression on render-to-texture.** It reports 1.1-1.4 ms of
  GPU time at 2x on the Deck. On RADV, images created with storage usage,
  or with mutable formats that aren't compatible with compression, can lose
  DCC, and the executor's resolves write images through compute. Probe: an
  in-run A/B on the Deck with `RADV_DEBUG=nodcc` against the default. If
  turning DCC off costs nothing, our images already lack it; check their
  usage flags and format lists for the ones that block it.
- **Skipping uniform-stencil work.** It reports about 1 ms. Our depth
  transfers already export stencil in one pass where the extension exists.
  Check whether the stencil a transfer carries is often a single value, and
  clear it instead of copying.
- **Native GPU producers (0.0.7.0-0.0.7.1).** These replace the game's
  command writers with native records. Our native draw slice did the same
  and saved nothing (#1071). Their 12.4 to 9.0 ms game-thread gain came
  mostly from removing two full memory fences and a global lock in
  interrupt handling, so audit our interrupt and fence callback path for
  the same, not the producers.

### B2. Occlusion culling one frame late (effort 20)

#784 rejected culling hidden draws because doing it safely needs this
frame's depth. If a draw that becomes visible may appear one frame late,
the previous frame's result is enough:

- Key each main-scene draw by its command list and offset. 96 % of the
  indirect buffers are byte-identical from frame to frame.
- Give each draw a bound once. The executor already bounds some draws by
  running the vertex shader on the CPU.
- Test the bounds against the last frame's depth pyramid in one compute
  pass, and predicate the draws with `VK_EXT_conditional_rendering`, so the
  GPU skips them without any CPU readback.
- Where the extension is missing (check Mali), read the results back two
  frames late and skip the draws on the recorder. That also gives back some
  recorder time on the desktop, although the decoder still walks the lists.

**Gate:** Odin main-pass GPU time down by 1.5 ms or more, with no
disocclusion artifact visible at racing speed.

### B3. A performance image contract (effort 25)

MR-2 rejected 1x MSAA with FXAA because it scored 39.1-39.2 dB, against a
40 dB PSNR floor. Under performance over correctness, the floor itself can
move for presets that target weak GPUs:

- Define a LOW-SPEC image contract by play test rather than by PSNR.
- Re-measure the GPU saving of 1x MSAA with FXAA, and of the 2x
  candidate, on the UHD 620 and the Mali tablet under that contract.

This is the only step below B4 that can bring the UHD 620 near 30 fps.

### B4. An owned static-world renderer (effort 60)

This is the first step that changes the scaling, rather than the constant
cost per draw. The recompiled game keeps running everything. Only the static
world (terrain, roads, buildings, the vegetation lists) stops going through
PM4:

1. **Intercept at the owner, not at the draw.** The engine sends the
   world's command lists to the list executor from `824167F8` and
   `82417060`. Those are reached from `CProceduralModels` (slot 41) and from
   the track's model-asset owner `824365B0` (`site/findings/rendering.toml`).
   Skipping the call at that point means no PM4 is built, chained or
   decoded for the world. DL-3 and the slice still decoded or derived
   every draw.
2. **Take the geometry from the player's own data once.** That can be
   from the disc at setup, or from the first frames that draw each
   streamed cell, since the lists are byte-stable. Build merged vertex and
   index buffers per cell and material, in a local cache, like the AOT
   pipeline recipes. Nothing of the game's is committed (docs/LEGAL.md).
3. **Draw it GPU-driven.** That means frustum and occlusion culling in
   compute (B2 built in), `vkCmdDrawIndexedIndirectCount` per pipeline, and
   bindless textures where the driver allows them. The material shaders can
   start as today's translated SPIR-V, fed from our own constant buffers,
   so no shader has to be rewritten first.
4. **Keep the rest on the current path:** cars, crowds, particles, the
   post chain and the HUD. The world still has to draw into the same
   surfaces and depth before those passes.

**Payoff (estimate).** The main scene is about 61 % of a race frame's draws,
camera depth 18 % and shadow atlases 11 %, and most of those are world
draws.

- **Desktop:** if 70-80 % of the draws leave the decoder and recorder, both
  threads fall from 6-8 ms toward 2-3 ms. The frame would then be set by
  the guest render and title threads (about 3-3.6 ms), roughly 250 fps
  where 120 is the limit today.
- **Deck:** most of the 24 ms of front-end CPU follows the draws, which
  gives power back to the GPU. GPU time falls by the occlusion share and
  the per-draw overhead.
- **UHD 620:** this alone doesn't reach 60. Combined with B3 and coarser
  world LOD (which the owned renderer can choose freely), 30 becomes
  plausible.
- **Control:** draw distance, LOD and culling become our code. So does
  any later world feature.

**Risks.**

- The earlier engine-level pilot (Xenos era, six families) needed 153 guest
  hooks and ran 91-95 ms frames. It hooked draws over the old emulator, so
  it isn't the same design, but it is the reason this step needs a gate.
- The world lists are rewritten while the game runs (streaming, time of
  day, damage). Cache keys need write generations, as the texture cache
  uses.
- Reflections, the shadow atlases and camera depth draw the world as well.
  Each view needs the owned path, or it falls back to PM4.

**Gate probe (about a day).** Return early from the list executor for
`824365B0`'s lists, so the world isn't drawn at all, and measure an in-run
A/B on the desktop and the Deck. That is the ceiling of B4's CPU saving. If
the desktop frame doesn't go below 5 ms, or Deck process CPU doesn't fall
by 12 ms, stop here. Skate 3 Recomp 2.0 claims more than 2x the frame rate
at about a quarter of the GPU power with a native renderer, but publishes
neither method nor hardware
([GamingOnLinux](https://gamingonlinux.com/2026/07/skate-3-recomp-2-0-brings-native-rendering-to-the-pc-port-of-the-xbox-classic-skate-3)),
so it's encouragement, not evidence.

### B5. An owned renderer for the whole frame (effort 80)

B4, extended to cars, characters, particles, the post chain (about 43 small
renderings) and the HUD. The decoder, recorder, EDRAM model, resolves,
write-watches and the 512 MB guest-memory mirror then have nothing left to
serve, apart from CPU readbacks such as car thumbnails. This adds:

- an install-time texture pack (CS-3.3): untile and convert once, with no
  untiling or texture requests during the frame;
- a frame structure of our own: one main pass instead of tiles, TAA or an
  upscaler on real motion vectors, dynamic resolution, and pass merging for
  tilers;
- on the Deck, the whole front end (about 24 ms of CPU) goes, so the APU's
  power goes to the GPU.

The cost over B4 is mostly the post chain and car materials. Each of their
title shaders needs a host version and an image check, and the 5361 pass
alone carries most of the image (MR-5). The guest threads still set the
desktop frame, at about 3-3.6 ms.

### B6. Decompilation and an open reimplementation (effort 100)

This is what B5 adds once the game logic is ours too: physics, AI,
streaming, the UI, audio through our own mixer, and our own file loaders
reading the player's extracted assets.

**What it adds over B5:**

- **CPU:** the guest threads get up to about a third faster. That's the
  1.2-1.5x measured for native scene code, over guest threads that are the
  rest of the frame once B5 removes the front end. On the desktop that is
  about 1 ms. On the Deck, render, simulation, physics and FMOD at
  roughly 20 ms of CPU become about 13-16. The frame-rate gain is small;
  the power and core-count gain is real (fewer threads, no FMOD
  emulation).
- **Memory:** the guest's 512 MB arena and the endian conversion go.
- **Control:** this is the real payoff:
  - new tracks, cars and modes without patching the guest;
  - fixed-timestep physics at any rate;
  - online play;
  - ports with no SDK (consoles, the web, RISC-V);
  - bugs fixed in source.

**What it costs:**

- 76,499 functions. Decompilations with tooling and many contributors have
  taken years: Super Smash Bros. Melee is 19,828 PowerPC functions, 100 %
  matched in September 2026.
- Assisted decompilation is now fast at the start and slow at the end. A
  Call of Duty: Modern Warfare 2 PC decompilation reports 99 % of functions
  in about 3 months, with 3 worker agents and a reviewer, at an estimated
  600-700 billion tokens; its code is not public
  ([write-up](https://momo5502.com/posts/2026-10-09-game-decompilation/)).
  An N64 project shows the last quarter stalling without experts
  ([write-up](https://blog.chrislewis.au/the-long-tail-of-llm-assisted-decompilation/)).
- Extrapolated: at four times Melee's size, a checked, non-matching rewrite
  is many months and trillions of tokens.
- **Licensing:** docs/LEGAL.md rules out committing a transcription of
  decompiler output. A public B6 has to be a clean-room reimplementation
  written from our own analysis, as OpenMW and OpenRCT2 did, not a
  published decompilation. That is slower than either.
- **Checking:** without matching, every rewritten function needs a check
  against the recompiled original. Today that is lockstep verification per
  function. CS-1 showed that whole-session replay doesn't hold. That check
  is the missing piece, and it was the most expensive part of the MW2
  effort.

**The workable route to B6 is the OpenRCT2 one.** OpenRCT2 replaced
functions inside a running original until the original was gone. Here,
every guest function can already be overridden (`guest_native`), so B6 is
B5 followed by subsystem after subsystem in native code, each checked by
behaviour gates (handling, AI lap times, Rally completion), as #1071
already plans for physics. It never needs a big switch-over. But each
subsystem pays only its share of a flat profile.

## Recommendation

- **Effort 60 (B4) is the knee.** It is the only step that removes
  per-draw emulation work rather than making it cheaper, which every
  rejected item has shown to be the wall. It is also the first step that
  helps both the CPU-bound desktop and the GPU-bound devices, and the
  earlier steps (B2's culling) become part of it.
- **B5 is worth it for low-end hardware and features:** the UHD 620, Mali
  and anything weaker than the Deck. It isn't worth it for the desktop frame
  rate.
- **B6 pays in control, not speed.** Above B5 it buys at most about a third
  of the guest threads' time. Choose it for mods, new content or new
  platforms, not to lower hardware requirements.

Order:

1. B1's three probes (days).
2. B4's gate probe (a day).
3. If the gate passes, B2 as B4's first piece, then B4 itself.
4. Decide B5 on the UHD 620 and Mali numbers after B4.

## Other projects surveyed (2026-11-15)

- **The Simpsons Game Recompiled** (ReXGlue): figures under B1. 132 fps
  at 1x and 103 at 2x on the Deck at 0.0.7.0.
- **Skate 3 Recomp 2.0** (mid-2026): a native D3D12 and Vulkan renderer
  with ports of the game's material shaders. The claims are unmeasured.
- **Tony Hawk's Project 8 Recomp 0.3.0:** Deck, about 2,665 draws, 25.0
  to 21.9 ms through native vertex/index handling, texture reuse and
  bounded waits. That's in line with our per-draw floor.
- **Silent Hill: Downpour Recomp 1.0:** triple-buffered memexport
  readback took its fence waits from about 18 a frame to 0. That's only
  relevant if FH1 uses memexport (unchecked).
- **The Mushihimesama Futari recomp's "Renut" renderer** draws the game's
  D3D calls and is slower than emulation on an M3 Max. That agrees with
  DL-3.
- **No public reverse engineering of FH1's file formats** (`.carbin`,
  `.xds`, `.rmb`) was found. ForzaTools and ForzaMods target ForzaTech
  games, so the records in `site/findings` are likely the furthest along.
