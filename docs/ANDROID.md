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
7xx and 8xx, the system's elsewhere), SYSTEM the device's own, and every
folder under `files/state/drivers` by name. IMPORT DRIVER (.ZIP) opens the
system's file picker for an adrenotools package (a `.zip` with `meta.json`
and the driver `.so`), which is unpacked into a folder named after the zip.
The page's note names the driver in use.

On the Adreno 830 (Snapdragon 8 Elite, Android 15) Turnip Gen8 V37 takes
20.2 ms of GPU per frame in the race at 1x with MSAA off, against 24.8 ms
for the system driver (Qualcomm v800.40) and the same for Qualcomm's
v800.51 and v842.8 packages; the route matrix renders the same on Turnip
and the system driver. Qualcomm packages (the "Adreno driver" zips shared
for emulators) name their libraries like the system driver's
(`vulkan.adreno.so`, `libgsl.so` and others). The system driver is already
loaded when the game opens Vulkan, so the loader once returned it for every
such package; the game now gives the copied package's libraries unique
names first, and the log's `Vulkan device` line shows the driver version
that runs. Packages built for Android 16, such as v891.7, need a binder
function Android 15 lacks: with that stubbed out v891.7 loads, then crashes
within a minute. Packaging
reads the driver binary from `.local/android/drivers/turnip-gen8-v37`
(`meta.json` and `libvulkan_freedreno.so`) and skips it with a warning when
absent.

Android builds trade some image quality for frame rate by default. Each is
a row on the in-game SETTINGS > GRAPHICS page that applies while the game
runs (SHADOWS, REFLECTION UPDATES, SINGLE-PASS SCENE; the last rebuilds the
renderer between frames, about 80 ms), and the GRAPHICS PRESET row sets
them together: QUALITY 30 (4x MSAA, shadows, 30 fps) or SMOOTH 60 (2x MSAA,
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

`android_thread_cores` (default `auto`, changes apply while the game
runs) pins threads to cores by thread-name prefix. `auto` puts the GPU
command decoder on the fastest cores when two or more of them form
their own cluster and do not cover every core (Snapdragon 8 Elite:
cores 6-7); other devices are left to the scheduler. On the Astra, in an
in-run A/B at the 60 fps limit, frames over 17.5 ms went from about
25 % to 2 %, p95 from 18.7 to 17.2 ms and decoder CPU from 16.2 to
10.2 ms a frame, with GPU time unchanged. The 22-minute soak with it
has not been run. Explicit values look like
`GPU_Commands=6-7;*=0-5` (`_` matches a space, `*` every other
thread); `off` restores the threads' earlier masks.

## What stays private

The package holds the game translated from your own disc, exactly as
`pinyon_shift.exe` does on Windows, so it is built on your PC and installed
on your own device, and it is never published or shared. The game files go
from your PC to your device over your local network or USB. Nothing is
uploaded. The repository refuses Android packages, libraries and signing keys
(see [legal](LEGAL.md)).

## Requirements

- A Windows PC where the game is already built (the launcher, or
  `tools/build-preview.ps1`): the Android build reuses the code translated
  there.
- Nothing else on the PC: the launcher downloads the pinned Android SDK
  command-line tools and JDK 17 when the PC has none, then the NDK, build
  tools and platform from `config/android-toolchain.json` once you accept the
  Android SDK license, and builds with the pinned CMake and Ninja. About 15 GB
  free on the install drive. From a terminal, `pinyon.py android doctor
  --install` does the same (`--accept-licenses` answers yes).
- The device: arm64, Android 13 (API 33) or later, a Vulkan 1.3 driver,
  about 8 GB free, on the same network as the PC. USB debugging is needed only
  for the adb commands.

## From the PC to the device

The launcher's source ZIP includes `config/performance/symbol-order-base.txt`
and `config/performance/symbol-order-v4.txt`, which the base and v4 Android
linkers require; the v4 file comes from a v4 probe build (#745). It contains only symbol names ordered
by our local profiling tool, with no translated instructions or game assets.
Clustering frequently called functions reduced `libmain.so` PSS from 52 MB to
34-36 MB on the Odin 2 Portal's boot-to-race route (two runs per build;
[NN-1.9](NEAR_NATIVE_RESEARCH.md)). If Ninja reports this file missing, update
the launcher and its installed sources, then retry **Build APK**.
The same applies if CMake reports `tests/camera_tuning_tests.cpp` missing:
the source ZIP includes the host test sources checked during configuration.

In the launcher, once the game plays on the PC, choose **Android**:

1. **Build APK** builds `.local/android/pinyon-shift.apk` (20 to 60 minutes
   the first time), from title update v4 when you play v4 on the PC. The
   panel shows where the package is, with **Show in folder** and **Save a
   copy**. A failure is described in `.local/logs/android-error.json`.
2. **Share on Wi-Fi** shows a QR code and a six-digit pairing code. Scan the
   code with the device's camera (or open the address under it in the
   device's browser), download the app and open it; Android asks once to
   allow the browser to install apps. Windows asks once to allow the launcher
   on private networks.
3. The app opens its setup screen while the game files are missing. It finds
   the PC by a broadcast on the local network (or takes the address the panel
   shows), asks for the pairing code and lists what the PC offers: the game
   files (7.2 GB, required), title update v4 (with a v4 package), imported
   DLC, the Rally overlay, the PC's mods, its custom radio stations, the XE
   mod and the PC's save. The save is never selected for you; when chosen,
   the device's own save is first copied to
   `files/state/backups/before-pc-save-<time>`. An interrupted copy resumes
   where it stopped. Then **Play**.

The mod rows carry the mods the PC has enabled, as it plays them. Before
sharing, the launcher rebuilds their generated patches (`zz-db-patches`,
`zz-archive-patches`) from the PC's game files, as every PC launch does;
the device's game files come from the same disc, so the patched archives
match. Because those patches are built for exactly the PC's set, the mods,
custom radio and XE rows are copied together. On the device each mod
folder in `files/state/mods` ends up as on the PC: files the PC no longer
has move to `files/state/backups/before-pc-mods-<time>`, which also keeps
the device's previous `enabled_mods`. `enabled_mods` is cleared while the
copy runs (an interrupted copy plays unmodded) and set to the PC's list
when it completes. Mods that only change how the game looks keep your save;
XE plays its own new save (`user-xe`), as on the PC. Not shared: native
mods (their library is a PC binary) and XE with a v4 package (XE is made
for the base game). If the game has never started on the device, the list
is applied at the second start, after the game has written its settings.

When the PC shares a newer build of the app than the one installed (a
higher version, or a later build of the same version), the setup screen
says so after connecting and offers **Install update**. The app downloads
the package from the share and hands it to Android's installer, which asks
to confirm; Android also asks once to allow Pinyon Shift to install apps.
The app closes while it updates; the save, settings and game files stay.
A base package is not offered to a device that has title update v4
installed, since a v4 save cannot be loaded by the base game again.

The launcher serves only while its Android panel is open and sharing, only to
private network addresses, and only the files it listed. Every request but
the download page and the package needs the pairing code, which changes each
time sharing starts; ten wrong codes stop the share. Nothing goes from the
device to the PC.

To copy more later, such as DLC imported afterwards, changed mods or a
rebuilt app, long-press the app icon and choose **Get files from PC**. Without a network, copy the extracted game
folder (`.local\game\base` in the install folder, the one holding
`default.xex`) to the device over USB and choose it with **Choose folder** on
the setup screen.

With USB debugging on, **Install over USB** in the panel installs the package
and copies the game with adb. From a terminal:

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

`build` cross-compiles the game and packages `.local/android/pinyon-shift.apk`,
signed with a key made on your PC. `push-data` copies the extracted game
(7.2 GB, 2,400 files) into the app's folder on the device,
`Android/data/studio.deimos.pinyonshift/files/game/base`; it resumes where it
stopped if interrupted. Saves, settings, logs and mods live beside it in
`files/state`, with the same layout as on the PC, so a save copies between
the two as a folder.

Builds before October 2026 installed as `com.pinyonshift.fh1`, which Android
treats as another app with its own folder. After installing the current
package, `python tools/pinyon.py android migrate` copies the earlier
install's saves, settings and drivers into the new folder (leaving the
originals) and moves its game files; uninstall the old app once the game
shows your save.

