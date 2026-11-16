# Linux on ARM64: AYN handhelds on Armada OS

Research for a native `linux-arm64` build of Pinyon Shift, aimed at ARM
handhelds that run a desktop Linux distribution instead of Android. The
reference target is the AYN Odin 2 Portal (SM8550, Adreno 740) running
Armada OS, which is the device the Android work was tuned on
([ANDROID_ODIN_BACKLOG.md](ANDROID_ODIN_BACKLOG.md)).

Status: research only (2026-11-16). Nothing here is built or scheduled.
[LINUX_PORT_BACKLOG.md](LINUX_PORT_BACKLOG.md) lists Linux on ARM64 as a
non-goal; this page is what reopening it would take.

## Summary

- Most of the work is already done. The SDK builds `linux-arm64` in its
  own CI (green on v0.10.1, 2026-11-06), the AArch64 code paths written
  for Android and macOS are keyed on the architecture, not on Android,
  and the Linux platform layer (SDL3, Wayland/X11, PipeWire, memfd guest
  memory, huge-page code) does not care about the CPU.
- What is missing is plumbing: a game preset, a cross toolchain, the
  setup and launcher gates, a prebuilt kit and CI.
- One real porting decision: about a dozen GPU defaults that make the
  Odin fast on Android are gated on `__ANDROID__`. On Linux the same
  Adreno 740 would get the desktop defaults. They need to move to a
  "mobile GPU" predicate keyed on the Vulkan driver or vendor.
- The GPU driver is the same family as on Android. The Odin's recommended
  Android setup is already Mesa Turnip, and the Turnip-specific shader
  work (implicit LOD, sparse shared memory) is keyed on the driver ID, so
  it carries over. The kernel side differs: upstream `msm` DRM instead of
  Qualcomm's KGSL.
- Expected gain over the Android build: the Linux-only CPU work (native
  scene culling, single-pass scene, huge-page code; 2.5-3 ms CPU on the
  Deck) and no Android shell. Unmeasured on ARM.
