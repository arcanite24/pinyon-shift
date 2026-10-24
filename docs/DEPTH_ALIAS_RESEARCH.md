# Sharing FH1's half-pitch depth image

Research R01, 2026-10-24. **Keep, default on for full four-sample storage.**
On multivac (Ryzen 7 5800X, RTX 4080, NVIDIA 581.08), the guarded path
saves 1.092 ms of executor GPU time at 3x, meeting the 1 ms desktop gate.
MSAA-off and two-host-sample storage retain the existing path.

The trial starts from Pinyon Shift `34e2f00c` and ShiftGlue `102fe952`,
with frozen generated code and private copies of the
`appdata-2026-09-27` render seed. The idea came from the
[FH2 renderer notes](https://github.com/Gabrick75/fh2-recompiled/blob/f1e3f12/docs/renderizador_nativo.md).
The implementation uses ShiftGlue's existing surface, ownership and
viewport machinery; no FH2 source was copied or translated.

## The layout and the observed draws

Images are keyed by EDRAM base, pitch, MSAA mode, format and depth/color
type. The 1280x720 1x depth at tile 0, pitch 16, and its 640x360 4x view
therefore normally have separate images. Their layouts address the same
720 tiles. Switching ownership copies depth and stencil between them.

One-frame logs at executor frame 4400 of `fh1-race-start-wait` confirm
five 720-tile alias transfers with stencil in every baseline configuration:

| Scale | MSAA | All transfers | All tile passes | Alias transfers | Alias tile passes |
| --- | --- | ---: | ---: | ---: | ---: |
| 1x | off | 285 | 50,427 | 5 | 32,400 |
| 3x | off | 220 | 44,739 | 5 | 32,400 |
| 1x | 4x | 220 | 44,739 | 5 | 32,400 |
| 3x | 4x | 220 | 44,739 | 5 | 32,400 |

NVIDIA reconstructs stencil in eight bit passes, plus one depth pass.
Whole-frame counts above are structural observations, not timing pairs:
loading waits put frame 4400 at different points in the race start.

The base-0 4x depth has three depth-only draws and a color-writing draw
using tile 720, pitch 16, format `8_8_8_8`. Depth is ALWAYS with writes,
NEVER without writes, or disabled. The three stencil-enabled draws
compare ALWAYS and replace all front-face stencil bits with zero
(read mask 0, write mask FF, reference 0). The color draw reads pixel
interpolator 0. This trace does not establish an ordered depth comparison
for quarter-resolution transparencies. The existing
[EDRAM finding](../site/findings/rendering.toml) records these states.

## What can share

The hot boolean `fh1_shared_depth_alias`, on by default, selects matching
base-0, pitch-16 4x D24FS8 draws whose inputs permit a different pixel
rate. Their attachment keys use the 1x layout; viewport, scissor and draw
coordinate scale double, and the pipeline uses one host sample. Matching
depth clears use doubled rectangles on that image too. Ordinary ownership
tracking still converts layouts for subsequent input-sensitive draws and
resolves. Changing the flag invalidates target preparation memos.

Only full four-host-sample storage qualifies. In `HostSample` in
`fh1_native_edram.hlsli`, single-sample MSAA keeps one value from a 2x2
group when transferring from 1x to 4x; returning broadcasts it to all four
pixels. Two-host-sample storage merges horizontal pairs. A general shared
path must reproduce that collapse or prove an overwrite. Pointing at the
original full-resolution image alone does neither, so those modes retain
the original images.

Ordered depth comparisons, occlusion queries, pixel depth writes,
interpolated inputs, pixel-position generation, texture fetch results,
shader kills, alpha testing, alpha-to-coverage and partial sample masks
retain the original layout. Shifted untiled bands also retain it because
their copy-down bookkeeping uses the original surface's pixel units.
In particular, the color-writing alias draw keeps its original 4x image
and interpolator rate. The three eligible depth-only draws share the 1x
image. Two alias copies remain; three are removed.

The existing depth-overwrite optimization must stay active. Its CPU
rectangles are in guest pixels, so both inner and outer rectangles double
before claiming tiles on the canonical image. Their tile coverage is
unchanged: a 40x8-pixel 4x tile becomes an 80x16-pixel 1x tile. Disabling
that optimization added a 720-tile color-to-depth transfer, 6,480 passes,
and understated the saving as 0.783 ms. The final path preserves its count
exactly and removes that extra copy. A coordinate self-check covers every
boundary through 8,192 guest pixels.

## Measured result

The final full-4x frame logs show **5 to 2 alias transfers**, or
**32,400 to 12,960 alias tile passes**. MSAA-off remains 5 and 32,400.
Across performance blocks, the median total reduction is three transfers
and 19,440 tile passes per frame; ordinary scene-dependent transfers still
vary. The depth-overwrite count changes by zero in every block.

At 3x full 4x MSAA, both toggle orders supply six disjoint three-window
blocks each. Positive numbers below mean time saved:

| Metric | Blocks | Median saving | Range |
| --- | ---: | ---: | ---: |
| Executor GPU frame | 12 | 1.092 ms | 0.798–1.321 ms |
| Transfer GPU phase | 12 | 1.047 ms | 0.977–1.122 ms |
| GPU frame, draw counts within 5% | 8 | 1.092 ms | 0.798–1.145 ms |

The balanced subset's draw difference is median +1.4 per frame, range
-30.6 to +38.0. Fitting pure profile windows for enabled state, draw count
and linear frame trend gives 1.023 ms saved in AB and 1.086 ms in BA.
The official `summarize-inrun-ab.py` also finds paired mean frame-time
savings of 1.046 and 1.149 ms respectively. The MSAA-off A/A control has
12 blocks, median GPU difference 0.064 ms, with a scene-change outlier of
2.331 ms; unpaired side averages are unsuitable here.

## Image qualification and method

All 16 off/on and on/off comparisons pass the runner's existing limits:
MAE 12, RMSE 30, different-pixel ratio 0.60, channel tolerance 4.
These are full-resolution captures, not exact matches of a frozen frame.

| Route | Scale | MSAA | Off/on MAE | On/off MAE | Off/off MAE |
| --- | --- | --- | ---: | ---: | ---: |
| Race start | 1x | off | 1.91 | 0.96 | 2.12 |
| Race start | 3x | off | 6.65 | 5.57 | 8.25 |
| Race start | 1x | 4x | 1.65 | 1.04 | 1.88 |
| Race start | 3x | 4x | 9.78 | 7.97 | 11.52 |
| Free-roam drive, then handbrake | 1x | off | 6.96 | 7.54 | 9.68 |
| Free-roam drive, then handbrake | 3x | off | 8.83 | 6.82 | 11.12 |
| Free-roam drive, then handbrake | 1x | 4x | 5.00 | 3.84 | 6.53 |
| Free-roam drive, then handbrake | 3x | 4x | 3.95 | 5.25 | 6.78 |

Lighting and animation continue while parked. Two 3x off/off references
exceed the different-pixel-ratio limit; their MAE remains below 12, and
both comparisons against the enabled image pass all three limits.
Maximum vehicle movement within a capture triplet is 9.1 mm.

Capture steps use completed output frames, leaving 15 between a toggle
and capture. A time-based calibration was unsuitable: a 3x readback took
411 ms and the next toggle, diagnostic arm and reset ran in one burst.
A logged flag change alone did not establish the state of a queued image.
Keep an off/off reference and inspect the pose. The handbrake is A;
an earlier B-button control continued reversing and was excluded.

Performance uses uncapped output, vsync off, GPU profiling and 150-native-
frame intervals inside five-second toggle windows. Intervals crossing a
toggle or dropping timestamps are excluded. Disjoint ABA/BAB blocks
compare the middle window with its neighbors. Both orders, draw counts,
the 5% subset and regression are retained in the evidence. Fleet locks
exclude heavy builds and other desktop game instances during these runs.

Resolve dumps at 1x are diagnostic temporal comparisons. Resolve
identities can change even on off/off sides; mismatched sets are not
counted as equality. The dump reads the guest mirror, so it does not
qualify 3x scaled resolve contents. No bit-exact stencil claim is made
from these dumps; input-sensitive draws retain the existing path.

The desktop gate qualifies this default. Odin was not tested and no
mobile saving is claimed. `fh1_shared_depth_alias=false` restores the
separate-image path. Captures, profiles, route snapshots, independent
analysis scripts and temporary trace patches remain under
`.local/codex-fleet/reports/R01/` in the main checkout.
