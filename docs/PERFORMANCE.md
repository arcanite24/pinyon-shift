# Performance

Measured on 2026-09-30 on one machine: AMD Ryzen 7 5800X (8 cores),
128 GB RAM, NVIDIA GeForce RTX 4080 (driver 581.08), Windows 11 Pro 26200,
3840×2160 display at 120 Hz.

## Against Xenia and the old Xenos renderer

The same scene on all four, from a new profile: the game's opening intro
cinematic and the start of the opening drive in the Viper. The internal
resolution is 1x (1280×720) and every program runs in a window at its default
settings.

| Program | Intro cinematic | Opening drive |
| --- | ---: | ---: |
| Xenia Canary (`67d80958c`, Direct3D 12) | 30.0 fps | 30.0 fps |
| Pinyon Shift 0.1.0 (ReXGlue Xenos renderer) | 28.3 fps | 29.0 fps |
| Pinyon Shift, native renderer on Direct3D 12 (legacy) | 118.7 fps | 119.5 fps |
| **Pinyon Shift, native renderer on Vulkan** | **119.8 fps** | **120.0 fps** |

On the console *Forza Horizon* runs at 30 fps, and Xenia and the Xenos-era
build keep that cap. The native renderer renders at up to the display's
refresh rate, here 120 Hz, which caps both native rows. The race below shows how
much headroom is left.

<details>
<summary>How these were measured</summary>

Each program started FH1 from a fresh profile and was driven by the same
script: A was pressed every five seconds, as the repository's
`fh1-opening-sync` route does. Xenia got the key as real input while its window
was in the foreground; the others got it posted to their window. Each target had
a warm-up run first, and the measured run started from a fresh profile again
with only the shader and pipeline caches kept.

- **Windows.** The intro cinematic is 105–165 s after launch and the opening
  drive 185–240 s, on all four (checked in window captures every 15 s).
- **Xenia and the 0.1.0 build.** Frames are counted on screen with DXGI Desktop
  Duplication, and only frames whose image changed count, since Xenia presents
  the same image several times. Averages are over one-second counts; the worst
  second was 29 fps for Xenia and 21 fps for the 0.1.0 build.
- **Native rows.** These are the game's own frame log. The same on-screen count
  gives 109.5/119.6 fps on Direct3D 12 and 116.1/118.2 fps on Vulkan, slightly
  lower because consecutive frames sometimes look alike.
- **Xenia with vsync off.** Xenia then shows about 125 distinct frames a
  second, but its emulated vblank is no longer synchronized and the game's clock
  runs fast: it reached the drive about 25 s early. Those runs are not in the
  table.

</details>

## The race, native renderer

The scripted race (`fh1-race-sync`) is the heaviest route. It is measured on
2026-10-07 at commit `e561680` over the race's frames with 5,000 draws or more
(its busiest part), with the game rate limited to 120, in a hidden window, from
the same save.

| Internal resolution | Median frame time | Median frame rate | p95 | Graphics memory |
| --- | ---: | ---: | ---: | ---: |
| 1x (1280×720), no MSAA, FSR 1 | 8.41 ms | **119 fps** | 10.75 ms | 0.9 GB |
| 2x (2560×1440), the game's 4x MSAA | 8.43 ms | **119 fps** | 11.71 ms | 3.3 GB |
| 3x (3840×2160), no MSAA | 9.82 ms | **102 fps** | 13.58 ms | 4.3 GB |

At a 60 fps limit, 2x with MSAA holds a 16.66 ms median (p95 17.04 ms). The records are
in [benchmarks/low-spec](../benchmarks/low-spec). On 2026-09-30 the same race took
9.1, 12.7 and 28.7 ms at 1x, 2x and 3x, and the retired Direct3D 12 backend
12.7, 15.2 and 17.5 ms. How the Vulkan path got here is in the
[performance backlog](PERFORMANCE_BACKLOG.md) and the
[desktop renderer backlog](DESKTOP_RENDERER_BACKLOG.md).

## Lower-end hardware (simulated)

The **Low-spec 60** preset (1x, no MSAA, bilinear output, the game's own
texture filtering, 60 fps) on the heavy start of the race
(`fh1-race-start-wait`, about 6,200 draws a frame), with this machine limited
to fewer cores or less free VRAM. These are sensitivity numbers from one
machine: a real older CPU also has smaller caches, slower memory and lower
clocks, and the GPU here is still an RTX 4080.

