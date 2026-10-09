---
title: How it works
section: Technical
order: 1
description: How Pinyon Shift recompiles Forza Horizon's PowerPC code and renders the game's GPU commands on Vulkan.
---

# How it works

Pinyon Shift isn't an emulator. The game's PowerPC code is translated ahead of time into C++, compiled for the host CPU, and linked with a runtime that stands in for the Xbox 360's kernel, file system, input, audio and GPU.

## Recompilation

[ShiftGlue](https://github.com/arcanite24/shiftglue-sdk), our fork of ReXGlue, reads `default.xex` from your disc and emits C++ for every function in it. The generated code calls other functions directly, so nothing is interpreted or JIT-compiled at run time. Guest memory stays big-endian, as the game expects.

Setup runs six reproducible stages:

1. Verify the ISO's exact size and SHA-256 against `config/supported-dumps.json`.
2. Install Visual Studio Build Tools if missing, and download pinned portable tools whose hashes are in `config/release-toolchain.json`.
3. Fetch the pinned ShiftGlue revision.
4. Extract the disc and generate the translated source under `.local/`.
5. Compile `pinyon_shift.exe`.
6. Prepare Vulkan shaders in a private startup run, so the first launch doesn't compile them.

The disc image is opened read-only. Everything produced from it stays in ignored local folders and is never committed or uploaded.

## Rendering

The game's GPU commands run through a renderer written for *Forza Horizon*, not a general Xenos emulation layer:

- The PM4 command processor reads the guest's command stream, and the FH1 native executor runs every draw, clear, resolve and swap in the game's order.
- The executor owns the EDRAM surfaces. Resolves write the guest texture layout into a mirror of guest memory, and textures are decoded from that mirror.
- The game's original Xenos shaders are translated to SPIR-V. Shaders seen during setup are stored in a pack, and new ones are translated during play and kept for the next launch.
- Rendering runs at 1x to 4x the console's 1280 × 720, with FSR 1, CAS or bilinear output scaling.

Vulkan 1.3 is the only supported API. The Direct3D 12 backend is legacy code and isn't offered to players.

## Frame rate

The console runs the game at 30 fps. Pinyon Shift runs it at 60 or 120 fps and fixes the systems that assumed 30, such as crowd and purchase animations, so the game keeps its normal speed. The GPU command thread, the main CPU cost, is measured per frame; see [Performance](performance.md).

## Host features

The host adds what the console didn't have, without changing the game's files: in-game settings, the trainer, photo export, save backups, achievements, an ultrawide field of view, language selection and a [mod API](modding.md). Saves are written atomically and backed up after each write.

## Android

The Android build reuses the code translated on the PC, cross-compiles it for arm64 with the pinned NDK and packages it with a key made on your PC. The same renderer runs on Vulkan, with Mesa Turnip bundled for Adreno 7xx GPUs.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/` | Host code: app, settings UI, saves, DLC, mods, diagnostics |
| `launcher/` | The Windows launcher (.NET) |
| `android/` | The Android app: manifest, Java activity, resources and bundled driver notices |
| `tools/` | Setup, build, test and packaging scripts; `pinyon.py` is the command line |
| `config/` | Supported dumps and updates, pinned toolchains, render-test routes |
| `include/pinyon_mod.h` | The C API for native mods |
| `thirdparty/shiftglue-sdk` | The recompiler and runtime, as a submodule |

Engineering notes, measurements and backlogs are in [docs/](https://github.com/arcanite24/pinyon-shift/tree/dev/docs), starting from [DEVELOPMENT.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DEVELOPMENT.md).
