# Linux and Steam Deck

Pinyon Shift builds and runs natively on x86-64 Linux, Steam Deck included.
Nothing runs through Proton or Wine. The setup is the same as on Windows: you
choose your own disc image, and the launcher verifies it, builds the game on
your machine and starts it.

## Steam Deck

You need your ISO of the USA retail disc (`MS-2505`), about 45 GB free on the
internal drive or a microSD card, and a charger: the first build takes
about 35 minutes and keeps the Deck busy throughout.

1. Hold the power button, choose **Switch to Desktop**.
2. Copy your ISO onto the Deck, for example from a USB drive or a microSD
   card, or over the network. Any folder works; **Downloads** is fine.
3. Open Firefox, download `PinyonShift-Launcher-linux-x86_64.tar.gz` from the
   [latest release](https://github.com/arcanite24/pinyon-shift/releases/latest)
   and verify the SHA-256 listed there.
4. In Dolphin, right-click the download and choose **Extract → Extract archive
   here**. Open the new `PinyonShift` folder and double-click
   `PinyonShiftLauncher`.
5. Choose **Choose disc image** and select your ISO, or drop it onto the
   launcher. Confirm ownership and choose **Verify and build**.
6. When the launcher says **Ready to drive**, choose **Add to Steam**. Steam
   restarts to pick up the entry and its artwork.
7. Double-click **Return to Gaming Mode** on the desktop. Pinyon Shift is in
   your library under **Non-Steam**. Start it from there from now on.

The launcher installs everything under `~/.local/share/PinyonShift`. Nothing
else on the Deck is changed apart from the Steam shortcut and an entry in the
applications menu, and SteamOS's read-only system needs no unlocking: no
password, no `pacman`, no developer mode.

### Playing on the Deck

- The built-in controls work as an Xbox 360 pad through Steam Input. Open the
  game's settings from the pause menu (SETTINGS), or anywhere by pressing
  View and Menu together (BACK + START, changeable under CONTROLS >
  CONTROLLER BUTTONS > SETTINGS MENU).
- **F6 > GRAPHICS > SCENE SHADING > COARSE** shades the scene once per 2 × 2
  pixels: a little softer, and about 8 % of the GPU's frame saved on the
  Deck.
- In our tests the race and free roam hold 60 fps at 1x (1280 × 720) under the
  Deck's default 15 W limit.
- **Leave Manual GPU Clock off** in the Quick Access menu's Performance
  settings. With it on, Steam can pin the GPU at 200 MHz, and the game drops
  to about 10 fps while the GPU reports full load at under 1 W.

## Linux PCs

Requirements:

- An x86-64 CPU with SSE4.1. The build uses x86-64-v3 (AVX2, FMA3, BMI2,
  MOVBE) when the CPU has it, as the Steam Deck's does.
- A Vulkan 1.3 driver: Mesa's RADV on AMD (Mesa 23 or newer), or NVIDIA's
  proprietary driver. Intel and NVIDIA on Linux are not qualified yet.
- glibc 2.31 or newer, `python3` 3.9 or newer, `git`, and GLib. Every current
  desktop distribution has them.
- About 45 GB free for the first build: the pinned compiler and the Steam
  Runtime SDK the game is built against take about 15 GB of it.

Download `PinyonShift-Launcher-linux-x86_64.tar.gz`, extract it and run
`PinyonShift/PinyonShiftLauncher`, then follow the Deck steps from step 5.
**Add to Steam** is optional on a PC; the launcher also adds Pinyon Shift to
your applications menu.

The game binary is built against the Steam Runtime 3 (sniper) SDK with a
pinned LLVM, so builds are reproducible and do not depend on your
distribution's compilers or libraries.

## From a terminal

The launcher runs these commands. In an extracted source tree or a repository
checkout:

```bash
python3 tools/pinyon.py setup --iso ~/Downloads/forza-horizon.iso
python3 tools/pinyon.py launch
python3 tools/pinyon.py shortcuts add
```

`setup` downloads its pinned, SHA-256 checked build tools into
`.local/toolchain`, reads the disc image directly (no `extract-xiso` or loop
mounts), checks every file against the supported dump and builds. Run
`setup --build-only` to rebuild after an update, and `shortcuts add
--no-steam` for only the applications menu entry. `shortcuts remove` undoes
both.

### Build options

- **CPU baseline.** Setup builds for the CPU it runs on: x86-64-v3 when
  `/proc/cpuinfo` lists `avx2 bmi1 bmi2 fma movbe f16c abm` (Haswell, Zen
  and later, the Steam Deck included), otherwise the FMA3 variant or
  SSE4.1. Set `PINYON_SHIFT_CPU_BASELINE=sse4.1` (or `fma`, `v3`) before
  `setup --build-only` to choose one, for example for a build that will be
  copied to an older PC. A build started on a CPU without its baseline stops
  with a message instead of crashing.
- **Code model.** Linux x86-64 builds use the small code model with linker
  relaxation (`REXGLUE_X86_64_CODE_MODEL=small`, the default). `large`
  (`-mcmodel=large -Wl,--no-relax`) is still accepted at configure time; it
  makes every call register-indirect.
- **Thread placement.** `linux_thread_cores` (default `auto`) pins threads by
  name. `auto` applies the layout measured on the Steam Deck when it detects a
  Deck (LCD or OLED) and does nothing on other PCs; the runtime log says
  which. `off` leaves every thread to the scheduler, and entries such as
  `GPU_Commands=4;*=5,7` set a layout of your own, as `android_thread_cores`
  does on Android. It can be changed while the game runs.
- **Building for a Deck on another PC** (the developer loop: WSL or a Linux
  PC, then `python3 tools/pinyon.py deck install`): configure with
  `cmake --preset linux-amd64-v3`, the Deck's x86-64-v3 variant, since a PC
  build cannot see the Deck's CPU. `deck install` copies
  `out/build/linux-amd64-v3` by default and falls back to the SSE4.1
  `linux-amd64-release` build with a note; `--build-directory` picks any
  other.

## DLC, the title update and saves

These work as they do on Windows. The launcher's **DLC and v4**,
**Settings** and **Import a save** panels do all of this, with the same
wording and checks as the Windows launcher, and Play builds and starts v4
when it is on (the XE mod wins over v4, as on Windows). Underneath, each
command prints one JSON object with `--json`, which is what the launcher
reads. To run them yourself, use the install's source folder while the game
is closed:

- **DLC.** `python3 tools/pinyon.py dlc import <package, folder or ZIP>`,
  then `dlc enable <package id>`. Enabling the Rally Expansion Pack prepares
  its assets. `dlc status` lists the packages.
- **Title update v4.** `title-update import <package, folder or ZIP>`
  verifies the update against your disc and installs it. `title-update
  enable` makes Play start v4, and `club-on` turns on the offline 1000 Club.
  The first v4 start builds `out/build/linux-amd64-v4` from your disc and
  update, for the same CPU baseline as the base build, and backs up your
  profile first: a profile saved by v4 cannot go back to the base game.
  `title-update restore` puts the pre-v4 backup back.
- **A save from another PC.** `import-save <folder or ZIP>` takes another
  install's `.local/preview` folder (from Windows,
  `%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview`) and copies
  its profiles here. It backs up your current ones to
  `.local/preview/backups/before-import-<time>` first. A save from Xenia is
  `import-save --xenia <content/XUID/4D5309C9 folder>`.
