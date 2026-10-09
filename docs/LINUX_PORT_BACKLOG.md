# Linux and Steam Deck backlog

Status: **open; created 2026-10-08** at `dev` checkpoint `690e149` (ShiftGlue
`c057fb2`). This is the detailed plan for NP-12 of the
[native port backlog](NATIVE_PORT_BACKLOG.md#np-12-linux-and-steam-deck),
written as a sibling of the [Android port backlog](ANDROID_PORT_BACKLOG.md):
same slice and row conventions (`LX-n`, `LX-n.m`), sizes, gates and trains.
It was written from a read-only audit of the tree and from probes of the
reference Steam Deck over the LAN. Nothing has been configured, built or run
on desktop Linux yet. `sdk/` stands for `thirdparty/shiftglue-sdk/`. Claims
the repository and the probes cannot show are marked **guess**, and each has
a row that checks it before anything depends on it.

## Goal

A player who owns the supported disc builds Pinyon Shift **natively for
x86-64 Linux** and plays it at the panel's 1280x800. The build can run on a
Linux PC, on the Steam Deck itself, or on their Windows PC for their Deck.
Play starts from Steam's Game Mode with the Deck's built-in controls, and
saves, settings, DLC, mods and the in-game host UI work as on Windows. The
game is an ELF executable. Wine, Proton and Windows binaries are not
involved anywhere.

"Linux port" is done when all of the following hold:

1. **Same legal model.** The binary is built locally from the player's own
   disc and is never published. Game data and the build travel only between
   the player's own machines ([legal](LEGAL.md)).
2. **Same code.** One generated translation, one SDK runtime, one FH1
   executor and one Vulkan backend serve Windows, Android and Linux. Linux
   differences live in the platform layer and in capability fallbacks.
3. **Correct.** The routes that gate Windows changes pass on the Deck (RADV).
   Simulation-time ratios and vehicle state match Windows, captures match the
   Windows goldens, and the executor skips nothing (NP-12's gate).
4. **Playable on the Deck.** It launches from Game Mode with a default
   controls layout, every feature is reachable without a keyboard, and the
   view fits 1280x800. Suspend and resume are clean, and the sound is right.
   At least one preset holds its frame rate for 20 minutes on battery. The
   targets are **guesses** until LX-7.0 measures: 60 fps in free roam, a
   steady 40 in the race, and 30 with the game's MSAA.
5. **Portable.** The same binary runs on SteamOS, Ubuntu 24.04, Fedora and
   Arch, under X11 and Wayland, on Mesa (RADV, ANV) and on NVIDIA's
   proprietary driver.
6. **Operable.** Setup, build, launch, DLC, crash reports and the
   route runner work without PowerShell. The developer tooling deploys to the
   Deck and runs routes on it from the PC.

### Non-goals

- Proton or Wine. The issue #388 player's GE-Proton setup may keep working,
  but it is not supported or tested, and nothing here depends on it.
- Publishing a built game in any form: binary, AppImage, Flatpak or Steam
  listing. The launcher, which is independently written, is distributed. The
  game never is.
- Linux on ARM64 (Asahi, Snapdragon X). AP-0 may add presets; nothing here
  schedules them.
- 32-bit, musl, or glibc older than the Steam Runtime's 2.31.
- Valve's Deck Verified programme. A non-Steam game cannot enter it, but its
  checklist (default controls, legible text at 1280x800, suspend, no
  keyboard needed) is the bar for LX-5.
- Replacing the Windows WPF launcher. LX-6 adds a Linux launcher. Whether
  it later replaces the WPF one is a separate decision.

## Decisions

These are proposals; the maintainer confirms them before the slices that
depend on them.

| ID | Decision | Why | Instead of |
| --- | --- | --- | --- |
| D1 | **Toolchain: pinned LLVM 20.1.8 plus the Steam Runtime 3 "sniper" SDK sysroot**, both downloaded and hash-checked like the Windows tools. clang targets `x86_64-linux-gnu` with `--sysroot`, links with lld, and links GCC 14's libstdc++ and libgcc statically. | The Windows build already pins LLVM 20.1.8 (`config/release-toolchain.json:51-56`), so both platforms use one compiler version. Sniper is the runtime Valve asks native Linux games to build against. Its glibc 2.31 floor runs on every current distribution and SteamOS (2.41), and the sysroot ships GCC 14 (C++23 `std::byteswap`, `<format>`). It needs no root, packages or containers. The same two archives serve a Linux PC, a Deck in Desktop Mode and a Windows cross-build. | Distribution compilers (unpinned, and the build host's glibc leaks into the binary); the SDK CI's Ubuntu 22.04 container (needs Docker, glibc 2.35); a Flatpak SDK (the wrong shape for build-it-yourself) |
| D2 | **Run on the host**, not inside the Steam Linux Runtime container. The binary carries `$ORIGIN` RPATH and loads Vulkan, X11, Wayland and the audio servers at run time through SDL. Everything else is static or bundled. | Fewest moving parts on the Deck. A binary built against glibc 2.31 runs on newer hosts. Running under "Steam Linux Runtime 3.0 (sniper)" as a compatibility tool is qualified later as an option (LX-8.6). | Requiring the container for every launch |
| D3 | **Build hosts, in this order:** (a) native x86-64 Linux, with WSL2 on the development PC; (b) the Deck itself in Desktop Mode, using the same tooling; (c) a Windows **Build for Steam Deck** that cross-compiles the PC's existing generated tree and sends the result over Wi-Fi with the pairing code, as **Build APK** does. | (a) is the fastest path to running code. (b) is the only path for players without a Windows PC. (c) spares most Deck owners a long compile on the Deck. | Building only on the Deck, or only on Windows |
| D4 | **A Python core first, a GUI second.** `tools/pinyon.py` gains `setup`, `build`, `prepare-shaders`, `dlc`, `deck` and `doctor` next to `launch`, covering every PowerShell stage. This is the Python core NP-D plans for both launchers. The proposed GUI is an **Avalonia port** of the WPF launcher's views. It reuses the launcher's non-UI C# and ships as a self-contained `linux-x64` .NET 8 app. | Setup and DLC changes happen in Desktop Mode, where a desktop GUI with touch works. In Game Mode the Steam shortcut starts the game directly, so the launcher needn't be controller-first. One C# codebase can later serve both platforms. | An SDL3 and ImGui launcher (controller-native, but it rewrites every WPF feature); a CLI only |
| D5 | **Windowing: what SDL picks, qualified on both.** Game Mode's gamescope runs Xwayland (two servers, `--xwayland-count 2`), so X11 through xcb is the Deck's main path. Wayland matters on desktop sessions. | `surface_gnulinux.cpp` already has both. | Forcing one |
| D6 | **The development loop reaches the Deck over SSH with the SteamOS devkit key.** Valve's SteamOS Devkit Client is paired on the development PC, and the Deck is `steamdeck`. Builds go over with rsync. Game Mode runs use a shortcut made by devkit-utils' `steam-client-create-shortcut`, and scripted runs use `gamescope --backend headless`. State lives in private roots under `~/pinyon-qual/<name>`. | It mirrors the Android tooling (`pinyon.py android`, private state roots) and leaves the Deck's own Steam library and saves alone. | Running by hand in Desktop Mode |

## Reference hardware

Probed on 2026-10-08:

| Machine | Facts |
| --- | --- |
| Steam Deck LCD (`Jupiter`) | SteamOS (holo), kernel 6.11.11-valve26. AMD Custom APU 0405: Zen 2, 4 cores and 8 threads, up to 3.5 GHz; RDNA 2 "VANGOGH". Mesa 24.3 RADV; Vulkan 1.3.296 on the device, loader 1.4.303. 14 GiB of RAM visible plus 8 GiB swap. Vulkan heaps: 3 GiB device-local and 6 GiB host-visible. Panel 1280x800 (a portrait 800x1280 panel that gamescope rotates). Game Mode runs gamescope 3.16.14 with two Xwayland servers; its `--backend headless` exists. Root filesystem read-only. podman 5.3 and distrobox 1.8 are present; no compilers. 113 GB free on `/home`. Wi-Fi 5 GHz. Proton and the sniper runtime are installed, and neither is used here. |
| Deck Vulkan features the renderer uses | All present: `geometryShader`, `sparseBinding`, `sparseResidencyBuffer`, fragment shader pixel and sample interlock, `VK_EXT_shader_stencil_export`, `sampleRateShading`, `independentBlend`, `fillModeNonSolid`, dynamic rendering, `VK_EXT_memory_budget`, `VK_KHR_present_wait` and `present_id`, `VK_EXT_swapchain_maintenance1`, `VK_EXT_calibrated_timestamps`. D24S8 support was not probed (LX-4.1). |
| Development PC (Multivac) | WSL2 Ubuntu 24.04 with 16 threads, 62 GB, clang 20.1.2 and CMake 3.28. WSL has no native Vulkan, so it serves for building and null-GPU runs only. |
| Needs a person | A desktop Linux install on NVIDIA's proprietary driver (for example Multivac's RTX 4080 booted into Linux); a Mesa desktop beyond the Deck; optionally a Deck OLED (90 Hz, HDR). |

