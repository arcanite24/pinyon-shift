# Draws without a framebuffer effect

The Vulkan executor already omits draws that have no attachment, memory export
or active occlusion query. `fh1_skip_draws_without_effect` is on by default and
hot-reloadable. Target selection uses the pixel shader's actual color outputs
and the normalized depth/stencil state, so a zero color mask with depth and
stencil disabled reaches this existing skip. The command processor also exits
when rasterization is disabled without a vertex memory export, or primitive
processing produces no vertices.

At SDK `102fe952`, these are in
`src/graphics/vulkan/command_processor.cpp` (`IssueDrawImpl`, the
`host_draw_vertex_count` check and the `BoundNothing` check),
`src/graphics/vulkan/fh1_native_executor.cpp` (`PrepareTargetsImpl`), and
`src/graphics/util/draw.cpp` (`GetNormalizedDepthControl` and
`GetNormalizedColorMask`). The census separates these existing skips from
additional candidates.

## Counting additional candidates

The October 24, 2026 census used multivac (Ryzen 7 5800X, RTX 4080, Windows
Vulkan), root `34e2f00c` and SDK `102fe952`, with copied generated sources and
frozen codegen.
The temporary diagnostic classified draws before shader/primitive/target
early-outs and reset its counts at each swap. Copy/resolve packets were not
draws. It recorded the presented output sequence separately from the executor
frame number to align the counts with route events.

Each draw was checked for eight overlapping causes:

- no effective color output;
- ADD blending with source ZERO and destination ONE on every written component;
- an enabled alpha test with NEVER and a pixel shader exporting target 0;
- an enabled depth test with NEVER;
- stencil tests that fail unconditionally on both enabled faces;
- an empty effective scissor;
- an empty derived viewport;
- zero indices.

Safe counts excluded memory-export shaders, every active occlusion query and
possible depth/stencil writers. Any non-KEEP stencil operation with a nonzero
write mask counted as a possible write, including ZERO. Raw counts before
these exclusions were retained to check for test-failure or empty-extent cases
that the conservative filter might miss. Causes overlap, so their counts must
not be added as if each described different draws.

The seed was `appdata-2026-09-27`, copied privately by
`tools/run-fh1-render-test.py`. The routes were `fh1-race-start-wait` and the
free-roam drive `fh1-hitch-drive`. The stock race route's first two final
captures were still on the countdown, despite its `vehicle-moved` wait; those
samples were excluded. A private copy appended captures at route frames 5050
(`race-active`) and 5290 (`race-active-later`), and stopped at 5350. Race samples
ran from 120 output frames before `race-active` through `race-active-later`;
the captures showed the race timer advancing and the car driving. Drive samples
took the last 600 outputs before the final capture, excluding its last two
outputs. The drive endpoints varied, including one car reaching the guardrail.
GPU phase profiling was enabled, but diagnostic timing was not a speedup measure.

The existing skip remained enabled. A separate counter at its actual branch
checked how often it ran. The new-candidate union excluded draws already
covered by existing skips. A new skip would require exact on/off captures and
either at least 50 race draws with 0.2 ms of Odin decoder/recorder CPU saving,
or 0.2 ms of GPU saving. The research brief permits a count-only rejection when
additional candidates are fewer than about 20 draws per frame.

## Result: one additional draw per frame

Three qualified race runs supplied 360 sampled frames each, and three free-roam
drive runs supplied 600 each: 2,880 gameplay frames. Every sampled frame had
exactly the same safe counts, so median, p10/p90 and minimum/maximum coincide:

| Cause | Race draws/frame | Free-roam draws/frame |
| --- | ---: | ---: |
| Effective color mask zero, no depth/stencil write | 121 | 121 |
| Destination-only blending | 0 | 0 |
| Alpha test NEVER | 0 | 0 |
| Depth test NEVER, no depth/stencil write | 1 | 1 |
| Stencil tests always fail | 0 | 0 |
| Empty scissor | 0 | 0 |
| Empty viewport | 0 | 0 |
| Zero indices | 0 | 0 |
| Union of safe causes | 121 | 121 |
| Already skipped by the no-attachment branch | 120 | 120 |
| Additional candidates | **1** | **1** |

The NEVER-depth draw is one of the 121 no-color draws, not another draw to add
to them. Its depth attachment remains bound for the test, so it misses the
existing no-attachment skip even though it cannot write anything. The raw
counts of destination-only blending, alpha NEVER, stencil failure, empty
scissor/viewport and zero indices were also zero in these windows; the
conservative write exclusions did not hide additional instances of those
causes. There were no memory-export draws or draws inside an occlusion query
in the sampled windows.

The additional skip was rejected at the rarity gate. The temporary census was
removed; the existing default-on skip is unchanged. There was no Odin A/B or
on/off image comparison, and no CPU or GPU saving is claimed. These are draw
state counts for these routes, not a bound on every event, weather or game mode.
