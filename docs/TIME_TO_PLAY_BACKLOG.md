# Time to play: prebuilt and bundled setup

Status: TP-1 to TP-7 worked through on 2026-10-31; see
[Results](#results-2026-10-31). The prebuilt assets go live with the first
tagged release after `dev` 787bc833. The Windows kit stays unpublished
until the DLSS question under TP-3 is settled.

Goal: the shortest time from downloading the launcher to playing, on
every platform, while releases keep the line in [LEGAL.md](LEGAL.md): no
game files, no translated code, nothing linked with it. Everything else
(the SDK runtime and renderer, third-party libraries, the code generator,
our own host code, the build tools) may ship prebuilt, under its licence.

The player's machine keeps only the work that needs their disc: verify the
image, translate the game code, compile that translation, link it, and
prepare the driver's shaders.

## Results (2026-10-31)

Measured on Multivac unless noted. "Kept" items are on `dev`; the release
workflow builds every prebuilt asset (`prebuilt-*` jobs, each allowed to
fail without blocking the release) and pins them in the release payload
only on a tag, so the checked-in config never points at an asset that
doesn't exist yet.

| Item | State | Result |
| --- | --- | --- |
| TP-1 trimmed LLVM and sysroot | kept | Windows LLVM 940 MB / 4.0 GB to 89 MB / 264 MB; Linux 2.0 GB / 11 GB to 109 MB / 682 MB; sniper sysroot 1.23 GB / 3.7 GB to 179 MB / 1.08 GB. A WSL Ubuntu setup from the trimmed toolchain and the Linux kit built and linked the game in 633 s (16 jobs, sharing the CPU with a Windows build), with 1.9 GB of toolchain on disk against about 15 GB. |
| TP-2 prebuilt generator | kept | In the kit (`bin/rexglue`). Saves the generator's 2:52. |
| TP-3 SDK kit | kept, Windows unpublished | Windows kit 23.7 MB (57 MB while it still carried the vendor DLLs), built in 252 s; the game configures in 3 s and builds from it; `fh1-free-roam` passes. Linux kit 12.7 MB in 246 s. Each kit records its clang, MSVC toolset and Windows SDK (or sysroot, NDK) in `kit.json`, and setup refuses a kit from another ShiftGlue revision. No vendor binary is in a kit: on Windows the game's configure fetches AMD's signed FidelityFX DLL and NVIDIA's DLSS runtime with the SDK's own pinned, hashed fetch modules, which the kit carries. The DLSS question: `rexruntime.dll` links NVIDIA's static NGX loader, so a published Windows kit is a binary release of the loader. NVIDIA's approval covers DLSS "with the Windows build"; whether it covers this is for the maintainer to confirm (`nvidia-rtx-license-questions@nvidia.com`). The workflow builds the Windows kit and attaches it only when the repository variable `PINYON_SHIFT_PUBLISH_WINDOWS_KIT` is `true`. CPU baseline, host split and v4: below. macOS kit: built only by the release workflow so far, not on the Mac mini. |
| TP-4 Windows without Build Tools | built, opt-in, fetch untested | With a kit, the game build needs only the CRT, STL and Windows SDK headers and libraries: `clang` reads `INCLUDE`, `lld-link` reads `LIB`, `llvm-mt` merges manifests, and no `rc.exe` or `mt.exe` runs. A build with only those two variables set (pointing at the installed toolset, no `VsDevCmd`) compiled and linked the game (61.9 MB). Setup fetches them with `xwin` 0.10.0 (pinned, hashed) when `PINYON_SHIFT_MSVC_SYSROOT=1` or a fetched sysroot exists. The fetch itself is untested: it needs the player to accept Microsoft's licence, and nobody has accepted it on anyone's behalf. Needs the licence review this item asked for before it becomes a default. |
| TP-5 Android shell and signer | kept | The shell (`android shell`): 44.7 MB, 362 MB unpacked, built in 201 s. Building the v4 APK from it needed only the NDK, CMake and Ninja: no JDK, no SDK manager, no runtime compile. `tools/apk_sign.py` aligns (16 KiB for `.so`) and signs (APK Signature Scheme v2) in Python, carrying over the key the old `keytool` made: `apksigner` and `zipalign -c -P 16` accept the result, and it installs over the earlier APK. RSA-3072 key generation 1.4 s, signing a 49 MB APK 0.22 s. The NDK r29 and platform-tools come straight from dl.google.com, pinned by SHA-256. On the Odin the shell APK loaded every library and created the Vulkan device; the title screen was not checked, because the device was locked. |
| TP-6 compile less | partition size kept, others rejected | Below. |
| TP-7 fewer steps | early downloads kept; others decided | Below. |

### TP-3 measurements

**CPU baseline: one SSE4.1 runtime per platform.** The same fma game
code (Multivac's own baseline) linked against the SSE4.1 kit runtime and
against an fma build of the same kit, `fh1-race-sync` from the
`appdata-2026-09-27-winwarm` seed, three interleaved rounds each, means over
the race (RTX 4080, Ryzen 7 5800X):

| Runtime | Process CPU per frame | GPU decoder | Title thread |
| --- | ---: | ---: | ---: |
| SSE4.1 | 25.37 ms (25.06-25.75) | 6.41 ms | 3.19 ms |
| fma | 25.75 ms (25.20-26.23) | 6.47 ms | 3.35 ms |

The fma runtime is no faster. The runtime's hot paths (the PM4 decoder,
texture and audio work) gain nothing from FMA. The kit stays SSE4.1, and
the generated code keeps choosing its own baseline at setup.

The host split and v4 as a run-time choice are not done. With the kit, our
host code is 71 compile jobs and 18 % of the compile CPU left (502 of
2,846 job-seconds in the INCLUDE/LIB-only build; the rest is the
generated code and the two facades), and on 16 threads it overlaps the
generated code. The split would save well under a minute there, and
about 2 minutes on 4 cores, for two host libraries per platform (base and
v4) until v4 becomes a run-time choice. Both stay on the list for after
TP-4's licence review, which decides how the Windows host code could be
prebuilt at all.

### TP-6 measurements

The generated code compiled from the kit, timed from Ninja's log (only the
`pinyon_shift_recomp` objects, frozen codegen, base game):

