# Installing and setup

The short version is in the [README](../README.md#play). This page covers the
launcher's settings, where it installs, portable installs and setup failures.

## Launcher settings

<p align="center">
  <img src="../.github/launcher-settings.png" alt="The launcher's Settings panel: Vulkan, internal resolution, output scaling, the resulting resolutions and the Treasure Map toggle" width="800">
</p>

**Settings** in the launcher shows Vulkan and picks the internal resolution
and the output scaling (bilinear, CAS or
FSR 1), and says what that means on your screen: for example, renders
1280 × 720, FSR 1 upscales to 3840 × 2160. The Treasure Map toggle is there
too: on by default, and once a save's map is revealed it stays revealed, as
after a purchase. **This PC** lists the graphics card, its memory and Vulkan
version, the CPU's cores and the display's refresh rate, recommends the
in-game preset that suits them (the same rule a new install uses, and
Balanced 40 below 4 CPU cores) and sets it with one click. It warns when no
Vulkan 1.3 driver is found. Existing Direct3D 12 settings migrate to Vulkan on the next
start. Everything else, including the **Low-spec 60**, **Balanced 40**,
**Performance 120** and **Quality 60** presets, is in the in-game settings, where
most changes apply at once; MSAA and the language are among the few that need a
restart. A new install starts at Low-spec 60, or at Performance 120 on a
discrete GPU with 6 GB or more, 6 or more CPU threads and a 120 Hz display.

## Game language

To change the game language, press **F6** at the title screen or during play,
open **Profile → Language**, and use Left/Right to choose a language and region.
Close and restart the game to apply it. This is available before the first race;
the choice stays saved for the next launch.

## Verification and privacy

The preview launcher is not code-signed yet, so Windows may identify it as an
unrecognized app. Use only the archive attached to this repository's release
and verify its published SHA-256.

The launcher verifies the image before reading it. Unsupported or modified
images are rejected. Your image and extracted game files stay on your machine.
The launcher downloads build tools and the pinned ShiftGlue source, extracts
the disc locally, generates the translation locally and compiles the executable
locally. Administrator permission is requested only if compatible Visual Studio
Build Tools must be installed or completed. VS 2022 Build Tools 17.1 or newer
are required; VS 2019 alone does not satisfy the C++ standard library
requirement. The game carries its own copy of the Visual C++ runtime.

## Install location

To build on another drive, choose **Change** next to **Installs to** on the
setup screen of the packaged launcher. The launcher remembers your choice for subsequent launches.
This selects an installation; it does not move an existing installation or save.
You can also override the remembered location from PowerShell:

```powershell
$env:PINYON_SHIFT_INSTALL_ROOT = 'D:\Games\PinyonShift'
.\PinyonShiftLauncher.exe
```

Source, downloaded tools, extracted game data and the default save and cache
tree live beneath that folder. Existing installations and saves are not moved;
an existing `PINYON_SHIFT_STATE_ROOT` override still takes precedence for saves
and caches. Launchers inside a repository checkout continue to use that
checkout. This is a custom build location, not a portable install: the choice
is remembered in `%LOCALAPPDATA%\PinyonShift\install-root.txt`, and Microsoft
Build Tools still need system-drive space.

## When setup fails

If setup fails, the launcher shows which step failed, its exit code, the first
real compiler, CMake or file-copy error from that step's log and a hint for
common causes (a full disk, low memory, antivirus, a file in use). The same
report is saved in `.local/logs/setup-error.json`, next to the complete logs.
Include that report when filing an issue; the final "build failed" line alone
cannot identify the cause.

## Portable install

To keep everything in one folder you can move or carry, put an empty file named
`portable.txt` next to `PinyonShiftLauncher.exe` (or start the launcher with
`--portable` for a single run). The launcher then keeps the release source,
downloaded build tools, the build, logs, crash reports, saves, settings,
photos, save backups and shader caches in a `data` folder beside itself, and
the setup screen reads **Portable:** followed by that folder:

```text
PinyonShift\
  PinyonShiftLauncher.exe
  pinyon-shift-source.zip
  portable.txt
  data\source\<version>\                  release source, tools, build, setup logs
  data\source\<version>\.local\preview\   saves, settings, game logs, crash reports
  data\temp\                              temporary files of setup and crash reports
```

Nothing is written to `%LOCALAPPDATA%\PinyonShift` or the registry, and
`PINYON_SHIFT_INSTALL_ROOT` and `PINYON_SHIFT_STATE_ROOT` are ignored. No
absolute path is stored: the launcher finds every location from its own folder
at each start, so the whole folder can move to another drive or Windows PC. A
build moved this way plays as it is; the next rebuild (after an update)
configures the moved build folder afresh and recompiles.

Extract a portable install into a folder you can write to, such as
`D:\Games\PinyonShift`: the launcher refuses read-only locations like Program
Files with an explanation. Keep the path short, too: the build creates files
about 185 characters below `data`, so the launcher will not start a build when
the `data` folder's path is longer than 70 characters. Outside the launcher's
control are Visual Studio Build Tools (a system install, added again on another
PC at its next build), the graphics driver's own shader cache, and the files
.NET unpacks from the launcher into `%TEMP%\.net` when it starts (set
`DOTNET_BUNDLE_EXTRACT_BASE_DIR` to a folder of your choice to move them too).
