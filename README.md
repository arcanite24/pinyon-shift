# Pinyon Shift

Pinyon Shift is a Windows-only playable preview of a native recompilation of
the Xbox 360 release of *Forza Horizon*. The project is early, imperfect, and
surprisingly drivable.

This repository contains the launcher, build tools, host code, configuration,
and patches needed to create the preview on your own computer. It does **not**
contain the game, game assets, generated translations, or a prebuilt game
executable.

## Play

1. Download `PinyonShift-Launcher.zip` from the latest release.
2. Extract the two files to a folder and run `PinyonShift.Launcher.exe`.
3. Select an ISO you personally dumped from a supported original disc.
4. Confirm ownership, then choose **Verify & Build**.
5. Leave the launcher open while it installs the Windows build tools and builds
   the preview. The first build can take 20–60 minutes and requires roughly
   25 GB of free disk space.

The launcher verifies the image before reading it. Unsupported or modified
images are rejected. Your image and extracted game files stay on your machine.
The launcher downloads build tools and the pinned ReXGlue source, extracts the
disc locally, generates the translation locally, and compiles the executable
locally. Administrator permission is requested only if Visual Studio Build
Tools must be installed.

Supported today: the USA retail base disc, serial `MS-2505`, title ID
`4D5309C9`. Windows 10/11 x64 and a DirectX 12-capable GPU are required.

## Preview limitations

- Xbox-compatible controllers are recommended; keyboard emulation is available
  as a fallback and has not been exhaustively tested.
- Gameplay audio is incomplete, although cutscene audio works.
- The player car may shake or jitter.
- Vehicle collisions can behave incorrectly.
- The camera may jump to an aerial view during the Mustang versus Mustang event.

This is a public preview, not a finished remaster. Please report reproducible
problems using the issue template and do not attach game files or generated
code.

## Build from source

From a PowerShell terminal in a repository checkout:

```powershell
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso
.\tools\launch-preview.ps1
```

The setup script provisions pinned dependencies under `.local/`, downloads and
patches ReXGlue, verifies/extracts the disc, generates translated source, and
builds Release. See [Building](docs/BUILDING.md) and
[Troubleshooting](docs/TROUBLESHOOTING.md) for details.

## Project boundaries

Only independently authored project files are licensed under the
[BSD 3-Clause License](LICENSE). Microsoft, Xbox, Turn 10 Studios, Playground
Games, *Forza Horizon*, and third-party dependencies remain the property of
their respective owners. Pinyon Shift is not affiliated with or endorsed by
them. See [Legal and distribution](docs/LEGAL.md) and
[Third-party notices](THIRD_PARTY_NOTICES.md).

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Repository checks reject disc
images, executables, generated translations, extracted assets, build products,
and other machine-local material.