| Variant | Job-seconds | Wall, 16 jobs | Objects |
| --- | ---: | ---: | ---: |
| `-O3 -gline-tables-only` (default) | 1,214 | 79.5 s | 166 MB |
| `-g0` | 1,140 (-6 %) | 75.1 s | 86 MB |
| Every unit at `-O1` | 1,129 (-7 %) | 74.7 s | 169 MB |

- **Cold code at `-O1`: rejected.** Even every unit at `-O1` saves only
  7 %, and no unit is cold: of 76,494 functions the probe routes entered
  38,770, spread over all 260 units (median 51 % of a unit's functions).
  At this size the compile is mostly parsing and code generation, not
  optimisation.
- **`-g0`: rejected.** 6 % less compile and half the object size, but the
  Windows crash reporter resolves generated frames to lines with
  `SymGetLineFromAddr64`; names alone would remain. Not worth 4 s on
  Multivac. POSIX reports use `dladdr` only, so nothing would change
  there.
- **Partition size: kept at 4 MiB.**

  | `max_file_size_bytes` | Units | 4 jobs: wall / job-s | 16 jobs: wall / job-s | Largest unit's compile memory |
  | --- | ---: | --- | --- | ---: |
  | 512 KiB | 495 | 207 s / 817 | | |
  | 1 MiB (old default) | 260 | 172 s / 678 | 80 s / 1,214 | 532 MB |
  | 2 MiB | 124 | 155 s / 603 | 78 s / 1,104 | 532 MB |
  | 4 MiB | 62 | 146 s / 568 | 74 s / 985 | 386 MB |

  Each unit includes the same large header; fewer units parse it fewer
  times. At 62 units, 16 threads still have work to the end. The largest
  unit's compile needs well under 1 GB. (Four parallel jobs on Multivac
  stand in for a 4-core PC.) Run time is unchanged: seven interleaved
  `fh1-race-sync` rounds each (same kit and fma flags as the TP-3 A/B) gave
  the title thread 3.30 ms a frame at 1 MiB and 3.31 ms at 4 MiB, and
  process CPU 25.47 ms and 25.58 ms, inside the 1 MiB build's own spread
  (25.00-25.95 ms). The first three rounds alone suggested 0.3 ms worse
  for 4 MiB, which more rounds did not confirm. Changed in ShiftGlue
  (`max_file_size_bytes`, 4 MiB); a changed budget repartitions from
  scratch, and the module fingerprint includes it, so existing installs
  translate once more.
