---
title: Troubleshooting
section: Playing
order: 4
description: Fixes for rejected disc images, failed builds, startup problems, controllers and crashes.
---

# Troubleshooting

## The ISO is rejected

Only the USA retail base disc (`MS-2505`) is supported. A bad dump, another region, a title update or a modified image won't match. The launcher doesn't accept near matches and can't download or repair an image.

## A download fails

Check the connection and run the launcher again. Network failures are retried, and every pinned download is verified by SHA-256 before use, so partial files are never trusted.

## The build fails

Restart Windows after a Build Tools install, free at least 30 GB, and close any running game before trying again. When a step fails, the launcher shows which one, its exit code and the first real compiler, CMake or file-copy error, with a hint for common causes: a full disk, low memory, antivirus, a file in use. The same report is saved in `.local/logs/setup-error.json`. Attach it to a bug report; the final "build failed" line alone can't identify the cause.

When the Visual Studio Installer stops, the error gives its exit code and, for the common ones, the reason: the installer or Visual Studio is already open, or another installation is running. The installer's own logs are the `dd_*.log` files in `%TEMP%`.

## A portable install can't start or build

- **"Portable folder is not writable"**: move the folder somewhere you own, such as `D:\Games\PinyonShift`, or delete `portable.txt`.
- **"Portable folder path is too long"**: the build creates files about 185 characters below `data`. Keep the `data` folder's path at 70 characters or fewer.

## The game doesn't start

Update the GPU driver and check that the GPU supports Vulkan 1.3. To reset the runtime settings, delete `.local/preview/config/pinyon_shift.toml`. Security software may quarantine the newly compiled, unsigned executable. Restore it only if it was built by your own install.

## A partial settings file or black frames on a fresh state

When `pinyon_shift.toml` exists without its configuration schema line, startup
backs it up as `pinyon_shift.toml.noschema.bak`, fills in the current defaults
(including Vulkan), and reapplies the settings already in the file. This also
covers a new state where the mod builders wrote only `enabled_mods` before the
first game launch. Existing explicit values keep precedence over defaults.

## The game runs on the wrong GPU

On a PC with two GPUs, such as a laptop, the game asks for the high-performance one. To pick another with Vulkan, find the "Available Vulkan physical devices" list near the top of `.local/preview/logs/runtime.log` and add its number to `.local/preview/config/pinyon_shift.toml`, for example `vulkan_device = 1`. Direct3D 12 takes `d3d12_adapter`, numbered in Windows' adapter order. `-1` goes back to the automatic choice. Windows' **Settings → System → Display → Graphics** can also assign `pinyon_shift.exe` (not the launcher) to a GPU.

## Stutter or something missing the first time

Vulkan prepares shaders during setup, and stores any new ones it meets during play, so a new effect can stutter once. If stutter repeats on every pass of the same route, or something stays missing after a relaunch, report it with the latest runtime log and performance CSV from `.local/preview/logs` (the launcher's **Logs** link opens it once the game has run).

## The picture tears

With **F6 > DISPLAY > VSYNC** on, the game presents without tearing on both Vulkan and Direct3D 12, and the change applies at once. With it off, Vulkan presents as soon as a frame is ready and may tear. Overlays that hook the game's presentation, such as RivaTuner or OBS's game capture, can add tearing or hitches of their own: close them to compare.

## A resolution scale error at startup

The renderer supports 1x, 2x, 3x and 4x, the same horizontally and vertically. Pick a supported scale in the launcher, or delete `pinyon_shift.toml` to reset.

## A controller isn't recognized

Connect it before starting the game. Close Steam or other remapping software, reconnect and relaunch. When reporting an unsupported controller, include its exact name, USB vendor and product IDs, and a screenshot from a gamepad tester.

## A menu item doesn't respond to the mouse

The Xbox menus don't use pointer targeting. Use A, <kbd>Space</kbd> or a left click to activate the selected row, and <kbd>Enter</kbd> for Start.

## A save copied from Xenia crashes the game

Xenia saves are signed with the Xenia profile's XUID. Import them with `tools/import-xenia-save.ps1` instead of copying; see [Saves](playing.md#saves).

## The game crashes

Leave the launcher open while playing. After a crash it prepares a sanitized ZIP under `.local/preview/reports`, selects it in Explorer and opens a prefilled GitHub issue. Attach the ZIP and describe what you did last. Reports never include the game, your saves or local paths.

Memory dumps in `.local/preview/crashes` can hold fragments of process memory, so they never go into the public report. Keep them local.

## Start over

Close the launcher and delete `.local` and `out` from the source folder under `%LOCALAPPDATA%\PinyonShift` (or under `data\source` for a portable install). Your ISO is outside these folders and is never deleted.