DLC and the v4 title update work as on the PC, with the content copied into
the device's state. Import and enable packages into a state folder on the PC
(`tools/manage-fh1-dlc.py`), then push its `user` folder (and `dlc`) to
`files/state`. On the base build, Rally also needs the overlay
`tools/prepare-fh1-rally.py` writes to `cache/rally_adapter`; the activity
turns Rally on when that overlay is present. The v4 build runs Rally and 1000
Club natively. It is built from the player's verified update after
`tools/build-v4.ps1` has generated its code:

```bash
python tools/verify-fh1-title-update.py --install STATE tu00000001_00000000
python tools/pinyon.py android build --title-update-v4
python tools/pinyon.py android push-title-update --state-root STATE
```

A save written by v4 cannot be loaded by the base build afterwards, so keep a
copy before its first v4 start. Offline 1000 Club needs
`pinyon_shift_car_challenge_gate_probe` and `xam_report_live_signin` on. When
the setup screen copies title update v4 from a PC with 1000 Club offline on,
it writes both to `files/state/config/android-arguments.txt`, whose lines the
game adds to its arguments at every start.

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

## HDR calibration

**SETTINGS > DISPLAY > HDR CALIBRATION** sends known signal levels through
the HDR10 presentation path. Paper white is the signal level of white menus
and the HUD; peak is the target used by the highlight expansion. HIGHLIGHTS
controls the strength of that expansion, independently of the calibration.
The patterns replace the guest image and its HUD mask, so the minimap or a
menu frame cannot cover the chart. They temporarily suspend HDR COMPARE
without changing its current choice; leaving calibration restores the comparison.

