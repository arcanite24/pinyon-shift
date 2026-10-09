---
title: Performance
section: Technical
order: 2
description: Measured frame rates of Pinyon Shift on desktop and Android, against Xenia and the console.
---

# Performance

Desktop numbers are from one machine: AMD Ryzen 7 5800X (8 cores), 128 GB RAM, NVIDIA GeForce RTX 4080 (driver 581.08), Windows 11, a 3840 × 2160 display at 120 Hz.

## Against Xenia

The same scene from a new profile: the opening intro cinematic and the start of the opening drive, at 1x (1280 × 720), each program windowed at its default settings.

| Program | Intro cinematic | Opening drive |
| --- | ---: | ---: |
| Xenia Canary (`67d80958c`, Direct3D 12) | 30.0 fps | 30.0 fps |
| Pinyon Shift 0.1.0 (ReXGlue Xenos renderer) | 28.3 fps | 29.0 fps |
| **Pinyon Shift, native renderer on Vulkan** | **119.8 fps** | **120.0 fps** |

The console runs the game at 30 fps, and Xenia keeps that cap. The native renderer runs up to the display's refresh rate, which caps the last row at 120.

## The race

The scripted race (`fh1-race-sync`) is the heaviest route. Measured over its busiest frames (5,000 draws or more), with the game limited to 120 fps.

| Internal resolution | Median frame time | Median | p95 | Graphics memory |
| --- | ---: | ---: | ---: | ---: |
| 1x (1280 × 720), no MSAA, FSR 1 | 8.41 ms | **119 fps** | 10.75 ms | 0.9 GB |
| 2x (2560 × 1440), the game's 4x MSAA | 8.43 ms | **119 fps** | 11.71 ms | 3.3 GB |
| 3x (3840 × 2160), no MSAA | 9.82 ms | **102 fps** | 13.58 ms | 4.3 GB |

At a 60 fps limit, 2x with MSAA holds a 16.66 ms median (p95 17.04 ms).

## Fewer cores

The Low-spec 60 preset on the heavy start of the race (about 6,200 draws a frame), with the same machine limited to fewer cores or less free VRAM. These show sensitivity to core count, not real older hardware: a real older CPU also has smaller caches and lower clocks, and the GPU is still an RTX 4080.

| Configuration | Game rate | Presents a second | Median | p95 |
| --- | ---: | ---: | ---: | ---: |
| 16 threads | 60 | 59.7 | 16.65 ms | 17.03 ms |
| 4 cores, 8 threads | 60 | 59.7 | 16.67 ms | 17.07 ms |
| 4 cores, 4 threads | 60 | 59.7 | 16.66 ms | 17.09 ms |
| 2 cores, 4 threads | 60 | 59.3 | 16.68 ms | 18.17 ms |
| 4 slow cores, Balanced 40 | 40 | 39.9 | 25.00 ms | 25.48 ms |
| 4 cores, 8 threads, about 1 GB VRAM free | 60 | 59.6 | 16.68 ms | 17.02 ms |

The game needs about 1.1 GB of graphics memory at 1x without MSAA, so a 2 GB card has room. Integrated GPUs and the Steam Deck haven't been measured yet.

## Android

Free roam and races at 1x with the in-game presets.

| Device | GPU | SMOOTH 60 | 4x MSAA, 60 limit | QUALITY 30 |
| --- | --- | ---: | ---: | ---: |
| AYN Odin 2 Portal | Adreno 740, Turnip | About 60 fps | About 52 fps | Holds 30 |
| AYN Thor (Max) | Adreno 740, Turnip | About 60 fps | | |
| RedMagic Astra | Adreno 830, Qualcomm | 60 fps while cool | | |

The Astra throttles after about three minutes: 37 to 39 fps at 40 to 44 °C skin temperature, 26 to 28 above 44.5 °C. These are rough single-device measurements.

Methods, logs and the full tables are in [docs/PERFORMANCE.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/PERFORMANCE.md) and the records in [benchmarks/](https://github.com/arcanite24/pinyon-shift/tree/dev/benchmarks).
