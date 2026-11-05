# FH1 native frame contract

XR-01 of the [Xenos retirement backlog](XENOS_RETIREMENT_BACKLOG.md). This is
the finite list of what the native renderer must implement, measured across
the game's modes with the frame census instead of inferred from one race.
It replaces "families" as the unit of coverage: a mode is covered when the
native renderer implements every surface configuration, resolve kind,
texture layout and primitive type listed for it. The native executor, now
the only renderer, runs every mode below with zero executor skips.

## How it was measured

The census (`thirdparty/shiftglue-sdk/src/graphics/d3d12/fh1_frame_census.cpp`)
runs inside `D3D12CommandProcessor::IssueDraw` after state is final, and in
`IssueCopy`, the optimized-clear report and `IssueSwap`. It copies no
payloads and aggregates each window of frames into bounded tables written as
JSON Lines. Enable it with:

```text
--fh1_frame_census=true --fh1_frame_census_path=<file.jsonl> [--fh1_frame_census_window=60]
```

Summarize with `tools/summarize-native-frame-contract.py <file> --mode
label:first-last ...`. `tools/summarize-fh1-stencil-census.py <file>
[--first-frame N --last-frame M]` tabulates, per depth surface, the draws
that enable stencil and the draws that may leave a nonzero stencil value
(the rule the executor uses to decide whether a depth transfer needs its
stencil-bit passes); censuses written before `stencil_ref_mask_bf` was
recorded report back-face stencil draws as unknown. The full metadata census
is wired into the retained D3D12 backend. Vulkan's optional ordered
pipeline-run census does not call its surface/resolve/texture observers;
do not interpret an empty Vulkan metadata file as a complete frame.
The records below are historical: they were taken from Xenos (reference)
rendering, before its removal, of seed `appdata-2026-09-27` with `run-fh1-render-test.py
--hidden`: the output-paced `fh1-native-race-mode-boundary` route (boot,
title menus, free roam, event and car-select menus, race, race pause and
quit, retire to free roam, pause, return to title), `fh1-fmv` with opening
movies, `fh1-free-roam`, `fh1-map`, `fh1-pause` and `fh1-photo-mode`;
17,580 frames in total. Every table stayed within capacity (zero overflow)
and every draw, clear, copy, ZPD event and swap was recorded, so no event is
unclassified.

## Per-mode scale

| Mode (mode-boundary route) | Frames | Draws/frame | Shader pairs | Surfaces | Texture layouts | Resolve kinds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Boot (legal, skipped intros) | 360 | 50.5 | 17 | 12 | 15 | 17 |
| Title and menus | 1,080 | 840.8 | 213 | 31 | 132 | 38 |
| Free roam | 360 | 3,224.7 | 207 | 26 | 115 | 33 |
| Event menus and car select | 2,160 | 2,423.8 | 246 | 30 | 131 | 35 |
| Race | 1,140 | 4,508.0 | 244 | 22 | 129 | 32 |
| Race pause and quit | 480 | 1,885.2 | 179 | 24 | 94 | 28 |
| Retire to free roam | 420 | 1,609.6 | 216 | 30 | 120 | 37 |
| Pause after retire | 240 | 3,568.7 | 183 | 25 | 98 | 30 |
| Return to title | 900 | 99.4 | 189 | 27 | 106 | 35 |
| FMV route (movies on) | 1,260 | 53.3 | 5 | 5 | 4 | 3 |
| Photo mode route | 2,460 | 1,226.0 | 260 | 35 | 147 | 39 |
| Free-roam route | 2,460 | 1,229.6 | 220 | 33 | 134 | 37 |
| Map route | 2,220 | 631.1 | 212 | 33 | 142 | 37 |

Mode boundaries come from the route's capture points and are approximate at
the 60-frame window level. "Resolve kinds" and "texture layouts" count
distinct register configurations, not distinct content.

## Render surfaces (29 configurations)

