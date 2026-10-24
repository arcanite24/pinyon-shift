# FH1 sky draw order (R04)

## Decision

Reject sky deferral: the main-scene sky already follows depth-writing scene
geometry in each predicated band. Its next draw blends against the colour
target. The sky also writes stencil, so it does not meet the proposed
opaque/depth-test/no-depth-write/no-stencil admission rule. No renderer
change or performance cvar is retained.

This is an ordering/state result, not a measured GPU speedup. There is no
on/off implementation to qualify against the 0.3 ms performance gate, or to
compare for image identity at 1x/3x in day/dusk scenes.

## Identity and state

The local disc shader corpus and embedded shader constant tables identify
these pixel shaders independently of their position in a frame. Hashes are
the SDK's XXH3-64 of the guest microcode. The local image's PE header gives
base `0x82000000`; adding each corpus container offset gives the addresses
below. These identify embedded shader containers, not callable functions.
V4 was not examined.

| Pixel shader | Base container address | Evidence for purpose | Race indices |
| --- | --- | --- | ---: |
| `CAE25D74AD7B16CB` | `0x82155780` | `TopColour`, `BottomColour`, `HazeColour`, `SunDirection`, `DitherMap`: sky gradient/haze | 9,300 |
| `4D035A14CD31FC2D` | `0x82157518` | `StarPowers`: stars | 9,096 |
| `CF453BD52292E8E8` | `0x82157388` | `SunColour`, `SunMap`: sun; also used outside the main scene | 4 |
| `90CAB86BE8159DA8` | `0x82156BA8` | `FrontCloudCoverAndSharpness`, `BackCloudCoverAndSharpness`: cloud cover | 8,700 |
| `FD9976C9E5DB9BB0` | `0x821564E0` | `FrontAlphaDensityMap`, `FrontAmbientMap`, `LayerFadeValuesMaskPowers`: lit clouds | 9,300 |

The gradient pairs with vertex shader `12BA4E86B158D049`. In the recorded
race frame all five draws use `RB_DEPTHCONTROL=087087E3`: depth test
`GREATER_EQUAL` (reversed depth), depth writes off, front/back stencil test
`ALWAYS`, and `REPLACE` on depth pass. `RB_STENCILREFMASK=00FFFF00` means
reference zero and full read/write masks. The gradient's blend is
`00010001` (ONE/ZERO for colour and alpha), with RGB write mask `7`.
Stars and clouds use `07060706` (source alpha / one minus source alpha);
the sun uses `01060106` (source alpha / ONE). Those draws consume the
background. Recognition by shader alone would also include reflection
draws with different attachment sizes.

The stars draw also switches the colour view from `00030000` to its
`000C0000` alias over the same EDRAM base. Equal pitch and depth attachment
do not by themselves establish one host rendering or a reorderable pass.

The current renderer preserves guest draw order in
`thirdparty/shiftglue-sdk/src/graphics/command_processor.cpp` (packet draw
dispatch) and `src/graphics/vulkan/command_processor.cpp` (`IssueDraw`,
`CmdVkDraw`/`CmdVkDrawIndexed`). Depth normalization in
`src/graphics/util/draw.cpp` does not remove this sky's stencil or depth
test. There was no existing sky-deferral feature.

## Recorded race frame

The previously recorded Odin race frame at executor swap 4500 contains
5,210 executed draws/copies. Its SHA-256 is
`2358f88a49ab2f6dcf054b97efa03338318c0c740745ea8933afa39e1cb69b92`.
Inspection reads the frame's starting registers, flattened packets,
shader loads and recorded memory, applying register writes and bin
predication without executing guest code or altering rendering. All 5,210
draw indices, index counts and pixel shader hashes match the independently
retained `race-draws.txt`.

| Band rows | Bin select | Sky draw index (zero-based) | Preceding depth-writing draws in the contiguous band run | Next draw |
| --- | --- | ---: | ---: | --- |
| 0–256 | `80000003` | 2,127 | 422 | stars, blended |
| 256–512 | `C` | 3,973 | 1,757 | stars, blended |
| 512–720 | `30` | 4,832 | 585 | stars, blended |

The counts stop at the preceding copy or window-offset change and are not
whole-band geometry totals. All counted depth writers use the same scene
depth as the sky, EDRAM tile 1024 (`RB_DEPTH_INFO=00010400`), 1280 pitch,
4x MSAA. The sky is therefore tested against depth already populated by
the scene, rather than the empty depth buffer in the motivating experiment.
Moving it to the first background-reading boundary crosses **zero** draws:
the stars blend is immediately next. Moving it past stars/clouds, across
a resolve, or into another band lacks an image-preservation argument.

The exact number of sky fragment invocations later overwritten was not
measured. Prior depth-writing draw counts establish ordering, not pixel
coverage; alpha layers and later scene lists still exist. This rejects
this specific early-sky deferral, not all sky shading optimizations or
all possible reorderings.

Local evidence is under `.local/codex-fleet/reports/R04/` in the main
checkout. Captured frame data and shader payloads remain local and are
not part of the repository.
