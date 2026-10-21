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
- About 15 GB free on the PC's install drive. The launcher downloads the pinned Android SDK, NDK and JDK 17 when the PC has none, after you accept the Android SDK license. With Android Studio's SDK already installed, it adds the missing packages to that SDK with its own pinned command-line tools.
- An arm64 device with an ARMv8.2 CPU (Cortex-A55, Cortex-A75 or newer; every Snapdragon 845 and later), Android 13 or later and a Vulkan 1.3 driver, about 8 GB free, on the same network as the PC.
- Tuned for Snapdragon 8 Gen 2 or newer (Adreno 740 and up).

## Install over Wi-Fi

1. In the launcher, choose **Android**, then **Build APK**. The first build takes 20 to 60 minutes.
2. Choose **Share on Wi-Fi**. Scan the QR code with the device's camera, download the app and open it. Android asks once to allow the browser to install apps; Windows asks once to allow the launcher on private networks.
3. The app finds the PC on the local network and asks for the six-digit code the launcher shows. It then lists what the PC offers: the game files (7.2 GB, required), title update v4, imported DLC, the PC's enabled mods, custom radio stations and the XE mod, and your PC save. Then **Play**.

No USB debugging is needed. Your PC save is never copied unless you select it, and the device's own save is backed up first. An interrupted copy resumes where it stopped. To copy more later, long-press the app icon and choose **Get files from PC**. When the PC offers a newer build of the app, the setup screen says so and offers **Install update**; a base build is never offered to a device that has title update v4.

Mods, radio and XE copy together, because the patches the PC builds for them match exactly its set of enabled mods. Files the PC no longer has are moved to `backups` on the device. Native mods (a PC library) aren't shared, and XE isn't shared to a v4 app.

The launcher serves only while sharing is on, only to private network addresses, and only the files it listed. The pairing code changes each time sharing starts, and ten wrong codes stop the share. Nothing goes from the device to the PC.

## Install over USB

With USB debugging on, **Install over USB** in the launcher does the same with adb. From a repository checkout:

```bash
python tools/pinyon.py android build
python tools/pinyon.py android install
python tools/pinyon.py android push-data
```

`push-data` copies the extracted game into `Android/data/studio.deimos.pinyonshift/files/game/base` and resumes if interrupted. Saves, settings, logs and mods live beside it in `files/state`, laid out as on the PC.

After the game has run once on a device, `python tools/pinyon.py android shader-pack` makes a shader pack for it: it starts the game to the title screen over adb, collects the SPIR-V of every shader the device's pipeline storage names, builds a pack and puts it in the state's shader cache. Later starts load the pack instead of translating those shaders: on the Odin 2 (Adreno 740), 711 shaders, shader translation at start 0.52 to 0.07 s and start to title 2.99 to 2.66 s. The pack belongs to the device and build it was made on; run the command again after updating. Stop the game first; the command refuses while it runs.

## Presets and drivers

**SETTINGS > GRAPHICS > GRAPHICS PRESET** has three choices:

| Preset | MSAA | Sun shadows | Rate |
| --- | --- | --- | ---: |
| ULTRA LOW 30 | Off | Off | 30 |
| SMOOTH 60 | 2x | Off | 60 |
| QUALITY 30 | 4x | On | 30 |

ULTRA LOW 30 is for entry-level phones and also keeps textures at most 256 texels across (**TEXTURE SIZE**), which saves memory a phone shares with the CPU. All three draw the game's three predicated tiles in one pass and redraw the reflection map at a quarter of the game's rate.

On Adreno 7xx and 8xx the bundled Mesa Turnip driver (Gen8 V37) is chosen automatically. It is much faster than the stock driver on the Adreno 740 and takes about a fifth less GPU time on the Adreno 830. Other GPUs use the system driver. **SETTINGS > GRAPHICS > GPU DRIVER** picks the driver for the next start. **IMPORT DRIVER (.ZIP)** adds an adrenotools package, including Qualcomm driver packages; the log's `Vulkan device` line shows which driver version runs.