The pattern uses the selected peak, without substituting Android's advertised
maximum; the advertised levels are used for HDR10 metadata. The peak pattern
compares a square at the selected peak with a 10,000-nit
reference field. It finds a clipping threshold only when the display path
clips those signals. A compositor which tone-maps them can keep the square
visible throughout the range. In that case, do not keep raising the peak
until it looks right: keep the existing value pending a measured calibration.
Reported HDR capabilities are desired content levels, not a measurement of
what the panel emits at the current brightness or display mode. Neither
HDR10 metadata nor a PQ swapchain guarantees an unmodified signal at the
panel ([Android HDR](https://source.android.com/docs/core/display/hdr),
[Vulkan HDR metadata](https://docs.vulkan.org/refpages/latest/refpages/source/VkHdrMetadataEXT.html)).

For a device qualification or an incorrect calibration report:

1. Use a private copy of a pinned render seed. Keep the installed save and
   normal configuration intact, and retain the installed APK before replacing
   it so it can be restored. Keep the device cool and the room lighting fixed.
2. Record the device/ROM, display color mode, refresh rate, brightness and
   adaptive-brightness setting. Disable adaptive brightness, night light and
   optional display enhancements for the comparison; restore them afterwards.
3. Repeat with SYSTEM and the bundled Turnip driver after restarting each
   time. Use identical paper white, peak, gamma and highlight settings.
   Record all three calibration steps with HDR COMPARE both on and off.
   [fh1-android-hdr-calibration.fh1test](../config/render-tests/fh1-android-hdr-calibration.fh1test)
   cycles the steps at fixed 200-nit white and 1000-nit peak signal levels;
   it does not derive or approve those settings for the device.
4. Retain `runtime.log`: `Android display environment` records the launch
   brightness/mode snapshot (`brightness_mode=0` is manual, `1` automatic),
   `Android display HDR` the advertised luminance, `Vulkan device` the actual
   driver, and `Created ... swapchain` its format, color space and transform.
   `HDR10 metadata` records the submitted levels, and `HDR calibration pattern`
   records the tested signal values when the step, white, peak or gamma changes.
   The launch snapshot does not track later system setting changes.
5. While the pattern is visible, save `adb shell dumpsys display` and
   `adb shell dumpsys SurfaceFlinger`. Inspect the game's layer data space,
   composition path and display HDR mode for both drivers. A screenshot is
   tone-mapped and cannot establish panel luminance. Measure black, paper
   white and clipping with a luminance meter at the same patch size and
   brightness/mode; retain those conditions with the readings.

Issue [#566](https://github.com/arcanite24/pinyon-shift/issues/566) remains an
Astra qualification gate. The AYN Odin 2 Portal reports 420 / 210.1615 /
0.323 cd/m² (maximum / average / minimum) in `dumpsys display`; these are
advertised values, not new measured limits. There is no established Astra
peak or correction curve, so the shared 200-nit paper-white and 1000-nit
peak defaults have not been replaced with a guessed device preset.

Visibility baseline (2026-10-18): the Odin's installed v4 APK 0.5.1 completed
this route through frame 1680 on both SYSTEM (0x802A4035) and Turnip
(0x6802063). Each run used a private copy of `odin-graphics-20261006` plus
verified pinned title-update-v4 files; a base-only state cannot boot that
installed v4 APK. The raw brightness setting stayed at 141 in manual mode,
and both refresh-rate settings at 120.00001 Hz. Both drivers used format 64,
a 10-bit buffer marked PQ, pre-transform 2 and the same 420 / 210.1615 /
0.323 metadata. Host-UI screenshots reproduce the guest menu image covering
the paper-white chart; Turnip also reproduces it with compare off. This
establishes the old renderer's chart contamination, not emitted luminance. The normal user trees retained all
36 file hashes; the APK and settings were unchanged and private states removed.

The updated base 0.6.0 build passed the same private route on both drivers.
Host-UI screenshots taken when the pattern-change logs appeared show the
square and gray steps instead of the guest menu. The paper-white chart band
has identical decoded RGB pixels with compare on and off, both within each
driver and between SYSTEM and Turnip; leaving calibration restores the
comparison divider. Startup logs include the raw display settings, and the
six step transitions log their 200-nit white / 1000-nit peak signal values.
This verifies chart visibility and signal routing, not physical luminance.
The test-only repack used the installed version code 501, with native
libraries and Java bytecode identical to the normal build. The original
0.5.1 APK was restored by exact SHA-256; all 36 user-file hashes and the
recorded brightness/refresh settings were unchanged. The APK, private states
and captures stay local; the Astra measurement gate remains open.



## Troubleshooting

| Symptom | Cause |
| --- | --- |
| The setup screen does not find the PC | The device and the PC are on different networks, the network blocks broadcasts, or Windows Firewall blocked the launcher: enter the address the launcher shows, and allow the launcher on private networks. |
| The app closes at once | Started from adb without the game files: open it from the app icon, or run `push-data`. If logcat says `Cannot create the state folder`, files were copied into the app's folder by hand: run `push-data` again, which lets the app use them. |
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