- **Translation is single-threaded:** 84-88 s of CPU in 84-88 s of wall at
  every partition size, almost all of it analysis before any file is
  written. Parallelising it is ShiftGlue work for later; it doesn't depend
  on any of the above.

### TP-7 decisions

- **Early downloads: kept.** Windows setup starts `tools/prefetch-setup.ps1`
  (the pinned tool archives and the kit) before verifying the disc, and
  the POSIX setup starts the same downloads on a thread. Provisioning then
  finds them in `.local/downloads`.
- **Background shader preparation: rejected.** The renderer page already
  measured what a player would see: with an empty driver cache,
  preparation cut frame time over budget in the first race from 13.0 s to
  5.7 s and the worst frame from 1.35 s to 0.53 s. Playing while it runs
  would bring that stutter back to the first race, for 2 minutes saved.
- **Reading the disc image in place: deferred.** ShiftGlue already has a
  `DiscImageDevice`, but the game mounts through our `OverlayDevice`
  (`src/mod/overlay_device.cpp`), which stacks `HostPathDevice`s for mods.
  The host UI reads `media/ui` from the game folder, and about nine tools
  read `.local/game/base` (verification, shader preparation, DLC and the
  Android push). Each needs an image reader first. Saves about a minute
  and 7 GB; worth its own change.

## Where the time goes today

Fresh v0.7.1 setup on Multivac (Ryzen 7 5800X, 16 threads, 128 GB),
2026-10-27. Visual Studio was already installed, so its install is not
in these numbers. The double translation (87 s) is already fixed
(ShiftGlue `a069c91f`, `dev` `59983771`).

| Step | Time | Game-derived? |
| --- | ---: | --- |
| Verify the game files | 8 s | yes |
| Download the tools (LLVM, CMake, Ninja, Git, Python, xz, extract-xiso) | 41 s | no |
| Clone ShiftGlue and its 23 libraries (2.1 GB) | 83 s | no |
| Copy or extract the game files (6.8 GB) | 64 s | yes |
| Configure and build the code generator | 2:52 | no |
| Translate the game | 1:34 | yes |
| Configure the game build | 1:27 | mostly no (SDK libraries) |
| Compile and link (5:28 before the fix, 3:54 after) | 3:54 | partly |
| Prepare shaders (plays the opening, hidden) | 2:06 | yes, driver-specific |

Compiling took about 4,600 CPU-seconds in all. The generated game code is
about 1,670 of them (36 %). The rest is the generator, the SDK, its
third-party libraries and our host code, all of which could ship
prebuilt.

The downloads and disk are larger than the build itself:

| Platform | Downloads before the build | Disk |
| --- | --- | --- |
| Windows | Visual Studio Build Tools (several GB, administrator, sometimes a restart); LLVM 940 MB unpacked to 4.0 GB; CMake 47 MB; MinGit 39 MB; Python 11 MB; ShiftGlue clone 2.1 GB | about 30 GB |
| Linux and Deck | LLVM (about 2 GB unpacked) and the Steam Runtime sniper sysroot (15 GB together on disk); CMake, Ninja, Python if older than 3.11; ShiftGlue clone. Needs system `git` | 45 GB |
| macOS | Command Line Tools (from Apple); CMake, Ninja, Python (always); ShiftGlue clone; MoltenVK and FidelityFX built from source, with SPIRV-Cross and cereal cloned at configure | 20 GB |
| Android (built on a Windows PC) | Everything for Windows, plus JDK 191 MB, Android command-line tools 156 MB, then NDK 29, build-tools 36, platform 36 and platform-tools through `sdkmanager` ("a few GB") | 15 GB more |

