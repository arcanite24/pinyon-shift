# Pinyon Shift on Android

**Status: alpha, for developers.** The game builds for Android, installs and
plays through the Vulkan renderer. On the reference tablet (nubia NP05J,
Snapdragon 8 Elite) the race runs at 60 fps at 1x until the device heats up,
and settles near 30 once its skin passes about 44 C
([60 fps backlog](ANDROID_60FPS_BACKLOG.md)). The target is a high-end Android handheld or phone with
a Snapdragon 8 Gen 2 or newer (Adreno 740+), 12 GB of memory and Android 13
or later. The plan and its progress are in the
[Android port backlog](ANDROID_PORT_BACKLOG.md); the AYN Odin 2 Portal
(Adreno 740) has its own [Odin backlog](ANDROID_ODIN_BACKLOG.md). On Adreno
7xx, Mesa Turnip runs the game much faster than the stock driver, and
newer Mesa builds faster still: on the Odin 2 Portal the busy drive takes
32 ms at 4x MSAA and 28 ms at 1x with Turnip Gen8 V37 (Mesa, Vulkan
1.4.359), against 39 and 34 ms with an older Turnip and 49 and 41 ms with
the stock driver.

The package bundles Turnip Gen8 V37 (MIT, built by StevenMXZ from Mesa; its
notice is in `android/drivers/turnip-gen8-v37/NOTICE.txt`) and installs it
into `files/state/drivers` at start. SETTINGS > GRAPHICS > GPU DRIVER picks
the Vulkan driver loaded at the next start (`android_gpu_driver`): AUTO, the
default, loads the one recommended for the GPU (Turnip Gen8 V37 on Adreno
7xx, the system's elsewhere, such as the Adreno 830), SYSTEM the device's
own, and every folder under `files/state/drivers` by name. IMPORT DRIVER
(.ZIP) opens the system's file picker for an adrenotools package (a `.zip`
with `meta.json` and the driver `.so`), which is unpacked into a folder
named after the zip. The page's note names the driver in use. Packaging
reads the driver binary from `.local/android/drivers/turnip-gen8-v37`
(`meta.json` and `libvulkan_freedreno.so`) and skips it with a warning when
absent.

Android builds trade some image quality for frame rate by default. Each is
a row on the in-game SETTINGS > GRAPHICS page that applies while the game
runs (SHADOWS, REFLECTION UPDATES, SINGLE-PASS SCENE; the last rebuilds the
renderer between frames, about 80 ms), and the GRAPHICS PRESET row sets
them together: QUALITY 30 (4x MSAA, shadows, 30 fps) or SMOOTH 60 (no MSAA,
no shadows, 60 fps), both single-pass with quarter-rate reflections. As
settings in `config/pinyon_shift.toml`: FH1's three predicated tiles are
drawn once (`fh1_untile_predicated_tiling`, same image), the reflection
cubemap is redrawn at a quarter of the game's rate
(`pinyon_shift_fh1_env_map_rate = 0.25`; 1 restores it) and the sun's
shadows are off (`pinyon_shift_fh1_shadows = false`; true restores them,
about 6 ms a frame on the Odin). With these, MSAA off and the frame limits
at 60 (`host_present_fps_limit` and `pinyon_shift_fh1_render_fps_limit`),
the Odin 2 Portal holds 60 fps in free roam and races on Turnip Gen8 V37
(15.5 ms of GPU a frame); with 4x MSAA it runs near 52 fps.

## What stays private

The package holds the game translated from your own disc, exactly as
`pinyon_shift.exe` does on Windows, so it is built on your PC and installed
on your own device, and it is never published or shared. The game files go
from your PC to your device over USB. Nothing is uploaded. The repository
refuses Android packages, libraries and signing keys (see
[legal](LEGAL.md)).

## Requirements

- A Windows PC where the game is already built (the launcher, or
  `tools/build-preview.ps1`): the Android build reuses the code translated
  there.
- The Android SDK command-line tools (Android Studio installs them) and JDK
  17. `pinyon.py android doctor --install` adds the pinned NDK, build tools
  and platform from `config/android-toolchain.json`, and shows the Android
  SDK license for you to accept (`--accept-licenses` answers yes).
- The device: arm64, Android 13 (API 33) or later, a Vulkan 1.3 driver,
  about 8 GB free, USB debugging turned on.

## From the PC to the device

In the launcher, once the game is built, **Build Android APK** does the
first two steps below. It asks you to accept the Android SDK license, and on
a PC with no Android SDK or JDK it fetches the pinned command-line tools and
Eclipse Temurin JDK 17 into the install folder (`.local/toolchain`), checked
against their SHA-256. A failure is described in
`.local/logs/android-error.json`. Then install the package and copy the
game with the last two commands.

From a terminal:

```bash
python tools/pinyon.py android doctor --install
```

```bash
python tools/pinyon.py android build
```

```bash
python tools/pinyon.py android install
```

```bash
python tools/pinyon.py android push-data
```

