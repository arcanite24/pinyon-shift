---
title: macOS
section: Start
order: 4
description: Build and play Pinyon Shift natively on an Apple silicon Mac.
---

# macOS

A native build for Apple silicon. The game's Vulkan renderer runs on Metal through MoltenVK, which the build includes.

## Requirements

- An Apple silicon Mac (M1 or newer) with macOS 13 or newer.
- Your ISO of the USA retail disc (`MS-2505`) and about 20 GB free.
- Apple's Command Line Tools. The launcher offers to install them.

## Install and play

1. Download `PinyonShift-Launcher-macos-arm64.zip` from the [latest release](https://github.com/arcanite24/pinyon-shift/releases/latest) and open it.
2. The app is not notarized, so approve its first start under **System Settings → Privacy & Security → Open Anyway**.
3. Install the Command Line Tools if the launcher asks for them.
4. Choose your disc image, confirm ownership and choose **Verify and build**.
5. Choose **Play**. Press **F6** in game for settings.

On an M4 Pro, free roam runs at a median of about 105 fps at the default 1x resolution.

More detail is in [docs/MACOS.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS.md).
