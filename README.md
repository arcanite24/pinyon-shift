# Pinyon Shift

<p align="center">
  <img src=".github/pinyon-shift-banner.png" alt="Pinyon Shift logo" width="800">
</p>

<p align="center">
  <b>The Xbox 360 release of <i>Forza Horizon</i>, recompiled to run natively on Windows.</b><br>
  Built on your own PC from your own disc, with internal resolutions up to 4K.
</p>

<p align="center">
  <a href="https://github.com/arcanite24/pinyon-shift/releases/latest"><b>Download the launcher</b></a>
  ·
  <a href="#play">How to play</a>
  ·
  <a href="#roadmap">Roadmap</a>
  ·
  <a href="#supporting-the-project">Support development</a>
</p>

<p align="center">
  <img src=".github/launcher-ready.png" alt="The Pinyon Shift launcher, ready to play: Vulkan at 1x (1280 × 720), with Play and Settings buttons" width="800">
</p>

Pinyon Shift is not an emulator. The game's PowerPC code is translated ahead of
time into C++ with [ShiftGlue](https://github.com/arcanite24/shiftglue-sdk), our
fork of ReXGlue, and compiled for x86-64 on your computer. The GPU command stream
the game builds is executed by a native renderer written for *Forza Horizon*,
on Vulkan (the default) or Direct3D 12. The project is a playable preview: early,
imperfect, and surprisingly drivable.

This repository contains the launcher, build tools, host code, configuration and
the pinned ShiftGlue submodule needed to create the preview on your own
computer. It does **not** contain the game, game assets, generated translations
or a prebuilt game executable.

> **Early days.** Rendering regressions and slowdowns in some areas remain
> possible. See the [0.4.0 release notes](docs/releases/0.4.0.md) for what the
> latest release contains and its known limitations.

## Highlights

- **Native code.** The title's executable is recompiled ahead of time; nothing
  is interpreted or JIT-compiled at run time.
- **A renderer built for this game.** Every draw, clear, resolve and swap runs
  in order with the game's own shaders, translated to SPIR-V (Vulkan) or DXBC
  (Direct3D 12). On Vulkan, one thread decodes the game's command stream while a
  second records the draws.
- **60 and 120 fps at the right game speed.** The render rate is decoupled from
  the console's 30 fps, with the simulation kept in step.
- **1x to 4x internal resolution**, FSR 1 output scaling, anisotropic and
  trilinear filtering, FXAA, and optional motion blur and depth of field.
- **Settings in game (F6)** for display, graphics, audio and controls, plus a
  trainer (F10: credits, game speed, time of day, free camera, collectibles on
  the map), photo export, save backups and [mods](docs/MODDING.md).
- **The Treasure Map included.** The add-on that showed every discount sign and
  barn find on the map was sold for Tokens through a service that no longer
  exists; it is on by default and can be turned off in the launcher.

## Performance

Measured on 2026-09-30 on one machine: AMD Ryzen 7 5800X (8 cores),
128 GB RAM, NVIDIA GeForce RTX 4080 (driver 581.08), Windows 11 Pro 26200,
3840×2160 display at 120 Hz.

### Against Xenia and the old Xenos renderer

The same scene on all four, from a new profile: the game's opening intro
cinematic and the start of the opening drive in the Viper. The internal
resolution is 1x (1280×720) and every program runs in a window at its default
settings.

| Program | Intro cinematic | Opening drive |
| --- | ---: | ---: |
| Xenia Canary (`67d80958c`, Direct3D 12) | 30.0 fps | 30.0 fps |
| Pinyon Shift 0.1.0 (ReXGlue Xenos renderer) | 28.3 fps | 29.0 fps |
| Pinyon Shift, native renderer on Direct3D 12 | 118.7 fps | 119.5 fps |
| **Pinyon Shift, native renderer on Vulkan** | **119.8 fps** | **120.0 fps** |

On the console *Forza Horizon* runs at 30 fps, and Xenia and the Xenos-era
build keep that cap. The native renderer renders at up to the display's
refresh rate, here 120 Hz, which caps both native rows. The race below shows how
much headroom is left.

<details>
<summary>How these were measured</summary>

Each program started FH1 from a fresh profile and was driven by the same
script: A was pressed every five seconds, as the repository's
`fh1-opening-sync` route does. Xenia got the key as real input while its window
was in the foreground; the others got it posted to their window. Each target had
a warm-up run first, and the measured run started from a fresh profile again
with only the shader and pipeline caches kept.

- **Windows.** The intro cinematic is 105–165 s after launch and the opening
  drive 185–240 s, on all four (checked in window captures every 15 s).
- **Xenia and the 0.1.0 build.** Frames are counted on screen with DXGI Desktop
  Duplication, and only frames whose image changed count, since Xenia presents
  the same image several times. Averages are over one-second counts; the worst
  second was 29 fps for Xenia and 21 fps for the 0.1.0 build.
- **Native rows.** These are the game's own frame log. The same on-screen count
  gives 109.5/119.6 fps on Direct3D 12 and 116.1/118.2 fps on Vulkan, slightly
  lower because consecutive frames sometimes look alike.
- **Xenia with vsync off.** Xenia then shows about 125 distinct frames a
  second, but its emulated vblank is no longer synchronized and the game's clock
  runs fast: it reached the drive about 25 s early. Those runs are not in the
  table.

</details>

### The race, native renderer

The scripted race (`fh1-race-sync`) is the heaviest route. It is measured over
the race's last 600 frames with the frame rate limited to 120, in a hidden
window, from the same save.

| Internal resolution | Vulkan | Direct3D 12 |
| --- | ---: | ---: |
| 1x (1280×720) | **110 fps** (9.1 ms) | 79 fps (12.7 ms) |
| 2x (2560×1440) | **79 fps** (12.7 ms) | 66 fps (15.2 ms) |
| 3x (3840×2160) | 35 fps (28.7 ms) | **57 fps** (17.5 ms) |

Median frame rate and frame time over the race's last 600 frames, its busiest
part.

Vulkan is the default because it records draws on a second thread, which makes
it the faster backend at 1x and 2x. At 3x and above the GPU is the limit, and
there Direct3D 12 is faster: the Vulkan backend spends more GPU time on the
game's multisampled surfaces. The optional single-sampled surfaces
(`fh1_scaled_msaa_single_sample`) bring Vulkan at 3x to about 24 ms. How the
Vulkan path got here is in the [performance backlog](docs/PERFORMANCE_BACKLOG.md).

## Play

1. Download `PinyonShift-Launcher.zip` from the latest release.
2. Extract the two files to a folder and run `PinyonShiftLauncher.exe`.
3. Drop the ISO you personally dumped from a supported original disc onto the
   launcher, or choose it with **Choose ISO**.
4. Confirm ownership, then choose **Verify and build**.
5. Leave the launcher open while it installs the Windows build tools and builds
   the preview. The first build can take 20–60 minutes and needs roughly 25 GB of
   free disk space.
6. Choose **Play**. Press **F6** in game for settings.

<p align="center">
  <img src=".github/launcher-settings.png" alt="The launcher's Settings panel: graphics API, internal resolution, output scaling, the resulting resolutions and the Treasure Map toggle" width="800">
</p>

**Settings** in the launcher picks the graphics API (Vulkan, recommended, or
Direct3D 12), the internal resolution and the output scaling (bilinear, CAS or
FSR 1), and says what that means on your screen: for example, renders
1280 × 720, FSR 1 upscales to 3840 × 2160. The Treasure Map toggle is there
too: on by default, and once a save's map is revealed it stays revealed, as
after a purchase. Vulkan is faster at 1x and 2x; for
3x and 4x choose Direct3D 12, which prepares shader packs for your computer
before its first start. Everything else, including the **Performance 120** and
**Quality 60** presets, is in the in-game settings, where most changes apply at
once; the graphics API and the language are among the few that need a
restart.

The preview launcher is not code-signed yet, so Windows may identify it as an
unrecognized app. Use only the archive attached to this repository's release
and verify its published SHA-256.

The launcher verifies the image before reading it. Unsupported or modified
images are rejected. Your image and extracted game files stay on your machine.
The launcher downloads build tools and the pinned ShiftGlue source, extracts
the disc locally, generates the translation locally and compiles the executable
locally. Administrator permission is requested only if Visual Studio Build Tools
must be installed.

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

If setup fails, the launcher shows which step failed, its exit code, the first
real compiler, CMake or file-copy error from that step's log and a hint for
common causes (a full disk, low memory, antivirus, a file in use). The same
report is saved in `.local/logs/setup-error.json`, next to the complete logs.
Include that report when filing an issue; the final "build failed" line alone
cannot identify the cause.

### Portable install

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

### Requirements

- The USA retail base disc, serial `MS-2505`, title ID `4D5309C9`.
- Windows 10 or 11, x64.
- A GPU with Vulkan 1.3 (the default) or Direct3D 12. Only NVIDIA GPUs are
  qualified so far; AMD and Intel are untested.

This is a public preview, not a finished remaster. Please report reproducible
problems with the issue template and do not attach game files or generated
code.

## Reporting crashes and bugs

Keep the launcher open while playing. If the game exits unexpectedly, the
launcher catches the exit, creates a sanitized diagnostic ZIP, and offers one
button to open a prefilled GitHub issue with that ZIP selected in Explorer.
Attach the selected ZIP and add the shortest reliable reproduction steps.

The public report includes build hashes, a stable crash ID, exception details,
the end of the runtime log, runtime settings, Windows build, CPU, GPU and driver
versions. It excludes the game, saves, generated code, input capture, local
paths and memory dumps. A fuller dump stays on the player's computer and should
only be shared privately if a maintainer requests it. Non-crash bugs can be
reported with **Report a problem** in the launcher.

## Build from source

From a PowerShell terminal in a repository checkout:

```powershell
.\tools\setup-preview.ps1 -IsoPath C:\path\to\your-disc.iso
.\tools\launch-preview.ps1
```

The setup script provisions pinned dependencies, initializes ShiftGlue,
verifies and extracts the disc, generates translated source, and builds Release
with both the Vulkan and the Direct3D 12 backends.
`python tools/pinyon.py launch` starts the built game the same way without
PowerShell, with `--state-root`, `--hidden` and game arguments after `--`; it is
the launcher for Linux builds. See [Building](docs/BUILDING.md) and
[Troubleshooting](docs/TROUBLESHOOTING.md) for details.

## Roadmap

Where the project is going; the open items are in no particular order. The
ordered plan, with vertical slices, sizes, dependencies and acceptance gates,
is the [native port backlog](docs/NATIVE_PORT_BACKLOG.md); renderer
performance work is in the [performance backlog](docs/PERFORMANCE_BACKLOG.md).

Done since 0.1:

- [x] Change resolution and render scale while the game is running
- [x] Apply graphics settings without restarting the preview (all but the
  graphics API)
- [x] Support ultrawide (21:9 and wider) displays, with a 16:9 HUD and a field
  of view setting
- [x] Ship a modding API for loading custom content: native plugins, file and
  archive overrides, database patches and texture replacement
- [x] Let mods add HUD labels, menu actions and replacement text
- [x] Play in any of the disc's 18 languages
- [x] Achievements, photo export, save backups and a trainer in game
- [x] Support portable installs

Next:

- [ ] Lower the hardware requirements and qualify AMD and Intel GPUs
- [ ] Fix the remaining rendering regressions
- [ ] Keep crowd and purchase animations at the right speed above 30 fps
- [ ] Hold 120 fps in every race, and reach 4K at 120 fps on Vulkan
- [ ] Make the first build faster and fully validated
- [ ] Update to a new release from inside the launcher
- [ ] Install, enable and order mods from the launcher
- [ ] Sign the launcher and preview executables
- [ ] Support more disc regions
- [ ] Load the car-pack add-ons from your own Xbox 360 content
- [ ] Import a save from an Xbox 360
- [ ] More trainer options: unlock cars and events, and let any car enter any
  event
- [ ] Verify DualSense, Steam Input and variable refresh rate displays
- [ ] Let mods add items to the game's own menus
- [ ] Build for macOS and Linux
- [ ] Ship a Steam Deck build
- [ ] Port the runtime to Android
- [ ] Import cars from *Forza Horizon 2*

Measured findings and validation rules are in
[development findings and priorities](docs/DEVELOPMENT.md).

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

## Supporting the project

Pinyon Shift is and will remain free. Every release, feature and setting is
public on the same day for everyone. There are no supporter builds, early
access, paid features or paid mods, and there never will be.

If you would like to support continued development, you can
[sponsor arcanite24 on GitHub] or [buy me a coffee on Ko-fi]. Contributions
pay for development time and for test hardware, such as Android phones and
lower-end GPUs used for the performance work. They do not buy builds, game
content, priority support or influence over the roadmap. Support is for the
work on this project, not for *Forza Horizon*, which remains the property of
its owners.

Sharing the project, reporting bugs with a diagnostic ZIP and contributing
code help just as much.

[sponsor arcanite24 on GitHub]: https://github.com/sponsors/arcanite24
[buy me a coffee on Ko-fi]: https://ko-fi.com/nerijs