`build` cross-compiles the game (20 to 60 minutes the first time) and
packages `.local/android/pinyon-shift.apk`, signed with a key made on your
PC. `push-data` copies the extracted game (7.2 GB, 2,400 files) into the
app's folder on the device, `Android/data/studio.deimos.pinyonshift/files/game/base`;
it resumes where it stopped if interrupted. Saves, settings, logs and mods
live beside it in `files/state`, with the same layout as on the PC, so a save
copies between the two as a folder.

Builds before October 2026 installed as `com.pinyonshift.fh1`, which Android
treats as another app with its own folder. After installing the current
package, `python tools/pinyon.py android migrate` copies the earlier
install's saves, settings and drivers into the new folder (leaving the
originals) and moves its game files; uninstall the old app once the game
shows your save.

Start the game from the launcher icon, or:

```bash
python tools/pinyon.py android run
```

`run --null-gpu` starts it without a renderer, and `run --route FILE` runs a
render-test route (`config/render-tests/`). `pull-logs` copies the logs,
crash reports and route output to `.local/android/device-logs/`.

## Controls

A controller (built in, Bluetooth or USB) works as on the PC. On a touch
screen, on-screen controls appear at the first touch: a steering stick
wherever the left thumb lands, throttle (RT) and brake (LT) under the right
thumb, A, B, X, Y, the bumpers, Back and Start. They hide 20 seconds after the
last touch, so a controller player never sees them
(`pinyon_shift_touch_controls` turns them off).

Android's Back button or gesture opens SETTINGS, and inside the menus it steps
back; tap a row to open or change it. SETTINGS also holds the trainer (with
cheats on), SAVE PHOTO and the achievements, which have keyboard keys on the PC.
Clicking both sticks (LS + RS) shows or hides the performance panel, F3 on a
keyboard; SETTINGS > CONTROLLER > PERFORMANCE PANEL changes the buttons
(`pad_chord_debug_overlay`).

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| The app closes at once | The game files are not on the device: run `push-data`. If logcat says `Cannot create the state folder`, files were copied into the app's folder by hand: run `push-data` again, which lets the app use them. |
| `VULKAN_CAPABILITY_REPORT` in the log | The device's features, formats and memory, logged at every start; attach it to reports. |
| RESOLUTION SCALE offers only 1X | Higher scales need resolve buffers larger than a phone's shared memory holds; `android_allow_resolution_scale` lifts the limit for testing. |
| `skipped a resolve` in the log | A guest copy the renderer cannot pack yet (one is known, in the title screen's attract sequence); the frame continues without it. |
| No sound | No output device could be opened; the game runs silently instead of stopping. |


## Settings restart verification (2026-10-06)

The settings menu now derives renderer restart requirements from SDK flag
metadata, while retaining project-specific title/profile requirements. On the
Odin 2 Portal, changing MSAA from 4X to OFF shows a restart badge and pending
restart note. A fresh process retains OFF and clears that pending note. This
qualifies settings persistence and restart presentation; it is not a new GPU
performance or image-quality measurement.

The [Android MSAA scenario](../config/render-tests/fh1-android-msaa-restart.fh1test)
uses a private state with MSAA initially 4X. Its Windows-line-ending variant
also runs on Android, covering CRLF handling in both the schema and clock
metadata. Run the scenario using a private state-root intent override and
inspect the host menu with an ADB screenshot; ordinary render-test captures
contain the guest output and omit the host UI. Existing device progress is
outside the qualification state and must not be replaced for this check.

The subsequent build includes the shared diagnostic Rally AI control-release
fix. Its signed/aligned APK was installed on the Odin without clearing app
data, and private session `20261006T065043Z-p2335` completed the CRLF reload
route at frame 1200 and shut down normally. This is a startup check; Rally
driving and GPU performance on Android remain unqualified. Current artifact
verification is recorded in ignored `.local/android/latest-apk-verification.json`.

Bloom now defaults to OFF with a live toggle in Graphics settings. It zeros
the title's frame-local bloom scale while preserving exposure, tone mapping
and weather data. A signed/aligned ARM64 build was installed on the Odin 2
Portal and passed a private-state on/off/restore gameplay run through frame
5400 (`20261006T103905Z-p8506`), with three native free-roam captures and normal
shutdown. All 17 files in the normal device user tree remain byte-identical.
The PC pinned seed profile is unchanged. Receipt:
`D:/horizon1-recomp-tests/android-bloom-20261006/qualification.json`.
This checks the switch and gameplay stability. Captures have different vehicle
poses; they are not a pixel-matched A/B. Stepped paint shading and very bright
vegetation are still visible on Android. Cutscenes, showroom/photo mode and
those graphics defects remain unqualified. Bloom filter passes still execute;
no performance improvement is claimed.

MSAA now defaults to OFF for unset configurations, including desktop. The
subsequent signed/aligned Odin build showed OFF with no saved MSAA flag and
retained an explicit saved 4X choice in separate private states. All 16 normal
device profile files retained their pre-install hashes. These are configuration
and startup checks; sustained driving performance remains unqualified.

Fatal scripted-test rejection now exits immediately after flushing its failure
receipt. Reusing an existing output directory previously triggered SDL thread
crashes during static destruction on the Odin. A private rejection check and
desktop subprocess check preserve that directory and emit the expected failure;
the updated Odin run produces no corresponding native crash record.