Quoted first-build times: 20 to 60 minutes on a PC, about 35 minutes on
the Deck, 18 to 20 on an M4 Pro, 20 to 60 for Android.

## What has to stay on the player's machine

- **Translating the game.** Only the generator reads the `.xex` files.
- **Compiling the generated code** (`pinyon_shift_recomp`, the two facade
  DLLs). The generated precompiled header bakes in game addresses.
- **A handful of host files** that include generated headers:
  `src/main.cpp`, `src/pinyon_shift_app.cpp` (`pinyon_shift_init.h`),
  `src/guest_native/reference_verify.cpp` and `region_oracle.cpp`.
- **The link**, because `src/guest_native` replaces weak generated
  functions with strong ones, which only works in the same link.
- **Shader preparation.** The pipelines are translated game shaders and
  are driver-specific; they can't ship.

Everything else is ours or third-party.

## What blocks prebuilt today

1. **The installed-SDK path doesn't work.** `cmake/PinyonShiftRexGlue.cmake`
   has a `find_package(rexglue 0.10.0 EXACT)` branch, but no preset, script
   or CI job uses it. The game build reaches into `${REXSDK_DIR}` for
   `sha256.cpp`, toml++, renderdoc, imgui and the DLL staging. The SDK's
   version comes from `git describe` (`0.10.0.638`), so `EXACT 0.10.0`
   would not match. Its install rules run only in a standalone SDK build,
   and the DLSS and FSR staging isn't exported.
2. **The boundary is C++.** Generated code calls the runtime through
   mangled C++ (`ResolveIndirectFunction`, the MMIO handler, the global
   critical region, the clock, spdlog) and uses inline headers over
   `PPCContext`, `KernelState` and `ThreadState`. A prebuilt runtime and a
   local compile must agree on class layouts, the standard library and
   name mangling:
   - Windows: the CRT and STL come from whatever Visual Studio the player
     has, with only a minimum version (17.1). This is the main risk.
   - Linux: pinned clang and sysroot, and `libstdc++` is linked statically
     into each library. Already consistent.
   - macOS: the Command Line Tools' libc++, whose ABI Apple keeps stable.
   - Android: the pinned NDK and `c++_shared`. Already consistent.
3. **Options that change the runtime have to match.**
   `REXGLUE_ENABLE_PERF_COUNTERS` (on in every Pinyon build) changes a
   class layout in `debug_overlay.h`. `REX_PHYSICAL_HEAP_4K_PAGES` (Linux
   and Android) is read by both the runtime and the generated header.
   Release and RelWithDebInfo name their libraries differently.
4. **The host code depends on the build variant.**
   `PINYON_SHIFT_TITLE_UPDATE_V4` is compiled into `fh1_guest_address.h`,
   `guest_native.h`, `pinyon_shift_app.cpp`, `dev_options.cpp` and
   `mod_host.cpp`. As it stands, base and v4 would need two prebuilt host
   libraries.
5. **The variant count.** Today Windows and Linux each build three CPU
   baselines (SSE4.1, FMA, x86-64-v3) in two configurations. The runtime
   never reads the baseline defines and the boundary is plain calls, so an
   SSE4.1 runtime should work with v3 generated code (not tested). The cost
   would be the runtime's own speed: the renderer and audio, not the game
   code.
6. **Vendor binaries.** [LEGAL.md](LEGAL.md) says no release ships a vendor
   binary. DLSS's import library is linked into `rexruntime`, and NVIDIA's
   approval covers DLSS "with the Windows build". Shipping a prebuilt
   runtime that contains the NGX loader needs that approval read against
   a binary release (§4(e): nothing may subject the SDK to an open-source
   licence). AMD's FidelityFX DLL and Intel's XeSS allow redistribution
   with their notice.

