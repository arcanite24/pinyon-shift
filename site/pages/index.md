---
title: Overview
section: Start
order: 1
description: Documentation for Pinyon Shift, the Xbox 360 release of Forza Horizon recompiled to run natively on Windows, with an Android alpha.
---

# Pinyon Shift

The Xbox 360 release of *Forza Horizon*, recompiled ahead of time into native code for Windows, with an Android alpha. You build it on your own PC from a disc you own.

{{release}}

The download is the launcher. It doesn't contain the game: the launcher verifies your disc image, then builds the game on your machine. Start with [Install on Windows](install.md).

## Requirements

| | |
| --- | --- |
| Game | USA retail disc of *Forza Horizon*, serial `MS-2505`, title ID `4D5309C9`, as an ISO or an [extracted folder](install.md#use-an-extracted-folder) |
| System | Windows 10 or 11, x64 |
| GPU | Vulkan 1.3. NVIDIA is tested; AMD and Intel are not qualified yet |
| CPU | 4 cores for the Low-spec 60 preset |
| Disk | About 30 GB free. The first build takes 20 to 60 minutes |

Android needs the game built on a PC first; see [Android](android.md).

## Status

A playable preview. Expect some rendering bugs and slowdowns. Vulkan is the only supported graphics API.

| Area | State |
| --- | --- |
| Code | The game's PowerPC code is translated to C++ and compiled. Nothing is interpreted or JIT-compiled while you play |
| Frame rate | 60 or 120 fps at the correct game speed (the console runs at 30) |
| Resolution | 1x to 4x internal resolution, FSR 1 output scaling, ultrawide with a 16:9 HUD |
| In game | Settings on <kbd>F6</kbd>, trainer, photo export, achievements, save backups, 18 languages |
| DLC | Your own Xbox 360 packages, verified and imported. Rally and 1000 Club run on the optional v4 build |
| Mods | Asset, database, texture and native mods; see [Modding](modding.md) |
| Android | Developer alpha. About 60 fps on Snapdragon 8 Gen 2 handhelds |

## What's in the repository

The launcher, build tools, host code and configuration. It does **not** contain the game, its assets, generated translations or a prebuilt executable. See [Legal](legal.md).

## Getting help

- Something went wrong: [Troubleshooting](troubleshooting.md).
- Found a bug: keep the launcher open while playing. If the game crashes, the launcher prepares a sanitized diagnostic ZIP and opens a prefilled [GitHub issue](https://github.com/arcanite24/pinyon-shift/issues). For other bugs, use **Report a problem** in the launcher.