- Rough size: two to three focused sessions to a booting, playable build
  from the PC (LA-1 to LA-3), one more for the player path (LA-4). The
  first step needs Armada on the Odin, booted from a microSD card with
  Android kept as the main system (see [Decisions](#decisions)).

## Armada OS

What it is, from its own pages and release notes (sources at the end):

| | |
|---|---|
| Base | Fedora bootc: image-based, read-only root, updated over the air; device support (kernel, device trees) derived from ROCKNIX |
| Session | Steam Game Mode on gamescope 3.17, KDE Plasma 6.8 desktop mode |
| Graphics | Mesa 26.2.6 (Turnip on Adreno) in build 20261109 |
| Input | InputPlumber 0.83; the Steam client sees a Deck-style controller with gyro |
| Steam | Native arm64 Steam client; x86 games through FEX with Vulkan/GL thunks to the native drivers; CachyOS Proton 11 for Windows games |
| Devices | AYN Odin 2, Odin 2 Mini, Odin 2 Portal, Odin 3, Odin 3 Portal, Thor; Retroid, AYANEO, KONKR and others (25+) |
| Install | Flashed to a microSD card; needs the device's ABL bootloader backed up and replaced (OpenABL since 20261109) from Android. Install to internal storage optional. The project warns this can brick a device. |
| Not published | Kernel version, page size, glibc version. Check on the device. |

Xbox 360 emulation there today is Xenia Edge's x86-64 AppImage under FEX.
A native build avoids translating both the recompiled game and the
runtime, which is the point of the port.

Other distributions on the same hardware: ROCKNIX (the upstream for
Armada's device support) and Armbian. Upstream kernel support for the
SM8550 AYN devices is in `drm-misc-next` (Odin 2 Mini, Portal, Thor; the
base Odin 2 not yet verified), so stock distributions are not there yet.
One Armbian report has Turnip crashing on the base Odin 2 with newer
kernels and Mesa 26.0.5; treat Turnip regressions per kernel as a risk.

## What the code already has

### SDK and runtime

- `thirdparty/shiftglue-sdk/CMakeLists.txt` maps Linux plus aarch64 to
  `REX_PLATFORM=linux-arm64`; the SDK has `linux-arm64` presets and a
  `build-linux-aarch64.yaml` workflow on `ubuntu-24.04-arm` with clang 20.
- Guest SIMD goes through SIMDe with NEON branches keyed on `__aarch64__`;
  native NEON paths in memory, XMA, audio conversion, the command and
  primitive processors are keyed the same way.
- Memory-ordering fences for `sync`/`lwsync`/`eieio`/`isync` are emitted
  on every AArch64 target ([platforms.md](../site/pages/platforms.md)).
- Guest memory on Linux is memfd with `MAP_FIXED_NOREPLACE`; statically
  recompiled code needs no JIT, so there is no W^X question.
- The POSIX exception handler walks `_aarch64_ctx` records generically;
  the crash reporter already has a `__linux__ && __aarch64__` path.

### Game repo

- `tools/pinyon.py` and `tools/pinyon_common.py` already map an aarch64
  host to `linux-arm64-<config>` (tested in `tools/tests/test_pinyon.py`).
- Linux-only defaults that a `linux-arm64` build inherits as is: native
  scene culling and UI update (`LINUX && !ANDROID`), the single-pass
  scene (`__linux__`), huge-page code (`LINUX && !ANDROID`).

### LA-1: first build (2026-11-16)

`linux-arm64-release` (base game) cross-built in WSL on multivac with
`cmake/toolchains/linux-aarch64-steamrt4.cmake`: the pinned LLVM 20.1.8,
the steamrt4 arm64 SDK sysroot (4.0.20261110.268882, glibc 2.41,
GCC 14), and the x86-64 toolchain's `ld.lld` and `wayland-scanner`
wrappers. Generated code is the same as for x86-64 (190 files, 6:48 to
generate). The build compiled without source changes in 9:44 (16
threads, 61 CPU minutes).

On the Odin under Armada desktop mode (KDE Wayland; `WAYLAND_DISPLAY`
is `wayland-1` there), every library resolved, the runtime picked
Turnip Adreno 740 over llvmpipe, and the opening video played at
59-60 fps on the internal screen with no errors in the runtime log.
Huge-page code was refused (`MADV_COLLAPSE` returns `EINVAL` on this
kernel), so code runs on 4 KiB pages.

Not done yet: the generator was built by hand against the sniper
sysroot (setup does this with the same flags), the build was copied
over SSH by hand, and nothing past the opening video was checked.

## Gaps

| Area | Today | Needed |
|---|---|---|
| Presets | `linux-base` hardcodes the x86-64 sniper toolchain, `-msse4.1` and the x86 code model | `linux-arm64-base` plus release/v4 presets; `-march=armv8.2-a` (LSE atomics, as Android: SM8550's cores are ARMv9) |
| Toolchain | `cmake/toolchains/linux-x86_64-sniper.cmake` only | `linux-aarch64-steamrt4.cmake`: same pinned LLVM 20.1.8, target `aarch64-linux-gnu`, a pinned arm64 sysroot |
| Sysroot | Steam Runtime 3 "sniper" amd64 SDK (glibc 2.31) | Valve publishes a Steam Runtime 4 **arm64** SDK sysroot (`com.valvesoftware.SteamRuntime.Sdk-arm64-steamrt4-sysroot.tar.gz`, 740 MiB, build 4.0.20261110). No public sniper arm64 SDK was found. steamrt4 is Debian 13 based, so the glibc floor rises to about 2.41, which current Fedora (Armada), ROCKNIX and Ubuntu 25.04+ meet. |
| Release toolchain | `config/release-toolchain.json` has `posix.linux-x86_64` only | `posix.linux-aarch64`: LLVM `Linux-ARM64` for on-device builds, LLVM Windows/x64 for cross builds, steamrt4 arm64 sysroot, python-build-standalone aarch64 |
| Setup | `tools/pinyon_setup.py` `host_platform()` rejects Linux on anything but x86_64; kit flags only for `linux-x86_64` | Accept aarch64; kit flags (`-march`, page-size option) |
| Prebuilt kit | `tools/build-prebuilt.py` repacks LLVM and the sysroot only for `linux-x86_64`; `release.yml` builds Linux on `ubuntu-latest` | A `prebuilt-linux-arm64` job on `ubuntu-24.04-arm` |
| Launcher | `tools/package-launcher.py` packages `linux-x64`, `osx-arm64`, `osx-x64` | Add the `linux-arm64` .NET RID (Avalonia supports it) |
| Page size | `PINYON_SHIFT_PHYSICAL_HEAP_4K_PAGES` defaults ON for Linux, and such a build refuses to start on a 16 KiB kernel | Read `getconf PAGESIZE` on Armada first. Qualcomm handheld kernels are usually 4 KiB; if any target is 16 KiB, ship the run-time offset build for arm64 |
| GPU defaults | See the next section | A mobile-GPU predicate |
| CI | Game CI builds Windows and Android only | A `linux-arm64-release` compile on `ubuntu-24.04-arm` (no GPU: build plus host tests, a null-plugin boot if cheap) |
| Docs | Linux ARM64 a non-goal | `docs/LINUX.md` section, `site/pages/platforms.md`, `site/features.toml` once it runs |

### GPU defaults gated on Android

Keyed on the driver or vendor already (carry over to Linux Turnip):
`spirv_implicit_lod_2d_turnip`, Turnip sparse shared memory, push
descriptors disabled on Qualcomm and Intel Mesa.

Keyed on `REX_PLATFORM_ANDROID` / `__ANDROID__` (lost on Linux):

- shader translator: `vulkan_bindless_textures`, `spirv_ieee_vertex_math`,
  `spirv_fast_pixel_math`, `spirv_specialize_texture_signs`,
  `vulkan_shared_memory_texel_buffer`;
- pipelines: `vulkan_async_pipeline_wait_ms`, prewarm threads, async
  pipeline settings;
- textures: preallocation, the resolution-scale cap;
- device: the geometry-shader requirement, FFX upscaler availability;
- game: env-map rate and shadow defaults
  (`src/native_renderer/graphics_hooks.cpp`), Mali coarse shading
  (`src/pinyon_shift_app.cpp`, Android and ARM vendor);
- the handheld graphics presets (ULTRA LOW 30, QUALITY 30, SMOOTH 60) in
  `settings_menu.cpp`; the GPU DRIVER setting and bundled Turnip are
  Android-only and stay so (on Linux Mesa comes from the distribution).

The right split is per item: some are Android-the-OS (surface handling,
driver loading), most are tile-based-mobile-GPU (Adreno, Mali). The
proposal is one SDK helper, for example `IsMobileGpu()` true for Qualcomm
and ARM vendor IDs or the Turnip/Qualcomm/ARM driver IDs, replacing the
platform check wherever the reason was the GPU. Handheld presets then
show when the GPU is mobile, on any OS. Decide each item by an in-run A/B
on the device, toggling the cvar inside one route as on Android
([ANDROID_60FPS_BACKLOG.md](ANDROID_60FPS_BACKLOG.md) has the method).

## Building for the device

Players build the game from their own disc on their own machine
([LINUX.md](LINUX.md)). Two ways to get there on an ARM handheld:

1. **On the device.** Armada's root is read-only like SteamOS, but setup
   already brings its own LLVM and sysroot, so nothing needs installing.
   The cost is time and memory: a fresh setup took 14:41 to the
   executable on the main Windows desktop (2026-10-27), and the Odin has one Cortex-X3 and seven smaller cores with
   8-16 GB (8 GB on the reference unit). Expect an hour or more and watch for memory pressure with
   parallel jobs. The prebuilt host-object kits (TP-*) cut most of it.
2. **Cross from the PC.** The x86-64 toolchain file already supports a
   Windows host; the arm64 one would too. This is the developer loop:
   build on multivac, deploy over SSH the way `pinyon.py deck install`
   does. It is also a reasonable player option for anyone with a PC.

## Plan

| Item | What | Done when |
|---|---|---|
| LA-0 | Device facts on Armada: `uname -r`, `getconf PAGESIZE`, glibc, `vulkaninfo` (driver ID, Mesa version, features the SDK requires: geometry shader, fragment shader interlock, sparse), SSH key login, gamescope and Steam shortcut behaviour, InputPlumber controller as SDL sees it, PipeWire | A short facts table in this file |
| LA-1 | `linux-arm64-*` presets, `linux-aarch64-steamrt4.cmake`, release-toolchain entry, cross build from multivac | A `pinyon_shift` binary and `librexruntime.so` for aarch64; host tests pass on `ubuntu-24.04-arm` |
| LA-2 | Boot on the Odin: deploy over SSH, run under gamescope, controls, audio, save in a private state root | Opening drive and free roam reach the same save hashes as Windows (the AP-0 gate) |
| LA-3 | Mobile-GPU predicate in the SDK; handheld presets on Linux; in-run A/B of each moved default | Each Android-gated default decided on Linux by measurement; frame times recorded against the Android build on the same route |
| LA-4 | Player path: setup accepts aarch64, prebuilt arm64 kit in `release.yml`, `linux-arm64` launcher package, Steam shortcut from the launcher | A clean Armada install goes from disc to Game Mode with the launcher alone |
| LA-5 | Docs and CI: `LINUX.md` section, platforms page and feature list, game CI compile job | Site builds, CI green |

Measure LA-3 as on Android: same route, same 1x/4x settings, last ~800
`perf.csv` rows, GPU clock read from the `msm` devfreq node (the KGSL
paths used on Android do not exist on upstream kernels).

## Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Installing Armada | ABL replacement can brick the device; the Odin holds the player's real Android save | Back up `files/state` first (as in the Odin notes); boot from SD so Android stays; maintainer's call |
| Turnip and kernel regressions | Community kernel and Mesa move monthly; one report of Turnip crashing with newer kernels on the base Odin 2 | Record kernel and Mesa versions with every result; validation layer runs as on Android |
| Missing Vulkan features on upstream `msm` | The Android build already copes with Turnip, but the desktop path assumes desktop features | LA-0's `vulkaninfo` before any code |
| 16 KiB pages | A 4 KiB-only build refuses to start | LA-0 checks; run-time offset fallback |
| Thermals and power | gamescope and Steam's performance sliders replace Android's governor; Steam over SSH skipped the game power profile on the Deck | Launch measurements from Steam, read clocks before trusting numbers |
| Audience | Armada is a preview distribution; few players run Linux on these devices today | Keep it a developer-supported target until LA-4 passes on a clean install |

## Decisions

- 2026-11-16: the maintainer installs Armada on the Odin 2 Portal from a
  microSD card. Android stays the device's main system and keeps the
  player's save; Armada is the secondary boot for this work. The Android
  save (`files/state/user`, `user-modded`, `config`, `photos`) was copied
  to the PC save archive beforehand and checked by md5 (57 files).
- Open: whether `linux-arm64` becomes a supported player target or stays
  a developer build.

## The reference device

Known from Android (2026-11-16): Odin 2 Portal base model, SM8550
(`kalama`), 7.0 GiB usable RAM, Android 13 with a 4 KiB page kernel,
internal storage 97 % full. With 8 GB, building on the device is the
slow path; cross builds from the PC are the developer loop.

### LA-0: Armada on the device (2026-11-16)

Armada 20261109 from a microSD card (OpenABL in both ABL slots; the
stock ABL is backed up off the device). Read over SSH as user `armada`:

| | |
|---|---|
| OS | Armada 20261109.dfed5d6, Fedora 44 base, composefs read-only root, `/var` on btrfs on the card (444 GB free) |
| Kernel | 7.2.6, **4 KiB pages**, THP `madvise`; device tree model "AYN Odin 2 Portal" |
| libc | glibc 2.43 (above the steamrt4 floor) |
| CPU | 1x Cortex-X3 2.96 GHz, 2x A715 + 2x A710 2.80 GHz, 3x A510 2.02 GHz; 7 GiB RAM |
| GPU | Turnip Adreno 740, Mesa 26.2.6, Vulkan 1.4, `DRIVER_ID_MESA_TURNIP`; geometry shader, pixel and sample interlock, sparse binding/residency, BC textures, push descriptors, `VK_EXT_shader_stencil_export`, dynamic rendering all present. An llvmpipe device is listed second. |
| GPU clock | devfreq `3d00000.gpu`, `simple_ondemand`, 220-680 MHz (same top clock as Android); no KGSL |
| Display | DRM `card1` with DSI-1 (internal), DP-1 (USB-C) |
| Session | gamescope 3.17.0-ogc1 in Game Mode, KDE Plasma desktop mode; native arm64 Steam |
| Input | "AYN Odin2 Gamepad" evdev plus InputPlumber virtual devices |
| Audio | PipeWire 1.6.11, built-in speaker and headphone sinks |
| Libraries | SDL3 3.4.20 system package (the build bundles its own) |
| SSH | sshd with the PC's key (`from="192.168.1.0/24"`); no firewalld running |

Consequences for the plan: the default 4 KiB-page build
(`PINYON_SHIFT_PHYSICAL_HEAP_4K_PAGES=ON`) runs here; every Vulkan
feature the desktop path asks for is present, so LA-2 starts from the
desktop renderer rather than an Android-specific one. The full
`vulkaninfo` report is kept outside the repository
(`.local/linux-arm64/odin-armada-vulkaninfo.txt`).

The internal panel stayed black on the first boot. Armada has an open
issue for newer Odin 2 Portal panels (Visionox VTDR6130 instead of the
Chipone ICNA3512 its device tree drives,
[armada-os/armada#845](https://github.com/armada-os/armada/issues/845));
on this unit it came up after the OpenABL device model was checked and
set, and the internal panel works since. Check that setting first.

## Sources

- Armada OS: [site](https://armadaos.dev/),
  [repository](https://github.com/armada-os/armada),
  [Xenia Edge page](https://armadaos.dev/emulation/emulators/xenia-edge/),
  [environment variables](https://armadaos.dev/compatibility/environment-variables/),
  [known issues](https://armadaos.dev/troubleshooting/known-issues/);
  release write-ups for
  [20261109](https://playingtux.com/en/articles/2026/11/armada-os-20261109-released/)
  and [20260817](https://playingtux.com/en/articles/2026/08/armada-os-20260817-released/);
  [install guide](https://averagetechnerds.com/install-armada-os-ayn-handhelds/).
- Kernel: [AYN QCS8550 device-tree series](https://lkml.iu.edu/2607.3/06614.html);
  [Armbian Odin 2 Turnip report](https://git.huazai-net.workers.dev/armbian/build/issues/9685).
- Steam Runtime 4 images, including the arm64 SDK sysroot:
  [repo.steampowered.com/steamrt4](https://repo.steampowered.com/steamrt4/images/latest-public-beta/).