## Plan, ranked by time saved per unit of risk

IDs are TP-n. Savings are from the Multivac run unless marked as an
estimate.

### TP-1. A trimmed, bundled build toolchain (all desktop platforms)

The build uses 13 of LLVM's tools. `clang`, `clang++`, `clang-cl` and
`clang-cpp` are four full 100 MB copies of one binary, and `bin/` alone is
3.2 GB.

- Repack the pinned LLVM in CI with only `clang` (one binary, the others
  as copies made at unpack or as hard links), `lld`, `llvm-ar` and the 9
  other tools the build calls, plus `lib/clang` (42 MB). Estimate: about
  250 MB unpacked, under 100 MB compressed, against 940 MB and 4.0 GB.
- Do the same for the Linux sniper sysroot: keep the headers, the
  libraries the game links and GCC 10's `libgcc`. Today LLVM and the
  sysroot take 15 GB together.
- Publish each repack as a release asset with its SHA-256 and build
  recipe, or put it in the launcher archive. Both LLVM (Apache 2.0 with
  LLVM exception) and the Steam Runtime SDK are redistributable. The
  sysroot's per-package licences need listing in
  `THIRD_PARTY_NOTICES.md`.
- Bundle the small tools in the launcher instead of downloading them:
  CMake (trimmed to `bin` and `share/cmake-3.31`), Ninja, and Python on
  macOS, where it is always downloaded today.

Saves the 41 s of downloads, most of 5 GB of disk on Windows and of 15 GB
on Linux, and removes a common failure point (slow or blocked
`github.com` and `repo.steampowered.com`).

### TP-2. A prebuilt code generator

`rexglue` is a standalone host tool, so the ABI issues above don't touch
it. Ship one per host (Windows x64, Linux x64, macOS arm64) in the
launcher, built from the pinned ShiftGlue revision. Its fingerprint now
hashes its own binary, so a changed generator still retranslates.

Saves the generator's configure and build: **2:52 on Multivac**, more on
fewer cores. Its third-party libraries (FFmpeg, glslang, SDL and others)
are no longer compiled for it.

### TP-3. A prebuilt SDK runtime and an SDK header bundle

This is the largest change, and the one that removes the clone.

- **Ship** `rexruntime` and `rexgpu-fh1` per platform (DLL, `.so`,
  `.dylib`), their import libraries, the FidelityFX Vulkan library (built
  from source on Linux and macOS at every first build today), MoltenVK on
  macOS, and a headers-only SDK tree: `include/rex`, the headers that
  generated code and the host use (simde, toml++, fmt, spdlog, xxhash,
  o1heap, disruptorplus, imgui, renderdoc), `rex_app.cpp` and
  `windowed_app_main_sdl.cpp`. Estimate: tens of MB, against a 2.1 GB
  clone. Git is then no longer needed at setup on any platform.
