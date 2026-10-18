---
title: macOS renderer performance
section: Internals
order: 7
description: How the free-roam frame on an M1 went from 131 to 19 ms on MoltenVK, as a method other Xbox 360 recompilations can follow.
---

# macOS renderer performance

A guide for bringing a recompiled Xbox 360 game to Apple silicon through MoltenVK, drawn from the four days (2026-10-15 to 2026-10-18) in which Pinyon Shift's free-roam frame on a MacBook Pro M1 (8-core GPU, 16 GB, macOS 26, MoltenVK 1.4.1) went from 131 ms to 19 ms. The full text, with every measurement, is [docs/MACOS_RENDERER_OPTIMIZATION.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS_RENDERER_OPTIMIZATION.md); the same guide is published on its own for other projects in the [xbox360-macos-renderer-guide](https://github.com/jamesonricks/xbox360-macos-renderer-guide) repository.

## The frame, step by step

| Build | Drive GPU ms | What changed |
| --- | ---: | --- |
| first measurement | 130.7 | a settings bug refreshed the CPU page state every frame, ending 360 render passes a frame for uploads |
| intended default | 71 | |
| uploads hoisted out of the open pass and merged into one barrier pair | 54-57 | fewer pass restarts on the tiler, about 0.06 ms each |
| fast pixel math | 28 | no `NoContraction` on pixel ALU results: MoltenVK's SPIRV-Cross emits an unoptimized helper call for each decorated multiply and add |
| fast vertex math | 21 | the same for vertex shaders, with `Invariant` kept on positions |
| no Metal argument buffers | **19** | MoltenVK's argument-buffer mode ends a Metal encoder at every barrier outside a render pass; 43 % of the 21 ms frame was gaps between encoders |

In play, with the frame rate limit at 60 and shadows, bloom, motion blur and depth of field on, the M1 holds 60 fps. [Frame generation](playing.md#frame-generation) sits on top as an option.

## What carries over

- **Measure the scene, bracket with controls, validate each run.** The route's whole-run median is a menu benchmark; the M1 throttles across consecutive runs; a run that stalled compiling pipelines reads faster than a valid one. Details on the [Lessons](lessons.md) page.
- **Read the compiled shader.** `MVK_CONFIG_SHADER_DUMP_DIR` writes the Metal source; Apple's `metal -S -emit-llvm` shows what runs. Calls to `spvFMul` and `spvFAdd` mean `NoContraction` helpers, and any translator that keeps the decoration for pass-to-pass invariance pays for them on MoltenVK.
- **Count encoders and the gaps between them** with a Metal System Trace before optimizing anything else on a tiler, and read the driver's barrier implementation before changing the barriers you emit.
- **Resolves of the open pass's own attachment have to end the pass**; CPU uploads do not, and can be moved ahead of it.
- **fp16 arithmetic** needs real 16-bit types (`RelaxedPrecision` does nothing on MoltenVK), overflow guards at the 32-bit sources, and an image check by eye; here it measured nothing once the helper calls were gone.
- **Two things players hit**: a black window while hundreds of stored pipelines compile on a cold Metal shader cache (now a "LOADING SHADERS n / total" line), and a black fullscreen after macOS's Space transition replaced the layer state a mid-animation swapchain was bound to (now rebuilt when SDL reports the transition finished).

The guide ends with a table of what did not pay off and a suggested order of work for a new game. The kept techniques are also on the [GPU optimizations](gpu-optimizations.md) page, and the dated record with every flag is in [docs/REVERSE_ENGINEERING.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/REVERSE_ENGINEERING.md).
