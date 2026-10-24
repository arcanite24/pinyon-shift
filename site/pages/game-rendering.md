---
title: Rendering
section: Reverse engineering
order: 7
description: How Forza Horizon draws a frame on the Xbox 360: its passes and draw counts, EDRAM surfaces and predicated tiling, resolves, shadows, post effects, render scenarios and the D3D code inside the executable.
---

# Rendering

The game renders through the Xbox 360's Direct3D 9 runtime, which is linked into `default.xex`, so the D3D code is part of the guest and shows up in these records with addresses. Most of what the game draws comes from command buffers (display lists) that the engine builds ahead of time, rewrites while the game runs, and chains into the ring once per EDRAM tile. Everything on this page was measured on the recompiled game, whose GPU stream is the one the console would have received.

A race frame is 2,900 to 7,400 draws. In order, the GPU fills two depth-only targets (the sun shadow map and a second depth pass), a few 2x MSAA targets, then the 4x MSAA main scene in three horizontal tiles, then a post chain of about 43 small renderings, and finally the HUD and the swap:

{{diagram:game-race-frame|Order of work in a race frame, from a race-start capture. Draw counts move with the scene; the shares hold: main scene about 61 %, sun shadow map 18 %, second depth pass 11 %.}}

The renderer this project replaced the Xenos emulator with is described under [Internals](renderer.md); this page is about what the game itself asks for.

## Frame structure and views

Average draws per frame range from about 50 at boot and 841 in the menus to 3,225 in free roam and 4,508 in a race. The same command buffers are replayed every frame, and the game's per-frame state goes into the segment that calls them.

{{findings:rendering/Frame structure and views}}

## Render targets and EDRAM

The 10 MB of EDRAM never holds a full 1280x720 4x MSAA frame, so the main scene is drawn in three predicated tiles of up to 256 rows, each replaying the same command buffers with a different bin select. Surfaces never use more than one colour target.

The depth at base tile 0, pitch 16, has both a 1280x720 single-sample view and a 640x360 four-sample view. The four samples of one pixel in the smaller view occupy four pixels in the larger view: both address the same 720 tiles. Reinterpreting those words does not establish that drawing at a different pixel rate is equivalent. The color-writing draw using this depth reads an interpolator, and the four alias draws in the current race trace do not use an ordered depth comparison. The [depth-alias research](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DEPTH_ALIAS_RESEARCH.md) separates those observed states from the earlier transparency hypothesis.

The main-scene sky already follows depth-writing geometry in each tile. It
tests the populated scene depth, writes stencil, and is followed immediately
by blended stars, then sun and cloud layers. Moving it later therefore does
not have the simple image-preservation argument of an opaque sky drawn over
empty depth. The [sky-order study](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/SKY_DRAW_ORDER.md)
records the shader identities and measured ordering.

{{findings:rendering/Render targets and EDRAM}}

## Resolves

A resolve copies EDRAM to a texture in main memory. The game does about 60 to 92 a frame, of 20 kinds. One of them, a 32x32 float resolve of the scene's luminance, drives auto exposure: when the memory under it was stale, the whole screen was overexposed ([#444](https://github.com/arcanite24/pinyon-shift/issues/444)).

{{findings:rendering/Resolves}}

## Shadows

The sun's shadow map is the 1280-wide depth-only pass at the start of the frame; skipping it removes every shadow. Shadow atlases are refreshed only in part each frame.

{{findings:rendering/Shadows}}

### Alpha-tested shadow casters

Enabled alpha-test or alpha-to-coverage register bits do not, by themselves,
identify foliage in FH1's shadow targets. Some flagged draws execute without
a pixel shader. A target-filtered experiment that removed all of them also
removed the player car's self-shadowing, restored when the filter was switched
off again. Count raw flags separately from draws whose effective pixel shader
uses alpha coverage. The [R03 experiment](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/PERFORMANCE_BACKLOG.md#r03-alpha-tested-shadow-casters)
records the selectors, measurements and image checks.

## Post effects

Bloom and luminance are built by reducing the scene to 320x192, 64x32 and 32x32 levels; the final pass applies motion blur and the colour grade from a 16x16x16 lookup texture. Every post group changes the frame, so none of it is dead work.

{{findings:rendering/Post effects}}

## Render scenarios

How much the game draws is data: `media/renderscenarios.zip` holds one XML file per situation (free roam, race, photo mode, menus), each a list of `DynamicRenderSettings` controls such as `FrameRate`, `TilingScenario`, car LOD distances, crowds and particles. The game parses every file at boot into its own object and pushes the active one to the render thread. The level-of-detail keys are covered on [World and tracks](game-world.md#render-scenarios-and-car-level-of-detail), where most turned out not to change what is drawn.

{{findings:rendering/Render scenarios}}

## D3D inside the game

The D3D runtime's own functions (command buffer execution, the ring writer, resolves, gamma, the swap and the fences) are linked into the executable and run as guest code. The present path waits for the previous frame's fence, so the game runs at most one frame ahead of the GPU ([Threads and frame loop](game-threads.md#present-and-fences)).

{{findings:rendering/D3D inside the game}}

## Shaders, textures and models

The game's shaders are compiled Xenos microcode, in `media/shaders/**/*.fxobj` and inside `default.xex`; a few are generated at run time. No resolve writes a block-compressed format, and texture assets are mostly DXT.

{{findings:rendering/Shaders, textures and models}}

## Light glows

Lamp, outpost and headlight glows are additive sprites that only the depth test hides behind geometry. Right after the player's car the game stamps the nearest depth over the car's stencil, so glows and smoke drawn later cannot cover it. Some lamp and headlight glows ask for an `ALWAYS` depth test and showed through the car and the terrain in the port; the host depth-tests them like the others ([#531](https://github.com/arcanite24/pinyon-shift/issues/531)).

{{findings:rendering/Light glows}}