- **Add a consumer mode** to `PinyonShiftRexGlue.cmake` that imports these
  targets from the bundle. Remove the remaining direct
  `${REXSDK_DIR}/thirdparty` and `src` paths from the game target (tests
  and tools can keep them; players don't build those). Export the DLSS
  and FSR staging. Keep `REXSDK_DIR` as the developer path.
- **Pin the ABI.**
  - Windows: build the bundle with the pinned clang against a pinned MSVC
    toolset and Windows SDK (see TP-4), and record both in the bundle's
    manifest. Until TP-4, build it with the oldest MSVC setup accepts
    (17.1). Microsoft supports linking older toolset binaries into a
    newer toolset's link, not the reverse.
  - Linux, macOS and Android: record the clang, sysroot or NDK in the
    manifest and refuse a mismatched bundle.
- **Fix the runtime options** in the bundle: perf counters on,
  `REX_PHYSICAL_HEAP_4K_PAGES` as today per platform, Release only. A
  RelWithDebInfo or Tracy build stays a source build for developers.
- **CPU baseline:** measure an SSE4.1 runtime against an FMA or v3 runtime
  with v3 generated code (Odin, Deck and Multivac routes, CPU ms/frame).
  Ship one runtime per platform if the difference is within noise.
  Otherwise ship two (SSE4.1 and v3) and choose at setup, as the generated
  code already does.
- **Split our host code** into a prebuilt `pinyon_host` library and the
  few files that include generated headers (`main.cpp`,
  `pinyon_shift_app.cpp`, `reference_verify.cpp`, `region_oracle.cpp`).
  `guest_native`'s strong overrides need no generated headers, so they can
  ship as object files linked with the generated code. Two linking forms
  to measure: whole-archive (simpler) or a list of objects.
- **Make v4 a run-time choice in the host code** where it is a compile-time
  define today (`fh1_guest_address.h` already holds both address sets).
  Otherwise ship two host libraries.

Saves the clone (83 s, 2.1 GB), most of the game configure (1:27), and
about 1,800 CPU-seconds of compiling (SDK, third-party, host). Estimate
for Multivac: setup from about 15 minutes to about 7. On a 4-core PC the
compile part falls from roughly 20 minutes to about 7 (extrapolated from
CPU-seconds, not measured).

It also makes updates cheap. A release that changes only the runtime or
the renderer replaces the bundle without recompiling anything. Today an
SDK bump retranslates every module and recompiles everything it touches.

### TP-4. Windows without Visual Studio Build Tools

Visual Studio is the largest download, the only step needing
administrator rights, and the only one that can ask for a restart. The
build uses only these parts of it:

- the MSVC STL and CRT headers and import libraries;
- the Windows SDK headers and libraries (`d3d12`, `dxgi`, `bcrypt`,
  `dbghelp`, `ws2_32` and others), `rc.exe` and `mt.exe`;
- the VC++ runtime DLLs staged beside the game.

There are two ways to drop the install:

- **A. Fetch only those packages from Microsoft at setup.** Read the same
  channel manifest the Visual Studio installer reads, take the x64 MSVC
  toolset and the Windows SDK packages at pinned versions, unpack them
  without the installer, and use `llvm-rc` and `llvm-mt` instead of
  `rc.exe` and `mt.exe` (the open-source `xwin` tool does this). This
  needs no administrator rights and is a few hundred MB, not several GB.
  It also pins the CRT and STL versions, which TP-3 needs. **This needs
  a licence review first:** the packages stay under Microsoft's terms, and
  the player accepts them, as the installer asks today. We'd be
  automating a download from Microsoft, not redistributing it.
- **B. Build for the MinGW target with llvm-mingw**, which is
  redistributable and could be bundled entirely. That is a port of the
  whole Windows build to another C++ ABI, and the DLSS loader is an MSVC
  static library. Too large for now; noted so it isn't reconsidered
  without a reason.

Saves the Build Tools install, which these measurements don't cover.
Measure it on a clean Windows VM before and after.

### TP-5. Android: a prebuilt app, compile only the game

Today the PC builds the whole APK: the JDK, `javac`, `d8`, `aapt2`,
`zipalign` and `apksigner`, the full NDK, and the runtime, renderer and
FidelityFX from source.

- **Ship a prebuilt unsigned APK shell** per release: `classes.dex`, the
  resources, `librexruntime.so`, `librexgpu-fh1.so`,
  `libamd_fidelityfx_vk.so`, `libc++_shared.so`, the adrenotools hooks,
  and the Turnip driver. Turnip is MIT, and nothing downloads it today.
  The PC compiles `libmain.so` and the two facades, adds them to the zip,
  aligns it and signs it with the per-PC key it already makes.
- **Drop the JDK and Android SDK** by aligning and signing (APK Signature
  Scheme v2/v3) in our own code: the launcher's C# or `pinyon_android.py`.
  Then only a compiler and the NDK sysroot are needed. The NDK's LLVM is
  the same clang as TP-1 with an Android target. Check whether the NDK
  sysroot (headers, `libc++`, the platform stubs) may be repacked under
  its licences. If not, keep downloading the NDK alone, still without the
  JDK and the SDK manager.
- **Linux and macOS get Android builds for free.** Today they need an SDK
  and JDK installed by hand; the bootstrap URLs are Windows-only.

Saves about 350 MB of JDK and tools plus a few GB of SDK packages, and
all the runtime compiling. The APK keeps the per-PC signing key, as now.

### TP-6. Compile less for the generated code

The generated code itself (about 1,670 CPU-seconds, 2 minutes on 16
threads, roughly 7 on 4 cores) is now the floor. Each of these needs a
compile-time and a run-time measurement:

- **Cold code at a lower optimization level.** The probe builds already
  count every function's calls, and the Android build already orders
  symbols by them. Compile the partitions holding functions that never
  ran in the probe routes with `-O1` and keep the rest at `-O3`.
  Measure compile CPU-seconds, and CPU ms/frame on the Odin and the Deck.
- **No debug information for players.** `-gline-tables-only` is the
  default; `-g0` saves some compile time and disk. Crash reports
  symbolized from line tables would lose their lines, so this needs the
  crash-report path checked first.
- **The partition size** (1 MiB files today): fewer, larger files compile
  each header once fewer times; more, smaller ones keep all cores busy to
  the end. Measure two sizes on a 4-core machine (Blindvac).
- The translation itself (94 s) runs before any compile can start. Find
  out whether it is single-threaded and what dominates it.

### TP-7. Fewer steps around the build

- **Read the disc image in place.** The runtime reads 6.8 GB of
  extracted files, and extraction takes about a minute plus the disk.
  Linux and macOS already read the XDVDFS image in Python without
  mounting it. A read-only image device in the runtime would serve the
  same files from the ISO; the generator needs only the three `.xex`
  files. Saves about a minute and 7 GB. On Android, one 7 GB file over
  Wi-Fi or USB instead of 2,400 is also faster.
- **Shader preparation in the background.** On Windows it blocks the end
  of setup for 2 minutes; on Linux and macOS it blocks the first Play.
  Offer Play right away and prepare while the menus run, with the
  existing stutter-free path as the default. It needs a measurement of
  what a player sees in the first race without it.
- **Start downloading before the disc is chosen.** Toolchain and bundle
  downloads need nothing from the player. Start them when the launcher
  opens, during disc selection and verification.

## Expected result

Estimate for Multivac with TP-1 to TP-3 and TP-7, Windows: verify 8 s, read
the image in place, translate 1:34, configure about 15 s, compile the game
code about 2 minutes, link about 20 s, shaders in the background. That is
**about 4 to 5 minutes to play**, against 17 today, and no Visual Studio
install once TP-4 lands. On a 4-core PC, about 10 to 12 minutes against
35 to 60. These are estimates to be checked against the same clean-install
measurement as the table at the top.

## Order of work

1. TP-1 and TP-2: independent of ABI questions, quick to verify, and they
   remove the largest downloads and three minutes of build.
2. TP-4's licence review in parallel, since TP-3's Windows ABI pin depends
   on its answer.
3. TP-3, starting with the consumer CMake mode and the CPU-baseline
   measurement, then the host-code split and v4 as a run-time choice.
4. TP-5 on top of TP-3's Android bundle.
5. TP-6 and TP-7, each kept or rejected on its measurement and recorded
   in `site/pages/lessons.md` either way.

Each step is measured the same way as the baseline: a clean install in a
private folder, setup's own timestamps, Ninja's log, peak disk. Use
Multivac and Blindvac (4 cores) on Windows, the Deck on Linux, and the
Mac mini.

## Related

- [LOCAL_BUILD_COST.md](LOCAL_BUILD_COST.md): earlier build-cost
  measurements and SDK checkout reuse (#671).
- [ONE_CLICK_SETUP_BACKLOG.md](ONE_CLICK_SETUP_BACKLOG.md): what setup
  already provisions and repairs.
- [LEGAL.md](LEGAL.md): the distribution boundary.
