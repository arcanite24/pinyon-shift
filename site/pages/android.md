---
title: Android
section: Playing
order: 2
description: Build Pinyon Shift for an Android handheld from the launcher and install it over Wi-Fi.
---

# Android

A developer alpha. The Android build is the same recompiled game, cross-compiled for arm64 on your PC from your own disc and installed on your own device. It's never published or shared.

## Requirements

- A Windows PC where the game is already built and plays.
- About 15 GB free on the PC's install drive. The launcher downloads the pinned Android SDK, NDK and JDK 17 when the PC has none, after you accept the Android SDK license.
- An arm64 device with Android 13 or later and a Vulkan 1.3 driver, about 8 GB free, on the same network as the PC.
- Tuned for Snapdragon 8 Gen 2 or newer (Adreno 740 and up).

## Install over Wi-Fi

1. In the launcher, choose **Android**, then **Build APK**. The first build takes 20 to 60 minutes.
2. Choose **Share on Wi-Fi**. Scan the QR code with the device's camera, download the app and open it. Android asks once to allow the browser to install apps; Windows asks once to allow the launcher on private networks.
3. The app finds the PC on the local network and asks for the six-digit code the launcher shows. It then lists what the PC offers: the game files (7.2 GB, required), title update v4, imported DLC and your PC save. Then **Play**.

No USB debugging is needed. Your PC save is never copied unless you select it, and the device's own save is backed up first. An interrupted copy resumes where it stopped. To copy more later, long-press the app icon and choose **Get files from PC**.

The launcher serves only while sharing is on, only to private network addresses, and only the files it listed. The pairing code changes each time sharing starts, and ten wrong codes stop the share. Nothing goes from the device to the PC.

## Install over USB

With USB debugging on, **Install over USB** in the launcher does the same with adb. From a repository checkout:

```bash
python tools/pinyon.py android build
python tools/pinyon.py android install
python tools/pinyon.py android push-data
```

`push-data` copies the extracted game into `Android/data/studio.deimos.pinyonshift/files/game/base` and resumes if interrupted. Saves, settings, logs and mods live beside it in `files/state`, laid out as on the PC.

## Presets and drivers

**SETTINGS > GRAPHICS > GRAPHICS PRESET** has two choices:

| Preset | MSAA | Sun shadows | Rate |
| --- | --- | --- | ---: |
| SMOOTH 60 | Off | Off | 60 |
| QUALITY 30 | 4x | On | 30 |

Both draw the game's three predicated tiles in one pass and redraw the reflection map at a quarter of the game's rate.

On Adreno 7xx the bundled Mesa Turnip driver (Gen8 V37) is chosen automatically and is much faster than the stock driver. Other GPUs, such as the Adreno 830, use the system driver. **SETTINGS > GRAPHICS > GPU DRIVER** picks the driver for the next start. **IMPORT DRIVER (.ZIP)** adds an adrenotools package.

## Measured devices

| Device | SoC and GPU | Driver | SMOOTH 60 |
| --- | --- | --- | --- |
| AYN Odin 2 Portal | Snapdragon 8 Gen 2, Adreno 740 | Turnip Gen8 V37 | About 60 fps |
| AYN Thor (Max) | Snapdragon 8 Gen 2, Adreno 740 | Turnip Gen8 V37 | About 60 fps |
| RedMagic Astra (nubia NP05J) | Snapdragon 8 Elite, Adreno 830 | Qualcomm | 60 fps while cool, falling toward 30 as it heats up |

## Controls

A built-in, Bluetooth or USB controller works as on the PC. On a touch screen, on-screen controls appear at the first touch and hide 20 seconds after the last one. Android's Back opens **SETTINGS**; inside the menus it steps back. Clicking both sticks shows the performance panel.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| The app doesn't find the PC | Different networks, a network that blocks broadcasts, or Windows Firewall. Enter the address the launcher shows and allow the launcher on private networks |
| The app closes at once | The game files are missing. Open it from the app icon, or run `push-data` again |
| RESOLUTION SCALE offers only 1X | Higher scales need more shared memory than a phone has |
| No sound | No output device could be opened. The game runs silently instead of stopping |

The full Android reference, including DLC and title update v4 on Android, is in [docs/ANDROID.md](https://github.com/arcanite24/pinyon-shift/blob/main/docs/ANDROID.md).
