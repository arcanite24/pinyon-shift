---
title: macOS
section: Start
order: 4
description: Build and play Pinyon Shift natively on an Apple silicon Mac.
---

# macOS

A native build for Apple silicon. The game's Vulkan renderer runs on Metal through MoltenVK, which the build includes.

## Requirements

- An Apple silicon Mac (M1 or newer) with macOS 13.3 Ventura or newer.
- Your ISO of the USA retail disc (`MS-2505`) and about 20 GB free.
- Apple's Command Line Tools. The launcher offers to install them.

## Install and play

1. Download `PinyonShift-Launcher-macos-arm64.zip` from the [latest release](https://github.com/arcanite24/pinyon-shift/releases/latest) and open it.
2. The app is not notarized, so approve its first start under **System Settings → Privacy & Security → Open Anyway**.
3. Install the Command Line Tools if the launcher asks for them.
4. Choose your disc image, confirm ownership and choose **Verify and build**.
5. Choose **Play**. Press **F6** in game for settings.

On the M4 Pro Mac mini, the 2026-10-18 free-roam qualification averaged
about 60 fps at 1x with a 60 fps limit, but about 40 fps with QUALITY 60
(2x, 4x MSAA). Start with LOW-SPEC 60, then raise scale or MSAA separately;
the [platform measurements](platforms.md#macos-on-apple-silicon) explain
the tested workload and its limits. The older 120 Hz result used a different
optimization route.

Fullscreen uses a borderless window on the current desktop. The presenter
keeps the Metal drawable at the swapchain size through fullscreen changes;
scripted transitions passed, while the OS-visible result still needs an
interactive check on the affected Macs.

The launcher's **DLC** panel imports your own DLC packages ([DLC and title update](dlc.md)), and **Import a save** brings a save from another install or from Xenia. On the M4 Pro all 21 packages imported and their 84 car rows loaded and could be driven in a scripted route, and the v4 build ran the 1000 Club challenges and reached the Horizon Rally entry.

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