<!-- Generated: tools/summarize-low-spec.py table --compact with the records in benchmarks/low-spec/2026-10-07 (all-sleep, c4t8-auto, c4t4-sleep, c4t4load-sleep, c2t4-sync-auto, c4t4load-fps40, c4t8-pressure). -->
| Configuration | Game rate | Presents a second | Median | p95 | Long frames | Decoder CPU | Recorder CPU | Title CPU | Peak VRAM |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 threads (the reference machine) | 60 fps | 59.7 | 16.65 ms | 17.03 ms | 0.5 % | 7.5 ms | 7.2 ms | 4.3 ms | 1126 MB |
| 4 cores, 8 threads | 60 fps | 59.7 | 16.67 ms | 17.07 ms | 0.5 % | 8.8 ms | 8.9 ms | 5.0 ms | 1128 MB |
| 4 cores, 4 threads | 60 fps | 59.7 | 16.66 ms | 17.09 ms | 0.6 % | 7.4 ms | 7.4 ms | 4.3 ms | 1122 MB |
| 4 slow cores (SMT siblings busy) | 60 fps | 59.2 | 16.69 ms | 17.84 ms | 0.6 % | 11.1 ms | 10.6 ms | 5.8 ms | 1128 MB |
| 2 cores, 4 threads (`fh1-race-sync`) | 60 fps | 59.3 | 16.68 ms | 18.17 ms | 1.0 % | 10.2 ms | 11.2 ms | 6.0 ms | 1118 MB |
| 4 slow cores, Balanced 40 | 40 fps | 39.9 | 25.00 ms | 25.48 ms | 0.4 % | 11.4 ms | 10.8 ms | 6.5 ms | 1128 MB |
| 4 cores, 8 threads, about 1 GB of VRAM free | 60 fps | 59.6 | 16.68 ms | 17.02 ms | 0.6 % | 8.9 ms | 9.0 ms | 5.0 ms | 1130 MB |

Long frames are those over one and a half frame intervals (25 ms at 60 fps).
The CPU columns are per frame. Every row holds its rate: the CPU work of
Low-spec 60 fits 4 cores, and 2 cores with 4 threads is the edge. Four slow
cores sit at it too: eight runs gave 58.9 to 59.3 presents a second, against
59.6 to 59.7 for four ordinary cores, so they meet the 59 a second gate only
in some runs; there, Balanced 40 leaves a wide margin. The game
needs about 1.1 GB of graphics memory at 1x without MSAA (34 native surfaces
take 265 MB, textures about 150 MB) and stays there over a long drive, so a
2 GB card has room. Whether a slower GPU keeps up is not simulated: integrated
GPUs and the Steam Deck need their own runs. The records, with the commit each
ran, are in [benchmarks/low-spec](../benchmarks/low-spec); the plan is in the
[low-spec backlog](LOW_SPEC_BACKLOG.md).

## Android handhelds

Measured in free roam and races at 1x (1280×720 internal) with the in-game
presets, from the same save. SMOOTH 60 is no MSAA, no sun shadows and a
60 fps limit; QUALITY 30 keeps the game's 4x MSAA and shadows at 30 fps.
Both draw FH1's three predicated tiles once and redraw the reflection map
at a quarter rate.

| Device | SoC, GPU, memory | Driver | SMOOTH 60 | 2x MSAA, 60 limit | 4x MSAA, 60 limit | QUALITY 30 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| AYN Odin 2 Portal | Snapdragon 8 Gen 2, Adreno 740, 8 GB | Turnip Gen8 V37 (bundled) | **about 60 fps** (15.5–16.2 ms GPU) | about 58 fps | about 52 fps | holds 30 |
| AYN Thor (Max) | Snapdragon 8 Gen 2, Adreno 740, 16 GB | Turnip Gen8 V37 (bundled) | **about 60 fps** | — | — | — |
| RedMagic Astra (nubia NP05J) | Snapdragon 8 Elite, Adreno 830 | Qualcomm (system) | **60 fps while cool**; 37–39 at 40–44 °C skin, 26–28 above 44.5 °C | — | — | — |

On Adreno 7xx, Mesa Turnip is much faster than the stock Qualcomm driver:
before the presets, the Odin's busy drive took 32 ms at 4x MSAA with Turnip
Gen8 V37 against 49 ms with the stock driver. The tablet's limit is heat,
not frame cost: after about three minutes it throttles. The numbers are
rough, single-device measurements; the method and logs are in the
[Android](ANDROID.md), [Odin](ANDROID_ODIN_BACKLOG.md) and
[60 fps](ANDROID_60FPS_BACKLOG.md) documents.
