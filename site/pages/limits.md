---
title: Performance limits
section: Technical
order: 2
description: For each measured device, its frame-rate target, whether the CPU or the GPU limits it, and how much room is left.
---

# Performance limits

Before choosing an optimization, check which side holds each device back. CPU work saved on a GPU-bound device doesn't make frames faster, and the reverse is just as true. The table uses the scripted race (`fh1-race-sync` and its longer Deck variant) unless a row says otherwise. Each figure is from the page or document linked in the row.

| Device | Target | Limited by | Margin | Source |
| --- | --- | --- | --- | --- |
| Desktop: Ryzen 7 5800X, RTX 4080, Windows | 120 fps (2x, 4x MSAA) | CPU: the draw recorder thread is busy 7.5-8.2 ms of the 8.3 ms frame | None at 120: with the limit at 240 the frame takes about 8.5 ms | [Performance](performance.md#the-race) |
| Steam Deck LCD, SteamOS | 60 fps (1x) | GPU, inside a shared power budget (below) | GPU none: 99-100 % busy, 16.4 ms of GPU time a frame. CPU: the busiest threads take 8-10 ms of 16.7 | Deck race, 2026-11-14 (below) |
| Laptop: i5-8250U, Intel UHD 620, Windows | 60 fps (LOW-SPEC 60, 1x) | GPU: about 78 ms of GPU time a frame, 12-13 fps; the CPU (recorder 14-15 ms a frame) would also limit it near 60 | Far below the target: the GPU needs about a fifth of its work | blindvac runs, 2026-11-14 (below) |
| AYN Odin 2 Portal, Adreno 740 | 60 fps (SMOOTH 60, 1x) | GPU | About 1 ms: 15.5 ms of GPU time a frame | [docs/ANDROID.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/ANDROID.md) |
| Galaxy Tab S10 Ultra, Mali-G720 | 60 fps | GPU (fragment work) | Short: about 20 ms a frame with the Mali defaults, 21.3-22.3 ms of GPU time before them | [Android](android.md) |
| Mac mini, M4 Pro | 120 fps at 1x, 60 at QUALITY 60 | GPU once the internal resolution or MSAA goes up | Holds 120 at 1x with MSAA off or 4x; 2x drops to about 82 fps (51 with 4x MSAA) | [macOS](macos.md) |

## The Steam Deck's shared power budget

The Deck's CPU and GPU share one power limit of 15 W. During the race the APU draws 9-12 W and the GPU stays 99-100 % busy at 1.2-1.3 GHz, below its 1.6 GHz peak. The GPU's clock follows the power the CPU leaves free, so its "GPU time" of about 16.4 ms fills the frame at whatever clock it gets. The two consequences:

- CPU savings don't shorten the frame directly. They lower the CPU's share of the power and leave more for the GPU's clock, which is worth having at the 60 limit but doesn't show up as frame time.
- GPU savings at the 60 limit show up as a lower clock or lower power, not as GPU time. Fewer draws and coarser LODs (`pinyon_shift_lod_distance_scale`) are the levers that matter here, and have to be judged by draw counts, power or the clock.

Measured with `gpu_busy_percent`, `pp_dpm_sclk` and the APU's `power1_average` sampled once a second during the race, and with the frame log's `guest_frame_gpu_time_ns`.

## Low-end Windows

On the UHD 620 laptop the GPU takes about 78 ms a frame at 1x, so no CPU saving changes its frame rate. CPU changes were measured there for their own sake: the symbol ordering file changed neither the frame time nor process CPU (three pairs). In-run A/Bs of the native scene culling, the LOD distance scale at 2 and streaming constant stores (two runs each, toggled every 10 seconds of the race) could not separate them from the scene: at 13 fps a run has only four blocks, and the two sides differed by up to 320 draws a frame from where the race was. They stay at their Windows defaults (native culling off). The GPU's work would have to fall about five times for LOW-SPEC 60 to reach its target; a resolution below 1x was measured and shelved ([render scale](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/RENDER_SCALE_BACKLOG.md)). Older numbers for this laptop, including the GeForce 930MX, are on the [performance page](performance.md#an-old-laptop).

## What follows

- Desktop: CPU-bound, so the recorder and the guest threads are where time goes. On Linux the code is on 2 MiB pages; a BOLT layout pass is wired up but off ([recompiler](recompiler.md)).
- Deck, Android and low-end PCs: GPU-bound. Fewer draws and less shading per draw count; CPU-side gains count on the Deck only through its power budget.