Where a phone's fastest cores form their own cluster of two or more (the Snapdragon 8 Elite's two 4.32 GHz cores), the GPU command decoder thread is pinned to them. Left to the scheduler it spent whole stretches on the slower cores: in an in-run A/B on the Astra at the 60 fps limit, 25 % of frames took over 17.5 ms and the decoder 16.2 ms of CPU a frame, against 2 % and 10.2 ms pinned, with the same GPU time. Phones with a single fastest core, such as the 8 Gen 2 and 8 Gen 3, are left alone. The `android_thread_cores` setting overrides it (`NAME=CORES` entries separated by semicolons, `off` to disable).

## HDR calibration

Keep brightness and the display mode fixed, and turn adaptive brightness off
while calibrating. **SETTINGS > DISPLAY > HDR CALIBRATION** shows the selected
signal levels; Android and the display may tone-map them before they reach
the panel. If the peak square never disappears, keep the existing peak
pending a measured calibration. Patterns replace the guest image and HUD;
HDR COMPARE is suspended while they are shown and resumes when you leave calibration.

HDR10 and calibration chart visibility were checked on the Odin 2 Portal with SYSTEM and Turnip at fixed brightness and refresh. The captured paper-white chart is identical with compare on or off; this does not measure panel luminance. The RedMagic Astra's
calibration remains unqualified ([#566](https://github.com/arcanite24/pinyon-shift/issues/566));
there is no measured Astra preset. The reported luminance is not a panel
measurement. The [Android reference](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/ANDROID.md#hdr-calibration)
describes the driver comparison, display diagnostics and measurements needed
to qualify it.

## Measured devices

| Device | SoC and GPU | Driver | SMOOTH 60 |
| --- | --- | --- | --- |
| AYN Odin 2 Portal | Snapdragon 8 Gen 2, Adreno 740 | Turnip Gen8 V37 | About 60 fps |
| AYN Thor (Max) | Snapdragon 8 Gen 2, Adreno 740 | Turnip Gen8 V37 | About 60 fps |
| RedMagic Astra (nubia NP05J) | Snapdragon 8 Elite, Adreno 830 | Qualcomm | 60 fps while cool, falling toward 30 as it heats up |

The Thor and the Astra were measured before SMOOTH 60 moved from no MSAA to 2x.

## Controls

A built-in, Bluetooth or USB controller works as on the PC. On a touch screen, on-screen controls appear at the first touch and hide 20 seconds after the last one. Android's Back opens **SETTINGS**; inside the menus it steps back. Clicking both sticks shows the performance panel.

## Troubleshooting

On older Linux kernels, including the Pixel 3 XL's reported 4.9.337 kernel,
the runtime now checks that a fixed allocation actually maps the requested
address. This prevents a relocated mapping from leaving a reused guest stack's
guard inaccessible. A native ARM64 probe on the Odin 2 Portal's 4 KB pages
reproduced the failure with old-kernel mapping behavior simulated and passed
with the fix. A current Pixel 3 XL launch is still needed to qualify that
device. The stack fault in issue #556
does not by itself show GPU memory exhaustion. The investigation is recorded
in [facade lifetime faults](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/FACADE_LIFETIME_FAULTS.md).

| Symptom | Cause |
| --- | --- |
| Build APK reports `symbol-order-base.txt`, `symbol-order-v4.txt` or `camera_tuning_tests.cpp` missing | An older source ZIP omitted required build inputs. Update the launcher and its installed sources, then retry Build APK |
| The app doesn't find the PC | Different networks, a network that blocks broadcasts, or Windows Firewall. Enter the address the launcher shows and allow the launcher on private networks |
| The app closes at once | The game files are missing. Open it from the app icon, or run `push-data` again |
| RESOLUTION SCALE offers only 1X | Higher scales need more shared memory than a phone has |
| No sound | No output device could be opened. The game runs silently instead of stopping |

The full Android reference, including DLC and title update v4 on Android, is in [docs/ANDROID.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/ANDROID.md).
