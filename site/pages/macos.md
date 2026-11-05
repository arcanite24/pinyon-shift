---
title: macOS
section: Start
order: 4
description: Build and play Pinyon Shift natively on an Apple silicon Mac, or try the experimental Intel Mac build.
---

# macOS

A native build for Apple silicon. The game's Vulkan renderer runs on Metal through MoltenVK, which the build includes.

## Requirements

- An Apple silicon Mac (M1 or newer) with macOS 13 or newer. Intel Macs on macOS 13.3 or newer have an [experimental build](#intel-macs-experimental).
- Your ISO of the USA retail disc (`MS-2505`), or the game extracted to a folder (the Games on Demand release of the same build works too), and about 20 GB free. Windows still takes the disc only.
- Apple's Command Line Tools. The launcher offers to install them.

## Install and play

1. Download `PinyonShift-Launcher-macos-arm64.zip` from the [latest release](https://github.com/arcanite24/pinyon-shift/releases/latest) and open it.
2. The app is not notarized, so approve its first start under **System Settings → Privacy & Security → Open Anyway**.
3. Install the Command Line Tools if the launcher asks for them.
4. Choose your disc image, confirm ownership and choose **Verify and build**.
5. Choose **Play**. Press **F6** in game for settings.

On the M4 Pro Mac mini, full screen on a 120 Hz 4K TV with the frame-rate
limits off, a 40 s free-roam drive (2026-11-01) held 120 fps at 1x, with
MSAA off or 4x. At 2x it averaged about 82 fps with MSAA off and 51 fps
with 4x MSAA. On a Mac QUALITY 60 therefore uses 2x MSAA, which holds its
60 fps limit on the M4 Pro.
Raise scale and MSAA separately; the
[platform measurements](platforms.md#macos-on-apple-silicon) explain the
workload and its limits.

On a 5K or 6K display, or a 4K one in a scaled mode, the game draws at most
3840 × 2160 pixels and macOS scales them to the screen; drawing all 6016 ×
3384 backing pixels halved the frame rate. `window_max_pixel_density = 4`
in the config restores full density, and `1` draws one pixel per point.

Fullscreen uses a borderless window on the current desktop, not a separate
macOS Space. The presenter keeps the Metal drawable at the swapchain size
through fullscreen changes, and the window rebuilds its connection when SDL
reports a fullscreen transition finished; scripted transitions passed, while
the OS-visible result still needs an interactive check on the affected Macs.
On a 5K or 6K display, or a 4K one in a scaled HiDPI mode, the drawable is
capped by pixel area at 3840 x 2160 (`window_max_pixel_density`; 0, the
default, is that automatic cap, 4 uses every backing pixel; restart required)
and the system scales it to the window. Automatic density never falls below
one drawable pixel per window point.

The launcher's **DLC** panel imports your own DLC packages ([DLC and title update](dlc.md)), and **Import a save** brings a save from another install or from Xenia. On the M4 Pro all 21 packages imported and their 84 car rows loaded and could be driven in a scripted route, and the v4 build ran the 1000 Club challenges and reached the Horizon Rally entry.

In the recorded M1 tests, the free-roam drive rendered at about 52 fps at 1x (19 ms of GPU a frame) with the defaults, more with TEXTURE GAMMA FAST, shadows off and quarter-rate reflections (in the play session, with the frame rate limit at 60 and shadows, bloom, motion blur and depth of field all on, it held 60 fps). These figures predate the 2026-11-02 upstream rebase and have not been remeasured. On macOS 26, [frame generation](playing.md#frame-generation) can add generated frames on top. It is opt-in and off by default. How the M1 frame got there is on the [macOS renderer performance](macos-renderer.md) page.

More detail is in [docs/MACOS.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS.md).

## Setup failures

Attach `.local/logs/setup-error.json` and the complete log named in the
error. The JSON alone does not contain compiler errors. If **Building the
translator** fails in a precompiled header (`cmake_pch.hxx`), setup also
records `rexglue-pch-diagnostics.log`. Include that file, `rexglue-build.log`
and `rexglue-configure.log` from `.local/logs`, and keep the failed build
directory. The [macOS troubleshooting guide](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS.md#troubleshooting)
explains the missing `std::bit_cast` / `std::byteswap` report that still
needs the affected Mac's compiler and header evidence.

## Intel Macs (experimental)

From 0.8.1, releases also include `PinyonShift-Launcher-macos-x86_64.zip` for Intel Macs on macOS 13.3 or newer. Install and play the same way. The build has only run under Rosetta on an Apple silicon Mac, where it reached free roam and drew it correctly; it has not run on an Intel or AMD Mac GPU yet. Expect rendering bugs and lower frame rates, and please report what you see. A Radeon Pro 5500M or newer is the realistic target; Intel UHD 630 and Iris graphics are in the class of the UHD 620, which drew about 20 fps at ULTRA LOW 30 on Windows. Details in [docs/MACOS.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS.md#intel-macs-experimental).