## How this backlog is organised

- **Slices** `LX-n` end with something a developer or player can run; rows are
  `LX-n.m`. Sizes are for one engineer: S is a week or less, M is 1-3 weeks,
  L is 1-2 months and XL is more than 2 months. They are estimated from the
  code, not committed.
- **Gates** reuse the [development findings](DEVELOPMENT.md) rules: the same
  seed and route for the control (Windows) and the candidate (Linux), and
  simulation-time bounds where guest timing changes. Captures are compared
  against the Windows run of the same route. Seeds come from
  `tools/create-render-seed.py`; never use the AppData save or the Deck's
  own state.
- **Trains.** `linux-alpha` builds from a checkout and renders on the Deck,
  for developers (LX-0 to LX-2). `linux-preview` takes a player from disc to
  play on a Linux PC and on the Deck (LX-3 to LX-7). `linux-1.x` adds the
  Linux launcher, Windows-to-Deck delivery and the distribution matrix
  (LX-6, LX-8).
- **Cross-references, not copies.** Rows owned by other backlogs (NP-12.x,
  NP-6.3, LS-x.y, AP-x.y) are referenced by ID, and their evidence stays
  there.

## Where the code stands

| Area | Finding | Linux readiness | Evidence |
| --- | --- | --- | --- |
| Presets | Root `linux-amd64-{debug,relwithdebinfo,release}` presets exist: Ninja, `clang`/`clang++`, `-msse4.1`. They configure only on a Linux host. There is no toolchain file or sysroot, and they have never been configured. | Written, unbuilt | `CMakePresets.json:31-51, 88-111, 184-195` |
| Generator | Configuring requires a Linux-built `rexglue` at `sdk/out/linux-amd64/Release/rexglue`, even when the generated tree already exists. The generated tree has no target-specific code (Android compiles the Windows one), but `codegen.d` holds absolute `C:/` paths. | Needs the Linux generator or frozen codegen | `cmake/PinyonShiftRexGlue.cmake:110-131`; `tools/build-android.ps1:55-62` |
| Large code model | `-mcmodel=large -Wl,--no-relax` on Linux x86-64 for the 263-unit, 302 MB translation. The link has never run. | Unproven | `sdk/CMakeLists.txt:117-129`; `sdk/cmake/rexglue_helpers.cmake:47-53` |
| POSIX runtime | Memory (memfd, reserve then fix), guest faults (sigaction, x86-64 and AArch64 register decode), assembly fibers, pthreads, `CLOCK_MONOTONIC_RAW`, XDG paths. Android runs all of it on AArch64; only the x86-64 register decode and the desktop-only branches are new. | Mostly proven by Android | `sdk/src/core/*_posix.cpp`; `sdk/src/core/exception_handler_posix.cpp:89-108` |
| Thread priority | `set_priority` asks for `SCHED_FIFO` with the guest's priority. Without `CAP_SYS_NICE` (normal on a Deck) it warns. A priority of 0 or below is invalid for FIFO, gets EINVAL, and reaches `assert_always`. Android maps priorities to nice values instead. | **Bug** on desktop Linux | `sdk/src/core/threading_posix.cpp:919-945` |
| Window and surface | SDL3 window; Wayland surface first, then X11 through xcb. `GetNativeWindowHandle` returns null off Windows, so `DisplayRefreshRate` has no answer. | Exists; refresh rate missing | `sdk/src/ui/window_sdl.cpp:246-256`; `sdk/src/ui/surface_gnulinux.cpp`; `src/platform/host_platform.cpp:180-191` |
| Fatal errors | `ShowSimpleMessageBox` and `ShowFatalError` only print to stderr, which nobody sees in Game Mode. | Missing | `sdk/src/core/system_posix.cpp:14-31`; `src/platform/host_platform.cpp:160-163` |
| Audio | SDL3 with PipeWire, PulseAudio and ALSA loaded at run time. | Exists; untested | `sdk/thirdparty/CMakeLists.txt:291-302`; `sdk/src/audio/sdl/sdl_audio_driver.cpp` |
| Input | SDL3 gamepads, including SDL's own Steam Deck driver; Steam Input's virtual pad when launched by Steam. Android's pad routes and handheld presets are behind `__ANDROID__`. | Exists; Deck layout and pad routes to do | `sdk/src/input/sdl/sdl_input_driver.cpp`; `src/ui/settings_menu.cpp:18, 300, 385, 512, 567`; `src/pinyon_shift_app.cpp:889` |
| Aspect | Hor+ widens wider windows, and ASPECT RATIO offers letterbox and crop. 16:10 is *narrower* than 16:9, so the Deck gets 1280x720 with bars or a cropped picture. | Works; a full 1280x800 view is new work | `src/ui/settings_menu.cpp:317-330`; `src/pinyon_shift_app.cpp:72, 847-862` |
| Crash reporter | Fatal signals on an alternate stack, with a backtrace. The alternate stack exists only on the thread that installs it. | Exists; per-thread stacks to do | `src/crash_reporter_posix.cpp` |
| Live profile scan | The live-credits memory scan uses `VirtualQuery` and returns nothing off Windows. | Missing | `src/save/live_profile.cpp:50-97` |
| Tooling | Setup, toolchain, SDK preparation, build, shaders, DLC, v4 and CI are PowerShell. `pinyon.py` has `launch` and `android` only and skips shader preparation off Windows. The render-test harness starts `powershell.exe launch-preview.ps1`. | The largest gap | `tools/pinyon.py`; `tools/run-fh1-render-test.py:1736`; `tools/replay-fh1-frame.py:62` |
| Launcher | WPF on .NET 8 (`net8.0-windows`, about 3,500 lines of C#). It calls PowerShell and `explorer.exe`. | Windows-only | `launcher/PinyonShift.Launcher/` |
| CI | No desktop Linux job in this repository (the Android job runs on Ubuntu). The SDK's inherited `build-linux-amd64` workflow runs only on `v*` tags and nightlies from `development`, so the fork's `main` has never been built on Linux. | Missing | `.github/workflows/ci.yml`; `sdk/.github/workflows/_build-platform.yaml` |
| Boundary | The repository policy already refuses `.so`, `.apk` and ELF magic (AP-6.2). | Done | `config/repository-policy.json:22-23, 49` |
| RADV evidence | Issue #388 ran the Windows build under GE-Proton on a Radeon 610M with Mesa RADV 26.2. Vulkan passes through to RADV there, so its results apply to native Linux: green and white artifacts in the intro cutscene that clear once the race starts, and about 15 fps on 2 CUs. | Expect the same artifacts on the Deck | [#388](https://github.com/arcanite24/pinyon-shift/issues/388) |

## Prerequisites from other backlogs

| Prerequisite | Why Linux needs it | State (2026-10-08) |
| --- | --- | --- |
| NP-12.1, NP-12.2 | Presets, the POSIX host layer and the crash reporter | Written; the shared parts run on Android, the desktop parts are unbuilt |
| NP-12.7, NP-D | The Python core for setup, build and launch | `launch` done; the rest is LX-3 |
| NP-12.8, NP-6.3 | Deck qualification and the Steam Input layout | LX-5 and LX-7 take them over |
| AP-0.1, AP-4.4, AP-7.5 | Null GPU runs, pad routes to keyboard-only features, handheld presets | Done on Android; LX-0.3, LX-5.3 and LX-7.1 extend them to Linux |
| LS-0.1, LS-0.2, LS-0.7, LS-1.6, LS-2.1, LS-2.4, LS-2.5 | The low-spec T2 (Steam Deck) measurements and the 40 fps step | Waiting on this backlog; the 40 fps step is done |
| AMD qualification (roadmap), NP-2.4 | The Deck is the project's first AMD GPU | LX-4 results feed both, although Windows AMD drivers differ from RADV |

## Slice map

| ID | Slice | Outcome | Size | Depends on | Train |
| --- | --- | --- | --- | --- | --- |
| LX-0 | First light on x86-64 Linux | The game builds in WSL from the Windows-generated tree and passes the CPU-side routes with the null GPU plugin | M | NP-12.1, NP-12.2 | linux-alpha |
| LX-1 | Pinned, portable toolchain | Pinned LLVM and the sniper sysroot produce one binary that runs unchanged on SteamOS, Ubuntu and Arch | M | LX-0 | linux-alpha |
| LX-2 | First frame on the Deck | The developer loop over SSH; the title screen, then the opening route, on RADV in Desktop Mode and in Game Mode | S-M | LX-0 | linux-alpha |
| LX-3 | Disc to play without PowerShell | `pinyon.py setup`, `build`, `prepare-shaders`, `dlc`, crash bundles and the route runner on Linux | L | LX-1, NP-D | linux-preview |
| LX-4 | RADV and Linux correctness | The route matrix on the Deck with zero skips and matching captures; #388's artifacts fixed; NVIDIA on Linux | M-L | LX-2 | linux-preview |
| LX-5 | The Deck experience | Game Mode shortcut, Steam Input layout, pad routes, 16:10, refresh rate, suspend and resume, visible errors, docked play | M | LX-2 | linux-preview |
| LX-6 | Linux launcher and Windows-to-Deck | A GUI launcher on Linux; Build for Steam Deck on Windows with Wi-Fi delivery | L | LX-3 | linux-1.x |
| LX-7 | Deck performance and battery | A measured budget; DECK 60, BALANCED 40 and QUALITY 30 presets held for 20 minutes on battery | L (open-ended) | LX-4 | linux-preview |
| LX-8 | Qualification, CI and documentation | Linux CI, the Deck route gate before releases, `docs/LINUX.md`, the Linux launcher release, the distribution matrix | M, ongoing | LX-1 | linux-1.x |

Total: **XL**, NP-12's size. The Android port went from its first build to
the race on a device in under a week because nearly everything it fixed was
shared POSIX code, and Linux inherits that. So LX-0 to LX-2 should be short.
The long poles are the PowerShell-free tooling (LX-3, LX-6) and the
open-ended performance work (LX-7).

## Working order

**First vertical slice: LX-0, then LX-2.1 and LX-2.2 straight away.** The
riskiest unknowns are the first desktop Linux link (the large code model
over 302 MB of generated C++, the x86-64 fault decode, the `SCHED_FIFO`
assert) and how RADV renders the executor. WSL answers the first within a
day of build time. A WSL build (glibc 2.39) runs as-is on SteamOS (glibc
2.41), so the Deck can show the second before the pinned toolchain exists.

Then, in order:

1. **LX-0** entire. The null-GPU routes prove the CPU side.
2. **LX-2.1 to LX-2.2**: the developer loop and the title screen on the
   Deck, with the capability report (LX-4.1) in the same run.
3. **LX-1** in parallel with LX-2. Once it lands, every Deck build comes from
   the pinned toolchain, and the CI job (LX-8.1) follows at once.
4. **LX-4.2 and LX-7.0** next, so LX-5 and LX-7 are planned on measured
   numbers rather than this document's guesses.
5. **LX-3**: a Linux PC or Deck user goes from disc to play from a checkout.
   This is the first player-facing deliverable.
6. **LX-5**, then **LX-7**'s presets, then **LX-6**.
7. **LX-8** throughout.

## Needs a person or hardware

| Item | What is left | Needs |
| --- | --- | --- |
| D1 to D6 | Confirming the decisions, above all the launcher technology (D4) and whether Windows-to-Deck delivery belongs in the first Linux preview (D3c) | The maintainer |
| LX-4.6 | The route matrix on NVIDIA's Linux driver | A desktop booted into Linux with an NVIDIA GPU (WSL has no native Vulkan) |
| LX-4.7 | Mesa desktops beyond the Deck: RADV on a discrete AMD card, ANV on Intel | That hardware, or a tester with it |
| LX-5.2, LX-5.6 | Judging the controls layout and how play feels after suspend | A player with the Deck; the route runner cannot judge feel |
| LX-7.4 | Battery runs | The Deck unplugged and left alone for each 20-minute run |
| Legal | A Linux binary is a locally linked preview executable, as the Windows one is ([LEGAL.md](LEGAL.md)); Windows-to-Deck delivery moves it between the player's own machines, as Android delivery does | The maintainer, to confirm |

## LX-0 First light on x86-64 Linux

**Why first.** Every later slice assumes the game builds and runs correctly
as an x86-64 ELF. The GPU is not needed: the null plugin (AP-0.1) runs the
CPU-side routes, and WSL has 16 threads and 62 GB for the build.

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-0.1 | **Linux generator and configure.** Build `rexglue` with the SDK's `linux-amd64` preset in WSL. Copy `.local/generated` onto WSL's ext4 filesystem rather than reading it through `/mnt/c`. Configure with `PINYON_SHIFT_FROZEN_CODEGEN=ON`, which leaves the Windows paths in `codegen.d` unused. Decide whether frozen codegen should skip the generator check at `PinyonShiftRexGlue.cmake:127-131`, as the Windows-to-Deck cross-build (LX-6.3) will need. | `cmake --preset linux-amd64-release` configures against the Windows-generated tree | S |
| LX-0.2 | **Compile and link.** Fix what breaks in the code only desktop Linux compiles: x86-64 register handling in the fault handler, `surface_gnulinux.cpp`, robust mutexes, `timer_create` with `SIGEV_THREAD_ID`, the large code model link (relocation overflows, link time, lld), and the host sources. | `pinyon_shift`, `librexgpu-fh1.so` and the facade modules link; `pinyon_shift_host_tests` pass | M |
| LX-0.3 | **Null-GPU route parity.** Run `fh1-opening-sync`, `fh1-buy-car`, `fh1-race-sync`, `fh1-free-roam`, `fh1-pause` and `fh1-timing-straight` with `--gpu_backend=null`, through LX-3.7's runner or a temporary direct one. The bar is AP-0.5's: simulation-time ratios within Windows' spread, and the vehicle state at `event-ready` equal to three decimals. | Six routes pass in three consecutive runs; save hashes compared once a deterministic route exists (AP-0.5, still open) | M |
| LX-0.4 | **Thread priorities.** Use Android's nice mapping on all of Linux, and keep real-time policies for processes that are allowed them (`RLIMIT_RTPRIO` or `CAP_SYS_NICE`). Never assert on EINVAL, and log the downgrade once. Raising priority (a negative nice) also needs `RLIMIT_NICE`, so measure what an unprivileged Deck process actually gets. | No assert or warning flood in a full route; what each thread got is logged; the pacing effect is measured in LX-7.3 | S |
| LX-0.5 | **Crash reporter and faults.** Give every guest and host thread its own alternate signal stack. Check x86-64 program-counter extraction with the crash self-test. The routes exercise guest MMIO faults on x86-64 Linux. | A forced crash writes a report with a symbolized backtrace; routes have no unexpected faults | S |
| LX-0.6 | **Building on the Deck: measurement only.** Compile the same tree on the Deck with LX-1's toolchain, or inside a distrobox until it exists, at `-j4` and `-j8`. Record wall time, peak memory per unit and swap use. The result decides whether D3b is offered or only allowed. | A time and a recommended job count in this document | S |

**Gates.** The Linux build links from the Windows-generated tree, the host
tests pass, and six null-GPU routes pass three times with Windows-equal
simulation ratios.

## LX-1 Pinned, portable toolchain

**Why.** A binary built with WSL's compiler carries Ubuntu 24.04's glibc and
libstdc++ requirements and depends on whatever the build host had installed.
Players need one reproducible recipe that gives the same binary everywhere.

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-1.1 | **Sysroot audit.** Pin a sniper SDK sysroot by version and SHA-256 from `repo.steampowered.com/steamrt3/images/` (`com.valvesoftware.SteamRuntime.Sdk-amd64,i386-sniper-sysroot.tar.gz`, about 1.1 GiB). **Guess:** it contains GCC 14's libstdc++ headers and `libstdc++.a`, plus the X11, xcb, xkbcommon, Wayland, libdecor, PulseAudio, PipeWire, ALSA, D-Bus and udev headers that SDL3 needs. List any gaps. Missing headers go into a small supplement archive built from the same Debian sources; the fallback is the sniper SDK container under podman. | A gap list, and a decision on whether a supplement is needed | S |
| LX-1.2 | **Toolchain file.** Write `cmake/toolchains/linux-x86_64-sniper.cmake`: clang 20.1.8 with `--target=x86_64-linux-gnu --sysroot=...`, lld, GCC 14's install directory, `-static-libstdc++ -static-libgcc`, pkg-config confined to the sysroot (or explicit paths, with no pkg-config at all, for Windows hosts), and `$ORIGIN` RPATH. The `linux-amd64-*` presets use it, and the Linux-host-only condition goes so that Windows can cross-build (LX-6.3). | The LX-0 build reproduces with the pinned toolchain and the same routes pass | M |
| LX-1.3 | **Pinned downloads.** Add Linux entries to `config/release-toolchain.json`: `LLVM-20.1.8-Linux-X64.tar.xz`, the sysroot, Linux builds of CMake and Ninja, python-build-standalone 3.13 (for `pinyon.py` and the launcher, so the system Python is never relied on), and an ISO extractor (LX-3.1). Downloads are hash-checked and reused as on Windows. | A clean Ubuntu container provisions everything without root or packages | S |
| LX-1.4 | **Host tools.** SDL3's Wayland backend runs `wayland-scanner` at build time (`sdk/thirdparty/sdl3/cmake/sdlchecks.cmake:657-670`). Pre-generate its protocol sources into ShiftGlue with a regeneration script, so no build host, including Windows, needs the scanner. | SDL3 builds with Wayland from the pinned toolchain alone | S |
| LX-1.5 | **Portability audit.** Check with `readelf` that `GLIBC_` symbol versions stay at or below 2.31 and that `NEEDED` lists only libc, libm, libdl, libpthread, librt and the loader. SDL loads everything else at run time. There must be no `libstdc++.so` and no absolute RUNPATH. Run the same binary on SteamOS, Ubuntu 24.04 and an Arch container. | The audit is a CI step (LX-8.1); the null-GPU route passes on all three | S |
| LX-1.6 | **Provenance.** `pinyon_shift_build.json` beside the binary records the toolchain, sysroot, ShiftGlue revision and generated-tree hash, as the APK does (AP-6.4). | Crash reports and `doctor` show it | S |

**Gates.** A clean Linux host builds the game with only the pinned
downloads; the ELF audit passes; the same binary passes the null-GPU route
on SteamOS, Ubuntu and Arch.

## LX-2 First frame on the Deck

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-2.1 | **Deck developer loop.** `pinyon.py deck doctor`, `install`, `push-data`, `run`, `stop` and `pull-logs` work over SSH with the devkit key, mirroring `pinyon.py android`. `install` copies the build with rsync; `push-data` copies the game folder once (6.9 GB over Wi-Fi). `run --route FILE --seed DIR --wait` uses a private state root under `~/pinyon-qual/<name>`, never `~/.local/share/PinyonShift`. | A route started on the PC runs on the Deck, and its logs and captures come back | M |
| LX-2.2 | **Desktop Mode first frame.** The title screen on RADV under KDE (both its X11 and Wayland sessions). The Vulkan capability report (AP-2.0's `VULKAN_CAPABILITY_REPORT`) is saved as `docs/linux/capability-steamdeck-lcd.json`. | The title screen renders; the report is committed | S |
| LX-2.3 | **Game Mode first frame.** Register a shortcut with devkit-utils' `steam-client-create-shortcut` and start it from Game Mode. Check gamescope focus, the 1280x800 output, which window system SDL picks under gamescope, and the present mode. | The opening drive plays from Game Mode with the built-in controls | S |
| LX-2.4 | **Headless route runs.** Run scripted routes inside `gamescope --backend headless`, or a nested gamescope, so qualification does not take over the screen. Confirm that captures come out on RADV. | `fh1-free-roam` passes headless with its three captures | S-M |

**Gates.** The title screen and the opening route render on the Deck from a
build the PC sent over; a route runs from the PC and returns its results.

## LX-3 Disc to play without PowerShell

**Why.** A Linux-only player has no PowerShell. Every setup stage needs a
Python equivalent, and these become NP-D's shared core.

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-3.1 | **`pinyon.py setup --iso`.** Check the size and SHA-256 against `config/supported-dumps.json`, then extract the disc, with the same read-only ISO, resumability and `.local` layout as `setup-preview.ps1`. The extractor is either a Python XDVDFS reader or the pinned extract-xiso built for Linux. | A Linux setup's extracted tree matches the Windows one file for file | M |
| LX-3.2 | **`pinyon.py build`.** Provision the toolchain (LX-1.3), prepare ShiftGlue (submodule or pinned clone), build the generator, run codegen, configure and build. The job count follows available memory (LX-0.6), so the Deck neither swaps to a crawl nor runs out of memory. | Disc to a built binary on Ubuntu and on the Deck with no other steps | M |
| LX-3.3 | **Shader preparation.** Do the private startup run that fills Vulkan shader storage before the first launch, which `pinyon.py launch` skips off Windows today. Key the stored artifacts on the Vulkan device UUID (NP-12.7). | The first launch translates nothing the preparation run covered | S-M |
| LX-3.4 | **DLC and title update.** Python equivalents of `manage-dlc.ps1`, `manage-title-update.ps1` and `build-v4.ps1`: import and verify packages, prepare the Rally cache, and verify, install and build v4. | The car packs and the Rally entry check (`fh1-rally-entry-assets`) pass on Linux | M |
| LX-3.5 | **Crash bundles.** A Linux version of `create-crash-report.ps1`: a sanitized ZIP and a prefilled issue link, with nothing of the game, saves or local paths. | A forced crash produces a bundle that passes the sanitizer tests | S |
| LX-3.6 | **State and paths.** State lives under `$XDG_DATA_HOME/PinyonShift`. Support portable installs and installs on the Deck's microSD card (`/run/media/...`), and confirm the case-insensitive lookups on ext4. | Play from internal storage and from the card | S |
| LX-3.7 | **Route harness without PowerShell.** `run-fh1-render-test.py` and `replay-fh1-frame.py` start the game through `pinyon.py launch` on every OS. | Windows routes unchanged; the same routes run on Linux | S |
| LX-3.8 | **Bring a Windows save.** Import the PC's preview state on Linux or the Deck, following Android's migration (`android migrate`). | A Windows save loads on the Deck with its progress | S |

**Gates.** On a clean Ubuntu 24.04 machine and on the Deck, a player goes
from their ISO to the title screen with documented `pinyon.py` commands
only; DLC and v4 work; a crash produces a bundle.

## LX-4 RADV and Linux correctness

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-4.1 | **Capability report and formats.** Probe D24S8 and every format the renderer uses without a query (the AP-2.0 list). Use the D32S8 depth path Android already has where D24S8 is missing. | The report lists nothing the renderer cannot handle | S |
| LX-4.2 | **Route matrix on the Deck.** Opening, free roam, race, buy-car, pause, settings and the scale switch at 1x on Vulkan, with zero executor skips. Compare captures with the Windows goldens, using a cross-vendor tolerance set the way NP-12.4 set D3D12 against Vulkan. | All routes pass three times; captures within tolerance | M |
| LX-4.3 | **#388's artifacts.** The green and white artifacts in the intro cutscene. Reproduce them on the Deck, record a frame dump, replay it on Windows and NVIDIA, and narrow it with `fh1_debug_skip_draws` and `fh1_debug_null_fetch` (NP-12.4's method). | No artifacts in the cutscene; the fix keeps the Windows replays byte-identical | M |
| LX-4.4 | **Frame replays.** The four goldens replay on RADV. | Within the cross-vendor tolerance | S |
| LX-4.5 | **Soak.** `fh1-long-drive` for an hour on the Deck. | No hang or device loss; ratio within bounds | S |
| LX-4.6 | **NVIDIA's Linux driver.** The route matrix on a desktop booted into Linux. | As LX-4.2 | M |
| LX-4.7 | **Other Mesa drivers.** RADV on a discrete card and ANV on Intel. | As LX-4.2, or a filed list of differences | S |

**Gates.** The route matrix and the replays pass on the Deck with zero skips;
#388's artifacts are gone; an hour-long soak is clean.

## LX-5 The Deck experience

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-5.1 | **Built-in controls.** Under Steam, the game must read only Steam Input's virtual pad, not the raw Deck device as well, which would double the input (SDL follows Steam's ignore list; verify). Without Steam (Desktop Mode, a terminal), SDL's Steam Deck driver takes over. Check rumble. | One pad, correct buttons and rumble in both modes | S |
| LX-5.2 | **Default Steam Input layout.** A gamepad layout with the back buttons (L4, R4, L5, R5) mapped to SETTINGS, photo and trainer, exported with `steamos-dump-controller-config` and applied by the shortcut (NP-6.3's Deck layout). | A fresh shortcut gets the layout | S-M |
| LX-5.3 | **Pad routes everywhere.** Take AP-4.4's SETTINGS, TRAINER and SAVE PHOTO rows out from behind `__ANDROID__` for every handheld, and add a pad chord to open SETTINGS from anywhere (#388's Guide-button request; Steam reserves the Steam button). | Every keyboard-only feature is reachable with the built-in controls | S |
| LX-5.4 | **16:10.** Letterboxed 1280x720 is the safe default. A full 1280x800 view needs vertical field-of-view widening ("Vert+"), the counterpart of NP-4.4's Hor+, with the HUD and cinematics checked. | The default fills 1280x720 cleanly; Vert+ is shipped or ruled out with reasons | M |
| LX-5.5 | **Refresh rate.** Read it from SDL's display mode, replacing the null native handle path, so frame-rate defaults follow the panel (60 Hz LCD, 90 Hz OLED). Document how the game's cap interacts with gamescope's frame limiter and the refresh slider (40-60 Hz on the LCD). | The FPS menu defaults to the panel rate; no doubled limiter judder | S |
| LX-5.6 | **Suspend and resume.** Sleep with the power button during a race and in menus. The Vulkan device survives, PipeWire audio comes back, there is no catch-up burst (PB-4.2's capped delta), and pacing recovers. | Ten cycles in one session without a fault | S-M |
| LX-5.7 | **Visible errors.** Show fatal errors in an SDL message box, or, if gamescope does not display it, on a screen drawn by the presenter. Game Mode has no terminal. | A missing-game-data start shows a readable message in Game Mode | S |
| LX-5.8 | **Docked play.** An external display at 1080p and 4K through gamescope. Higher scales are gated on memory (a 3 GiB device-local heap plus shared memory). | 1x and 2x on a 1080p display; memory logged | S |
| LX-5.9 | **Text entry.** Find where the game or host UI asks for text, and confirm that Steam's on-screen keyboard reaches it. | Every text field can be filled without a keyboard, or there is none | S |
| LX-5.10 | **Shortcut and artwork.** Add to Steam: write the non-Steam entry (name, start script, working directory) and the project's own grid, hero, logo and icon art, never *Forza Horizon*'s, then restart Steam or use `steam://addnonsteamgame`. | The game appears in the library with art and starts from Game Mode | S |

**Gates.** From Game Mode, a player starts the game, plays a race with the
built-in controls, opens every host feature without a keyboard, suspends and
resumes, and quits back to Steam; nothing needed Desktop Mode after setup.

## LX-6 Linux launcher and Windows-to-Deck

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-6.1 | **Choose the GUI (D4).** The proposal is an Avalonia port of the WPF views over the shared C# services, with the PowerShell calls replaced by the `pinyon.py` core. The alternative is an SDL3 and ImGui launcher that shares the host UI's style. | A decision recorded here | S |
| LX-6.2 | **Linux launcher.** Pick or drop an ISO, verify and build (LX-3), Play, Settings, the DLC panel, Report a problem, Add to Steam. Ship it as a self-contained `linux-x64` archive. | Disc to play on the Deck in Desktop Mode without a terminal | L |
| LX-6.3 | **Build for Steam Deck on Windows.** Cross-compile with the pinned toolchain (LX-1.2 without the host condition) from the PC's generated tree. This step only compiles, with no extraction or codegen. It relies on the pre-generated Wayland protocols (LX-1.4) and on not needing pkg-config. | A Windows-built binary passes LX-4.2 on the Deck | M |
| LX-6.4 | **Wi-Fi delivery.** Reuse the Android share's pairing (`AndroidShare.cs`, six-digit code). The Linux launcher on the Deck receives the build, the game data, the DLC and, optionally, the save. | Delivered from the PC and playable without SSH or USB | M |
| LX-6.5 | **Updates.** Resend only the files that changed, usually the binary and its modules, using a manifest. | A rebuild reaches the Deck in seconds, not a 7 GB copy | S |

## LX-7 Deck performance and battery

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-7.0 | **First measurement.** Race and free roam at 1x: frame median and p95, GPU time (`fh1_native_gpu_profile`), recorder and decoder busy time, CPU and GPU clocks, package power (hwmon, gamescope stats or a MangoHud log) and temperatures. This is the low-spec backlog's LS-0.2 for T2. | Numbers in this document; targets for LX-7.1 set | S |
| LX-7.1 | **Deck presets.** Start from Low-spec 60 and Android's handheld presets (single pass, quarter-rate reflections, no MSAA). Proposed: DECK 60, BALANCED 40 (LS-1.6's step; the LCD runs at 40 Hz) and QUALITY 30. Lift the `__ANDROID__` guard so Linux handhelds get them. | Each preset holds its rate cold in the race | M |
| LX-7.2 | **Fast pixel math on RADV.** Compare GPU time with and without `spirv_fast_pixel_math` and #403's NaN check. | Kept on the Deck only if it saves time without the #403 smear | S |
| LX-7.3 | **Waits, threads and power sharing.** Measure LS-2.1's POSIX sleeps, LS-2.4's thread placement on 4 cores and 8 threads, LX-0.4's priorities, and LS-2.5's question: does less CPU work buy GPU clock under the shared power limit? | Kept where measured faster | S-M |
| LX-7.4 | **Sustained and battery.** 20 minutes of `fh1-long-drive` on battery at each preset, recording the frame rate over time, battery drain per hour and temperatures, plus a sweep of Steam's TDP limit. | A preset that holds its rate for 20 minutes; battery hours published | M |
| LX-7.5 | **First session.** Shader preparation time and hitches with empty caches (LS-0.7), the size of RADV's disk cache, and Vulkan packs keyed on the Deck's device. | Hitches counted and preparation timed | S-M |
| LX-7.6 | **Memory.** Heap use against `VK_EXT_memory_budget`, texture cache limits for 16 GB shared, and whether the BIOS framebuffer size setting matters. | No eviction churn at 1x | S |

## LX-8 Qualification, CI and documentation

| Item | Work | Acceptance | Size |
| --- | --- | --- | --- |
| LX-8.1 | **Linux CI job.** Build the runtime, `rexgpu-fh1` and the host tests with the pinned toolchain and sysroot, with no game files. Run the host tests and the ELF audit (LX-1.5). | Green on `dev` | S |
| LX-8.2 | **ShiftGlue CI.** Build `linux-amd64` on pushes to the fork's `main`; the inherited workflow builds only tags and `development`. | Green on `main` | S |
| LX-8.3 | **Release gate on the Deck.** Run LX-4.2's matrix from the PC before every release, as the Android devices' runs are. | Listed in the release checklist | S |
| LX-8.4 | **Documentation.** Write `docs/LINUX.md` covering Linux PCs and the Deck: requirements, setup, Add to Steam, controls, presets and troubleshooting. Add a Linux section to BUILDING.md, update the README's requirements and roadmap, and add release notes. | Reviewed by the maintainer | S |
| LX-8.5 | **Release packaging.** CI builds `PinyonShift-Launcher-linux-x86_64.tar.gz` at release time, and the boundary checks cover it. | It contains nothing generated or derived from the disc | S |
| LX-8.6 | **Distribution matrix.** SteamOS stable and beta, Ubuntu 24.04, Fedora, Arch and Bazzite; X11 and Wayland sessions; NVIDIA; and running under the sniper runtime as a compatibility tool (D2). | A support table in `docs/LINUX.md` | S, ongoing |