All modes combined, by guest surface pitch, MSAA, color and depth formats.
Host formats follow the mapping the shader pack was translated for (the
Xenos render-target cache's, now kept as the host render configuration without
the cache): `2_10_10_10_FLOAT` and
`2_10_10_10_FLOAT_AS_16_16_16_16` are both `R16G16B16A16_FLOAT` (so the
known alias pair can share storage), `2_10_10_10` and
`2_10_10_10_AS_10_10_10_10` are `R10G10B10A2_UNORM`, `8_8_8_8` is
`R8G8B8A8_UNORM`, `D24FS8` is `D32_FLOAT_S8X24_UINT` and `D24S8` is
`D24_UNORM_S8_UINT`.

| Pitch | MSAA | Color | Depth | Draws | Modes |
| ---: | --- | --- | --- | ---: | ---: |
| 1280 | 4x | 2_10_10_10_FLOAT | D24FS8 | 7,759,457 | 11 |
| 1280 | 4x | 2_10_10_10_FLOAT_AS_16_16_16_16 | D24FS8 | 4,708,408 | 10 |
| 1280 | 1x | — | D24FS8 | 3,224,349 | 10 |
| 1040 | 1x | — | D24S8 | 1,511,678 | 10 |
| 1280 | 1x | 2_10_10_10_AS_10_10_10_10 | — | 923,350 | 12 |
| 320 | 2x | 2_10_10_10_FLOAT | D24FS8 | 513,147 | 10 |
| 1280 | 1x | 8_8_8_8 | D24FS8 | 183,606 | 10 |
| 1280 | 1x | 2_10_10_10_FLOAT | — | 179,863 | 11 |
| 320 | 2x | 2_10_10_10_FLOAT_AS_16_16_16_16 | D24FS8 | 130,188 | 10 |
| 640 | 4x | 2_10_10_10 | D24FS8 | 126,346 | 10 |
| 80 | 1x | 8_8_8_8 | D24FS8 | 124,294 | 9 |
| 1280 | 1x | 8_8_8_8 | — | 113,334 | 10 |
| 1280 | 1x | 2_10_10_10_AS_10_10_10_10 | D24FS8 | 70,500 | 8 |
| 1280 | 1x | 2_10_10_10 | — | 53,515 | 12 |
| 640 | 4x | — | D24FS8 | 25,295 | 10 |
| 640 | 4x | — | D24S8 | 18,064 | 11 |
| 640 | 4x | 8_8_8_8 | D24FS8 | 10,190 | 10 |
| 640 | 4x | 2_10_10_10_FLOAT | D24FS8 | 9,316 | 11 |
| 80 | 1x | 32_FLOAT | — | 9,032 | 11 |
| 160 | 4x | 2_10_10_10_FLOAT | D24FS8 | 3,496 | 10 |
| 1280 | 1x | 8_8_8_8_GAMMA | — | 3,487 | 6 |
| 400 | 2x | 8_8_8_8 | D24FS8 | 1,245 | 6 |
| 200 | 4x | 8_8_8_8 | D24FS8 | 1,096 | 6 |
| 200 | 4x | — | D24S8 | 984 | 6 |
| 400 | 1x | 8_8_8_8 | — | 984 | 6 |
| 1280 | 1x | — | — | 456 | 4 |
| 1280 | 2x | — | — | 72 | 3 |
| 1280 | 1x | 16_16_16_16 | — | 46 | 1 |
| 640 | 4x | 16_16_16_16 | — | 27 | 1 |

Every surface uses one color target at most; multiple render targets never
occur. The 1280-pitch 4× float surfaces are the banded main scene; the 1280
and 1040 depth-only 1× surfaces and the D24S8 1040 surface are the shadow
phases.

## Resolves (20 kinds)