- **Crash reports.** After a crash, `launch` writes a ZIP to
  `.local/preview/reports` and prefills a GitHub issue link. Paths and your
  user name are removed, and no game files, saves or memory dumps go in.
- **Shader preparation.** Before the first start, Play runs the opening once,
  hidden, so the first race does not stutter while Vulkan builds pipelines.
  It runs once per build. If it fails, the game still plays.
- **Hardware check.** `hardware --json` names the Vulkan GPU and suggests a
  game preset. It warns when the only Vulkan device is a software renderer
  (llvmpipe), which means the GPU driver is missing.

On a Steam Deck (LCD, 15 W) the 21 packages imported and enabled with these
commands load as on Windows: the same 84 DLC car rows, a DLC car bought from
the Autoshow and driven. A v4 build boots with the update applied and
reaches the offline 1000 Club and the native Rally intro.

The launcher's **Android** panel builds the Android app (`android build`,
the v4 app when v4 is on). Off Windows it needs the Android SDK's
command-line tools and a JDK 17 that you install (Android Studio, or
`ANDROID_HOME` and `JAVA_HOME` set); the launcher then adds the NDK and
build tools with `sdkmanager`. Only the Windows launcher downloads the SDK
and Java itself. **Share on Wi-Fi** shows a QR code and a pairing
code: the device installs the app and copies the game files, DLC, Rally
data, the v4 update and your mods from this computer. It listens on TCP
47615 and UDP 47616, so allow those on the local network if a firewall is
on. **Install over USB** uses `adb` for a device with USB debugging.

## Where things live

```text
~/.local/share/PinyonShift/source/<version>/   source, tools, game files, build
  .local/preview/user/                         saves
  .local/preview/                              settings, game logs, crash reports
  .local/logs/                                 setup logs
```

`PINYON_SHIFT_INSTALL_ROOT` moves the install elsewhere, for example to a
microSD card under `/run/media/`. In the launcher, **Change** on the setup
screen picks the folder and remembers it. An empty `portable.txt` beside
`PinyonShiftLauncher` makes a portable install: everything, temporary files
included, stays in the `data` folder next to it.

## Troubleshooting

- **Setup failed.** The launcher names the step and the log. The same report
  is in `.local/logs/setup-error.json`; attach it when you file an issue.
- **Very low frame rate on the Deck.** Check Manual GPU Clock, above.
- **The game does not appear in Game Mode.** Choose **Add to Steam** again
  while Steam is running; it rewrites the entry and restarts Steam. A backup
  of Steam's previous shortcuts is kept next to them as
  `shortcuts.vdf.pinyon-backup`.

## Uninstalling

1. Remove the shortcut in Steam, or run `python3 tools/pinyon.py shortcuts
   remove` in the install's source folder to remove it and the menu entry.
2. Copy your saves out of `.local/preview/user` if you want to keep them.
3. Delete `~/.local/share/PinyonShift`.

## Support status

| System | Status |
| --- | --- |
| Steam Deck LCD, SteamOS 3.7 | Builds and plays; 60 fps at 1x; the DLC and v4 load and play |
| Ubuntu 24.04 (WSL) | Release archive to a built game in 20 minutes; Add to Steam writes the shortcut and art; runs with a null GPU |
| Arch Linux (container, libxml2 2.15) | The pinned toolchain configures and links with setup's `ld.lld` wrapper (#472); a full build not run |
| Other distributions, NVIDIA, Intel | Not tested yet |

Work still open is tracked in the
[Linux and Steam Deck backlog](LINUX_PORT_BACKLOG.md).
