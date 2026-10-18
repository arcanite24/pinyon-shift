---
title: Overview
section: Internals
order: 1
description: Engineering notes on how Pinyon Shift recompiles, runs and renders Forza Horizon, written for people working on other Xbox 360 recompilations.
---

# Internals

These pages record how Pinyon Shift works and what was measured along the way, so that later Xbox 360 recompilation projects can reuse what held up and skip what didn't. They describe the code on the `dev` branch in October 2026.

- [Recompiler](recompiler.md): from `default.xex` to C++, function discovery, code generation and the Xenon behaviours that had to match.
- [Runtime and hooks](runtime.md): guest memory, the kernel, threads, waits, files, audio, mid-asm hooks, the frame-rate unlock and the title update build.
- [Native renderer](renderer.md): the threads, the frame contract, EDRAM and resolves, textures, shaders and the present path.
- [GPU optimizations](gpu-optimizations.md): what was slow on the GPU and the recorder thread, what changed and what it measured.
- [Platform ports](platforms.md): Windows, Linux and the Steam Deck, macOS and Android.
- [macOS renderer performance](macos-renderer.md): the M1 frame from 131 to 19 ms on MoltenVK, as a method for other recompilations.
- [Lessons](lessons.md): what carries over to other projects, including what didn't work.

## The system

Pinyon Shift translates the game's PowerPC code to C++ ahead of time, on the player's machine, and links it with a runtime that stands in for the Xbox 360's kernel, memory, files, audio, input and GPU. Nothing is interpreted or JIT-compiled while the game runs.

{{diagram:system-overview|The build runs once per install; the running game is translated code plus the ShiftGlue runtime and a renderer written for this one game.}}

Three parts carry most of the work:

| Part | Where | What it does |
| --- | --- | --- |
| ShiftGlue | [shiftglue-sdk](https://github.com/arcanite24/shiftglue-sdk), a fork of ReXGlue 0.10.0 | Recompiler, kernel and XAM HLE, memory, threads, audio, input, the Vulkan backend |
| FH1 native executor | ShiftGlue, `src/graphics/vulkan/fh1_native_executor.cpp` | Render targets, resolves, clears and swap for *Forza Horizon* only |
| Host code | this repository, `src/` | Settings, saves, mods, hooks into the game, the frame-rate fixes |

The guest-to-host contract is narrow: the translated code calls the runtime through kernel exports and the GPU ring buffer, and host code reaches into the game only through hooks declared in configuration. Game files on disc are never modified, and the repository holds no game code or data.

## Facts at a glance

| | |
| --- | --- |
| Game | *Forza Horizon*, USA retail disc `MS-2505`, title ID `4D5309C9`; optional title update v4 |
| Executable images | `default.xex` plus two facade modules the game loads |
| Translated functions | about 76,500 (base) |
| Generated source | about 260 C++ files, about 300 MB |
| Hooks into game code | 130 mid-asm hooks, a few whole-function replacements |
| Guest threads in a race | about 42, mapped one to one to host threads |
| Draws per race frame | about 4,500 to 6,200 |
| Graphics API | Vulkan 1.3 on every platform |
| Frame rate | 30, 40, 60 or 120 fps, game speed unchanged |

## Where the details are

These pages summarize. The engineering record, with every measurement and the reasoning behind each decision, is in the repository's [docs/](https://github.com/arcanite24/pinyon-shift/tree/dev/docs):

| Topic | Document |
| --- | --- |
| Moving off the Xenos emulation path | [NATIVE_PORT_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/NATIVE_PORT_BACKLOG.md), [XENOS_RETIREMENT_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/XENOS_RETIREMENT_BACKLOG.md) |
| What a frame of the game contains | [NATIVE_FRAME_CONTRACT.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/native-renderer/NATIVE_FRAME_CONTRACT.md) |
| Desktop CPU and GPU work | [PERFORMANCE_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/PERFORMANCE_BACKLOG.md), [DESKTOP_RENDERER_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DESKTOP_RENDERER_BACKLOG.md), [RECORDER_PER_DRAW_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/RECORDER_PER_DRAW_BACKLOG.md), [RECORDER_REPLAY_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/RECORDER_REPLAY_BACKLOG.md) |
| Smaller PCs | [LOW_SPEC_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/LOW_SPEC_BACKLOG.md) |
| Android | [ANDROID_PORT_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/ANDROID_PORT_BACKLOG.md), [ANDROID_60FPS_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/ANDROID_60FPS_BACKLOG.md), [ANDROID_ODIN_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/ANDROID_ODIN_BACKLOG.md) |
| Linux and macOS | [LINUX_PORT_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/LINUX_PORT_BACKLOG.md), [MACOS.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS.md), [MACOS_RENDERER_OPTIMIZATION.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/MACOS_RENDERER_OPTIMIZATION.md) |
| The title update | [TITLE_UPDATE_V4_BACKLOG.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/TITLE_UPDATE_V4_BACKLOG.md) |
| Game internals found so far | [Reverse engineering](reverse-engineering.md), [Address index](game-addresses.md) |
| Other recompilers' optimizations | [RECOMP_OPTIMIZATION_SURVEY.md](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/RECOMP_OPTIMIZATION_SURVEY.md) |

Measurements on these pages name their machine. Unless stated otherwise, "desktop" is a Ryzen 7 5800X with an RTX 4080 on Windows 11, "Odin" is an AYN Odin 2 Portal (Adreno 740, Turnip), "8 Elite" is a RedMagic Astra (Adreno 830) and "Deck" is a Steam Deck LCD.