| Source | Samples | Destination | Exp bias | Clears | Copies | Destination sizes |
| --- | --- | --- | ---: | --- | ---: | --- |
| color 2_10_10_10_FLOAT 1x | sample0 | 2_10_10_10 | −4 | yes | 167,664 | 128×128, 64×64, 32×32, 32×16 … |
| color 2_10_10_10_FLOAT 1x | sample0 | 2_10_10_10 | −2 | yes | 145,724 | 1280×720, 320×192, 160×192, 160×96 … |
| color 2_10_10_10_FLOAT 4x | average 0–3 | 2_10_10_10 | −2 | yes | 49,230 | 1280×720 |
| color 2_10_10_10_FLOAT_AS_16 4x | average 0–3 | 2_10_10_10 | −2 | yes | 29,502 | 1280×720 |
| depth D24FS8 4x | sample0 | 8_8_8_8 | 0 | no | 26,244 | 1280×720 |
| color 8_8_8_8 1x | sample0 | 8_8_8_8 | 0 | yes | 25,320 | 1280×720, 640×360, 64×64 |
| depth D24S8 1x | sample0 | 8_8_8_8 | 0 | no | 18,651 | 1024×1024 |
| color 2_10_10_10_FLOAT 2x | average 0–1 | 2_10_10_10 | −4 | yes | 12,150 | 256×256 |
| color 8_8_8_8 1x | sample0 | 8_8_8_8 | 0 | no | 11,385 | 1280×720, 384×128 |
| color 32_FLOAT 1x | sample0 | 32_FLOAT | 0 | yes | 9,032 | 32×32 |
| color 2_10_10_10_FLOAT_AS_16 2x | average 0–1 | 2_10_10_10 | −4 | yes | 8,826 | 256×256 |
| color 2_10_10_10 1x | sample0 | 2_10_10_10 | −2 | yes | 8,165 | 1280×720 |
| color 2_10_10_10 1x | sample0 | 2_10_10_10 | 0 | yes | 7,670 | 1280×720 |
| depth D24FS8 1x | sample0 | 8_8_8_8 | 0 | no | 5,095 | 1280×720 |
| color 2_10_10_10_AS_10_10_10_10 1x | sample0 | 2_10_10_10 | 0 | yes | 4,568 | 1280×720 |
| color 2_10_10_10_FLOAT 1x | sample0 | 8_8_8_8 | 0 | yes | 2,004 | 320×192 |
| color 2_10_10_10_FLOAT_AS_16 2x | average 0–1 | 2_10_10_10 | −2 | yes | 1,136 | 1280×720 |
| color 8_8_8_8 2x | average 0–1 | 8_8_8_8 | 0 | yes | 1,096 | 384×128 |
| depth D24FS8 2x | sample0 | 8_8_8_8 | 0 | no | 96 | 1280×720 |
| color 16_16_16_16 1x | sample0 | 16_16_16_16_FLOAT | 0 | yes | 75 | 1280×720 |

A resolve rectangle is in surface pixel coordinates and writes the same
texels of the destination texture whose origin is `RB_COPY_DEST_BASE`
(`draw_util::GetResolveInfo`). Depth resolves write the packed guest depth
and stencil bits into an 8_8_8_8 texture that later draws fetch as
`24_8`/`24_8_FLOAT` or 8_8_8_8; the native path must reproduce those bits,
not a converted color.

## Textures (22 format and dimension pairs)

| Format | Dimension | Fetches | From a resolve | Routes |
| --- | --- | ---: | ---: | ---: |
| DXT1 | 2D | 22,076,065 | 0 | 5 |
| 8_8_8_8 | 2D | 11,102,302 | 10,178,177 | 5 |
| DXT4_5_AS_16_16_16_16 | 2D | 5,890,728 | 75,818 | 5 |
| DXT4_5 | 2D | 3,229,479 | 0 | 5 |
| 2_10_10_10_AS_16_16_16_16 | cube | 2,930,727 | 2,930,727 | 5 |
| DXT4_5 | cube | 2,844,387 | 0 | 5 |
| DXT1_AS_16_16_16_16 | 2D | 2,146,124 | 4,279 | 5 |
| 2_10_10_10_AS_16_16_16_16 | 2D | 1,306,286 | 1,306,275 | 6 |
| DXN | 2D | 703,883 | 0 | 5 |
| 24_8 | 2D | 656,025 | 656,025 | 5 |
| DXT5A | 2D | 203,741 | 2,418 | 5 |
| DXT1 | cube | 115,129 | 0 | 5 |
| 24_8_FLOAT | 2D | 82,244 | 82,244 | 5 |
| 32_FLOAT | 2D | 50,692 | 50,687 | 5 |
| 8_8_8_8_AS_16_16_16_16 | 2D | 33,818 | 9,644 | 6 |
| 8_8_8_8 | 3D | 25,346 | 0 | 5 |
| 8 | 2D | 15,153 | 0 | 6 |
| DXT2_3_AS_16_16_16_16 | 2D | 10,688 | 10,688 | 1 (map) |
| DXT3A | 2D | 5,007 | 1,336 | 5 |
| 1_REVERSE | 1D | 2,836 | 0 | 1 |
| 16 | 1D | 2,836 | 0 | 1 |
| 16_16_16_16_FLOAT | 2D | 238 | 238 | 1 |

