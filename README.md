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

The preview launcher is not code-signed yet, so Windows may identify it as an
unrecognized app. Use only the archive attached to this repository's release
and verify its published SHA-256.

The launcher verifies the image before reading it. Unsupported or modified
images are rejected. Your image and extracted game files stay on your machine.
The launcher downloads build tools and the pinned ReXGlue source, extracts the
disc locally, generates the translation locally, and compiles the executable
locally. Administrator permission is requested only if Visual Studio Build
Tools must be installed.

Supported today: the USA retail base disc, serial `MS-2505`, title ID
`4D5309C9`. Windows 10/11 x64 and a DirectX 12-capable GPU are required.

This is a public preview, not a finished remaster. Please report reproducible
problems using the issue template and do not attach game files or generated
code.

## Reporting crashes and bugs

Keep the launcher open while playing. If the game exits unexpectedly, the
launcher catches the exit, creates a sanitized diagnostic ZIP, and offers one
button to open a prefilled GitHub issue with that ZIP selected in Explorer.
Attach the selected ZIP and add the shortest reliable reproduction steps.

The public report includes build hashes, a stable crash ID, exception details,
the end of the runtime log, runtime settings, Windows build, CPU, GPU, and driver
versions. It excludes the game, saves, generated code, input capture, local
paths, and memory dumps. A fuller dump stays on the player's computer and should
only be shared privately if a maintainer requests it. Non-crash bugs can be
reported with **Report a problem** in the launcher.

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
