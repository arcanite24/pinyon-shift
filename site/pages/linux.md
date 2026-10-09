---
title: Linux and Steam Deck
section: Start
order: 3
description: Build and play Pinyon Shift natively on Linux and the Steam Deck, then add it to Steam.
---

# Linux and Steam Deck

A native Linux build, not Proton. Setup works as on Windows: you choose your own disc image, and the launcher verifies it, builds the game on your machine and starts it.

## Steam Deck

You need your ISO of the USA retail disc (`MS-2505`), about 45 GB free and a charger. The first build takes about 35 minutes.

1. Hold the power button and choose **Switch to Desktop**.
2. Copy your ISO onto the Deck, from a USB drive, a microSD card or the network.
3. Download `PinyonShift-Launcher-linux-x86_64.tar.gz` from the [latest release](https://github.com/arcanite24/pinyon-shift/releases/latest).
4. In Dolphin, right-click it, choose **Extract → Extract archive here**, open `PinyonShift` and double-click `PinyonShiftLauncher`.
5. Choose your disc image, confirm ownership and choose **Verify and build**.
6. Choose **Add to Steam**. Steam restarts with the entry and its artwork.
7. Return to Gaming Mode. Pinyon Shift is in your library under **Non-Steam**.

Everything installs under `~/.local/share/PinyonShift`. SteamOS needs no unlocking, password or developer mode.

The race and free roam hold 60 fps at 1x within the Deck's default 15 W limit. Leave **Manual GPU Clock** off in the Performance settings: with it on, Steam can pin the GPU at 200 MHz and the game drops to about 10 fps.

## Linux PCs

- x86-64 with SSE4.1, and a Vulkan 1.3 driver (RADV from Mesa 23 or newer, or NVIDIA's).
- glibc 2.31 or newer, `python3` 3.9 or newer, `git` and GLib.
- About 45 GB free for the first build.

Extract the same archive, run `PinyonShiftLauncher` and follow the steps from step 5. The launcher also adds the game to your applications menu.

From a terminal, in the extracted source:

```bash
python3 tools/pinyon.py setup --iso ~/Downloads/forza-horizon.iso
python3 tools/pinyon.py launch
python3 tools/pinyon.py shortcuts add
```

More detail, including uninstalling and troubleshooting, is in [docs/LINUX.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/LINUX.md).