"From a resolve" means the fetch base lay inside a range some earlier
resolve in the same 60-frame window had written. Block-compressed rows with
a nonzero count (DXT on the map, DXT4_5_AS_16, DXT5A, DXT3A) are guest
memory the CPU reused after a resolve, not resolve output: no resolve
writes a block format. The native renderer therefore needs write
generations, not just address ranges, to decide whether a fetch reads
resolve output or CPU data.

Resolve-sourced fetches (depth-as-color shadow maps, reflection cubes, the
post chain) must bind native resolve outputs; every other layout is decoded
from guest memory (BC/DXN/DXT5A block formats, 8-bit movie planes, the
16³ grading LUT and two 1D lookup textures).

## Primitives, front buffer, side effects

- Guest primitives: triangle strips 16.9 M draws, triangle lists 3.5 M, quad
  lists 3.3 M, point lists 0.81 M, rectangle lists 0.44 M. No line, fan,
  polygon or tessellated draws were observed.
- All 17,580 swaps presented a 1280×720 `2_10_10_10_AS_16_16_16_16` front
  buffer.
- **Memexport: zero draws in every mode.**
- Occlusion: zero draws ran under the legacy occlusion query. FH1's
  queries use `EVENT_WRITE_ZPD`: 1,056 events over 48 report addresses, all
  in two 60-frame windows of the mode-boundary route (frames 1381–1440,
  the title-to-free-roam load, and 2281–2340, the event menus). Race, free
  roam, map, pause, photo and movie frames issued none. The native renderer
  answers them through the `legacy` host-query path (XR-06 of the backlog).
- Optimized clears: depth and rectangle clears appear in every mode with
  scene rendering. The Xenos renderer replaced some of them with its owned
  clears; the native executor runs them itself.

## Routes added later

`fh1-rewind-sync` (the new-player opening event from `fresh-2026-09-28`,
driving and rewinding) and `fh1-buy-car` (the autoshow, a purchase and the
thumbnail studio tracks) were censused the same way on Xenos: 10,980
frames, zero overflow, no memexport or occlusion-query draws, no new
primitive types and the same front buffer. Against the tables above they
add 11 surface configurations (8_8_8_8 color over the 4x D24FS8 scene
layout for the showroom and studio renders, and small 1x and 4x targets of
pitch 80 to 800), 10 resolve kinds (8_8_8_8 and 16_16_16_16_FLOAT copies
of 32x32 to 768x288, the thumbnail among them, and a 4x average of an
8_8_8_8 scene target) and 47 texture layouts (cube maps of 64 to 512
texels, more DXT/DXN sizes and mip ranges). None needs new executor code:
`native` runs both routes with zero executor skips.

## Census cost

Each record carries `cost_ns`, the time spent inside the census (including
the window flush and two clock reads per event). On the mode-boundary route
at the default log level (SDK `a440732`): 172 ns per draw, median
0.41 ms per frame, p95 0.92 ms, worst 60-frame window 1.005 ms at 6,500
draws per frame (race). The target was under 1 ms per frame; only the
heaviest race windows reach it. The census is off by default.

## Gaps and unknowns

- When this census was taken, the installed 1x pack missed at least two
  vertex-shader variants (`AFF858C659830DD3` modification 1 and
  `AE8FEE9795590D78` modification `0x7F`). The producer now translates the
  autoshow variants, and packs repair themselves from recorded misses (see
  [pack misses](SHADER_PACK_FORMAT.md#pack-misses-and-self-repair)); a
  shader missing from the pack is still dropped until the next launch.
- Night, weather, livery and multiplayer screens are not in this census yet
  (no pinned routes reach them). New configurations they bring must enter
  this contract as named skips.
- Window-level mode boundaries mix a few transition frames into neighbouring
  modes.
- The census records configurations, not per-frame event order; ordering
  still comes from executing the guest stream in order.
