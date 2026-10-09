---
title: Build from source
section: Technical
order: 3
description: Build Pinyon Shift from a repository checkout with PowerShell or the pinyon.py command line.
---

# Build from source

The launcher runs these same scripts. Use a checkout when you're changing host or ShiftGlue code.

## Requirements

- Windows 10 or 11, x64, PowerShell 5.1 or newer.
- Visual Studio 2022 C++ Build Tools 17.1 or newer. Setup installs them if missing.
- A GPU with Vulkan 1.3, an internet connection and about 30 GB free.

Setup checks the C++ library and the Windows SDK before building, and stops with compiler diagnostics if they're too old.

## Set up and play

```bash
git clone https://github.com/arcanite24/pinyon-shift.git
```

```powershell
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso
.\tools\launch-preview.ps1
```

`setup-preview.ps1` runs the [six setup stages](how-it-works.md#recompilation) and can be run again after a failure: finished downloads and extraction are reused after they're verified. Other forms:

```powershell
# Check the image only
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso -VerifyOnly
# Build from an extracted folder
.\tools\setup-preview.ps1 -ExtractedPath 'D:\Games\Forza Horizon'
```

## Rebuild

After changing host or ShiftGlue code:

```powershell
.\tools\build-preview.ps1
```

## The pinyon.py command line

`tools/pinyon.py` works without PowerShell and is the launcher for Linux builds.

```bash
python tools/pinyon.py launch -- --fullscreen=true
python tools/pinyon.py android doctor --install
python tools/pinyon.py android build
```

`launch` also takes `--state-root`, `--hidden` (no window, audio muted) and `--render-test-script` for scripted routes. Game arguments go after `--`. The Android commands are listed on the [Android](android.md#install-over-usb) page.

## Package the launcher

```powershell
.\tools\package-launcher.ps1
```

The package holds a self-contained launcher and a source archive. It excludes the compiled game, generated translations and all game content.

## Contributing

Read [CONTRIBUTING.md](https://github.com/arcanite24/pinyon-shift/blob/dev/CONTRIBUTING.md) first. Repository checks reject disc images, executables, generated translations, extracted assets and build products. Commit subjects follow Conventional Commits.
