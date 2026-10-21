---
title: Platform ports
section: Internals
order: 6
description: What it took to run Pinyon Shift natively on Windows, Linux and the Steam Deck, Apple silicon Macs and Android, with the measurements behind each platform's settings.
---

# Platform ports

The same generated C++ and the same Vulkan renderer run on every platform. What differs is the toolchain, how the host maps memory, waits and schedules threads, and which GPU work pays off.

| | Windows | Linux, Steam Deck | macOS | Android |
| --- | --- | --- | --- | --- |
| CPU | x86-64, SSE4.1 (FMA3 variant) | x86-64, SSE4.1 (x86-64-v3 variant, the Deck's) | arm64 | arm64 |
| Compiler | Clang 20.1.8 (`clang-cl`) | Clang 20.1.8, Steam Runtime 3 sysroot | Command Line Tools clang | NDK r29 |
| Vulkan | system driver | RADV or NVIDIA | MoltenVK, bundled | Turnip on Adreno 7xx, else the system driver |
| Host page size | 4 KB, 64 KB granularity | 4 KB | 16 KB | 4 or 16 KB |
| Audio, input | SDL3, XInput | SDL3 | SDL3 | AAudio, SDL3, touch |

## Windows

The reference PC is a Ryzen 7 5800X (8 cores, 16 threads) with an RTX 4080. Against the console's 30 fps and Xenia's 30 fps cap, the native renderer runs the opening drive at 120 fps, the display's limit. The heavy race holds 119 fps at 1x and 2x and 102 fps at 3x ([Performance](performance.md)). Most desktop work was on the CPU side of the renderer; see [GPU optimizations](gpu-optimizations.md#the-recorder-thread).

**Smaller PCs.** The game's frame rate sets every per-second CPU cost, since the simulation steps and the recorder's work scale with it. 60 fps is half the CPU work of 120, and 40 a third. That is the idea behind the presets:

| Preset | Settings | For |
| --- | --- | --- |
| Ultra Low 30 | Low-spec 60 without sun shadows, reflections at a quarter rate, the scene in one pass, textures at most 256 texels across, 30 limit | integrated graphics on 2 physical cores |
| Low-spec 60 | 1x, no MSAA, bilinear, the game's anisotropy, no FXAA, 60 limit | new installs |
| Balanced 40 | the same at 40, even pacing on 120 Hz displays and the Deck's 40 Hz mode | under 4 physical cores |
| Performance 120 | | discrete GPU with 6 GB or more, 6 or more threads, a 120 Hz display |

The core-count limits were tested on the same PC with the game restricted to fewer cores (`--host-cpus`), a load on the sibling threads, and a VRAM balloon. These show sensitivity, not real older hardware:

| Low-spec 60, heavy race start | Presents a second |
| --- | ---: |
| 16 threads | 59.7 |
| 4 cores, 8 threads | 59.7 |
| 4 cores, 4 threads (the recorder was faster without SMT: 7.4 against 8.9 ms) | 59.7 |
| 4 slow cores | 58.9–59.3 |
| 2 cores, 4 threads | 59.0–59.3, 0.8–1.0 % long frames |
| 4 slow cores, Balanced 40 | 39.9 |
| about 1 GB of VRAM free | unchanged |

**Toolchain.** The FMA3 variant is chosen at build time when Windows reports AVX2, with a guard that stops it on a CPU without FMA3; it cut the guest main thread's CPU by 6–7 %. Windows rounds a sub-millisecond `Sleep` to a yield, so short waits there use high-resolution waitable timers.

## Linux and the Steam Deck

**Build.** Clang 20.1.8 targets `x86_64-linux-gnu` against the Steam Runtime 3 ("sniper") SDK sysroot and links with `lld`. libstdc++ is linked statically, so the 195 MB binary needs only glibc 2.30 and no system C++ runtime. The launcher reads the disc image directly, without mounting it, and sizes the build's job count to memory. The first build takes about 35 minutes on the Deck.

**What changed from Windows.**

- Real-time thread priorities fail with `EPERM` for an unprivileged process, and a guest priority of 0 or less was invalid and failed thread creation. Priorities map to nice values instead.
- Multi-object and alertable waits polled every millisecond; they now wake on signal.
- Timers use `CLOCK_MONOTONIC_RAW`; the display refresh rate comes from SDL.
- Audio goes through SDL3, which loads PipeWire, PulseAudio or ALSA at run time.
- SteamOS ships `librenderdoc.so`, which hooked every run; RenderDoc is now used only when it is already loaded.
- Input comes from SDL3, including SDL's Deck driver and Steam Input's virtual pad when Steam starts the game.
- LLVM's Linux `ld.lld` and the sysroot's `wayland-scanner` link `libxml2.so.2`, which SteamOS, Arch and other distributions with libxml2 2.14 or newer no longer have. Setup runs both through small wrappers that load only that library and its ICU from the sysroot, so nothing has to be installed on the host.

**Toolchain.** Linux x86-64 builds use the small code model with linker relaxation. The large model with `--no-relax` was there for code over 2 GB, but the executable's code is 53 MB, and the large model made nearly every call a `movabs` plus a register-indirect call (13 direct calls in the whole executable against 365,000 with the small model). The build also uses x86-64-v3 (AVX2, FMA3, BMI, MOVBE) when the CPU has it: setup reads `/proc/cpuinfo`, since the game is built on the machine that runs it, and the `linux-amd64-v3` preset builds the Deck variant on another PC. The same guard as on Windows stops a v3 build on an older CPU; the SSE4.1 build stays for those. Measured together on the Deck LCD, in six interleaved Steam launches of the race (three per build) with per-thread `perf stat` over 40 s from the start, against the spread of the three old-build runs:

| Per frame | Change | Old-build spread |
| --- | ---: | ---: |
| Simulation thread cycles | −10.5 ± 1.2 % | 1.5 % |
| Render thread cycles | −7.1 ± 3.0 % | 4.5 % |
| Audio thread cycles | −26.4 ± 2.2 % | 0.7 % |
| Job thread cycles | −14.3 ± 2.8 % | 2.0 % |
| GPU command decoder cycles per draw | −2.9 ± 0.6 % | 0.9 % |
| Process CPU time, adjusted for draws | −5.5 ± 0.5 % | |
| Frame time p99 | −6.6 % | 1.0 % |

GPU time and APU power did not change; the APU stays at its 15 W limit in both builds.

**Thread placement.** On a Steam Deck (LCD or OLED, detected from the board's DMI name or the CPU model), `linux_thread_cores=auto`, the default, pins threads by name: the simulation and audio threads on core 0's two SMT siblings, render and GPU submission on core 1's, the GPU command decoder and the recorder on cores 2 and 3, and every other thread on the remaining siblings of cores 2 and 3. Elsewhere it changes nothing; the runtime log states the decision. An in-run A/B on the Deck race, switching placement on and off every 180 frames in five runs with two toggle orders (the toggles fall on fixed route frames), gave process CPU −6.1 ± 1.3 % and −6.8 ± 1.5 % adjusted for draws, mostly from the decoder (−7 to −10 %) and the recorder (−6 to −8 %), each alone on a physical core. p99 stayed level (23.45 ms unpinned against 23.56 ms pinned, both orders weighted alike, capture frames excluded) and p95 was about 1 ms better; frames over 25 ms were 3.3 against 4.8 a run, too few to call. A later check of the tails on the shipped build, with the on and off windows in a random order in eight runs and four pairs of whole runs, found p99 level (+0.09 ± 0.51 ms within runs, -0.14 ± 0.88 ms between runs) and p95 0.8 to 1.7 ms better; auto showed about two more frames over 25 ms a run, within noise. `linux_thread_cores` takes the same `NAME=CORES;...` entries as [Android's](android.md) `android_thread_cores` and changes while the game runs; `off` leaves placement to the scheduler.

**The Deck.** The Steam Deck LCD (Zen 2, 4 cores and 8 threads, RDNA 2 on Mesa RADV) runs the race and free roam at 60 fps at 1x under its default 15 W limit. A replayed frame at 1x:

| Change | Frame |
| --- | ---: |
| Default | 11.19 ms |
| Partial resolves (on for every Linux build, identical image) | 10.87 ms |
| Coarse 2 × 2 shading (SCENE SHADING > COARSE) | 10.42 ms |
| New defaults plus coarse shading | 9.9 ms |

One trap: with Manual GPU Clock on in the Quick Access menu, Steam can pin the GPU at 200 MHz. The game drops to about 10 fps while the GPU reports full load at under 1 W, and starting over SSH leaves the clock there too. The launcher's `deck doctor` reports the clock.

## macOS on Apple silicon

**Build.** Command Line Tools clang for arm64 with a macOS 13 target, and a MoltenVK that ShiftGlue builds and bundles. The generated code is the same C++: VMX operations reach NEON through SIMDe (byte shuffles become `tbl`), FPCR replaces MXCSR, and `std::fma` is one instruction. Guest functions are weak thunks rather than aliases, because Mach-O has no overridable alias. Setup from the disc image to a built game takes about 18–20 minutes on an M4 Pro.

**16 KB pages.** One host page holds four guest pages. The write-watch code took a host page's protection from its first guest page, so a committed page next to an uncommitted one faulted (SIGBUS in free roam, runs 2–4). Using the union of the four guest pages' access fixed it. The GPU's shared-memory tracking also used host pages, so a CPU write beside the 4 KB exposure resolve discarded it and free roam was overexposed and flashed (luma 171.5 against 114.7 on Windows); it now tracks 4 KB pages and keeps GPU-written pages a write did not touch (111.9).

**Exposure and fullscreen.** Keeping that GPU copy valid does not put it in CPU guest RAM. A later M1 Max contributor trace found CPU reads of the float luminance resolve, so completed small float resolves are now read back too, a frame or two late without a GPU wait, after an unscaled copy when needed. The 4 KB tracking fix stays in place. Fullscreen defaults to a borderless window on the current desktop, and the presenter restores the Metal drawable to the swapchain extent before acquiring an image; surface recreation on resize alone did not cover a late SDL update to 1x1. The layer belongs to the connected paint context and is cleared on disconnect.

**MoltenVK limits.** No geometry shaders and no wireframe fill, so the vertex-shader expansion paths are used. No fragment shading rate, so SCENE SHADING does nothing. The portability subset lacks separate stencil reference masks, and SPIRV-Cross rejects some decorations on function-local arrays, which the translator avoids.

**Results.** The earlier 40 s free-roam optimization route at 1x, MSAA off, measured a median 8.35 ms on an M4 Pro Mac mini, with the GPU busy about 67 % of the time. This is a historical result, not a guarantee that every current route holds 120 fps. The M4 Pro is shading-bound, as the Adreno GPUs are, so macOS takes their defaults: fast pixel math, texture signs as specialization constants and untiled predicated tiling. It also turns off MoltenVK's Metal argument buffers. Together these took that route's free-roam GPU frame from 12.3–12.7 to 5.6–5.7 ms ([measurements](gpu-optimizations.md#apple-silicon)). Two more switches pay off there that don't on the RTX 4080: texture gamma through sRGB views (−8 % at 1x, offered as TEXTURE GAMMA FAST) and quads as triangle lists (−5 % at 2x, now the default everywhere).

Those measurements use MSAA off and untiled predicated tiling on. QUALITY 60 sets 2x scale, 4x MSAA and untiled predicated tiling off, so the 1x result is not a qualification of that preset. The [qualification procedure](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS.md#renderer-qualification) uses a pinned seed, all six scale/MSAA combinations and a 60 fps limit, and separates captures from the interval used for CPU, GPU and memory measurements. A successful scripted route alone does not establish a 60 fps budget or correct car geometry.

The 2026-10-18 base-game qualification on that Mac (12 CPU cores, 24 GiB,
macOS 26.3) measured these single-run means over 36.6–36.7 s of driving:

| Scale | MSAA off | 2x MSAA | 4x MSAA |
| --- | ---: | ---: | ---: |
| 1x | 59.85 fps | 59.95 fps | 59.55 fps |
| 2x | 59.84 fps | 53.65 fps | 39.55 fps |

At 2x/4x the median/p95/p99 frame was 23.16/34.53/38.69 ms, mean guest GPU
time 24.01 ms, process CPU 105% of one core and GPU busy 90%. Median Vulkan
heap usage was 3671 MiB and peak native surfaces 467 MiB. These overlap;
process RSS also omits much of Metal's memory. A separate quality drive's
`vmmap` snapshot reported a 4.6G physical footprint and swapped regions;
system-wide memory compression was substantial, so memory pressure is a
possible contributor alongside GPU cost. The [full measurement and
image gates](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS.md#m4-pro-results-2026-10-18)
include all resource columns and variability. The captures show filled cars,
but the original M1 Max failure did not reproduce and a persistent sky tint
varied between restarts. A fixed 1x/MSAA-off packet frame replayed on Mac
and Windows with RGB mean absolute errors 1.165/1.120/0.830 out of 255;
larger local differences remain, so this is not a bit-exact or 2x/4x gate.
QUALITY 60 still misses its performance budget.
Fullscreen menu/cvar routes completed, but OS screen capture was denied,
so visible fullscreen output and native Space behavior remain unqualified.

**Startup.** MoltenVK passes every stored pipeline to the Metal compiler again at each start, so creating them before the title ran gave a black screen of about 20 s (732 pipelines in 21.6 s on 9 threads). The title now starts at once and the stored pipelines are created behind it.

**Waits.** The GPU commands thread yields for up to 2 ms in WAIT_REG_MEM before it sleeps, as on Windows. macOS short sleeps overshoot under load: with 100 µs sleeps a free-roam drive had 187 frames over 25 ms and a p99 of 41.8 ms, against 23 frames and 19.8 ms with the yield. The slow frames that remain follow CPU load from other apps. When the guest audio thread falls behind, it kicks the XMA decoder up to 20 times as often, so a busy Mac shows bursts of slow frames that an idle one doesn't.

**Distribution.** The launcher bundle is ad-hoc signed and not notarized, so players approve its first start in System Settings.

## Android

**Build.** NDK r29, `arm64-v8a`, API 33, `c++_shared`, 16 KB ELF alignment (`-Wl,-z,max-page-size=16384`). The game is `libmain.so`, started by SDL. The Windows launcher builds the APK from the code it already translated and shares it over Wi-Fi.

**Bring-up** was done first on an Android emulator on the M4 Pro. Guest memory needed `memfd` shared memory and a reserve-then-fix layout; APCs use bionic's `sigqueue`; a double `pthread_join` crashed. The page-fault path parsed `/proc/self/maps`, 12,000 lines per fault, which cost the 8 Elite heavily until it was removed.

**Memory ordering.** x86 is strongly ordered, so the recompiler had dropped the game's PowerPC barriers. On AArch64 they had to come back: `sync` and `eieio` became full fences, `lwsync` acquire-release and `isync` acquire, about 320 sites in all. The x86 output is unchanged, byte for byte.

**Drivers.** Turnip (Mesa) is bundled and chosen automatically on Adreno 7xx. On the Odin's busy drive, frame time at 4x / 1x:

| Driver | 4x | 1x |
| --- | ---: | ---: |
| Stock Qualcomm | 49 ms | 41 ms |
| Older Turnip | 39 ms | 34 ms |
| Turnip Gen8 V37 (bundled) | 32 ms | 28 ms |

Qualcomm drivers needed three workarounds: infinite fence waits return at once, push descriptors read as null, and the recorder thread is off there. Sparse buffers read back zeros on an older Turnip, so shared memory used a plain buffer there; with the bundled Turnip gen8-v37 the Adreno 740 renders correctly with the sparse buffer and uses 290 MB less device memory in a race, so it is sparse again on that GPU (`vulkan_sparse_shared_memory_turnip`; other Adrenos are unchecked and keep the plain buffer). RedMagic phones cap an unknown app's clocks until the game is added to their Game Space.

**Heat.** The RedMagic Astra (8 Elite) holds 60 fps for about the first minute, then 37–39 fps at 40–44 °C skin temperature and 26–28 fps above 44.5 °C, with the cores at 2.0–2.2 GHz and the GPU frame at 35.6 ms against 20 ms cold. An ADPF performance hint changed nothing. One build measured 21.5–32 ms in the same scene across a batch, which is why live settings are compared inside one run, flipping every 300 frames.

**Presets.** Measured on the Odin 2 Portal (Adreno 740 at its 680 MHz maximum, 90–99 % busy):

| Preset | MSAA | Sun shadows | Rate |
| --- | --- | --- | ---: |
| SMOOTH 60 | 2x for the game's 4x | off | 60 |
| QUALITY 30 | the game's 4x | on | 30 |

Both draw the scene's three bands in one pass (25.4 against 28.3 ms at 1x), update the reflection map at a quarter rate (about 2.1 ms), use bilinear output (FSR 1 costs 1.4 ms) and the game's own anisotropy. Shadows cost about 6.4 ms. The Odin and the Thor hold about 60 fps with SMOOTH 60; the Astra does while cool.

**Tiled GPUs.** Adreno renders in tiles, so every rendering, clear and store has a cost a desktop GPU doesn't show. What paid off was fewer renderings (clears folded in, the scene drawn once) and specialized resolve and transfer passes; see [GPU optimizations](gpu-optimizations.md#renderings-and-clears). What didn't: forcing on-chip (GMEM) rendering for MSAA, 49.7 ms against 18.9 ms at 4x, so on-chip MSAA is no route to 4x at 60; store-op tuning; and trimming render areas, which the driver already does.

**Stutters.** Hitches on Android came from the runtime's global lock, not the GPU; see [the global critical region](runtime.md#threads). A later periodic one, a 30–40 ms frame every 30 s of play on the Odin, was the driver pipeline cache being saved on the GPU commands thread; it is now saved on the storage write thread ([GPU optimizations](gpu-optimizations.md#shaders)). What remains in capture-free race and free-roam routes on the Odin, Windows and the Deck is the race's loading screen and a few frames where the game waits on GPU fences 60–100 times in one frame, each wait a full trip to the host GPU.

## What carried across

- Don't assume 4 KB pages: the guest's `0xE0000000` view and write-watches both broke on larger pages.
- Put back the guest's memory barriers on ARM, and don't rely on `volatile` to order anything there.
- Waits differ by OS: Windows rounds short sleeps to yields, Linux denies real-time priorities, and polling multi-waits burn CPU everywhere.
- Keep I/O, audio device opens and `mprotect` off any process-wide lock.
- Measure each GPU separately. Texture gamma saved 8 % on the M4 Pro and nothing on the RTX 4080; partial resolves saved 3 % on the Deck and nothing on the desktop.
